#!/bin/sh -e

cd "$(dirname "$0")"

SCRIPT_DIR=$(pwd)
DEPS_DIR="$SCRIPT_DIR/deps"

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
        printf '%s\n' "curl or wget is required to download libuv." >&2
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

UV_VERSION="${UV_VERSION:-1.53.0}"
UV_VERSION="${UV_VERSION#v}"
UV_SHA256="${UV_SHA256:-cb0d6dd2128d5a95bd242c6cc982a24fe608fa93da57b6b4ec763b0018c53e64}"
. "$SCRIPT_DIR/dependency-cache.sh"

if [ -z "$UV_VERSION" ]; then
    printf '%s\n' "Unable to determine latest libuv release." >&2
    exit 1
fi

if dependency_is_current libuv "$UV_VERSION" "$DEPS_DIR/include/uv.h" "$DEPS_DIR/lib/libuv.a"; then
    exit 0
fi

printf 'Building libuv %s\n' "$UV_VERSION"
download "https://dist.libuv.org/dist/v${UV_VERSION}/libuv-v${UV_VERSION}.tar.gz" "libuv-v${UV_VERSION}.tar.gz"
verify_sha256 "libuv-v${UV_VERSION}.tar.gz" "$UV_SHA256"
rm -rf "libuv-v${UV_VERSION}"
tar -xzf "libuv-v${UV_VERSION}.tar.gz"

cmake -S "libuv-v${UV_VERSION}" -B "libuv-v${UV_VERSION}/cmake-build" \
    -DCMAKE_BUILD_TYPE=Release -DLIBUV_BUILD_SHARED=OFF -DBUILD_TESTING=OFF
cmake --build "libuv-v${UV_VERSION}/cmake-build" --parallel "$(jobs)"
cp -R "libuv-v${UV_VERSION}/include/." ../deps/include/
cp "libuv-v${UV_VERSION}/cmake-build/libuv.a" ../deps/lib/
dependency_mark_current libuv "$UV_VERSION"
printf '[libuv 100%%] Build complete\n'
