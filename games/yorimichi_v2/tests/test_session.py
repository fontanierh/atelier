"""tools/editor/session.py: one warm editor, jobs fed in order, each with its own environment and receipt."""
import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME / 'tools/editor'))
import session as S  # noqa: E402


class FakeEditor:
    """job_queue.py's side of the protocol, without Unreal: ready, then each job's log section and receipt."""
    def __init__(self, folder: Path, log: Path, fail=(), effect=None, close_code=0):
        self.folder, self.log, self.fail = folder, log, set(fail)
        self.effect, self.close_code = effect, close_code
        self.ran, self.returncode = [], None
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def write(self, name, value):
        (self.folder / name).write_text(json.dumps(value))

    def serve(self):
        nonce = json.loads((self.folder / 'session.json').read_text())['nonce']
        self.write('ready.json', {'nonce': nonce})
        expected = 1
        while True:
            try:
                job = json.loads((self.folder / 'next.json').read_text())
            except (FileNotFoundError, ValueError):
                job = None
            if not job or job.get('seq') != expected:
                time.sleep(.01)
                continue
            if job.get('close'):
                self.returncode = self.close_code
                return
            self.ran.append((job['name'], job['env']))
            error = 'boom' if job['name'] in self.fail else None
            body = f'work of {job["name"]}'
            if self.effect and not error:
                try:
                    body = self.effect(job, self.folder)
                except Exception as raised:
                    error = str(raised)
            with self.log.open('a') as log:
                log.write(f'V2 JOB START {expected} {job["name"]}\n{body}\n'
                          f'V2 JOB END {expected} {job["name"]} {"failed" if error else "ok"}\n')
            self.write(f'{expected}.receipt.json', {'nonce': nonce, 'seq': expected, 'error': error, 'seconds': .5})
            if error:
                self.returncode = 1
                return
            expected += 1

    def poll(self):
        return self.returncode

    def wait(self):
        self.thread.join(5)
        return self.returncode


def make(tmp_path, game, **kw):
    editors = []

    def launch(folder):
        editors.append(FakeEditor(folder, tmp_path / 'stdout.log', **kw))
        return editors[0]
    session = S.Session(game, out=tmp_path / 'sessions', launch=launch, log=tmp_path / 'stdout.log',
                        echo=lambda *_: None, open_seconds=5)
    return session, editors


@pytest.fixture
def game(tmp_path):
    root = tmp_path / 'repo/games/yorimichi_v2'
    plugin = tmp_path / 'repo/platform/engine/Plugins/Core'
    (plugin / 'Source').mkdir(parents=True)
    (plugin / 'Core.uplugin').write_text('{}\n')
    (plugin / 'Source/Core.cpp').write_text('// core\n')
    (root / 'unreal/Scripts').mkdir(parents=True)
    (root / 'unreal/Source').mkdir(parents=True)
    (root / 'unreal/Scripts/move_actor.py').write_text('pass\n')
    return root


def test_jobs_run_in_order_in_one_editor_each_with_its_own_environment(tmp_path, game, monkeypatch):
    monkeypatch.setattr(S, 'load_build', lambda: None)
    session, editors = make(tmp_path, game)
    with session:
        first = session.run('one', 'move_actor.py', {'V2_SAVE_ALLOW': '/a.txt'})
        second = session.run('two', 'move_actor.py', {'V2_SAVE_ALLOW': '/b.txt', 'V2_SAVE_DENY': None})
    assert len(editors) == 1
    assert editors[0].ran == [('one', {'V2_SAVE_ALLOW': '/a.txt'}),
                              ('two', {'V2_SAVE_ALLOW': '/b.txt', 'V2_SAVE_DENY': None})]
    assert 'work of one' in first and 'work of two' not in first and 'work of two' in second
    summary = json.loads((session.folder / 'summary.json').read_text())
    assert [j['name'] for j in summary['jobs']] == ['one', 'two'] and summary['exit'] == 0
    assert 'startup_seconds' in summary


def test_a_failed_job_ends_the_session(tmp_path, game, monkeypatch):
    monkeypatch.setattr(S, 'load_build', lambda: None)
    session, editors = make(tmp_path, game, fail={'one'})
    with pytest.raises(S.SessionError, match='job 1 one: boom'):
        with session:
            session.run('one', 'move_actor.py', {})
            session.run('two', 'move_actor.py', {})
    assert [name for name, _ in editors[0].ran] == ['one']


