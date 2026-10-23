"""Exercise CI selection through pytest, including new files and failure propagation."""
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

from ci_tests import GROUPS, CollectionGroup, group_for

RUNNER = Path(__file__).with_name('ci_tests.py')


def run_group(root, group):
    report = root / f'{group}.json'
    result = subprocess.run(
        [sys.executable, str(RUNNER), group, '--collection-report', str(report), '-q'],
        cwd=root, env={**os.environ, 'ATELIER_CI_WORKERS': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'PYTEST_ADDOPTS': ''},
        capture_output=True, text=True, timeout=20)
    return result, json.loads(report.read_text()) if report.exists() else None


def test_groups_cover_normal_collection_once(tmp_path):
    (tmp_path / 'pytest.ini').write_text('[pytest]\ntestpaths = platform games future\n')
    files = {
        'platform/studio/tests/test_board_new.py': 'board',
        'platform/harness/tests/test_board_harness_new.py': 'board',
        'platform/harness/tests/test_capacity_new.py': 'studio',
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


def test_multi_worker_shards_preserve_collection_and_merge_junit(tmp_path):
    (tmp_path / 'pytest.ini').write_text('[pytest]\ntestpaths = games\n')
    for idx in range(3):
        path = tmp_path / f'games/new/tests/test_part_{idx}.py'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'def test_case_{idx}():\n    assert {idx} >= 0\n')
    report = tmp_path / 'games.json'
    junit = tmp_path / 'results.xml'
    result = subprocess.run(
        [sys.executable, str(RUNNER), 'games',
         '--collection-report', str(report), f'--junitxml={junit}', '-q'],
        cwd=tmp_path, env={**os.environ, 'ATELIER_CI_WORKERS': '2', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'PYTEST_ADDOPTS': ''},
        capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(report.read_text())
    assert len(data['selected']) == 3
    tree = ET.parse(junit)
    names = {tc.attrib['name'] for tc in tree.iter('testcase')}
    assert names == {'test_case_0', 'test_case_1', 'test_case_2'}


class _Item:
    def __init__(self, nodeid, markers=()):
        self.nodeid = nodeid
        self._markers = markers

    def iter_markers(self):
        return [SimpleNamespace(name=name) for name in self._markers]


class _Config:
    class hook:
        @staticmethod
        def pytest_deselected(items):
            pass


def _shard(group, index, count, nodeids):
    items = [_Item(nodeid) for nodeid in nodeids]
    CollectionGroup(group, None, index, count).pytest_collection_modifyitems(_Config(), items)
    return [item.nodeid for item in items]


def test_machine_wide_render_tests_stay_on_one_worker_and_cover_every_node_once():
    """Harness tests create or observe Blender/UnrealEditor processes; another worker scanning the
    process table would see them as foreign. They must stay on one shard, and every node must still
    run exactly once."""
    nodeids = ([f'platform/harness/tests/test_capacity_{i}.py::test_{i}' for i in range(4)]
               + [f'platform/harness/tests/test_board_like.py::test_{i}' for i in range(2)]
               + [f'platform/studio/tests/test_plain_{i}.py::test_{i}' for i in range(9)]
               + [f'games/x/tests/test_game_{i}.py::test_{i}' for i in range(3)])
    shards = [_shard('studio', index, 3, nodeids) for index in range(3)]
    flat = [node for shard in shards for node in shard]
    assert sorted(flat) == sorted(set(flat)), 'a node ran on more than one shard'
    expected = {n for n in nodeids if 'harness/tests/test_board_like' not in n and not n.startswith('games/')}
    assert set(flat) == expected
    assert all(node.startswith('platform/harness/') is False for shard in shards[1:] for node in shard)
    assert any(node.startswith('platform/harness/') for node in shards[0])


def test_macos_only_tests_run_in_the_macos_job():
    """A skip in a Linux group would leave these unexercised, so they belong to the only job on a
    macOS runner. The marker alone decides it: a path would name a game from platform code."""
    for nodeid in ('games/x/tests/test_packaging.py::test_app',
                   'games/x/tests/test_layers.py::TestLayers::test_digest',
                   'platform/studio/tests/test_portable.py::test_example'):
        assert group_for(nodeid, {'macos_only'}) == 'board'
    assert group_for('games/x/tests/test_other.py::test_example', {'slow'}) == 'games'
    assert group_for('platform/studio/tests/test_other.py::test_example') == 'studio'


def test_a_macos_only_test_runs_on_exactly_one_group(tmp_path):
    """Routing by marker must not lose or duplicate a node in the partition."""
    (tmp_path / 'pytest.ini').write_text('[pytest]\nmarkers =\n    macos_only: needs macOS\n'
                                        'testpaths = games\n')
    portable = tmp_path / 'games/x/tests/test_portable.py'
    portable.parent.mkdir(parents=True)
    portable.write_text('def test_linux() -> None:\n    pass\n')
    mac = tmp_path / 'games/x/tests/test_mac.py'
    mac.write_text('import pytest\n\npytestmark = pytest.mark.macos_only\n\n'
                   'def test_mac() -> None:\n    pass\n')
    selected = {}
    for group in ('board', 'games'):
        result, report = run_group(tmp_path, group)
        assert result.returncode == 0, result.stdout + result.stderr
        selected[group] = report['selected']
        assert set(report['collected']) == {'games/x/tests/test_mac.py::test_mac',
                                            'games/x/tests/test_portable.py::test_linux'}
    assert selected['board'] == ['games/x/tests/test_mac.py::test_mac']
    assert selected['games'] == ['games/x/tests/test_portable.py::test_linux']
