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
                 partition='explicit', collision_owner='One',
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


def test_material_graph_edits_change_only_the_leaf_that_uses_the_slot(tmp_path, monkeypatch):
    import numpy as np
    from atelier import mesh_ir
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'world'))
    planner = importlib.import_module('region_mesh_parts')
    def spec(roughness):
        return dict(kind='vertex_color_principled_v1', attribute='Color', roughness=float(np.float32(roughness)),
            metallic=0.0, base_color_default=[float(np.float32(.8))]*3+[1.0],
            viewport_color=[float(np.float32(.8))]*3+[1.0], viewport_roughness=0.5,
            viewport_metallic=0.0, viewport_specular=0.5, backface_culling=False, default_profile_sha256='a'*64)
    source = dict(positions=np.array([[0,0,0],[1,0,0],[0,1,0],[10,0,0],[11,0,0],[10,1,0]],dtype=np.float32),
        starts=np.array([0,3]), counts=np.array([3,3]), vertex_indices=np.arange(6),
        normals=np.array([[0,0,1]]*6,dtype=np.float32),materials=np.array([1,2]),smooth=np.array([False,True]),
        uvs=[('UVMap',np.zeros((6,2),dtype=np.float32))],
        colours=[('Color','POINT','FLOAT_COLOR',np.ones((6,4),dtype=np.float32))],
        slots=[SimpleNamespace(name=name) for name in ('Unused','Bark','Leaf')])
    monkeypatch.setattr(planner, 'capture', lambda mesh: source)
    obj = SimpleNamespace(name='Whole',type='MESH',modifiers=[],data=SimpleNamespace(shape_keys=None),matrix_world=np.eye(4))
    folder = tmp_path / 'plan'; groups = [('Whole_cell_0_0',[0]),('Whole_cell_1_0',[1])]
    values = [spec(.5),spec(.85),spec(.5)]
    original = planner.plan(obj, folder, face_groups=groups, options={'export_apply':True}, material_specs=values)
    before = [(folder / row['payload']).read_bytes() for row in original['pieces']]
    values[0] = spec(.25)
    planner.plan(obj, folder, face_groups=groups, options={'export_apply':True}, material_specs=values)
    assert [(folder / row['payload']).read_bytes() for row in original['pieces']] == before
    values[1] = spec(.25)
    planner.plan(obj, folder, face_groups=groups, options={'export_apply':True}, material_specs=values)
    assert (folder / original['pieces'][0]['payload']).read_bytes() != before[0]
    assert (folder / original['pieces'][1]['payload']).read_bytes() == before[1]
    for row, expected in zip(original['pieces'], values[1:]):
        metadata, _ = mesh_ir.decode((folder / row['payload']).read_bytes())
        assert metadata['material_specs'] == [expected]


def cell_source(monkeypatch, cells):
    import numpy as np
    import importlib
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'world'))
    planner=importlib.import_module('region_mesh_parts')
    positions=[];materials=[];smooth=[]
    for cell,count in cells:
        positions.extend([[128.*cell+1.,1.,0.],[128.*cell+2.,1.,0.],[128.*cell+1.,2.,0.]]*count)
        materials.extend([cell%2]*count);smooth.extend([bool(cell%2)]*count)
    count=len(materials)
    source=dict(positions=np.asarray(positions,dtype=np.float32),starts=np.arange(count)*3,
        counts=np.full(count,3),vertex_indices=np.arange(count*3),normals=np.tile([0.,0.,1.],(count*3,1)).astype('f4'),
        materials=np.asarray(materials),smooth=np.asarray(smooth),
        uvs=[('UVMap',np.tile([[0.,0.],[1.,0.],[0.,1.]],(count,1)).astype('f4'))],
        colours=[('Color','POINT','FLOAT_COLOR',np.tile([.2,.4,.6,1.],(count*3,1)).astype('f4'))],
        slots=[SimpleNamespace(name='Even'),SimpleNamespace(name='Odd')])
    monkeypatch.setattr(planner,'capture',lambda _:source)
    obj=SimpleNamespace(name='Whole',type='MESH',modifiers=[],data=SimpleNamespace(shape_keys=None),matrix_world=np.eye(4))
    return planner,obj,source


