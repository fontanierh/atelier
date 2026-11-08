"""Park dressing: a park's trees (one object per unit) and its kei cars (one object each). tools/migrate/parks.py assigns each
tree to a unit and writes the entries; objects.py loads and plans them; the editor step saves them with the runtime's own
builders (UV2MigrationParkDressing) and lists them in the manifest, so Spawn skips exactly those."""
import importlib.util
import json
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'content'))
import records  # noqa: E402


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


parks = load('v2_dressing_parks', 'tools/migrate/parks.py')
objects = load('v2_dressing_objects', 'tools/migrate/objects.py')

PINE_RECORD = 'adopted/japan/assets/tree-pine'
BUSH_RECORD = 'adopted/japan/assets/bush'
KEI_RECORD = 'prop/megapark/kei-pickup'
PARK = {
    'render': [{'name': 'SM_MP_A', 'origin_cm': [0, 0, 0]}, {'name': 'SM_MP_B', 'origin_cm': [1000, 0, 0]}],
    'collision': [{'name': 'UC_MP_C_0', 'origin_cm': [0, 500, 0]}],
    'trees': {
        'Tree_Pine_B': [[10, 0, 0, 0, 1], [990, 0, 0, 0, 1], [500, 0, 0, 0, 1], [20, 400, 0, 90, 1.1]],
        'Bush_Ochre_A': [[1000, 10, 0, 0, 1], [30, 30, 0, 0, 1]],
        'HD_NorthRockA': [[5, 5, 0, 0, 1]],
    },
    'props': [{'mesh': 'SM_Kei_Pickup', 'location_cm': [0, 0, 0], 'forward': [1, 0, 0], 'up': [0, 0, 1]}],
}
OWNERS = {'SM_MP_A': 'cell-x150-zm750', 'SM_MP_B': 'seam', 'UC_MP_C_0': 'cell-x150-zm750'}
RECORDS = {'Tree_Pine_B': [PINE_RECORD], 'Bush_Ochre_A': [BUSH_RECORD], 'SM_Kei_Pickup': [KEI_RECORD]}
LFS = 'version https://git-lfs.github.com/spec/v1\noid sha256:' + '0' * 64 + '\nsize 1234\n'


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def game(tmp_path, monkeypatch):
    """A kit with the Mega Park units, the Japan tree, bush and kei records, and the regions the plan reads."""
    game = tmp_path / 'game'
    units = {'units': {'cell-x150-zm750': {}, 'seam': {}}, 'packages': {
        '/Game/MegaPark/Meshes/SM_MP_A': 'cell-x150-zm750', '/Game/MegaPark/Meshes/UC_MP_C_0': 'cell-x150-zm750',
        '/Game/MegaPark/Meshes/SM_MP_B': 'seam'}}
    write(game / 'assets/adopted/megapark/units.json', json.dumps(units))
    for unit in ('cell-x150-zm750', 'seam'):
        write(game / f'assets/adopted/megapark/{unit}/asset.toml', f'id = "adopted/megapark/{unit}"\n')
    write(game / 'assets/adopted/japan/assets/tree-pine/asset.toml',
          f'id = "{PINE_RECORD}"\n\n[[outputs]]\npackage = "/Game/Japan/Assets/Tree_Pine_B"\n\n'
          '[[outputs]]\npackage = "/Game/Japan/FoliageLODs/Tree_Pine_B/Tree_Pine_B_LOD1"\n')
    write(game / 'assets/adopted/japan/assets/bush/asset.toml',
          f'id = "{BUSH_RECORD}"\n\n[[outputs]]\npackage = "/Game/Japan/Assets/Bush_Ochre_A"\n')
    write(game / 'assets/prop/megapark/kei-pickup/asset.toml',
          f'id = "{KEI_RECORD}"\nkind = "static-mesh"\n\n[[outputs]]\npackage = "/Game/Japan/Assets/SM_Kei_Pickup"\n')
    write(game / 'unreal/Content/Data/megapark/park.json', json.dumps(PARK))
    for rid, bounds, tag in (('w00-island', [-1000, -1000, 1000, 1000], None),
                             ('w11-megapark', [-1000, -1000, 0, 0], 'megapark')):
        folder = game / 'world/regions' / rid
        write(folder / 'region.toml', f'schema = 1\nid = "region/{rid}"\nabout = "{rid}"\nbounds_cm = {bounds}\n'
                                      'maps = ["/Game/V2/Maps/Slice"]\n')
        records.write_json(folder / 'actors.verified.json', {'schema': 1, 'kind': 'editor-saved', 'asset': f'region/{rid}',
                                                             'engine': 'test', 'files': {}})
        if tag:
            write(folder / 'objects.toml', f'schema = 1\ntag = "{tag}"\ndata = "megapark/park.json"\n')
    monkeypatch.setattr(objects.save_validate, 'engine_identity', lambda: 'test')
    monkeypatch.setattr(objects.save_validate, 'actor_info', lambda path: (None, None))
    # The kit's asset records are read as text by the planner; migrate() only needs the regions from discovery.
    monkeypatch.setattr(objects.records, 'discover', lambda root: (
        [], [records.load_region(p) for p in sorted((root / 'world' / 'regions').glob('*/region.toml'))]))
    monkeypatch.setenv('ATELIER_AGENT', objects.authority.BOOTSTRAP_WRITER)
    monkeypatch.delenv('ATELIER_CLAIMS_TASK', raising=False)
    return game


