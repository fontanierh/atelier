"""Batch import: one warm editor per N assets. Each asset's outcome is its own: a failure restores only its files, a
session that dies restores only what it did not finish, and a rerun starts nothing."""
import hashlib
import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'content'))
import records  # noqa: E402

spec = importlib.util.spec_from_file_location('v2_import_run_batch', ROOT / 'tools' / 'import' / 'run.py')
run = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = run
spec.loader.exec_module(run)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())


def mesh_asset(game, name, package):
    folder = game / 'assets/props' / name
    source = f'glb {name}'.encode()
    write(folder / 'src/model.glb', source)
    write(folder / 'asset.toml', f'''schema = 1
id = "prop/{name}"
kind = "static-mesh"
authority = "generated"
owner = "region/w04-skatepark"
[[sources]]
path = "src/model.glb"
sha256 = "{sha(source)}"
[recipe]
importer = "static-mesh"
version = 1
[[outputs]]
package = "{package}"
''')
    return folder


class FakeSession:
    """Plays tools/editor/session.py's contract for `import` jobs: in order, one result per job, the first failure
    ends the session, a crash raises BatchCrash with the results reported so far."""

    def __init__(self, game, *, fail=(), crash_during=None, stray=None, skip_write=(), stop_after=None):
        self.game, self.fail, self.crash_during = game, set(fail), crash_during
        self.stray, self.skip_write, self.stop_after = stray, set(skip_write), stop_after
        self.calls = 0
        self.headless_calls = []

    def __call__(self, jobs_file, *, log_file, headless=False):
        self.calls += 1
        self.headless_calls.append(headless)
        jobs = json.loads(jobs_file.read_text())['jobs']
        results, exit_code = {}, 0
        for seq, job in enumerate(jobs, 1):
            asset = job['asset']
            if self.stop_after is not None and seq > self.stop_after:
                break                                   # a clean exit before this job: the session ends, nothing failed
            plan = json.loads(Path(job['plan']).read_text())
            if asset == self.crash_during:
                for package in plan['packages']:            # the editor wrote part of it, then died
                    write(records.package_files(self.game, package)[0], b'half written')
                raise run.BatchCrash('the editor crashed', results)
            if asset in self.fail:
                for package in plan['packages']:
                    write(records.package_files(self.game, package)[0], b'partial')
                results[asset] = {'status': 'failed', 'error': 'import script raised', 'written': []}
                exit_code = 1
                break
            written = []
            for package in plan['packages']:
                if asset in self.skip_write:
                    continue
                target = records.package_files(self.game, package)[0]
                write(target, f'imported {asset}'.encode())
                written.append('games/yorimichi_v2/' + records.content_relative(self.game, target))
            if self.stray and asset == self.stray[0]:
                write(self.game / self.stray[1], b'stray')
                written.append('games/yorimichi_v2/' + self.stray[1])
            if plan['importer'] == 'static-mesh':
                one = {'count': 1, 'screen_sizes': [1.0], 'reductions': [1.0]}
                write(Path(job['plan']).with_name('lod-result.json'), json.dumps(
                    {package: {'before': None, 'after': one} for package in plan['packages']}))
            results[asset] = {'status': 'done', 'error': None, 'written': written}
        return run.SessionOutcome(results, exit_code)


@pytest.fixture
def game(tmp_path, monkeypatch):
    monkeypatch.setenv('ATELIER_AGENT', run.BOOTSTRAP_WRITER)
    for name in ('a', 'b', 'c'):
        mesh_asset(tmp_path, name, f'/Game/Props/SM_{name.upper()}')
        write(tmp_path / f'unreal/Content/Props/SM_{name.upper()}.uasset', f'old {name}')
    return tmp_path


def batch(game, ids, runner, size=3):
    return run.import_batch(game, ids, engine='5.8.2-1', claim=None, batch_size=size, runner=runner,
                            echo=lambda *_: None)


def content(game, name):
    return (game / f'unreal/Content/Props/SM_{name.upper()}.uasset').read_bytes()


def recorded(game, name):
    return (game / f'assets/props/{name}/verified.json').is_file()