def payloads(root):return {p.name:p.read_bytes() for p in root.iterdir() if p.suffix=='.npz'}


def authored_hull():
    import numpy as np
    return dict(vertices=[[0,0,0],[1,0,0],[0,1,0],[0,0,1]],
        faces=[[0,2,1],[0,1,3],[1,2,3],[2,0,3]],matrix=np.eye(4).tolist())


def test_spatial_owner_never_collapses_when_total_crosses_whole_budget(tmp_path,monkeypatch):
    planner,obj,_=cell_source(monkeypatch,[(0,31000),(2,2000)])
    root=tmp_path/'retained';before=planner.plan(obj,root,partition='spatial');first=payloads(root)
    assert before['source_triangles']==33000
    planner,obj,_=cell_source(monkeypatch,[(0,30000),(2,2000)])
    after=planner.plan(obj,root,partition='spatial')
    assert after['source_triangles']==32000 and after['partition']=='spatial'
    assert {row['name'] for row in after['pieces']}=={'Whole_cell_0_0','Whole_cell_2_0'}
    assert payloads(root)['Whole_cell_2_0.npz']==first['Whole_cell_2_0.npz']
    fresh=tmp_path/'fresh';planner.plan(obj,fresh,partition='spatial')
    assert payloads(root)==payloads(fresh)  # No previous-plan/history input decides identity.


def test_explicit_whole_refuses_large_geometry_before_output_and_missing_policy_refuses(tmp_path,monkeypatch):
    planner,obj,_=cell_source(monkeypatch,[(0,32769)])
    with pytest.raises(ValueError,match='bounded source face group'):planner.plan(obj,tmp_path/'large',partition='whole')
    assert not (tmp_path/'large').exists()
    with pytest.raises(ValueError,match='Declare whole or spatial'):planner.plan(obj,tmp_path/'implicit')
    assert not (tmp_path/'implicit').exists()
    planner,obj,_=cell_source(monkeypatch,[(2,1)])
    result=planner.plan(obj,tmp_path/'small',partition='whole')
    assert [row['name'] for row in result['pieces']]==['Whole']


@pytest.mark.parametrize('cells', [[(2,1),(3,1),(-2,1)],[(-2,1),(2,1),(3,1)]])
def test_earlier_cell_append_or_prepend_cannot_take_fixed_ucx_owner(tmp_path,monkeypatch,cells):
    from atelier import mesh_ir
    planner,obj,_=cell_source(monkeypatch,[(2,1),(3,1)])
    root=tmp_path/'plan';kwargs=dict(partition='spatial',collisions=[authored_hull()],collision_owner='Whole_cell_2_0')
    planner.plan(obj,root,**kwargs);before=payloads(root)
    planner,obj,_=cell_source(monkeypatch,cells);current=planner.plan(obj,root,**kwargs)
    assert current['collision_owner']=='Whole_cell_2_0' and current['pieces'][0]['name']=='Whole_cell_2_0'
    assert {key:payloads(root)[key] for key in before}==before
    hulls={row['name']:len(mesh_ir.decode((root/row['payload']).read_bytes())[0]['collisions']) for row in current['pieces']}
    assert hulls=={'Whole_cell_2_0':1,'Whole_cell_-2_0':0,'Whole_cell_3_0':0}
    fresh=tmp_path/'fresh';planner.plan(obj,fresh,**kwargs);assert payloads(fresh)==payloads(root)


