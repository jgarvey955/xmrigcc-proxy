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
        printf '%s\n' "curl or wget is required to download libuv." >&2
        exit 1
    fi
}

latest_release_tag() {
    repo="$1"

    release_json=".libuv-release.json"
    download "https://api.github.com/repos/${repo}/releases/latest" "$release_json" >/dev/null
    sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' "$release_json" | head -n 1
}

jobs() {
    nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || sysctl -n hw.logicalcpu 2>/dev/null || printf '1\n'
}

UV_VERSION="${UV_VERSION:-$(latest_release_tag libuv/libuv)}"
UV_VERSION="${UV_VERSION#v}"

if [ -z "$UV_VERSION" ]; then
    printf '%s\n' "Unable to determine latest libuv release." >&2
    exit 1
fi

printf 'Building libuv %s\n' "$UV_VERSION"
download "https://dist.libuv.org/dist/v${UV_VERSION}/libuv-v${UV_VERSION}.tar.gz" "libuv-v${UV_VERSION}.tar.gz"
rm -rf "libuv-v${UV_VERSION}"
tar -xzf "libuv-v${UV_VERSION}.tar.gz"

cd "libuv-v${UV_VERSION}"
sh autogen.sh
./configure --disable-shared
make -j"$(jobs)"
cp -fr include ../../deps
cp .libs/libuv.a ../../deps/lib
