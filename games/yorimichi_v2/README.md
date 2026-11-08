# Yorimichi V2

The original Yorimichi island, rebuilt as an Unreal 5.8 project whose **editable content is committed** to Git LFS.
A fresh checkout opens the game without Blender, an import job or anyone's private cache. Work is split into
small owned parts, so several people and agents can change different things at once. The migration follows
[the V2 plan](../../docs/YORIMICHI_V2_PLAN.md). Status is in [docs/INVENTORY.md](docs/INVENTORY.md), choices are in
[docs/DECISIONS.md](docs/DECISIONS.md), and the pinned engine and tools are in [docs/TOOLCHAIN.md](docs/TOOLCHAIN.md).
The original game in `games/yorimichi` stays as the reference until V2 passes acceptance.

Excluded from this version: phone streaming and the go-kart (`Driving`). Everything else in the original game is in
scope.

## Layout

| Path | What |
| --- | --- |
| `game.toml`, `build.py` | identity and play profiles; the build validates and compiles only (`--list` shows the steps) |
| `assets/<kind>/<asset>/` | one asset record each: `asset.toml` (identity, owner, sources, recipe, outputs), `src/` and `prepared/` inputs when it is generated, `verified.json` (the exact package bytes it produced) |
| `world/regions/<region>/` | `region.toml` (bounds, neighbours, maps) and `actors.verified.json` (the saved actors it owns) |
| `schemas/` | the JSON schemas of those records |
| `tools/content/` | records library and the read-only content check |
| `tools/import/` | the targeted importer |
| `tools/review/` | the change-set report for reviews |
| `restricted.toml`, `restricted.lock.json`, `tools/restricted/` | restricted audio: declared roots, pinned hashes, pin and fetch |
| `tools/test/` | the native automation test runner |
| `tools/migrate/` | one-time migration: donor adoption, the world migration runner, scene dumps and their parity compare |
| `tools/parity/` | visual parity: the slice's named poses (`poses.json`) and the capture compare (`compare.py`) |
| `unreal/` | `YorimichiV2.uproject`, `Config/`, `Source/` (by feature), `Plugins/HorseRacing`, `Scripts/` (editor scripts), **`Content/` (committed)** |
| `tests/` | Python checks for these tools |

## Setup

Requirements and the pinned engine are listed in [docs/TOOLCHAIN.md](docs/TOOLCHAIN.md). Git LFS must be installed
(`git lfs version`). The repository's hooks apply LFS's read-only flags to lockable files, and upload LFS objects
before a push.

```sh
git lfs install --local                               # once per clone: without the LFS filter, a pull skips everything
git lfs pull --include="games/yorimichi_v2/**"        # the committed content
uv run python games/yorimichi_v2/tools/content/check.py   # is every package present, current and owned?
```

### Restricted audio

Sounds cut from licensed masters never go to public Git LFS (DECISIONS D05 group 2). `restricted.toml` lists their
roots (`/Game/Audio`, `/Game/Japan/Audio`); Git ignores them, and `restricted.lock.json` pins each file's sha256
and size. With access to the authorized restricted storage (a directory laid out like `unreal/Content`):

```sh
V2_RESTRICTED_SOURCE=DIR uv run python games/yorimichi_v2/tools/restricted/fetch.py fetch   # copy in, verified
uv run python games/yorimichi_v2/tools/restricted/fetch.py pin   # after adoption or a claimed edit; then upload the same bytes
```

Without it these packages are absent locally, and the content check (so every build, play and package) fails with
"fetch required". `--allow-restricted-absent` only notes it, for checkouts without restricted access that do not
build or play. A fetch never overwrites a local file that differs from its pin.

### Workspaces on one machine

Keep compiled workspaces and reuse them for later tasks. A new Git worktree pays a full editor compile (17 and
32 minutes in the C01 run) and about 18 GB of build output; a copy-on-write clone of another workspace's build
folders did not help. In the C04 handoff, an already compiled receiving workspace was ready 5.5 s after the
transfer. So each workspace has one writer at a time and moves to its next task's branch only after its Unreal
work has stopped. This is the proven one-machine workflow. Several machines are a separate gate (DECISIONS D03),
not yet proven.

## Everyday commands

Each command below has been run as written. A command marked *(pending)* exists but has not yet been proven on
real content; it must not be relied on until that mark is gone.

