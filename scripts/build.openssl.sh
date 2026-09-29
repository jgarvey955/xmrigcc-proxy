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
        curl -fL "$url" -o "$out"
    elif command -v wget >/dev/null 2>&1; then
        wget "$url" -O "$out"
    else
        printf '%s\n' "curl or wget is required to download OpenSSL." >&2
        exit 1
    fi
}

latest_release_field() {
    repo="$1"
    pattern="$2"

    release_json=".openssl-release.json"
    download "https://api.github.com/repos/${repo}/releases/latest" "$release_json" >/dev/null
    sed -n "$pattern" "$release_json" | head -n 1
}

jobs() {
    nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || sysctl -n hw.logicalcpu 2>/dev/null || printf '1\n'
}

OPENSSL_TAG="${OPENSSL_VERSION:-$(latest_release_field openssl/openssl 's/.*"tag_name": *"\([^"]*\)".*/\1/p')}"
OPENSSL_VERSION="${OPENSSL_TAG#openssl-}"
OPENSSL_URL="$(latest_release_field openssl/openssl 's/.*"browser_download_url": *"\([^"]*openssl-[0-9][^"]*\.tar\.gz\)".*/\1/p')"

if [ -z "$OPENSSL_VERSION" ] || [ -z "$OPENSSL_URL" ]; then
    printf '%s\n' "Unable to determine latest OpenSSL release." >&2
    exit 1
fi

printf 'Building OpenSSL %s\n' "$OPENSSL_VERSION"
download "$OPENSSL_URL" "openssl-${OPENSSL_VERSION}.tar.gz"
rm -rf "openssl-${OPENSSL_VERSION}"
tar -xzf "openssl-${OPENSSL_VERSION}.tar.gz"

cd "openssl-${OPENSSL_VERSION}"
./config -no-shared -no-asm -no-zlib -no-comp -no-dgram -no-filenames -no-cms
make -j"$(jobs)"
cp -fr include ../../deps
cp libcrypto.a ../../deps/lib
cp libssl.a ../../deps/lib
