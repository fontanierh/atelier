"""The ski lab's physics checks (platform/web/ski-lab) run under Node's test runner."""
import shutil
import subprocess

import pytest

from atelier import paths


def test_ski_lab_physics():
    if not shutil.which('node'):
        pytest.skip('node is not installed')
    lab = paths.PLATFORM / 'web' / 'ski-lab'
    result = subprocess.run(['node', '--test', 'test_ski.mjs'], cwd=lab, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