def test_a_failed_job_is_an_interrupted_batch_that_keeps_the_finished_jobs(game):
    """The session exits nonzero: a finished job is recorded, the failed one restores, the unreached one is not run and
    not retried in this run, and no further session starts."""
    session = FakeSession(game, fail={'prop/b'})
    report = batch(game, ['prop/a', 'prop/b', 'prop/c'], session)
    assert report['imported'] == ['prop/a'] and recorded(game, 'a')
    assert list(report['failed']) == ['prop/b'] and not recorded(game, 'b')
    assert content(game, 'b') == b'old b'                      # b's partial write was restored
    assert report['not_run'] == ['prop/c'] and content(game, 'c') == b'old c' and not recorded(game, 'c')
    assert report['interrupted'] and 'exited 1' in report['interrupted']
    assert session.calls == 1


def test_a_clean_exit_leaves_the_unreached_job_for_the_next_session(game):
    session = FakeSession(game, stop_after=1)
    report = batch(game, ['prop/a', 'prop/b', 'prop/c'], session)
    assert report['imported'] == ['prop/a', 'prop/b', 'prop/c'] and report['interrupted'] is None
    assert session.calls == 3                       # one job per clean session: b and c wait for the next ones


def test_static_mesh_chunks_are_headless_and_texture_chunks_stay_rendered(game):
    texture = game / 'assets/textures/t'
    write(texture / 'src/model.glb', b'tex')
    write(texture / 'asset.toml', f"""schema = 1
id = "texture/t"
kind = "texture"
authority = "generated"
owner = "region/w04-skatepark"
[[sources]]
path = "src/model.glb"
sha256 = "{sha(b'tex')}"
[recipe]
importer = "texture"
version = 1
[[outputs]]
package = "/Game/Props/T_Tex"
""")
    write(game / 'unreal/Content/Props/T_Tex.uasset', b'old tex')
    session = FakeSession(game)
    report = batch(game, ['prop/a', 'prop/b', 'texture/t'], session, size=3)
    assert report['imported'] == ['prop/a', 'prop/b', 'texture/t']
    assert session.headless_calls == [True, False]           # the two meshes, then the texture on its own


def test_a_session_that_dies_restores_only_the_unfinished_assets(game):
    session = FakeSession(game, crash_during='prop/b')
    report = batch(game, ['prop/a', 'prop/b', 'prop/c'], session)
    assert report['imported'] == ['prop/a'] and recorded(game, 'a')
    assert content(game, 'b') == b'old b' and not recorded(game, 'b')
    assert content(game, 'c') == b'old c' and not recorded(game, 'c')
    assert report['interrupted'] and 'crashed' in report['interrupted']
    assert session.calls == 1                                  # a dead session is not retried in this run


def test_an_unrecorded_write_or_a_stray_write_fails_only_that_asset(game):
    session = FakeSession(game, skip_write={'prop/b'}, stray=('prop/c', 'unreal/Content/Props/Stray.uasset'))
    report = batch(game, ['prop/a', 'prop/b', 'prop/c'], session)
    assert report['imported'] == ['prop/a']
    assert 'was not written by its job' in report['failed']['prop/b'] and content(game, 'b') == b'old b'
    assert 'outside' in report['failed']['prop/c'] and content(game, 'c') == b'old c'


def test_a_rerun_starts_no_session(game):
    batch(game, ['prop/a', 'prop/b', 'prop/c'], FakeSession(game))
    session = FakeSession(game)
    report = batch(game, ['prop/a', 'prop/b', 'prop/c'], session)
    assert report['unchanged'] == ['prop/a', 'prop/b', 'prop/c'] and report['imported'] == []
    assert session.calls == 0


def test_batch_size_bounds_the_jobs_per_session(game):
    session = FakeSession(game)
    report = batch(game, ['prop/a', 'prop/b', 'prop/c'], session, size=2)
    assert report['imported'] == ['prop/a', 'prop/b', 'prop/c'] and session.calls == 2


