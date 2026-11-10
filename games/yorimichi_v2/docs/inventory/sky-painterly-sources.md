# Sky and painterly source preparation

**Prepared only**, from the PR803 checkpoint `085749fd1d`: two family entries and their self-contained builder.
No asset records, receipts, original sources or saved packages changed in this preparation. Native acceptance and
the claimed record move remain with the integration owner.

| Package | Planned record | Builder and input |
| --- | --- | --- |
| `/Game/Japan/Materials/M_Sky` | `master/japan/base/sky` | `sky_material`; reads `/Game/Japan/Textures/T_sky`, owned by `texture/japan/sky` |
| `/Game/Japan/Materials/M_Painterly` | `master/japan/base/painterly` | `painterly_material`; no package reads, its kernel is included in the pinned builder |

Family: `tools/migrate/master_families/japan_sky_painterly.py`.
Builder: `unreal/Scripts/material_masters/sky_painterly_masters.py`.
The adopted owner remains `adopted/japan/materials/base-materials`. The preparation's `keeps` is the fourteen-package
PR803 remainder minus exactly `M_Sky` and `M_Painterly`. At integration, reconcile it with any preceding family moves
and update the preceding families' keeps as usual. Do not restore already moved packages or drop other retained ones.

## Recoverable originals

The donor baseline is `7eec0f98dd` (DECISIONS D01). The copies remain under
`assets/adopted/japan/materials/base-materials/source/unreal/Scripts/`.

| Original | SHA-256 | Used portion |
| --- | --- | --- |
| `shared_materials.py` | `8cf144f9752bffe771bbddfe984091ad4c288259bc00abba4a64fad5d6678720` | `master` 169–221 specialized to the fixed unlit sky; `painterly_material` 103–166 |
| `painterly_kernel.py` | `70f9be7d03f23727829837b2334f3a84691de5bda4189a164c09868feac48077` | `kernel` 9–25 and `shader` 28–57, copied into the builder |
| `material_assets.py` | `4f48db1203b44c5abca932291ce323f7247a655753167a5f72dfefe5ac4be50f` | Node/link helpers 34–42; saves remain the V2 importer's responsibility |

Sky's original `T_sky.png` is pinned by its texture record as
`accae01fb894cd8607c6305d3a4cd252ca737a3043651e5ad8f7b6411a298b38`.
The complete painterly HLSL, seven runtime parameter defaults, four scene texture IDs, named inputs and wiring remain
the donor's. Neither builder imports V1 code or fetches anything from a donor checkout.

## Native integration remaining

Before reading originals or importing these masters, the common digest needs material settings `is_sky` and
`blendable_location`, and expression property `scene_texture_id`. The PR803 digest does not yet record them; accepting
without them would conceal a changed fog treatment, post-process stage or scene/depth input. The integration owner
is preparing that shared change separately.

Use the existing complete claim, planner and importer route after the preceding base-material families reach a stopped
boundary. Preserve saved-original digests, rebuild in scratch, compare the declared properties, graph and parameters,
then import and read back the same two packages. The generated code and recording-based graph tests are preparation
evidence; they do not establish native compilation or visible appearance. Keep the existing package until a later
verified checkpoint includes these imports.
