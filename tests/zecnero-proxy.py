#!/usr/bin/env python3
"""Local Zecnero proxy protocol tests; optionally mine real regtest blocks."""
import argparse
import base64
import copy
import hashlib
import http.server
import json
import pathlib
import select
import signal
import socket
import socketserver
import ssl
import subprocess
import tempfile
import threading
import time
import urllib.request
from contextlib import contextmanager


PROXY_RPC_USER = 'integration-proxy'
PROXY_RPC_PASSWORD = 'integration-proxy-password-at-least-20-characters'


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def stop(proc):
    if proc and proc.poll() is None:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def wait_for(check, seconds=10):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError('Timed out waiting for test condition')


def make_certificate(root):
    ca = root / 'ca.pem'
    ca_key = root / 'ca-key.pem'
    cert = root / 'cert.pem'
    key = root / 'key.pem'
    request = root / 'cert.csr'
    extensions = root / 'cert.ext'
    extensions.write_text(
        'subjectAltName=DNS:localhost,IP:127.0.0.1\n'
        'basicConstraints=critical,CA:FALSE\n'
        'keyUsage=critical,digitalSignature,keyEncipherment\n'
        'extendedKeyUsage=serverAuth\n'
        'subjectKeyIdentifier=hash\n'
        'authorityKeyIdentifier=keyid,issuer\n')
    subprocess.run([
        'openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
        '-subj', '/CN=Zecnero proxy integration test CA',
        '-addext', 'basicConstraints=critical,CA:TRUE',
        '-addext', 'keyUsage=critical,keyCertSign,cRLSign',
        '-addext', 'subjectKeyIdentifier=hash',
        '-addext', 'authorityKeyIdentifier=keyid:always',
        '-keyout', str(ca_key), '-out', str(ca)], check=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run([
        'openssl', 'req', '-new', '-newkey', 'rsa:2048', '-nodes',
        '-subj', '/CN=localhost', '-keyout', str(key), '-out', str(request)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run([
        'openssl', 'x509', '-req', '-in', str(request), '-CA', str(ca),
        '-CAkey', str(ca_key), '-CAcreateserial', '-days', '1',
        '-extfile', str(extensions), '-out', str(cert)], check=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    der = ssl.PEM_cert_to_DER_cert(cert.read_text())
    return cert, key, hashlib.sha256(der).hexdigest()


def launch(binary, root, name, config, extra=()):
    config.setdefault('log-file', str(root / (name + '-events.log')))
    path = root / (name + '.json')
    path.write_text(json.dumps(config))
    with (root / (name + '.log')).open('wb') as log:
        return subprocess.Popen([str(binary), *extra, '-c', str(path)], cwd=root,
                                stdout=log, stderr=subprocess.STDOUT)


def proxy_config(upstream, listen, mode):
    return {'autosave': False, 'background': False, 'colors': False, 'watch': False,
            'donate-level': 0, 'donate-over-proxy': False, 'mode': mode,
            'verbose': True, 'retries': 2, 'retry-pause': 1,
            'bind': [{'host': '127.0.0.1', 'port': listen, 'tls': False}],
            'pools': [upstream]}


@contextmanager
def server(cls, handler):
    instance = cls(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield instance.server_address[1]
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join()


class Worker:
    def __init__(self, listen):
        def connect():
            try:
                return socket.create_connection(('127.0.0.1', listen), timeout=0.2)
            except OSError:
                return None
        self.sock = wait_for(connect)
        self.sock.settimeout(10)
        self.stream = self.sock.makefile('rb')
        self.sequence = 1
        self.send({'id': 1, 'method': 'login', 'params': {
            'login': 'worker', 'pass': 'x', 'agent': 'zecnero-proxy-test',
            'algo': ['rx/zecnero', 'rx/zecnero2']}})
        login = self.response(1)['result']
        self.rpc_id = login['id']
        self.job = login['job']
        self.extensions = login.get('extensions', [])

    def send(self, value):
        self.sock.sendall(json.dumps(value).encode() + b'\n')

    def receive(self):
        line = self.stream.readline()
        assert line, 'Proxy disconnected worker'
        value = json.loads(line)
        if value.get('method') == 'job':
            self.job = value['params']
        return value

    def response(self, request_id):
        while True:
            value = self.receive()
            if value.get('id') == request_id:
                return value

    def next_job(self, old_id):
        while self.job['job_id'] == old_id:
            self.receive()
        return self.job

    def submit(self, result='01' + '00' * 31, job=None, nonce=None, algo=True, commitment=None):
        job = job or self.job
        raw = bytes.fromhex(job['blob'])
        nonce = nonce or (b'\x01\x00\x00' + raw[111:112]).hex()
        self.sequence += 1
        params = {'id': self.rpc_id, 'job_id': job['job_id'], 'nonce': nonce, 'result': result}
        if algo:
            params['algo'] = job['algo']
        if commitment is not None:
            params['commitment'] = commitment
        self.send({'id': self.sequence, 'method': 'submit', 'params': params})
        return self.response(self.sequence)

    def close(self):
        self.stream.close()
        self.sock.close()


def rpc_tests(binary, root, mode):
    template = json.loads((pathlib.Path(__file__).parent / 'zecnero-template.json').read_text())
    state = {'template': template, 'cookie': 'test:secret', 'response': {'result': None},
             'submissions': [], 'auth': [], 'sync': False, 'requests': 0, 'notifications': []}
    cookie = root / (mode + '.cookie')
    cookie.write_text(state['cookie'])
    cookie.chmod(0o600)

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path == '/discord-test':
                state['notifications'].append(data['content'])
                self.send_response(204)
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            auth = self.headers.get('Authorization')
            state['auth'].append(auth)
            expected = 'Basic ' + base64.b64encode(state['cookie'].encode()).decode()
            # A request already in flight may use the previous cookie.
            if auth not in (expected, state.get('previous_auth')):
                self.send_response(401)
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            result = {'id': data['id'], 'jsonrpc': '2.0', 'error': None}
            if data['method'] == 'getblocktemplate':
                state['requests'] += 1
                if state['sync']:
                    result['error'] = {'code': -10, 'message': 'node syncing'}
                else:
                    if state.get('roll_time'):
                        state['template']['curtime'] += 1
                    result['result'] = copy.deepcopy(state['template'])
            else:
                assert data['method'] == 'submitblock'
                state['submissions'].append(bytes.fromhex(data['params'][0]))
                result.update(state['response'])
            body = json.dumps(result).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    proc = None
    workers = []
    with server(http.server.ThreadingHTTPServer, Handler) as rpc_port:
        try:
            listen = port()
            upstream = {'algo': 'randomx/zecnero', 'url': f'127.0.0.1:{rpc_port}',
                        'daemon': True, 'user': 'x', 'daemon-cookie-file': str(cookie),
                        'daemon-poll-interval': 1000, 'daemon-job-timeout': 15000}
            config = proxy_config(upstream, listen, mode)
            config['discord'] = {'enabled': True, 'webhook': f'http://127.0.0.1:{rpc_port}/discord-test',
                                 'notify-accepted': True, 'notify-rejected': False, 'accepted-interval': 0}
            proc = launch(binary, root, 'rpc-' + mode, config)
            a = Worker(listen)
            workers.append(a)
            b = Worker(listen)
            workers.append(b)
            assert len(a.job['blob']) == 280 and a.job['algo'] == 'rx/zecnero'
            assert a.job['seed_hash'] == template['seedhash']
            assert int.from_bytes(bytes.fromhex(a.job['target']), 'little') == int(template['target'][:16], 16)
            assert a.job['blob'] != b.job['blob'], 'Workers received overlapping work'
            assert ('nicehash' in a.extensions) == (mode == 'nicehash')

            # Real daemons advance curtime on every poll. That alone must not
            # bypass daemon-job-timeout and broadcast a new job every second.
            state['roll_time'] = True
            requests = state['requests']
            wait_for(lambda: state['requests'] >= requests + 3, 5)
            readable, _, _ = select.select([a.sock, b.sock], [], [], 0.2)
            assert not readable, 'Timestamp-only daemon polls were forwarded as new jobs'
            state['roll_time'] = False

            assert a.submit(result='gg' + '00' * 31).get('error'), 'Malformed hash accepted'
            assert a.submit(nonce='zz000000').get('error'), 'Malformed nonce accepted'
            above_target = (int(template['target'], 16) + 1).to_bytes(32, 'little').hex()
            assert a.submit(result=above_target).get('error'), 'Full 256-bit target not enforced'
            assert not state['submissions']

            for response in [{'result': 'bad-pow'}, {'result': ''}, {'result': False},
                             {'error': {'code': -1, 'message': 'rejected'}}, {}]:
                state['response'] = response
                # Equality must pass the daemon's inclusive 256-bit target check.
                exact_target = bytes.fromhex(template['target'])[::-1].hex()
                assert a.submit(result=exact_target).get('error'), f'Accepted rejection response: {response}'
            assert len(state['submissions']) == 5
            for block in state['submissions']:
                header = bytearray.fromhex(a.job['blob'])
                header[108:111] = b'\x01\x00\x00'
                assert block[:140] == header, 'Worker header changed during submission'
                assert block[140:142] == b'\x00\x01'
                assert block[142:] == bytes.fromhex(template['coinbasetxn']['data'])

            # A valid low hash with a zero high word must not be rejected as diff 0.
            state['previous_auth'] = 'Basic ' + base64.b64encode(state['cookie'].encode()).decode()
            state['cookie'] = 'test:rotated'
            replacement = cookie.with_suffix('.new')
            replacement.write_text(state['cookie'] + '\n')
            replacement.chmod(0o600)
            replacement.replace(cookie)
            state['response'] = {'result': None}
            old = dict(a.job)
            assert not a.submit(algo=False).get('error'), 'Valid candidate rejected'
            wait_for(lambda: any('Height: 1\n' in message for message in state['notifications']))
            notification = next(message for message in state['notifications'] if 'Height: 1\n' in message)
            assert '\nCoin: Zecnero\nAlgorithm: rx/zecnero\n' in notification, notification
            a.next_job(old['job_id'])
            assert a.submit(job=old).get('error'), 'Stale candidate accepted'
            assert state['auth'][-1] == 'Basic ' + base64.b64encode(b'test:rotated').decode()

            previous = a.job['job_id']
            state['template']['powversion'] = 2
            state['template']['algo'] = 'rx/zecnero2'
            state['template']['height'] = 2
            a.next_job(previous)
            assert a.job['algo'] == 'rx/zecnero2'
            assert not a.submit(commitment='02' * 32).get('error')
            wait_for(lambda: any('Height: 2\n' in message for message in state['notifications']))
            notification = next(message for message in state['notifications'] if 'Height: 2\n' in message)
            assert '\nCoin: Zecnero\nAlgorithm: rx/zecnero2\n' in notification, notification
            a.next_job(a.job['job_id'])

            state['sync'] = True
            log = root / ('rpc-' + mode + '-events.log')
            wait_for(lambda: 'mining paused' in log.read_text())
            assert a.submit(commitment='02' * 32).get('error'), 'Syncing node accepted work'
            state['sync'] = False
            a.next_job(a.job['job_id'])
            assert not a.submit(commitment='02' * 32).get('error')
            print(f'PASS RPC {mode}: worker isolation, exact block encoding, rejection replies, cookie rotation, v1/v2, sync recovery, notification heights')
        finally:
            for worker in workers:
                worker.close()
            stop(proc)


def pool_tests(binary, root, algo):
    job = {'job_id': 'pool-1', 'algo': algo, 'blob': ('04' + '00' * 139),
           'target': 'ffff7f00', 'height': 12, 'seed_hash': '00' * 32}
    submissions = []

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            for line in self.rfile:
                request = json.loads(line)
                if request['method'] == 'login':
                    result = {'id': 'pool-session', 'job': job, 'extensions': ['algo']}
                    error = None
                elif request['method'] == 'submit':
                    submissions.append(request['params'])
                    result = {'status': 'OK'}
                    error = None if len(submissions) > 1 else {'code': -1, 'message': 'test rejection'}
                else:
                    result, error = {'status': 'KEEPALIVED'}, None
                self.wfile.write(json.dumps({'id': request['id'], 'result': result, 'error': error}).encode() + b'\n')
                self.wfile.flush()

    class TCPServer(socketserver.ThreadingTCPServer):
        daemon_threads = True

    proc = worker = None
    with server(TCPServer, Handler) as pool_port:
        try:
            listen = port()
            upstream = {'algo': algo, 'url': f'127.0.0.1:{pool_port}', 'user': 'wallet', 'pass': 'x'}
            proc = launch(binary, root, 'pool-' + algo.replace('/', '-'), proxy_config(upstream, listen, 'nicehash'))
            worker = Worker(listen)
            assert worker.job['algo'] == algo and worker.job['seed_hash'] == job['seed_hash']
            assert worker.job['target'] == job['target']
            commitment = '02' * 32 if algo == 'rx/zecnero2' else None
            if commitment is not None:
                assert worker.submit().get('error'), 'v2 share without RandomX hash accepted'
                assert worker.submit(commitment='zz' * 32).get('error'), 'malformed v2 RandomX hash accepted'
                assert not submissions
            assert worker.submit(commitment=commitment).get('error')
            assert not worker.submit(commitment=commitment).get('error')
            assert len(submissions) == 2 and submissions[-1]['job_id'] == 'pool-1'
            assert submissions[-1]['algo'] == algo
            assert submissions[-1]['nonce'][6:] == worker.job['blob'][222:224]
            if commitment is not None:
                assert submissions[-1]['commitment'] == commitment
            else:
                assert 'commitment' not in submissions[-1]
            print(f'PASS pool {algo}: header/target/seed forwarding and accepted/rejected replies')
        finally:
            if worker:
                worker.close()
            stop(proc)


def miner_pool_test(binary, miner_binary, root):
    """Mine across v1 -> v2 through the proxy and verify the v2 proof fields upstream."""
    root.mkdir()
    blob = bytearray(140)
    blob[0] = 4
    job_v1 = {'job_id': 'v1-integration', 'algo': 'rx/zecnero', 'blob': blob.hex(),
              'target': 'ffffffff', 'height': 1, 'seed_hash': '00' * 32}
    job_v2 = dict(job_v1, job_id='v2-integration', algo='rx/zecnero2', height=2)
    state = {'v1': None, 'v2': None, 'error': None}

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            try:
                for line in self.rfile:
                    request = json.loads(line)
                    next_job = None
                    if request['method'] == 'login':
                        result = {'id': 'v2-pool-session', 'job': job_v1, 'extensions': ['algo']}
                    elif request['method'] == 'submit':
                        params = request['params']
                        if params['algo'] == 'rx/zecnero':
                            assert 'commitment' not in params
                            state['v1'] = params
                            next_job = job_v2
                        else:
                            randomx_hash = bytes.fromhex(params['commitment'])
                            proof_input = bytearray(blob)
                            proof_input[108:112] = bytes.fromhex(params['nonce'])
                            expected = hashlib.blake2b(proof_input + randomx_hash, digest_size=32).hexdigest()
                            assert params['algo'] == 'rx/zecnero2'
                            assert params['result'] == expected
                            state['v2'] = params
                        result = {'status': 'OK'}
                    else:
                        result = {'status': 'KEEPALIVED'}
                    self.wfile.write(json.dumps({'id': request['id'], 'result': result, 'error': None}).encode() + b'\n')
                    if next_job is not None:
                        self.wfile.write(json.dumps({'jsonrpc': '2.0', 'method': 'job', 'params': next_job}).encode() + b'\n')
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as exc:
                state['error'] = exc

    class TCPServer(socketserver.ThreadingTCPServer):
        daemon_threads = True

    proxy = miner = None
    with server(TCPServer, Handler) as pool_port:
        try:
            listen = port()
            upstream = {'algo': 'rx/zecnero', 'url': f'127.0.0.1:{pool_port}',
                        'user': 'wallet', 'pass': 'x'}
            proxy = launch(binary, root, 'v2-proxy', proxy_config(upstream, listen, 'simple'))
            config = {'autosave': False, 'background': False, 'colors': False, 'watch': False,
                      'donate-level': 0, 'dmi': False,
                      'randomx': {'mode': 'auto', 'init': 1, 'rdmsr': False, 'wrmsr': False, 'numa': False},
                      'cpu': {'enabled': True, 'huge-pages': False,
                              'rx/zecnero': [-1], 'rx/zecnero2': [-1]},
                      'opencl': False, 'cuda': False, 'cc-client': {'enabled': False},
                      'pools': [{'algo': 'rx/zecnero', 'url': f'127.0.0.1:{listen}',
                                 'user': 'worker', 'pass': 'x'}]}
            miner = launch(miner_binary, root, 'v2-miner', config, ['--daemonized'])

            def submitted():
                assert state['error'] is None, state['error']
                assert proxy.poll() is None and miner.poll() is None, 'Proxy/miner exited early'
                return state['v1'] and state['v2']

            wait_for(submitted, 60)
            miner_log = (root / 'v2-miner-events.log').read_text()
            assert miner_log.count('init dataset') == 1, 'v1/v2 switch rebuilt the shared dataset'
            assert 'algo rx/zecnero height 1' in miner_log and 'algo rx/zecnero2 height 2' in miner_log
            print('PASS miner -> proxy -> pool v1/v2 switch, commitment and RandomX hash')
        finally:
            stop(miner)
            stop(proxy)


def regtest(binary, node_binary, miner_binary, root, mode, connection, nu1_height=None):
    root.mkdir()
    rpc_port, miner_rpc_port, listen = port(), port(), port()
    cookie = root / 'rpc/.cookie'
    miner_cookie = root / 'proxy-miner.cookie'
    cert, key, fingerprint = make_certificate(root)
    credentials = root / 'miner-clients.toml'
    credentials.write_text(f'''[[client]]
username = "{PROXY_RPC_USER}"
password = "{PROXY_RPC_PASSWORD}"
profile = "pool"
''')
    credentials.chmod(0o600)
    activation_heights = ''
    if nu1_height is not None:
        activation_heights = f'''[network.testnet_parameters.activation_heights]
NU6 = 1
"NU6.2" = {nu1_height}
'''
    (root / 'node.toml').write_text(f'''[network]
network = "Regtest"
listen_addr = "127.0.0.1:{port()}"
[network.testnet_parameters]
experimental_randomx_v2 = true
{activation_heights}
[state]
ephemeral = true
[rpc]
listen_addr = "127.0.0.1:{rpc_port}"
enable_cookie_auth = true
cookie_dir = "{root}/rpc"
debug_force_finished_sync = true
[rpc.tls]
mode = "auto"
cert_path = "{cert}"
key_path = "{key}"
[rpc.miner]
listen_addr = "127.0.0.1:{miner_rpc_port}"
credentials_file = "{credentials}"
cookie_ttl_seconds = 300
max_connections = 32
max_connections_per_ip = 16
max_requests_per_minute = 6000
max_bootstrap_attempts_per_minute = 100
[rpc.miner.tls]
mode = "auto"
cert_path = "{cert}"
key_path = "{key}"
[mining]
miner_address = "nmH2sBPxwa1KyUGqPf37WMsk9ZQrWM7uZ67"
[tracing]
use_color = false
''')

    def rpc(method, params):
        request = urllib.request.Request(f'http://127.0.0.1:{rpc_port}/',
            data=json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}).encode(),
            headers={'Content-Type': 'application/json', 'Authorization': 'Basic ' +
                     base64.b64encode(cookie.read_bytes().strip()).decode()})
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.load(response)
        if data.get('error'):
            raise RuntimeError(data['error'])
        return data['result']

    node = proxy = miner = None
    try:
        with (root / 'node.log').open('wb') as log:
            node = subprocess.Popen([str(node_binary), '-c', str(root / 'node.toml')], cwd=root,
                                    stdout=log, stderr=subprocess.STDOUT)

        def ready():
            try:
                return rpc('getblocktemplate', [{}])
            except (OSError, RuntimeError):
                assert node.poll() is None, 'Node exited early'
                return None
        template = wait_for(ready, 60)
        assert template['height'] == 1 and template['powversion'] == 1
        upstream = {'algo': 'rx/zecnero', 'daemon': True,
                    'user': 'x', 'daemon-poll-interval': 1000}
        if connection == 'full':
            upstream.update({'url': f'127.0.0.1:{rpc_port}',
                             'tls': True, 'tls-fingerprint': fingerprint,
                             'daemon-cookie-file': str(cookie)})
        elif connection == 'http':
            upstream.update({'url': f'127.0.0.1:{miner_rpc_port}', 'tls': False})
        elif connection == 'tls':
            upstream.update({
                'url': f'127.0.0.1:{miner_rpc_port}', 'tls': True,
                'rpc-login': f'{PROXY_RPC_USER}:{PROXY_RPC_PASSWORD}',
                'daemon-cookie-source': f'https://127.0.0.1:{miner_rpc_port}/mining/cookie',
                'daemon-cookie-file': str(miner_cookie),
                'daemon-cookie-fingerprint': fingerprint})
        else:
            raise AssertionError(f'unknown connection profile: {connection}')
        proxy = launch(binary, root, 'proxy', proxy_config(upstream, listen, mode))
        config = {'autosave': False, 'background': False, 'colors': False, 'watch': False,
                  'donate-level': 0, 'dmi': False, 'log-file': str(root / 'miner-events.log'),
                  'randomx': {'mode': 'auto', 'init': 2, 'rdmsr': False, 'wrmsr': False, 'numa': False},
                  'cpu': {'enabled': True, 'huge-pages': False, 'rx/zecnero': [-1], 'rx/zecnero2': [-1]},
                  'opencl': False, 'cuda': False, 'cc-client': {'enabled': False},
                  'pools': [{'algo': 'rx/zecnero', 'url': f'127.0.0.1:{listen}', 'user': 'worker', 'pass': 'x'}]}
        miner = launch(miner_binary, root, 'miner', config, ['--daemonized'])

        target_blocks = max(3, (nu1_height or 0) + 3)

        def mined():
            assert proxy.poll() is None and miner.poll() is None, 'Proxy/miner exited early'
            info = rpc('getblockchaininfo', [])
            return info if info['blocks'] >= target_blocks else None
        info = wait_for(mined, 180)
        stop(miner)
        block = bytes.fromhex(rpc('getblock', ['1', 0]))
        assert block[140:142] == b'\x00\x01'
        assert block[142:] == bytes.fromhex(template['coinbasetxn']['data'])
        assert rpc('getblocktemplate', [{}])['powversion'] == 2
        log = (root / 'miner-events.log').read_text()
        assert 'algo rx/zecnero height 1' in log and 'algo rx/zecnero2 height 2' in log
        rejected = [line for line in log.splitlines() if 'rejected' in line.lower()]
        # Regtest finds more candidates while the node validates its first block.
        # These are explicitly declined, not reported as daemon-accepted blocks.
        assert all('Block submission already pending' in line or 'Invalid job id' in line or
                   'Incorrect algorithm' in line for line in rejected), rejected
        proxy_log = (root / 'proxy-events.log').read_text()
        assert proxy_log.count('Zecnero block accepted by node') >= 3
        assert 'rejected (' not in proxy_log, 'Daemon rejected a submitted block'
        if connection == 'tls':
            assert miner_cookie.read_text().startswith('__miner__:')
            assert miner_cookie.stat().st_mode & 0o077 == 0
        boundary = f', NU1 activation at {nu1_height}' if nu1_height is not None else ''
        print(f"PASS real regtest {mode}/{connection}: {info['blocks']} PoW-validated blocks, v1/v2 activation{boundary}, intact coinbase, no daemon rejections; {len(rejected)} pending/stale candidates declined locally")
    finally:
        stop(miner)
        stop(proxy)
        stop(node)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proxy', required=True, type=pathlib.Path)
    parser.add_argument('--node', type=pathlib.Path)
    parser.add_argument('--miner', type=pathlib.Path)
    parser.add_argument('--nu1-height', type=int,
                        help='configure Regtest NU1 at this height and mine three blocks past it')
    args = parser.parse_args()
    if args.node and not args.miner:
        parser.error('--node requires --miner')
    if args.nu1_height is not None and args.nu1_height < 2:
        parser.error('--nu1-height must be at least 2')
    root = pathlib.Path(tempfile.mkdtemp(prefix='zecnero-proxy-test-'))
    print(f'Test artifacts: {root}', flush=True)
    binary = args.proxy.resolve()
    for mode in ['nicehash', 'simple', 'extra_nonce']:
        rpc_tests(binary, root, mode)
    for algo in ['rx/zecnero', 'rx/zecnero2']:
        pool_tests(binary, root, algo)
    if args.miner:
        miner_pool_test(binary, args.miner.resolve(), root / 'miner-pool-v2')
    if args.node:
        scenarios = [('nicehash', 'full'), ('simple', 'http'), ('extra_nonce', 'tls')]
        for mode, connection in scenarios:
            regtest(binary, args.node.resolve(), args.miner.resolve(),
                    root / f'regtest-{mode}-{connection}', mode, connection, args.nu1_height)


if __name__ == '__main__':
    main()
