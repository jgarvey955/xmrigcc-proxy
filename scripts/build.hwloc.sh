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
        printf '%s\n' "curl or wget is required to download hwloc." >&2
        exit 1
    fi
}

jobs() {
    nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || sysctl -n hw.logicalcpu 2>/dev/null || printf '1\n'
}

HWLOC_TAG="${HWLOC_VERSION:-2.15.0}"
HWLOC_VERSION="${HWLOC_TAG#hwloc-}"
HWLOC_SERIES="${HWLOC_VERSION%.*}"
HWLOC_URL="https://download.open-mpi.org/release/hwloc/v${HWLOC_SERIES}/hwloc-${HWLOC_VERSION}.tar.gz"

if [ -z "$HWLOC_VERSION" ] || [ -z "$HWLOC_URL" ]; then
    printf '%s\n' "Unable to determine latest hwloc release." >&2
    exit 1
fi

printf 'Building hwloc %s\n' "$HWLOC_VERSION"
download "$HWLOC_URL" "hwloc-${HWLOC_VERSION}.tar.gz"
rm -rf "hwloc-${HWLOC_VERSION}"
tar -xzf "hwloc-${HWLOC_VERSION}.tar.gz"

cd "hwloc-${HWLOC_VERSION}"
./configure --disable-shared --enable-static --disable-io --disable-libudev --disable-libxml2
make -j"$(jobs)"
cp -fr include ../../deps
cp hwloc/.libs/libhwloc.a ../../deps/lib
