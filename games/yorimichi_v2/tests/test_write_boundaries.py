"""Every build step that writes packages authorizes at its own boundary and checks what it wrote."""
import importlib.util
import io
import json
import os
import shutil
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from claims_fake import FakeClaims  # noqa: E402


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


recipe = load('v2_build_recipe', 'build.py')
authority = recipe._authority()


@pytest.fixture
def writer(monkeypatch):
    monkeypatch.setenv('ATELIER_AGENT', authority.BOOTSTRAP_WRITER)
    monkeypatch.delenv('ATELIER_CLAIMS_TASK', raising=False)
    for name in ('V2_EDITOR_CLAIM', 'V2_EDITOR_PATHS', 'V2_EDITOR_SCOPES', 'V2_SAVE_ALLOW', 'V2_SAVE_DENY'):
        monkeypatch.delenv(name, raising=False)
    yield
    for name in ('V2_SAVE_ALLOW', 'V2_SAVE_DENY'):   # set by the code under test, not by monkeypatch
        os.environ.pop(name, None)


def bench_record(game):
    folder = game / 'assets/props/bench'
    folder.mkdir(parents=True)
    (folder / 'src').mkdir()
    (folder / 'src/bench.glb').write_bytes(b'mesh')
    (folder / 'asset.toml').write_text(
        'schema = 1\nid = "prop/bench"\nkind = "static-mesh"\nauthority = "generated"\n'
        'owner = "region/w04-skatepark"\nlicense = "original"\n'
        '[[sources]]\npath = "src/bench.glb"\nsha256 = "' + '0' * 64 + '"\n'
        '[recipe]\nimporter = "static-mesh"\nversion = 1\n[[outputs]]\npackage = "/Game/Props/SM_Bench"\n')


def test_a_directly_selected_import_rechecks_its_plan(tmp_path, monkeypatch, writer):
    game = tmp_path / 'game'
    bench_record(game)
    monkeypatch.setattr(recipe, 'GAME', game)
    plan = tmp_path / 'plan.json'
    good = {'asset': 'prop/bench', 'importer': 'static-mesh', 'version': 1, 'claim': None, 'packages': ['/Game/Props/SM_Bench'],
            'write_paths': []}
    plan.write_text(json.dumps(good))
    monkeypatch.setenv('V2_IMPORT_PLAN', str(plan))
    recipe._authorize_import(None, io.StringIO())
    allowed = Path(os.environ['V2_SAVE_ALLOW']).read_text().split()
    assert any(a.endswith('/unreal/Content/Props/SM_Bench.uasset') for a in allowed)
    plan.write_text(json.dumps({**good, 'packages': ['/Game/Other/SM_Other']}))   # another record's package
    with pytest.raises(RuntimeError, match='does not match its record'):
        recipe._authorize_import(None, io.StringIO())
    fake = FakeClaims(scopes=['asset/prop'], covers=False)
    monkeypatch.setattr(authority.subprocess, 'run', fake)
    plan.write_text(json.dumps({**good, 'claim': 'T3'}))
    with pytest.raises(authority.Unauthorized, match='does not exactly cover'):
        recipe._authorize_import(None, io.StringIO())
    assert any(p.endswith('/unreal/Content/Props/SM_Bench.uasset') for p in fake.checks[0])   # derived, not trusted
    fake.scopes, fake.covers = ['asset/prop/other'], True
    with pytest.raises(authority.Unauthorized, match='no active scope covering asset/prop/bench or region/w04-skatepark'):
        recipe._authorize_import(None, io.StringIO())
    fake.scopes = ['region/w04-skatepark']   # the record's owner scope covers it, as in the change-set report
    recipe._authorize_import(None, io.StringIO())
    monkeypatch.setenv('ATELIER_AGENT', 'someone-else')
    plan.write_text(json.dumps(good))
    with pytest.raises(authority.Unauthorized, match='not the bootstrap writer'):
        recipe._authorize_import(None, io.StringIO())


def settle(game):
    """Date every file a minute back: a record written just now is never kept (authority.SETTLED_NS)."""
    past = time.time_ns() - 60 * 10**9
    for path in game.rglob('*'):
        os.utime(path, ns=(past, past))


