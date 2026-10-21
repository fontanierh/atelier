# World build practices

This guide has two halves. [Keep the world whole](#keep-the-world-whole) covers how regions, terrain and
built pieces must fit together so playtests stop finding holes, gaps, floating objects and invisible faces.
The rest covers how a world is structured for small rebuilds. The enforceable form of both is
[`games/CONTRACTS`](../games/CONTRACTS), which contract review checks on every PR that touches a game.

## Keep the world whole

Each rule below comes from a defect a playtest found after it had shipped. Design them out when you write the
generator, and add the check while the code is fresh.

**Ground on what is drawn.** Several surfaces often exist at one point: natural and carved stages, a coarse
backdrop hidden under a fine region, a neighbour's apron. Players only see and touch the final surface of the
footprint's owner. Seat trees, props and buildings with that owner's final product or its exact height function.
Never seat them on a hidden or superseded surface, and never on `max()` or `min()` of two. Hidamari's forest stood
up to 8 m in the air because placement took the higher of the city ground and the far hills hidden beneath it.

**Give every seam one owner.** Where two surfaces meet, one side owns the edge: usually the finer one, or the region
the player stands in. The other side follows the owner's exact edge profile, from the same function and samples, and
fades back to its own shape over a declared margin. That applies to surfaces that abut edge to edge. Where one surface
lies over another (paving, a deck or a slab over ground), the upper one owns the footprint, and the lower one stays
below it by a declared clearance instead. A coarse mesh needs vertices where the fine edge bends; a straight coarse
edge across a curved fine one leaves slivers. Clamped lookups past a grid's range (`np.interp` holds its last value)
are a common cause of a flat edge beside a sloping neighbour. A skirt or wall may close an intended height change, but
must never hide a mismatch you cannot explain. For every new or moved boundary, add a test that samples both sides
along the whole edge and asserts zero difference (or the seam's named tolerance). The slit west of the hippodrome came
from two such edges, 18 m apart, with no test.

**No one-sided sheets.** A quad renders from one side only. Anything the camera can see from below or behind
must be a closed solid, a slab with thickness, or (for intended thin surfaces such as cloth, foliage cards, flags
and decals) a two-sided material. That includes roofs, eaves, awnings, canopies, decks, bridges, stairs, balconies
and signs. Roofs sit on their wall plates, and soffits and gable infill close them from below. Openings such as
windows, doorways and open pavilions are fine when their edges are finished with a reveal, frame or thickness.
Build with closed primitives rather than bare faces, and keep winding consistent. Brinecove's `geom.py` has a
`panel` slab and a seated `gable_roof`. Similar copies live in several regions; consolidate them into a shared
module when you next change one.

**Make pieces meet by construction.** Compute adjoining edges from one plan: treads and risers, landings,
walls and roofs, paving and kerbs, platforms and skirts. Do not tune separate offsets until they look close
enough. A slab floating above the ground leaves daylight under it, so anything standing on the ground extends
below its lowest point. Coplanar faces flicker, so overlap them by depth or by material, or remove one.

**Walkable means walked.** The character steps up 0.45 m (UE MaxStepHeight). Keep risers at most 0.3 m (about 0.25 m
reads best), with treads deep enough to land on, landings between long flights, and flush joins at both ends. A stair
once rose 25 m in 24 one-metre risers on floating slabs, and the terrace paving walled off its top. Plan checks and
ray traces do not prove a route: drive the character up and down it in a guarded game (a committed scenario, or
`live.drive` / `UYorimichiLive::Drive` over the live bridge) and record its position and movement mode.

**Fix the class, not the instance.** When a playtest finds one of these defects, fix the general mechanism and
add an automated check of the rule (a seam sampler, a grounding check, a closure check), so the next region of
the same kind is covered without anyone remembering. When a fix cannot be checked automatically (a pure material
or art change), say why in the PR and attach captures. Bind captures and traversal evidence to the source revision
they ran on.

## Structure the world for small rebuilds

Structure a game so that changing an asset rebuilds that asset, changing its placement updates placement data,
and changing terrain updates the affected area. A region should describe the world it uses through explicit
inputs and references. It should own its outputs and preserve the outputs of other regions.

These practices support [normal incremental builds](INCREMENTAL_BUILDS.md). The [recipe guide](BUILD_RECIPES.md)
explains named products, narrow inputs and spatial queries; [build checkpoints](BUILD_CHECKPOINTS.md) covers
cross-revision reuse. Older generators need complete independent output ownership before individual cache
entries are safe. Native generators and runtime-derived query volumes still need migration and validation.

Measure an expensive generator before choosing its split. Emit phase boundaries for source loading, neighbour
queries, simplification, AO, collision and export, then inspect `atelier build <game> <step> --timings`.
The [phase protocol](BUILD_RECIPES.md#measure-work-inside-a-command) works through stdout without a shared helper
dependency. Keep measurements outside content products. Nested phases include their children; unmeasured command
time can include admission, interpreter startup and shutdown, so it is not evidence of editor startup alone.
After a representative small edit, inspect `--changes` to see which named-product members changed and which
stayed identical. Unknown baselines need another comparable successful build before drawing conclusions. Use
these measured boundaries to choose smaller owners; a report of retired content is not a deletion command.

## Separate assets from their placement

Keep a reusable library for trees, rocks, street furniture, building kits, vehicles, character parts, materials
and sounds. Give each asset a stable ID. Regions refer to those IDs and specify transforms and overrides.

For example, changing a bench's position should update a harbour placement record. Changing the bench mesh
should rebuild and import that mesh once. Every region referencing it then uses the updated asset at the same
logical path. Placement generation needs to rerun only if it reads a changed property, such as the bench's bounds.
Use a reference-only edge only when the consumer embeds no derived asset data. HLOD/HISM bounds, baked lighting,
visibility, embedded collision and compiled material usage are read dependencies even if they are stored in a map.

Generate reusable meshes around a local origin. Apply region placement separately. Bake world position into
geometry only when the operation actually needs it, such as terrain fitting or neighbourhood AO, and declare
those inputs. A moved region may then reuse its library meshes while rebuilding its terrain and neighbour effects.

A useful source layout is:

```text
games/<game>/
  assets/                         committed source library and manifests
    foliage/
    buildings/
    characters/
    audio/
  world/
    terrain/                      height and surface generators
    regions/<region>/
      layout.py                   placements and markers
      terrain.py                  local cuts, pads and boundary constraints
      geometry.py                 geometry unique to this region
      connections.toml            roads, entrances and other declared joins
  build.py                        composes recipes and declares dependencies
```

This illustrates responsibilities, not a required filename schema. Generated files still belong in
`build/<game>/` or the game's ignored Unreal Content directory. Licences, source paths and checksums remain
with committed source manifests.

## Make outputs small and independently consumable

Separate a region's mesh library, placements, terrain constraints, collision, lights, gameplay markers and
runtime data. Consumers should read only the products they need. A region-wide JSON file should not combine
unrelated outputs simply because one script currently emits them together.

Split expensive generation at natural units: a tree species, building-kit part, animation clip, terrain tile
or bounded collision section. Shared parameters should be data inputs. A shared helper implementation changing
may legitimately rerun all consumers; splitting its responsibilities reduces accidental dependencies.

Small cache units do not require one Blender or Unreal process per unit. The executor may batch compatible
units into one guarded process while keeping their manifests independent. Avoid thousands of tiny Unreal
packages where a bounded spatial/material group is a better runtime unit. Measure memory, package overhead,
draw calls and rebuild scope together.

Opt-in [batches](BUILD_RECIPES.md#reuse-a-tool-process-without-merging-actions) preserve these independent keys and
receipts. Reset per-asset module caches and tool state explicitly; test a cold asset, a warm asset and reversed asset
order. A bounded session yields capacity with completed results saved, so an agent must coordinate before resuming.

## Give every generated package one owner

An importer owns a declared package set and fully describes the final settings of those packages. Material
assignment, LODs, collision policy, CPU buffers and other overlays are part of that owner's recipe or explicit
inputs to it. A later region must not silently patch another region's material or mesh.

Shared materials and audio libraries have their own owners. A region can create an instance of a shared material
and own its parameters, while the shared shader remains independently built. Keep package paths stable across
ordinary edits. Add or remove only outputs belonging to the current owner; never clear a parent namespace to
prepare a normal import.

When an import requires replacement to clear stale settings, replace and validate the affected asset while
preserving references. Removing a source asset is a real deletion: update references and the output inventory,
and verify that the old asset no longer enters the cooked game.
Imported source metadata must resolve through the receiving project's stable staging layout and source catalog.
Test reimport without the original checkout. Rename/deletion tests must also check the asset registry and redirectors.

## Describe terrain and neighbour dependencies

Regions often share ground, roads, rivers and vegetation boundaries. Make those relationships explicit through
height/surface tiles, footprint masks and connection records. Each boundary should have one source of truth
for coordinates, height samples, normals and any blend margin. Both sides use the same units and samples.

A generator querying neighbours must record the query volume and its contents. Hash both the selected assets
and the selection itself: a new wall can cast AO on a ramp, and removing that wall must update the ramp too.
Movement invalidates the old and new influence volumes.

For audited Python actions, declare a product's conservative `collection` and six-coordinate `bounds`, then add
a `BBoxQuery` to each consumer's `queries`. Use one coordinate frame and unit per collection. The graph resolves
inclusive intersections before scheduling, and `atelier.build_context.query(name)` returns only those frozen
products. Read source catalogue JSON freshly inside `steps(ctx)`; importing a cached module's global catalogue
does not refresh it. Keep the raw catalogue out of the consumer's inputs so distant edits stay independent.
See [the runnable sandbox example](../games/sandbox/README.md#spatial-dependencies-without-unreal) and
[the API and limits](BUILD_RECIPES.md#spatial-product-reads).

Use the operation's actual reach. AO may need a 12 m margin; a support cast down to terrain may need a 30 m
vertical volume; a road smoother can influence a longer stretch. Tile sizes and margins should be derived from
these operations and measured edit patterns. A fixed tile grid without border dependencies creates cracks and
stale geometry.

Global reductions need special care. A world-wide minimum used as a grid origin can change every tile when one
remote vertex moves. Use fixed world-space grids and stable local frames. Where an operation is genuinely global,
give its result an explicit product and allow the build graph to show its real cost.
For example, Crater Park's [`spatial_order`](../games/yorimichi/world/regions/craterpark/build.py) subtracts
`centres.min(0)` before computing Morton codes. That is valid for today's global ordering pass; caching its chunks
requires a stable origin and spatially local groups of 64 collision triangles within each chunk.

## Keep identity and randomness stable

Use persistent source IDs for pieces and placements. Use derived IDs based on their owner and stable local feature
identity for generated rails and collision sections. Do not number the entire world in discovery order: inserting
one piece must not rename every later output. Position-derived identity is appropriate only if moving the element
is intended to replace it.

Seed procedural generation by world seed, region/tile ID, asset ID and purpose. An added tree must not advance a
single global random stream and rearrange a distant forest. Keep output order deterministic. Preserve meaningful
ordering, especially collision triangle order used by acceleration structures and gameplay.

Keep elapsed time, machine paths and debug reports out of content manifests. Distinguish a source's byte hash
from a proven semantic digest. A normalized digest is only valid if its ignored fields cannot change what the
consumer does. Full byte checksums still verify storage and transport.

## Keep world assembly thin

The persistent map should hold global atmosphere, startup and references needed to compose the world. Region
placement belongs in separate records or region maps. Updating one region should not resave all the others.

A runtime JSON/HISM world can follow this structure without converting every object into an editor actor.
Sublevels or Level Instances can provide useful boundaries for authored scenes. World Partition can serve
streaming and large editor workflows. Choose the representation for those needs; import dependencies still need
to be explicit regardless of the map format.

Runtime loading by string or manifest must be reflected in the cook roots. Include soft references, data-driven
asset paths and plugin mounts. Test a packaged game as well as the editor so an asset present in a developer's
Content folder cannot hide an incomplete cook.

## Keep code dependencies narrow

Separate gameplay code from stable serialized asset types and editor import helpers. An input tuning change
should not reimport trees. Changing a saved asset type, import helper or relevant configuration must invalidate
the content that uses it.

Use data products for most regional differences. Introduce a C++ module for a coherent code responsibility,
and a content plugin for a reusable library with a stable mount. Region boundaries and C++ module boundaries
do not need to coincide.

Characters follow the same pattern: separate body, skeleton, textures, clips, retarget configuration, fit results
and runtime definition. A texture edit should not retarget motion. A rest-pose or skeleton change should reach
every clip that actually uses it. Sounds should be imported by cue or a small bank independent of world geometry.

## Verify the edit boundary

For every new recipe, keep a representative edit with an expected affected-output set:

| Edit | Expected work |
| --- | --- |
| Move one prop | Placement data; local terrain/neighbour effects only if they read that placement |
| Change one texture | Its texture product and required derived data; dependent material compilation where needed |
| Change a tree LOD | That tree's final mesh package and relevant cooked data |
| Change a ramp | Its geometry, affected neighbours, collision sections, rails and placement metadata |
| Change one animation | That clip, its actual retarget consumers and affected verification |
| Remove an asset | Its inventory entry and references; retirement of its generated and cooked packages |
| Change the world seed | Every procedural product that consumes the seed |

Compare incremental results with a clean build, including bounds, slots, LOD counts, collision, seams, references
and gameplay. Check that unrelated output hashes are unchanged. Test both adding and removing neighbours, an
interrupted build, missing outputs and reuse in a different worktree. Timing alone cannot detect stale content.

With today's build engine, use explicit `inputs`, `products` and content-dependent `reads`; use `references` only
for products whose contents the consumer does not inspect. Legacy `needs`, order-only `after` and cutoff steps
remain supported. Keep unsupported cases conservative. Use the ordinary checkpoint lookup for completed task
results and current native source/options validation for staged candidates; complete ownership and matching
inputs are required. Follow the recipe examples and edit-boundary tests when narrowing another region.

For a generator with one Python command, `audit=True` checks observed file reads and writes before certification.
It catches a placement generator accidentally reading a reference-only mesh or reusing old output bytes. Declare
whole directories only when their complete membership is an input, and use owned outputs or private scratch for
temporary files. For a conditional read of one known source, declare `optional_inputs=[path]` instead of its parent
directory. Its absence and content are tracked without making sibling files dependencies; it grants no listing
or source-write access. The [recipe guide](BUILD_RECIPES.md#audit-a-python-generators-accesses) explains the enforced checks
and the metadata, environment and native-I/O limits. This audit complements clean-versus-incremental comparisons.

## Current regional consumer boundaries

Brinecove publishes separate geometry, materials, runtime, map and clearance views. Belmonte uses the same
library projection for geometry (including relocated collision hulls), materials/default bindings and runtime.
Their exporters still contain combined generation work; these consumer boundaries do not by themselves split
natural terrain, road/pad constraints or individual building generation into separate producers.

Belmonte's native importer reads `belmonte.geometry` and `belmonte.materials`; it does not reopen placement
runtime data. Its complete final mesh library, material/texture library, racing screen material and report have
separate native products. Track import reads the material view and the native material/texture product, so a
revalidated geometry package or racing screen does not invalidate track when those consumed materials stay
byte-identical. Runtime staging reads `belmonte.runtime`. Placement transforms, signs and plant instances still
reach the complete runtime view while leaving the model and default-binding views unchanged.

These native products are workspace checkpoint results, never portable-cache entries. A changed input or missing
product still takes the ordinary validated import. Adding these inventories causes one receiving validation
transition; it must be measured on a stopped warm checkout before claiming native time or cook-byte savings.
The projection currently fingerprints its whole texture directory to grant audited access to selected texture
files. As in Brinecove, an unused texture can therefore rerun the small projection without changing its products.
This is a remaining scoped performance exception, not a completed producer split or an edit-locality guarantee
for the projection itself. Focused build-graph tests cover actual downstream propagation and missing/hull proof.
