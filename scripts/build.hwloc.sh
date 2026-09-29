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

latest_release_field() {
    repo="$1"
    pattern="$2"

    release_json=".hwloc-release.json"
    download "https://api.github.com/repos/${repo}/releases/latest" "$release_json" >/dev/null
    sed -n "$pattern" "$release_json" | head -n 1
}

jobs() {
    nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || sysctl -n hw.logicalcpu 2>/dev/null || printf '1\n'
}

HWLOC_TAG="${HWLOC_VERSION:-$(latest_release_field open-mpi/hwloc 's/.*"tag_name": *"\([^"]*\)".*/\1/p')}"
HWLOC_VERSION="${HWLOC_TAG#hwloc-}"
HWLOC_URL="$(latest_release_field open-mpi/hwloc 's/.*"browser_download_url": *"\([^"]*hwloc-[0-9][^"]*\.tar\.gz\)".*/\1/p')"

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
