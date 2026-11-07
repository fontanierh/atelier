"""DECISIONS D04's committed switch, and claimed regional migration that creates actor packages after it closes."""
import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'content'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import records  # noqa: E402
from claims_fake import ClaimService  # noqa: E402


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


recipe = load('v2_d04_recipe', 'build.py')
authority = recipe._authority()
importer = load('v2_d04_import', 'tools/import/run.py')
sv = load('v2_d04_save_validate', 'tools/content/save_validate.py')
adopt = load('v2_d04_adopt', 'tools/migrate/adopt.py')
migration = load('v2_d04_migrate', 'tools/migrate/run.py')

ENGINE = '5.8.2-test'
SLICE = 'unreal/Content/__ExternalActors__/V2/Maps/Slice'
OTHER = 'unreal/Content/__ExternalActors__/V2/Maps/Other'
OLD, NEW, SKY = f'{SLICE}/0/AA/OLD.uasset', f'{SLICE}/1/BB/KIOSK.uasset', f'{SLICE}/2/CC/SKY.uasset'
FAR = f'{OTHER}/0/DD/FAR.uasset'
FAR_NEW = f'{SLICE}/3/EE/KIOSK2.uasset'
ENV = ('ATELIER_AGENT', 'ATELIER_CLAIMS_TASK', 'ATELIER_CLAIMS_ACTOR', 'V2_MIGRATE_PLAN', 'V2_EDITOR_CLAIM',
       'V2_EDITOR_PATHS', 'V2_EDITOR_SCOPES', 'V2_EDITOR_SCRIPT', 'V2_SAVE_ALLOW', 'V2_SAVE_DENY')


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())


def governance(tmp_path, closed):
    path = tmp_path / 'governance.toml'
    path.write_text(f'schema = 1\n[d04]\nwriter = "{authority.BOOTSTRAP_WRITER}"\nclosed = {str(closed).lower()}\n')
    return path


def repo_path(rel):
    return f'games/yorimichi_v2/{rel}'


@pytest.fixture
def env(monkeypatch):
    saved = {name: os.environ.pop(name, None) for name in ENV}
    yield monkeypatch
    for name, value in saved.items():
        os.environ.pop(name, None)
        if value is not None:
            os.environ[name] = value


@pytest.fixture
def game(tmp_path, env):
    """Regions w00 (environment) and w01 on the Slice map, w09 on another map; w01 and w09 own one actor each."""
    game = tmp_path / 'game'
    for name, bounds, map_ in (('w00', [-1000, -1000, 1000, 1000], 'Slice'), ('w01', [0, 0, 100, 100], 'Slice'),
                               ('w09', [5000, 0, 6000, 100], 'Other')):
        write(game / f'world/regions/{name}/region.toml',
              f'schema = 1\nid = "region/{name}"\nbounds_cm = {json.dumps(bounds)}\nmaps = ["/Game/V2/Maps/{map_}"]\n')
    for region, rel in (('w01', OLD), ('w09', FAR)):
        write(game / rel, f'region/{region}:Old:whole:id0')
        records.write_json(game / f'world/regions/{region}/actors.verified.json', {
            'schema': 1, 'kind': 'editor-saved', 'asset': f'region/{region}', 'engine': ENGINE,
            'files': {rel: records.sha256_file(game / rel)}})
    write(game / 'unreal/Content/V2/Maps/Slice.umap', 'map')
    env.setattr(recipe, 'GAME', game)
    env.setattr(migration.save_validate, 'engine_identity', lambda: ENGINE)
    env.setattr(migration.save_validate, 'actor_info', lambda path: (path.read_text(), None))
    return game


@pytest.fixture
def claims(env):
    service = ClaimService()
    env.setattr(subprocess, 'run', service)
    return service


def editor(game, tmp_path, files, seen=None, after_save=lambda: None):
    """The guarded migrate.map step with the editor's saves stubbed by plain writes."""
    ctx = type('Ctx', (), {'out': tmp_path / 'out'})()

    def run(plan_file):
        os.environ['V2_MIGRATE_PLAN'] = str(plan_file)
        recipe._authorize_migration(ctx, io.StringIO())
        if seen is not None and os.environ.get('V2_SAVE_DENY'):
            seen.update(Path(os.environ['V2_SAVE_DENY']).read_text().split())
        for rel, data in files.items():
            write(game / rel, data)
        after_save()
        recipe._check_migration_writes(ctx, io.StringIO())
        return 'V2 MIGRATE DONE created=0 kept=0 patches=0\n'
    return run


