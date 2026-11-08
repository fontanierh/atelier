"""Transport route objects: the railway track, the ferry terminals and the gondola's static stations and pylons saved as
objects (w20-railway, w17-ferry, w18-gondola objects.toml; objects.py plans them as `railways`, `ferries` and `gondolas`; the
editor step saves them with UV2MigrationTravel). Each object lists the entries of its route's data file, each entry once."""
import importlib.util
import json
import sys
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


objects = load('v2_migrate_objects_routes', 'tools/migrate/objects.py')
LFS = 'version https://git-lfs.github.com/spec/v1\noid sha256:' + '0' * 64 + '\nsize 1234\n'
RAILWAY, FERRY, GONDOLA = 'region/w20-railway', 'region/w17-ferry', 'region/w18-gondola'
DATA = {RAILWAY: ('w20-railway', 'railway', 'belmonte_track/track.json'),
        FERRY: ('w17-ferry', 'ferry', 'ferry/service/service.json'),
        GONDOLA: ('w18-gondola', 'gondola', 'gondola/runtime.json')}


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def real(rel):
    path = ROOT / 'unreal/Content/Data' / rel
    if not path.is_file() or records.is_lfs_pointer(path):
        pytest.skip(f'{rel} is a Git LFS pointer in this checkout')
    return json.loads(path.read_text())


def committed(region):
    folder = ROOT / 'world/regions' / DATA[region][0]
    return objects.load_objects(SimpleNamespace(id=region, folder=folder))


def route_names(loaded):
    return [name for item in loaded['objects'] for name in item['route']]


def real_names(region):
    """Every entry the route's real data file holds, by the names objects.toml uses."""
    if region == RAILWAY:
        spec = real(DATA[region][2])
        names = [p['name'] for p in spec['pieces']]
        names += [f"{g['mesh'].rsplit('/', 1)[-1].split('.')[0]}#{g['key']}" for g in spec['instances']]
    elif region == FERRY:
        names = [t['key'] for t in real(DATA[region][2])['terminals']]
    else:
        names = [s['name'] for s in real(DATA[region][2])['static']]
    return names


def fake_data(region, names):
    """A small data file of the route's shape holding exactly `names` (for the plan tests, which need no real meshes)."""
    if region == RAILWAY:
        pieces = [{'name': n, 'mesh': f'/Game/BelmonteTrack/{n}.{n}', 'at': [0, 0, 0], 'kind': 'chunk', 'collision': 1}
                  for n in names if '#' not in n]
        instances = []
        for n in names:
            if '#' in n:
                mesh, key = n.split('#')
                instances.append({'kind': 'sleeper', 'mesh': f'/Game/BelmonteTrack/{mesh}.{mesh}', 'key': key,
                                  'hierarchical': True, 'collision': False, 'shadow': False, 'cull_cm': 1, 'instances': []})
        return {'pieces': pieces, 'instances': instances, 'cull_cm': {'piece': 1}}
    if region == FERRY:
        return {'terminals': [{'key': n} for n in names]}
    return {'static': [{'name': n, 'mesh': f'/Game/Gondola/{n}.{n}'} for n in names]}


@pytest.fixture
def game(tmp_path, monkeypatch):
    """The environment's manifest, the three route regions with their committed objects.toml, and fake data files."""
    game = tmp_path / 'game'
    write(game / 'world/regions/w00-island/region.toml', 'schema = 1\nid = "region/w00-island"\nbounds_cm = [-1000, -1000, 1000, 1000]\n'
          'maps = ["/Game/V2/Maps/Slice"]\n')
    write(game / 'world/regions/w00-island/actors.verified.json', '{"asset": "region/w00-island", "engine": "test", "files": {}}')
    for region, (folder, tag, data) in DATA.items():
        write(game / 'world/regions' / folder / 'region.toml',
              f'schema = 1\nid = "{region}"\nbounds_cm = [-1000, -1000, 1000, 1000]\nmaps = ["/Game/V2/Maps/Slice"]\n')
        write(game / 'world/regions' / folder / 'actors.verified.json', '{"asset": "%s", "engine": "test", "files": {}}' % region)
        write(game / 'world/regions' / folder / 'objects.toml', (ROOT / 'world/regions' / folder / 'objects.toml').read_text())
        names = [n for item in committed(region)['objects'] for n in item['route']]
        write(game / 'unreal/Content/Data' / data, json.dumps(fake_data(region, names)))
    monkeypatch.setattr(objects.save_validate, 'engine_identity', lambda: 'test')
    monkeypatch.setattr(objects.save_validate, 'actor_info', lambda path: (None, None))
    monkeypatch.setenv('ATELIER_AGENT', objects.authority.BOOTSTRAP_WRITER)
    monkeypatch.delenv('ATELIER_CLAIMS_TASK', raising=False)
    return game


def plan_of(game, regions, environment='region/w00-island'):
    seen = []

    def editor(plan_file):
        seen.append(json.loads(plan_file.read_text()))
        return 'no completion line'   # the plan is what these tests read; the editor step is not run

    with pytest.raises(objects.ObjectError, match='did not report completion'):
        objects.migrate(game, regions, environment, None, editor=editor, out=game / 'out', echo=lambda *_: None)
    return seen[0]


