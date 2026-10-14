# Structuring worlds for small rebuilds

Structure a game so that changing an asset rebuilds that asset, changing its placement updates placement data,
and changing terrain updates the affected area. A region should describe the world it uses through explicit
inputs and references. It should own its outputs and preserve the outputs of other regions.

These authoring practices support the [incremental build proposal](INCREMENTAL_BUILDS.md). Several can be used
with today's `Step` recipes. Named products and read-only inspection are implemented in the
[recipe guide](BUILD_RECIPES.md), along with automatic restoration of opted-in portable products. Native Unreal
restoration across revisions and tracked spatial queries remain proposed. Verified whole-build reuse at the same
clean revision supports named products, including native packages.
The [artifact pool guide](ARTIFACT_POOL.md) describes reuse available today.

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

The [foliage pilot](../games/yorimichi/docs/FOLIAGE_BUILDS.md) provides a concrete example: one small JSON specification
per asset, an export product for its complete LOD chain, and one final native package owner. Shared materials publish
a separate, small interface product for the paths and LOD-blend flags imports consume. A shader implementation edit
therefore need not reimport a mesh if that interface stays identical. This separation is valid only when the consumer
does not inspect other shader state; declare those reads if it starts to do so.

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
remain supported. Keep unsupported cases conservative. Adopt the recipe examples and edit-boundary tests as
games migrate, then add dependency tracing and native cache proofs before enabling automatic import restoration.
