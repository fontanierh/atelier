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

    def __init__(self, game, *, fail=(), crash_during=None, stray=None, skip_write=()):
        self.game, self.fail, self.crash_during = game, set(fail), crash_during
        self.stray, self.skip_write = stray, set(skip_write)
        self.calls = 0

    def __call__(self, jobs_file):
        self.calls += 1
        jobs = json.loads(jobs_file.read_text())['jobs']
        results = {}
        for job in jobs:
            asset = job['asset']
            plan = json.loads(Path(job['plan']).read_text())
            if asset == self.crash_during:
                for package in plan['packages']:            # the editor wrote part of it, then died
                    write(records.package_files(self.game, package)[0], b'half written')
                raise run.BatchCrash('the editor crashed', results)
            if asset in self.fail:
                for package in plan['packages']:
                    write(records.package_files(self.game, package)[0], b'partial')
                results[asset] = {'status': 'failed', 'error': 'import script raised', 'written': []}
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
        return results


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


def test_failure_restores_only_its_files_and_the_unreached_job_runs_in_the_next_session(game):
    session = FakeSession(game, fail={'prop/b'})
    report = batch(game, ['prop/a', 'prop/b', 'prop/c'], session)
    assert report['imported'] == ['prop/a', 'prop/c']
    assert list(report['failed']) == ['prop/b'] and report['interrupted'] is None
    assert content(game, 'b') == b'old b'                      # b's partial write was restored
    assert not recorded(game, 'b') and recorded(game, 'a') and recorded(game, 'c')
    assert session.calls == 2                                  # c waited for the second session


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


def test_run_session_reads_the_failed_job_and_the_summary_of_the_others(game, tmp_path, monkeypatch):
    driver = tmp_path / 'session.py'
    driver.write_text("KINDS = ('import',)\n")          # a driver that knows the import kind
    monkeypatch.setattr(run, 'SESSION', driver)
    jobs = tmp_path / 'JOBS.json'
    jobs.write_text(json.dumps({'jobs': [{'kind': 'import', 'asset': 'prop/a'}, {'kind': 'import', 'asset': 'prop/b'},
                                         {'kind': 'import', 'asset': 'prop/c'}]}))
    summary = tmp_path / 'summary.json'
    summary.write_text(json.dumps({'jobs': [{'name': 'import prop/a', 'seconds': 1., 'written': ['x']}]}))
    stdout = f'session nonce closed (exit 1); summary {summary}\nediter\n'
    stderr = 'editor session failed: job 2 import prop/b: import script raised'
    monkeypatch.setattr(run, 'subprocess', types.SimpleNamespace(
        run=lambda *a, **k: subprocess.CompletedProcess(a, 1, stdout, stderr)))
    results = run.run_session(jobs)
    assert results['prop/a'] == {'status': 'done', 'error': None, 'written': ['x']}
    assert results['prop/b']['status'] == 'failed' and 'import script raised' in results['prop/b']['error']
    assert results['prop/c']['status'] == 'not-run'


def test_the_default_session_refuses_to_start_when_it_has_no_import_job_kind(game, tmp_path, monkeypatch):
    """Today's session.py knows no 'import' job: the default runner says so before it starts an editor."""
    jobs = tmp_path / 'JOBS.json'
    jobs.write_text('{"jobs": []}')
    no_import = tmp_path / 'session.py'
    no_import.write_text("KINDS = ('objects', 'script')\n")
    started = []
    monkeypatch.setattr(run, 'SESSION', no_import)
    monkeypatch.setattr(run, 'subprocess', types.SimpleNamespace(run=lambda *a, **k: started.append(a)))
    with pytest.raises(run.BatchCrash, match="no 'import' job kind"):
        run.run_session(jobs)
    assert started == []
    report = batch(game, ['prop/a'], lambda jobs_file: run.run_session(jobs_file))
    assert report['imported'] == [] and report['interrupted']
    assert content(game, 'a') == b'old a' and not recorded(game, 'a')
