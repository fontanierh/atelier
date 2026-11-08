"""Hippodrome objects: the hippodrome's ten meshes saved as one object per unit (w15-hippodrome/objects.toml; objects.py
plans them as `hippodromes`; the editor step saves them with UV2Migration::MigrateHippodromePieces)."""
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


objects = load('v2_migrate_objects_hippodrome', 'tools/migrate/objects.py')
REGION = 'region/w15-hippodrome'
COMMITTED = ROOT / 'world/regions/w15-hippodrome/objects.toml'
LFS = 'version https://git-lfs.github.com/spec/v1\noid sha256:' + '0' * 64 + '\nsize 1234\n'
COURSE = ['SM_HD_Ground', 'SM_HD_Skirt', 'SM_HD_Track', 'SM_HD_Rails', 'SM_HD_Lane', 'SM_HD_LaneSkirt']
MESHES = COURSE + ['SM_HD_Grandstand', 'SM_HD_JudgesTower', 'SM_HD_FinishPost', 'SM_HD_ToteBoard']
HIPPODROME = {'asset_root': '/Game/Hippodrome', 'origin': [600.0, 525.0, 48.26], 'meshes': [
    {'name': name, 'at': [0.0, 0.0, 0.0], 'yaw': 0.0, 'blocks': True} for name in MESHES]}


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def add_region(game, name, bounds):
    """A region record with its (empty) verification, as records.discover reads them."""
    folder = game / 'world/regions' / name
    write(folder / 'region.toml', f'schema = 1\nid = "region/{name}"\nabout = "{name}"\nbounds_cm = {bounds}\n'
                                  'maps = ["/Game/V2/Maps/Slice"]\n')
    records.write_json(folder / 'actors.verified.json', {'schema': 1, 'kind': 'editor-saved', 'asset': f'region/{name}',
                                                         'engine': 'test', 'files': {}})
    return folder


@pytest.fixture
def game(tmp_path, monkeypatch):
    """The environment's manifest, the hippodrome region with its committed objects.toml, and the hippodrome data."""
    game = tmp_path / 'game'
    add_region(game, 'w00-island', [-1000, -1000, 1000, 1000])
    add_region(game, 'w15-hippodrome', [-1000, -1000, 0, 0])
    write(game / 'world/regions/w15-hippodrome/objects.toml', COMMITTED.read_text())
    write(game / 'unreal/Content/Data/hippodrome/hippodrome.json', json.dumps(HIPPODROME))
    monkeypatch.setattr(objects.save_validate, 'engine_identity', lambda: 'test')
    monkeypatch.setattr(objects.save_validate, 'actor_info', lambda path: (None, None))
    monkeypatch.setenv('ATELIER_AGENT', objects.authority.BOOTSTRAP_WRITER)
    monkeypatch.delenv('ATELIER_CLAIMS_TASK', raising=False)
    return game


def region_of(game):
    return SimpleNamespace(id=REGION, folder=game / 'world/regions/w15-hippodrome')


# --- the committed entries ----------------------------------------------------------------------------------------------

def test_the_committed_hippodrome_objects_load_and_cover_every_mesh_once():
    loaded = objects.load_objects(SimpleNamespace(id=REGION, folder=COMMITTED.parent))
    assert loaded['tag'] == 'hippodrome' and loaded['data'] == 'hippodrome/hippodrome.json'
    assert [(o['id'], o['park']) for o in loaded['objects']] == [
        ('object/hippodrome/course', COURSE),
        ('object/hippodrome/grandstand', ['SM_HD_Grandstand']),
        ('object/hippodrome/judges-tower', ['SM_HD_JudgesTower']),
        ('object/hippodrome/finish-post', ['SM_HD_FinishPost']),
        ('object/hippodrome/tote-board', ['SM_HD_ToteBoard']),
    ]
    held = [name for o in loaded['objects'] for name in o['park']]
    assert sorted(held) == sorted(MESHES)
    assert {o['model'] for o in loaded['objects']} == {'adopted/hippodrome/loose_files'}


