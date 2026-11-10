"""The shared group-split lifecycle (tools/migrate/group_split.py) on a small fake tree: one group of two members replaced by
two objects, through prepare, save and retire, each repeating safely, and the receipt gate before retirement."""
import importlib.util
import json
import re
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


group_split = load('v2_migrate_group_split', 'tools/migrate/group_split.py')
objects = load('v2_migrate_objects_group_split', 'tools/migrate/objects.py')


class FakeError(RuntimeError):
    pass


REGION = 'w99-test'
GROUP_ID = 'object/test/posts'
NEW_IDS = ['object/test/post-0', 'object/test/post-1']
MODEL = 'adopted/test/post'
SPLIT = group_split.Split(
    region=REGION, pending='posts-retire.json', group=re.compile(r'object/test/posts$'), group_ids=(GROUP_ID,),
    is_replacement=lambda i: i in NEW_IDS, error=FakeError, label='test posts', noun='post',
    unprepared=lambda groups: 'the posts group is listed', done=lambda wanted: f'{len(wanted)} posts listed')
TAKEN = [{'object': NEW_IDS[0], 'name': 'Post_0'}, {'object': NEW_IDS[1], 'name': 'Post_1'}]
HEAD = '# a test region\nschema = 1\ntag = "test"\ndata = "Data/test/runtime.json"\n'
GROUP = {'id': GROUP_ID, 'route': ['Post_0', 'Post_1'], 'model': MODEL, 'about': 'two posts'}


def block(item):
    return (f'[[objects]]\nid = "{item["id"]}"\nroute = {json.dumps(item["route"])}\nmodel = "{item["model"]}"\n'
            f'about = "{item["about"]}"\n')


def render(text):
    """objects.toml with the group replaced by one object per member."""
    return HEAD + '\n' + '\n'.join(block({'id': t['object'], 'route': [t['name']], 'model': MODEL, 'about': t['name']}) for t in TAKEN)


def actor(game, name):
    path = game / f'unreal/Content/__ExternalActors__/T/{name}.uasset'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(name.encode())
    return f'/Game/__ExternalActors__/T/{name}', path


def fake_tree(game):
    region = game / 'world/regions' / REGION
    region.mkdir(parents=True)
    (region / 'objects.toml').write_text(HEAD + '\n' + block(GROUP))
    package, _ = actor(game, 'GROUP')
    folder = game / 'assets' / GROUP_ID
    folder.mkdir(parents=True)
    item = dict(GROUP, models=[MODEL], groups=[])
    (folder / 'asset.toml').write_text(objects.record_text(item, f'region/{REGION}', package))
    saved = {'schema': 1, 'objects': {GROUP_ID: group_split.saved_definition(GROUP)}}
    (region / 'objects.saved.json').write_text(json.dumps(saved, indent=2, sort_keys=True) + '\n')


def save(game):
    """What objects.py's save leaves for each replacement: record, actor package, verified.json and saved entry."""
    region = game / 'world/regions' / REGION
    listed = objects.load_objects(SimpleNamespace(id=f'region/{REGION}', folder=region))['objects']
    saved = json.loads((region / 'objects.saved.json').read_text())
    for index, pid in enumerate(NEW_IDS):
        item = next(i for i in listed if i['id'] == pid)
        package, path = actor(game, f'POST{index}')
        folder = game / 'assets' / pid
        folder.mkdir(parents=True)
        (folder / 'asset.toml').write_text(objects.record_text(item, f'region/{REGION}', package))
        (folder / 'verified.json').write_text(json.dumps({
            'schema': 1, 'kind': 'editor-saved', 'asset': pid, 'engine': 'test', 'dependencies': {MODEL: 'a' * 64},
            'files': {path.relative_to(game).as_posix(): records.sha256_file(path)}}, indent=2) + '\n')
        saved['objects'][pid] = group_split.saved_definition(item)
    (region / 'objects.saved.json').write_text(json.dumps(saved, indent=2, sort_keys=True) + '\n')


