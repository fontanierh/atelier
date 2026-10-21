# Cook mode status

Configured checkpoint games use UE 5.8 dependency-tracked incremental cooking through normal `atelier build`.
See [build checkpoints](BUILD_CHECKPOINTS.md). The operator requested a source-first rollout without native
build/cook validation. No packaged parity or measured end-to-end speedup is established by this change.

`--cook-mode modern-full` remains an explicit diagnostic and requires a rebuild reason for checkpoint games.
It is not a recovery step for ordinary cache misses. Preserve cooked state and inspect invalidation first.
Incremental requests can legitimately fall back to full when the cooker invalidates its previous state.
Neither mode bypasses compilation, package scope, worker caps, admission or memory guards.

Observations retain their requested/effective distinction. Native parity stays unproven until separately
validated; a successful command, checksum or package skip count does not prove gameplay correctness.