def test_the_committed_meshes_are_the_real_hippodrome_file_meshes():
    """Against the real data file; skipped where it is still a Git LFS pointer in this checkout."""
    real = ROOT / 'unreal/Content/Data/hippodrome/hippodrome.json'
    if not real.is_file() or records.is_lfs_pointer(real):
        pytest.skip('the hippodrome data is a Git LFS pointer in this checkout')
    names = {m['name'] for m in json.loads(real.read_text())['meshes']}
    assert names == set(MESHES)


# --- the plan (what the editor step is given) ----------------------------------------------------------------------------

def test_the_plan_carries_each_mesh_with_its_unit(game):
    seen = []

    def editor(plan_file):
        seen.append(plan_file.read_bytes())
        return 'no completion line'   # the plan is what this test reads; the editor step is not run

    with pytest.raises(objects.ObjectError, match='did not report completion'):
        objects.migrate(game, [REGION], 'region/w00-island', None, editor=editor, out=game / 'out', echo=lambda *_: None)
    plan = json.loads(seen[0])
    assert plan['parks'] == []
    assert plan['hippodromes'] == [{
        'region': REGION, 'tag': 'hippodrome', 'data': 'hippodrome/hippodrome.json', 'pieces': MESHES,
        'units': ['course'] * 6 + ['grandstand', 'judges-tower', 'finish-post', 'tote-board']}]
    assert plan['groups'] == [] and plan['splits'] == [] and plan['environment'] == 'region/w00-island'


def test_a_mesh_the_file_does_not_hold_is_refused(game):
    body = COMMITTED.read_text().replace('park = ["SM_HD_Grandstand"]', 'park = ["SM_HD_Nope"]')
    write(game / 'world/regions/w15-hippodrome/objects.toml', body)
    with pytest.raises(objects.ObjectError, match='SM_HD_Nope is no mesh of hippodrome/hippodrome.json'):
        objects.migrate(game, [REGION], 'region/w00-island', None, editor=lambda plan_file: '', out=game / 'out',
                        echo=lambda *_: None)


def test_a_mesh_listed_twice_is_refused(game):
    body = COMMITTED.read_text().replace('park = ["SM_HD_ToteBoard"]', 'park = ["SM_HD_Grandstand"]')
    write(game / 'world/regions/w15-hippodrome/objects.toml', body)
    with pytest.raises(objects.ObjectError, match='park piece is listed twice'):
        objects.load_objects(region_of(game))


def test_an_empty_unit_is_refused(game):
    body = COMMITTED.read_text().replace('park = ["SM_HD_FinishPost"]', 'park = []')
    write(game / 'world/regions/w15-hippodrome/objects.toml', body)
    with pytest.raises(objects.ObjectError, match='park needs a list of mesh names'):
        objects.load_objects(region_of(game))


def test_hippodrome_objects_need_the_environment_manifest(game):
    with pytest.raises(objects.ObjectError, match='--environment is needed'):
        objects.migrate(game, [REGION], None, None, editor=lambda plan_file: '', out=game / 'out', echo=lambda *_: None)


def test_a_hippodrome_file_still_an_lfs_pointer_is_refused(game):
    write(game / 'unreal/Content/Data/hippodrome/hippodrome.json', LFS)
    with pytest.raises(objects.ObjectError, match='LFS pointer'):
        objects.migrate(game, [REGION], 'region/w00-island', None, editor=lambda plan_file: '', out=game / 'out',
                        echo=lambda *_: None)


def test_the_file_shape_picks_the_hippodrome_migration_and_a_park_file_still_plans_as_a_park(game, tmp_path):
    units = objects.load_objects(region_of(game))['objects']
    kind, entry = objects.piece_plan(REGION, 'hippodrome', 'hippodrome/hippodrome.json', units, game)
    assert kind == 'hippodromes' and entry['pieces'] == MESHES
    write(game / 'unreal/Content/Data/megapark/park.json',
          json.dumps({'render': [{'name': 'SM_MP_A', 'origin_cm': [0, 0, 0]}], 'collision': []}))
    park_units = [{'id': 'object/megapark/cell', 'park': ['SM_MP_A'], 'model': 'adopted/megapark/cell', 'about': 'x'}]
    kind, entry = objects.piece_plan('region/w11-megapark', 'megapark', 'megapark/park.json', park_units, game)
    assert kind == 'parks' and entry['pieces'] == ['SM_MP_A'] and entry['is_collision'] == [False]
