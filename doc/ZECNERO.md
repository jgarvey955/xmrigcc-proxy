# Zecnero

The proxy accepts `rx/zecnero` (RandomX v1) and `rx/zecnero2` (RandomX v2).
`randomx/zecnero`, `randomx/zecnero2`, and `rx2/zecnero` are aliases.
Workers need a Zecnero-capable miner, such as xmrigCC4me-zecnero. The proxy
forwards work and submissions; the worker performs the RandomX hashing.

## Direct daemon mining

Copy `config-zecnero.example.json`, set the node's RPC address and the actual
local cookie path, then run:

```sh
./build/xmrigcc-proxy -c config-zecnero.json
```

Point workers at `127.0.0.1:3333` with `algo: "rx/zecnero"`, `daemon: false`,
and both Zecnero algorithms enabled. Bind the proxy to the appropriate LAN
address for remote workers. The example uses a local testnet RPC endpoint;
choose the endpoint for the network you intend to mine.

The upstream `user` is the payout address. `x` uses the node's configured
address. Worker logins do not change the payout. Cookie credentials are read
from a local file on every request, including after rotation. For a node using
static Basic authentication, omit `daemon-cookie-file` and use
`daemon-rpc-user` plus `pass`. HTTPS RPC and certificate fingerprints use the
existing `tls` and `tls-fingerprint` settings.

The daemon's `powversion` selects v1 or v2 automatically. Unknown versions,
inconsistent targets, malformed templates, and unsupported mandatory rules
stop job distribution. Syncing nodes pause submissions and participate in
normal backup-pool failover. Polling has a one-second minimum. ZMQ and
CryptoNote self-select are not used for Zecnero RPC.

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
  --node /path/to/zecnerod --miner /path/to/xmrigMiner
```

The first test uses local mock RPC and Stratum servers to check serialization,
worker isolation, cookie rotation, rejection replies, sync recovery, and v1/v2
job forwarding. The optional node/miner test mines through the proxy on fresh,
isolated regtest chains with experimental v2 activation at height 2, in each
proxy mode. It does not use an existing daemon, wallet, or database. Artifacts
are kept in a temporary directory printed by the test.
