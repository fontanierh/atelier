"""Every test starts with its own open D04 switch: the committed governance.toml is closed once the slice merged, and
a test of a write route must not depend on it. A test of the closed switch sets its own file or passes a path."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools' / 'content'))
import authority  # noqa: E402


@pytest.fixture(autouse=True)
def d04_open(tmp_path_factory, monkeypatch):
    path = tmp_path_factory.mktemp('governance') / 'governance.toml'
    path.write_text(f'schema = 1\n[d04]\nwriter = "{authority.BOOTSTRAP_WRITER}"\nclosed = false\n')
    monkeypatch.setattr(authority, 'GOVERNANCE', path)
    return path
