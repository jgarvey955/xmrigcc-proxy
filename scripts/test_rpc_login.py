#!/usr/bin/env python3
"""Test against a NEW offline Salvium regtest daemon. Never accepts a daemon URL.

Requires Python requests. Every daemon/proxy gets a temporary configuration,
temporary data, and unused loopback ports. Only child processes are stopped.
"""

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import threading
import time

import requests
from requests.auth import HTTPDigestAuth


WALLET = "SC11pP3tKp5e5UJwTeTNhXQpv4UsbpmvTDSKRn22X1gLVTfJKyfJMbG6apw15backjJxGgi8pVT1sJA5p1etwT232pL2xUbKUB"
LOGIN = "proxy-test:password:with:colons"


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for(check, seconds=20):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(0.05)
    raise AssertionError("Timed out waiting for test condition")


@contextlib.contextmanager
def process(args, directory, label):
    log = directory / (label + ".log")
    env = os.environ.copy()
    env.pop("RPC_LOGIN", None)
    with log.open("w") as output:
        child = subprocess.Popen(args, cwd=directory, env=env, stdin=subprocess.DEVNULL,
                                 stdout=output, stderr=subprocess.STDOUT)
        try:
            yield child, log
        except BaseException:
            print(log.read_text(errors="replace")[-6000:])
            raise
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()


