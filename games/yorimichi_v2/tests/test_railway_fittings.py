"""The W20 railway's track-fittings group as one object per fitting kind (tools/migrate/railway_fittings.py): the selection is
deterministic and in route order; every taken entry is an instanced group of track.json with key "" and its full count; no
group is listed twice; the other objects (track, station, bridge, tunnels, the chunks) are unchanged; a partly taken group
is refused; and the steps (prepare, save, retire) each repeat safely in a fake copy of the tree."""
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


fittings = load('v2_migrate_railway_fittings', 'tools/migrate/railway_fittings.py')
objects = load('v2_migrate_objects_fittings', 'tools/migrate/objects.py')
GAME = ROOT
REGION_FOLDER = ROOT / 'world/regions/w20-railway'
DATA = ROOT / 'unreal/Content/Data/belmonte_track/track.json'
KIND_IDS = ['object/railway/buffer-stops', 'object/railway/stop-boards', 'object/railway/turnouts',
            'object/railway/tunnel-portals']


@pytest.fixture(scope='module')
def data():
    if not DATA.is_file() or records.is_lfs_pointer(DATA):
        pytest.skip('belmonte_track/track.json is a Git LFS pointer in this checkout')
    return json.loads(DATA.read_text())


@pytest.fixture(scope='module')
def committed():
    return (REGION_FOLDER / 'objects.toml').read_text()


def blocks_by_id(text):
    return {o['id']: o for o in tomllib.loads(text)['objects']}


# --- the selection and the rendered objects.toml (read only) ---------------------------------------------------------------

def test_selection_is_deterministic_and_in_the_group_route_order(data):
    first = fittings.select(data)
    assert first == fittings.select(data)
    assert [t['name'] for t in first] == fittings.GROUP_ROUTE
    assert [t['object'] for t in first] == KIND_IDS
    assert sum(t['count'] for t in first) == 12


def test_every_key_exists_in_the_runtime_file(data):
    groups = {f'{g["mesh"].rsplit("/", 1)[-1].split(".")[0]}#{g["key"]}': g for g in data['instances']}
    for t in fittings.select(data):
        assert t['name'] in groups, t['name']
        assert len(groups[t['name']]['instances']) == t['count']
        assert groups[t['name']]['key'] == ''


def test_each_model_names_the_existing_record_that_owns_the_mesh(data):
    for t in fittings.select(data):
        assert t['model'] == 'adopted/belmontetrack/track-small'
        assert (GAME / 'assets' / t['model'] / 'asset.toml').is_file()


def test_rendered_objects_load_and_list_each_group_once(data, committed, tmp_path):
    (tmp_path / 'objects.toml').write_text(fittings.render(committed, data))
    loaded = objects.load_objects(SimpleNamespace(id='region/w20-railway', folder=tmp_path))
    routes = [name for item in loaded['objects'] for name in item['route']]
    assert len(routes) == len(set(routes))
    assert [r for r in routes if r in fittings.GROUP_ROUTE] == fittings.GROUP_ROUTE
    groups = {f'{g["mesh"].rsplit("/", 1)[-1].split(".")[0]}#{g["key"]}' for g in data['instances']}
    pieces = {p['name'] for p in data['pieces']}
    assert set(routes) <= groups | pieces
    assert [i['id'] for i in loaded['objects'] if i['id'] in KIND_IDS] == KIND_IDS
    assert 'object/railway/track-fittings' not in {i['id'] for i in loaded['objects']}


def test_the_track_station_and_route_objects_are_unchanged(data, committed):
    before = {k: v for k, v in blocks_by_id(committed).items() if k != fittings.GROUP_ID}
    after = {k: v for k, v in blocks_by_id(fittings.render(committed, data)).items() if k not in KIND_IDS}
    assert before == after
    assert len(before) == 12
    assert 'object/railway/chunks-0-19' in after and 'object/railway/station-belmonte' in after


def test_the_header_and_data_line_are_unchanged(data, committed):
    rendered = fittings.render(committed, data)
    assert rendered.split('[[objects]]', 1)[0].rstrip() == committed.split('[[objects]]', 1)[0].rstrip()
    assert 'data = "belmonte_track/track.json"' in rendered


def test_a_partly_taken_group_is_refused(data, committed):
    partial = committed.replace(', "SM_TK_Portal#"]', ']')
    assert partial != committed
    with pytest.raises(fittings.FittingsError, match='is not the four-entry group'):
        fittings.render(partial, data)


def test_a_rerun_on_its_own_output_is_refused(data, committed):
    text = fittings.render(committed, data)
    with pytest.raises(fittings.FittingsError, match='already has an object'):
        fittings.render(text, data)


def test_a_missing_runtime_count_is_refused(data):
    changed = json.loads(json.dumps(data))
    for g in changed['instances']:
        if g['mesh'].endswith('SM_TK_Portal') and g['key'] == '':
            g['instances'] = g['instances'][:-1]
    with pytest.raises(fittings.FittingsError, match='holds 5 fittings, 6 expected'):
        fittings.select(changed)