def test_changed_editor_code_ends_the_batch_before_the_next_job(tmp_path, game, monkeypatch):
    monkeypatch.setattr(S, 'load_build', lambda: None)
    session, editors = make(tmp_path, game)
    with pytest.raises(S.SessionError, match='changed since the editor started'):
        with session:
            session.run('one', 'move_actor.py', {})
            (game / 'unreal/Scripts/move_actor.py').write_text('print(1)\n')
            session.run('two', 'move_actor.py', {})
    assert [name for name, _ in editors[0].ran] == ['one']


def test_changed_plugin_code_ends_the_batch_before_the_next_job(tmp_path, game, monkeypatch):
    monkeypatch.setattr(S, 'load_build', lambda: None)
    session, editors = make(tmp_path, game)
    with pytest.raises(S.SessionError, match='changed since the editor started'):
        with session:
            session.run('one', 'move_actor.py', {})
            (tmp_path / 'repo/platform/engine/Plugins/Core/Source/Core.cpp').write_text('// core v2\n')
            session.run('two', 'move_actor.py', {})
    assert [name for name, _ in editors[0].ran] == ['one']


def test_a_job_needs_a_claim_and_its_own_inputs_only(tmp_path, game, monkeypatch):
    monkeypatch.setattr(S, 'load_build', lambda: None)
    session, editors = make(tmp_path, game)
    with session:
        with pytest.raises(S.SessionError, match='needs a claim'):
            session.script('move_actor.py', None, ['games/yorimichi_v2/x'])
        with pytest.raises(S.SessionError, match='only its own V2_ inputs'):
            session.script('move_actor.py', 'TASK', ['games/yorimichi_v2/x'], env={'PYTHONPATH': '/x'})
        with pytest.raises(S.SessionError, match='needs a claim'):
            session.objects(['region/w09-brinecove'], 'region/w00-island', None)
    assert editors[0].ran == []


def test_headless_batch_rejects_script_before_starting_editor(tmp_path, game):
    session, editors = make(tmp_path, game)
    session.headless = True
    with pytest.raises(S.SessionError, match='only object migration'):
        S.run_jobs([{'kind': 'objects'}, {'kind': 'script', 'script': 'capture_poses.py'}], session)
    assert editors == [] and not session.folder.exists()


def test_headless_session_binds_mode_and_refuses_late_render_job(tmp_path, game, monkeypatch):
    monkeypatch.setattr(S, 'load_build', lambda: None)
    session, editors = make(tmp_path, game)
    session.headless = True
    with session:
        assert json.loads((session.folder / 'session.json').read_text())['headless'] is True
        session.run('objects', 'migrate_objects.py', {})
        with pytest.raises(S.SessionError, match='only object migration'):
            session.run('capture', 'capture_poses.py', {})
    assert [name for name, _ in editors[0].ran] == ['objects']


def test_editor_itself_refuses_a_render_script_in_headless_mode(monkeypatch, tmp_path):
    import types
    source = (GAME / 'unreal/Scripts/job_queue.py').read_text()
    monkeypatch.setitem(sys.modules, 'unreal', types.ModuleType('unreal'))
    namespace = {'__file__': str(GAME / 'unreal/Scripts/job_queue.py')}
    exec(compile(source.rsplit('\nmain()', 1)[0], namespace['__file__'], 'exec'), namespace)
    assert namespace['job_script']('migrate_objects.py', headless=True).name == 'migrate_objects.py'
    assert namespace['job_script']('capture_poses.py').name == 'capture_poses.py'
    with pytest.raises(RuntimeError, match='only object migration'):
        namespace['job_script']('capture_poses.py', headless=True)
    plan = tmp_path / 'plan.json'
    plan.write_text(json.dumps({'kind': 'static-mesh', 'importer': 'static-mesh'}))
    env = {'V2_IMPORT_PLAN': str(plan)}
    assert namespace['job_script']('import_asset.py', kind='import', env=env, headless=True).name == 'import_asset.py'
    with pytest.raises(RuntimeError, match='needs a prepared import'):
        namespace['job_script']('import_asset.py', env=env)
    plan.write_text(json.dumps({'kind': 'texture', 'importer': 'texture'}))
    with pytest.raises(RuntimeError, match='only object migration'):
        namespace['job_script']('import_asset.py', kind='import', env=env, headless=True)
    assert namespace['job_script']('import_asset.py', kind='import', env=env).name == 'import_asset.py'