class Daemon:
    def __init__(self, port, authenticated, certificate=None):
        self.port = port
        self.tls = certificate is not None
        self.url = f'{"https" if self.tls else "http"}://127.0.0.1:{port}'
        self.fingerprint = None
        self.session = requests.Session()
        self.session.trust_env = False
        if certificate:
            self.session.verify = str(certificate)
            self.fingerprint = hashlib.sha256(ssl.PEM_cert_to_DER_cert(certificate.read_text())).hexdigest()
        if authenticated:
            self.session.auth = HTTPDigestAuth(*LOGIN.split(":", 1))

    def get(self, path):
        response = self.session.get(self.url + path, timeout=30)
        response.raise_for_status()
        return response.json()

    def rpc(self, method, params):
        response = self.session.post(self.url + "/json_rpc", timeout=60,
                                     json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        response.raise_for_status()
        value = response.json()
        assert "error" not in value, value
        return value["result"]


@contextlib.contextmanager
def daemon_process(binary, directory, authenticated=True, tls=False):
    directory.mkdir()
    port, p2p = free_port(), free_port()
    config = directory / "daemon.conf"
    config.write_text(f"rpc-login={LOGIN}\n" if authenticated else "# No RPC authentication\n")
    certificate = directory / "cert.pem" if tls else None
    if tls:
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                        "-subj", "/CN=localhost", "-addext", "subjectAltName=IP:127.0.0.1",
                        "-keyout", str(directory / "key.pem"), "-out", str(certificate)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    args = [str(binary), "--config-file", str(config), "--data-dir", str(directory / "data"),
            "--log-file", str(directory / "daemon-internal.log"), "--regtest", "--offline",
            "--fixed-difficulty", "1", "--non-interactive", "--disable-dns-checkpoints", "--no-igd",
            "--no-zmq", "--rpc-bind-ip", "127.0.0.1", "--rpc-bind-port", str(port),
            "--p2p-bind-ip", "127.0.0.1", "--p2p-bind-port", str(p2p), "--rpc-ssl", "enabled" if tls else "disabled",
            "--max-concurrency", "2", "--log-level", "0"]
    if tls:
        args += ["--rpc-ssl-certificate", str(certificate), "--rpc-ssl-private-key", str(directory / "key.pem")]
    with process(args, directory, "daemon") as (child, _):
        client = Daemon(port, authenticated, certificate)
        def ready():
            assert child.poll() is None, "Isolated daemon exited during startup"
            try:
                return client.get("/getheight").get("height")
            except requests.RequestException:
                return False
        wait_for(ready, 45)
        print(f"Isolated offline regtest RPC: 127.0.0.1:{port}", flush=True)
        try:
            yield client
        finally:
            client.session.close()


def daemon_pool(daemon, login=LOGIN):
    pool = {"url": f"127.0.0.1:{daemon.port}", "coin": "SAL", "user": WALLET,
            "daemon": True, "daemon-poll-interval": 100, "daemon-job-timeout": 60000,
            "tls": daemon.tls, "tls-fingerprint": daemon.fingerprint}
    if login is not None:
        pool["rpc-login"] = login
    return pool


@contextlib.contextmanager
def proxy_process(binary, directory, pools, cli_login=None, mode="nicehash"):
    directory.mkdir()
    port = free_port()
    config = directory / "proxy.json"
    event_log = directory / "proxy-events.log"
    config.write_text(json.dumps({"bind": [{"host": "127.0.0.1", "port": port}],
                                 "pools": pools, "mode": mode, "http": {"enabled": False},
                                 "tls": {"enabled": False}, "colors": False, "watch": False,
                                 "verbose": True, "retries": 1, "retry-pause": 1,
                                 "log-file": str(event_log)}))
    args = [str(binary), "--config", str(config)]
    if cli_login is not None:
        args += ["--url", pools[0]["url"], "--daemon", "--coin", "SAL",
                 "--user", WALLET, "--rpc-login", cli_login]
    with process(args, directory, "proxy") as (child, log):
        def connect():
            assert child.poll() is None, "Test proxy exited during startup"
            try:
                return socket.create_connection(("127.0.0.1", port), timeout=0.2)
            except OSError:
                return False
        sock = wait_for(connect)
        sock.settimeout(30)
        stream = sock.makefile("rwb")
        stream.write((json.dumps({"id": 1, "method": "login", "params": {
            "login": "test-miner", "pass": "x", "agent": "rpc-login-regression", "algo": ["rx/0"]}}) + "\n").encode())
        stream.flush()
        try:
            yield stream, event_log
        except BaseException:
            if event_log.exists():
                print(event_log.read_text(errors="replace")[-6000:])
            raise
        finally:
            stream.close()
            sock.close()


def receive(stream):
    line = stream.readline()
    assert line, "Proxy closed miner connection"
    value = json.loads(line)
    assert not value.get("error"), value
    return value


@contextlib.contextmanager
def fake_pool(template):
    """A local Stratum stand-in to test fallback without contacting an online pool."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    server.settimeout(0.2)
    stop = threading.Event()
    logins = []
    errors = []
    def run():
        try:
            while not stop.is_set():
                try:
                    conn, _ = server.accept()
                except socket.timeout:
                    continue
                with conn:
                    conn.settimeout(0.2)
                    data = b""
                    while b"\n" not in data and not stop.is_set():
                        try:
                            chunk = conn.recv(8192)
                            if not chunk:
                                break
                            data += chunk
                        except socket.timeout:
                            continue
                    if not data:
                        continue
                    login = json.loads(data.split(b"\n")[0])
                    logins.append(login)
                    job = {"blob": template["blockhashing_blob"], "job_id": "fallback-job",
                           "target": "ffffffff", "algo": "rx/0", "seed_hash": template["seed_hash"],
                           "height": template["height"]}
                    reply = {"id": login["id"], "error": None,
                             "result": {"id": "test-pool", "job": job, "status": "OK"}}
                    conn.sendall((json.dumps(reply) + "\n").encode())
                    stop.wait(10)
        except Exception as error:
            errors.append(error)
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    try:
        yield server.getsockname()[1], logins, errors
    finally:
        stop.set()
        thread.join(2)
        server.close()


def run(args, root):
    with daemon_process(args.daemon, root / "authenticated") as daemon:
        with requests.Session() as session:
            session.trust_env = False
            response = session.get(f"http://127.0.0.1:{daemon.port}/getheight", timeout=5)
            assert response.status_code == 401
        template = daemon.rpc("getblocktemplate", {"wallet_address": WALLET, "extra_nonce": "00" * 8})
        assert template["difficulty"] == 1
        with proxy_process(args.proxy, root / "good-login", [daemon_pool(daemon)]) as (stream, log):
            login = receive(stream)["result"]
            job = login["job"]
            assert job["height"] == template["height"] and job["algo"] == "rx/0"
            # At fixed difficulty 1 every nonce is valid. The daemon checks PoW;
            # the synthetic hash only satisfies the proxy's share prefilter.
            # The initial login job may precede assignment of proxy_mapper_id;
            # read the assigned nonce directly from the CryptoNote header.
            blob = bytes.fromhex(job["blob"])
            offset = 0
            for _ in range(3):  # major version, minor version, timestamp
                while blob[offset] & 0x80:
                    offset += 1
                offset += 1
            nonce = blob[offset + 32:offset + 36].hex()
            stream.write((json.dumps({"id": 2, "method": "submit", "params": {
                "id": login["id"], "job_id": job["job_id"], "nonce": nonce,
                "result": "00" * 24 + "0100000000000000", "algo": "rx/0"}}) + "\n").encode())
            stream.flush()
            while True:
                reply = receive(stream)
                if reply.get("id") == 2:
                    assert reply["result"]["status"] == "OK"
                    break
            assert daemon.get("/getheight")["height"] == template["height"] + 1
            print("PASS: authenticated template, miner job, submitblock, and accepted regtest block", flush=True)
            daemon.rpc("generateblocks", {"wallet_address": WALLET, "amount_of_blocks": 1})
            expected_height = daemon.get("/getheight")["height"]
            while True:
                reply = receive(stream)
                if reply.get("method") == "job" and reply["params"]["height"] == expected_height:
                    break
            assert LOGIN not in log.read_text()
            print("PASS: authenticated height polling detects an independently generated block", flush=True)

        with proxy_process(args.proxy, root / "cli-login", [daemon_pool(daemon, None)], LOGIN) as (stream, _):
            assert receive(stream)["result"]["job"]["height"] == expected_height
            print("PASS: --rpc-login command-line option", flush=True)

        with proxy_process(args.proxy, root / "wrong-login", [daemon_pool(daemon, "proxy-test:wrong")]) as (_, log):
            wait_for(lambda: "authentication failed (HTTP 401)" in log.read_text())
            assert "new job" not in log.read_text()
            print("PASS: incorrect credentials rejected without issuing a mining job", flush=True)

        if args.notls_proxy:
            with proxy_process(args.notls_proxy, root / "notls-login", [daemon_pool(daemon)]) as (_, log):
                wait_for(lambda: "rpc-login requires a build with WITH_TLS=ON" in log.read_text())
                assert "new job" not in log.read_text()
                print("PASS: non-TLS binary reports the OpenSSL requirement explicitly", flush=True)

        with fake_pool(template) as (port, logins, errors):
            pools = [daemon_pool(daemon, "proxy-test:wrong"),
                     {"url": f"127.0.0.1:{port}", "user": "online-pool-wallet", "pass": "worker-password", "coin": "SAL"}]
            with proxy_process(args.proxy, root / "fallback", pools) as (stream, _):
                assert receive(stream)["result"]["job"]["job_id"] == "fallback-job"
                assert not errors, errors
                assert logins[0]["params"]["login"] == "online-pool-wallet"
                assert logins[0]["params"]["pass"] == "worker-password"
                assert "proxy-test" not in json.dumps(logins)
                print("PASS: authenticated daemon entry falls back to a normal Stratum pool with its own credentials", flush=True)

    with daemon_process(args.daemon, root / "unauthenticated", False) as daemon:
        with proxy_process(args.proxy, root / "no-login", [daemon_pool(daemon, None)]) as (stream, _):
            assert receive(stream)["result"]["job"]["height"] == 1
            print("PASS: daemon mining without RPC authentication remains supported", flush=True)

    with daemon_process(args.daemon, root / "https", tls=True) as daemon:
        with proxy_process(args.proxy, root / "tls-login", [daemon_pool(daemon)]) as (stream, _):
            assert receive(stream)["result"]["job"]["height"] == 1
            print("PASS: Digest authentication over HTTPS with certificate pinning", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proxy", type=Path, required=True)
    parser.add_argument("--daemon", type=Path, required=True)
    parser.add_argument("--notls-proxy", type=Path, help="Optional non-TLS binary to verify its error message")
    args = parser.parse_args()
    args.proxy, args.daemon = args.proxy.resolve(), args.daemon.resolve()
    if args.notls_proxy:
        args.notls_proxy = args.notls_proxy.resolve()
    with tempfile.TemporaryDirectory(prefix="xmrigcc-rpc-login-test-") as temporary:
        run(args, Path(temporary))
    print("All child processes stopped; temporary daemon data removed.")
