# Independent foliage builds

The foliage pilot separates the shared library from world placement. A tree, bush or grass asset owns its complete
export and imported LOD chain. Shared textures, material graphs, instances and parameter collections have a separate
owner. Existing `/Game/Japan/Assets/<name>` paths remain stable, so placement data can keep referring to them.

**Validation status:** recipe edit-boundary and protocol tests run without native tools. The October 14 native
source proof passed on Blender 5.2.1 LTS: all 64 legacy mesh records and serialized geometry matched. The serialized
comparison ignores Blender's auto-numbered collision data-block names in nine trunk FBXs, while preserving their
UCX model names and all geometry. All 100 split output files were byte-identical across repeated exports, another
directory and reversed asset order in a fresh process. A byte-pattern scan found no common local-path prefixes in
those files. The read-only Unreal 5.8.2 baseline covers all 18 assets and leaves their package bytes unchanged.
Split-import equivalence, incremental repair, package
loading and cooking remain acceptance gates. No end-to-end speedup is claimed; source `cache=True` and automatic
native package caching stay disabled until their remaining gates pass.

## Edit one asset

Specifications live in [`assets/foliage/`](../assets/foliage): generator, seed/shape arguments, material palette,
LOD strides and screen sizes, and collision policy. The stable catalogue lives in
[`world/asset_catalog.py`](../world/asset_catalog.py); shader settings are separate from the asset ID list.

```sh
uv run atelier build yorimichi unreal.foliage.Tree_Maple_A --plan --explain
nice -n 10 uv run atelier build yorimichi unreal.foliage.Tree_Maple_A
```

Use normal render-board admission before the second command. The selector builds prerequisites and only the
selected tree's source/native owner. `world.foliage_lods` selects all exports; `unreal.foliage` selects all imports.
An ordinary `atelier build yorimichi` includes the library and the final content/network data assembly.

An existing Interchange-imported mesh first passes through its owned FBX seed to establish legacy import data.
The final pass then applies the declared metre-to-centimetre settings while preserving the package object and
path. Bounds are checked before importing LODs and again after assembly; a failed migration stays uncertified.

| Owner | Reads | Writes |
| --- | --- | --- |
| `world.foliage.<name>` | Its specification, generator/helper closure, declared texture bytes and Blender tool context | `build/yorimichi/foliage/<name>/`: LOD0, authored LOD FBXs, private import seed and manifest |
| `unreal.materials` | Shared shader recipes, textures, isolated import module and engine/configuration | Shared textures, materials and collections; `materials/foliage-interface.json` |
| `unreal.foliage.<name>` | That source product, the material interface and isolated import module/engine/configuration | Its mesh package, `Japan/FoliageLODs/<name>/`, sidecars and an import validation report |
| `unreal.world` | Legacy world/region products; stable library package paths | Legacy world content, preserving the exact material and foliage catalogue |

The material interface records the stable material paths and `lod_blend` flags baked into mesh import. Native
foliage references the material packages and reads this interface. Legacy forest/treehouse imports still read the
full shared material product where their code inspects material state. Do not replace those reads with references
just to reduce invalidation.

The native owner resets stale LODs, collision, slots and CPU-access settings before applying its full recipe. It
validates triangle counts, bounds, material order, screen sizes and trunk collision. Base FBXs no longer come from
`world.props`; the world importer skips stale pre-split foliage FBXs and preserves only exact owned package paths.
Collision validation counts convex UCX hulls separately from box, sphere and capsule primitives; Unreal's simple
collision count excludes convex hulls. The final collision trace policy must also match the specification.
Regional importers must not modify shared material instances. Private regional material namespaces are checked for
collisions with the shared catalogue.

## Bounded process reuse

Each completed action keeps its own historical `atelier build yorimichi <step> --timings` and `--changes` receipts,
including when it shares a process with other actions. Phase IDs are scoped to that action; output differences
compare its previous certified inventory. Optional sidecars appear as added or retired members, while an absent
sidecar is not a retained output member. These diagnostics do not enter product identity, grant admission or
establish native equivalence; the native proof and remaining acceptance gates below still apply.
Batch action timings exclude shared startup/shutdown and host validation/acknowledgement; `--timings` labels
that scope instead of allocating the shared overhead to an asset.

Independent export/import misses can share a guarded process. Blender resets its scene and foliage caches between
assets; Unreal scripts read their per-action environment inside `main()`. Every asset keeps its own key, validation
and success stamp. A failed later action leaves earlier verified work available for the next invocation.

The session uses the normal BIG lock and 10 GiB guard, measured growth, and a 240-second between-action budget.
Exit 75 (`BATCH YIELDED`) saves the completed prefix and prints the resume command. Check Waiting and hand off
before resuming without `--force`, keeping the original first-ready age. `--plan` shows the remaining actions as
`run`. Full logs and guard telemetry are under `logs/batch.<id>.*`; individual action logs and stamps remain.
Session logs and `.state/batches/<id>` receipts are local diagnostics; prune completed sessions with routine log
maintenance after retaining needed evidence. They are excluded from whole-build reuse and artifact publication.

## Proof before enabling caches

The portable FBX adapter fixes timestamps and generated IDs and removes texture file references from the exported
material slots. It is included in action inputs. Exporter/tool changes invalidate source results. Geometry, vertex
and polygon order, material slot order and collision remain significant; deterministic metadata cannot conceal a
change to them.

Native validation must establish all of the following:

- Compare the old generator/importer with the split output for all 18 assets: geometry and ordered indices,
  materials, bounds, LODs, collision and runtime flags.
- Export cold, warm and from another directory, then reverse action order. Require identical source bytes and
  equivalent native package contents. Verify at least three imports in one guarded session with usable telemetry.
  Compare the sampled per-action growth with the session guard peak; short spikes may fall between samples.
- Repeat a no-op build with no tool launch. Edit one specification, one LOD helper, a consumed alpha texture and
  a shared shader separately. Record selected actions and all changed output hashes; a shader-only change with
  an unchanged interface must leave foliage imports current.
- Check an interrupted import and missing/corrupt outputs. Verify a clean build agrees with the incremental result.
- Load and cook the assets, including treehouse/forest users of the shared materials. Check references, foliage
  fading and trunk collision in the editor and packaged game.
- Before portable source or native publication, scan for checkout paths and prove restore/reimport without the
  donor checkout. Whole-build reuse remains stricter: same clean revision and engine, complete inventories and a
  fresh target with no Intermediate/Saved discovery caches.

This pilot does not split terrain, regional geometry, characters, sounds or cooking. Their legacy dependencies
remain until equivalent ownership and edit-boundary proofs exist. Follow the platform's
[world practices](../../../docs/WORLD_BUILD_PRACTICES.md) and [recipe API](../../../docs/BUILD_RECIPES.md) for the next
package family rather than copying a filtered region into another checkout or touching stamps.