def test_run_session_streams_the_output_and_reads_the_summary_and_the_failed_job(game, tmp_path, monkeypatch):
    driver = tmp_path / 'session.py'
    driver.write_text("KINDS = ('import',)\n")          # a driver that knows the import kind
    monkeypatch.setattr(run, 'SESSION', driver)
    jobs = tmp_path / 'JOBS.json'
    jobs.write_text(json.dumps({'jobs': [{'kind': 'import', 'asset': 'prop/a'}, {'kind': 'import', 'asset': 'prop/b'},
                                         {'kind': 'import', 'asset': 'prop/c'}]}))
    summary = tmp_path / 'summary.json'
    summary.write_text(json.dumps({'jobs': [{'name': 'import prop/a', 'asset': 'prop/a', 'seconds': 1., 'written': ['x']}]}))
    output = [f'editor session 1234 closed (exit 1); summary {summary}\n', 'editor session failed: job 2 import prop/b: '
              'import script raised\n']
    started = []

    class FakeProcess:
        def __init__(self, command, **kwargs):
            started.append((command, kwargs))
            self.stdout = iter(output)

        def wait(self):
            return 1

    monkeypatch.setattr(run, 'subprocess', types.SimpleNamespace(Popen=FakeProcess, PIPE=-1, STDOUT=-2))
    log = tmp_path / 'logs' / 'session-1.log'
    outcome = run.run_session(jobs, log_file=log, headless=True)
    assert outcome.exit_code == 1
    assert outcome.results['prop/a'] == {'status': 'done', 'error': None, 'written': ['x']}
    assert outcome.results['prop/b']['status'] == 'failed' and 'import script raised' in outcome.results['prop/b']['error']
    assert outcome.results['prop/c']['status'] == 'not-run'
    assert log.read_text() == ''.join(output)                 # streamed to the log file as it ran
    assert started[0][0][-1] == '--headless'


def test_the_default_session_refuses_to_start_when_it_has_no_import_job_kind(game, tmp_path, monkeypatch):
    """Today's session.py knows no 'import' job: the default runner says so before it starts an editor."""
    jobs = tmp_path / 'JOBS.json'
    jobs.write_text('{"jobs": []}')
    no_import = tmp_path / 'session.py'
    no_import.write_text("KINDS = ('objects', 'script')\n")
    started = []
    monkeypatch.setattr(run, 'SESSION', no_import)
    monkeypatch.setattr(run, 'subprocess', types.SimpleNamespace(Popen=lambda *a, **k: started.append(a)))
    with pytest.raises(run.BatchCrash, match="no 'import' job kind"):
        run.run_session(jobs, log_file=tmp_path / 'session.log')
    assert started == []
    report = batch(game, ['prop/a'], run.run_session)
    assert report['imported'] == [] and report['interrupted']
    assert content(game, 'a') == b'old a' and not recorded(game, 'a')


def test_a_batch_is_authorized_by_one_check_before_any_write(game, monkeypatch):
    """Each protected check reads the claim's locks from the remote: a batch makes one check for all its writes."""
    calls = []
    monkeypatch.setattr(run.authority, 'authorize', lambda paths, claim, what, scopes=(): calls.append((paths, scopes)))
    report = run.import_batch(game, ['prop/a', 'prop/b', 'prop/c'], engine='5.8.2-1', claim='T1', batch_size=2,
                              runner=FakeSession(game), echo=lambda *_: None)
    assert report['imported'] == ['prop/a', 'prop/b', 'prop/c']
    assert len(calls) == 1 and len(calls[0][1]) == 3


