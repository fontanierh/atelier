"""Pre-export source policy remains identical to the immutable runtime grouping."""
import copy
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pytest

GAME=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(GAME/'world'),str(GAME/'world/regions')]
from belmonte import runtime_groups  # noqa: E402


@pytest.mark.parametrize('name,expected',[
    ('SM_BM_Wall',True),('SM_BM_Water',False),('SM_BM_Foam_Detail',False),('SM_BM_water',True)])
def test_shared_logical_collision_policy_is_strict_and_case_preserving(name,expected):
    assert runtime_groups.logical_collision(name) is expected


@pytest.mark.parametrize('name',[None,1,''])
def test_invalid_source_collision_owner_refuses(name):
    with pytest.raises(ValueError):runtime_groups.logical_collision(name)


def test_shared_policy_keeps_complete_original_runtime_groups_exact():
    fixture=json.loads((GAME/'tests/fixtures/belmonte-runtime-groups-source.json').read_text())
    assert hashlib.sha256(fixture['source'].encode()).hexdigest()==fixture['sha256']
    data=dict(placements=[]);meshes=[];by_asset={};materials={0:dict(name='A'),1:dict(name='B')}
    for index,name in enumerate(('SM_BM_Wall','SM_BM_Water','SM_BM_Foam','SM_BM_Door')):
        entry=dict(name=name,bounds_m=[[0.,0.,0.],[2.,3.,4.]],parent_bounds_m=[[0.,0.,0.],[10.,20.,30.]],parent_material_slots=[0,1])
        meshes.append(entry);by_asset[name]=[(entry,[0,1],index!=3)]
        for scale in ([1.,1.,1.],[2.,3.,4.]):
            data['placements'].append(dict(asset=name,materials=[0,1],transform=dict(translation_cm=[1.,2.,3.],
                scale=scale,rotation_xyzw=[0.,0.,0.,1.])))
    extra=[dict(name='SM_BM_NorthApron')]
    before=dict(np=np,data=copy.deepcopy(data),materials=copy.deepcopy(materials),by_asset=copy.deepcopy(by_asset),
                meshes=copy.deepcopy(meshes),extra=copy.deepcopy(extra))
    exec(compile(fixture['source'],'immutable-original-runtime-groups','exec'),before)
    actual_materials=copy.deepcopy(materials)
    actual=runtime_groups.groups(copy.deepcopy(data),actual_materials,copy.deepcopy(by_asset),copy.deepcopy(meshes),copy.deepcopy(extra))
    assert actual==before['groups']
    assert actual_materials==before['materials']


def test_finite_fbx_query_frame_keeps_original_float64_operation_order(monkeypatch):
    from gondola import query_frames
    value=json.loads(query_frames.CODEC.read_text())
    monkeypatch.setattr(query_frames,'checked_codec',lambda:value)
    positions=np.array([[1122.0999755859375,335.,36.04499816894531],[0.,-0.,1.],[2.,3.,4.]],dtype='<f4')
    indices=np.array([[0,1,2]],dtype='<i4')
    surface=dict(role='render',positions=positions,triangles=indices,matrix=np.eye(4))
    matrix=np.asarray(value['world_matrix'],dtype='<f8')
    expected=(positions.astype('<f8')@matrix[:3,:3].T+matrix[:3,3])[indices]
    actual=query_frames.imported_identity_triangles([surface])
    assert actual.dtype==np.dtype('<f8') and actual.tobytes()==expected.tobytes()
    assert actual[0,0].tolist()==[1122.1000261695312,334.9998305676137,36.04499816894531]
    shifted=dict(surface,matrix=np.array([[1,0,0,1],[0,1,0,0],[0,0,1,0],[0,0,0,1]],dtype='<f8'))
    with pytest.raises(ValueError,match='Unsupported source query frame'):query_frames.imported_identity_triangles([shifted])
    with pytest.raises(ValueError,match='Unsupported source query frame'):
        query_frames.imported_identity_triangles([dict(surface,positions=positions.astype('<f8'))])