def plan(game):
    return migration.make_plan(game, ['region/w01'], 'region/w00', [], True, [], 32.0)


def never(plan_file):
    raise AssertionError('the editor must not start')


def test_the_switch_fails_closed(tmp_path):
    assert authority.d04(governance(tmp_path, False)) == (authority.BOOTSTRAP_WRITER, False)
    assert authority.d04(governance(tmp_path, True))[1] is True
    assert authority.d04(tmp_path / 'missing.toml') == (None, True)
    (tmp_path / 'bad.toml').write_text('[d04]\nwriter = "x"\nclosed = "no"\n')
    assert authority.d04(tmp_path / 'bad.toml')[1] is True
    assert authority.d04(authority.GAME / 'governance.toml') == ('jim-macbook-5', True)   # the committed record: closed


def test_closed_d04_refuses_the_bootstrap_writer_on_every_route(tmp_path, game, env):
    env.setattr(authority, 'GOVERNANCE', governance(tmp_path, True))
    env.setenv('ATELIER_AGENT', authority.BOOTSTRAP_WRITER)
    env.setattr(sv, 'engine_identity', lambda: ENGINE)
    folder = game / 'assets/props/bench'
    write(folder / 'src/model.glb', 'mesh')
    write(folder / 'asset.toml', 'schema = 1\nid = "prop/bench"\nkind = "static-mesh"\nauthority = "generated"\n'
          'owner = "region/w01"\n[[sources]]\npath = "src/model.glb"\nsha256 = "'
          + records.sha256_file(folder / 'src/model.glb') + '"\n[recipe]\nimporter = "static-mesh"\nversion = 1\n'
          '[[outputs]]\npackage = "/Game/Props/SM_Bench"\n')
    write(game / 'assets/materials/painted/asset.toml', 'schema = 1\nid = "material/painted"\nkind = "material"\n'
          'authority = "editor"\nowner = "shared/material/painted"\n[[outputs]]\npackage = "/Game/M/M_Painted"\n')
    write(game / 'unreal/Content/M/M_Painted.uasset', 'material')
    bench = next(a for a in records.discover(game)[0] if a.id == 'prop/bench')
    import_plan = tmp_path / 'import.json'
    import_plan.write_text(json.dumps({'asset': 'prop/bench', 'importer': 'static-mesh', 'version': 1, 'claim': None,
                                       'packages': ['/Game/Props/SM_Bench'], 'write_paths': []}))
    env.setenv('V2_IMPORT_PLAN', str(import_plan))
    env.setenv('V2_EDITOR_SCRIPT', str(ROOT / 'unreal/Scripts/open_close.py'))
    donor = tmp_path / 'donor'
    write(donor / 'Japan/Assets/House_A.uasset', 'house')
    env.setattr(adopt, 'references', lambda path: [])
    ctx = type('Ctx', (), {'out': tmp_path / 'out'})()
    routes = {
        'import': lambda: importer.authorize(game, bench, None),
        'import step': lambda: recipe._authorize_import(ctx, io.StringIO()),
        'editor script': lambda: recipe._authorize_editor(ctx, io.StringIO()),
        'save validation': lambda: sv.validate(game, 'material/painted', echo=lambda *_: None),
        'adoption': lambda: adopt.adopt(game, donor, ['Japan'], [], 'x', echo=lambda *_: None),
        'migration step': lambda: recipe._authorize_migration(ctx, io.StringIO()),
        'migration': lambda: migration.migrate(game, plan(game), None, editor=never, out=tmp_path / 'm'),
    }
    for route, call in routes.items():
        try:
            call()
        except Exception as error:  # noqa: BLE001 — each route wraps the refusal in its own error type
            assert 'D04 is closed' in str(error), (route, error)
        else:
            raise AssertionError(f'{route}: the bootstrap writer passed with D04 closed')
    assert not (game / 'unreal/Content/Japan').exists()
    assert not (game / 'assets/materials/painted/verified.json').exists()
    env.setattr(authority, 'GOVERNANCE', governance(tmp_path, False))   # open: the same writer passes
    importer.authorize(game, bench, None)
    recipe._authorize_migration(ctx, io.StringIO())


