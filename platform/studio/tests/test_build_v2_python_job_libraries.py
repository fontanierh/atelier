"""The Python job child imports installed libraries only from the loop's declared folders (portable).

The child runs with -P -s -S, so it never derives the loop's venv itself. These tests start the child
exactly as the loop does, with a configuration built by the loop's own `job_config`, on any host.
A Linux pass is not macOS sandbox evidence.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from atelier.build_v2 import python_job, python_worker

REPO = Path(__file__).resolve().parents[3]

PROBE = '''
import json
import os
import sys

def run(context):
    found = {}
    for name in context.params['modules']:
        try:
            found[name] = __import__(name).VALUE
        except ImportError:
            found[name] = None
    context.output('probe.json').write_text(json.dumps({
        'path': sys.path, 'modules': found, 'pth_ran': os.environ.get('ATELIER_PTH_RAN'),
        'site_loaded': 'site' in sys.modules,
        'flags': {'no_site': sys.flags.no_site, 'no_user_site': sys.flags.no_user_site,
                  'safe_path': sys.flags.safe_path},
    }))
'''


class Libraries(python_worker.Platform):
    """The interpreter's own platform plus a test platform root, with chosen installed-library folders."""

    def __init__(self, root, folders):
        self.root = str(root)
        self.folders = [str(folder) for folder in folders]

    def import_roots(self):
        return sorted({*python_worker.interpreter_roots(), self.root})

    def reads(self):
        subpaths, literals = python_worker.platform_reads()
        return subpaths + [self.root], literals

    def site_libraries(self):
        return self.folders


def package(folder, name, value):
    (folder / name).mkdir(parents=True)
    (folder / name / '__init__.py').write_text(f'VALUE = {value!r}\n', encoding='utf-8')


def run_child(tmp_path, platform, modules=()):
    """One job child, started as the loop starts it; returns (report, probe or None)."""
    job_dir = tmp_path / 'job'
    (job_dir / 'ops').mkdir(parents=True)
    (job_dir / 'output').mkdir()
    (job_dir / 'ops/run.py').write_text(PROBE, encoding='utf-8')
    job = {'job_id': 'job-1', 'unit': 'u', 'op': {'kind': 'py', 'version': '1'}, 'job_dir': str(job_dir),
           'script': 'ops/run.py', 'code': ['ops/run.py'], 'inputs': [], 'params': {'modules': list(modules)},
           'outputs': [{'path': 'probe.json', 'required': True}]}
    result_read, result_write = os.pipe()
    config = python_worker.job_config(job, str(job_dir), result_write, platform)
    child = subprocess.Popen([sys.executable, *python_worker.CHILD_FLAGS, '-c', python_worker.JOB_SOURCE],
                             cwd=job_dir, env=dict(python_worker.JOB_ENVIRONMENT), stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, pass_fds=(result_write,))
    os.close(result_write)
    logs, _ = child.communicate(json.dumps(config).encode('utf-8'), timeout=60)
    with os.fdopen(result_read, 'rb') as results:
        report = json.loads(results.read() or b'null')
    probe = job_dir / 'output/probe.json'
    return report, (json.loads(probe.read_text()) if probe.exists() else None), logs.decode(errors='replace')


def test_the_child_keeps_no_site_flags_and_runs_no_pth_file(tmp_path):
    assert {'-P', '-s', '-S'} <= set(python_worker.CHILD_FLAGS)
    root = tmp_path / 'platform'
    site = root / 'site-packages'
    package(site, 'declared_fixture', 7)
    package(root / 'pth-target', 'pth_only_fixture', 9)
    # A .pth file adding a folder and running code: site processing would honour both.
    (site / 'zz-hook.pth').write_text(f'{root / "pth-target"}\nimport os; os.environ["ATELIER_PTH_RAN"] = "1"\n',
                                      encoding='utf-8')
    report, probe, logs = run_child(tmp_path, Libraries(root, [site]), ['declared_fixture', 'pth_only_fixture'])
    assert report == {'status': 'ok'}, logs
    assert probe['flags'] == {'no_site': 1, 'no_user_site': 1, 'safe_path': True}
    assert not probe['site_loaded']
    assert probe['pth_ran'] is None
    assert probe['modules'] == {'declared_fixture': 7, 'pth_only_fixture': None}
    assert str(root / 'pth-target') not in probe['path']


def test_declared_libraries_follow_the_standard_library_and_nothing_else_is_added(tmp_path):
    root = tmp_path / 'platform'
    site, plat = root / 'lib/site-packages', root / 'lib-dynload-site'
    package(site, 'declared_fixture', 'pure')
    plat.mkdir(parents=True)
    # An existing folder inside an approved root but not declared is never an import location.
    package(root / 'undeclared', 'undeclared_fixture', 1)
    report, probe, logs = run_child(tmp_path, Libraries(root, [site, plat, site]),
                                    ['declared_fixture', 'undeclared_fixture'])
    assert report == {'status': 'ok'}, logs
    assert probe['modules'] == {'declared_fixture': 'pure', 'undeclared_fixture': None}
    path = probe['path']
    assert path[-2:] == [str(site), str(plat)], 'declared folders are appended once, after the standard library'
    added = [entry for entry in path[1:] if Path(entry).is_relative_to(root)]
    assert added == [str(site), str(plat)]
    assert path[0] == str((tmp_path / 'job/ops').resolve())
    assert not any(Path(entry).is_relative_to(REPO) for entry in path), 'no editable or checkout path'


