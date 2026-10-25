# Zecnero

The proxy accepts `rx/zecnero` (RandomX v1) and `rx/zecnero2` (RandomX v2).
`randomx/zecnero`, `randomx/zecnero2`, `rx/zmr2`, and `rx2/zecnero` are aliases.
Workers need a Zecnero-capable miner, such as xmrigCC4me-zecnero. The proxy
forwards work and submissions; the worker performs the RandomX hashing.

## Direct daemon mining

Copy `config-zecnero.example.json`, choose one of its three daemon connection
profiles, fill in that profile's credentials, and then run:

```sh
./build/xmrigcc-proxy -c config-zecnero.json
```

Point workers at `127.0.0.1:3333` with `algo: "rx/zecnero"`, `daemon: false`,
and both Zecnero algorithms enabled. Bind the proxy to the appropriate LAN
address for remote workers. The example uses a local testnet RPC endpoint;
choose the endpoint for the network you intend to mine.

The upstream `user` is the payout address. `x` uses the node's configured
address. Worker logins do not change the payout. The proxy supports all prior
daemon and pool connection options plus these isolated miner-RPC choices:

- TLS miner-only RPC (`HOST:18734`): set `tls`, an individual
  `rpc-login` (`username:password`), `daemon-cookie-source`, and an owner-only local
  `daemon-cookie-file`. Use normal CA/hostname verification or set the exact
  64-hex `daemon-cookie-fingerprint`. The proxy retrieves and renews only its
  short-lived `__miner__` cookie.
- HTTP miner-only RPC (`HOST:18734`): leave TLS and all cookie/login fields
  unset. Only zecnerod's strict mining methods are available.
- Private full RPC (`HOST:18732`): retain the existing daemon-owned local
  `daemon-cookie-file`, static Basic credentials, or `rpc-login` behavior. The
  example uses verified TLS; plaintext remains compatible for a loopback-only
  endpoint.

Cookie bootstrap is accepted only from the exact HTTPS origin configured as
the RPC endpoint. Full-RPC cookies are never downloaded or reused on the
miner-only listener.

The daemon's `powversion` selects v1 or v2 automatically. Unknown versions,
inconsistent targets, malformed templates, and unsupported mandatory rules
stop job distribution. Syncing nodes pause submissions and participate in
normal backup-pool failover. Polling has a one-second minimum. ZMQ and
CryptoNote self-select are not used for Zecnero RPC.

For v2, workers compare and submit the Blake2b-256 commitment as `result` and
include the underlying RandomX hash in the Stratum `commitment` field, matching
the `rx/2` convention. Direct RPC submits the assembled block for the daemon to
verify. Pool/bridge mode forwards both fields unchanged.

All three proxy modes work with direct RPC:

- `nicehash` splits the four-byte mining nonce between workers.
- `simple` gives each worker its own upstream session and randomized header.
- `extra_nonce` assigns workers distinct bytes in the remaining header nonce.

The 140-byte header, seed, commitments, coinbase, and transactions retain the
node's encoding. Stratum advertises the conservative high 64 bits of the node
target; submissions are checked against its full 256-bit target. The daemon
validates the actual proof of work. An accepted response is sent to the worker
only after `submitblock` succeeds. Rejections are returned to the worker.
Only one candidate is submitted at a time. Extra candidates found while the
node verifies it receive `Block submission already pending`; this is common
with regtest's very easy target. Old jobs receive a stale-job error.

## Pool or bridge upstream

Use the pool/bridge Stratum address, `daemon: false`, its wallet/login and
password, and `algo: "rx/zecnero"` or `"rx/zecnero2"`. Omit the RPC cookie
settings. Use `nicehash` or `simple` mode. Jobs preserve the upstream algorithm,
seed, target, and header. The upstream must support the selected algorithm.

The built-in Salvium donation endpoint is skipped for Zecnero work. The example
also disables donation forwarding.

## Tests

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DWITH_ZECNERO_TESTS=ON
cmake --build build -j
ctest --test-dir build --output-on-failure
python3 tests/zecnero-proxy.py --proxy build/xmrigcc-proxy \
  --miner /path/to/xmrigMiner
python3 tests/zecnero-proxy.py --proxy build/xmrigcc-proxy \
  --node /path/to/zecnerod --miner /path/to/xmrigMiner
```

The real-node run exercises private full RPC, strict HTTP miner-only RPC, and
authenticated TLS miner-only RPC on isolated disposable Regtest nodes.

The first test uses local mock RPC and Stratum servers to check serialization,
worker isolation, cookie rotation, rejection replies, sync recovery, and v1/v2
job forwarding. With `--miner`, it also mines through a controlled upstream
across a same-seed v1-to-v2 switch and independently checks the submitted
commitment and RandomX hash. The optional node/miner test mines through the proxy on fresh,
isolated regtest chains with experimental v2 activation at height 2, in each
proxy mode. It does not use an existing daemon, wallet, or database. Artifacts
are kept in a temporary directory printed by the test.
