"""The seven adopted Japan material records: their package count, and the class each package is filed under in
docs/inventory/exceptions.md ("Japan materials"). They must stay source-less until a verified import or an editor read
closes them (adding sources would make their imports stale). Counts are checked from committed files only: the
records, their verified.json hashes and the exceptions table. The donor scripts and the saved packages live outside
this repository, so their evidence is recorded in the doc, not re-read here."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'content'))
import records  # noqa: E402

FAMILY = ROOT / 'assets' / 'adopted' / 'japan' / 'materials'
RECORDS = ['bark', 'buildings', 'foliage', 'ground', 'rock-concrete', 'sky-wind', 'water']
EXCEPTIONS = ROOT / 'docs' / 'inventory' / 'exceptions.md'

# Group (where the candidate generator is) for each of the 43 packages.
SHARED = [  # build_materials in unreal/Scripts/shared_materials.py
    'MI_Bark',  'MI_BarkOlive',  'MI_BarkTuscan',  'MI_Lattice',  'MI_Metal',  'MI_Paint',  'MI_Plaster',
    'MI_RoofTile',  'MI_Tile',  'MI_Vermilion',  'MI_Wood',  'MI_Feather',  'MI_FeatherDark',  'MI_Flower',
    'MI_Grass',  'MI_LeafBroad',  'MI_LeafCedar',  'MI_LeafGinkgo',  'MI_LeafMaple',  'MI_LeafOchre',
    'MI_LeafOchreSmall',  'MI_LeafPine',  'MI_LeafSmall',  'MI_Ground',  'MI_Litter',  'MI_Moss',  'MI_Road',
    'MI_Concrete',  'MI_Rock',  'MI_Stone',  'MI_Sky',  'MI_Water',
]
OTHER = [  # forest_ground.py, import_island_world.py, mountain_material.py, import_southwest.py
    'MI_FarForest',  'MI_Sand',  'MI_Coast',  'MI_CoastRock',  'MI_NorthRockCaps',
]
TUSCAN = [  # import_forest.py, textures from tools/forest_textures.py
    'MI_LeafCypress',  'MI_LeafOak',  'MI_LeafOlive',  'MI_LeafStonePine',
]
BLOCKED = [  # used leaves: a recipe recorded from the editor read (no donor builder)
    'MI_LeafAmber',  'MI_LeafCrimson',
]
ALL = SHARED + OTHER + TUSCAN + BLOCKED


INSTANCES = ROOT / 'assets' / 'material' / 'japan' / 'materials'   # tools/migrate/held_instances.py writes here


def written():
    """True once the JAPANMI write has moved the 41 instances out of the adopted records."""
    return not (FAMILY / RECORDS[0] / 'asset.toml').is_file()


def loaded():
    if written():
        return {name: records.load_asset(INSTANCES / f'{name}-instances' / 'asset.toml') for name in RECORDS}
    return {name: records.load_asset(FAMILY / name / 'asset.toml') for name in RECORDS}


def leaves():
    return {name: records.load_asset(ROOT / 'assets' / 'material' / 'japan' / name / 'asset.toml')
            for name in ('leaf-amber', 'leaf-crimson')}


def test_the_seven_records_hold_41_packages_and_no_source_or_recipe():
    """Before the JAPANMI write: seven source-less adopted records. After it: seven generated material-instance records,
    one per adopted record, each with a recipe row per output and no source of its own, and no adopted record left."""
    assets = loaded()
    assert len(assets) == 7
    assert sum(len(a.outputs) for a in assets.values()) == 41
    if not written():
        assert all(not a.sources and a.recipe is None for a in assets.values())
        return
    for asset in assets.values():
        assert asset.kind == 'material-instance' and asset.authority == 'generated' and not asset.sources
        rows = asset.recipe.settings['instances']
        assert sorted(r['package'] for r in rows) == sorted(o.package for o in asset.outputs)
    assert not any((FAMILY / name).exists() for name in RECORDS)


def test_the_two_used_leaves_are_one_material_instance_record_each_with_a_recipe_and_no_source():
    for asset in leaves().values():
        assert asset.kind == 'material-instance' and asset.authority == 'generated'
        assert len(asset.outputs) == 1 and asset.recipe is not None and not asset.sources


def test_the_packages_are_the_43_material_instances_and_each_has_a_verified_hash():
    packages = [o.package.rsplit('/', 1)[1] for a in [*loaded().values(), *leaves().values()] for o in a.outputs]
    assert len(packages) == len(set(packages)) == 43
    assert sorted(packages) == sorted(ALL)
    assert all(p.startswith('MI_') for p in packages)
    for name in RECORDS:
        verified = (FAMILY / name / 'verified.json').read_text()
        for package in re.findall(r'"unreal/Content/Japan/Materials/(MI_[A-Za-z0-9]+)\.uasset"', verified):
            assert package in ALL
        hashes = re.findall(r'"([0-9a-f]{64})"', verified)
        assert len(hashes) == len(re.findall(r'\.uasset"', verified))


def test_the_classification_is_41_generator_rows_and_2_used_leaves_with_no_imported_original():
    assert len(ALL) == 43 and len(set(ALL)) == 43
    assert (len(SHARED), len(OTHER), len(TUSCAN), len(BLOCKED)) == (32, 5, 4, 2)
    assert BLOCKED == ['MI_LeafAmber', 'MI_LeafCrimson']
    assert len(SHARED) + len(OTHER) + len(TUSCAN) == 41   # class (b); class (a) is empty


def test_the_exceptions_table_lists_each_package_once_with_the_same_status():
    rows = re.findall(r'^\| `(MI_[A-Za-z0-9]+)` \| `[^`]+` \| (Prepared, read-confirmed|Prepared, recipe recorded) \|',
                      EXCEPTIONS.read_text(), re.M)
    assert sorted(name for name, _ in rows) == sorted(ALL)
    status = dict(rows)
    assert {name for name, s in status.items() if s == 'Prepared, recipe recorded'} == set(BLOCKED)
    assert sum(1 for s in status.values() if s == 'Prepared, read-confirmed') == 41