def test_a_venv_inside_a_checkout_is_reachable_but_its_editable_project_sources_are_not(tmp_path):
    """A venv usually lives in the checkout: its site folder is importable only as an interpreter root,
    and the editable-install `.pth` finder that would add the project sources never runs under -S."""
    checkout = tmp_path / 'checkout'
    venv = checkout / '.venv'
    site = venv / 'lib/python3/site-packages'
    package(site, 'installed_fixture', 'installed')
    package(checkout / 'src', 'project_fixture', 'project')
    (site / '__editable__.project-0.pth').write_text(f'{checkout / "src"}\n', encoding='utf-8')
    (site / '__editable___project_finder.py').write_text('raise RuntimeError("editable finder ran")\n',
                                                         encoding='utf-8')
    (site / '__editable__.finder.pth').write_text('import __editable___project_finder\n', encoding='utf-8')
    report, probe, logs = run_child(tmp_path, Libraries(venv, [site]), ['installed_fixture', 'project_fixture'])
    assert report == {'status': 'ok'}, logs
    assert probe['modules'] == {'installed_fixture': 'installed', 'project_fixture': None}
    inside = [entry for entry in probe['path'] if Path(entry).is_relative_to(checkout)]
    assert inside == [str(site)], 'only the declared venv folder, never the project sources'


def test_the_loops_own_installed_libraries_reach_the_child(tmp_path):
    """The regression: under -S the child's sysconfig no longer names the loop's venv."""
    folders = python_worker.site_libraries()
    assert folders and all(Path(folder).is_absolute() for folder in folders)
    report, probe, logs = run_child(tmp_path, python_worker.Platform())
    assert report == {'status': 'ok'}, logs
    for folder in folders:
        assert folder in probe['path']
    # The checkout may hold the venv: a checkout entry is allowed only under the interpreter's own roots.
    roots = [Path(os.path.realpath(root)) for root in python_worker.interpreter_roots()]
    for entry in probe['path'][1:]:
        real = Path(os.path.realpath(entry))
        if real.is_relative_to(REPO.resolve()):
            assert any(real.is_relative_to(root) for root in roots), entry
    for project in ('platform', 'games'):
        assert not any(Path(os.path.realpath(entry)).is_relative_to(REPO.resolve() / project)
                       for entry in probe['path']), project
    config = python_worker.job_config(
        {'script': 'ops/run.py', 'code': ['ops/run.py'], 'inputs': [], 'params': {}, 'outputs': []},
        str(tmp_path), 3)
    assert config['site_libraries'] == folders


@pytest.mark.parametrize('case', ['missing', 'file'])
def test_the_loop_passes_a_bad_scheme_folder_through_and_the_child_refuses_it(tmp_path, monkeypatch, case):
    """The loop never drops a scheme folder: a missing purelib or a file platlib fails the job."""
    root = tmp_path / 'platform'
    root.mkdir()
    (root / 'plain-file').write_text('x', encoding='utf-8')
    bad = str(root / 'missing') if case == 'missing' else str(root / 'plain-file')
    real = python_worker.sysconfig.get_paths
    good = real()['purelib']
    names = {'missing': {'purelib': bad, 'platlib': good}, 'file': {'purelib': good, 'platlib': bad}}[case]
    monkeypatch.setattr(python_worker.sysconfig, 'get_paths', lambda *args, **kwargs: {**real(*args, **kwargs),
                                                                                         **names})
    folders = python_worker.site_libraries()
    assert bad in folders, 'the loop passes every scheme folder, unfiltered'

    class Interpreter(Libraries):
        def site_libraries(self):
            return python_worker.Platform.site_libraries(self)

    report, probe, _ = run_child(tmp_path, Interpreter(root, []))
    assert report['status'] == 'failed' and report['kind'] == 'dependency', report
    assert bad in report['message']
    assert probe is None, 'the op never ran'


def test_an_undeclared_location_fails_the_job_before_it_runs(tmp_path):
    root = tmp_path / 'platform'
    root.mkdir()
    outside = tmp_path / 'outside'
    package(outside, 'outside_fixture', 1)
    report, probe, _ = run_child(tmp_path, Libraries(root, [outside]), ['outside_fixture'])
    assert report['status'] == 'failed' and report['kind'] == 'dependency', report
    assert 'outside the platform roots' in report['message']
    assert probe is None, 'the op never ran'


@pytest.mark.parametrize('case', ['outside', 'symlink-escape', 'missing', 'file', 'relative', 'not-a-string',
                                  'not-a-list', 'absent'])
def test_every_bad_installed_library_folder_is_refused(tmp_path, case):
    root = tmp_path / 'platform'
    root.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    (root / 'escape').symlink_to(outside, target_is_directory=True)
    (root / 'plain-file').write_text('x', encoding='utf-8')
    folders = {
        'outside': [str(outside)],
        'symlink-escape': [str(root / 'escape')],
        'missing': [str(root / 'missing')],
        'file': [str(root / 'plain-file')],
        'relative': ['platform'],
        'not-a-string': [7],
        'not-a-list': str(root),
        'absent': None,
    }[case]
    config = {} if folders is None else {'site_libraries': folders}
    with pytest.raises(python_job.UndeclaredModuleError):
        python_job.site_libraries(config, [os.path.realpath(root)])


def test_a_symlink_that_stays_inside_a_root_is_accepted_as_declared(tmp_path):
    root = tmp_path / 'platform'
    (root / 'real-site').mkdir(parents=True)
    (root / 'linked-site').symlink_to(root / 'real-site', target_is_directory=True)
    folders = [str(root / 'linked-site'), str(root / 'real-site'), str(root / 'linked-site')]
    assert python_job.site_libraries({'site_libraries': folders}, [os.path.realpath(root)]) == folders[:2]