def region_of(game):
    return SimpleNamespace(id='region/w11-megapark', folder=game / 'world/regions/w11-megapark')


def set_objects(game, body):
    write(game / 'world/regions/w11-megapark/objects.toml',
          'schema = 1\ntag = "megapark"\ndata = "megapark/park.json"\n\n' + body)


TREE_OBJECTS = ('[[objects]]\nid = "object/megapark/trees-seam"\ntrees = "seam"\n'
                f'model = ["{BUSH_RECORD}", "{PINE_RECORD}"]\nabout = "the trees and bushes of the seam"\n\n'
                '[[objects]]\nid = "object/megapark/kei-pickup"\nprops = ["SM_Kei_Pickup"]\n'
                f'model = "{KEI_RECORD}"\nabout = "the Mega Park car park prop SM_Kei_Pickup"\n')


# --- the converter (tools/migrate/parks.py) ------------------------------------------------------------------------

def test_a_tree_goes_to_the_unit_of_its_nearest_piece(game):
    trees, unmodelled = parks.tree_units(PARK, OWNERS, RECORDS)
    by = {(t['species'], t['index']): t['unit'] for t in trees}
    assert by[('Tree_Pine_B', 0)] == 'cell-x150-zm750'     # nearest: SM_MP_A at the origin
    assert by[('Tree_Pine_B', 1)] == 'seam'                # nearest: SM_MP_B at x = 1000
    assert by[('Tree_Pine_B', 3)] == 'cell-x150-zm750'     # nearest: UC_MP_C_0 at y = 500 (x = 20, y = 400)
    assert unmodelled == ['HD_NorthRockA']


def test_a_tree_equidistant_from_two_pieces_goes_to_the_earlier_piece(game):
    trees, _ = parks.tree_units(PARK, OWNERS, RECORDS)
    tie = [t for t in trees if t['species'] == 'Tree_Pine_B' and t['index'] == 2]   # x = 500: SM_MP_A and SM_MP_B tie
    assert tie == [{'species': 'Tree_Pine_B', 'index': 2, 'unit': 'cell-x150-zm750'}]


def test_every_modelled_tree_is_assigned_exactly_once(game):
    trees, unmodelled = parks.tree_units(PARK, OWNERS, RECORDS)
    modelled = sum(len(v) for k, v in PARK['trees'].items() if k not in unmodelled)
    assert len(trees) == modelled
    assert len({(t['species'], t['index']) for t in trees}) == len(trees)


def test_a_piece_no_unit_owns_is_refused_for_the_trees(game):
    with pytest.raises(parks.ConvertError, match='SM_MP_B is owned by no unit'):
        parks.tree_units(PARK, {k: v for k, v in OWNERS.items() if k != 'SM_MP_B'}, RECORDS)


