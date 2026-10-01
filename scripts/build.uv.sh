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

jobs() {
    if [ -n "${JOBS:-}" ]; then
        printf '%s\n' "$JOBS"
    else
        nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || sysctl -n hw.logicalcpu 2>/dev/null || printf '1\n'
    fi
}

UV_VERSION="${UV_VERSION:-1.53.0}"
UV_VERSION="${UV_VERSION#v}"

if [ -z "$UV_VERSION" ]; then
    printf '%s\n' "Unable to determine latest libuv release." >&2
    exit 1
fi

printf 'Building libuv %s\n' "$UV_VERSION"
download "https://dist.libuv.org/dist/v${UV_VERSION}/libuv-v${UV_VERSION}.tar.gz" "libuv-v${UV_VERSION}.tar.gz"
rm -rf "libuv-v${UV_VERSION}"
tar -xzf "libuv-v${UV_VERSION}.tar.gz"

cmake -S "libuv-v${UV_VERSION}" -B "libuv-v${UV_VERSION}/cmake-build" \
    -DCMAKE_BUILD_TYPE=Release -DLIBUV_BUILD_SHARED=OFF -DBUILD_TESTING=OFF
cmake --build "libuv-v${UV_VERSION}/cmake-build" --parallel "$(jobs)"
cp -R "libuv-v${UV_VERSION}/include/." ../deps/include/
cp "libuv-v${UV_VERSION}/cmake-build/libuv.a" ../deps/lib/
printf '[libuv 100%%] Build complete\n'
