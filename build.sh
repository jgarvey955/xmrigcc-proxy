#!/usr/bin/env bash
# Portable helper to build xmrigcc-proxy on common Linux (apt) and macOS hosts.
# - Verifies toolchain and required dev libraries.
# - Installs missing pieces when a supported package manager is present.
# - Runs the CMake configure and build steps.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${ROOT_DIR}/build"

log() { printf '[build] %s\n' "$*"; }
err() { printf '[build] ERROR: %s\n' "$*" >&2; }

command_exists() { command -v "$1" >/dev/null 2>&1; }

jobs() {
    if command_exists nproc; then nproc; elif command_exists sysctl; then sysctl -n hw.logicalcpu; else echo 2; fi
}

require_cmd() {
    local cmd="$1"
    local pkg="$2"
    if command_exists "$cmd"; then return 0; fi
    err "Missing command: ${cmd} (install package: ${pkg})"
    return 1
}

ensure_apt_packages() {
    local pkgs=("$@")
    local missing=()
    for pkg in "${pkgs[@]}"; do
        dpkg -s "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
    done

    if (( ${#missing[@]} )); then
        log "Installing packages: ${missing[*]}"
        sudo apt-get update
        sudo apt-get install -y --no-install-recommends "${missing[@]}"
    else
        log "All apt packages present"
    fi
}

ensure_brew_packages() {
    local pkgs=("$@")
    local missing=()
    for pkg in "${pkgs[@]}"; do
        brew list "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
    done

    if (( ${#missing[@]} )); then
        log "Installing Homebrew packages: ${missing[*]}"
        brew install "${missing[@]}"
    else
        log "All Homebrew packages present"
    fi
}

detect_platform() {
    if [[ "$(uname -s)" == "Darwin" ]]; then
        echo "macos"
    elif command_exists apt-get; then
        echo "debian"
    else
        echo "unknown"
    fi
}

install_prereqs() {
    local platform
    platform="$(detect_platform)"

    # Base toolchain
    require_cmd git git || true
    require_cmd cmake cmake || true
    require_cmd pkg-config pkg-config || true
    require_cmd make build-essential || true
    require_cmd g++ g++ || true

    case "$platform" in
        debian)
            ensure_apt_packages \
                build-essential cmake git pkg-config automake libtool \
                libuv1-dev libssl-dev libhwloc-dev libsodium-dev
            ;;
        macos)
            if ! command_exists brew; then
                err "Homebrew is required on macOS (https://brew.sh/)"
                exit 1
            fi
            ensure_brew_packages cmake pkg-config git libuv openssl@3 hwloc libsodium
            # Ensure pkg-config can find OpenSSL for CMake on macOS
            export PKG_CONFIG_PATH="/usr/local/opt/openssl@3/lib/pkgconfig:/opt/homebrew/opt/openssl@3/lib/pkgconfig:${PKG_CONFIG_PATH:-}"
            ;;
        *)
            err "Unsupported platform. Install: CMake, make, g++, pkg-config, libuv, OpenSSL, hwloc, libsodium manually."
            exit 1
            ;;
    esac
}

configure() {
    mkdir -p "${BUILD_DIR}"
    cd "${BUILD_DIR}"

    log "Configuring project with CMake"
    cmake .. \
        -DWITH_TLS=ON \
        -DWITH_HTTPD=ON
}

build() {
    cd "${BUILD_DIR}"
    log "Building"
    cmake --build . -- -j"$(jobs)"
}

main() {
    install_prereqs
    configure
    build
    log "Done. Binaries are in ${BUILD_DIR}"
}

main "$@"
