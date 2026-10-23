"""The export boundary rejects a region-sized selection before writing bytes."""
import sys
from types import SimpleNamespace
import pytest
from atelier.blender import fbx


def mesh(name, triangles):
    return SimpleNamespace(name=name, type='MESH', modifiers=[],
                           data=SimpleNamespace(calc_loop_triangles=lambda: None,
                                                loop_triangles=[None] * triangles))


def export(monkeypatch, selected):
    calls = []
    monkeypatch.setitem(sys.modules, 'bpy', SimpleNamespace(context=SimpleNamespace(selected_objects=selected)))
    monkeypatch.setattr(fbx, 'export_fbx', lambda **options: calls.append(options) or {'FINISHED'})
    return calls, lambda: fbx.export_atomic_fbx(filepath='part.fbx', use_selection=True, object_types={'MESH'})


def test_one_small_mesh_and_only_its_hulls_are_exported(monkeypatch):
    calls, run = export(monkeypatch, [mesh('Part', 12), mesh('UCX_Part_00', 12)])
    assert run() == {'FINISHED'}
    assert len(calls) == 1


@pytest.mark.parametrize('selected', [[mesh('Huge', 32769)],
    [mesh('One', 12), mesh('Two', 12)], [mesh('One', 12), mesh('UCX_Foreign_00', 12)], []])
def test_large_or_nonatomic_exports_refuse_before_exporter(monkeypatch, selected):
    calls, run = export(monkeypatch, selected)
    with pytest.raises(ValueError): run()
    assert calls == []


def test_unapplied_modifier_cannot_hide_extra_geometry(monkeypatch):
    obj = mesh('Part', 12); obj.modifiers = [SimpleNamespace(type='ARRAY')]
    calls, run = export(monkeypatch, [obj])
    with pytest.raises(ValueError): run()
    assert calls == []
