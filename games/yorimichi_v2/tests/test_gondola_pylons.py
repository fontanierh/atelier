"""The W18 gondola's pylons as objects of their own (tools/migrate/gondola_pylons.py): the selection is deterministic and in
route order; every taken tower is a static entry of gondola/runtime.json, listed once; the station objects are unchanged;
a partly taken group is refused; and the steps (prepare, save, retire) each repeat safely in a fake copy of the tree."""
import importlib.util
import json
import shutil
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
def unprepared(data):
    """The lifecycle tests below start from the unsplit real tree. Once the split ran on it (state `done`), they skip and
    test_the_real_tree_is_split pins the result instead."""
    current, _ = pylons.state(GAME, pylons.select(data))
    if current != 'unprepared':
        pytest.skip(f'the real tree is {current}, not unprepared: the split already ran')


@pytest.fixture(scope='module')
def committed(unprepared):
    return (REGION_FOLDER / 'objects.toml').read_text()


def static_names(data):
    return [s['name'] for s in data['static']]


# --- the selection and the rendered objects.toml (read only) ---------------------------------------------------------------

def test_selection_is_deterministic_and_in_route_order(data):
    first = pylons.select(data)
    assert first == pylons.select(data)
    assert [p['name'] for p in first] == ['GD_L1_0_Tower', 'GD_L1_1_Tower', 'GD_L1_2_Tower', 'GD_L1_3_Tower',
                                          'GD_L2_0_Tower', 'GD_L2_1_Tower', 'GD_L2_2_Tower', 'GD_L2_3_Tower',
                                          'GD_L3_0_Tower', 'GD_L3_1_Tower']
    for line in ('1', '2', '3'):
        indexes = [p['index'] for p in first if p['line'] == line]
        assert indexes == sorted(indexes)


def test_the_limit_takes_a_prefix_and_each_tower_names_its_record_and_object(data):
    assert pylons.select(data, limit=3) == pylons.select(data)[:3]
    for p in pylons.select(data):
        assert p['model'] == f'adopted/gondola/tower-l{p["line"]}-{p["index"]}'
        assert p['object'] == f'object/gondola/pylon-l{p["line"]}-{p["index"]}'


def test_rendered_objects_load_and_list_each_tower_once(data, committed, tmp_path):
    text = pylons.render(committed, data)
    (tmp_path / 'objects.toml').write_text(text)
    loaded = objects.load_objects(SimpleNamespace(id='region/w18-gondola', folder=tmp_path))
    routes = [name for item in loaded['objects'] for name in item['route']]
    assert len(routes) == len(set(routes))
    assert [r for r in routes if r.endswith('_Tower')] == [p['name'] for p in pylons.select(data)]
    assert set(routes) <= set(static_names(data))
    assert len(loaded['objects']) == 16


def test_the_station_objects_are_unchanged(data, committed):
    before = {o['id']: o for o in tomllib.loads(committed)['objects'] if o['id'].startswith('object/gondola/station-')}
    after = {o['id']: o for o in tomllib.loads(pylons.render(committed, data))['objects']
             if o['id'].startswith('object/gondola/station-')}
    assert len(before) == 6 and before == after


def test_a_partly_taken_group_is_refused(data, committed, monkeypatch):
    monkeypatch.setattr(pylons, 'LIMIT', 3)
    with pytest.raises(pylons.PylonError, match='object/gondola/pylons-l1 is only partly taken'):
        pylons.render(committed, data)


def test_a_rerun_on_its_own_output_is_refused(data, committed):
    text = pylons.render(committed, data)
    with pytest.raises(pylons.PylonError, match='already has an object'):
        pylons.render(text, data)


def test_check_writes_nothing_and_reports_the_state(unprepared, capsys):
    before = [p.read_bytes() for p in (REGION_FOLDER / 'objects.toml', REGION_FOLDER / 'objects.saved.json')]
    assert pylons.main(['--check']) == 0
    assert 'state: unprepared' in capsys.readouterr().out
    assert [p.read_bytes() for p in (REGION_FOLDER / 'objects.toml', REGION_FOLDER / 'objects.saved.json')] == before


def test_the_claim_paths_name_every_file_and_both_scopes(data, unprepared):
    plan = pylons.claim_paths(GAME, pylons.select(data))
    paths = set(plan['paths'])
    assert 'games/yorimichi_v2/world/regions/w18-gondola/objects.toml' in paths
    assert 'games/yorimichi_v2/world/regions/w18-gondola/objects.saved.json' in paths
    assert 'games/yorimichi_v2/world/regions/w18-gondola/pylon-retire.json' in paths
    assert 'games/yorimichi_v2/assets/object/gondola/pylons-l3/asset.toml' in paths
    assert 'games/yorimichi_v2/assets/object/gondola/pylon-l3-1/verified.json' in paths
    assert f'games/yorimichi_v2/{objects.MANIFEST["region/w00-island"]}' in paths
    assert plan['scopes'] == ['region/w00-island', 'region/w18-gondola']


