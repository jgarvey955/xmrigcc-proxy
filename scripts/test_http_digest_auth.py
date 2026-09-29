#!/usr/bin/env python3
"""Cross-check Digest responses with hashlib, including malformed challenges.

Requires a C++ compiler and OpenSSL development libraries; uses temporary files.
"""

import hashlib
from pathlib import Path
import subprocess
import tempfile
from urllib.request import parse_http_list, parse_keqv_list


ROOT = Path(__file__).resolve().parents[1]
DRIVER = r'''
#include "base/net/http/HttpDigestAuth.h"
#include <iostream>
int main(int argc, char **argv) {
    if (argc != 5) { return 2; }
    std::cout << xmrig::HttpDigestAuth::authorization(argv[1], argv[2], argv[3], argv[4]);
}
'''


with tempfile.TemporaryDirectory(prefix="xmrigcc-digest-unit-") as temporary:
    root = Path(temporary)
    driver = root / "driver.cpp"
    binary = root / "digest-test"
    driver.write_text(DRIVER)
    subprocess.run(["c++", "-std=c++11", "-DXMRIG_FEATURE_TLS", "-I", str(ROOT / "src"),
                    str(driver), str(ROOT / "src/base/net/http/HttpDigestAuth.cpp"),
                    "-lcrypto", "-o", str(binary)], check=True)

    def response(challenge, login="test-user:pass:word", method="POST", uri="/json_rpc"):
        return subprocess.check_output([str(binary), challenge, login, method, uri], text=True)

    for algorithm in ("MD5", "MD5-sess", "SHA-256", "SHA-256-sess"):
        for qop in (None, "auth", "auth-int, auth"):
            for method, uri in (("GET", "/getheight"), ("POST", "/json_rpc")):
                challenge = f'Digest realm="monero-rpc", nonce="test-nonce", algorithm={algorithm}, opaque="test-opaque"'
                if qop is not None:
                    challenge += f', qop="{qop}"'
                header = response(challenge, method=method, uri=uri)
                assert header.startswith("Digest "), header
                fields = parse_keqv_list(parse_http_list(header[7:]))
                def h(value):
                    return hashlib.new("md5" if algorithm.startswith("MD5") else "sha256", value.encode()).hexdigest()
                a1 = h("test-user:monero-rpc:pass:word")
                if algorithm.endswith("-sess"):
                    a1 = h(a1 + ":test-nonce:" + fields["cnonce"])
                a2 = h(method + ":" + uri)
                expected = h(a1 + ":test-nonce:" +
                             ("00000001:" + fields["cnonce"] + ":auth:" if qop is not None else "") + a2)
                assert fields["response"] == expected, (algorithm, qop, method, header)
                assert fields["uri"] == uri and fields["opaque"] == "test-opaque"
    print("PASS: 24 independent Digest hash checks (GET/POST, MD5/SHA-256, session variants, qop lists)")

    challenge = 'Digest realm="monero-rpc", nonce="test", qop="auth"'
    assert response(challenge)  # omitted algorithm defaults to MD5
    assert response(challenge, "user:")  # explicit empty password
    assert response(challenge, 'us"er:password')
    assert response('Digest realm="escaped\\\"realm",nonce="test",qop="auth"')
    first = response(challenge)
    assert first != response(challenge), "Each exchange needs a fresh cnonce"
    for bad in ("user", ":password", "user\r\n:password"):
        assert not response(challenge, bad)
    for bad in (
        'Basic realm="test"',
        'Digest realm="test"',
        'Digest realm="test",nonce=""',
        'Digest realm="test",nonce="n",qop="auth-int"',
        'Digest realm="test",nonce="n",algorithm=unknown',
        'Digest realm="test",nonce="n",userhash=true',
        'Digest realm="test",nonce="n",nonce="duplicate"',
        'Digest realm="test",nonce="unterminated',
        'Digest realm="test",nonce="n\r\nInjected: value"',
        'Digest realm="test",nonce="n",',
    ):
        assert not response(bad), bad
    print("PASS: credential validation, escaping, fresh cnonce, and unsupported/malformed challenge rejection")
