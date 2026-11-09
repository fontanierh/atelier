# Decisions

Short records of real deviations from, or choices left open by, [the V2 plan](../../../docs/YORIMICHI_V2_PLAN.md).
Newest last. Each says what was decided, why, and what would reopen it. Historical setup decisions are marked
as such; [INVENTORY.md](INVENTORY.md) is the current implementation status.

## D01 — Baseline identities (P0)

- **Source baseline:** `7eec0f98dd02c9505d3870336717b3edf830be73` (main, 6 November 2026).
- **Reference release:** `yorimichi-macos-2026-10-23-r13`, built at `bd5382b1`, which is `main` at `7f3c0a8f` plus two
  build-system fixes. Its manifest, `package-manifest.json`, `SHA256SUMS` and `verification.json` stay on the GitHub
  release; they are not copied into the repository.
- 114 commits touch `games/yorimichi` or `platform/engine` between `bd5382b1` and the source baseline. V2 ports the
  source baseline. The release is a play reference only: where its behavior and the baseline's differ, the
  inventory row records which one V2 follows.

## D02 — Reconstruct the donor once (completed bootstrap decision)

The donor was built and used for adoption. The following records the original reason and recovery route; it is
not a request to rebuild the retired game or rerun its disabled tests. Preserve pinned originals and accepted
outputs independently of the old donor checkout. See [donor/README.md](donor/README.md).

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
- **Second machine for C02/C06/P3.4/P6.4/P7.3:** none is reachable from this session. These proofs remain **unverified**, not substituted. A fresh clone on the same
  machine does not count as a second machine. Later owner direction (D11) permits independent migration while
  these acceptance items wait.

## D04 — Bootstrap binary-content writer (§9)

**Historical bootstrap rule (closed below):** until P2-B's claim service passed and adopted or released every
bootstrap lock, the **only** V2 binary-content
writer on all machines is the owner `jim-macbook-5`, in workspace `atelier-yv2`. Other workers may change text
code only. This record is the task record visible to every worker.

Enforcement: `tools/content/authority.py` is the one rule every write route calls (import, `editor.run`, save
validation, adoption). A claimed write is checked with `atelier claims check --stage publish` (exact paths,
verified LFS locks); without a claim only the bootstrap writer passes, and not in a checkout that has a claims
task. **Closes** once the slice's adopted content is merged: from then on every binary write needs a claim.

The switch is committed state, not a convention: `governance.toml` `[d04]` names the writer and `closed`
(`false` until the slice merges). `authority.authorize` reads it on every unclaimed write; when closed, or
when the file is missing or malformed, nobody is exempt on any route (import, editor script, save validation,
adoption, migration). Closing D04 is a reviewed one-line commit.

