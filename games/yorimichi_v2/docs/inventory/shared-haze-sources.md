# Shared haze source handoff

**Prepared code; three existing records still need their claimed source refresh and native acceptance.** The old pinned
sources, package bytes and receipts are unchanged. This preparation is based on PR803 head `8527a978f8`.

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

For each record, the source write is its `asset.toml`, replacement entry source and new `src/master_haze.py`. Use the
existing claimed journal route, with `master_records.record_text(family, master, master_records.builder_sha(family))`
and the bytes from `master_records.builder_sources(family)`. These families are already `done`; their ordinary migration
command deliberately does not rewrite completed records. Include the three outputs, their receipts and required
companions in the native import claim. Ronin does not render haze, but shares Sword Camp's pinned entry module and
therefore needs a fresh receipt too.

Canonical source SHA-256:

| Source | SHA-256 |
| --- | --- |
| `swordcamp_masters.py` | `75b50e78a7fd332dbcb3f1f5ab0fe65d0651fff3403067ff983fbbeda34261e8` |
| `hidamari_city_masters.py` | `e074aa853dce3a38eee39ad2c9e239401abbbe6826b35f9ec2bc8b4bb87103ca` |
| `master_haze.py` | `329f98441c026c766803a3ce1d1d5e1aba5e09927ee91e12fc51152b8b77a49b` |

The previous entry pins are `a276af6753066718c187577590cda86c7069075cfe145e6b5ad117991989cc82` (both Sword Camp records)
and `9940b19f7fece3fdf2fdeef73ea7dac63fba5ff68e1c32a5ec0fed3df6b6c875` (Hidamari). Keep their recorded acceptance as the
baseline. Do not change `verified.json` fingerprints to make new sources appear imported. The normal import must perform
scratch comparison, save and read-back, and issue its own receipts for these three in the next planned batch. Every
other accepted master and its evidence remains intact.

Both cold and warm import preparation must check every source pin before planning a write. The warm-path preflight
correction is a separate integration prerequisite; this patch leaves the existing import caller unchanged.

## Validation boundary

The three existing donor trace hashes are unchanged. Focused checks also compare the complete donor haze branches,
pin every declared helper, detect a helper change in the input fingerprint, refuse undeclared siblings, and isolate
same-named helpers and failure cleanup across jobs. These are Python checks, not a new native acceptance claim.

Until the claimed refresh, `test_every_committed_master_record_is_what_its_family_plans` correctly fails for these three
records: the templates now declare shared sources, while the accepted records still name the old bytes. Keep that check;
do not weaken it or broaden native imports to unrelated masters.
