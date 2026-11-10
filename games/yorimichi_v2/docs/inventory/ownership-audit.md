# Adopted-record ownership: current state and audit context

Snapshot: **main `3027366ced` (2026-11-09)**. This page replaces the initial proposed-unit counts, which
predated recovery and adoption. The current status index is [INVENTORY](../INVENTORY.md); source closure is
tracked in [sources.md](sources.md), and unfinished useful-object boundaries in [exceptions.md](exceptions.md).

## Landed ownership changes

| Family | Current record structure | What it establishes |
|---|---|---|
| City surfaces | 1,048 generated `prop/citysurfaces/*` records, plus the adopted generator record | Accepted per-record source/import ownership; saved placements still have their own region ownership |
| Island terrain | Recovered per-piece generated records; the old adopted family retains its generator record | Terrain recovery is no longer an unwritten units-map proposal |
| Belmonte train | 67 generated `prop/belmontetrain/*` meshes; 24 remaining adopted records hold 592 other packages | Imported train meshes are recovered; the seven residual records (473 packages) are classified in [exceptions.md](exceptions.md): none is closed; 321 material slots bind to donor GLBs by name, all 138 textures have a donor original, and the 14 unused LOD1/LOD2 meshes match the donor and are retired by `belmontetrain_lods.py` |
| Gondola | 26 adopted records / 96 packages, 9 saved route placements | Saved stations; the ten towers are saved as their own objects (`gondola_pylons.py`) and the three pylon groups are retired |
| Ferry | 4 adopted records / 66 packages, 2 saved terminal placements | Both terminals have saved placement ownership |
| Railway | 14 adopted records / 146 packages, 13 saved route placements | Stations, bridge and track sections have saved ownership. The track-fittings group is prepared, not saved, as twelve per-fitting objects (one per row of its four mesh groups) |
| SkateRide | 692 adopted records / 3,331 packages, including 691 clip-family records | The prefix/chunk split proposal has landed; clip originals and importer code follow the restricted manifest |
| Japan models and ten smaller families | 100 Japan model records; 141 family meshes and 29 textures recovered | The old unsourced-model grouping list is obsolete |
| Brine Cove | 11 small-prop placements, 3 new ship/hull placements and 6 market-stall placements saved on main | Further market/town splits and old-tile retirement remain active work |

The two terminal placements, nine gondola placements and thirteen railway placements are recorded in the
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

## Follow-up outside this snapshot

[PR #787](https://github.com/fontanierh/atelier/pull/787) contains the additional 15 market stalls and seven town1
placements at reviewed head `ac513cf127`. Town2–9 are pending; a completed import log alone is not acceptance.
The initial town2 attempt was reverted after a package-name collision, and the retry uses a unique-name preflight.
Brine Cove source preservation and the remaining retirements land with the follow-up, not with this status note.

The historical audit's proposed `groups.toml` edits and counts remain in Git history. Do not reapply them to current
records: doing so could recreate deleted adopted IDs or overwrite a recovered owner's package.
