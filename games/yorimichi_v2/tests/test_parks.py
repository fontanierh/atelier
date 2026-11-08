"""Park objects: a park's render and collision pieces saved as one object per adopted unit (tools/migrate/parks.py writes
the entries; objects.py loads and plans them; the editor step saves them)."""
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


parks = load('v2_migrate_parks', 'tools/migrate/parks.py')
objects = load('v2_migrate_objects_parks', 'tools/migrate/objects.py')
LFS = 'version https://git-lfs.github.com/spec/v1\noid sha256:' + '0' * 64 + '\nsize 1234\n'

MEGA = {'render': [{'name': 'SM_MP_A', 'origin_cm': [0, 0, 0]}, {'name': 'SM_MP_B', 'origin_cm': [1, 0, 0]}],
        'collision': [{'name': 'UC_MP_C_0', 'origin_cm': [0, 0, 0]}]}
CRATER = {'render': [{'name': 'SM_CP_p8_1', 'origin_cm': [0, 0, 0]}, {'name': 'SM_CP_floor_1', 'origin_cm': [0, 0, 0]}],
          'collision': [{'name': 'UC_CP_mixed_0', 'origin_cm': [0, 0, 0]}]}
OWNERSHIP = {'render': {'SM_CP_p8_1': 'p8', 'SM_CP_floor_1': 'crater_floor'},
             'collision': {'UC_CP_mixed_0': {'owner': 'mixed'}}}
MEGA_PARK_OBJECTS = ('[[objects]]\nid = "object/megapark/cell-x150-zm750"\npark = ["SM_MP_A", "UC_MP_C_0"]\n'
                     'model = "adopted/megapark/cell-x150-zm750"\nabout = "a test cell"\n\n'
                     '[[objects]]\nid = "object/megapark/seam"\npark = ["SM_MP_B"]\n'
                     'model = "adopted/megapark/seam"\nabout = "the test seam"\n')


HEADER = '# test region\nschema = 1\ntag = "{tag}"\ndata = ""\n'


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def add_region(game, name, bounds, tag=None):
    """A region record with its (empty) verification, as records.discover reads them."""
    folder = game / 'world/regions' / name
    write(folder / 'region.toml', f'schema = 1\nid = "region/{name}"\nabout = "{name}"\nbounds_cm = {bounds}\n'
                                  'maps = ["/Game/V2/Maps/Slice"]\n')
    records.write_json(folder / 'actors.verified.json', {'schema': 1, 'kind': 'editor-saved', 'asset': f'region/{name}',
                                                         'engine': 'test', 'files': {}})
    if tag:
        write(folder / 'objects.toml', f'# test region\nschema = 1\ntag = "{tag}"\ndata = ""\n')
    return folder


@pytest.fixture
def kit(tmp_path):
    """What the converter reads: the unit records, the Crater Park ownership file and both objects.toml files."""
    game = tmp_path / 'kit'
    units = {'units': {'cell-x150-zm750': {}, 'seam': {}}, 'packages': {
        '/Game/MegaPark/Meshes/SM_MP_A': 'cell-x150-zm750', '/Game/MegaPark/Meshes/UC_MP_C_0': 'cell-x150-zm750',
        '/Game/MegaPark/Meshes/SM_MP_B': 'seam', '/Game/MegaPark/Materials/MI_x': 'seam'}}
    write(game / 'assets/adopted/megapark/units.json', json.dumps(units))
    for unit in ('cell-x150-zm750', 'seam'):
        write(game / f'assets/adopted/megapark/{unit}/asset.toml', f'id = "adopted/megapark/{unit}"\n')
    crater = {'p8-roll-in-rollin': '/Game/CraterPark/Meshes/SM_CP_p8_1',
              'crater-floor-3-2': '/Game/CraterPark/Meshes/SM_CP_floor_1',
              'collision-mixed': '/Game/CraterPark/Meshes/UC_CP_mixed_0'}
    for record, package in crater.items():
        write(game / f'assets/adopted/craterpark/{record}/asset.toml',
              f'id = "adopted/craterpark/{record}"\n\n[[outputs]]\npackage = "{package}"\n')
    write(game / 'assets/adopted/craterpark/craterpark_ownership.json', json.dumps(OWNERSHIP))
    write(game / 'world/regions/w11-megapark/objects.toml', HEADER.format(tag='megapark'))
    write(game / 'world/regions/w12-craterpark/objects.toml', HEADER.format(tag='craterpark'))
    return game


