"""Planning cannot silently drop evaluated static geometry before export admission."""
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize('kind,modifiers,shape_keys', [
    ('CURVE', [], None), ('MESH', ['ARRAY'], None), ('MESH', [], object())])
def test_unfinished_geometry_is_refused_before_creating_output(tmp_path, monkeypatch, kind, modifiers, shape_keys):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'world'))
    planner = importlib.import_module('region_mesh_parts')
    obj = SimpleNamespace(name='Part', type=kind, modifiers=modifiers,
                          data=SimpleNamespace(shape_keys=shape_keys))
    root = tmp_path / 'planned'
    with pytest.raises(ValueError, match='completed static mesh'):
        planner.plan(obj, root)
    assert not root.exists()