def test_two_records_outputting_one_tree_mesh_are_refused(game):
    records_twice = {**RECORDS, 'Tree_Pine_B': [PINE_RECORD, 'adopted/other/pine']}
    with pytest.raises(parks.ConvertError, match='two records'):
        parks.tree_units(PARK, OWNERS, records_twice)


def test_tree_entries_are_one_object_per_unit_with_their_records(game):
    entries = parks.tree_entries('megapark', PARK, OWNERS, RECORDS)
    assert [e['id'] for e in entries] == ['object/megapark/trees-cell-x150-zm750', 'object/megapark/trees-seam']
    seam = next(e for e in entries if e['id'].endswith('trees-seam'))
    # The seam holds the pine at x = 990 and the bush at x = 1000: its model is both records, sorted.
    assert seam['trees'] == 'seam'
    assert seam['model'] == [BUSH_RECORD, PINE_RECORD]


def test_a_prop_is_one_object_named_by_its_record(game):
    entries = parks.prop_entries('megapark', PARK, RECORDS)
    assert entries == [{'id': 'object/megapark/kei-pickup', 'props': ['SM_Kei_Pickup'], 'model': KEI_RECORD,
                        'about': 'the Mega Park car park prop SM_Kei_Pickup'}]


def test_a_prop_with_no_record_is_refused(game):
    with pytest.raises(parks.ConvertError, match='no record outputs'):
        parks.prop_entries('megapark', PARK, {})


def test_the_entries_write_as_toml_that_reads_back(game):
    entries = parks.tree_entries('megapark', PARK, OWNERS, RECORDS) + parks.prop_entries('megapark', PARK, RECORDS)
    text = ''.join(parks.toml_entry(e) for e in entries)
    back = tomllib.loads(text)['objects']
    assert [o['id'] for o in back] == ['object/megapark/trees-cell-x150-zm750', 'object/megapark/trees-seam',
                                       'object/megapark/kei-pickup']
    assert back[1]['trees'] == 'seam' and back[1]['model'] == [BUSH_RECORD, PINE_RECORD]
    assert back[2]['props'] == ['SM_Kei_Pickup'] and back[2]['model'] == KEI_RECORD


def test_a_rewrite_replaces_the_generated_dressing_and_keeps_the_rest(game):
    kept = ('[[objects]]\nid = "object/megapark/zeppelin"\ngroup = "SM_Z"\nmodel = "adopted/megapark/zeppelin"\n'
            'about = "the zeppelin station"\n')
    entries = parks.tree_entries('megapark', PARK, OWNERS, RECORDS) + parks.prop_entries('megapark', PARK, RECORDS)
    first = parks.merge('schema = 1\ntag = "megapark"\ndata = ""\n\n' + kept, 'megapark/park.json', entries)
    assert kept in first and first.count('[[objects]]') == 4
    assert parks.merge(first, 'megapark/park.json', entries) == first   # a rerun writes the same text
    fewer = parks.merge(first, 'megapark/park.json', entries[:1])
    assert fewer.count('trees = ') == 1 and 'props = ' not in fewer and kept in fewer


def test_the_real_data_assigns_every_tree_but_the_five_rocks():
    real = ROOT / 'unreal/Content/Data/megapark/park.json'
    crater = ROOT / 'unreal/Content/Data/craterpark/park.json'
    if not real.is_file() or records.is_lfs_pointer(real) or records.is_lfs_pointer(crater):
        pytest.skip('the park files are Git LFS pointers in this checkout')
    mega = json.loads(real.read_text())
    crate = json.loads(crater.read_text())
    units = json.loads((ROOT / 'assets/adopted/megapark/units.json').read_text())
    found = parks.japan_records(ROOT)
    trees, unmodelled = parks.tree_units(mega, parks.mega_owners(units), found)
    assert unmodelled == ['HD_NorthRockA', 'HD_NorthRockB']
    assert len(trees) == 6937 - 5
    assert {t['unit'] for t in trees} <= set(parks.mega_owners(units).values())
    crater_trees, crater_unmodelled = parks.tree_units(crate, parks.crater_owners(ROOT / 'assets/adopted/craterpark'), found)
    assert crater_unmodelled == [] and len(crater_trees) == 631
    props = parks.prop_entries('megapark', mega, found)
    assert sorted(p['model'] for p in props) == [f'prop/megapark/kei-{k}' for k in ('microvan', 'pickup', 'retro', 'wagon')]