def test_check_writes_nothing_and_reports_the_state(capsys):
    files = [REGION_FOLDER / 'objects.toml', REGION_FOLDER / 'objects.saved.json']
    before = [p.read_bytes() for p in files]
    assert fittings.main(['--check']) == 0
    assert 'state: unprepared' in capsys.readouterr().out
    assert [p.read_bytes() for p in files] == before


def test_the_claim_paths_name_every_file_and_both_scopes(data):
    plan = fittings.claim_paths(GAME, fittings.select(data))
    paths = set(plan['paths'])
    assert 'games/yorimichi_v2/world/regions/w20-railway/objects.toml' in paths
    assert 'games/yorimichi_v2/world/regions/w20-railway/objects.saved.json' in paths
    assert 'games/yorimichi_v2/world/regions/w20-railway/fittings-retire.json' in paths
    assert 'games/yorimichi_v2/assets/object/railway/buffer-stops/asset.toml' in paths
    assert 'games/yorimichi_v2/assets/object/railway/tunnel-portals/verified.json' in paths
    assert 'games/yorimichi_v2/assets/object/railway/track-fittings/asset.toml' in paths
    assert f'games/yorimichi_v2/{objects.MANIFEST["region/w00-island"]}' in paths
    assert plan['scopes'] == ['region/w00-island', 'region/w20-railway']


def test_the_command_line_dispatches_each_step(monkeypatch):
    """--retire takes --claim (step 3); --claim alone prepares (step 1); --check and --paths take none."""
    calls = []
    monkeypatch.setattr(fittings, 'runtime', lambda game: {})
    monkeypatch.setattr(fittings, 'select', lambda data: [])
    monkeypatch.setattr(fittings, 'retire', lambda game, taken, claim: calls.append(('retire', claim)))
    monkeypatch.setattr(fittings, 'prepare', lambda game, taken, claim: calls.append(('prepare', claim)))
    assert fittings.main(['--retire', '--claim', 'TASK']) == 0
    assert fittings.main(['--claim', 'TASK']) == 0
    assert calls == [('retire', 'TASK'), ('prepare', 'TASK')]
    assert fittings.main(['--retire']) == 1
    assert fittings.main(['--check', '--claim', 'TASK']) == 1


# --- the lifecycle in a fake copy of the tree ------------------------------------------------------------------------------

def copy_tree(tmp: Path, data_bytes: bytes) -> None:
    """The parts of the W20 tree the steps read and write: the region's lists, the group's record and actor package, the
    runtime file, and a placeholder record for the track-small model."""
    region = tmp / 'world/regions/w20-railway'
    region.mkdir(parents=True)
    for name in ('objects.toml', 'objects.saved.json'):
        shutil.copy2(REGION_FOLDER / name, region / name)
    (tmp / 'unreal/Content/Data/belmonte_track').mkdir(parents=True)
    (tmp / 'unreal/Content/Data/belmonte_track/track.json').write_bytes(data_bytes)
    src = GAME / 'assets/object/railway/track-fittings'
    dst = tmp / 'assets/object/railway/track-fittings'
    shutil.copytree(src, dst)
    for output in records.load_asset(dst / 'asset.toml').outputs:
        for path in records.package_files(GAME, output.package):
            if path.is_file():
                target = tmp / path.relative_to(GAME)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
    model = tmp / 'assets' / fittings.MODEL
    model.mkdir(parents=True)
    (model / 'asset.toml').write_text('schema = 1\n')


def tree_bytes(tmp: Path) -> dict:
    return {p.relative_to(tmp).as_posix(): p.read_bytes() for p in sorted(tmp.rglob('*')) if p.is_file()}


def write_receipts(tmp: Path, taken: list[dict]) -> None:
    """What objects.py's save leaves: each replacement's record, its actor package, its verified.json and its saved entry."""
    region = tmp / 'world/regions/w20-railway'
    listed = objects.load_objects(SimpleNamespace(id='region/w20-railway', folder=region))['objects']
    saved = json.loads((region / 'objects.saved.json').read_text())
    for index, t in enumerate(taken):
        item = next(i for i in listed if i['id'] == t['object'])
        package = f'/Game/__ExternalActors__/V2/Maps/Slice/T/E/FIT{index:03d}'
        actor = tmp / 'unreal/Content/__ExternalActors__/V2/Maps/Slice/T/E' / f'FIT{index:03d}.uasset'
        actor.parent.mkdir(parents=True, exist_ok=True)
        actor.write_bytes(b'fitting %d' % index)
        folder = tmp / 'assets' / t['object']
        folder.mkdir(parents=True)
        (folder / 'asset.toml').write_text(objects.record_text(item, 'region/w20-railway', package))
        rel = actor.relative_to(tmp).as_posix()
        (folder / 'verified.json').write_text(json.dumps({
            'schema': 1, 'kind': 'editor-saved', 'asset': t['object'], 'engine': 'test',
            'dependencies': {t['model']: 'a' * 64}, 'files': {rel: records.sha256_file(actor)}}, indent=2) + '\n')
        saved['objects'][t['object']] = fittings.saved_definition(item)
    (region / 'objects.saved.json').write_text(json.dumps(saved, indent=2, sort_keys=True) + '\n')


