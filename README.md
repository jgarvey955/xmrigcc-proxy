# XMRig Proxy - Updated to work with SALVIUM
to Donate SAL1 -> SC11UA22DFrAQerDwJwcf8Yh2ySTb7ipaFL8qSEX26tqUDdPf1RQBmmRuZG4SnRd8DNpp5vE1zDHnKNStiFDQsce49Q7fyp8Yp

[![Github All Releases](https://img.shields.io/github/downloads/bendr0id/xmrigcc-proxy/total.svg)](https://github.com/bendr0id/xmrigcc-proxy/releases)
[![Github Latest](https://img.shields.io/github/downloads/bendr0id/xmrigCC-proxy/latest/total.svg)](https://github.com/bendr0id/xmrigcc-proxy/releases)
[![GitHub release](https://img.shields.io/github/release/bendr0id/xmrigcc-proxy/all.svg)](https://github.com/bendr0id/xmrigcc-proxy/releases)
[![GitHub Release Date](https://img.shields.io/github/release-date-pre/bendr0id/xmrigcc-proxy.svg)](https://github.com/bendr0id/xmrigcc-proxy/releases)
[![GitHub license](https://img.shields.io/github/license/bendr0id/xmrigcc-proxy.svg)](https://github.com/bendr0id/xmrigcc-proxy/blob/master/LICENSE)

Extremely high performance Monero (XMR) Stratum protocol proxy, can easily handle over 100K connections on cheap $5 (1024 MB) virtual machine. Reduce number of pool connections up to 256 times, 100K workers become just 391 worker on pool side. Written on C++/libuv same as [XMRigCC](https://github.com/bendr0id/xmrigCC) miner.

**This proxy is compatible with XMRigCC**

Zecnero pool, bridge, and direct RPC mining (`rx/zecnero` and `rx/zecnero2`)
is described in [doc/ZECNERO.md](doc/ZECNERO.md), with an
[example configuration](config-zecnero.example.json).

## Compatibility

:warning: :warning: :warning: **This proxy is compatible with all algos supported by the latest version of XMRigCC** :warning: :warning: :warning:

**Nicehash support must be enabled on miner side, it mandatory.**

In the default `nicehash` proxy mode, every connected miner on an upstream is
assigned a different high byte of the 32-bit nonce. This divides each job into
256 non-overlapping ranges of 16,777,216 nonces. Run miners with `--nicehash`.
The proxy rejects a submitted nonce outside the miner's assigned range.

With the HTTP API enabled, `GET /1/mapping` reports the live assignments and
their `mapper_id`, `nonce_prefix`, `nonce_start`, and `nonce_end`. A healthy
mapping reports zero `collisions`, zero `overlap_percent`, and 100 percent
`partition_efficiency_percent`. These values prove assignment uniqueness; they
do not claim that every nonce was actually hashed or that a fast miner did not
wrap its 24-bit range before the next job.

* Compatible with any Monero, Electroneum, Sumokoin and AEON pools, except **nicehash.com**.
* Any miner with nicehash support, `--nicehash` option for [XMRig(CC)](https://github.com/bendr0id/xmrigCC), `"nicehash_nonce": true,` for xmr-stak-cpu.
* [Comparison](https://github.com/xmrig/xmrig-proxy/wiki/Comparison) with other proxies.

## Why?
This proxy is designed to handle donation traffic from XMRig. No other solution works well with high connection and disconnection rates.

## Download
* Binary releases: https://github.com/bendr0id/xmrigcc-proxy/releases
* Git tree: https://github.com/bendr0id/xmrigcc-proxy.git
  * Clone with `git clone https://github.com/bendr0id/xmrigcc-proxy.git` :hammer: [Build instructions](https://github.com/xmrig/xmrig-proxy/wiki/Build).

## Build on Windows

The upstream `cmake .. && make -j*` instructions are for Unix-like shells with
dependencies installed in default system paths. With Visual Studio on Windows,
point CMake at the latest XMRig static dependency bundle and build through CMake:

```
sh scripts/update_deps.sh msvc2022/x64
mkdir build
cd build
cmake .. -DXMRIG_DEPS=../scripts/deps
cmake --build . --config Release
```

For MSYS2, use the matching bundled profile instead:

```
sh scripts/update_deps.sh gcc/x64
mkdir -p build
cd build
cmake .. -DXMRIG_DEPS=../scripts/deps -DBUILD_STATIC=ON
make -j$(nproc)
```

## Static build on Linux

Linux builds libuv 1.53.0, hwloc 2.15.0, and OpenSSL 4.0.3 from source into
`scripts/deps`. These are the latest stable upstream releases verified on
September 30, 2026; the defaults are pinned for reproducible builds:

```
scripts/build_deps.sh
mkdir -p build
cd build
cmake .. -DXMRIG_DEPS=../scripts/deps -DBUILD_STATIC=ON
make -j$(nproc)
```

The helper scripts also accept explicit version overrides, for example
`UV_VERSION=1.53.0 HWLOC_VERSION=2.15.0 OPENSSL_VERSION=4.0.3 scripts/build_deps.sh`.
  
## Usage
:boom: If you are using Linux and need to manage over **1000 connections**, you must [increase the limits on open files](https://github.com/xmrig/xmrig-proxy/wiki/Ubuntu-setup).

### Discord share notifications

Accepted and rejected Discord notifications include `Coin` and `Algorithm`,
even with `discord.verbose` disabled. The algorithm is saved with the submitted
share, so a subsequent job change cannot change the notification's algorithm.
Batch summaries show `Last coin` and `Last algorithm` for the last accepted
share; the totals can span multiple algorithms or coins.

Set `coin` in each pool entry (for example, `"coin": "SAL"` for Salvium or
`"coin": "XMR"` for Monero). Daemon mining also uses the coin detected from the
wallet, and `rx/zecnero` / `rx/zecnero2` identify Zecnero automatically. Other
unidentified coins display `Unknown (set pool coin)` because algorithms such
as `rx/0` are shared by multiple coins.

Run the local notification checks with
`python3 tests/discord-notifications.py --proxy build/xmrigcc-proxy`.

### Direct daemon mining with RPC login

Set `daemon` and `rpc-login` on the individual entry in `pools`. The `user`
field remains your payout wallet address. `rpc-login` supplies the daemon's
HTTP Digest credentials, matching its `--rpc-login user:password` setting.
The password may contain colons; the first colon separates the username.
Omit `rpc-login` (or set it to `null`) when the daemon does not require login.

After switching from a build without RPC login support, check the active config:
that build's autosave may have removed `rpc-login`. Restore it in each protected
Salvium daemon entry using the credentials from that daemon's config. Rebuilding
alone cannot recover removed credentials. Zecnero uses `daemon-cookie-file` or
`daemon-rpc-user` with `pass` instead.

For example, a local Salvium daemon followed by an ordinary pool as a backup:

```json
{
    "mode": "nicehash",
    "pools": [
        {
            "coin": "SAL",
            "url": "127.0.0.1:19081",
            "user": "YOUR_SALVIUM_WALLET_ADDRESS",
            "daemon": true,
            "rpc-login": "rpcuser:rpcpassword"
        },
        {
            "coin": "SAL",
            "url": "us2.salvium.herominers.com:1230",
            "user": "YOUR_SALVIUM_WALLET_ADDRESS",
            "pass": "x",
            "daemon": false
        }
    ]
}
```

Entries use the existing pool order and failover behavior. Credentials from the
daemon entry are never used for the Stratum pool. Keep `mode` set to `nicehash`
or `simple` when mixing daemon and pool entries; `extra_nonce` requires every
entry to be a daemon. With `nicehash` mode, miners still need `--nicehash`.

The command-line equivalent for a daemon entry is:

```sh
./xmrigcc-proxy -o 127.0.0.1:19081 --daemon --coin SAL \
    -u YOUR_SALVIUM_WALLET_ADDRESS --rpc-login 'rpcuser:rpcpassword'
```

RPC authentication uses OpenSSL and requires a build with `WITH_TLS=ON` (the
default), including when the daemon uses plain HTTP. Set `tls: true` on the
daemon entry if its RPC endpoint uses HTTPS. A `WITH_TLS=OFF` build reports an
explicit error when `rpc-login` is configured. This feature covers direct
daemon mining; self-select mode is unchanged.

If an existing build was configured without TLS, reconfigure it with
`cmake -S . -B build -DWITH_TLS=ON`, then run `cmake --build build -j4`.
The updated executable is `build/xmrigcc-proxy`.

To run the integration test, provide a proxy binary and a Salvium daemon binary
(Python `requests` and the `openssl` command are required):

```sh
python3 scripts/test_rpc_login.py --proxy build/xmrigcc-proxy \
    --daemon /path/to/salviumd
```

The test starts its own offline regtest daemons with fresh temporary data,
temporary configurations, and unused loopback ports. It checks authentication,
an accepted difficulty-1 test block through the proxy, height polling, the CLI
option, bad credentials, a local Stratum failover fixture, and unauthenticated
daemon compatibility. It also tests HTTPS with certificate pinning. Add
`--notls-proxy /path/to/xmrigcc-proxy-notls` to check the error from a build
without OpenSSL. It stops only the processes it starts and never connects to an
existing daemon.

`python3 scripts/test_http_digest_auth.py` separately checks Digest calculations
against Python's `hashlib` and verifies malformed-challenge rejection. That test
requires a C++ compiler and OpenSSL development libraries.

### TLS versions

All encrypted connections require TLS 1.2 or newer: incoming miners, the HTTPS
API, upstream pools, and outgoing HTTPS requests (including daemon RPC).
TLS 1.0 and 1.1 are disabled, following [RFC 8996](https://www.rfc-editor.org/rfc/rfc8996.html).
The server `tls.protocols` setting and `--tls-protocols` accept `TLSv1.2` and
`TLSv1.3`. Legacy selections are ignored and cannot lower the minimum, including
when `protocols` is `null` or contains only legacy names.

Run `python3 scripts/test_tls_versions.py` to verify incoming miner/API and
outgoing Stratum/HTTPS handshakes using the normal `build/xmrigcc-proxy` binary.
The test uses temporary certificates and local endpoints only; it requires
Python with TLS 1.3 support and the `openssl` command.
  
### Options
```
  -b, --bind=ADDR          bind to specified address, example "0.0.0.0:3333"
  -a, --algo=ALGO          mining algorithm (--algorithms to print supported)
      --coin=COIN          specify coin instead of algorithm
  -m, --mode=MODE          proxy mode, nicehash (default) or simple
  -o, --url=URL            URL of mining server
  -O, --userpass=U:P       username:password pair for mining server
  -u, --user=USERNAME      pool username or daemon payout wallet address
  -p, --pass=PASSWORD      password for mining server
      --daemon            use daemon RPC instead of a pool for solo mining
      --rpc-login=USER:PASS  HTTP Digest credentials for the current daemon entry
                            requires a TLS-enabled build; set after its --url
  -r, --retries=N          number of times to retry before switch to backup server (default: 1)
  -R, --retry-pause=N      time to pause between retries (default: 1 second)
      --custom-diff=N      override pool diff
      --reuse-timeout=N    timeout in seconds for reuse pool connections in simple mode
      --verbose            verbose output
      --user-agent=AGENT   set custom user-agent string for pool
      --no-color           disable colored output
      --no-workers         disable per worker statistics
      --variant            algorithm PoW variant
      --donate-level=N     donate level, default 2%
  -B, --background         run the miner in the background
  -c, --config=FILE        load a JSON-format configuration file
      --no-watch           disable configuration file watching
  -l, --log-file=FILE      log all output to a file
  -S, --syslog             use system log for output messages
  -A  --access-log-file=N  log all workers access to a file
      --api-port=N         port for the miner API
      --api-access-token=T use Bearer access token for API
      --api-worker-id=ID   custom worker-id for API
      --api-no-ipv6        disable IPv6 support for API
      --api-no-restricted  enable full remote access (only if API token set)
      --tls                enable SSL/TLS support for pool connection (needs pool support)
      --tls-bind=ADDR      bind to specified address with enabled TLS
      --tls-cert=FILE      load TLS certificate chain from a file in the PEM format
      --tls-cert-key=FILE  load TLS certificate private key from a file in the PEM format
      --tls-dhparam=FILE   load DH parameters for DHE ciphers from a file in the PEM format
      --tls-protocols=N    server TLS protocols: "TLSv1.2 TLSv1.3" (TLS 1.2 minimum)
      --tls-ciphers=S      set list of available TLSv1.2 ciphers
      --tls-ciphersuites=S set list of available TLSv1.3 ciphersuites 
  -h, --help               display this help and exit
  -V, --version            output version information and exit
      --algorithms         prints out a list of supported algos
```

## Contact
* ben [at] graef.in
* [telegram](https://telegram.me/bendr0id)
* [discord](https://discord.gg/r3rCKTB)
* [reddit](https://www.reddit.com/user/BenDr0id/)