@pytest.fixture
def batch(tmp_path, monkeypatch, writer):
    """A batch of import jobs on the bench record, under claim T3 holding its owner scope, counting discoveries."""
    game = tmp_path / 'game'
    bench_record(game)
    settle(game)
    monkeypatch.setattr(recipe, 'GAME', game)
    monkeypatch.setattr(authority, '_RECORDS', [])
    import records
    reads = []
    real = records.discover
    monkeypatch.setattr(records, 'discover', lambda g: reads.append(g) or real(g))
    fake = FakeClaims(scopes=['region/w04-skatepark'])
    monkeypatch.setattr(authority.subprocess, 'run', fake)
    plan = tmp_path / 'plan.json'
    plan.write_text(json.dumps({'asset': 'prop/bench', 'importer': 'static-mesh', 'version': 1, 'claim': 'T3',
                                'packages': ['/Game/Props/SM_Bench'], 'write_paths': []}))
    monkeypatch.setenv('V2_IMPORT_PLAN', str(plan))
    return type('Batch', (), {'game': game, 'reads': reads, 'claims': fake, 'allow': tmp_path / 'save-allow.txt',
                              'job': staticmethod(lambda: recipe._authorize_import(None, io.StringIO()))})


def test_a_batch_reads_the_records_once_and_still_checks_every_job(batch):
    batch.job()
    batch.allow.unlink()
    batch.job()
    assert len(batch.reads) == 1                        # the second job reuses the first job's reading
    assert len(batch.claims.checks) == 2 and batch.allow.is_file()   # the live claim check and save list: every job


def test_a_record_changed_between_jobs_is_read_again_and_enforced(batch):
    batch.job()
    record = batch.game / 'assets/props/bench/asset.toml'
    text = record.read_text()
    record.write_text(text.replace('region/w04-skatepark', 'region/w05-skatepark'))   # same size, new owner
    with pytest.raises(authority.Unauthorized, match='no active scope covering asset/prop/bench or region/w05-skatepark'):
        batch.job()
    assert len(batch.reads) == 2
    record.write_text(text)
    batch.job()
    batch.job()
    assert len(batch.reads) == 4                        # a just-written record is read again, never kept


def test_a_destination_newly_owned_by_another_record_is_refused(batch):
    batch.job()
    other = batch.game / 'assets/props/thief'
    other.mkdir()
    (other / 'asset.toml').write_text('schema = 1\nid = "prop/thief"\nkind = "static-mesh"\nauthority = "editor"\n'
                                      'owner = "region/w09-docks"\n[[outputs]]\npackage = "/Game/Props/SM_Bench"\n')
    with pytest.raises(RuntimeError, match='destination is owned by .*asset/prop/thief'):
        batch.job()
    shutil.rmtree(other)
    batch.job()
    region = batch.game / 'world/regions/w09-docks'
    region.mkdir(parents=True)
    (region / 'region.toml').write_text('schema = 1\nid = "region/w09-docks"\nbounds_cm = [0, 0, 1, 1]\nmaps = []\n')
    (region / 'actors.verified.json').write_text(json.dumps({
        'schema': 1, 'kind': 'editor-saved', 'engine': 'test',
        'files': {'unreal/Content/Props/SM_Bench.uexp': '0' * 64}}))   # an actor package's companions are its region's
    with pytest.raises(RuntimeError, match=r"destination is owned by \['region/w09-docks'\]"):
        batch.job()


def test_migration_is_bootstrap_only(monkeypatch, writer):
    recipe._authorize_migration(None, io.StringIO())
    monkeypatch.setenv('ATELIER_AGENT', 'someone-else')
    with pytest.raises(authority.Unauthorized):
        recipe._authorize_migration(None, io.StringIO())


def test_a_claimed_editor_script_must_stay_inside_its_paths(tmp_path, monkeypatch, writer):
    game = tmp_path / 'game'
    (game / 'unreal/Content/V2').mkdir(parents=True)
    monkeypatch.setattr(recipe, 'GAME', game)
    monkeypatch.setattr(authority.subprocess, 'run', FakeClaims(scopes=['region/w01-start']))
    monkeypatch.setenv('V2_EDITOR_CLAIM', 'T9')
    monkeypatch.setenv('V2_EDITOR_PATHS', 'games/yorimichi_v2/unreal/Content/V2/A.uasset')
    ctx = type('Ctx', (), {'out': tmp_path / 'out'})()
    with pytest.raises(RuntimeError, match='need V2_EDITOR_SCOPES'):
        recipe._authorize_editor(ctx, io.StringIO())
    monkeypatch.setenv('V2_EDITOR_SCOPES', 'region/w01-start')
    recipe._authorize_editor(ctx, io.StringIO())
    allowed = Path(os.environ['V2_SAVE_ALLOW']).read_text().split()
    for ext in ('.uasset', '.uexp', '.ubulk'):   # a package's companions are admitted with it
        assert any(a.endswith(f'games/yorimichi_v2/unreal/Content/V2/A{ext}') for a in allowed)
    (game / 'unreal/Content/V2/A.uasset').write_bytes(b'a')
    (game / 'unreal/Content/V2/A.uexp').write_bytes(b'a')
    log = io.StringIO()
    recipe._check_editor_writes(None, log)
    assert 'wrote games/yorimichi_v2/unreal/Content/V2/A.uasset' in log.getvalue()
    recipe._authorize_editor(ctx, io.StringIO())
    (game / 'unreal/Content/V2/B.uasset').write_bytes(b'b')
    with pytest.raises(RuntimeError, match='outside its claimed paths: games/yorimichi_v2/unreal/Content/V2/B.uasset'):
        recipe._check_editor_writes(None, io.StringIO())