def test_the_committed_objects_hold_the_dressing():
    """The committed objects.toml files list the trees and the kei cars the converter writes."""
    mega = tomllib.loads((ROOT / 'world/regions/w11-megapark/objects.toml').read_text())['objects']
    trees = [o for o in mega if 'trees' in o]
    props = [o for o in mega if 'props' in o]
    assert len(trees) == 16 and sorted(o['id'] for o in props) == [f'object/megapark/kei-{k}' for k in
                                                                    ('microvan', 'pickup', 'retro', 'wagon')]
    crater = tomllib.loads((ROOT / 'world/regions/w12-craterpark/objects.toml').read_text())['objects']
    assert len([o for o in crater if 'trees' in o]) == 20
    for entry in trees + props:
        models = [entry['model']] if isinstance(entry['model'], str) else entry['model']
        for model in models:
            assert (ROOT / 'assets' / model / 'asset.toml').is_file(), model


# --- loading and planning (tools/migrate/objects.py) -----------------------------------------------------------------

def test_tree_and_prop_entries_load(game):
    set_objects(game, TREE_OBJECTS)
    loaded = objects.load_objects(region_of(game))
    by_id = {o['id']: o for o in loaded['objects']}
    assert by_id['object/megapark/trees-seam']['trees'] == 'seam'
    assert by_id['object/megapark/kei-pickup']['props'] == ['SM_Kei_Pickup']


@pytest.mark.parametrize('body, message', [
    ('trees = ""', 'trees needs the unit'),
    ('trees = 3', 'trees needs the unit'),
    ('props = "SM_Kei_Pickup"', 'props needs a list'),
    ('props = []', 'props needs a list'),
])
def test_malformed_tree_and_prop_entries_are_refused(game, body, message):
    set_objects(game, '[[objects]]\nid = "object/megapark/x"\n' + body + '\nmodel = "prop/megapark/kei-pickup"\nabout = "x"\n')
    with pytest.raises(objects.ObjectError, match=message):
        objects.load_objects(region_of(game))


def test_a_tree_unit_or_prop_listed_twice_is_refused(game):
    set_objects(game, '[[objects]]\nid = "object/megapark/trees-seam"\ntrees = "seam"\nmodel = "adopted/japan/assets/tree-pine"\n'
                      'about = "a"\n\n[[objects]]\nid = "object/megapark/more-seam"\ntrees = "seam"\n'
                      'model = "adopted/japan/assets/tree-pine"\nabout = "b"\n')
    with pytest.raises(objects.ObjectError, match='listed twice'):
        objects.load_objects(region_of(game))


def test_the_tree_plan_carries_each_tree_of_the_named_units(game):
    set_objects(game, TREE_OBJECTS)
    items = [o for o in objects.load_objects(region_of(game))['objects'] if 'trees' in o]
    plan = objects.tree_plan('region/w11-megapark', 'megapark', 'megapark/park.json', items, game)
    # The plan names the units; the editor step assigns their trees with the runtime rule (the seam holds two trees here).
    assert plan['units'] == ['seam']
    seam = [t for t in parks.tree_units(PARK, OWNERS, RECORDS)[0] if t['unit'] == 'seam']
    assert sorted((t['species'], t['index']) for t in seam) == [('Bush_Ochre_A', 0), ('Tree_Pine_B', 1)]