# --- the lifecycle in a fake copy of the tree ------------------------------------------------------------------------------

def copy_tree(tmp: Path, data_bytes: bytes) -> None:
    """The parts of the W18 tree the steps read and write: the region's lists, the three groups' records and actor packages,
    the runtime file, and a placeholder record for each tower's model."""
    region = tmp / 'world/regions/w18-gondola'
    region.mkdir(parents=True)
    for name in ('objects.toml', 'objects.saved.json'):
        shutil.copy2(REGION_FOLDER / name, region / name)
    (tmp / 'unreal/Content/Data/gondola').mkdir(parents=True)
    (tmp / 'unreal/Content/Data/gondola/runtime.json').write_bytes(data_bytes)
    for n in (1, 2, 3):
        src = GAME / f'assets/object/gondola/pylons-l{n}'
        dst = tmp / f'assets/object/gondola/pylons-l{n}'
        shutil.copytree(src, dst)
        for package in records.load_asset(dst / 'asset.toml').outputs:
            for path in records.package_files(GAME, package.package):
                if path.is_file():
                    target = tmp / path.relative_to(GAME)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)
    for model in [p['model'] for p in pylons.select(json.loads(data_bytes))]:
        (tmp / 'assets' / model).mkdir(parents=True)
        (tmp / 'assets' / model / 'asset.toml').write_text('schema = 1\n')


def tree_bytes(tmp: Path) -> dict:
    return {p.relative_to(tmp).as_posix(): p.read_bytes() for p in sorted(tmp.rglob('*')) if p.is_file()
            and 'Saved' not in p.parts}


def write_receipts(tmp: Path, taken: list[dict]) -> None:
    """What objects.py's save leaves: each replacement's record, its actor package, its verified.json and its saved entry."""
    region = tmp / 'world/regions/w18-gondola'
    listed = objects.load_objects(SimpleNamespace(id='region/w18-gondola', folder=region))['objects']
    saved = json.loads((region / 'objects.saved.json').read_text())
    for index, p in enumerate(taken):
        item = next(i for i in listed if i['id'] == p['object'])
        package = f'/Game/__ExternalActors__/V2/Maps/Slice/T/E/PYLON{index:03d}'
        actor = tmp / 'unreal/Content/__ExternalActors__/V2/Maps/Slice/T/E' / f'PYLON{index:03d}.uasset'
        actor.parent.mkdir(parents=True, exist_ok=True)
        actor.write_bytes(b'pylon %d' % index)
        folder = tmp / 'assets' / p['object']
        folder.mkdir(parents=True)
        (folder / 'asset.toml').write_text(objects.record_text(item, 'region/w18-gondola', package))
        rel = actor.relative_to(tmp).as_posix()
        (folder / 'verified.json').write_text(json.dumps({
            'schema': 1, 'kind': 'editor-saved', 'asset': p['object'], 'engine': 'test',
            'dependencies': {p['model']: 'a' * 64}, 'files': {rel: records.sha256_file(actor)}}, indent=2) + '\n')
        saved['objects'][p['object']] = pylons.saved_definition(item)
    (region / 'objects.saved.json').write_text(json.dumps(saved, indent=2, sort_keys=True) + '\n')


