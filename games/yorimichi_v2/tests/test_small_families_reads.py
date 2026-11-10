"""The plan agrees with the committed reads (docs/inventory/small-families-reads/ and the two gate files): the loose
meshes' slots and LODs, the sub-object classes, the texture gates, and the instance parents and parameters each family
plan relies on. The evidence is the read output, compacted; the donor test is skipped without a donor checkout."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'migrate'))
import small_families as sf  # noqa: E402

READS = ROOT / 'docs/inventory/small-families-reads'


def evidence(name):
    return json.loads((READS / f'{name}.json').read_text())


def test_each_loose_mesh_has_the_one_slot_and_lod_the_plan_assumes():
    loose = evidence('hippodrome-meshes')['loose']
    for package, (slug, name) in sf.HIPPO_CLAIM.items():
        row = loose['Hippodrome/' + name]
        assert row['slots'] == [[f'HD_{name[len("SM_HD_"):]}', sf.hippo_slot(name)]], name
        assert len(row['lods']) == 1, name
        assert row['collision_trace'] == 'CTF_USE_COMPLEX_AS_SIMPLE', name


def test_the_slot_material_is_one_of_the_sub_object_instances():
    subs = evidence('hippodrome-meshes')['sub_objects']
    for _, (_, name) in sf.HIPPO_CLAIM.items():
        key = 'Hippodrome/' + sf.hippo_slot(name).split('/Game/Hippodrome/', 1)[1]
        assert subs[key] == 'MaterialInstanceConstant', name


def test_the_fourteen_sub_objects_are_textures_and_instances_and_no_meshes():
    subs = evidence('hippodrome-meshes')['sub_objects']
    assert len(subs) == 14
    classes = sorted(subs.values())
    assert classes.count('Texture2D') == 4 and classes.count('MaterialInstanceConstant') == 10
    assert 'StaticMesh' not in classes


def test_the_tree_house_and_plaza_gates_open_on_the_committed_reads():
    assert sf.read_status(sf.GAME, sf.TREE_READ, sf.TREE_CLAIM, sf.TREE_SETTINGS)[0]
    assert sf.read_status(sf.GAME, sf.PLAZA_READ, sf.PLAZA_TEXTURES, sf.PLAZA_SETTINGS)[0]


def test_the_masters_are_recorded_as_loaded_not_instances():
    for family in ('hippodrome', 'skatepark', 'swordcamp'):
        assert evidence(f'{family}-materials')['instances'] == {}, family
    assert evidence('hippodrome-materials')['not_instances'] == sorted(
        ['M_HD_Dirt', 'M_HD_Grass', 'M_HD_Rail', 'M_HD_Stone', 'M_HD_Structure'])


def test_the_megapark_instances_have_the_retail_parents_and_the_script_parameters():
    rows = evidence('megapark-materials')['instances']
    assert len(rows) == 24
    assert {r['parent'] for r in rows.values()} <= {'M_RetailOpaque', 'M_RetailMasked', 'M_RetailTranslucent'}
    script = {'MacroScale', 'DetailScale', 'MacroOpacity', 'UseDecal', 'HasLightmap', 'LightmapNorm', 'Moss'}
    for name, row in rows.items():
        assert script <= set(row['scalars']), name


def test_the_other_instance_families_name_their_parents_and_texture_parameters():
    tree = evidence('treehouse-materials')['instances']
    assert {r['parent'] for r in tree.values()} == {'M_TreeHouse', 'M_TH_Light'}
    assert tree['MI_TH_pane']['textures'] == [] and tree['MI_TH_pane']['parent'] == 'M_TH_Light'
    assert all(r['textures'] == ['Tex'] for name, r in tree.items() if name != 'MI_TH_pane')
    belmonte = evidence('belmonte-materials')['instances']
    assert len(belmonte) == 7 and {r['parent'] for r in belmonte.values()} == {'M_Belmonte'}
    assert all(r['textures'] == ['Tex'] for r in belmonte.values())
    fx = evidence('fx-materials')
    assert sorted(fx['instances']) == ['MI_FX_Dust', 'MI_FX_Glow', 'MI_FX_Ring', 'MI_FX_Spark']
    assert all(r['textures'] == ['Sprite'] for r in fx['instances'].values())
    assert sorted(fx['not_instances']) == ['M_FX_Additive', 'M_FX_Dust', 'M_FX_Trail']
    hid = evidence('hidamari-materials')['instances']
    assert list(hid) == ['MI_HD_flat'] and hid['MI_HD_flat']['parent'] == 'M_HDCity'


def test_the_bike_wheel_read_gives_one_palette_slot_and_one_lod():
    bike = evidence('bike-meshes')
    assert set(bike) == {'Japan/Assets/BK_WheelFront', 'Japan/Assets/BK_WheelRear'}
    for wheel in bike.values():
        assert wheel['slots'] == [['BikePalette', '/Game/Japan/Materials/M_Bike']]
        assert [t for _, t in wheel['lods']] == [26060]


def test_the_standalone_mega_park_map_references_resolve_to_their_records():
    """The native read of SuperUltraMegaPark: no unresolved /Game dependency, each one owned by the record the read names
    (the 29 collision meshes are the cell records' UC_MP_<hash>_0 packages), and every mesh component loads its mesh."""
    refs = json.loads((READS / 'megapark-map-refs.json').read_text())
    assert refs['map'] == '/Game/MegaPark/Maps/SuperUltraMegaPark' and refs['unresolved'] == []
    deps = refs['dependencies']
    assert len(deps) == 79 and all(d['holds'] and d['owner'] for d in deps.values())
    collision = {k: d for k, d in deps.items() if '/UC_MP_' in k}
    assert len(collision) == 29
    for package, dep in collision.items():
        name = package.rsplit('/', 1)[1]
        assert name.endswith('_0') and dep['holds'] == [f'StaticMesh:{name}']
        assert dep['owner'].startswith('adopted/megapark/cell-')
        record = sf.records.load_asset(ROOT / 'assets' / dep['owner'] / 'asset.toml')
        assert package in {o.package for o in record.outputs}
    assert refs['mesh_components'] == 79 and refs['components_without_mesh'] == 0
