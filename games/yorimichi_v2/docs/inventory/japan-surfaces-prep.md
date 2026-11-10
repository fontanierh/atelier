# Japan surface masters: prepared source handoff

**Historical preparation.** These masters were subsequently imported, merged in #804 and included in package
`c89f535441be`. The instructions and pending claims below describe the preparation checkpoint, not work still
to start. See [INVENTORY](../INVENTORY.md) for current status and the limits of the accepted evidence.

Prepared from donor `7eec0f98dd`, on the PR #803 baseline `085749fd1d`. This is generator preparation only: no asset record,
package or receipt has changed, and native acceptance remains open. The family is `japan_surfaces`.

Its removal set is exactly `M_Painted`, `M_Foliage`, `M_Grass`, and `M_Village` under `/Game/Japan/Materials`. Before applying,
the native controller must reconcile the family's baseline `keeps` with the adopted record's current outputs after the
sea and sky families. Keep the remaining packages and their source tree; do not apply a stale kept set.

The builder uses the separately pinned `master_haze.py` helper for the donor atmosphere/sea constants and graph.
The family declares that helper, and the importer loads only its pinned record sources in a private module namespace.
Foliage and fresh camera-fade graphs remain in the surface builder. No donor module is imported at runtime; no builder
writes another package or saves its own. Village is not camera-fade patched in the donor. Painted stays opaque; its selected
instances already enable masking. Foliage and grass retain their own cutoffs, and shadow passes retain the silhouette.

## Pinned donor sources

All paths below are relative to the donor's `games/yorimichi/`. Existing V2 original copies are retained by
`adopted/japan/materials/base-materials`, except `import_village.py`, also pinned by the Hidamari generator record.

| Source | SHA-256 |
| --- | --- |
| `unreal/Scripts/shared_materials.py` | `8cf144f9752bffe771bbddfe984091ad4c288259bc00abba4a64fad5d6678720` |
| `unreal/Scripts/atmosphere.py` | `b59478df43df83b8c7386e7ff7c097f32faf647716fdacb804f3cf0c99336ebf` |
| `unreal/Scripts/sea_look.py` | `ffae53cded2bb461534c88c100bc75d3f93ec3bf396eb303e5d4ec3ad4dbb4fa` |
| `unreal/Scripts/foliage_material.py` | `70fbd4b6ad988d7192b78b227711c6ccb30fe40928301d98a4c18288b338249a` |
| `unreal/Scripts/see_through.py` | `9d7da40163a6e4023d91e8fc2aaacdd2578bf07ef02f05b4e10dcc1c4c8fd105` |
| `unreal/Scripts/import_village.py` | `fccc0aae775eb8ae84d7010344f37900e6e654168a50502f5fb89d38048ea17c` |
| `unreal/Scripts/material_assets.py` | `4f48db1203b44c5abca932291ce323f7247a655753167a5f72dfefe5ac4be50f` |
| `world/gen_textures.py` | `5b8b93fe242873529e1a781a994fd3be9309a6aa3af56fb3b7d07b971e27aaf6` |

The atmosphere uses `HAZE_CM=900000`, `START_CM=3000`, `HORIZON=(.126,.311,.720)`, `FAR=.74`, and rounded
`FAR_COLOUR=(.0932,.2301,.5328)`. The helper HLSL and complete node-call traces match the donor, including the final
`see_through.world_materials()` overlay on the three shared parents.

## Explicit inputs and remaining acceptance

- `texture/japan/white` owns `/Game/Japan/Textures/T_white`. Its original PNG is pinned as
  `b68de61392c506377e0d673fa36e239a47b67e603bdcb9cbf61d4ddbcd9722ff`. The retained `gen_textures.white`
  generator is an 8×8 RGB image of `(255,255,255)`; `texture_catalog.py` selects its defaults.
- `adopted/japan/materials/base-materials` still owns `/Game/Japan/Materials/MPC_Wind`. Its `make_mpc` generator is
  retained in the pinned `shared_materials.py`; conversion of the collection itself is not part of this family.
- `adopted/seethrough` owns `/Game/SeeThrough/MPC_SeeThrough`. The pinned `see_through.py` records its vector definitions;
  the builder receives this existing collection and never creates or modifies it. Its conversion remains separate.
- Grass receives the installed engine material function `/Engine/Functions/Engine_MaterialFunctions02/Utility/DitherTemporalAA`
  through declared reads, as supported by the importer. Its default texture is white, as in the donor; grass instances
  carry their painted grass textures.

Integration must include the declared-helper planner and loader before applying this family. The helper source is copied
and pinned beside the builder in each generated record; changing it makes those records stale.

Before accepting native imports, the shared digest needs material settings `dithered_lod_transition` and
`tangent_space_normal`, plus expression properties `collection`, `g`, `b`, `a`, `material_function`,
`use_custom_primitive_data` and `primitive_data_index`. The graph also writes `desc` tags used by the donor helpers;
the existing builder-coverage test sees those tags. These shared-file changes belong to integration, not this preparation.

Run the existing claimed four-master batch and compare fresh saved-original and after digests, including those fields.
No material identity, source closure or native success is claimed from the Python traces alone. The focused tests exercise
all four donor traces, complete declared reads, early refusal for missing reads, grass normals/fading and camera fading.