def test_prepare_save_retire_each_repeat_safely(data, unprepared, tmp_path, monkeypatch):
    calls = []

    def fake_authorize(paths, claim, what, *, scopes=(), repo=None):
        calls.append((claim, tuple(sorted(scopes))))
        if claim != 'TASK':
            raise pylons.authority.Unauthorized('no claim')

    monkeypatch.setattr(pylons.authority, 'authorize', fake_authorize)
    data_bytes = (ROOT / 'unreal/Content/Data/gondola/runtime.json').read_bytes()
    copy_tree(tmp_path, data_bytes)
    taken = pylons.select(data)
    no_lock = lambda game, rels: []   # noqa: E731  (git-lfs lock attributes are a claim-time concern, not this test's)
    region = tmp_path / 'world/regions/w18-gondola'

    assert pylons.state(tmp_path, taken)[0] == 'unprepared'
    assert pylons.prepare(tmp_path, taken, 'TASK', lockable=no_lock, echo=lambda *_: None) == 'prepared'
    listed = tomllib.loads((region / 'objects.toml').read_text())['objects']
    assert {i['id'] for i in listed if i['id'].startswith('object/gondola/pylon-')} == {p['object'] for p in taken}
    assert not [i for i in listed if pylons.GROUP.match(i['id'])]
    assert (tmp_path / 'assets/object/gondola/pylons-l1/asset.toml').is_file()
    assert 'object/gondola/pylons-l1' in json.loads((region / 'objects.saved.json').read_text())['objects']
    assert json.loads((region / 'pylon-retire.json').read_text())['groups'].keys() == {
        'object/gondola/pylons-l1', 'object/gondola/pylons-l2', 'object/gondola/pylons-l3'}

    # A rerun of prepare is a no-op: nothing is written, not even the pending file's bytes.
    before = tree_bytes(tmp_path)
    assert pylons.prepare(tmp_path, taken, 'TASK', lockable=no_lock, echo=lambda *_: None) == 'prepared'
    assert tree_bytes(tmp_path) == before

    # The save failed: no replacement has a receipt, so retire refuses and changes nothing.
    with pytest.raises(pylons.PylonError, match='retire refused: the pylon objects are prepared'):
        pylons.retire(tmp_path, taken, 'TASK', lockable=no_lock, echo=lambda *_: None)
    assert tree_bytes(tmp_path) == before

    # The save completes: receipts exist, so retire completes and a rerun is a no-op.
    write_receipts(tmp_path, taken)
    assert pylons.state(tmp_path, taken)[0] == 'saved'
    assert pylons.retire(tmp_path, taken, 'TASK', lockable=no_lock, echo=lambda *_: None) == 'done'
    assert not (tmp_path / 'assets/object/gondola/pylons-l1/asset.toml').exists()
    assert not (tmp_path / 'assets/object/gondola/pylons-l1/verified.json').exists()
    assert not (tmp_path / 'unreal/Content/__ExternalActors__/V2/Maps/Slice/A/P5/OXNPYPALF2J1WU4BQWWGA6.uasset').exists()
    saved = json.loads((region / 'objects.saved.json').read_text())['objects']
    assert not [k for k in saved if pylons.GROUP.match(k)]
    assert len(saved) == 16 and all(p['object'] in saved for p in taken)
    assert not (region / 'pylon-retire.json').exists()
    assert (tmp_path / 'assets/object/gondola/pylon-l3-1/asset.toml').is_file()
    after = tree_bytes(tmp_path)
    assert pylons.retire(tmp_path, taken, 'TASK', lockable=no_lock, echo=lambda *_: None) == 'done'
    assert tree_bytes(tmp_path) == after

    # Each write was authorized under the W18 and W00 scopes.
    assert calls and all(scopes == ('region/w00-island', 'region/w18-gondola') for _, scopes in calls)


def test_a_claim_that_does_not_hold_the_steps_refuses_before_any_write(data, unprepared, tmp_path, monkeypatch):
    def refuse(paths, claim, what, *, scopes=(), repo=None):
        raise pylons.authority.Unauthorized('no claim')

    monkeypatch.setattr(pylons.authority, 'authorize', refuse)
    copy_tree(tmp_path, (ROOT / 'unreal/Content/Data/gondola/runtime.json').read_bytes())
    before = tree_bytes(tmp_path)
    with pytest.raises(pylons.PylonError, match='no claim'):
        pylons.prepare(tmp_path, pylons.select(data), 'OTHER', lockable=lambda g, r: [], echo=lambda *_: None)
    assert tree_bytes(tmp_path) == before


def test_the_command_line_dispatches_each_step(monkeypatch):
    """--retire takes --claim (step 3); --claim alone prepares (step 1); --check and --paths take none."""
    calls = []
    monkeypatch.setattr(pylons, 'runtime', lambda game: {})
    monkeypatch.setattr(pylons, 'select', lambda data: [])
    monkeypatch.setattr(pylons, 'retire', lambda game, taken, claim: calls.append(('retire', claim)))
    monkeypatch.setattr(pylons, 'prepare', lambda game, taken, claim: calls.append(('prepare', claim)))
    assert pylons.main(['--retire', '--claim', 'TASK']) == 0
    assert pylons.main(['--claim', 'TASK']) == 0
    assert calls == [('retire', 'TASK'), ('prepare', 'TASK')]
    assert pylons.main(['--retire']) == 1
    assert pylons.main(['--check', '--claim', 'TASK']) == 1


def test_the_real_tree_is_split(data):
    """After the split: each replacement is listed and saved with an accepted receipt, and the replaced group is gone."""
    current, detail = pylons.state(GAME, pylons.select(data))
    if current == 'unprepared':
        pytest.skip('the split has not run on the real tree yet')
    assert (current, detail) == ('done', 'the groups are retired and the ten pylon objects are listed')
    listed = [o['id'] for o in tomllib.loads((REGION_FOLDER / 'objects.toml').read_text())['objects']]
    saved = json.loads((REGION_FOLDER / 'objects.saved.json').read_text())['objects']
    taken = [t['object'] for t in pylons.select(data)]
    assert len(taken) == 10 and set(taken) <= set(listed) and set(taken) <= set(saved)
