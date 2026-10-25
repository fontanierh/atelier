"""Reached package children belong to the frozen code closure, without executing them."""
from pathlib import Path

import pytest

from atelier import build


@pytest.mark.parametrize('initializers', [False, True])
@pytest.mark.parametrize('scanner_type', [build._FastImportScanner.__mro__[1], build._FastImportScanner])
def test_relative_reached_package_binds_literal_namespace_child_and_its_imports(tmp_path, initializers, scanner_type):
    files = {
        'entry.py': 'from domain.left import entry\n',
        'domain/left/entry.py': 'from ..megapark import gate\n',
        'domain/megapark/gate.py': 'def later():\n    from megapark import plants\n',
        'domain/megapark/plants.py': 'from . import leaf\nraise RuntimeError("capture must never execute modules")\n',
        'domain/megapark/leaf.py': 'VALUE = 1\n',
    }
    if initializers:
        files.update({name + '/__init__.py': '' for name in ('domain', 'domain/left', 'domain/megapark')})
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    result = scanner_type().local_imports(tmp_path / 'entry.py', (tmp_path,))
    assert set(result) == {tmp_path / name for name in files}
    assert all(isinstance(path, Path) for path in result)