def test_a_read_only_editor_script_needs_no_claim_and_may_save_nothing(tmp_path, monkeypatch):
    game = tmp_path / 'game'
    (game / 'unreal/Content/V2').mkdir(parents=True)
    monkeypatch.setattr(recipe, 'GAME', game)
    monkeypatch.setenv('V2_EDITOR_READ_ONLY', '1')
    monkeypatch.delenv('V2_EDITOR_CLAIM', raising=False)
    monkeypatch.delenv('V2_EDITOR_PATHS', raising=False)
    ctx = type('Ctx', (), {'out': tmp_path / 'out'})()
    log = io.StringIO()
    recipe._authorize_editor(ctx, log)                               # D04 closed: no claim, still admitted
    assert 'read-only' in log.getvalue()
    assert Path(os.environ['V2_SAVE_ALLOW']).read_text() == ''      # the editor's save guard refuses every save
    recipe._check_editor_writes(None, io.StringIO())
    recipe._authorize_editor(ctx, io.StringIO())
    (game / 'unreal/Content/V2/A.uasset').write_bytes(b'a')
    with pytest.raises(RuntimeError, match='read-only editor script changed files'):
        recipe._check_editor_writes(None, io.StringIO())
    monkeypatch.setenv('V2_EDITOR_CLAIM', 'T9')
    with pytest.raises(RuntimeError, match='without V2_EDITOR_CLAIM'):
        recipe._authorize_editor(ctx, io.StringIO())


def test_a_claimed_editor_script_must_declare_its_paths(monkeypatch, writer):
    monkeypatch.setenv('V2_EDITOR_CLAIM', 'T9')
    with pytest.raises(RuntimeError, match='needs V2_EDITOR_PATHS'):
        recipe._authorize_editor(None, io.StringIO())


def test_a_claim_must_name_its_paths(writer):
    with pytest.raises(authority.Unauthorized, match='must name the paths'):
        authority.authorize([], 'T1', 'probe')


def test_a_held_scope_covers_its_descendants_only():
    assert authority.covered('asset/prop/bench', ['asset/prop'])
    assert authority.covered('region/w01-start', ['region/W01-START'])
    assert not authority.covered('asset/prop/bench', ['asset/prop/bench-02', 'region/prop'])


def test_the_editor_route_never_writes_generated_packages(tmp_path, monkeypatch, writer):
    game = tmp_path / 'game'
    bench_record(game)
    (game / 'unreal/Content/Props').mkdir(parents=True)
    monkeypatch.setattr(recipe, 'GAME', game)
    ctx = type('Ctx', (), {'out': tmp_path / 'out'})()
    monkeypatch.setenv('V2_EDITOR_SCRIPT', str(ROOT / 'unreal/Scripts/import_asset.py'))
    with pytest.raises(RuntimeError, match='only through its import'):
        recipe._authorize_editor(ctx, io.StringIO())
    monkeypatch.setenv('V2_EDITOR_SCRIPT', str(ROOT / 'unreal/Scripts/open_close.py'))
    monkeypatch.setattr(authority.subprocess, 'run', FakeClaims(scopes=['asset/prop/bench']))
    monkeypatch.setenv('V2_EDITOR_CLAIM', 'T9')
    monkeypatch.setenv('V2_EDITOR_PATHS', 'games/yorimichi_v2/unreal/Content/Props/SM_Bench.uasset')
    with pytest.raises(RuntimeError, match='written only by their importer'):
        recipe._authorize_editor(ctx, io.StringIO())
    for name in ('V2_EDITOR_CLAIM', 'V2_EDITOR_PATHS'):
        monkeypatch.delenv(name)
    recipe._authorize_editor(ctx, io.StringIO())           # the bootstrap writer: refused at the save itself
    denied = Path(os.environ['V2_SAVE_DENY']).read_text().split()
    assert any(d.endswith('/unreal/Content/Props/SM_Bench.uasset') for d in denied)
    (game / 'unreal/Content/Props/SM_Bench.uasset').write_bytes(b'resaved in the editor')
    with pytest.raises(RuntimeError, match='wrote generated packages'):
        recipe._check_editor_writes(None, io.StringIO())