def test_a_claimed_migration_creates_binds_and_records_its_regions_actors(tmp_path, game, claims, env):
    env.setattr(authority, 'GOVERNANCE', governance(tmp_path, True))      # works with no bootstrap exemption
    env.setenv('ATELIER_AGENT', 'agent-a')
    claims.grant('T1', 'agent-a', ['region/w01', 'region/w00'], {repo_path(OLD)})
    denied = set()
    files = {NEW: 'region/w01:Kiosk:whole:id1', SKY: 'region/w00:Sky:whole:id2', OLD: 'region/w01:Old:whole:id0 v2'}
    created = migration.migrate(game, plan(game), 'T1', editor=editor(game, tmp_path, files, denied),
                                out=tmp_path / 'm', echo=lambda *_: None)
    assert created == [NEW, SKY]
    # The editor could save the claimed file and new ones, never another existing package.
    assert any(d.endswith(FAR) for d in denied) and any(d.endswith('Slice.umap') for d in denied)
    assert not any(d.endswith(OLD) for d in denied)
    assert {repo_path(NEW), repo_path(SKY)} <= claims.tasks['T1']['paths']               # bound to the claim ...
    [extension] = claims.extensions
    assert extension[5] == '1' and '--acquire' in extension                            # ... with its LFS locks
    assert sorted(extension[i + 1] for i, a in enumerate(extension) if a == '--lock-path') == \
        [repo_path(NEW), repo_path(SKY)]
    w01 = records.load_verified(game / 'world/regions/w01/actors.verified.json')['files']
    w00 = records.load_verified(game / 'world/regions/w00/actors.verified.json')['files']
    assert sorted(w01) == [OLD, NEW] and list(w00) == [SKY]
    assert migration.migrate(game, plan(game), 'T1', editor=editor(game, tmp_path, {}), out=tmp_path / 'm',
                             echo=lambda *_: None) == []                                 # a rerun creates nothing
    assert len(claims.extensions) == 1


def test_a_bind_batch_that_times_out_is_retried(tmp_path, game, claims, env):
    env.setenv('ATELIER_AGENT', 'agent-a')
    claims.grant('T1', 'agent-a', ['region/w01', 'region/w00'])
    claims.extend_timeouts = 2                         # a busy claim service: the third try gets through
    files = {NEW: 'region/w01:Kiosk:whole:id1', SKY: 'region/w00:Sky:whole:id2'}
    assert migration.migrate(game, plan(game), 'T1', editor=editor(game, tmp_path, files),
                             out=tmp_path / 'm', echo=lambda *_: None) == [NEW, SKY]
    assert (game / NEW).exists() and repo_path(NEW) in claims.tasks['T1']['paths']
    claims.extend_timeouts = 3                         # three timeouts: the bind fails and sets what it made aside
    with pytest.raises(authority.BindFailed, match='cannot bind.*wait in'):
        migration.migrate(game, plan(game), 'T1', editor=editor(game, tmp_path, {FAR_NEW: 'region/w01:K2'}),
                          out=tmp_path / 'm', echo=lambda *_: None)
    assert not (game / FAR_NEW).exists() and (authority.PENDING / 'files' / FAR_NEW).is_file()
    assert repo_path(FAR_NEW) not in claims.tasks['T1']['paths']
    with pytest.raises(migration.MigrationError, match='resume it'):     # no new run while a set waits
        migration.migrate(game, plan(game), 'T1', editor=never, out=tmp_path / 'm')
    os.environ['V2_MIGRATE_PLAN'] = str(tmp_path / 'direct.json')        # nor through the build step directly
    (tmp_path / 'direct.json').write_text(json.dumps({**plan(game), 'claim': 'T1'}))
    with pytest.raises(RuntimeError, match='failed bind'):
        recipe._authorize_migration(type('Ctx', (), {'out': tmp_path / 'out'})(), io.StringIO())
    with pytest.raises(migration.MigrationError, match='no saved editor output'):
        migration.resume(game, out=tmp_path / 'm')
    (authority.PENDING / 'stdout.log').write_text('V2 MIGRATE DONE created=0 kept=0 patches=0\n')   # run.py saves it
    claims.extend_timeouts = 3                         # still failing: the files go back to wait
    with pytest.raises(authority.BindFailed):
        migration.resume(game, out=tmp_path / 'm', echo=lambda *_: None)
    assert not (game / FAR_NEW).exists() and (authority.PENDING / 'files' / FAR_NEW).is_file()
    claims.extend_timeouts = 0                         # settled: the resumed bind binds and records them
    assert migration.resume(game, out=tmp_path / 'm', echo=lambda *_: None) == [FAR_NEW]
    assert (game / FAR_NEW).read_text() == 'region/w01:K2' and repo_path(FAR_NEW) in claims.tasks['T1']['paths']
    assert FAR_NEW in records.load_verified(game / 'world/regions/w01/actors.verified.json')['files']
    assert not authority.PENDING.exists()


