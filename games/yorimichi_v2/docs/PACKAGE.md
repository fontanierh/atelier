# Yorimichi V2 package

The package workflow is implemented. A normal build validates and compiles; cooking remains explicit. Commands
below run from the repository root of an owned checkout at a stopped native-job boundary. Publication uses the
existing verified package and the [release workflow](../../../docs/RELEASES.md), without another cook.

## Current checkpoint (2026-11-10)

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
- **Content scope:** see [INVENTORY.md](INVENTORY.md). This package is the first to include:
  - the first small-families batch ([PR #797](https://github.com/fontanierh/atelier/pull/797));
  - the Brine Cove signal mast and shipyard slip as their own objects ([PR #798](https://github.com/fontanierh/atelier/pull/798),
    [PR #800](https://github.com/fontanierh/atelier/pull/800)).

  PRs #799 and #801 add material-master records preparation and inventory only; they change no packaged bytes.
- **Staging time:** UAT reads one Zen attachment per oplog entry with a blocking request inside a parallel loop,
  so staging (about 15 000 entries) spends most of its time on .NET thread-pool growth. The log shows a single
  "Reading oplog" line for that whole time; that is progress, not a hang, while Zen keeps listening on 8558.

The owner directed on 2026-11-09 that human and multiplayer playtesting follows building; multiplayer will be
played with his brother. These checks remain unverified acceptance work, not a block on independent migration.

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
