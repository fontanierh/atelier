# Shared haze source handoff

**Saved and accepted on the PR803 branch, not yet merged or packaged.** Commit `6c807a71f9` refreshes the three
records, pinned sources, packages and receipts under MASTERS2. All three were rebuilt in the accepted 14-master warm
batch and matched their originals with the rooted topology-v2 digest. Preparation began at PR803 head `8527a978f8`.

Sword Camp and Hidamari now use one `unreal/Scripts/material_masters/master_haze.py` implementation. It preserves the
donor `atmosphere.apply` branches, optional emission, named output pins, defaults and `glow` helper. The only API addition
is the explicit editor module first: `haze.apply(unreal, material, base, glow=None, base_out='', glow_out='', x=400, y=0)`.
The original `atmosphere.py` and `sea_look.py` files remain preserved through their existing source routes.

Each family declares `helpers = ['master_haze.py']`. Its entry builder remains the first pinned source; helpers follow
in dependency order. The existing material-master schema already supports multiple Python sources. The importer loads
only declared helpers into a fresh private namespace and removes it on success or failure. It changes no search path
and reads source bytes directly, so another warm job's modules or an old bytecode cache cannot supply a helper.

## Claimed refresh

| Record | Output | Entry source |
| --- | --- | --- |
| `master/swordcamp/camp` | `/Game/SwordCamp/Materials/M_SwordCamp` | `src/swordcamp_masters.py` |
| `master/swordcamp/ronin-body` | `/Game/SwordCamp/Materials/M_RoninBody` | `src/swordcamp_masters.py` |
| `master/hidamari/city` | `/Game/Japan/Hidamari/Materials/M_HDCity` | `src/hidamari_city_masters.py` |

Each refreshed record contains its updated `asset.toml`, replacement entry source and new `src/master_haze.py`,
matching `master_records.record_text` and `master_records.builder_sources`. The source refresh used the claimed journal
route; the normal importer performed the rebuild and issued the receipts. Ronin does not render haze, but shares
Sword Camp's pinned entry module and therefore also received a fresh import receipt.

Canonical source SHA-256:

| Source | SHA-256 |
| --- | --- |
| `swordcamp_masters.py` | `75b50e78a7fd332dbcb3f1f5ab0fe65d0651fff3403067ff983fbbeda34261e8` |
| `hidamari_city_masters.py` | `e074aa853dce3a38eee39ad2c9e239401abbbe6826b35f9ec2bc8b4bb87103ca` |
| `master_haze.py` | `329f98441c026c766803a3ce1d1d5e1aba5e09927ee91e12fc51152b8b77a49b` |

The previous entry pins are `a276af6753066718c187577590cda86c7069075cfe145e6b5ad117991989cc82` (both Sword Camp records)
and `9940b19f7fece3fdf2fdeef73ea7dac63fba5ff68e1c32a5ec0fed3df6b6c875` (Hidamari). Their saved originals supplied the
before baseline. The normal import performed scratch comparison, save and read-back before issuing each new receipt;
no fingerprint was changed merely to label the new sources imported. Other accepted masters retain their evidence.

Both cold and warm import preparation check every source pin before planning a write. The warm-path preflight
correction is included in PR803.

## Validation boundary

The three existing donor trace hashes are unchanged. Focused checks also compare the complete donor haze branches,
pin every declared helper, detect a helper change in the input fingerprint, refuse undeclared siblings, and isolate
same-named helpers and failure cleanup across jobs. Those Python checks are separate from the native evidence below.

The native accessor compiled successfully on `8098aefbd1`. The 14-original read and the post-import comparison both
accepted every master; material parameters and textures also matched. The batch imported 14 masters and two leaf
dependents with zero failures. The three refresh records and receipts are isolated in `6c807a71f9`; the eleven new
Japan masters remain in PR804. `test_every_committed_master_record_is_what_its_family_plans` passes after this refresh.
This evidence does not replace human appearance or second-machine acceptance.
