# Yorimichi V2

The original Yorimichi island, rebuilt as an Unreal 5.8 project whose **editable content is committed** to Git LFS.
After hydrating Git LFS and fetching the pinned restricted content, a checkout opens the game without Blender
or a world-generation/import job. Work is split into
small owned parts, so several people and agents can change different things at once. The migration design is in
[the V2 plan](../../docs/YORIMICHI_V2_PLAN.md). Status is in [docs/INVENTORY.md](docs/INVENTORY.md), choices are in
[docs/DECISIONS.md](docs/DECISIONS.md), and the pinned engine and tools are in [docs/TOOLCHAIN.md](docs/TOOLCHAIN.md).
The retired original in `games/yorimichi` stays as a source reference; its tests remain disabled.

**Current scope (owner decision, 2026-11-10):** migration is complete; further useful-object splitting is on demand
for the model or placement being changed. Start with its [owning record and targeted editing route](#how-content-is-owned-and-changed).
There is no whole-game splitting prerequisite for a selected edit. Generated-model geometry edits still require an
independent generator before the edit, as described below.

[INVENTORY.md](docs/INVENTORY.md) remains the canonical progress overview for the whole-island package checkpoint
and saved follow-ups. It distinguishes prepared, imported, saved, merged, packaged and human-verified work.
The migration scope decision does not certify pending gameplay, authoring or multiplayer acceptance.

Excluded from this version: phone streaming and the go-kart (`Driving`). Everything else in the original game is in
scope.

## Report a visual issue in game

Open the menu and choose **Dev mode: fly and take notes**. Aim at the issue, press **N** (controller **Y**),
write a note and press **Enter** to save. Press **X**, or choose **Export dev notes** in the menu, to export
notes and screenshots as a zip on macOS. Each note records the map, camera/player coordinates and the hit
actor/component name when the view hits something; it does not yet identify the stable V2 asset/source path.
This describes the existing implementation; human verification on the current package remains open (INVENTORY F27).

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
| `restricted.toml`, `restricted.lock.json`, `restricted.originals.json`, `tools/restricted/` | restricted packages and recoverable originals: declared roots, pinned hashes, links and verified fetch |
| `tools/test/` | the native automation test runner |
| `tools/migrate/` | selected object/region authoring, retained donor adoption and migration recovery tools |
| `tools/editor/`, `tools/package/` | claimed editor saves and warm batches; explicit packaging and acceptance checks |
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

### Restricted content and recoverable originals

Licensed audio and the restricted animation/character/mount/Crater Park roots take the private route in
DECISIONS D05. `restricted.toml` is the current root list; Git ignores their packages, and
`restricted.lock.json` pins each file's SHA-256 and size. With access to the authorized restricted storage (a directory laid out like `unreal/Content`):

```sh
V2_RESTRICTED_SOURCE=DIR uv run python games/yorimichi_v2/tools/restricted/fetch.py fetch   # copy in, verified
uv run python games/yorimichi_v2/tools/restricted/fetch.py pin   # after adoption or a claimed edit; then upload the same bytes
```

Without it these packages are absent locally, and the content check (so every build, play and package) fails with
"fetch required". `--allow-restricted-absent` only notes it, for checkouts without restricted access that do not
build or play. A fetch never overwrites a local file that differs from its pin.

`restricted.originals.json` separately links the restricted packages and Adventure assets to recoverable
models, textures, animation inputs and importer code. Fetch originals when editing their sources:

```sh
uv run python games/yorimichi_v2/tools/restricted/originals.py fetch --source DIR
uv run python games/yorimichi_v2/tools/restricted/originals.py check
```

The package store and original-source store are different inputs. A package alone is an original only when
it was genuinely authored in Unreal; adoption does not establish that provenance.

### Optional music

Fetch the soundtrack directly when needed:

```sh
uv run python games/yorimichi_v2/assets/audio/music/fetch.py
```

V2 declares this under `[release.music]`, not `[fetch].scripts`; `atelier fetch yorimichi_v2` does not
invoke it. The package launcher uses the pinned bundle. Sound effects remain available without music.

### Workspaces on one machine

Keep compiled workspaces and reuse them for later tasks. A new Git worktree pays a full editor compile (17 and
32 minutes in the C01 run) and about 18 GB of build output; a copy-on-write clone of another workspace's build
folders did not help. In the C04 handoff, an already compiled receiving workspace was ready 5.5 s after the
transfer. So each workspace has one writer at a time and moves to its next task's branch only after its Unreal
work has stopped. Supported non-rendering object and static-mesh queues can overlap in two separate owned checkouts when
the broker admits their full reservations and complete package claims are disjoint. Shared maps or environment
packages stay in one sequential queue. Rendered sessions, textures, games, captures, compilation and cooking
remain exclusive. Two checkouts on this machine do not prove a second-machine workflow (DECISIONS D03).

## Everyday commands

Commands are repository interfaces; the linked evidence pages identify the revisions and scope actually
exercised. Historical timings are examples, not full-game performance guarantees. Run focused tests only for
changed behavior and reuse passing evidence; hosted CI runs the active suite.

```sh
uv run python games/yorimichi_v2/tools/content/check.py [--full] [--json]   # read-only; exit 1 lists each problem and its fix
uv run atelier build yorimichi_v2 --list
uv run pytest games/yorimichi_v2/tests/test_content_check.py -q   # example: only when the content checker changes
uv run python games/yorimichi_v2/tools/import/run.py ASSET_ID --plan        # what a targeted import would write
ATELIER_AGENT=OWNER nice -n 10 uv run atelier build yorimichi_v2           # check + compile (cold ~17 min, warm 1 s)
V2_EDITOR_READ_ONLY=1 V2_EDITOR_SCRIPT=$PWD/games/yorimichi_v2/unreal/Scripts/open_close.py \
  ATELIER_AGENT=OWNER nice -n 10 uv run atelier build yorimichi_v2 editor.run   # one guarded editor script (here: open a map, save nothing)
uv run python games/yorimichi_v2/tools/content/save_validate.py ID --claim TASK   # record an editor-owned asset or region after a save
ATELIER_AGENT=OWNER uv run python games/yorimichi_v2/tools/import/run.py ASSET_ID --claim TASK   # targeted import (prop/lantern: 30 s, 1 package; unchanged rerun 1 s, no Unreal)
uv run python games/yorimichi_v2/tools/migrate/adopt.py --donor-content DIR --folder F --check-only   # one-time donor adoption, one record per ownership unit (D08)
uv run python games/yorimichi_v2/tools/migrate/adopt.py --repartition --check-only   # split older per-folder adopted records into units
uv run python games/yorimichi_v2/tools/migrate/adopt.py --pin-data --claim TASK   # pin unreal/Content/Data in runtime-data.lock.json after a claimed change
uv run python games/yorimichi_v2/tools/migrate/run.py REGION... --environment REGION --claim TASK   # one-time world migration (the slice: 803 actors); a rerun keeps every migrated actor and its edits
uv run python games/yorimichi_v2/tools/migrate/compare.py ORIGINAL.json V2.json   # parity of two scene dumps
V2_EDITOR_READ_ONLY=1 V2_EDITOR_SCRIPT=$PWD/games/yorimichi_v2/unreal/Scripts/capture_poses.py V2_CAPTURE_DIR=DIR \
  ATELIER_AGENT=OWNER nice -n 10 uv run atelier build yorimichi_v2 editor.run   # editor diagnostics into an empty DIR, saves nothing; runtime parity uses capture_runtime.py below
uv run python games/yorimichi_v2/tools/parity/compare.py DONOR_DIR V2_DIR --out OUT --min-ssim S   # visual parity of two receipted capture sets (all poses in poses.json)
uv run python games/yorimichi_v2/tools/parity/capture_runtime.py --source donor-runtime --checkout DONOR --out DIR
uv run python games/yorimichi_v2/tools/parity/capture_runtime.py --session ID --source v2 --out DIR   # the same poses from the running V2 game
# The donor baseline comes from the running donor game (its scenery is spawned at run time); capturing V2 the same way
# keeps both on one render path. Each receipt names the revision the game was proven to launch from (its session, or
# for the donor the process on its live port). capture_poses.py on an editor map proves none: compare.py rejects it
ATELIER_AGENT=OWNER nice -n 10 uv run python games/yorimichi_v2/tools/test/automation.py [FILTER...]   # native tests, guarded (default Yorimichi.V2)
V2_EDITOR_CLAIM=TASK V2_EDITOR_PATHS="REPO_RELATIVE_PACKAGE_AND_COMPANION_PATHS" V2_EDITOR_SCRIPT=$PWD/games/yorimichi_v2/unreal/Scripts/move_actor.py V2_MOVE_ACTOR=/Game/__ExternalActors__/... V2_MOVE_BY_CM="X Y Z" \
  ATELIER_AGENT=OWNER nice -n 10 uv run atelier build yorimichi_v2 editor.run   # move one saved actor, save only its package (31 s)
ATELIER_AGENT=OWNER nice -n 10 uv run atelier play yorimichi_v2   # whole island, normal window; retains guards and prints its session ID
ATELIER_AGENT=OWNER nice -n 10 uv run atelier play yorimichi_v2 --profile slice -- -RenderOffscreen   # same island map; historical profile name
uv run python games/yorimichi_v2/tools/test/route.py --session ID --out DIR     # walk + skate route in that game, report.json
uv run python games/yorimichi_v2/tools/test/train_ride.py --session ID --out DIR   # board, ride and leave the Belmonte train
uv run python games/yorimichi_v2/tools/test/ferry_ride.py --session ID --start hidamari   # board, cross and leave the ferry
uv run python games/yorimichi_v2/tools/test/gondola_ride.py --session ID --start hidamari belmonte floor   # ride each gondola line
uv run python games/yorimichi_v2/tools/test/budgets.py open --out DIR           # a plan §15 budget: warm-up + 5 runs, receipt
```

Routine play uses the saved renderer and tree-optimization preferences. If a session needs a larger memory ceiling,
use the supported `--memory-gib N` option (10–24), with its full admission reservation and a recorded reason;
larger guarded sessions are already authorized. Do not force a heavier renderer for routine work.

On main since [#837](https://github.com/fontanierh/atelier/pull/837), normal desktop play uses an
aspect-matched scene target 1440 pixels high; its width follows the window aspect. The window's logical size
on a Retina display is not the render-target size. Offscreen captures retain their requested `-resx`/`-resy`,
and explicit non-1440p windowed launches retain their selected size. Check the `DESKTOP PREVIEW viewport=`
log for managed desktop sessions and the actual image dimensions for captures. This describes the current
source behavior; older packaged apps retain their own revision's behavior. Current merged changes and their
acceptance limits are in [INVENTORY](docs/INVENTORY.md#post-handoff-development-checkpoint).

`/Game/V2/Maps/TestMinimal` is the minimal World Partition map (`map/test-minimal`, `region/test-minimal`): it opens
from a fresh checkout without donor content. Collaboration test results are kept in
[docs/COLLABORATION_TESTS.md](docs/COLLABORATION_TESTS.md), the slice budgets in [docs/BUDGETS.md](docs/BUDGETS.md).

### Warm editor batches

Use the existing import caller to prepare and journal a batch; static meshes select the headless route, while
textures stay rendered. The caller preserves completed accepted jobs after a later job fails.

```sh
ATELIER_AGENT=OWNER uv run python games/yorimichi_v2/tools/import/run.py ID1 ID2 --claim TASK --batch 20
ATELIER_AGENT=OWNER uv run python games/yorimichi_v2/tools/editor/session.py JOBS.json --headless
```

`JOBS.json` is `{"jobs": [...]}`; the job schema and examples are in `tools/editor/session.py`. Headless sessions
accept object migrations and prepared static-mesh imports only. Each job retains its own authorization,
save lists and result check; import receipts become accepted only after the editor exits and the caller
validates them. Keep loaded code fixed for the batch. A shared package stays with one controller and queue.
The object queue's 15-job proof and production import use are recorded in
[COLLABORATION_TESTS.md](docs/COLLABORATION_TESTS.md).

## How content is owned and changed

Every package under `unreal/Content` belongs to exactly one record. The content check fails on a package that
nobody owns.

**Before an agent or human edits a generated model, first make its generator independent.** Confirm that the
model can be generated from its own explicit parameters and inputs without constructing the rest of its city,
region or unrelated collection. If not, parameterize the generator to select the model before construction,
or extract a separate model script, with shared helpers kept shared. Preserve the accepted result during
that refactor, then apply the requested geometry change. A separate source mesh or Unreal asset alone does
not meet this requirement. Record the selected generation and import route with the asset. Imported or
hand-authored models instead need their independent editable original and targeted preparation/import route.
Follow the [model-edit workflow](../../docs/WORLD_BUILD_PRACTICES.md#make-a-model-independent-before-editing-it).

- **Generated asset** (`authority = "generated"`): its sources and recipe are authoritative, and only its importer
  writes its packages. After the model-edit prerequisite above, change its source and run the targeted import
  for that asset ID. The importer skips unchanged inputs without starting Unreal and writes only the declared
  packages. A failed job retains or restores its journaled writes; already accepted jobs in a batch stay completed.
- **Editor-owned asset or saved actors** (`authority = "editor"`, region actor records): the saved package is
  authoritative for editor edits; save under its claim and record the result with save validation. This write
  authority does not establish source provenance. Adopted imported/generated art still needs its original inputs
  or generator route. Only genuinely Unreal-authored content may use its package as the original; use the
  recorded owner route when changing or recovering it.
- **Split** assets name the writer of each output.

Before changing a binary package, claim its scope and complete write paths (`atelier claims`). D04 closed
on 2026-11-07: `governance.toml` has `closed = true`, and every writer now needs a claim. A claimed migration (`tools/migrate/run.py --claim TASK`) may
create new actor packages in its claimed regions; they are bound to the claim with their LFS locks before they
are recorded.

For an interrupted object save, follow the [object claim recovery steps](docs/inventory/transport-objects.md#recovering-object-package-claims).
`objects.py --claim-paths` includes existing selected placement records' package files and companions, even when
save validation has not yet written their receipts. Listing paths does not validate or accept the save.

The normal build and play never generate, import, resave or cook. Packaging is explicit and runs a full-hash
content check first.

```
ATELIER_AGENT=OWNER nice -n 10 uv run atelier build yorimichi_v2 unreal.package --cook-memory-gib 20   # explicit guarded cook; revision-bound timings are in PACKAGE.md
ditto build/yorimichi_v2/package/archive/Mac/YorimichiV2.app "$HOME/YorimichiV2-Package/YorimichiV2.app"
uv run python games/yorimichi_v2/tools/package/acceptance.py automated --app "$HOME/YorimichiV2-Package/YorimichiV2.app"
ATELIER_AGENT=OWNER nice -n 10 uv run atelier playtest yorimichi_v2 --app "$HOME/YorimichiV2-Package/YorimichiV2.app" --memory-gib 22
```

The last line plays the extracted package under the render lock and memory guard. The
[current package checkpoint](docs/PACKAGE.md#current-development-package-checkpoint-2026-11-11) contains the final
migration and later performance/visual work; its automated results do not complete manual acceptance. Use the
[testing handoff](docs/PACKAGE.md#testing-the-final-handoff) to select a revision or matching package, record
observed manual checks and keep each package's evidence separate.