def test_a_unit_with_no_tree_is_refused_before_the_editor(game):
    set_objects(game, '[[objects]]\nid = "object/megapark/trees-nowhere"\ntrees = "nowhere"\n'
                      f'model = "{PINE_RECORD}"\nabout = "none"\n')
    items = objects.load_objects(region_of(game))['objects']
    with pytest.raises(objects.ObjectError, match="hold no tree"):
        objects.tree_plan('region/w11-megapark', 'megapark', 'megapark/park.json', items, game)


def test_a_prop_the_file_does_not_hold_is_refused(game):
    set_objects(game, '[[objects]]\nid = "object/megapark/kei-x"\nprops = ["SM_Kei_Nope"]\n'
                      f'model = "{KEI_RECORD}"\nabout = "x"\n')
    items = objects.load_objects(region_of(game))['objects']
    with pytest.raises(objects.ObjectError, match='SM_Kei_Nope is no prop'):
        objects.prop_plan('region/w11-megapark', 'megapark', 'megapark/park.json', items, game)


def test_the_saved_keys_match_what_the_runtime_lists(game):
    tree = {'id': 'object/megapark/trees-seam', 'trees': 'seam'}
    prop = {'id': 'object/megapark/kei-pickup', 'props': ['SM_Kei_Pickup']}
    piece = {'id': 'object/megapark/seam', 'park': ['SM_MP_B']}
    assert objects.saved_key('megapark', tree) == 'megapark:trees/seam'
    assert objects.saved_key('megapark', prop) == 'megapark:props/kei-pickup'
    assert objects.saved_key('megapark', piece) == 'megapark:seam'


def test_the_migration_plan_carries_trees_and_props_and_needs_the_environment(game):
    set_objects(game, TREE_OBJECTS)
    seen = []

    def editor(plan_file):
        seen.append(json.loads(plan_file.read_text()))
        return 'no completion line'

    with pytest.raises(objects.ObjectError, match='did not report completion'):
        objects.migrate(game, ['region/w11-megapark'], 'region/w00-island', None, editor=editor,
                        out=game / 'out', echo=lambda *_: None)
    plan = seen[0]
    assert plan['trees'][0]['region'] == 'region/w11-megapark' and plan['trees'][0]['tag'] == 'megapark'
    assert plan['trees'][0]['units'] == ['seam']
    assert plan['props'] == [{'region': 'region/w11-megapark', 'tag': 'megapark', 'data': 'megapark/park.json',
                              'meshes': ['SM_Kei_Pickup'], 'units': ['kei-pickup']}]
    with pytest.raises(objects.ObjectError, match='--environment is needed'):
        objects.migrate(game, ['region/w11-megapark'], None, None, editor=editor, out=game / 'out',
                        echo=lambda *_: None)


# --- the editor side is named the same in Python and in the C++ --------------------------------------------------------

def test_the_python_calls_the_functions_the_cpp_defines():
    cpp = (ROOT / 'unreal/Source/Yorimichi/World/V2MigrationParkDressing.cpp').read_text()
    header = (ROOT / 'unreal/Source/Yorimichi/World/V2MigrationParkDressing.h').read_text()
    script = (ROOT / 'unreal/Scripts/migrate_objects.py').read_text()
    for name in ('MigrateParkTrees', 'MigrateParkProps'):
        assert name in cpp and name in header
    # Python calls the UFUNCTIONs by their snake_case names: MigrateParkTrees is migrate_park_trees.
    assert 'V2MigrationParkDressing.migrate_park_trees' in script and 'V2MigrationParkDressing.migrate_park_props' in script


def test_the_committed_tree_units_match_the_converter():
    """tree_units.json beside each park.json is what ASuperUltraMegaPark::TreeUnit reads: it must be the converter's text."""
    real = {tag: ROOT / 'unreal/Content/Data' / tag / 'park.json' for tag in ('megapark', 'craterpark')}
    if any(not p.is_file() or records.is_lfs_pointer(p) for p in real.values()):
        pytest.skip('the park files are Git LFS pointers in this checkout')
    expected = parks.sidecars(ROOT, json.loads(real['megapark'].read_text()), json.loads(real['craterpark'].read_text()))
    for path, text in expected.items():
        assert path.read_text() == text, f'{path} is out of date: run tools/migrate/parks.py'
