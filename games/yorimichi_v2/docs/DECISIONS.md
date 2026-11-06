# Decisions

Short records of real deviations from, or choices left open by, [the V2 plan](../../../docs/YORIMICHI_V2_PLAN.md).
Newest last. Each says what was decided, why, and what would reopen it.

## D01 — Baseline identities (P0)

- **Source baseline:** `7eec0f98dd02c9505d3870336717b3edf830be73` (main, 6 November 2026).
- **Reference release:** `yorimichi-macos-2026-10-23-r13`, built at `bd5382b1`, which is `main` at `7f3c0a8f` plus two
  build-system fixes. Its manifest, `package-manifest.json`, `SHA256SUMS` and `verification.json` stay on the GitHub
  release; they are not copied into the repository.
- 114 commits touch `games/yorimichi` or `platform/engine` between `bd5382b1` and the source baseline. V2 ports the
  source baseline. The release is a play reference only: where its behavior and the baseline's differ, the
  inventory row records which one V2 follows.

## D02 — No editable donor project exists; build one once (P0.3)

A search of this machine found no completed editable Yorimichi Unreal project. The checkouts that still have
`games/yorimichi/unreal/Content` hold only small V2 experiments (at most 40 packages). Every earlier full build
was cleaned up. A cooked release cannot be turned back into editable packages.

**Route:** run the original pipeline once, at the source baseline, in a dedicated migration workspace
(`atelier-yv2-donor`, detached at the baseline). Use the normal guarded `atelier build yorimichi` and the machine's
existing verified build cache. That build's `Content` is the donor. V2 copies packages from it, keeping their
`/Game/...` paths, and never edits the donor in place. After copying, V2 no longer needs that workspace; it is kept
only as a recovery reference until P6.

## D03 — Development hosts (P0.5)

- **Primary:** this machine, an Apple-silicon Mac running the pinned Unreal 5.8 (see [TOOLCHAIN.md](TOOLCHAIN.md)).
- **Collaborator:** the known collaborator machines are one Mac and one Windows device that is rarely online. The
  working assumption is a **macOS** collaborator. The Windows route is:
  **Windows workers do code and review only. All Unreal work uses owned workspaces on a supported Mac.** A
  Windows launch/admission adapter is out of scope unless a Windows host is actually assigned.
- **Second machine for C02/C06/P3.4/P6.4/P7.3:** none is reachable from this session. These checks stay **blocked**, not substituted. A fresh clone on the same
  machine does not count as a second machine (plan §12, P3 stop rule).

## D04 — Bootstrap binary-content writer (§9)

Until P2-B's claim service passes and adopts or releases every bootstrap lock, the **only** V2 binary-content
writer on all machines is the owner `jim-macbook-5`, in workspace `atelier-yv2`. Other workers may change text
code only. This record is the task record visible to every worker.

Enforcement: `tools/content/authority.py` is the one rule every write route calls (import, `editor.run`, save
validation, adoption). A claimed write is checked with `atelier claims check --stage publish` (exact paths,
verified LFS locks); without a claim only the bootstrap writer passes, and not in a checkout that has a claims
task. **Closes** once the slice's adopted content is merged: from then on every binary write needs a claim.

## D05 — Asset rights before public upload (§4, P0 pass/stop)

The repository is public and Git LFS is not private storage. No source in the repository carries a license
field, and there is no LICENSE file. The inventory (inventory/world.md §5) sorts V2 content into three groups:

1. **Public LFS allowed:** packages derived from sources the owner has **already published in this repository**
   with recorded provenance (owner-made or AI-generated with a provenance record). This covers terrain, houses,
   props, foliage, the skate pier, the characters, effects and fonts (OFL). Committing the Unreal form of
   content that is already public does not widen what is published. Raw Mixamo clips are already committed;
   their derived animation packages follow the same rule. **Owner review is still recommended**, because Mixamo's
   terms forbid redistributing raw clips as such.
2. **Restricted, never public LFS:** sounds cut from the Sonniss GDC masters. Their license forbids sharing them
   as a sound pack of their own, and the masters are fetched, not committed. These SoundWave packages go to
   authorized restricted storage, with pinned hashes and a documented fetch. The music library stays the
   existing pinned external release (plan §14).
3. **Blocked pending the owner:** **Super Ultra Mega Park** (`assets/megapark`, W11, F26, F31). Its data carries
   retail material identifiers, a decoded vertex codec and baked lightmaps. Its provenance as "Atelier's own asset
   library" is unverified. Until the owner settles its rights, V2 does not upload its packages. Crater Park's
   source (`fontanierh/crater-skate-park`) is very likely the owner's own, but V2 records its license before
   upload.

Import metadata inside packages must not keep the donor's absolute paths. The staged-package lint scan and the
content check enforce this.

## D06 — Hidamari stable stays as at baseline

At the baseline, `AHidamariStable::bEnabled = false`: the stable exists in source but does not run. The owner
earlier asked to leave the Hidamari stable out of a port. V2 migrates W14's static dressing with the region, and
keeps the service disabled exactly as at baseline. It does not invent a working stable. Reopen this only on owner
instruction.

## D07 — Static scenery is migrated by the code that builds it

The original island is almost entirely spawned at runtime by `AJapanWorld::Load` and its region services
(inventory §0). V2 does not re-describe that scenery in a migration script. A transient, migration-mode
`AJapanWorld` builds it in the editor exactly as the game does: same clearances, collision, shadows, cull
distances, custom data and tags. `UV2Migration::MigrateStaticScenery` then copies each instance group into saved
`AV2ScenePatch` actors, one per group and patch cell inside each region's half-open bounds, with stable IDs.
Each map's `AV2WorldManifest` tells the runtime which instances and services that map holds saved; `Load` skips
them, then registers the patches into the same runtime lists. The menu settings, screen-size cull and see-through
therefore keep working unchanged. A slice map is `bOnlyMigrated` and runs only its listed services.

The saved Slice map's pieces come from the runtime island roster (`terrain/island.json`), placed the way the
original island owner places them. The environment actors repeat `build_level`'s settings. `tools/migrate/
compare.py` compares scene dumps from the two games over the same bounds, and is the parity oracle.

The skate pier (W04) splits the same way: `ASkatePark::Initialize(Path, bSpawnScenery)` keeps its look, rails and
spawns at runtime, and the service `SkatePark.Scenery` saves its meshes and garden trees as one patch of the region
holding the pier, copied from a park the migration loads with scenery.

## D08 — Adoption is per top-level donor folder

Donor packages enter V2 once, through `tools/migrate/adopt.py`, keeping their package paths. Each top-level
`/Game` folder becomes one editor-owned `adopted/<folder>` record that lists every package it brought. Save
validation records the record's bytes. A later edit is an ordinary claimed editor edit of that record, and a
finer record (a prop, a region's map) may take packages over explicitly. Adoption refuses packages another
record owns, reports every hard reference that resolves to nothing in V2, and reports packages whose bytes name
a home folder or private host. Those need the editor scrub before commit. Runtime data (`Content/Data`) is
copied from the donor's staged data and committed as runtime data. The rights groups of D05 decide which
folders are adopted publicly.
