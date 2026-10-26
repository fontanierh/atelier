# World input boundaries

World steps track the files their commands read, including local Python imports. A module that mixes
natural terrain mathematics with railway deformation and export code gives every consumer all those
inputs. Separate those responsibilities before narrowing a dependency: omitting a real read can leave
stale geometry.

Crater Park's editor floor and bowl-seal check use `hidamari/natural_terrain.py`: the original seeded
height function, sampling origin and spacing, and selected caldera depth. `hidamari/mountains.py`
re-exports that API and owns the final joined, carved surface, placement and snow/export operations.
The selected park document and its referenced terrain files remain inputs. Belmonte source meshes,
railway earthworks and station implementation are no longer indirect inputs of Crater Park geometry.
Hidamari, FarHills and Zeppelin still track the final terrain they actually sample; those real geometry
couplings must remain until a separately validated terrain-product boundary replaces them.

Brinecove's source verification has a small build boundary:

```text
assets/source-library.json
  -> world.brinecove.sources (selected model keys + sha256 values; cutoff)
  -> world.brinecove (Blender, also tracking actual GLB/provenance bytes and FarHills final terrain)
```

The selector publishes sorted, deterministic JSON under the generated build directory. Unrelated library
entries and unused metadata produce identical bytes, so the existing cutoff keeps the expensive export
current. Selected additions, removals and checksum changes invalidate it. The production command passes
that declared snapshot explicitly; a missing or invalid snapshot fails rather than reopening the global
registry. Direct authoring invocation still defaults to the committed registry.

Focused tests exercise ordinary build/stamp execution across these boundaries and verify both the
removed incidental dependencies and the retained terrain dependencies. Numerical reference points and
the existing caldera/placement tests protect geometry behavior. These source checks do not establish a
native build-time improvement; measure that at the next owner's normal build boundary.

The atlas signs the extracted kernel and depth configuration as geography inputs too. Its
`coasts/natural-kernel-equivalence.json` witness carries this source relocation into current
attestations using unchanged function/constant ASTs and independently captured height arrays.
Original generation records, paintings, masks and accepted exports remain unchanged; this carry
does not claim a new native export or acceptance run.

Runtime staging also tracks the character roster that determines its bike and portrait paths.
`data.stage` declares `assets/characters/pipeline/definition.py`, every current
`assets/characters/*/character.toml`, and only corresponding **present** `adventure.toml`
paths in deterministic input membership. Absent paths are not required inputs. Adding or removing
a character, changing configuration bytes, or adding/removing even an empty adventure file changes
the existing labeled Merkle input observation (this consumer already reads named products).
No new named product or separate operational-plan digest is used as a task key. A future operational
SourcePlan must still retain explicit absent-path witnesses for execution/repair. Older stamps
that omitted these inputs can miss once. This does not establish a rebuild-count or timing result,
and the remaining staging copies retain their existing byte and mtime behavior.
