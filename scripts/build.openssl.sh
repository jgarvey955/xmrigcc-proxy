#!/bin/sh -e

cd "$(dirname "$0")"

mkdir -p deps/include
mkdir -p deps/lib

mkdir -p build
cd build

download() {
    url="$1"
    out="$2"

    if command -v curl >/dev/null 2>&1; then
        curl -fL --retry 3 "$url" -o "$out"
    elif command -v wget >/dev/null 2>&1; then
        wget --tries=3 "$url" -O "$out"
    else
        printf '%s\n' "curl or wget is required to download OpenSSL." >&2
        exit 1
    fi
}

jobs() {
    if [ -n "${JOBS:-}" ]; then
        printf '%s\n' "$JOBS"
    else
        nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || sysctl -n hw.logicalcpu 2>/dev/null || printf '1\n'
    fi
}

verify_sha256() {
    actual=$(sha256sum "$1" | awk '{print $1}')
    [ "$actual" = "$2" ] || { printf 'SHA-256 mismatch for %s\n' "$1" >&2; exit 1; }
}

OPENSSL_TAG="${OPENSSL_VERSION:-4.0.3}"
OPENSSL_VERSION="${OPENSSL_TAG#openssl-}"
OPENSSL_SHA256="${OPENSSL_SHA256:-325b5c806167c13b40b1ffeadfe0248197c00eccc4cf123ec1e28d2d2fd216d9}"
OPENSSL_URL="https://github.com/openssl/openssl/releases/download/openssl-${OPENSSL_VERSION}/openssl-${OPENSSL_VERSION}.tar.gz"

if [ -z "$OPENSSL_VERSION" ] || [ -z "$OPENSSL_URL" ]; then
    printf '%s\n' "Unable to determine latest OpenSSL release." >&2
    exit 1
fi

printf 'Building OpenSSL %s\n' "$OPENSSL_VERSION"
download "$OPENSSL_URL" "openssl-${OPENSSL_VERSION}.tar.gz"
verify_sha256 "openssl-${OPENSSL_VERSION}.tar.gz" "$OPENSSL_SHA256"
rm -rf "openssl-${OPENSSL_VERSION}"
tar -xzf "openssl-${OPENSSL_VERSION}.tar.gz"

cd "openssl-${OPENSSL_VERSION}"
set -- no-shared no-zlib no-comp no-dgram no-filenames no-cms no-tests
if [ "${OPENSSL_VERSION%%.*}" -ge 4 ]; then
    set -- "$@" no-jitter no-fips-jitter
fi
./config "$@"
make -j"$(jobs)" build_libs
cp -fr include ../../deps
cp libcrypto.a ../../deps/lib
cp libssl.a ../../deps/lib
