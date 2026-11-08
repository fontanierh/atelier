"""tools/editor/session.py: one warm editor, jobs fed in order, each with its own environment and receipt."""
import json
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
    def __init__(self, folder: Path, log: Path, fail=()):
        self.folder, self.log, self.fail = folder, log, set(fail)
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
                self.returncode = 0
                return
            self.ran.append((job['name'], job['env']))
            error = 'boom' if job['name'] in self.fail else None
            with self.log.open('a') as log:
                log.write(f'V2 JOB START {expected} {job["name"]}\nwork of {job["name"]}\n'
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


def test_editor_itself_refuses_a_render_script_in_headless_mode(monkeypatch):
    import types
    source = (GAME / 'unreal/Scripts/job_queue.py').read_text()
    monkeypatch.setitem(sys.modules, 'unreal', types.ModuleType('unreal'))
    namespace = {'__file__': str(GAME / 'unreal/Scripts/job_queue.py')}
    exec(compile(source.rsplit('\nmain()', 1)[0], namespace['__file__'], 'exec'), namespace)
    assert namespace['job_script']('migrate_objects.py', headless=True).name == 'migrate_objects.py'
    assert namespace['job_script']('capture_poses.py').name == 'capture_poses.py'
    with pytest.raises(RuntimeError, match='only object migration'):
        namespace['job_script']('capture_poses.py', headless=True)