def test_missing_declared_ucx_owner_refuses_before_changing_previous_outputs(tmp_path,monkeypatch):
    planner,obj,_=cell_source(monkeypatch,[(2,1),(3,1)])
    root=tmp_path/'plan';kwargs=dict(partition='spatial',collisions=[authored_hull()],collision_owner='Whole_cell_2_0')
    planner.plan(obj,root,**kwargs);before={p.name:p.read_bytes() for p in root.iterdir()}
    planner,obj,_=cell_source(monkeypatch,[(-2,1),(3,1)])
    with pytest.raises(ValueError,match='render member is absent'):planner.plan(obj,root,**kwargs)
    assert {p.name:p.read_bytes() for p in root.iterdir()}==before
    with pytest.raises(ValueError,match='explicit collision-owner'):planner.plan(obj,tmp_path/'missing',partition='spatial',collisions=[authored_hull()])
    assert not (tmp_path/'missing').exists()


def test_authored_policy_and_owner_metadata_cannot_lie_about_actual_payloads(tmp_path,monkeypatch):
    planner,obj,_=cell_source(monkeypatch,[(2,1),(3,1)])
    root=tmp_path/'plan';value=planner.plan(obj,root,partition='spatial',collisions=[authored_hull()],collision_owner='Whole_cell_2_0')
    for field,replacement in [('partition','whole'),('collision_owner','Whole_cell_3_0')]:
        changed=dict(value,**{field:replacement})
        with pytest.raises(ValueError):planner.validate(root,changed)
    missing=dict(value);missing.pop('partition')
    with pytest.raises(ValueError):planner.validate(root,missing)


def test_declared_spatial_union_conserves_exact_all_corner_fields_and_whole_hull(tmp_path,monkeypatch):
    from collections import Counter
    from atelier import mesh_ir
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'tools'))
    from atomic_equivalence import face_counter,hull_counter
    planner,obj,source=cell_source(monkeypatch,[(2,2),(3,2)])
    source['normals'][0]=[.25,.5,.75]
    source['uvs'][0][1][0]=[.125,.875]
    source['colours'][0][3][0]=[.1,.2,.3,.4]
    original=planner.subset(source,tuple(range(len(source['counts']))))
    meta,original=mesh_ir.decode(mesh_ir.encode(original,key='Original',slots=[s.name for s in source['slots']],
        matrix=obj.matrix_world.tolist(),options={},collisions=[authored_hull()]))
    expected=face_counter(meta,original);expected_hulls=hull_counter(meta['collisions'])
    root=tmp_path/'plan';value=planner.plan(obj,root,partition='spatial',collisions=[authored_hull()],collision_owner='Whole_cell_2_0')
    actual=Counter();hulls=Counter()
    for row in value['pieces']:
        meta,piece=mesh_ir.decode((root/row['payload']).read_bytes())
        actual.update(face_counter(meta,piece));hulls.update(hull_counter(meta['collisions']))
    assert actual==expected and hulls==expected_hulls


def test_local_corner_edit_carries_current_data_without_changing_sibling_bytes(tmp_path,monkeypatch):
    import numpy as np
    from atelier import mesh_ir
    planner,obj,source=cell_source(monkeypatch,[(2,1),(3,1)])
    root=tmp_path/'plan';before=planner.plan(obj,root,partition='spatial');old=payloads(root)
    source['uvs'][0][1][0]=[.25,.75]  # Counts, bounds and spatial membership stay unchanged.
    after=planner.plan(obj,root,partition='spatial');new=payloads(root)
    assert new['Whole_cell_2_0.npz']!=old['Whole_cell_2_0.npz']
    assert new['Whole_cell_3_0.npz']==old['Whole_cell_3_0.npz']
    assert [(r['name'],r['triangles'],r['min'],r['max']) for r in before['pieces']]==[(r['name'],r['triangles'],r['min'],r['max']) for r in after['pieces']]
    _,piece=mesh_ir.decode(new['Whole_cell_2_0.npz'])
    assert np.array_equal(piece['uvs'][0][1][0],np.asarray([.25,.75],dtype='f4'))