# --- the committed entries ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize('region', [RAILWAY, FERRY, GONDOLA])
def test_the_committed_route_objects_load_with_a_model_each(region):
    loaded = committed(region)
    assert loaded['tag'] == DATA[region][1] and loaded['data'] == DATA[region][2]
    assert loaded['objects'] and all(item['model'] for item in loaded['objects'])
    assert all(item['id'].startswith(f'object/{DATA[region][1]}/') for item in loaded['objects'])


@pytest.mark.parametrize('region', [RAILWAY, FERRY, GONDOLA])
def test_the_committed_route_objects_hold_every_real_entry_once(region):
    """Against the real data file; skipped where it is still a Git LFS pointer in this checkout."""
    names = real_names(region)
    held = route_names(committed(region))
    assert len(held) == len(set(held)), 'an entry is held by two objects'
    assert sorted(held) == sorted(names)


def test_the_railway_sleepers_follow_their_chunk_run():
    """A sleeper group's key is its chunk index: each chunk run holds the sleepers of its own chunks."""
    runs = {item['id']: item['route'] for item in committed(RAILWAY)['objects'] if item['id'].startswith('object/railway/chunks-')}
    assert len(runs) == 4
    for oid, entries in runs.items():
        first, last = (int(v) for v in oid.rsplit('/', 1)[1].split('-')[1:])
        sleepers = sorted(int(e.split('#')[1]) for e in entries if '#' in e and e.startswith('SM_TK_Sleeper#'))
        assert sleepers == list(range(first, last + 1)), oid


# --- the plan (what the editor step is given) ----------------------------------------------------------------------------

def test_the_plan_carries_each_route_entry_with_its_unit(game):
    plan = plan_of(game, [RAILWAY, FERRY, GONDOLA])
    assert plan['environment'] == 'region/w00-island'
    assert plan['parks'] == [] and plan['hippodromes'] == [] and plan['groups'] == []
    railways = {r['region']: r for r in plan['railways']}
    assert railways[RAILWAY]['tag'] == 'railway' and railways[RAILWAY]['data'] == 'belmonte_track/track.json'
    assert len(railways[RAILWAY]['names']) == len(railways[RAILWAY]['units'])
    assert 'SM_TK_Sleeper#0' in railways[RAILWAY]['names'] and 'chunks-0-19' in railways[RAILWAY]['units']
    ferries = {f['region']: f for f in plan['ferries']}
    assert ferries[FERRY]['names'] == ['hidamari', 'brinecove']
    assert ferries[FERRY]['units'] == ['terminal-hidamari', 'terminal-brinecove']
    gondolas = {g['region']: g for g in plan['gondolas']}
    assert len(gondolas[GONDOLA]['names']) == 52 and len(set(gondolas[GONDOLA]['units'])) == 9


def test_a_route_entry_the_file_does_not_hold_is_refused(game):
    body = (game / 'world/regions/w17-ferry/objects.toml').read_text().replace('route = ["brinecove"]', 'route = ["nowhere"]')
    write(game / 'world/regions/w17-ferry/objects.toml', body)
    with pytest.raises(objects.ObjectError, match='nowhere is no entry of ferry/service/service.json'):
        objects.migrate(game, [FERRY], 'region/w00-island', None, editor=lambda plan_file: '', out=game / 'out',
                        echo=lambda *_: None)


def test_a_route_entry_listed_twice_is_refused(game):
    body = (game / 'world/regions/w17-ferry/objects.toml').read_text().replace('route = ["brinecove"]', 'route = ["hidamari"]')
    write(game / 'world/regions/w17-ferry/objects.toml', body)
    with pytest.raises(objects.ObjectError, match='a route entry is listed twice'):
        objects.load_objects(SimpleNamespace(id=FERRY, folder=game / 'world/regions/w17-ferry'))


def test_an_empty_route_is_refused(game):
    body = (game / 'world/regions/w17-ferry/objects.toml').read_text().replace('route = ["brinecove"]', 'route = []')
    write(game / 'world/regions/w17-ferry/objects.toml', body)
    with pytest.raises(objects.ObjectError, match='route needs a list of entry names'):
        objects.load_objects(SimpleNamespace(id=FERRY, folder=game / 'world/regions/w17-ferry'))


def test_route_objects_need_the_environment_manifest(game):
    with pytest.raises(objects.ObjectError, match='--environment is needed'):
        objects.migrate(game, [FERRY], None, None, editor=lambda plan_file: '', out=game / 'out', echo=lambda *_: None)


def test_a_route_file_of_no_known_shape_is_refused(game):
    write(game / 'unreal/Content/Data/ferry/service/service.json', json.dumps({'render': []}))
    with pytest.raises(objects.ObjectError, match='is no railway, ferry or gondola file'):
        objects.migrate(game, [FERRY], 'region/w00-island', None, editor=lambda plan_file: '', out=game / 'out',
                        echo=lambda *_: None)


def test_a_route_file_still_an_lfs_pointer_is_refused(game):
    write(game / 'unreal/Content/Data/gondola/runtime.json', LFS)
    with pytest.raises(objects.ObjectError, match='LFS pointer'):
        objects.migrate(game, [GONDOLA], 'region/w00-island', None, editor=lambda plan_file: '', out=game / 'out',
                        echo=lambda *_: None)