def test_a_publish_check_timeout_sets_the_files_aside_and_a_resumed_refusal_deletes_them(tmp_path, game, claims, env):
    env.setenv('ATELIER_AGENT', 'agent-a')
    claims.grant('T1', 'agent-a', ['region/w01', 'region/w00'])
    claims.check_timeouts = 1                          # extended, then the final check times out: a service fault
    with pytest.raises(authority.BindFailed, match='timed out'):
        migration.migrate(game, plan(game), 'T1', editor=editor(game, tmp_path, {NEW: 'region/w01:K'}),
                          out=tmp_path / 'm', echo=lambda *_: None)
    assert not (game / NEW).exists() and (authority.PENDING / 'files' / NEW).is_file()
    (authority.PENDING / 'stdout.log').write_text('V2 MIGRATE DONE created=0 kept=0 patches=0\n')
    claims.unlocked.add(repo_path(NEW))                # resumed, the check now refuses: the files are deleted
    with pytest.raises(authority.Unauthorized, match='verified locks'):
        migration.resume(game, out=tmp_path / 'm', echo=lambda *_: None)
    assert not (game / NEW).exists() and not authority.PENDING.exists()


def test_creation_in_another_regions_folder_or_outside_actor_folders_is_refused(tmp_path, game, claims, env):
    env.setenv('ATELIER_AGENT', 'agent-a')
    claims.grant('T1', 'agent-a', ['region/w01', 'region/w00'])
    for rel in (f'{OTHER}/1/EE/STRAY.uasset', 'unreal/Content/V2/Stray.uasset'):
        with pytest.raises(authority.Unauthorized, match='outside the actor folders of region/w01, region/w00'):
            migration.migrate(game, plan(game), 'T1', editor=editor(game, tmp_path, {NEW: 'region/w01:K', rel: 'x'}),
                              out=tmp_path / 'm', echo=lambda *_: None)
        assert not (game / rel).exists() and not (game / NEW).exists()   # every created file is removed
    assert claims.extensions == [] and claims.tasks['T1']['paths'] == set()
    assert not (game / 'world/regions/w00/actors.verified.json').exists()


def test_modifying_an_existing_unclaimed_file_is_refused(tmp_path, game, claims, env):
    env.setenv('ATELIER_AGENT', 'agent-a')
    claims.grant('T1', 'agent-a', ['region/w01', 'region/w00'])
    for rel in (OLD, 'unreal/Content/V2/Maps/Slice.umap'):
        denied = set()
        with pytest.raises(authority.Unauthorized, match='does not exactly cover'):
            migration.migrate(game, plan(game), 'T1', editor=editor(game, tmp_path, {NEW: 'region/w01:K', rel: 'v2'},
                                                                   denied), out=tmp_path / 'm', echo=lambda *_: None)
        assert any(d.endswith(rel) for d in denied)            # the editor's save guard refuses it first
        assert not (game / NEW).exists()                       # the refused run's created file is removed
    assert claims.extensions == []                             # nothing is bound when any write is refused


def test_a_claimed_existing_file_without_its_verified_lock_refuses_before_the_editor(tmp_path, game, claims, env):
    env.setenv('ATELIER_AGENT', 'agent-a')
    claims.grant('T1', 'agent-a', ['region/w01', 'region/w00'], paths=[f'games/yorimichi_v2/{OLD}'])
    claims.unlocked.add(f'games/yorimichi_v2/{OLD}')               # listed in the claim, but its LFS lock is missing
    with pytest.raises(authority.Unauthorized, match='verified locks'):
        migration.migrate(game, plan(game), 'T1', editor=editor(game, tmp_path, {}), out=tmp_path / 'm',
                          echo=lambda *_: None)
    assert (game / OLD).read_text() == 'region/w01:Old:whole:id0'   # refused at authorization: nothing written
    claims.unlocked.clear()                                          # with its lock verified, the step proceeds
    os.environ['V2_MIGRATE_PLAN'] = str(tmp_path / 'direct.json')
    (tmp_path / 'direct.json').write_text(json.dumps({**plan(game), 'claim': 'T1'}))
    recipe._authorize_migration(type('Ctx', (), {'out': tmp_path / 'out'})(), io.StringIO())
    assert any('--paths' in c and f'games/yorimichi_v2/{OLD}' in c for c in claims.checks)