@pytest.fixture
def imports(game, monkeypatch):
    from claims_fake import ClaimService
    from test_import_run import mesh_asset, records, run

    recipe = S.load_build()
    monkeypatch.setattr(recipe, 'GAME', game)
    monkeypatch.setattr(S, 'load_build', lambda: recipe)
    allow = S.authority.allow_saves
    monkeypatch.setattr(S.authority, 'allow_saves', lambda paths, file: allow(paths, file, repo=game.parents[1]))
    monkeypatch.setenv('ATELIER_AGENT', 'import-test')
    monkeypatch.setenv('V2_SAVE_DENY', 'between-jobs.txt')
    claims = ClaimService()
    monkeypatch.setattr(S.authority.subprocess, 'run', claims)

    def prepare(name):
        folder = mesh_asset(game, name, f'/Game/Props/SM_{name}')
        asset = records.load_asset(folder / 'asset.toml')
        journal = run.Journal(game, asset)
        files = run.generated_files(game, asset)
        journal.begin(files)
        paths = ['games/yorimichi_v2/' + file.relative_to(game).as_posix() for file in files]
        plan = {'asset': asset.id, 'kind': 'static-mesh', 'importer': 'static-mesh', 'version': 1,
                'claim': name, 'packages': [f'/Game/Props/SM_{name}'], 'write_paths': paths}
        plan_file = journal.dir / 'plan.json'
        plan_file.write_text(json.dumps(plan))
        claims.grant(name, 'import-test', [f'asset/{asset.id}'], paths)
        return {'kind': 'import', 'asset': asset.id, 'claim': name, 'plan': str(plan_file), 'write_paths': paths,
                'name': f'import {asset.id}', 'script': 'import_asset.py', 'env': {'V2_IMPORT_PLAN': str(plan_file)}}

    def save(job, _folder):
        plan = json.loads(Path(job['env']['V2_IMPORT_PLAN']).read_text())
        allowed = Path(job['env']['V2_SAVE_ALLOW']).read_text().splitlines()
        assert job['env']['V2_SAVE_DENY'] is None
        for package in plan['packages']:
            path = records.package_files(game, package)[0]
            assert str(path) in allowed
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'imported')
        return 'V2 IMPORT DONE'

    return prepare, save, claims


def test_imports_share_editor_but_reauthorize_and_record_each_job(tmp_path, game, imports):
    prepare, save, claims = imports
    jobs = [prepare('bench'), prepare('lamp')]

    def saving(job, folder):
        # The previous success is on disk while the editor is still running the next job.
        summary = json.loads((folder / 'summary.json').read_text())
        assert len(summary['jobs']) == job['seq'] - 1
        return save(job, folder)

    session, editors = make(tmp_path, game, effect=saving)
    session.headless = True
    S.run_jobs(jobs, session)
    assert len(editors) == 1 and len(claims.checks) == 2
    envs = [env for _, env in editors[0].ran]
    assert envs[0]['V2_SAVE_ALLOW'] != envs[1]['V2_SAVE_ALLOW']
    summary = json.loads((session.folder / 'summary.json').read_text())
    expected = [f'games/yorimichi_v2/unreal/Content/Props/SM_{name}.uasset' for name in ('bench', 'lamp')]
    assert [j['written'] for j in summary['jobs']] == [[path] for path in expected]
    assert json.loads((session.folder / 'checked.json').read_text()) == expected
    assert summary['exit'] == 0 and os.environ['V2_SAVE_DENY'] == 'between-jobs.txt'
    # Completion and rollback still belong to the importer, after native exit.
    assert all(Path(job['plan']).with_name('journal.json').is_file() for job in jobs)
    assert not list((game / 'assets').rglob('verified.json'))


