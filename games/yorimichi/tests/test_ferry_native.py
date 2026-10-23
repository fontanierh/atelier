"""Ferry saved-candidate checks are read-only and reject wrong current native state."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

GAME = Path(__file__).resolve().parents[1]


@pytest.fixture
def native(monkeypatch):
    editor = SimpleNamespace(get_simple_collision_count=lambda mesh: mesh.simple,
        get_convex_collision_count=lambda mesh: mesh.hulls)
    unreal = SimpleNamespace(StaticMeshEditorSubsystem=object(), get_editor_subsystem=lambda kind: editor,
        CollisionTraceFlag=SimpleNamespace(CTF_USE_SIMPLE_AS_COMPLEX='simple'))
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    monkeypatch.setitem(sys.modules, 'forest_native', SimpleNamespace(hulls_match=lambda mesh, hulls: mesh.hulls == len(hulls)))
    spec = importlib.util.spec_from_file_location('ferry_native_test', GAME / 'unreal/Scripts/ferry_native.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


class Mesh:
    simple = hulls = 0
    triangles = 12
    lods = 1
    path = '/Game/Ferry/Ship/FY_Hull.FY_Hull'
    slot = 'FY_WhitePaint'
    material = 'current white'

    @property
    def static_materials(self):
        return [SimpleNamespace(get_editor_property=lambda field: self.slot)]

    def get_path_name(self): return self.path
    def get_num_lods(self): return self.lods
    def get_num_triangles(self, level): return self.triangles
    def get_material(self, index): return self.material


@pytest.mark.parametrize('defect', ['triangles', 'lods', 'simple', 'hulls', 'slot', 'material', 'path'])
def test_saved_candidate_refuses_current_geometry_or_material_mismatch(native, defect):
    mesh = Mesh()
    state = dict(entries=dict(FY_Hull=dict(triangles=12, metadata=dict(slots=['FY_WhitePaint']))), hulls=[])
    materials = dict(FY_WhitePaint='current white')
    assert native.reusable(mesh, 'FY_Hull', state, materials)
    setattr(mesh, defect, 'wrong' if defect in ('slot', 'material', 'path') else 99)
    assert not native.reusable(mesh, 'FY_Hull', state, materials)
