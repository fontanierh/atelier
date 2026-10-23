# Blender op contracts (unused library)

D2 defines `blender_plan` and `blender_export_piece`, version 1. They are not wired into the
production recipes or a dynamic backend. This first route supports existing MeshIR schema 2 to
one FBX render mesh with its explicitly owned UCX hulls, plus `export.json`. MeshSet, encoded GLB,
GLB material graphs, arbitrary auxiliary products and native recipe migration remain pending.
No new geometry format, executor, store, scheduler or worker protocol is introduced.

A planner recipe registers `BlenderPlanSpec` with its explicit input slots, parameter schema and
fixed `OutputGroupContract`. The class is `GeometryPayload`, encoding `mesh_ir`, manifest
`plan.json`; keyed `output_root`, `parent` and `plan_limits` must equal that contract. Its declared
entry script calls `blender_ops.run_plan(context, producer)`, where the existing project planner
writes its complete flat output group. The adapter requires current explicit partition, complete
source-face/material mapping and whole-collision ownership, then fully decodes every emitted
member before returning. It never mutates the declared output roster. Existing A4b expansion and
private one-member projections remain the authority for child generation and exact retirements.

Concrete frozen entry scripts live directly under `platform/studio/`, whose directory is the
existing worker's project import root: `build_v2_blender_plan.py` adapts exactly one declared
`source` file without re-encoding it; register that explicit slot on `BlenderPlanSpec`.
`build_v2_blender_export.py` calls `blender_ops.run_export_piece(context)`. Their script files
are additional declared code, alongside `blender_code_files(kind)`; no live PYTHONPATH is used.
A project-specific planner entry may replace the whole adapter while retaining the same fixed
contract and declaring its actually used helper closure.

The piece entry script calls `blender_ops.run_export_piece(context)`. Its sole content input is
`payload`, a selected one-file `GeometryPayload` Item. Keyed parameters are `payload_member`,
`payload_encoding=mesh_ir`, `payload_role=geometry`, `format=fbx`, and optional per-piece `options`
and `seed`. Declare one store-only `StaticMeshSource` Item with exactly one required flat FBX primary and `export.json`. The A4b template's local
Item id stays `asset`; a fixed primary such as `asset.fbx` is independent of the selected piece
name. The native mesh/UCX and receipt asset names bind the selected payload asset, while receipt
primary binds the exact declared filename. Any later file-only assembly maps that declared
primary to its owned destination explicitly. Selection, format and fixed ownership options
cannot be overridden. Manifest and member fields are closed, with duplicate-field refusal over
the exact frozen manifest bytes. Payload and per-piece FBX settings use a small typed allowlist;
unknown keys, nested option objects, nonfinite values, invalid enums and non-boolean flags refuse
before native creation/export or producer completion. `global_scale` is explicitly bounded to
0.001–1000; captured world color must be three finite values within 0–1. Scene batching or copied media is refused. Consumer decoding restores
ordered topology, corner normals, all UV/color channels and roles, material tables, transforms
and explicit collision through the existing decoder/mesh helpers and deterministic FBX exporter.
No sibling, planner input key, roster, source history or absolute checkout path enters this child.

Call `blender_code_files(kind)` to declare the minimum body/helper closure, plus the recipe entry
and all actually used project planner helpers. Freeze their bytes with ordinary A3/C1 staging.
`blender_validator_identity(snapshot)` binds the decoder closure, op/validator versions and limit.
The frozen C2b five-file startup bundle is separately owned by the existing worker adapter.
Installed Blender, add-ons, Python and NumPy are platform/manual invalidation, not automatic keys.

The producer verifies the complete emitted plan with the existing NumPy decoder. The consumer
fully decodes its selected payload and parses its emitted FBX using Blender's existing FBX parser
before writing the receipt and returning Completed. The parser checks complete render/UCX mesh
inventory; it is not an independent normals/material/UV fidelity comparison. B2 validators read
only their certified frozen objects, check exact membership/schema/roles/bounds/hash bindings and
receipt-to-selected-content binding. They do not perform a second semantic geometry decode,
reopen live producer paths, launch a helper, or mint unchecked authority. Output quiescence and
existing B1 freeze/publication ordering remain mandatory. Assembly is a later file-only inventory
operation, not a geometry remerge or a mutable-output copy fallback.

## Evidence and remaining acceptance

Portable tests exercise contract refusals, complete ownership, selected-output key cutoff,
malformed/truncated/linked/aliased members, material/collision mapping, decoder-code identity and
receipt digest binding. The archived `Village_Edges.npz` fixture is the exact retained schema-2
payload from revision `0ebc872762a40fd0fc206b9364bcbde6af8577cb`, independently SHA-checked and
fully decoded here: 7860 triangles, 3574 polygons, 89 collision hulls and VillagePalette. Its
provenance file binds the bytes. The old executed helper closure is unavailable and its old plan
lacks today's explicit partition/collision-owner fields. This is decoder sample coverage, not
reproduction of the old planner, current-source equivalence or a native export run.

Native T1b acceptance is pending: real selected Village export, clean oracle geometry/channel/
material/collision comparison, deterministic alone/sequential/fresh-worker bytes, complete outputs
and fault controls. Existing C2b 21-job proof covers only its unchanged worker. MAC1 defers Darwin
CI; this change launches no native job and activates no production migration. LOD-bearing and
other encoding/format recipes require their own explicit adapter and acceptance, never a silent
fallback into this first single-MeshIR route.
