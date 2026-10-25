"""The actual coastal constructor captures policy before the selected projection is keyed."""
from pathlib import Path
import sys
from types import SimpleNamespace

GAME = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(GAME / 'world'), str(GAME / 'world/regions')]


def test_actual_finished_parts_publish_collision_lods_and_authoritative_material_roles(monkeypatch):
    from brinecove import piece_inputs, geometry_finish
    from atelier import model_export
    import region_mesh_set

    materials = {}
    def create(name):
        material = SimpleNamespace(name=name, use_nodes=False)
        materials[name] = material
        return material
    monkeypatch.setitem(sys.modules, 'bpy', SimpleNamespace(data=SimpleNamespace(
        materials=SimpleNamespace(get=materials.get, new=create))))
    parts = {(0, 0, False, 0): SimpleNamespace(name='SM_BC_Harbor_A', mats=['wood'], faces=[[0, 1, 2]]),
             (0, 0, True, 0): SimpleNamespace(name='SM_BC_Harbor_B', mats=['rock_dark'], faces=[[0, 1, 2]])}
    monkeypatch.setattr(geometry_finish, 'settle', lambda rim: None)
    monkeypatch.setattr(geometry_finish, 'split', lambda *args, **kwargs: (parts, 0, 0, 0))
    monkeypatch.setattr(model_export, 'mesh_object', lambda part, slots: SimpleNamespace(
        name=part.name, data=SimpleNamespace(materials=list(slots.values()),
            polygons=[SimpleNamespace(vertices=[0, 1, 2])])) )
    captured = {}
    def plan(objects, root, **kwargs):
        captured.update(kwargs)
        return {'pieces': [{'name': obj.name} for obj in objects]}
    monkeypatch.setattr(region_mesh_set, 'plan', plan)
    piece_inputs.finish_parts(SimpleNamespace(faces=[[0, 1, 2]]), 'Harbor', None, None)
    a, b = captured['metadata']['SM_BC_Harbor_A'], captured['metadata']['SM_BC_Harbor_B']
    assert a['collision'] is True and b['collision'] is False
    assert a['lods'] is False and b['lods'] is False
    assert a['material_kinds'] == {'BC_wood': 'opaque'}
    assert b['material_kinds'] == {'BC_rock_dark': 'terrain'}
