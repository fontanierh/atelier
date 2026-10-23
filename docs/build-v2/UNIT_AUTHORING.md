# Writing a build v2 unit

This guide is for someone adding a unit declaration to the build v2 engine. Production builds still run
on v1; nothing here changes a live recipe. The parseable example is
[`platform/build-v2/examples/units.toml`](../../platform/build-v2/examples/units.toml), and the field
reference is [`platform/build-v2/README.md`](../../platform/build-v2/README.md).

## Choose a unit

A unit is one piece of work with one key and one saved result. Make it as small as it can run on its own:
one exported piece, one imported item, one finished asset, one placement region, one map, one cooked
package.

Two things belong in the same unit when neither is useful without the other, or when one cannot change
while the other's output stays valid. Split them when:

- each output is consumed separately;
- an edit to one input should not rerun the other;
- a failure in one should not block the other;
- one part is a cheap plan or query and the other is expensive work.

Never make a unit read the checkout as a whole. A unit sees only its declared inputs, copied into an
empty job folder. Blender and Python jobs run in a sandbox that refuses reads, existence checks and
listings outside it. Unreal jobs cannot be sandboxed per job, so they use file tracing and saved-package
reference checks instead; that is best effort, and the clean-rebuild comparison is the safety net.

## Declare exactly what it reads

Declarations are TOML files with `schema_version = 1` and a `cache_version`, followed by one or more
`[[units]]` tables.

`code` lists every project-owned code file the unit runs: the entry `script` plus the modules and
helpers it loads. The entry script must appear in `code`. Data and settings the unit reads are
`inputs`, not `code`. Paths are project-relative with forward slashes, and `..` is refused.

`inputs` names each input. Every `name` must exist in that op kind's definition, with the role the
definition expects. A content input takes its bytes from one of these:

- a file: `{ role = "content", name = "shape", source = { kind = "file", path = "data/shape.json", selector = "/triangle" } }`;
- another unit's item: `source = { kind = "item", unit = "sample.plan", item = "harbor" }`.

A file input may add `optional = true` when the op allows an absent file. Absence is not the same as an
empty file, and both are part of the identity. A `selector` is an RFC 6901 JSON pointer and copies only
that part of the file.

`params` are the op's own settings, typed by its definition. Content the unit reads belongs in
`inputs`; code belongs in `code`.

Missing an input produces stale content; adding an input the unit does not read wastes work and is
reported. Declare optional and conditional branches too, and use `conditional` to say when the unit or
content input is used.

## Content, reference and query roles

An input's `role` is either `content` or `reference`.

| Role | What enters the key | Use it when |
|---|---|---|
| `content` | The bytes, or the selected value, or the exact output of another unit | The result depends on the contents |
| `reference` | Only `logical_path` and `class` | The unit points at a package by path but never reads its bytes |

A reference must name a `proof`: the test that shows changing the referenced bytes does not change this
unit's output. Without that proof the input is content. A reference may name a `producer` item so the
producer can be scheduled, but the producer's bytes never enter the key. Mesh material slots are the
usual reference case; a material instance's parent is probably content, because its switches change the
result.

A query is not a third input role. It is a small unit that computes the few values a consumer needs,
and the consumer takes the query's output as a content input from an item. Use queries, or a narrow
selector, when only part of a larger result affects the output.

## `whole` notes

`whole = "why"` goes on a content input that reads a broad or aggregate output without a narrower
selector or query, for example a whole package set, map or large file. The reason is mandatory when the
op definition marks that input slot as needing one; the validator refuses the declaration otherwise.

Do not add a note to an already bounded input. One mesh payload, its FBX, or one query result needs no
`whole` note. Before writing one, try the cheaper shapes: build a mesh in local space and place it,
stretch or repeat a generic part, split off the part that must follow the ground, or query only the
needed values. A `whole` note is for the case where the unit really consumes all of it.

## Stable IDs

Choose stable unit and item IDs so graph links and ownership stay clear. Logical output paths/classes and
declared item identities enter the key. A unit's scheduling label alone must not invalidate identical
work.

