#!/bin/sh -e

REPO="xmrig/xmrig-deps"
DEPS_TAG="${XMRIG_DEPS_TAG:-v25.06.16}"
DEPS_SHA256="${XMRIG_DEPS_SHA256:-8a7c06647f3625c1e3c78b70ea9faa70fddcceefbe2523e0a01046780939cd3d}"
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
DEST_DIR="${DEST_DIR:-${SCRIPT_DIR}/deps}"
PROFILE="${1:-}"

detect_profile() {
    os="$(uname -s)"
    arch="$(uname -m)"

    case "${os}:${arch}" in
        Linux:x86_64|Linux:amd64)
            printf '%s\n' "No Linux binary profile is provided by ${REPO}; use scripts/build_deps.sh instead." >&2
            exit 1
            ;;
        Linux:i386|Linux:i486|Linux:i586|Linux:i686)
            printf '%s\n' "No Linux binary profile is provided by ${REPO}; use scripts/build_deps.sh instead." >&2
            exit 1
            ;;
        Darwin:arm64|Darwin:aarch64)
            printf '%s\n' "No macOS binary profile is provided by ${REPO}; use scripts/build_deps.sh instead." >&2
            exit 1
            ;;
        MINGW*:x86_64|MSYS*:x86_64|CYGWIN*:x86_64)
            printf '%s\n' "msvc2022/x64"
            ;;
        MINGW*:aarch64|MSYS*:aarch64|CYGWIN*:aarch64)
            printf '%s\n' "msvc2022/arm64"
            ;;
        *)
            printf '%s\n' "Unsupported host ${os}/${arch}; pass a profile, for example gcc/x64 or msvc2022/x64." >&2
            exit 1
            ;;
    esac
}

download() {
    url="$1"
    out="$2"

    if command -v curl >/dev/null 2>&1; then
        curl -fL --retry 3 "$url" -o "$out"
    elif command -v wget >/dev/null 2>&1; then
        wget --tries=3 "$url" -O "$out"
    else
        printf '%s\n' "curl or wget is required to download ${REPO}." >&2
        exit 1
    fi
}

verify_sha256() {
    actual=$(sha256sum "$1" | awk '{print $1}')
    [ "$actual" = "$2" ] || { printf 'SHA-256 mismatch for %s\n' "$1" >&2; exit 1; }
}

if [ -z "$PROFILE" ]; then
    PROFILE="$(detect_profile)"
fi

tmp_dir="${SCRIPT_DIR}/build/xmrig-deps.$$"
rm -rf "$tmp_dir"
mkdir -p "$tmp_dir"
trap 'rm -rf "$tmp_dir"' EXIT INT TERM

archive="${tmp_dir}/xmrig-deps.tar.gz"
printf 'Downloading pinned %s release %s...\n' "$REPO" "$DEPS_TAG"
url="https://github.com/${REPO}/archive/refs/tags/${DEPS_TAG}.tar.gz"
download "$url" "$archive"
verify_sha256 "$archive" "$DEPS_SHA256"

mkdir -p "${tmp_dir}/src"
tar -xzf "$archive" -C "${tmp_dir}/src"
root_dir="$(find "${tmp_dir}/src" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
profile_dir="${root_dir}/${PROFILE}"

if [ ! -d "$profile_dir" ]; then
    printf 'Profile "%s" not found in %s release %s.\n' "$PROFILE" "$REPO" "$DEPS_TAG" >&2
    printf 'Available profiles:\n' >&2
    find "$root_dir" -mindepth 2 -maxdepth 2 -type d | sed "s#${root_dir}/#  #" | sort >&2
    exit 1
fi

rm -rf "$DEST_DIR"
mkdir -p "$DEST_DIR"
cp -R "${profile_dir}/include" "$DEST_DIR/"
cp -R "${profile_dir}/lib" "$DEST_DIR/"

printf 'Installed %s profile %s into %s\n' "$REPO" "$PROFILE" "$DEST_DIR"
