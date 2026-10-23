# 3.7.0
* Added `rx/zecnero2` and the official `rx/zmr2` alias for release-compatible
  Zecnero RandomX v2 mining.
* Required and forwarded the v2 raw RandomX hash in the Stratum `commitment`
  field while preserving the Blake2b-256 proof in `result`.
* Added end-to-end miner-to-proxy validation of v1/v2 same-seed transitions,
  dataset reuse, malformed commitment rejection, and upstream proof checks.
* Updated OpenSSL to 4.1.0 and verified the remaining pinned dependencies
  against their current releases.
* Updated the release workflow to the current official GitHub Actions majors.
* Added exact-version dependency stamps so completed dependency builds and
  matching prebuilt profiles are reused only when their artifacts are present.
* Routed direct and relayed donation traffic for the fixed donation wallet to
  HeroMiners US2 on port 1111 and accepted the US fallback endpoint.

# 3.6.7
* Fixed Zecnero daemon polling treating the rolling block-header timestamp as
  new work and broadcasting a replacement job to every miner once per second.
* Restored `daemon-job-timeout` coalescing for timestamp-only template updates
  while forwarding real parent, root, target, and transaction changes at once.
* Added an end-to-end regression test with a daemon that advances `curtime` on
  every poll.

# 3.6.6
* Synchronized the proxy release version with XMRigCC 3.6.6. The RandomX
  hardware-AES dispatch correction is miner-only and requires no proxy code
  changes.

# 3.6.5
* Synchronized the proxy release version with XMRigCC 3.6.5. The daemon
  shutdown fix is client-only and requires no proxy code changes.

# 3.6.4
* Synchronized the proxy release version with XMRigCC 3.6.4. The daemon
  terminal lifecycle fix is client-only and requires no proxy code changes.

# 3.6.0
* Updated llhttp to 9.4.3 and fmt to 12.2.0.
* Replaced best-effort miner writes with bounded asynchronous writes that
  preserve partial output under socket backpressure.
* Enabled TCP keepalive and `TCP_NODELAY` on accepted miner sockets and raised
  the connection backlog for burst handling.
* Bounded and batched asynchronous file logging.
* Pinned source and binary dependency archives with SHA-256 verification.

# 3.5.1
* Fixed daemon/RPC submission tracking so disconnects and invalid or mismatched
  responses are counted as outcome unknown instead of rejected.
* Added outcome-unknown totals to proxy statistics, share logs, the API, and
  Discord notifications.
* Hardened Stratum, self-select, Zecnero, and splitter error handling against
  stale or missing upstream mappings.

# 3.5.0
* Synced with XMRigCC 3.5.0 and xmrig-proxy 6.26.0.
* Added RandomX v2 commitment forwarding and FCMP++ solo-mining support.
* Fixed miner timeout and keepalive timing with monotonic clocks.
* Added current OpenBSD and LibreSSL compatibility fixes.
* Retained existing Zecnero proxy modes, TLS hardening, and RPC support.

# 3.4.8
* Synched changes to XMRigCC 3.4.8
  * Added Virel(VRL) RandomX variant (rx/vrl)
# 3.4.6
* Synched changes to XMRigCC 3.4.6
  * Removed Bonero
# 3.4.5
* Synched changes to XMRigCC 3.4.5
* Fixed daemon solo mining Bonero v18 (Config: algo=rx/0, coin=Bonero)
# 3.4.2
* Synched changes to XMRigCC 3.4.2
* Support for RandomXEQ (Equilibria)
# 3.4.1
* Synched changes to XMRigCC 3.4.1
* Support for RandomTuske
* Removed Lozzax
# 3.4.0
* Synched changes to XMRigCC 3.4.0
* Support for Zephyr
# 3.3.3
* Synched changes to XMRigCC 3.3.3
# 3.3.2
* Synched changes to XMRigCC 3.3.2 / xmrig-proxy 6.19.2-dev (wownero fix)
    * cryptonight (0/1/2/r/fast/half/xao/rto/gpu/rwz/zls/double/conceal)
    * cryptonight-lite (0/1)
    * cryptonight-heavy (0/tube/xhv)
    * cryptonight-pico (0/tlo)
    * cryptonight-extremelite (upx2)
    * randomx (0/wow/arq/sfx/keva/lozzax/xdag)
    * argon2/chukwa
    * argon2/chukwav2
    * argon2/chukwa-lite (ninja)
# 3.3.1
* Synched changes to XMRigCC 3.3.1 / xmrig-proxy 6.18.1-dev
    * cryptonight (0/1/2/r/fast/half/xao/rto/gpu/rwz/zls/double/conceal)
    * cryptonight-lite (0/1)
    * cryptonight-heavy (0/tube/xhv)
    * cryptonight-pico (0/tlo)
    * cryptonight-extremelite (upx2)
    * randomx (0/wow/arq/sfx/keva/lozzax/xdag)
    * argon2/chukwa
    * argon2/chukwav2
    * argon2/chukwa-lite (ninja)
# 2.8.4
* Synched changes to support XMRigCC 2.8.4
    * cryptonight (0/1/2/r/fast/half/xao/rto/gpu/rwz/zls/double/conceal/cache_hash)
    * cryptonight-lite (0/1)
    * cryptonight-heavy (0/tube/xhv)
    * cryptonight-pico (0/tlo)
    * cryptonight-extremelite (upx2)
    * randomx (0/wow/arq/sfx/keva/panthera)
    * argon2/chukwa
    * argon2/chukwav2
    * argon2/chukwa-lite (ninja)
    * astrobwt
# 2.8.2
* Synched changes to support XMRigCC 2.8.2
    * cryptonight (0/1/2/r/fast/half/xao/rto/rwz/zls/double/conceal)
    * cryptonight-lite (0/1)
    * cryptonight-heavy (0/tube/xhv)
    * cryptonight-pico (0/tlo)
    * cryptonight-extremelite (upx2)
    * randomx (0/wow/arq/sfx/keva/panthera)
    * argon2/chukwa
    * argon2/chukwav2
    * argon2/chukwa-lite (ninja)
    * astrobwt
# v2.8.0
* Synched changes to support XMRigCC 2.8.0
    * cryptonight (0/1/2/r/fast/half/xao/rto/rwz/zls/double/conceal)
    * cryptonight-lite (0/1)
    * cryptonight-heavy (0/tube/xhv)
    * cryptonight-pico (0/tlo)
    * cryptonight-extremelite (upx2)
    * randomx (0/wow/loki/arq/sfx/keva/panthera)
    * argon2/chukwa
    * argon2/chukwa-lite (ninja)
    * astrobwt
# v2.7.0
* Synched changes to support XMRigCC 2.7.0
    * cryptonight (0/1/2/r/fast/half/xao/rto/rwz/zls/double/conceal)
    * cryptonight-lite (0/1)
    * cryptonight-heavy (0/tube/xhv)
    * cryptonight-pico (0/tlo)
    * cryptonight-extremelite (upx2)
    * randomx (0/wow/loki/arq/sfx/keva)
    * argon2/chukwa
    * argon2/chukwa-lite (ninja/pengo)
    * astrobwt
