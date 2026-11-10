# Yorimichi V2 package

The package workflow is implemented. A normal build validates and compiles; cooking remains explicit. Commands
below run from the repository root of an owned checkout at a stopped native-job boundary. Publication uses the
existing verified package and the [release workflow](../../../docs/RELEASES.md), without another cook.

## Current main checkpoint (2026-11-10)

- **Built:** clean main `da0a41f891` (after #803/#804/#809/#810); fingerprint `c89f535441be`.
  Guarded `unreal.package` completed in 255.7 s. The 49 recovered material masters and Hippodrome residual batch
  are included. Older apps and their evidence remain separate.
- **Automated acceptance:** all eight checks pass, including the 62 pinned runtime-data files.
- **Observed launch/shutdown:** ledger records both passing for this fingerprint: Slice loaded in 15.9 s,
  no error lines, guard peak 7.8 GiB; Apple Event quit produced `LogExit` and process exit 0. This is log-only evidence.
- **Host and leave:** the [#810 check](https://github.com/fontanierh/atelier/pull/810) passed all nine checks on
  the first attempt: listen server on port 7777, session/content identity, then `LeaveGame` back to Solo with
  no game net driver, one rider and the same build. It covers the host's own lifecycle in one process.
- **Still open:** `input`, `map_travel`, `gameplay`, `sound`, `settings_persistence`, `save_persistence`, and
  a real second-machine session. The recorded verification verdict fails on the six **unrecorded** manual items;
  it does not report six observed gameplay failures. Hosting/leave does not complete those checks.

The following sections retain the earlier packages' evidence; their results apply only to their named revisions.

## Integration package for #803 and #804 (2026-11-10)

- **Built:** branch revision `7f43b4ccf3`: main `72a7033bf2` (with the packaging guard fix
  [PR #807](https://github.com/fontanierh/atelier/pull/807)) plus [PR #803](https://github.com/fontanierh/atelier/pull/803)
  and [PR #804](https://github.com/fontanierh/atelier/pull/804). The guarded `unreal.package` finished at 13:03 Paris in
  243 s, with the cook up to date; the EPERM guard failure of the earlier attempts did not recur. Fingerprint
  `88d415e733ec`, about 3.2 GB, extracted outside every checkout. It is a pre-merge package: it is not main's package.
- **Automated checks:** all eight pass (identity, executable, signatures, audio entitlement, 14 bundled dependencies,
  no excluded content, 62 runtime-data files unchanged).
- **Observed launch:** `first_launch` and `shutdown` are recorded as passed for `88d415e733ec`. Guarded
  `atelier playtest --app`: LoadMap of the Slice in 15.6 s, no error lines, guard peak 7.9 GiB; the Quit event exited
  with code 0 and the broker released the reservation with a successful tree observation. The evidence is the log
  and guard reports; that session could not capture the screen.
- **Not in this package:** the multiplayer session map fix ([PR #808](https://github.com/fontanierh/atelier/pull/808)) and
  the multiplayer content manifest ([PR #809](https://github.com/fontanierh/atelier/pull/809)). A later package from
  `f276a40021` (with #808) passed the same automated checks and launch, but `HostGame` was refused: `This build has no
  multiplayer content manifest`. No V2 package before #809 can host or join a session.
- **Remaining manual checks:** `input`, `map_travel`, `gameplay`, `sound`, `settings_persistence` and
  `save_persistence` are not recorded, so `verify` fails for this package as for the earlier main package below.

## Earlier main checkpoint (2026-11-10 08:38 Paris)

- **Built:** main `7719234597` (after [PR #801](https://github.com/fontanierh/atelier/pull/801)), ready at 08:38 Paris.
  The step took 280 s because the cook reused the previous one; `check.py --full` reported 0 problems over 7,219
  assets first. The extracted app is about 3.2 GB; package fingerprint `0adbb5ab212e`. The previous checkpoint
  app (`bb451f636160`, #797) is kept beside it.
- **Automated checks:** all pass on the extracted app: bundle identity `com.atelier.yorimichiv2`, executable,
  signatures, audio entitlement, 14 bundled dependencies, excluded phone/kart content absent, and 62 runtime-data
  files with no missing or changed bytes.
- **Observed launch:** `first_launch` and `shutdown` are recorded as passed for `0adbb5ab212e`:
  - guarded launch, with a peak of 7.8 GiB;
  - LoadMap of the Slice in 15.7 s, with no error lines;
  - clean exit on the Quit event.

  The other manual items (input, map travel, gameplay, sound, settings and save persistence) are not recorded
  for this app.
- **Content scope:** this older package includes:
  - the first small-families batch ([PR #797](https://github.com/fontanierh/atelier/pull/797));
  - the Brine Cove signal mast and shipyard slip as their own objects ([PR #798](https://github.com/fontanierh/atelier/pull/798),
    [PR #800](https://github.com/fontanierh/atelier/pull/800)).

  PRs #799 and #801 add material-master records preparation and inventory only; they change no packaged bytes.

The owner directed on 2026-11-09 that human and multiplayer playtesting follows building; multiplayer will be
played with his brother. These checks remain unverified acceptance work, not a block on independent migration.

## A quiet staging read

`Reading oplog` covers a request for the entry list and subsequent attachment reads. Zen answering on port 8558
proves server availability, **not progress of that request**. Use the existing UAT log, guard reports and saved
staging outputs to distinguish progress from a heartbeat; do not infer progress from connection count alone.

On 2026-11-10, the first request waited for its 1,200-second HTTP timeout while Zen stayed healthy. The existing
second attempt then parsed 15,081 entries in seconds and completed staging. The pinned engine's
`OplogReader.cs` hardcodes that 20-minute per-request timeout; no shorter timeout setting is exposed in this path.
The three-attempt reader recovery is inside UAT, separate from Atelier's overall package deadline.

Keep the successful cook and caches for retry. If the explicit job deadline is reached, cancel only the owned
controller through the normal guarded path and allow cleanup to finish before retrying the same package command.
Do not restart shared Zen, clear reservations or discard the cook to diagnose a healthy but silent request.
Changing the engine request timeout requires a separate supported engine change; the memory guard is not a
request-timeout control.

## Prepare and build

Hydrate the committed Git LFS content and fetch the pinned restricted roots first; see
[the README](../README.md#restricted-content-and-recoverable-originals). Public Git LFS does not contain those
private packages. The build refuses missing, stale or changed inputs rather than regenerating them.

```sh
V2_RESTRICTED_SOURCE=DIR uv run python games/yorimichi_v2/tools/restricted/fetch.py fetch
uv run python games/yorimichi_v2/tools/content/check.py --full
uv run python games/yorimichi_v2/tools/package/cook_config.py
ATELIER_AGENT=OWNER nice -n 10 uv run atelier build yorimichi_v2 unreal.package --cook-memory-gib 20
```

The package step repeats the full content check, validates cook configuration, and invokes UAT
`BuildCookRun -cookall -stage -pak -package -archive`. `-cookall` includes committed content and the fetched
restricted packages. `DirectoriesToAlwaysCook` must cover string-loaded roots; the configuration check also
rejects missing maps, excluded feature content and a template bundle identifier. Phone booths are scenery.

The Mac bundle identifier is configured in `unreal/Config/Mac/MacEngine.ini`; it is verified in the built app's
`Info.plist` by the acceptance check. V2 uses its own saved-state identity. Old donor saves are not imported.
Optional soundtrack bytes use `assets/audio/music/fetch.py` and `music.lock.json`; required sound effects do
not depend on that optional download. Fetch it explicitly when needed:

```sh
uv run python games/yorimichi_v2/assets/audio/music/fetch.py
```

`atelier fetch yorimichi_v2` does not invoke this script: V2 has `[release.music]`, not `[fetch].scripts`.

## Extract and check

The archive lives at `build/yorimichi_v2/package/archive/Mac/YorimichiV2.app`. Copy the app outside every checkout:

```sh
mkdir -p "$HOME/YorimichiV2-Package"
ditto build/yorimichi_v2/package/archive/Mac/YorimichiV2.app "$HOME/YorimichiV2-Package/YorimichiV2.app"
APP="$HOME/YorimichiV2-Package/YorimichiV2.app"
uv run python games/yorimichi_v2/tools/package/acceptance.py automated --app "$APP"
ATELIER_AGENT=OWNER nice -n 10 uv run atelier playtest yorimichi_v2 --app "$APP" --memory-gib 22
```

`atelier playtest --app` launches the extracted local package under normal admission and memory guards. It does
not require another cook. Automated checks cover identity, executable/signatures, audio entitlement, bundled
dependencies, excluded content names and pinned runtime-data bytes. They do not prove input, gameplay or sound.

## Record observed playtests

The person/controller records only observed results for the exact running package:

```sh
EV="$HOME/YorimichiV2-Package/evidence.json"
uv run python games/yorimichi_v2/tools/package/acceptance.py record --app "$APP" --evidence "$EV" first_launch pass --note "Observed result"
uv run python games/yorimichi_v2/tools/package/acceptance.py verify --app "$APP" --evidence "$EV" --report "$HOME/YorimichiV2-Package/verdict.json"
```

Required manual items are `first_launch`, `input`, `map_travel`, `gameplay`, `sound`, `settings_persistence`,
`save_persistence` and `shutdown`. A changed app changes its fingerprint; `record` refuses an old package's
ledger unless `--reset` explicitly starts a new ledger for the replacement. Preserve the old evidence separately.
A build or passing automated checks never marks those manual items complete.

For multiplayer acceptance, use matching packages on two actual machines and record
`two_machine_multiplayer`; then add `--multiplayer` to `verify`. The multiplayer implementation exists, but this
actual two-machine packaged playtest is not recorded as passed. Two checkouts on one machine do not substitute.
The packaged bridge has no Python input route, so a human playtest is not replaced by the editor's scripts.

To exercise the host's session lifecycle in an existing package containing #810, use the existing guarded check:

```sh
ATELIER_AGENT=OWNER nice -n 10 uv run python games/yorimichi_v2/tools/package/host_leave.py run --app "$APP"
uv run python games/yorimichi_v2/tools/package/host_leave.py verify RECEIPT_DIR
```

The first command prints the receipt directory. The second re-judges those saved receipts and the recorded exit
code without launching another game. This check does not cook, does not replace the six manual checks, and does
not prove another player can join from a second machine. Reuse passing evidence for an unchanged package.

`verify` exits successfully only when every selected automated and manual item passes for the current package.
Its report records the package fingerprint, bundle identifier, checkout revision/dirty state and check results.
A not-yet-complete verdict does not prohibit continuing content migration.

## Focused checks when this workflow changes

`tests/test_package_config.py` covers cook configuration without hydrated content, and
`tests/test_package_acceptance.py` covers the ledger and automated checks against a fixture package. Run the
relevant focused tests for changed behavior; reuse existing passing evidence and required hosted CI. No package
rebuild or broad local suite is needed for a documentation/status update.

## Still open

- The remaining independently editable objects and recoverable-source work listed in [INVENTORY.md](INVENTORY.md).
- Human gameplay, sound, settings/save persistence and two-machine playtests on the current package.
- Any current defects found in those playtests. The missing-asset and performance observations in
  [PARITY.md](PARITY.md) are explicitly bound to older revisions, not an assertion that the latest app has them.