def test_import_checks_claim_again_before_second_job(tmp_path, game, imports):
    prepare, save, claims = imports
    jobs = [prepare('bench'), prepare('lamp')]

    def saving(job, folder):
        result = save(job, folder)
        claims.transfer('lamp', 'another-agent')
        return result

    session, editors = make(tmp_path, game, effect=saving)
    with pytest.raises(S.SessionError, match='job 2 import prop/lamp'):
        S.run_jobs(jobs, session)
    assert [name for name, _ in editors[0].ran] == ['import prop/bench']
    assert not (game / 'unreal/Content/Props/SM_lamp.uasset').exists()
    assert session.summary['jobs'][0]['written'] and editors[0].poll() == 0


@pytest.mark.parametrize('failure', ['stray', 'missing', 'marker', 'native'])
def test_failed_import_stops_batch_and_keeps_prior_success(tmp_path, game, imports, failure):
    prepare, save, _ = imports
    jobs = [prepare(name) for name in ('bench', 'lamp', 'tree')]

    def saving(job, folder):
        if job['seq'] != 2:
            return save(job, folder)
        if failure == 'native':
            raise RuntimeError('native import failed')
        if failure == 'missing':
            return 'V2 IMPORT DONE'
        save(job, folder)
        if failure == 'stray':
            (game / 'unreal/Content/Props/Stray.uasset').write_bytes(b'outside claim')
        return 'no completion' if failure == 'marker' else 'V2 IMPORT DONE'

    session, editors = make(tmp_path, game, effect=saving)
    with pytest.raises(S.SessionError, match='job 2 import prop/lamp'):
        S.run_jobs(jobs, session)
    assert len(editors[0].ran) == 2 and editors[0].poll() is not None
    summary = json.loads((session.folder / 'summary.json').read_text())
    assert [j['name'] for j in summary['jobs'] if 'written' in j] == ['import prop/bench']
    assert all(Path(job['plan']).with_name('journal.json').is_file() for job in jobs)


@pytest.mark.parametrize('change', ['claim', 'env', 'journal', 'texture'])
def test_unprepared_or_rendering_import_refused_before_launch(tmp_path, game, imports, change):
    prepare, _, _ = imports
    job = prepare('bench')
    if change == 'claim':
        job['claim'] = 'other'
    elif change == 'env':
        job['env']['V2_SAVE_ALLOW'] = 'wider.txt'
    elif change == 'journal':
        Path(job['plan']).with_name('journal.json').unlink()
    else:
        path = Path(job['plan'])
        path.write_text(json.dumps(json.loads(path.read_text()) | {'kind': 'texture', 'importer': 'texture'}))
    session, editors = make(tmp_path, game)
    session.headless = True
    with pytest.raises((S.SessionError, FileNotFoundError)):
        S.run_jobs([job], session)
    assert editors == []


def test_incomplete_import_journal_cannot_authorize_unbacked_destination(tmp_path, game, imports):
    prepare, _, _ = imports
    job = prepare('bench')
    job['write_paths'] = job['write_paths'][:1]  # omit possible package companions from plan AND journal
    plan_file = Path(job['plan'])
    plan = json.loads(plan_file.read_text()) | {'write_paths': job['write_paths']}
    plan_file.write_text(json.dumps(plan))
    plan_file.with_name('journal.json').write_text(json.dumps({
        'asset': job['asset'], 'files': {'unreal/Content/Props/SM_bench.uasset': None}}))
    session, editors = make(tmp_path, game)
    with pytest.raises(S.SessionError, match='journal does not cover every import destination'):
        S.run_jobs([job], session)
    assert editors[0].ran == []


def test_nonzero_native_close_is_not_reported_as_success(tmp_path, game, imports):
    prepare, save, _ = imports
    job = prepare('bench')
    session, editors = make(tmp_path, game, effect=save, close_code=2)
    with pytest.raises(S.SessionError, match='ended with exit 2'):
        S.run_jobs([job], session)
    assert session.summary['jobs'][0]['written'] and session.summary['exit'] == 2


def test_failed_session_start_closes_native_before_returning_to_importer(tmp_path, game, imports, monkeypatch):
    prepare, _, _ = imports
    job = prepare('bench')
    session, editors = make(tmp_path, game)

    def no_start(*_):
        raise S.SessionError('editor start timed out')

    monkeypatch.setattr(session, '_wait', no_start)
    with pytest.raises(S.SessionError, match='editor start timed out'):
        S.run_jobs([job], session)
    assert editors[0].poll() == 0 and editors[0].ran == []
    assert Path(job['plan']).with_name('journal.json').exists()
