"""The W18 gondola's pylons as objects of their own (tools/migrate/gondola_pylons.py): the selection is deterministic and in
route order; every taken tower is a static entry of gondola/runtime.json, listed once; the station objects are unchanged;
a partly taken group is refused; and --check writes nothing."""
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


pylons = load('v2_migrate_gondola_pylons', 'tools/migrate/gondola_pylons.py')
objects = load('v2_migrate_objects_pylons', 'tools/migrate/objects.py')
REGION_FOLDER = ROOT / 'world/regions/w18-gondola'


@pytest.fixture(scope='module')
def data():
    path = ROOT / 'unreal/Content/Data/gondola/runtime.json'
    if not path.is_file() or records.is_lfs_pointer(path):
        pytest.skip('gondola/runtime.json is a Git LFS pointer in this checkout')
    return json.loads(path.read_text())


@pytest.fixture(scope='module')
def committed():
    return (REGION_FOLDER / 'objects.toml').read_text()


def static_names(data):
    return [s['name'] for s in data['static']]


def test_selection_is_deterministic_and_in_route_order(data):
    first = pylons.select(data)
    assert first == pylons.select(data)
    assert [p['name'] for p in first] == ['GD_L1_0_Tower', 'GD_L1_1_Tower', 'GD_L1_2_Tower', 'GD_L1_3_Tower',
                                          'GD_L2_0_Tower', 'GD_L2_1_Tower', 'GD_L2_2_Tower', 'GD_L2_3_Tower',
                                          'GD_L3_0_Tower', 'GD_L3_1_Tower']
    for line in ('1', '2', '3'):
        indexes = [p['index'] for p in first if p['line'] == line]
        assert indexes == sorted(indexes)


def test_the_limit_takes_a_prefix(data):
    assert pylons.select(data, limit=3) == pylons.select(data)[:3]


def test_every_taken_tower_is_a_runtime_entry_listed_once(data):
    taken = [p['name'] for p in pylons.select(data)]
    assert len(taken) == len(set(taken))
    assert set(taken) <= set(static_names(data))


def test_each_tower_names_its_own_record_and_object(data):
    for p in pylons.select(data):
        assert p['model'] == f'adopted/gondola/tower-l{p["line"]}-{p["index"]}'
        assert p['object'] == f'object/gondola/pylon-l{p["line"]}-{p["index"]}'


def test_rendered_objects_load_and_list_each_tower_once(data, tmp_path):
    text = pylons.render((REGION_FOLDER / 'objects.toml').read_text(), data)
    (tmp_path / 'objects.toml').write_text(text)
    loaded = objects.load_objects(SimpleNamespace(id='region/w18-gondola', folder=tmp_path))
    routes = [name for item in loaded['objects'] for name in item['route']]
    assert len(routes) == len(set(routes))
    pylon_routes = [name for name in routes if name.endswith('_Tower')]
    assert pylon_routes == [p['name'] for p in pylons.select(data)]
    assert set(pylon_routes) <= set(static_names(data))
    assert all(len(item['route']) == 1 for item in loaded['objects'] if item['id'].startswith('object/gondola/pylon-'))


def test_the_station_objects_are_unchanged(data, committed):
    before = {o['id']: o for o in tomllib.loads(committed)['objects'] if o['id'].startswith('object/gondola/station-')}
    after = {o['id']: o for o in tomllib.loads(pylons.render(committed, data))['objects']
             if o['id'].startswith('object/gondola/station-')}
    assert len(before) == 6 and before == after


def test_the_pylon_groups_are_removed_once_all_their_towers_are_taken(data, committed):
    text = pylons.render(committed, data)
    listed = [o['id'] for o in tomllib.loads(text)['objects']]
    assert not [i for i in listed if i.startswith('object/gondola/pylons-l')]
    assert len(listed) == len(set(listed)) == 16


def test_a_partly_taken_group_is_refused(data, committed, monkeypatch):
    monkeypatch.setattr(pylons, 'LIMIT', 3)
    with pytest.raises(pylons.PylonError, match='object/gondola/pylons-l1 is only partly taken'):
        pylons.render(committed, data)


def test_a_rerun_on_its_own_output_is_refused(data, committed):
    text = pylons.render(committed, data)
    with pytest.raises(pylons.PylonError, match='already has an object'):
        pylons.render(text, data)


def test_check_writes_nothing(tmp_path, monkeypatch):
    before = (REGION_FOLDER / 'objects.toml').read_bytes()
    assert pylons.main(['--check']) in (0, 1)
    assert (REGION_FOLDER / 'objects.toml').read_bytes() == before


def test_paths_name_the_objects_toml_and_the_records_a_claim_covers(data):
    paths = pylons.paths(pylons.select(data))
    assert 'games/yorimichi_v2/world/regions/w18-gondola/objects.toml' in paths
    assert 'games/yorimichi_v2/assets/object/gondola/pylon-l3-1/asset.toml' in paths
    assert 'games/yorimichi_v2/assets/object/gondola/pylons-l1/verified.json' in paths
