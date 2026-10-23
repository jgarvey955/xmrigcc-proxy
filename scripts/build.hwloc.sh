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
        printf '%s\n' "curl or wget is required to download hwloc." >&2
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

HWLOC_TAG="${HWLOC_VERSION:-2.15.0}"
HWLOC_VERSION="${HWLOC_TAG#hwloc-}"
HWLOC_SHA256="${HWLOC_SHA256:-f54bbdfc9f8015308c2e7bbab3e7789e47436a4a016689e5749a0c35d6877619}"
HWLOC_SERIES="${HWLOC_VERSION%.*}"
HWLOC_URL="https://download.open-mpi.org/release/hwloc/v${HWLOC_SERIES}/hwloc-${HWLOC_VERSION}.tar.gz"
. "$SCRIPT_DIR/dependency-cache.sh"

if [ -z "$HWLOC_VERSION" ] || [ -z "$HWLOC_URL" ]; then
    printf '%s\n' "Unable to determine latest hwloc release." >&2
    exit 1
fi

if dependency_is_current hwloc "$HWLOC_VERSION" "$DEPS_DIR/include/hwloc.h" "$DEPS_DIR/lib/libhwloc.a"; then
    exit 0
fi

printf 'Building hwloc %s\n' "$HWLOC_VERSION"
download "$HWLOC_URL" "hwloc-${HWLOC_VERSION}.tar.gz"
verify_sha256 "hwloc-${HWLOC_VERSION}.tar.gz" "$HWLOC_SHA256"
rm -rf "hwloc-${HWLOC_VERSION}"
tar -xzf "hwloc-${HWLOC_VERSION}.tar.gz"

cd "hwloc-${HWLOC_VERSION}"
# Keep hwloc's successful visibility-flag check as a notice, preserving the flag.
patch -p1 < ../../hwloc-visibility-notice.patch
./configure --disable-shared --enable-static --disable-io --disable-libudev --disable-libxml2
make -j"$(jobs)"
cp -fr include ../../deps
cp hwloc/.libs/libhwloc.a ../../deps/lib
dependency_mark_current hwloc "$HWLOC_VERSION"
