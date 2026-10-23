"""Retired North Trail exports do not enter the complete production ground closure."""
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

WORLD=Path(__file__).resolve().parents[1]/'world'
sys.path.insert(0,str(WORLD))
import yori
import region_query
from gondola import inputs,query_frames


def test_ground_paths_follow_published_trail_query_and_bind_exact_frame_code(tmp_path):
    ground=dict(groups=[])
    paths=inputs.geometry_paths(tmp_path,ground)
    assert tmp_path/'hidamari/query-data/HD_NorthTrail.npz' in paths
    assert all(path.suffix!='.fbx' for path in paths)
    for relative in ('world/gondola/query_frames.py','world/region_query.py','assets/vehicles/gondola/fbx-query-frame.json'):
        assert 'games/yorimichi/'+relative in inputs.CODE


def test_legacy_float32_frame_and_order_are_byte_exact(monkeypatch):
    codec=json.loads(query_frames.CODEC.read_text());monkeypatch.setattr(query_frames,'checked_codec',lambda:codec)
    epsilon=codec['world_matrix'][0][1]
    rows=[dict(role='render',positions=np.array([[0,1,2],[1,0,2],[1,1,2]],dtype='<f4'),
               triangles=np.array([[2,0,1]],dtype='<i4'),matrix=np.eye(4,dtype='<f8'))]
    expected=np.array([[[1+epsilon,1-epsilon,2],[epsilon,1,2],[1,-epsilon,2]]],dtype='<f8')
    actual=query_frames.imported_identity_triangles(rows)
    assert actual.dtype==expected.dtype and actual.tobytes()==expected.tobytes()
    assert actual.tobytes()!=region_query.triangles(rows).tobytes()
    rows[0]['matrix'][0,3]=1
    with pytest.raises(ValueError,match='Unsupported'):query_frames.imported_identity_triangles(rows)


def test_normal_ground_probe_uses_npz_without_fbx_and_preserves_belmonte_path(tmp_path,monkeypatch):
    spec=importlib.util.spec_from_file_location('gondola_compat_probe',WORLD/'gondola/probe.py')
    probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
    codec=json.loads(query_frames.CODEC.read_text());monkeypatch.setattr(query_frames,'checked_codec',lambda:codec)
    trail=tmp_path/'hidamari/query-data/HD_NorthTrail.npz'
    surface=dict(name='HD_NorthTrail',role='render',positions=np.array([[400,4000,1],[401,4000,2],[400,4001,3]],dtype='<f4'),
                 triangles=np.array([[0,1,2]],dtype='<i4'),matrix=np.eye(4,dtype='<f8'))
    region_query.save(trail,[surface],owner='HD_NorthTrail',stage='final')
    before=dict(belmonte_ground=dict(origin_cm=[0,0,0],groups=[dict(name=name,path='ground/glb/'+name+'.glb')
        for name in ('SM_BM_BT_Terrain_near','SM_BM_NorthApron')]))
    monkeypatch.setattr(probe.yori,'OUT',tmp_path);monkeypatch.setattr(probe,'snapshot',lambda _:before)
    wanted=[];triangles=np.array([[[400,4000,4],[401,4000,4],[400,4001,4]]],dtype='<f8')
    def legacy(path):wanted.append(path);return triangles.copy()
    monkeypatch.setattr(probe.source,'triangles',legacy)
    probe.main()
    assert not (tmp_path/'hidamari/assets/HD_NorthTrail.fbx').exists()
    assert wanted==[tmp_path/'belmonte'/row['path'] for row in before['belmonte_ground']['groups']]
    with np.load(tmp_path/'gondola/world/ground.npz',allow_pickle=False) as result:
        expected=query_frames.imported_identity_triangles([surface])
        assert result['trail'].tobytes()==expected.tobytes()
        assert result['valley'].tobytes()==result['apron'].tobytes()==triangles.tobytes()


@pytest.mark.parametrize('version,build_hash',[((5,2,2),b'9e2066aef7ef'),((5,2,1),b'unproved')])
def test_unproved_blender_or_fbx_tool_identity_refuses(monkeypatch,version,build_hash):
    import types
    bpy=types.ModuleType('bpy');bpy.app=SimpleNamespace(version=version,build_hash=build_hash)
    fbx=types.ModuleType('io_scene_fbx');fbx.parse_fbx=SimpleNamespace(__file__='unread.py')
    extras=types.ModuleType('bpy_extras');utils=types.ModuleType('bpy_extras.io_utils');extras.io_utils=utils
    for name,module in (('bpy',bpy),('io_scene_fbx',fbx),('bpy_extras',extras),('bpy_extras.io_utils',utils)):
        monkeypatch.setitem(sys.modules,name,module)
    monkeypatch.setattr(query_frames,'_checked',None)
    with pytest.raises(ValueError,match='exact roundtrip proof required'):query_frames.checked_codec()


def test_cold_normal_graph_produces_the_trail_query_before_ground_collection(tmp_path):
    from atelier import build
    recipe=build.load_recipe('yorimichi')
    steps=recipe.steps(SimpleNamespace(game='yorimichi',out=tmp_path,uproject=None))
    selected=build.order(steps,['world.gondola_ground_inputs'])
    producer=next(step for step in selected if any(product.name=='hidamari.query.HD_NorthTrail' for product in step.products))
    assert any(tmp_path/'hidamari/query-data/HD_NorthTrail.npz' in product.paths for product in producer.products)
    assert selected.index(producer)<next(index for index,step in enumerate(selected) if step.name=='world.gondola_ground_inputs')