**Closed 2026-11-07**, after the slice's adopted and migrated content merged (#738, #740) and the claims service
passed C21 on GitHub LFS locks (#739). No bootstrap lock remained: the only V2 locks on the remote were held by active
claims. `governance.toml` has `closed = true`, so every binary write now needs a claim, the former writer's included.
The tests pin their own open or closed switch (`tests/conftest.py`), never the committed one.

New actor packages under a claim (the migration after D04): World Partition names a One File Per Actor package
(`__ExternalActors__/<map>/…/<hash>.uasset`) only when it saves it, so no claim can list it beforehand.
**Chosen: claimed creation, bound after the save.** A run whose claim holds every touched region's scope
(`region/<name>`, exclusive in the claim service) may create files in those regions' maps' actor folders
(`Region.actor_folders`). The `migrate.map` step denies saving every existing package the claim does not list
exactly; after the editor, `authority.bind_created` compares content snapshots taken before and after: a created
file must have been absent, unrecorded and inside those folders, or the run is refused; changed or deleted
existing files must be exactly claimed. The created files are then added to the claim with their LFS locks
(`atelier claims extend ID --lock-path … --acquire`, the claim service's documented route for new files under a
region) and pass the same publish check before save validation records them; each must end in a touched
region's record. Nothing unbound reaches a commit: if the claim service fails the bind, the checked created files move
out of the content tree to `build/yorimichi_v2/migrate/pending/`, and `tools/migrate/run.py --resume` binds and
records them later without another editor run. *Rejected: reserving actor paths before saving.* It needs an
editor dry run to predict the hashed names and fails whenever the editor names a package differently; the
created set measured from the disk is exact by construction.

## D05 — Asset rights before public upload (§4, P0 pass/stop)

The repository is public and Git LFS is not private storage. At the initial baseline, source records did not establish editable-redistribution rights.
A later source or package record must retain its actual provenance and approved route. The inventory (inventory/world.md §5) sorts V2 content into three groups:

1. **Public LFS allowed, per source:** a package goes to public LFS only when its own source has a recorded
   permission for redistributing it in editable form: owner-made, AI-generated with a provenance record, or a
   third-party license that allows it (fonts under OFL). That a source is already published in this repository is
   not that permission, since nobody recorded checking its terms. This covers terrain, houses, props, foliage, the
   skate pier, effects and fonts. **Third-party animation is not cleared yet:** Mixamo's terms allow its clips in a
   game but not distributing them as files, and an editable animation package is such a file. The characters and
   skate rider (`/Game/Cairo`, `/Game/CairoAdventure`, `/Game/Modori`, `/Game/Nox`, `/Game/Paul`, `/Game/SkateRide`,
   `/Game/SkateMotion`; their clips are Mixamo-derived or of
   unrecorded origin) therefore take the group 2 route until each source's permission is recorded; then a root is
   removed from `restricted.toml` and `.gitignore` in a reviewed commit. The full port (2026-11-07) adds the same
   way the mounts and their riders (`/Game/Horses`, `/Game/{Cairo,Modori,Nox,Paul}{Bike,Horse}`), the combat
   characters (`/Game/FoxHunter`, `/Game/SwordTrainer`, `/Game/Wanderer`), whose animation origin is not recorded, and
   Crater Park (`/Game/CraterPark`, group 3 below) until its license is recorded.
2. **Restricted, never public LFS:** sounds cut from the Sonniss GDC masters (and, until cleared, the group 1
   animation roots). Their license forbids sharing them
   as a sound pack of their own, and the masters are fetched, not committed. These SoundWave packages go to
   authorized restricted storage, with pinned hashes and a documented fetch. The music library stays the
   existing pinned external release (plan §14). Mechanism: `restricted.toml` declares the roots (`/Game/Audio`,
   `/Game/Japan/Audio` and the group 1 animation roots, Git-ignored), `restricted.lock.json` pins each file, `tools/restricted/fetch.py` pins and
   fetches, and the content check fails on a tracked or unpinned restricted file (README, "Restricted audio").
3. **Blocked pending the owner (now empty).** **Super Ultra Mega Park** (`assets/megapark`, W11, F26, F31) was
   held here because its data carries retail material identifiers, a decoded vertex codec and baked lightmaps, and
   its provenance as "Atelier's own asset library" was unverified. **Cleared 2026-11-08:** the owner granted its
   asset permissions in full ("Mega park asset permissions fully granted", relayed on the agent board, #31124). Mega
   Park is therefore group 1: its packages (`/Game/MegaPark`) and runtime data (`Data/megapark`) go to public LFS
   like any other adopted content, and the full port includes its standalone level and static dressing. The
   clearance covers the park's assets only; go-kart driving (X02) and phone streaming stay excluded. Crater Park's
   source (`fontanierh/crater-skate-park`) is very likely the owner's own, but V2 records its license before
   upload; until then its packages are restricted (group 2 storage), so the port plays it without uploading it.

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

## D08 — Adoption is per ownership unit, package paths unchanged

Donor packages enter V2 once, through `tools/migrate/adopt.py`, keeping their package paths. Only ownership is
split: each adopted folder's packages become editor-owned records of one ownership unit each, by default one per
folder two levels below `/Game` (`adopted/japan/hidamari`, owner `shared/japan/hidamari`), split by subfolder and
then into sorted chunks so no record lists more than 200 packages. Units are prefix-free, so separate edits claim
separate units instead of contending on one folder-wide record (C01, C19). `adopt.py --repartition` rewrites the
earlier one-record-per-folder records into these units with identical membership. A folder of unrelated packages, or one that would
only split into sorted batches, takes a rule in `assets/adopted/groups.toml`: its packages split by what they are
(one record per feature, family or area, named by a capture of the package name; an unmatched package gets its
own record), so two unrelated edits never claim one record. This took the 131 mixed Japan props, the skate clips
and the atomic terrain and city cells from 74 records to 270, with the same 6820 packages and the same paths. Save
validation records the record's bytes. Adoption records package ownership; it does not turn an imported binary into an Unreal-authored original.
Source recovery can replace it with a generated record and its targeted import route (D11). A finer record (a prop, a region's map) may take packages over explicitly. Adoption refuses packages another
record owns, reports every hard reference that resolves to nothing in V2, and reports packages whose bytes name
a home folder or private host. Those need the editor scrub before commit. Runtime data (`Content/Data`) is
copied from the donor's staged data and committed as runtime data. The rights groups of D05 decide which
folders are adopted publicly.

## D09 — The desktop look is the game's own, and the island backdrop stays loaded

The original's look came partly from its desktop launcher (`tools/desktop_preview.py` and the shipped launch
script), not the game. Every forward start passed a sky light at a third (`r.SkylightIntensityMultiplier .33`), no
distance fields, a 3 lux harbor fill, cascade caching off, a shadow slope bias of 3, and vsync. V2 does not depend on that donor launcher.
`UJapanPreferences::Apply` sets the renderer-dependent part: forward has a third of the sky light, no
distance-field AO and the harbor fill; Lumen has the full sky light. The fixed cvars are in `DefaultEngine.ini`
`[SystemSettings]`, so play and a packaged build agree. Without them, the slice's surfaces were 10–34% brighter
and bluer than the original.

The original spawns every island piece (terrain, far hills, road, lane, guardrail, wires), the sky dome and the sea
at load. The sky light captures the scene beyond 1.5 km once, so the migration places those actors always loaded
(`migrate_map.always_loaded`), not streamed. An island cell or a scenery instance that no region of the map holds
belongs to the environment region, so the island has no holes. This includes the harbour's water (`HD_Sea`), whose
anchor lies on open water outside every region. A run that leaves a region out never gives that region's cells to the
environment.

## D10 — Three static leftovers: the mini Mega ramp and the Ronin camp are objects; the Crater cloud stays runtime

The runtime spawns three static pieces from code, outside any region file. Each has a manifest check (D07) or a reason
to stay at runtime.

- **Mini Mega ramp (W03), saved.** `object/megaramp/ramp` (w03-mega/objects.toml, `static = ["Mega_Ramp", "Mega_Trim"]`)
  is one unit: both meshes at world.json's `mega` origin, built by `AMegaRamp::MakePiece` (the same builder
  `AMegaRamp::Initialize` uses, so collision is unchanged: Mega_Ramp blocks and is ridden, Mega_Trim is look only). The
  runtime ramp is not spawned when the manifest lists both meshes as `mega:Mega_Ramp` and `mega:Mega_Trim` and their
  packages exist. Models: `prop/mega/ramp` and `prop/mega/trim` (recovered targeted imports).
- **Ronin camp props (W13), saved.** A new region `w13-swordcamp` (region.toml, a box around (-5400, 9400) cm) holds four
  objects, `object/swordcamp/{fire-pit,jinmaku,weapon-rack,bales}`, one SM_Camp* mesh each. Their placement is
  `SwordTrainer::RoninCampPropPlacement`, the same frame, table (`FindRoninCampProp`) and ground trace
  `SpawnRoninCamp` uses. `SpawnRoninCamp` skips a prop the manifest lists as `swordcamp:SM_Camp*`. The camp's Kasa
  Ronin and the trainers are combat (F04, F05) and stay runtime. Models: `prop/swordcamp/camp-fire-pit`, `camp-jinmaku`, `camp-weapon-rack` and `camp-bales`.
  **Recorded verification gap:** runtime clearing visits AJapanWorld-owned instances, whereas saved patches are
  separate actors. Migration may already have baked the 15.5 m camp clearing; no revision-bound closure is
  recorded here. Confirm the saved W13 clearing during the remaining appearance/editor acceptance, without
  blocking unrelated migration. The donor rule is in inventory/world.md §0.
- **Crater cloud (W12), runtime by design.** `ACraterCloud::Spawn` builds its five lens shells as
  `UProceduralMeshComponent`s from the committed record `craterpark/cloud.json` (1.2 MB, generated by the adopted
  craterpark cloud source). No static mesh asset exists for it. Saving it would mean new generated mesh assets with their
  own record and generator, for scenery with no collision, shadow, tick or replication. The record stays the single
  source of truth, so the runtime build is kept. Revisit only if the cloud becomes an editable object.

## D11 — Finish the full port with recoverable, independently editable content (2026-11-07–09)

The owner authorized the full original-game migration in small playable increments. Perfect slice measurements,
unavailable collaborators and later human playtests do not block independent content work. Keep guards,
claims, targeted imports, separate mutable checkouts and one controller per editor. Phone streaming and go-kart
driving remain excluded; Mega Park is cleared in D05.

Every useful object must be independently editable, even when rendering retains instancing or batching.
Imported art needs its models, textures and applicable rig/animation inputs; generated art needs its generator,
settings and inputs. Only content genuinely authored in Unreal can use its saved package as the original.
Unknown sources stay unfinished until recovered or replaced, and restricted originals keep their pinned route.
The first wreck/Brine Cove proof does not close this whole-game requirement.

The warm editor queue and supported disjoint headless overlap are implemented; see
[COLLABORATION_TESTS.md](COLLABORATION_TESTS.md). Preparation workers handle concrete separate batches while
native queues run. Reuse existing batching and journals; preserve completed work for retries. Run focused checks
for changed behavior and required hosted CI, not repeated full local suites or unrelated benchmarks.

On 2026-11-09 the owner explicitly placed human and multiplayer playtesting after construction, including a live
multiplayer session with his brother. Human-editor and actual second-machine proofs remain open acceptance
items, not development gates. Track merged, saved, packaged and play-verified work separately in
[INVENTORY.md](INVENTORY.md), updating it with each completed batch.