@pytest.fixture
def game(tmp_path, monkeypatch):
    """Regions for the migration: the environment's manifest and the two park regions, and the Mega Park data."""
    game = tmp_path / 'game'
    add_region(game, 'w00-island', [-1000, -1000, 1000, 1000])
    add_region(game, 'w11-megapark', [-1000, -1000, 0, 0], tag='megapark')
    add_region(game, 'w12-craterpark', [0, -1000, 1000, 0], tag='craterpark')
    write(game / 'unreal/Content/Data/megapark/park.json', json.dumps(MEGA))
    monkeypatch.setattr(objects.save_validate, 'engine_identity', lambda: 'test')
    monkeypatch.setattr(objects.save_validate, 'actor_info', lambda path: (None, None))
    monkeypatch.setenv('ATELIER_AGENT', objects.authority.BOOTSTRAP_WRITER)
    monkeypatch.delenv('ATELIER_CLAIMS_TASK', raising=False)
    return game


def park_files(tmp_path, mega=MEGA, crater=CRATER):
    mega_path, crater_path = tmp_path / 'mega.json', tmp_path / 'crater.json'
    mega_path.write_text(json.dumps(mega))
    crater_path.write_text(json.dumps(crater))
    return mega_path, crater_path


def all_names(park):
    return [e['name'] for kind in ('render', 'collision') for e in park[kind]]


def objects_toml(game, body, tag='megapark'):
    write(game / f'world/regions/w{"11-megapark" if tag == "megapark" else "12-craterpark"}/objects.toml',
          f'schema = 1\ntag = "{tag}"\ndata = "{tag}/park.json"\n\n' + body)


def region_of(game):
    return SimpleNamespace(id='region/w11-megapark', folder=game / 'world/regions/w11-megapark')


# --- the converter (tools/migrate/parks.py) ---------------------------------------------------------------------------

def test_every_piece_is_one_object_and_a_rerun_writes_the_same_text(kit, tmp_path):
    mega_path, crater_path = park_files(tmp_path)
    first = parks.outputs(kit, mega_path, crater_path)
    counts = {}
    for path, text in first.items():
        objects_held = tomllib.loads(text)['objects']
        held = [name for entry in objects_held for name in entry['park']]
        assert len(held) == len(set(held))
        expected = all_names(MEGA if 'megapark' in str(path) else CRATER)
        assert sorted(held) == sorted(expected)
        counts[path.parent.name] = len(objects_held)
    assert counts == {'w11-megapark': 2, 'w12-craterpark': 3}
    for path, text in first.items():
        write(path, text)
    assert parks.outputs(kit, mega_path, crater_path) == first
    mega_objects = tomllib.loads(first[kit / 'world/regions/w11-megapark/objects.toml'])['objects']
    assert {o['id']: o['model'] for o in mega_objects} == {
        'object/megapark/cell-x150-zm750': 'adopted/megapark/cell-x150-zm750', 'object/megapark/seam': 'adopted/megapark/seam'}


def test_a_piece_no_unit_owns_is_refused(kit, tmp_path):
    mega_path, crater_path = park_files(tmp_path, mega={**MEGA, 'render': MEGA['render'] + [{'name': 'SM_MP_Z'}]})
    with pytest.raises(parks.ConvertError, match='SM_MP_Z is owned by no unit'):
        parks.outputs(kit, mega_path, crater_path)


def test_the_ownership_file_must_agree_with_the_records(kit, tmp_path):
    bad = dict(OWNERSHIP, render={'SM_CP_p8_1': 'p9', 'SM_CP_floor_1': 'crater_floor'})
    write(kit / 'assets/adopted/craterpark/craterpark_ownership.json', json.dumps(bad))
    mega_path, crater_path = park_files(tmp_path)
    with pytest.raises(parks.ConvertError, match='SM_CP_p8_1'):
        parks.outputs(kit, mega_path, crater_path)


def test_a_mesh_two_records_own_is_refused(kit, tmp_path):
    write(kit / 'assets/adopted/craterpark/collision-mixed/asset.toml',
          'id = "x"\n\n[[outputs]]\npackage = "/Game/CraterPark/Meshes/SM_CP_p8_1"\n')
    mega_path, crater_path = park_files(tmp_path)
    with pytest.raises(parks.ConvertError, match='two records'):
        parks.outputs(kit, mega_path, crater_path)


def test_other_entries_survive_the_rewrite(kit, tmp_path):
    kept = ('[[objects]]\nid = "object/megapark/zeppelin"\ngroup = "SM_Z"\nmodel = "adopted/megapark/zeppelin"\n'
            'about = "the zeppelin station"\n')
    path = kit / 'world/regions/w11-megapark/objects.toml'
    write(path, path.read_text() + '\n' + kept)
    mega_path, crater_path = park_files(tmp_path)
    text = parks.outputs(kit, mega_path, crater_path)[path]
    assert kept in text
    assert text.count('[[objects]]') == 3
    write(path, text)
    assert parks.outputs(kit, mega_path, crater_path)[path] == text


