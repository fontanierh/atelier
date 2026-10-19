# Soundbank network acceptance

`tools/review_network_session.py --soundbanks --listen --app APP --cook-receipt RECEIPT
--expected-identity ID --aggregate-memory-gib 14` uses the existing packaged Development
listen/client gameplay driver. Compile, cook and independently verify the package at the
same clean source revision first. Use a fresh output directory inside that app's sandbox,
or let the runner create one. The runner retains normal source/cook/binary identity checks,
private loopback admission, actual-child guards and normal intentional disconnect.

This explicit case enables audio while retaining NullRHI and the LiveBridge refusal for
network worlds. The full 14 GiB aggregate is both reserved and guarded; each child retains
its normal 10 GiB ceiling. It does not request an 18 GiB performance window. Packaged memory
is not inferred from editor measurements: retain the first actual guarded result, including
any memory stop. No profile, reserve or pressure check changes are needed.

The opt-in development probe extends only the sustained-skating phase. It applies ordinary
push input to the locally controlled rider, without teleport, velocity injection, fabricated
components or remote input. Both worlds must observe two real ready actors and playing roll
components. The host records Original, selects Dry Street, then restores Original. The guest
selects Dry Street and keeps that local choice across all three host phases. Each phase is
acknowledged through fresh run-local receipts before the next change; the existing gameplay
and session lifecycle must then complete normally. Missing assets or incomplete observation
fails within 45 seconds; the enclosing 240-second native lifecycle remains bounded.

The validator requires stable per-process player/pawn/component identities, the actual loaded
foot/skate bank bindings, every loop's wave, and nonzero genuinely playing roll components on
local and remote actors. Host final waves must equal every captured Original reference, while
guest waves remain identical. These receipts prove component playback state and client-local
presentation ownership. They do not replace retained real master-output recordings, subjective
listening, rendered remote art acceptance, or a two-machine test.