def test_a_refused_bind_removes_every_created_file(tmp_path, game, claims, env):
    env.setenv('ATELIER_AGENT', 'agent-a')
    claims.grant('T1', 'agent-a', ['region/w01', 'region/w00'])
    claims.unlocked.add(f'games/yorimichi_v2/{NEW}')               # its lock is acquired but cannot be verified
    with pytest.raises(authority.Unauthorized, match='verified locks'):
        migration.migrate(game, plan(game), 'T1', editor=editor(game, tmp_path, {NEW: 'region/w01:K'}),
                          out=tmp_path / 'm', echo=lambda *_: None)
    assert not (game / NEW).exists() and not authority.PENDING.exists()   # a refusal, not a service fault


@pytest.mark.parametrize('failure', ['down', 'garbled'])
def test_a_claim_service_failure_right_after_the_save_removes_every_created_file(tmp_path, game, claims, env, failure):
    env.setenv('ATELIER_AGENT', 'agent-a')
    claims.grant('T1', 'agent-a', ['region/w01', 'region/w00'])
    before = {p: p.read_bytes() for p in game.rglob('*') if p.is_file()}

    def fail():
        claims.failure = failure
    with pytest.raises(Exception):
        migration.migrate(game, plan(game), 'T1', editor=editor(game, tmp_path, {NEW: 'region/w01:K'}, after_save=fail),
                          out=tmp_path / 'm', echo=lambda *_: None)
    assert not (game / NEW).exists()
    assert {p: p.read_bytes() for p in game.rglob('*') if p.is_file()} == before   # existing files are kept as they were
    assert claims.tasks['T1']['paths'] == set()                                    # and the claim is unchanged


def test_a_claim_must_hold_every_touched_region_before_the_editor_starts(tmp_path, game, claims, env):
    env.setenv('ATELIER_AGENT', 'agent-a')
    claims.grant('T1', 'agent-a', ['region/w01'])
    with pytest.raises(authority.Unauthorized, match='cover region/w01, region/w00'):
        migration.migrate(game, plan(game), 'T1', editor=never, out=tmp_path / 'm')
    claims.grant('T2', 'agent-b', ['region'])
    with pytest.raises(authority.Unauthorized, match="held by 'agent-a'"):
        migration.migrate(game, plan(game), 'T2', editor=never, out=tmp_path / 'm')
    os.environ['V2_MIGRATE_PLAN'] = str(tmp_path / 'direct.json')    # selecting the step directly is checked too
    (tmp_path / 'direct.json').write_text(json.dumps({**plan(game), 'claim': 'T1'}))
    with pytest.raises(authority.Unauthorized, match='cover region/w01, region/w00'):
        recipe._authorize_migration(type('Ctx', (), {'out': tmp_path / 'out'})(), io.StringIO())


def test_a_created_actor_no_touched_region_records_fails_the_run(tmp_path, game, claims, env):
    env.setenv('ATELIER_AGENT', 'agent-a')
    claims.grant('T1', 'agent-a', ['region/w01', 'region/w00'])
    stray = f'{SLICE}/3/FF/HARBOUR.uasset'     # in the shared map folder, labelled for a region the run does not touch
    files = {SKY: 'region/w00:Sky:w:id2', stray: 'region/w09:Harbour:w:id9'}
    with pytest.raises(migration.MigrationError, match='1 created file'):
        migration.migrate(game, plan(game), 'T1', editor=editor(game, tmp_path, files), out=tmp_path / 'm',
                          echo=lambda *_: None)


def test_a_region_owns_its_actor_packages_companions(game):
    """An editor save of a region's actor may write its .uexp/.ubulk/.uptnl: the region owns those paths too, so a
    claimed move declares no extra scopes for them (C01's native placement edit was refused for lack of this)."""
    stem = repo_path(OLD)[:-len('.uasset')]
    scopes, unowned = authority.owning_scopes(game, [stem + ext for ext in ('.uasset', '.uexp', '.ubulk', '.uptnl')])
    assert scopes == {'region/w01'} and unowned == []


def test_a_large_protected_check_runs_in_bounded_commands(game, claims, env):
    env.setenv('ATELIER_AGENT', 'agent-a')
    claims.grant('T1', 'agent-a', ['region/w01'], {repo_path(OLD), repo_path(NEW)})
    env.setattr(authority, 'CHECK_PATHS', 1)
    authority.authorize([repo_path(OLD), repo_path(NEW)], 'T1', 'a write', scopes={'region/w01'})
    assert [c[c.index('--paths') + 1:] for c in claims.checks] == [[repo_path(OLD)], [repo_path(NEW)]]