```sh
uv run python games/yorimichi_v2/tools/content/check.py [--full] [--json]   # read-only; exit 1 lists each problem and its fix
uv run atelier build yorimichi_v2 --list
uv run pytest games/yorimichi_v2/tests -q
uv run python games/yorimichi_v2/tools/import/run.py ASSET_ID --plan        # what a targeted import would write
ATELIER_AGENT=OWNER nice -n 10 uv run atelier build yorimichi_v2           # check + compile (cold ~17 min, warm 1 s)
V2_EDITOR_SCRIPT=$PWD/games/yorimichi_v2/unreal/Scripts/open_close.py \
  ATELIER_AGENT=OWNER nice -n 10 uv run atelier build yorimichi_v2 editor.run   # one guarded editor script (here: open a map, save nothing)
uv run python games/yorimichi_v2/tools/content/save_validate.py ID [--claim TASK]   # record an editor-owned asset or region after a save
ATELIER_AGENT=OWNER uv run python games/yorimichi_v2/tools/import/run.py ASSET_ID   # targeted import (prop/lantern: 30 s, 1 package; unchanged rerun 1 s, no Unreal)
uv run python games/yorimichi_v2/tools/migrate/adopt.py --donor-content DIR --folder F --check-only   # one-time donor adoption, one record per ownership unit (D08)
uv run python games/yorimichi_v2/tools/migrate/adopt.py --repartition --check-only   # split older per-folder adopted records into units
uv run python games/yorimichi_v2/tools/migrate/adopt.py --pin-data [--claim TASK]   # pin unreal/Content/Data in runtime-data.lock.json after a claimed change
uv run python games/yorimichi_v2/tools/migrate/run.py REGION... --environment REGION   # one-time world migration (the slice: 803 actors); a rerun keeps every migrated actor and its edits
uv run python games/yorimichi_v2/tools/migrate/compare.py ORIGINAL.json V2.json   # parity of two scene dumps
V2_EDITOR_SCRIPT=$PWD/games/yorimichi_v2/unreal/Scripts/capture_poses.py V2_CAPTURE_DIR=DIR \
  ATELIER_AGENT=OWNER nice -n 10 uv run atelier build yorimichi_v2 editor.run   # (pending) into an empty DIR: one PNG per parity pose + capture.json receipt, saves nothing
uv run python games/yorimichi_v2/tools/parity/compare.py DONOR_DIR V2_DIR --out OUT --min-ssim S   # visual parity of two receipted capture sets (all poses in poses.json)
uv run python games/yorimichi_v2/tools/parity/capture_runtime.py --source donor-runtime --checkout DONOR --out DIR
uv run python games/yorimichi_v2/tools/parity/capture_runtime.py --session ID --source v2 --out DIR   # the same poses from the running V2 game
# The donor baseline comes from the running donor game (its scenery is spawned at run time); capturing V2 the same way
# keeps both on one render path. Each receipt names the revision the game was proven to launch from (its session, or
# for the donor the process on its live port). capture_poses.py on an editor map proves none: compare.py rejects it
ATELIER_AGENT=OWNER nice -n 10 uv run python games/yorimichi_v2/tools/test/automation.py [FILTER...]   # native tests, guarded (default Yorimichi.V2)
V2_EDITOR_SCRIPT=$PWD/games/yorimichi_v2/unreal/Scripts/move_actor.py V2_MOVE_ACTOR=/Game/__ExternalActors__/... V2_MOVE_BY_CM="X Y Z" \
  ATELIER_AGENT=OWNER nice -n 10 uv run atelier build yorimichi_v2 editor.run   # move one saved actor, save only its package (31 s)
uv run atelier play yorimichi_v2 --profile slice -- -RenderOffscreen                # the slice game; prints its live session ID
uv run python games/yorimichi_v2/tools/test/route.py --session ID --out DIR     # walk + skate route in that game, report.json
uv run python games/yorimichi_v2/tools/test/train_ride.py --session ID --out DIR   # board, ride and leave the Belmonte train
uv run python games/yorimichi_v2/tools/test/ferry_ride.py --session ID --start hidamari   # board, cross and leave the ferry
uv run python games/yorimichi_v2/tools/test/gondola_ride.py --session ID --start hidamari belmonte floor   # ride each gondola line
uv run python games/yorimichi_v2/tools/test/budgets.py open --out DIR           # a plan §15 budget: warm-up + 5 runs, receipt
```

`/Game/V2/Maps/TestMinimal` is the minimal World Partition map (`map/test-minimal`, `region/test-minimal`): it opens
from a fresh checkout without donor content. Collaboration test results are kept in
[docs/COLLABORATION_TESTS.md](docs/COLLABORATION_TESTS.md), the slice budgets in [docs/BUDGETS.md](docs/BUDGETS.md).

## How content is owned and changed

Every package under `unreal/Content` belongs to exactly one record. The content check fails on a package that
nobody owns.

- **Generated asset** (`authority = "generated"`): its sources and recipe are authoritative, and only its importer
  writes its packages. Change a source and run the targeted import for that asset ID. The importer skips unchanged
  inputs without starting Unreal and writes only the declared packages. If anything goes wrong it restores them
  exactly.
- **Editor-owned asset or saved actors** (`authority = "editor"`, region actor records): the saved package is the
  source. Save the edit in the editor, then record it with save validation. Never reimport it.
- **Split** assets name the writer of each output.

Before changing a binary package, claim its scope (`atelier claims`). Until the claim service has adopted V2's
protected writes, one bootstrap writer does all binary work (DECISIONS D04); `governance.toml` holds that switch,
and once it is closed every write needs a claim. A claimed migration (`tools/migrate/run.py --claim TASK`) may
create new actor packages in its claimed regions; they are bound to the claim with their LFS locks before they
are recorded.

The normal build and play never generate, import, resave or cook. Packaging is explicit and runs a full-hash
content check first.
