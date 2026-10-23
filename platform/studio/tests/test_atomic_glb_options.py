"""Atomic GLB does not discard the source owner's declared modifier/image policy."""
import sys
from types import SimpleNamespace

import pytest
from atelier.blender import gltf


def test_declared_geometry_policy_reaches_the_actual_export_call(monkeypatch):
    calls = []
    monkeypatch.setattr(gltf, 'validate_atomic_selection', lambda **_: None)
    def export(**options):
        calls.append(options)
        return {'FINISHED'}
    monkeypatch.setitem(sys.modules, 'bpy', SimpleNamespace(ops=SimpleNamespace(
        export_scene=SimpleNamespace(gltf=export))))
    gltf.export_atomic_glb('output.glb', options={'export_apply': True, 'export_image_format': 'NONE'})
    assert len(calls) == 1 and calls[0]['export_apply'] is True
    assert calls[0]['export_image_format'] == 'NONE'
    assert calls[0]['export_all_vertex_colors'] and calls[0]['export_texcoords']
    assert calls[0]['export_skins'] is False and calls[0]['export_animations'] is False


@pytest.mark.parametrize('options', [{'export_yup': False}, {'export_apply': 1},
                                   {'export_image_format': 'AUTO'}])
def test_unrepresented_export_settings_refuse_before_importing_blender(monkeypatch, options):
    monkeypatch.delitem(sys.modules, 'bpy', raising=False)
    with pytest.raises(ValueError):
        gltf.export_atomic_glb('output.glb', options=options)


def test_finite_image_free_graph_uses_original_shader_traversal(monkeypatch):
    from atelier import mesh_materials
    material = SimpleNamespace(type='MESH'); calls = []; checked = []
    monkeypatch.setattr(gltf, 'validate_atomic_selection', lambda **_: None)
    monkeypatch.setattr(mesh_materials, 'capture_slots', lambda obj: checked.append(obj))
    monkeypatch.setitem(sys.modules, 'bpy', SimpleNamespace(context=SimpleNamespace(selected_objects=[material]),
        ops=SimpleNamespace(export_scene=SimpleNamespace(gltf=lambda **kw: calls.append(kw) or {'FINISHED'}))))
    gltf.export_atomic_glb('output.glb', options={'export_apply': True}, finite_materials=True)
    assert checked == [material] and calls[0]['export_image_format'] == 'AUTO'
    def unsupported(_): raise ValueError('image or unsupported graph')
    monkeypatch.setattr(mesh_materials, 'capture_slots', unsupported)
    with pytest.raises(ValueError, match='unsupported graph'):
        gltf.export_atomic_glb('output.glb', finite_materials=True)
    assert len(calls) == 1
