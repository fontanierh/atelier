# Region build layers

A region publishes separate geometry, material, placement, terrain and clearance products. Consumers read the products they use. Run the ordinary `atelier build GAME TARGET --plan --explain` command to inspect the graph; the normal build performs verified reuse and executes the remaining work.

## Brinecove consumer boundaries

`world.brinecove` produces the regional export. `world.brinecove.meshes` publishes five independently inventoried views under the game's build folder:

| Product | Contents | Consumer |
| --- | --- | --- |
| `brinecove.geometry` | All model records, complete model membership and actual model hashes | `unreal.brinecove` |
| `brinecove.materials` | Material definitions and consumed texture hashes | `unreal.brinecove` |
| `brinecove.runtime` | Complete instance placements and runtime records | `data.stage` |
| `brinecove.map` | Tree placements, zones, regional clearance and declared final ground | `world.map` |
| `brinecove.clearance` | Every non-plant placement plus its actual model bytes and bounds | `world.ferry_probes` |

Adding or moving an instance of an existing tree changes placement/runtime and the map. It leaves the model/material import and ferry geometry products unchanged. Changing a tree model reaches the model importer. Changing ground reaches the map and ferry probe. Moving a solid pier reaches the ferry probe; moving authored pier/building layout also reaches the map through its layout source inputs. The probe still uses every non-plant group, including decorative solids, according to its existing collision-sweep algorithm.

Brinecove's 36 plant prototypes have independent source owners, `world.brinecove.model.NAME`, publishing `brinecove.model.NAME` under `models/brinecove/plants/NAME`. Each model consumes one committed definition plus shared geometry, UV/atlas and export code. It has no terrain, layout, instance-placement or material-colour input. The normal checkpoint store reuses these complete input/tool-keyed products; remaining models can share a bounded, guarded Blender batch. The model library is required by the ordinary regional export, with no alternate inline generation path.

A placement edit can still rerun the regional terrain/town/placement assembly, but it does not regenerate the plant models. Changing one model definition rebuilds that model and its consumers. The ordered catalogue preserves existing model/group order and checks additions/removals. Assembly verifies independent GLBs before copying them into its complete regional inventory. The initial transition needs these new source products and may export the 36 models once; historical outputs are not certified under new tool identities by inference. Native GLB byte parity and timing remain unmeasured.

The terrain, town and hero-model portions still run together. GLB files can contain embedded material metadata, so a material change that also changes a GLB still changes its geometry product. No native cook or import saving is claimed solely from Python dependency tests.

Model additions and removals participate in complete inventory checks. Missing, changed, linked or unreported model files fail publication. The map's ground sampler still verifies the selected report entries against actual GLB bytes; its selected fields are represented in the map product. The ferry consumer reads the clearance view directly, and runtime staging reads the runtime view.

## Producer layering across regions

Use the same layers for every region, following [world build practices](WORLD_BUILD_PRACTICES.md). Preserve real terrain contact and seam dependencies while splitting expensive generation into these owners:

1. Natural terrain and boundary constraints from roads, pads and authored footprints.
2. Final terrain after those constraints, with explicit boundary/seam products.
3. Unique models: one building, kit component or species per independently reusable owner.
4. Materials/textures independently from model transforms.
5. Shared-model instance placements, runtime markers and gameplay records.
6. Actual footprint, collision and clearance geometry consumed by fitting and route checks.

Brinecove's remaining terrain/town/hero owners, Hidamari's kit/city/north/vegetation and Belmonte's preparation/materials/terrain/planting are subsequent producer slices. Existing terrain, train, ferry and gondola consumers retain their real source and product reads until their replacements have equivalent coverage. A reference edge must never hide a consumed terrain, bounds, material or collision value.

Each slice needs execution regressions for unchanged inputs, instance movement, model/material changes, footprint changes, terrain changes and membership additions/removals. Assert both the executed task set and unchanged unrelated output bytes. Native adoption additionally reports actual reused/imported counts and current geometry, material and collision checks.

## Bounded mixed-model pieces

The ordinary Brinecove exporter keeps its final ground tiles and existing small model identities.
Mixed non-ground parts above 32,768 fan triangles are divided into fixed spatial child cells.
Each whole face goes into one cell, preserving its positions, normals, UVs, material and role labels;
solid/soft collision policy and identity placement transforms stay with every piece. Child names
use the original 256 m tile and quadrant path. They remain stable only while their ancestor
subdivision decisions remain unchanged: crossing the budget can split or collapse a parent and
rename its children. Persistent authored model/piece ownership remains separate work. The exporter
refuses invalid or unresolved coincident over-budget geometry rather than silently exporting another oversized monolith.

This is a bound on source triangle work, not a proven bound on a later representation's JSON bytes
or native memory. Final ground, independent plant prototypes and hero models retain their current
owners. More pieces can improve culling while adding draw calls/material sections. Actual culling,
collision continuity, GLB/native bytes and same-input frame/build timing need receiving validation;
no speed or memory result follows solely from the pure partition tests. The initial topology-owner
transition is real source work and must wait for an ordinary stopped receiver boundary.

Regional generation/export is still one owner. Separate piece preparation/checkpoints, bounded
per-LOD transport, per-building owners and compact native geometry transport remain required work.
The current production foliage run must not adopt this change before its first game measurement.
