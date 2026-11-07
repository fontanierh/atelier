"""Retired suites never execute, even when a caller explicitly selects one."""
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
POLICY = runpy.run_path(str(ROOT / 'conftest.py'))
RETIRED_TREES = POLICY['_RETIRED_TEST_TREES']
RETIRED_FILES = [p.replace('*', 'probe') for p in POLICY['_RETIRED_TEST_FILES']]
RUNNER = ROOT / 'platform/studio/tests/ci_tests.py'


@pytest.fixture
def suite(tmp_path):
    shutil.copy2(ROOT / 'conftest.py', tmp_path / 'conftest.py')
    (tmp_path / 'pytest.ini').write_text('[pytest]\ntestpaths = games platform\n')
    for name in [*(f'{p}/tests/test_retired.py' for p in RETIRED_TREES), *RETIRED_FILES]:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('raise RuntimeError("retired test was imported")\n')
    for name in ('games/current/tests/test_active.py', 'platform/studio/tests/test_active.py'):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('def test_active():\n    pass\n')
    return tmp_path


def invoke(root, args, cwd=None):
    return subprocess.run(
        [sys.executable, *args], cwd=cwd or root, text=True, capture_output=True, timeout=20,
        env={**os.environ, 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'PYTEST_ADDOPTS': '',
             'ATELIER_CI_WORKERS': '1'})


def test_plain_pytest_never_imports_retired_suites(suite):
    result = invoke(suite, ['-m', 'pytest', '-q', '--import-mode=importlib'])
    assert result.returncode == 0, result.stdout + result.stderr
    assert '2 passed' in result.stdout


@pytest.mark.parametrize('group', ['studio', 'games'])
def test_ci_collects_the_same_active_suite(suite, group):
    report = suite / 'collection.json'
    result = invoke(suite, [str(RUNNER), group, '--collection-report', str(report),
                            '-q', '--import-mode=importlib'])
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(report.read_text())
    assert set(data['collected']) == {
        'games/current/tests/test_active.py::test_active',
        'platform/studio/tests/test_active.py::test_active',
    }
    assert len(data['selected']) == 1


@pytest.mark.parametrize('requested', [
    *RETIRED_TREES,
    *(f'{p}/tests/test_retired.py' for p in RETIRED_TREES),
    *(f'{p}/tests/test_retired.py::test_old' for p in RETIRED_TREES),
    *RETIRED_FILES,
])
def test_explicit_retired_paths_are_refused(suite, requested):
    result = invoke(suite, ['-m', 'pytest', '-q', requested])
    assert result.returncode == pytest.ExitCode.USAGE_ERROR, result.stdout + result.stderr
    assert 'Retired experiment tests are disabled' in result.stderr
    assert 'retired test was imported' not in result.stdout + result.stderr


@pytest.mark.parametrize('retired', RETIRED_TREES)
def test_invocation_inside_a_retired_tree_is_refused(suite, retired):
    result = invoke(suite, ['-m', 'pytest', '-q'], cwd=suite / retired / 'tests')
    assert result.returncode == pytest.ExitCode.USAGE_ERROR, result.stdout + result.stderr
    assert 'Retired experiment tests are disabled' in result.stderr
