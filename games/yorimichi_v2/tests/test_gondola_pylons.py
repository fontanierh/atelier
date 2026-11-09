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
GAME = ROOT
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


def test_check_writes_nothing():
    before = (REGION_FOLDER / 'objects.toml').read_bytes()
    assert pylons.main(['--check']) in (0, 1)
    assert (REGION_FOLDER / 'objects.toml').read_bytes() == before


GROUP_PACKAGES = {'OXNPYPALF2J1WU4BQWWGA6', 'JL5ZQDUJRMEIYACD76AXMG', 'M90M3QGF1CH7RRRY3KDFBM'}


def test_retire_deletes_exactly_the_group_records_and_actor_packages(data):
    taken = pylons.select(data)
    plan = pylons.retire_plan(GAME, taken, (REGION_FOLDER / 'objects.toml').read_text(),
                              (REGION_FOLDER / 'objects.saved.json').read_text())
    assert plan['groups'] == ['object/gondola/pylons-l1', 'object/gondola/pylons-l2', 'object/gondola/pylons-l3']
    records_deleted = sorted(d for d in plan['deletes'] if d.startswith('assets/object/gondola/pylons-l'))
    assert records_deleted == sorted(f'assets/object/gondola/pylons-l{n}/{name}'
                                     for n in (1, 2, 3) for name in ('asset.toml', 'verified.json'))
    packages = sorted(d for d in plan['deletes'] if d.startswith('unreal/Content/__ExternalActors__/'))
    assert len(packages) == 3 and all(any(stem in d for stem in GROUP_PACKAGES) for d in packages)
    assert set(plan['deletes']) == set(records_deleted) | set(packages)


def test_retire_drops_exactly_the_three_group_keys_from_the_saved_list(data):
    taken = pylons.select(data)
    saved_text = (REGION_FOLDER / 'objects.saved.json').read_text()
    plan = pylons.retire_plan(GAME, taken, (REGION_FOLDER / 'objects.toml').read_text(), saved_text)
    before, after = json.loads(saved_text), json.loads(plan['saved_text'])
    assert set(before['objects']) - set(after['objects']) == set(plan['groups'])
    assert all(after['objects'][k] == before['objects'][k] for k in after['objects'])
    assert after['schema'] == before['schema']
    assert len(after['objects']) == 6


def test_retire_is_refused_when_the_saved_definition_differs(data):
    body = json.loads((REGION_FOLDER / 'objects.saved.json').read_text())
    body['objects']['object/gondola/pylons-l2']['route'] = ['GD_L2_0_Tower']
    with pytest.raises(pylons.PylonError, match='object/gondola/pylons-l2: objects.saved.json does not record'):
        pylons.retire_plan(GAME, pylons.select(data), (REGION_FOLDER / 'objects.toml').read_text(), json.dumps(body))


def test_retire_is_refused_when_a_group_record_is_missing(data, tmp_path):
    with pytest.raises(pylons.PylonError, match='pylons-l1: its record .* is missing'):
        pylons.retire_plan(tmp_path, pylons.select(data), (REGION_FOLDER / 'objects.toml').read_text(),
                           (REGION_FOLDER / 'objects.saved.json').read_text())


def test_retire_is_refused_when_a_pylon_is_already_saved(data):
    body = json.loads((REGION_FOLDER / 'objects.saved.json').read_text())
    body['objects']['object/gondola/pylon-l1-0'] = {'id': 'object/gondola/pylon-l1-0'}
    with pytest.raises(pylons.PylonError, match='object/gondola/pylon-l1-0 is already saved'):
        pylons.retire_plan(GAME, pylons.select(data), (REGION_FOLDER / 'objects.toml').read_text(), json.dumps(body))


def test_step_paths_cover_the_retire_the_write_and_the_later_save(data):
    paths = pylons.step_paths(GAME, pylons.select(data))
    step, save = set(paths['step']), set(paths['save'])
    assert 'games/yorimichi_v2/world/regions/w18-gondola/objects.toml' in step
    assert 'games/yorimichi_v2/world/regions/w18-gondola/objects.saved.json' in step
    assert 'games/yorimichi_v2/assets/object/gondola/pylons-l3/asset.toml' in step
    assert any(p.startswith('games/yorimichi_v2/unreal/Content/__ExternalActors__/') for p in step)
    assert 'games/yorimichi_v2/assets/object/gondola/pylon-l3-1/asset.toml' in save
    assert 'games/yorimichi_v2/assets/object/gondola/pylon-l3-1/verified.json' in save
    assert f'games/yorimichi_v2/{objects.MANIFEST["region/w00-island"]}' in save
    assert not step & save


def test_apply_without_authority_writes_nothing(data, monkeypatch):
    monkeypatch.setattr(pylons.authority, 'd04', lambda *a, **k: (None, True))
    watched = [REGION_FOLDER / 'objects.toml', REGION_FOLDER / 'objects.saved.json', GAME / 'assets/object/gondola/pylons-l1/asset.toml']
    before = [p.read_bytes() for p in watched]
    with pytest.raises(pylons.PylonError):
        pylons.apply_step(GAME, pylons.select(data), 'TASK', echo=lambda *_: None)
    assert [p.read_bytes() for p in watched] == before


def test_the_journaled_write_applies_its_writes_and_deletes_exactly(tmp_path):
    keep, gone = tmp_path / 'assets/x/asset.toml', tmp_path / 'unreal/Content/gone.uasset'
    keep.parent.mkdir(parents=True), gone.parent.mkdir(parents=True)
    keep.write_text('old'), gone.write_text('bin')
    ops = {'writes': {'assets/x/asset.toml': b'new'}, 'deletes': ['unreal/Content/gone.uasset']}
    result = pylons.apply.execute(tmp_path, ops, scopes={'region/w18-gondola'}, lockable=lambda g, r: [])
    assert result == {'written': ['assets/x/asset.toml'], 'deleted': ['unreal/Content/gone.uasset']}
    assert keep.read_text() == 'new' and not gone.exists()
    assert not (tmp_path / pylons.apply.JOURNAL).exists()
