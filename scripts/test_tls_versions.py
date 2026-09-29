#!/usr/bin/env python3
"""Check TLS protocol negotiation using only temporary, local test endpoints."""

import argparse
import contextlib
import json
from pathlib import Path
import queue
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import warnings


VERSIONS = [ssl.TLSVersion.TLSv1, ssl.TLSVersion.TLSv1_1,
            ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_3]
WALLET = "SC11pP3tKp5e5UJwTeTNhXQpv4UsbpmvTDSKRn22X1gLVTfJKyfJMbG6apw15backjJxGgi8pVT1sJA5p1etwT232pL2xUbKUB"


def listener():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    sock.settimeout(10)
    return sock


def free_port():
    with listener() as sock:
        return sock.getsockname()[1]


def tls_context(version, root=None):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER if root else ssl.PROTOCOL_TLS_CLIENT)
    if root:
        context.load_cert_chain(root / "cert.pem", root / "key.pem")
    else:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    # Intentionally permit legacy protocols in the TEST PEER, so rejection
    # must come from the proxy's protocol policy rather than this fixture.
    context.set_ciphers("ALL:@SECLEVEL=0")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        context.minimum_version = version
        context.maximum_version = version
    return context


@contextlib.contextmanager
def proxy(binary, root, name, pool, protocols=None, cli_protocols=None):
    directory = root / name
    directory.mkdir()
    miner_port, api_port = free_port(), free_port()
    config = directory / "config.json"
    config.write_text(json.dumps({
        "bind": [{"host": "127.0.0.1", "port": miner_port, "tls": True}],
        "pools": [pool], "mode": "nicehash", "watch": False, "colors": False,
        "http": {"enabled": True, "host": "127.0.0.1", "port": api_port, "restricted": True},
        "tls": {"enabled": True, "cert": str(root / "cert.pem"), "cert_key": str(root / "key.pem"),
                "protocols": protocols}, "log-file": str(directory / "events.log")
    }))
    command = [str(binary), "-c", str(config)]
    if cli_protocols is not None:
        command += ["--tls-protocols", cli_protocols]
    with (directory / "stdout.log").open("w") as output:
        child = subprocess.Popen(command, cwd=directory, stdin=subprocess.DEVNULL,
                                 stdout=output, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 10
            while True:
                assert child.poll() is None, "Test proxy exited"
                try:
                    with socket.create_connection(("127.0.0.1", miner_port), timeout=0.2):
                        break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise AssertionError("Test proxy did not start")
                    time.sleep(0.05)
            yield miner_port, api_port
        except BaseException:
            for file in (directory / "events.log", directory / "stdout.log"):
                if file.exists():
                    print(file.read_text(errors="replace")[-4000:])
            raise
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()


def check_inbound(port, version, expected):
    context = tls_context(version)
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=3) as raw:
            with context.wrap_socket(raw, server_hostname="localhost") as conn:
                assert expected, f"Unexpectedly negotiated {conn.version()} on {port}"
    except (ssl.SSLError, ConnectionResetError) as error:
        assert not expected, (version.name, port, error)


def check_outbound(binary, root, version, daemon):
    results = queue.Queue()
    server_context = tls_context(version, root)
    server = listener()
    def serve():
        try:
            raw, _ = server.accept()
            with raw:
                raw.settimeout(5)
                try:
                    with server_context.wrap_socket(raw, server_side=True) as conn:
                        data = conn.recv(8192)
                        results.put((True, data))
                except ssl.SSLError as error:
                    results.put((False, error.reason))
        except Exception as error:
            results.put(error)
    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    pool = {"url": f"127.0.0.1:{server.getsockname()[1]}", "tls": True, "coin": "SAL",
            "user": WALLET, "pass": "x", "daemon": daemon}
    try:
        with proxy(binary, root, f'outbound-{daemon}-{version.name}', pool):
            result = results.get(timeout=10)
            assert not isinstance(result, Exception), result
            allowed = version >= ssl.TLSVersion.TLSv1_2
            assert result[0] == allowed, (daemon, version.name, result)
            if allowed:
                assert (b"POST /json_rpc" if daemon else b'"method":"login"') in result[1], result
            else:
                assert result[1] == "UNSUPPORTED_PROTOCOL", result
    finally:
        thread.join(6)
        server.close()


def run(binary, root):
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                    "-subj", "/CN=localhost", "-keyout", str(root / "key.pem"),
                    "-out", str(root / "cert.pem")], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Only our own listener is used as an upstream for inbound handshake tests.
    with listener() as upstream:
        pool = {"url": f"127.0.0.1:{upstream.getsockname()[1]}", "coin": "SAL", "user": WALLET}
        selections = [None, "TLSv1 TLSv1.1 TLSv1.2 TLSv1.3", "TLSv1 TLSv1.1",
                      "TLSv1.2", "TLSv1.3"]
        for index, protocols in enumerate(selections):
            with proxy(binary, root, f"inbound-{index}", pool, protocols) as ports:
                for port in ports:
                    for version in VERSIONS:
                        expected = version >= ssl.TLSVersion.TLSv1_2
                        if protocols == "TLSv1.2":
                            expected = version == ssl.TLSVersion.TLSv1_2
                        elif protocols == "TLSv1.3":
                            expected = version == ssl.TLSVersion.TLSv1_3
                        check_inbound(port, version, expected)
            print(f"PASS: miner and API listeners enforce TLS 1.2 minimum; protocols={protocols!r}", flush=True)
        with proxy(binary, root, "inbound-cli", pool,
                   cli_protocols="TLSv1 TLSv1.1 TLSv1.2 TLSv1.3") as ports:
            for port in ports:
                for version in VERSIONS:
                    check_inbound(port, version, version >= ssl.TLSVersion.TLSv1_2)
            print("PASS: --tls-protocols cannot re-enable TLS 1.0 or 1.1", flush=True)

    for daemon in (False, True):
        for version in VERSIONS:
            check_outbound(binary, root, version, daemon)
        print(f'PASS: outgoing {"HTTPS daemon RPC" if daemon else "Stratum"} rejects TLS 1.0/1.1 and connects with TLS 1.2/1.3', flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proxy", type=Path, default=Path("build/xmrigcc-proxy"))
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="xmrigcc-tls-test-") as temporary:
        run(args.proxy.resolve(), Path(temporary))
    print("All TLS test processes stopped and temporary files removed.")
