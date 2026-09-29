#!/bin/sh -e

cd "$(dirname "$0")"

./build.uv.sh
./build.hwloc.sh
./build.openssl.sh
