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


@pytest.mark.parametrize('fail',[False,True])
def test_explicit_source_ambient_is_scoped_and_restored_on_export_failure(monkeypatch,fail):
    previous=SimpleNamespace(color=[.3,.2,.1]);scene=SimpleNamespace(world=previous)
    created=[];removed=[];seen=[]
    def new(name):
        world=SimpleNamespace(color=[0,0,0]);created.append(world);return world
    monkeypatch.setitem(sys.modules,'bpy',SimpleNamespace(
        context=SimpleNamespace(scene=scene,selected_objects=[mesh('Part',12)]),
        data=SimpleNamespace(worlds=SimpleNamespace(new=new,remove=removed.append))))
    def write(**options):
        seen.append(list(scene.world.color));assert 'scene_world_color' not in options
        if fail:raise RuntimeError('serializer failed')
        return {'FINISHED'}
    monkeypatch.setattr(fbx,'export_fbx',write)
    def run():return fbx.export_atomic_fbx(filepath='part.fbx',use_selection=True,object_types={'MESH'},
        scene_world_color=[.05,.05,.05])
    if fail:
        with pytest.raises(RuntimeError,match='serializer failed'):run()
    else:assert run()=={'FINISHED'}
    assert seen==[[.05,.05,.05]] and scene.world is previous and previous.color==[.3,.2,.1]
    assert removed==created and len(created)==1


@pytest.mark.parametrize('value',[[float('nan'),0,0],[0,0],[0,0,2],[False,0,0],'default'])
def test_invalid_ambient_refuses_without_creating_scene_or_export(monkeypatch,value):
    calls,run=export(monkeypatch,[mesh('Part',12)])
    with pytest.raises(ValueError,match='world colour'):
        fbx.export_atomic_fbx(filepath='part.fbx',use_selection=True,object_types={'MESH'},scene_world_color=value)
    assert calls==[]


def test_captured_ambient_retains_actual_float_values_without_aliasing_source():
    color=[.05000000074505806]*3;scene=SimpleNamespace(world=SimpleNamespace(color=color))
    result=fbx.world_color(scene);color[0]=.2
    assert result==[.05000000074505806]*3
    assert fbx.world_color(SimpleNamespace(world=None)) is None