def test_prepare_save_retire_each_repeat_safely(data, tmp_path, monkeypatch):
    calls = []

    def fake_authorize(paths, claim, what, *, scopes=(), repo=None):
        calls.append((claim, tuple(sorted(scopes))))
        if claim != 'TASK':
            raise fittings.authority.Unauthorized('no claim')

    monkeypatch.setattr(fittings.authority, 'authorize', fake_authorize)
    copy_tree(tmp_path, DATA.read_bytes())
    taken = fittings.select(data)
    no_lock = lambda game, rels: []   # noqa: E731  (git-lfs lock attributes are a claim-time concern, not this test's)
    region = tmp_path / 'world/regions/w20-railway'
    group_record = tmp_path / 'assets/object/railway/track-fittings/asset.toml'
    group_packages = [p.relative_to(GAME) for output in records.load_asset(
        GAME / 'assets/object/railway/track-fittings/asset.toml').outputs
        for p in records.package_files(GAME, output.package)]

    assert fittings.state(tmp_path, taken)[0] == 'unprepared'
    assert fittings.prepare(tmp_path, taken, 'TASK', lockable=no_lock, echo=lambda *_: None) == 'prepared'
    listed = tomllib.loads((region / 'objects.toml').read_text())['objects']
    assert [i['id'] for i in listed if i['id'] in KIND_IDS] == KIND_IDS
    assert not [i for i in listed if fittings.GROUP.match(i['id'])]
    assert group_record.is_file()
    assert fittings.GROUP_ID in json.loads((region / 'objects.saved.json').read_text())['objects']
    pending = json.loads((region / 'fittings-retire.json').read_text())
    assert pending['groups'].keys() == {fittings.GROUP_ID}
    assert pending['replacements'] == sorted(KIND_IDS)

    # A rerun of prepare is a no-op: nothing is written, not even the pending file's bytes.
    before = tree_bytes(tmp_path)
    assert fittings.prepare(tmp_path, taken, 'TASK', lockable=no_lock, echo=lambda *_: None) == 'prepared'
    assert tree_bytes(tmp_path) == before

    # The save has not happened: no replacement has a receipt, so retire refuses and changes nothing.
    with pytest.raises(fittings.FittingsError, match='retire refused: the fitting objects are prepared'):
        fittings.retire(tmp_path, taken, 'TASK', lockable=no_lock, echo=lambda *_: None)
    assert tree_bytes(tmp_path) == before

    # The save completes: receipts exist, so retire completes and a rerun is a no-op.
    write_receipts(tmp_path, taken)
    assert fittings.state(tmp_path, taken)[0] == 'saved'
    assert fittings.retire(tmp_path, taken, 'TASK', lockable=no_lock, echo=lambda *_: None) == 'done'
    assert not group_record.exists()
    assert not (tmp_path / 'assets/object/railway/track-fittings/verified.json').exists()
    assert all(not (tmp_path / rel).exists() for rel in group_packages)
    saved = json.loads((region / 'objects.saved.json').read_text())['objects']
    assert fittings.GROUP_ID not in saved
    assert {t['object'] for t in taken} <= set(saved)
    assert not (region / 'fittings-retire.json').exists()
    assert (tmp_path / 'assets/object/railway/buffer-stops/asset.toml').is_file()
    after = tree_bytes(tmp_path)
    assert fittings.retire(tmp_path, taken, 'TASK', lockable=no_lock, echo=lambda *_: None) == 'done'
    assert tree_bytes(tmp_path) == after

    # Each write was authorized under the W20 and W00 scopes.
    assert calls and all(scopes == ('region/w00-island', 'region/w20-railway') for _, scopes in calls)


def test_a_claim_that_does_not_hold_the_steps_refuses_before_any_write(data, tmp_path, monkeypatch):
    def refuse(paths, claim, what, *, scopes=(), repo=None):
        raise fittings.authority.Unauthorized('no claim')

    monkeypatch.setattr(fittings.authority, 'authorize', refuse)
    copy_tree(tmp_path, DATA.read_bytes())
    before = tree_bytes(tmp_path)
    with pytest.raises(fittings.FittingsError, match='no claim'):
        fittings.prepare(tmp_path, fittings.select(data), 'OTHER', lockable=lambda g, r: [], echo=lambda *_: None)
    assert tree_bytes(tmp_path) == before
