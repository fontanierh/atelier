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


def planned_pair(root):
    import json
    import numpy as np
    from atelier import mesh_ir
    from atelier.export_manifest import sha
    root.mkdir()
    matrix = np.eye(4); matrix[0, 3] = 11
    hull = dict(vertices=[[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]],
                faces=[[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]], matrix=np.eye(4).tolist())
    piece = dict(positions=[[0, 0, 0], [1, 0, 0], [0, 1, 0]], faces=[[0, 1, 2]],
                 normals=[[0, 0, 1]] * 3, materials=[0], smooth=[False],
                 uvs=[('UVMap', [[0, 0], [1, 0], [0, 1]])], colours=[])
    rows = []
    for index, key in enumerate(('One', 'Two')):
        path = root / (key + '.npz')
        mesh_ir.write(path, mesh_ir.encode(piece, key=key, slots=['Material'], matrix=matrix.tolist(),
            options={}, collisions=[hull] if index == 0 else []))
        rows.append(dict(name=key, payload=path.name, sha256=sha(path), triangles=1, polygons=1,
                         min=[11, 0, 0], max=[12, 1, 0], collision_hulls=1 if index == 0 else 0))
    value = dict(schema=1, parent='Whole', complete=True, triangle_limit=32768,
                 source_triangles=2, source_polygons=2, source_collision_hulls=1,
                 slots=['Material'], matrix=matrix.tolist(), pieces=rows)
    (root / 'plan.json').write_text(json.dumps(value))
    return value


def test_logical_parent_retains_authored_collision_policy_beyond_zero_hull_child(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'world'))
    planner = importlib.import_module('region_mesh_parts')
    root = tmp_path / 'planned'
    value = planned_pair(root)
    actual = planner.validate(root)
    assert actual['source_collision_hulls'] == 1
    assert [row['collision_hulls'] for row in actual['pieces']] == [1, 0]
    assert actual['matrix'][0][3] == 11
    assert actual == value


@pytest.mark.parametrize('mutation', ['bounds', 'polygons', 'collision', 'slots', 'frame'])
def test_planned_parent_metadata_cannot_disagree_with_current_child_bytes(tmp_path, monkeypatch, mutation):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'world'))
    planner = importlib.import_module('region_mesh_parts')
    root = tmp_path / 'planned'
    value = planned_pair(root)
    if mutation == 'bounds': value['pieces'][1]['min'][0] = 10
    if mutation == 'polygons': value['source_polygons'] = 3
    if mutation == 'collision': value['source_collision_hulls'] = 0
    if mutation == 'slots': value['slots'] = ['Different']
    if mutation == 'frame': value['matrix'][0][3] = 12
    with pytest.raises(ValueError):
        planner.validate(root, value)


def test_explicit_lod_groups_conserve_original_polygon_ids_and_budget(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'world'))
    planner = importlib.import_module('region_mesh_parts')
    planner.validate_face_groups([('Second', [1]), ('First', [0])], [4, 3])
    for groups, counts in [([('One', [0, 0])], [3, 3]), ([('One', [0])], [3, 3]),
                           ([('One', [2])], [3, 3]), ([('One', [0])], [32771]),
                           ([('One', [0]), ('ONE', [1])], [3, 3])]:
        with pytest.raises(ValueError): planner.validate_face_groups(groups, counts)


def test_recorded_face_membership_cannot_duplicate_or_drop_a_base_polygon(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'world'))
    planner = importlib.import_module('region_mesh_parts')
    root = tmp_path / 'planned'
    value = planned_pair(root)
    for index, row in enumerate(value['pieces']): row['source_faces'] = [index]
    assert planner.validate(root, value) == value
    value['pieces'][1]['source_faces'] = [0]
    with pytest.raises(ValueError, match='exactly once'): planner.validate(root, value)


def test_unused_material_edit_preserves_actual_leaf_payloads_and_face_bindings(tmp_path, monkeypatch):
    import numpy as np
    from atelier import mesh_ir
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'world'))
    planner = importlib.import_module('region_mesh_parts')
    source = dict(positions=np.array([[0,0,0],[1,0,0],[0,1,0],[10,0,0],[11,0,0],[10,1,0]],dtype=np.float32),
        starts=np.array([0,3]), counts=np.array([3,3]), vertex_indices=np.arange(6),
        normals=np.array([[0,0,1]]*6,dtype=np.float32),materials=np.array([1,2]),smooth=np.array([False,True]),
        uvs=[('UVMap',np.zeros((6,2),dtype=np.float32))],colours=[],
        slots=[SimpleNamespace(name=name) for name in ('Unused','Bark','Leaf')])
    monkeypatch.setattr(planner,'capture',lambda mesh:source)
    obj=SimpleNamespace(name='Whole',type='MESH',modifiers=[],data=SimpleNamespace(shape_keys=None),matrix_world=np.eye(4))
    groups=[('Whole_cell_0_0',[0]),('Whole_cell_1_0',[1])]
    folder=tmp_path/'plan'
    original=planner.plan(obj,folder,face_groups=groups)
    payloads={row['payload']:(folder/row['payload']).read_bytes() for row in original['pieces']}
    source['slots'][0].name='ChangedUnused'
    current=planner.plan(obj,folder,face_groups=groups)
    assert current['slots']==['ChangedUnused','Bark','Leaf']
    assert {row['payload']:(folder/row['payload']).read_bytes() for row in current['pieces']}==payloads
    for row, expected in zip(current['pieces'],('Bark','Leaf')):
        meta,piece=mesh_ir.decode((folder/row['payload']).read_bytes())
        assert meta['slots']==[expected] and piece['materials'].tolist()==[0]
    # A real material change affects precisely the leaf whose faces consume it.
    source['slots'][1].name='ChangedBark'
    changed=planner.plan(obj,folder,face_groups=groups)
    assert (folder/changed['pieces'][0]['payload']).read_bytes()!=payloads[changed['pieces'][0]['payload']]
    assert (folder/changed['pieces'][1]['payload']).read_bytes()==payloads[changed['pieces'][1]['payload']]


def test_compacted_piece_cannot_remap_to_a_different_parent_material(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'world'))
    planner=importlib.import_module('region_mesh_parts');root=tmp_path/'plan';value=planned_pair(root)
    value['slots'].append('Foreign')
    value['pieces'][0].update(slots=['Material'],source_material_indices=[1])
    with pytest.raises(ValueError,match='material ownership'):planner.validate(root,value)
