# Adopted-record ownership: current state and audit context

Snapshot: **main `028bc6243b` (2026-11-10)**. This page replaces the initial proposed-unit counts, which
predated recovery and adoption. The current status index is [INVENTORY](../INVENTORY.md); source closure is
tracked in [sources.md](sources.md), and unfinished useful-object boundaries in [exceptions.md](exceptions.md).

## Landed ownership changes

| Family | Current record structure | What it establishes |
|---|---|---|
| City surfaces | 1,048 generated `prop/citysurfaces/*` records, plus the adopted generator record | Accepted per-record source/import ownership; saved placements still have their own region ownership |
| Island terrain | Recovered per-piece generated records; the old adopted family retains its generator record | Terrain recovery is no longer an unwritten units-map proposal |
| Belmonte train | 67 generated mesh records, 138 texture records and 21 material-instance records | The seven residual adopted records are retired: #796 imported their 459 packages (138 textures and 321 instances), with matching read-back. The 14 unused standalone LOD packages were retired in #790; vehicle records retain their LOD chains |
| Gondola | 26 adopted records / 96 packages, 16 saved route placements | Saved stations; the ten towers are saved as their own objects (by the retired `gondola_pylons.py`, see git history) and the three pylon groups are retired |
| Ferry | 4 adopted records / 66 packages, 2 saved terminal placements | Both terminals have saved placement ownership |
| Railway | 14 adopted records / 146 packages, 24 saved route placements | Stations, bridge and track sections have saved ownership. The twelve per-fitting objects are saved and the old group retired (#790) |
| SkateRide | 692 adopted records / 3,331 packages, including 691 clip-family records | The prefix/chunk split proposal has landed; clip originals and importer code follow the restricted manifest |
| Japan models and ten smaller families | 100 Japan model records; 141 family meshes and 29 textures recovered | The old unsourced-model grouping list is obsolete |
| Brine Cove | Eleven small props, three ship/hull placements, all 21 market stalls, all 265 town objects, two harbour Soft fragments, signal mast and shipyard slip saved on main | #787 completed town/ship tile retirement and preserved fused originals; #798/#800 completed mast/slip. Residual useful-object boundaries remain in [exceptions](exceptions.md) |

The two terminal placements, sixteen gondola placements and twenty-four railway placements are recorded in the
corresponding `world/regions/*/objects.saved.json`. A units map describes ownership; a saved receipt describes
accepted package bytes. Neither by itself proves gameplay or that every useful item inside a group is independent.

## Current rules

- Each package has one record or region owner. Object placements refer to the current recovered model IDs;
  `tools/migrate/object_models.py` reconciles model references without re-saving unchanged actors.
- Region claims and shared scopes still protect writes. One active claim must cover a route's complete touched
  set, including its environment companions. Keep one controller per mutable editor checkout.
- Restricted storage is a supported editable route. `restricted.originals.json` on main links 6,768 restricted
  packages and 124 Adventure/animation packages; do not revive the old request to locate every clip library.
- Rendering batches may remain. An actor or record that bundles several useful objects still needs an editing
  boundary for those objects. Terrain and scatter counts are not counts of missing objects.
- Imported binaries with unknown originals remain unfinished until recovered or replaced. They cannot become
  Unreal-authored merely by changing an authority label.

## Historical audit context

[PR #787](https://github.com/fontanierh/atelier/pull/787) is merged, including town2–9, source preservation and
retirement of 42 emptied town tiles and three ship tiles. Its first town2 attempt was reverted after a package-name
collision; those first import completions remain rejected evidence, while the corrected saved batch is accepted.
The master-material follow-ups are tracked separately in [INVENTORY](../INVENTORY.md).

The historical audit's proposed `groups.toml` edits and counts remain in Git history. Do not reapply them to current
records: doing so could recreate deleted adopted IDs or overwrite a recovered owner's package.
