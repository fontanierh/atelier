# Yorimichi V2: the package (P7)

Plan: `docs/YORIMICHI_V2_PLAN.md` §12 P7, §14 "Desktop and package behavior", §18. This file is the controller's
command sequence for P7 steps 1–4. Every command says whether it exists in the repository and whether it has run for
V2. A command marked **not yet runnable** is a gap; the reason is written beside it.

Commands run from the repository root. `atelier` commands run in the canonical checkout (its artifacts and installed
engine). Nothing here publishes or pushes.

## What the package is

- Cook and package: `atelier build yorimichi_v2 unreal.package --cook-memory-gib 20` (`UnrealPackage`: UAT
  `BuildCookRun -cookall -stage -pak -package -archive`, macOS). `unreal.package` is explicit, so a plain build never runs
  it. The donor's slice cook needed more than the default 10 GiB guard ceiling (PARITY, "Packaged slice").
- Content: every committed package under `unreal/Content` is cooked (`-cookall`). Restricted roots (`restricted.toml`:
  `/Game/Audio`, `/Game/Japan/Audio`, the character and mount animation roots, `/Game/CraterPark`) are absent from a fresh
  checkout and must be fetched and pinned first. The package step refuses an absent or changed one.
- Cook configuration: `unreal/Config/DefaultGame.ini` `DirectoriesToAlwaysCook` covers every top-level `/Game` folder that
  code, scripts, config, live tools and runtime data load by path. The package step runs
  `tools/package/cook_config.py` and fails on: a string-loaded root not cooked, excluded feature content (X01 phone
  streaming, X02 kart driving) in `Content`, a missing map (`GameDefaultMap` or a play profile), or the template Mac bundle
  identifier. Phone booths are city scenery and are not excluded.
- App identity: `unreal/Config/Mac/MacEngine.ini` sets `BundleIdentifier=com.atelier.yorimichiv2`, so V2's saves live in
  their own sandbox and do not touch the donor's. The key name is the one `MacTargetSettings` uses and is **not yet
  verified against a packaged `Info.plist`**. The acceptance `identity.bundle_id` check is that verification.
- Optional music: `assets/audio/music/fetch.py` and its pinned `music.lock.json`, ported from the donor. It is the same
  bundle, the same bytes, the same `yorimichi` cache, so it is downloaded once. Without it the game is silent; required
  sound effects are complete without it. Declared as `[release.music]` in `game.toml`.

## Sequence

### 0. Before the cook

| Command | Status |
|---|---|
| `V2_RESTRICTED_SOURCE=DIR uv run python games/yorimichi_v2/tools/restricted/fetch.py fetch` | exists; needs the authorized restricted storage directory (DIR). Not yet run for this package. |
| `uv run python games/yorimichi_v2/tools/content/check.py --full` | exists; read-only; the package step runs it too. |
| `uv run python games/yorimichi_v2/tools/package/cook_config.py` | exists; prints each failure and warning; exit 1 on a failure. Currently 0 failures and 2 warnings (`/Game/A`, a fixture name in a test; `/Game/HidamariStable`, a disabled feature W14). |
| `uv run python games/yorimichi_v2/assets/audio/music/fetch.py` | exists, ported from the donor; **not yet run for V2**. `atelier fetch yorimichi_v2` does not read `[release.music]`, so the script is run directly. |
| `atelier build yorimichi_v2 --list` | exists; lists the steps and shows `unreal.package` as explicit. |

### 1. Produce the package

```
atelier build yorimichi_v2 unreal.package --cook-memory-gib 20
```

Status: exists; **not yet run for V2 at the final inputs** (the last run was the donor-era slice, PARITY). The step log
records the cook-configuration result, the content check result and the archive path. Keep the archive where the step
reports it; do not re-cook for publication (P7 step 4).

### 2. Extract and verify outside the repository

Extract the archive's `.app` to a folder outside every checkout, for example:

```
mkdir -p "$HOME/YorimichiV2-Package" && ditto "<archive>/Yorimichi V2.app" "$HOME/YorimichiV2-Package/Yorimichi V2.app"
```

Status: `ditto` exists; the app name and the archive path come from the step log and are **not yet confirmed**.

Automated checks (exist; run on the extracted app):

```
APP="$HOME/YorimichiV2-Package/Yorimichi V2.app"
uv run python games/yorimichi_v2/tools/package/acceptance.py automated --app "$APP"
```

These check the identity, the code signature (`codesign --verify --deep --strict`), the bundled dependencies (`otool -L`
resolves inside the package), excluded content names, and the committed runtime-data bytes.

Manual checks, each recorded by the controller after watching the running app. `--note` says what was seen:

```
EV=$HOME/YorimichiV2-Package/evidence.json
uv run python games/yorimichi_v2/tools/package/acceptance.py record --app "$APP" --evidence $EV first_launch pass --note "..."
```

Required items: `first_launch`, `input`, `map_travel`, `gameplay`, `sound`, `settings_persistence`, `save_persistence`,
`shutdown`. Status: `record` and `verify` exist; **the packaged app has no Atelier launch command yet**, so the controller
launches `Yorimichi V2.app` by hand (Finder or `open`). Map travel and gameplay use the routes the slice uses
(`/Game/V2/Maps/Slice`, `/Game/MegaPark/Maps/SuperUltraMegaPark`); the packaged route is not yet automated.

A changed package (a new cook, a new `.pak`) changes the fingerprint, and `record` refuses old evidence. Use `--reset`
only to start the ledger again for the same package.

### 3. Two machines (supported multiplayer target)

Manual. There is no command: two matching packages on two machines, a session on each, recorded with
`record ... two_machine_multiplayer pass --note "..."`. Editor sessions do not count.
Status: **not runnable as a command**; the packaged multiplayer path is not in V2 yet.

### 4. Record identities and verdict

```
uv run python games/yorimichi_v2/tools/package/acceptance.py verify --app "$APP" --evidence $EV --report "$HOME/YorimichiV2-Package/verdict.json"
```

Add `--multiplayer` once step 3 is recorded. The verdict JSON holds the verdict, each check, the package fingerprint, the
bundle identifier, and the git commit and dirty state of this checkout. Exit 0 only when every automated check and every
required manual item passes for this package. Publication is a separate action and not part of P7.

## Tests

```
uv run pytest -q games/yorimichi_v2/tests
```

`test_package_config.py` checks the coverage rules and the committed configuration against the real tree (no hydrated
content needed). `test_package_acceptance.py` checks the ledger and the automated checks on a fake package.

## Known gaps (not yet closed)

- The cook was measured only for the donor-era slice. The final V2 package has not been cooked.
- The bundle identifier key is unverified until a package is built and its `Info.plist` is read.
- The restricted storage (`V2_RESTRICTED_SOURCE`) is needed for any real package; it is not in this checkout.
- Old saves: none imported. The plan allows a one-time versioned copy with validation; none is planned or implemented.
- Forward-renderer and 1440 defaults are set in the donor's settings; not re-measured for V2 in the package.
- The 271 requested-but-absent packages in the slice (PARITY) are not closed by this change; the packaged route still has to
  load them or stop asking.