def test_the_committed_entries_match_the_real_park_data():
    """Against the real park files; skipped where they are still Git LFS pointers in this checkout."""
    real = {tag: ROOT / 'unreal/Content/Data' / tag / 'park.json' for tag in ('megapark', 'craterpark')}
    if any(not p.is_file() or records.is_lfs_pointer(p) for p in real.values()):
        pytest.skip('the park files are Git LFS pointers in this checkout')
    for path, text in parks.outputs(ROOT, real['megapark'], real['craterpark']).items():
        assert path.read_text() == text, f'{path} is out of date: run tools/migrate/parks.py'


# --- loading and planning (tools/migrate/objects.py) -------------------------------------------------------------------

def test_park_entries_load(game):
    objects_toml(game, MEGA_PARK_OBJECTS)
    loaded = objects.load_objects(region_of(game))
    assert loaded['data'] == 'megapark/park.json'
    assert [(o['id'], o['park'], o['groups']) for o in loaded['objects']] == [
        ('object/megapark/cell-x150-zm750', ['SM_MP_A', 'UC_MP_C_0'], []), ('object/megapark/seam', ['SM_MP_B'], [])]


def test_malformed_park_entries_are_refused(game):
    cases = [
        MEGA_PARK_OBJECTS.replace('park = ["SM_MP_B"]', 'park = ["SM_MP_B"]\ngroup = "SM_X"'),
        MEGA_PARK_OBJECTS.replace('park = ["SM_MP_B"]', 'park = ["SM_MP_A"]'),
        MEGA_PARK_OBJECTS.replace('park = ["SM_MP_B"]', 'park = []'),
    ]
    for body in cases:
        objects_toml(game, body)
        with pytest.raises(objects.ObjectError):
            objects.load_objects(region_of(game))
    objects_toml(game, MEGA_PARK_OBJECTS)
    path = game / 'world/regions/w11-megapark/objects.toml'
    write(path, path.read_text().replace('data = "megapark/park.json"', 'data = ""'))
    with pytest.raises(objects.ObjectError, match='needs data'):
        objects.load_objects(region_of(game))


def test_a_park_name_the_file_does_not_hold_is_refused(game):
    objects_toml(game, MEGA_PARK_OBJECTS.replace('"SM_MP_B"', '"SM_MP_NOPE"'))
    with pytest.raises(objects.ObjectError, match='SM_MP_NOPE is no render or collision piece'):
        objects.park_plan('region/w11-megapark', 'megapark', 'megapark/park.json',
                          objects.load_objects(region_of(game))['objects'], game)


def test_a_park_file_still_an_lfs_pointer_is_refused(game):
    write(game / 'unreal/Content/Data/megapark/park.json', LFS)
    objects_toml(game, MEGA_PARK_OBJECTS)
    with pytest.raises(objects.ObjectError, match='LFS pointer'):
        objects.park_plan('region/w11-megapark', 'megapark', 'megapark/park.json',
                          objects.load_objects(region_of(game))['objects'], game)


def test_the_plan_carries_each_piece_with_its_kind_and_unit(game):
    objects_toml(game, MEGA_PARK_OBJECTS)
    seen = []

    def editor(plan_file):
        seen.append(plan_file.read_bytes())
        return 'no completion line'   # the plan is what this test reads; the editor step is not run

    with pytest.raises(objects.ObjectError, match='did not report completion'):
        objects.migrate(game, ['region/w11-megapark'], 'region/w00-island', None, editor=editor,
                        out=game / 'out', echo=lambda *_: None)
    plan = json.loads(seen[0])
    assert plan['parks'] == [{'region': 'region/w11-megapark', 'tag': 'megapark', 'data': 'megapark/park.json',
                              'pieces': ['SM_MP_A', 'UC_MP_C_0', 'SM_MP_B'], 'is_collision': [False, True, False],
                              'units': ['cell-x150-zm750', 'cell-x150-zm750', 'seam']}]
    assert plan['groups'] == [] and plan['splits'] == [] and plan['environment'] == 'region/w00-island'
    with pytest.raises(objects.ObjectError, match='did not report completion'):   # a rerun plans the same bytes
        objects.migrate(game, ['region/w11-megapark'], 'region/w00-island', None, editor=editor,
                        out=game / 'out', echo=lambda *_: None)
    assert seen[1] == seen[0]


def test_park_objects_need_the_environment_manifest(game):
    objects_toml(game, MEGA_PARK_OBJECTS)
    with pytest.raises(objects.ObjectError, match='--environment is needed'):
        objects.migrate(game, ['region/w11-megapark'], None, None, editor=lambda plan_file: '', out=game / 'out',
                        echo=lambda *_: None)