Choose names from what the thing is, not from its position, index or list order. Adding a piece must not
rename the others, or identical work gets new identities.

Changing package paths, classes or declared item identities changes the work; renaming a unit's
scheduling label alone does not. A plan that drops a piece removes that piece's old outputs; it does not
imply anything about its neighbours.

## Keep raw, finish and placement separate

These stages have different inputs and different owners, so they are different units.

- **Raw import** owns one item's scratch Unreal package set in the store. It never writes a checkout
  asset path.
- **Finish** owns one asset's checkout package: material slots, collision, LODs and build settings. It
  takes the raw set as content and references what it only points at. Changing finish rules re-finishes
  without re-importing.
- **Placement** owns one region's runtime layout file, and names the assets it places as references. It
  does not own their bytes.
- **Map** owns only what is baked into the `.umap`.
- **Compile**, **cook** and **package** are separate units with their own receipts and lifetimes.

Do not let finish re-export, let placement claim meshes, or let an assembly claim sibling outputs by
listing a manifest. Independent pieces stay independent until a declared merge unit combines them.

## Output ownership

Every output item declares `id`, `logical_path`, `class`, `files` and `destination` (`store`, `checkout`
or `external`, for example Zen-owned cooked data whose adapter defines the locator).

`files` is the complete permitted set, including optional sidecars. Each file's `path` is relative to the
job output folder. A checkout item needs an `install_path` under the allowed checkout roots. `required`
defaults to true; set it false only for a genuine optional sidecar, and keep at least one required file.

Each checkout path has exactly one final owner across the declaration. Within each unit's job, each
output path is claimed once; different isolated jobs may use the same relative filename. Checkout owners
are refused for overlapping paths, an owner claiming both an ancestor and a descendant, case or Unicode
aliases. Declared code and source inputs may not overlap any checkout install path. Store outputs may
share a logical path with a finish output because they never share mutable files. List every file and
sidecar: a missing, altered or unexpected file fails acceptance.

## Staged paths

The agreed contract is that each input's path inside the job folder, its extension and its normalised
file mode are part of the key. An executable bit is restored on install, so a mode change is a real
change. The source location, the selector text and job IDs are not part of the key, because a job sees
only the staged bytes, never where they came from. The selected values still enter through content
identity. Moving a source file without changing its staged layout and bytes therefore does not rerun the
unit; changing the staged layout does.

Staged input paths must not alias a code or script path or the writable `output/` tree, including
ancestor, case and Unicode aliases. Key construction and staging must enforce this.

Worker enforcement of this contract is still pending. Do not rely on it yet as proof that a declaration
is keyed correctly.

## Platform invalidation is explicit

The key covers the cache version, op kind and version, project code, worker and validator versions,
params and inputs. Installed tools are treated as stable and are not fingerprinted automatically:
Python, installed libraries and lockfiles, Blender and add-ons, Unreal, Xcode, SDKs and clang.

When a platform change needs fresh results, invalidate deliberately:

- bump `op.version` for the affected op kinds;
- bump `cache_version` for a full rebuild.

Old results stay in the store. An op-only bump that produces identical bytes still stops downstream
work. Do not add tool versions to `code` or `params` as a substitute; the version bump applies the rule
to every unit of that op.

## Tests to supply

Every declaration arrives with tests that make its claims checkable:

- each content input changes the key; if the output still comes out identical, downstream work stops,
  which is a correct result;
- changing a reference's bytes leaves the key unchanged, under the named `proof` test;
- the unit runs twice and produces identical output, byte for byte where our own formats are concerned
  (Unreal packages use the class comparator that lists the fields it ignores);
- the sandbox refuses an undeclared read for Blender and Python jobs;
- required outputs are present and validated, a missing or altered required output fails, and an absent
  optional sidecar is accepted;
- an input the fixture never reads carries a `conditional` note saying when it is read;
- Unreal-side changes, when the unit has any, get a real Unreal run; a replay does not cover them.

The declarations themselves are checked by the schema and the validator. Those checks do not prove
determinism, key correctness or native equivalence; the tests above do.