@pytest.mark.parametrize("fail_texture", [False, True])
def test_mixed_dependency_fanout_uses_ready_kind_sessions(game, monkeypatch, fail_texture):
    """DFS interleaves each material with its textures; accepted textures feed one later material session.
    An interrupted texture session keeps its finished receipts, and the retry does not import them again."""
    write(game / 'assets/materials/base/asset.toml', '''schema = 1
id = "material/base"
kind = "material"
authority = "editor"
owner = "region/w04-skatepark"
[[outputs]]
package = "/Game/Props/M_Base"
''')
    write(game / 'unreal/Content/Props/M_Base.uasset', b'base')
    write(game / 'assets/materials/base/verified.json', json.dumps({
        'schema': 1, 'kind': 'editor-saved', 'engine': '5.8.2-1',
        'files': {'unreal/Content/Props/M_Base.uasset': sha(b'base')}}))
    for name in ('a', 'b', 'c', 'shared'):
        write(game / f'assets/textures/{name}/src/image.png', name)
        write(game / f'assets/textures/{name}/asset.toml', f'''schema = 1
id = "texture/{name}"
kind = "texture"
authority = "generated"
owner = "region/w04-skatepark"
[[sources]]
path = "src/image.png"
sha256 = "{sha(name.encode())}"
[recipe]
importer = "texture"
version = 1
[[outputs]]
package = "/Game/Props/T_{name}"
''')
    for name in ('a', 'b', 'c'):
        write(game / f'assets/materials/{name}/asset.toml', f'''schema = 1
id = "material/{name}"
kind = "material-instance"
authority = "generated"
owner = "region/w04-skatepark"
input_dependencies = ["material/base", "texture/{name}", "texture/shared"]
[recipe]
importer = "material-instance"
version = 2
[recipe.settings]
parent = "/Game/Props/M_Base"
textures = {{Tex = "/Game/Props/T_{name}", Shared = "/Game/Props/T_shared"}}
[[outputs]]
package = "/Game/Props/MI_{name}"
''')
    prepare = run._prepare_batch
    prepared_materials = []

    def checked_prepare(game, asset, by_id, **kwargs):
        if asset.kind == 'material-instance':
            for dep in asset.input_dependencies:
                receipt = records.load_verified(by_id[dep].verified)
                if dep.startswith('texture/'):
                    assert receipt['kind'] == 'imported'
                    assert all((game / rel).read_bytes() == f'imported {dep}'.encode()
                               for rel in receipt['files'])
            prepared_materials.append(asset.id)
        return prepare(game, asset, by_id, **kwargs)

    monkeypatch.setattr(run, '_prepare_batch', checked_prepare)
    ids = ['texture/a', 'texture/b', 'texture/c', 'texture/shared']
    if fail_texture:
        interrupted = FakeSession(game, fail={'texture/b'})
        report = batch(game, ids, interrupted, size=10)
        assert report['imported'] == ['texture/a', 'texture/shared']
        assert report['interrupted'] and interrupted.calls == 1
        assert prepared_materials == []
    session = FakeSession(game)
    report = batch(game, ids, session, size=10)
    assert session.calls == 2 and session.headless_calls == [False, False]
    assert not report['failed'] and report['interrupted'] is None
    assert prepared_materials == ['material/a', 'material/b', 'material/c']
    assert report['imported'][-3:] == prepared_materials
    if fail_texture:
        assert report['unchanged'] == ['texture/a', 'texture/shared']
        assert report['imported'][:2] == ['texture/b', 'texture/c']
    else:
        assert report['imported'][:4] == ['texture/a', 'texture/shared', 'texture/b', 'texture/c']


def test_unchanged_first_asset_advances_across_a_kind_dependency_chain(game):
    """An accepted mesh -> texture -> mesh chain can drain its first kind without starting a session."""
    first = batch(game, ['prop/a'], FakeSession(game))
    assert first['imported'] == ['prop/a']
    write(game / 'assets/textures/bridge/src/image.png', b'bridge')
    write(game / 'assets/textures/bridge/asset.toml', f'''schema = 1
id = "texture/bridge"
kind = "texture"
authority = "generated"
owner = "region/w04-skatepark"
input_dependencies = ["prop/a"]
[[sources]]
path = "src/image.png"
sha256 = "{sha(b'bridge')}"
[recipe]
importer = "texture"
version = 1
[[outputs]]
package = "/Game/Props/T_Bridge"
''')
    mesh = game / 'assets/props/c/asset.toml'
    mesh.write_text(mesh.read_text().replace('[[sources]]', 'input_dependencies = ["texture/bridge"]\n[[sources]]'))
    session = FakeSession(game)
    report = batch(game, ['prop/a'], session)
    assert report['unchanged'] == ['prop/a']
    assert report['imported'] == ['texture/bridge', 'prop/c']
    assert not report['failed'] and report['interrupted'] is None
    assert session.headless_calls == [False, True]