def tree_bytes(game):
    return {p.relative_to(game).as_posix(): p.read_bytes() for p in sorted(game.rglob('*'))
            if p.is_file() and 'Saved' not in p.parts}


@pytest.fixture
def claimed(monkeypatch):
    calls = []

    def fake_authorize(paths, claim, what, *, scopes=(), repo=None):
        calls.append((claim, what, tuple(sorted(scopes))))
        if claim != 'TASK':
            raise group_split.authority.Unauthorized('no claim')

    monkeypatch.setattr(group_split.authority, 'authorize', fake_authorize)
    return calls


def test_prepare_save_retire_each_repeat_safely(tmp_path, claimed):
    quiet, no_lock = (lambda *_: None), (lambda game, rels: [])
    fake_tree(tmp_path)
    region = tmp_path / 'world/regions' / REGION
    assert group_split.state(SPLIT, tmp_path, TAKEN) == ('unprepared', 'the posts group is listed')

    assert group_split.prepare(SPLIT, tmp_path, TAKEN, 'TASK', render, lockable=no_lock, echo=quiet) == 'prepared'
    assert [i['id'] for i in tomllib.loads((region / 'objects.toml').read_text())['objects']] == NEW_IDS
    assert json.loads((region / 'posts-retire.json').read_text())['replacements'] == NEW_IDS
    before = tree_bytes(tmp_path)
    assert group_split.prepare(SPLIT, tmp_path, TAKEN, 'TASK', render, lockable=no_lock, echo=quiet) == 'prepared'
    assert tree_bytes(tmp_path) == before

    # No replacement has a receipt yet: retire refuses and changes nothing.
    with pytest.raises(FakeError, match='retire refused: the post objects are prepared'):
        group_split.retire(SPLIT, tmp_path, TAKEN, 'TASK', lockable=no_lock, echo=quiet)
    assert tree_bytes(tmp_path) == before

    save(tmp_path)
    assert group_split.state(SPLIT, tmp_path, TAKEN)[0] == 'saved'
    assert group_split.retire(SPLIT, tmp_path, TAKEN, 'TASK', lockable=no_lock, echo=quiet) == 'done'
    assert not [p for p in (tmp_path / 'assets' / GROUP_ID).rglob('*') if p.is_file()] and not (tmp_path / 'unreal/Content/__ExternalActors__/T/GROUP.uasset').exists()
    assert sorted(json.loads((region / 'objects.saved.json').read_text())['objects']) == NEW_IDS
    assert not (region / 'posts-retire.json').exists()
    assert group_split.state(SPLIT, tmp_path, TAKEN) == ('done', '2 posts listed')
    after = tree_bytes(tmp_path)
    assert group_split.retire(SPLIT, tmp_path, TAKEN, 'TASK', lockable=no_lock, echo=quiet) == 'done'
    assert tree_bytes(tmp_path) == after
    assert {(what, scopes) for _, what, scopes in claimed} == {
        ('test posts prepare', ('region/w00-island', f'region/{REGION}')),
        ('test posts retire', ('region/w00-island', f'region/{REGION}'))}


def test_a_changed_actor_package_is_no_receipt(tmp_path, claimed):
    fake_tree(tmp_path)
    group_split.prepare(SPLIT, tmp_path, TAKEN, 'TASK', render, lockable=lambda g, r: [], echo=lambda *_: None)
    save(tmp_path)
    (tmp_path / 'unreal/Content/__ExternalActors__/T/POST1.uasset').write_bytes(b'edited after the save')
    assert group_split.state(SPLIT, tmp_path, TAKEN) == (
        'prepared', '1 replacement(s) without an accepted receipt, e.g. object/test/post-1')


def test_a_claim_that_does_not_hold_the_step_refuses_before_any_write(tmp_path, claimed):
    fake_tree(tmp_path)
    before = tree_bytes(tmp_path)
    with pytest.raises(FakeError, match='no claim'):
        group_split.prepare(SPLIT, tmp_path, TAKEN, 'OTHER', render, lockable=lambda g, r: [], echo=lambda *_: None)
    assert tree_bytes(tmp_path) == before
