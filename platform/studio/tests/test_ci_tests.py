"""Exercise CI selection through pytest, including new files and failure propagation."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from ci_tests import GROUPS

RUNNER = Path(__file__).with_name('ci_tests.py')


def run_group(root, group):
    report = root / f'{group}.json'
    result = subprocess.run(
        [sys.executable, str(RUNNER), group, '--collection-report', str(report), '-q'],
        cwd=root, env={**os.environ, 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'PYTEST_ADDOPTS': ''},
        capture_output=True, text=True, timeout=20)
    return result, json.loads(report.read_text()) if report.exists() else None


def test_groups_cover_normal_collection_once(tmp_path):
    (tmp_path / 'pytest.ini').write_text('[pytest]\ntestpaths = platform games future\n')
    files = {
        'platform/studio/tests/test_board_new.py': 'board',
        'platform/studio/tests/test_new.py': 'studio',
        'games/new/tests/test_new_game.py': 'games',
        'future/test_new_location.py': 'studio',
    }
    for name in files:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('import pytest\n@pytest.mark.parametrize("value", [0, 1])\n'
                        'def test_example(value):\n    assert value >= 0\n')
    expected = {f'{path}::test_example[{value}]' for path in files for value in (0, 1)}
    seen = set()
    for group in GROUPS:
        result, report = run_group(tmp_path, group)
        assert result.returncode == 0, result.stdout + result.stderr
        assert set(report['collected']) == expected
        selected = report['selected']
        assert len(selected) == len(set(selected))
        assert not seen.intersection(selected)
        assert set(selected) == {node for node in expected if files[node.split('::')[0]] == group}
        assert selected == [node for node in report['collected'] if node in selected]
        seen.update(selected)
    assert seen == expected


@pytest.mark.parametrize(('source', 'group', 'exit_code'), [
    ('def test_bad():\n    assert False\n', 'studio', 1),
    ('invalid python !\n', 'studio', 2),
    ('def test_ok():\n    pass\n', 'board', 5),
])
def test_pytest_failures_still_fail(tmp_path, source, group, exit_code):
    (tmp_path / 'pytest.ini').write_text('[pytest]\n')
    (tmp_path / 'test_case.py').write_text(source)
    result, _ = run_group(tmp_path, group)
    assert result.returncode == exit_code, result.stdout + result.stderr
