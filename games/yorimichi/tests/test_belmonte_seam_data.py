"""Independent constructors retain the exact shared boundary stitch semantics."""
from copy import deepcopy
import importlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

GAME=Path(__file__).resolve().parents[1]


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(GAME/'world'))
    monkeypatch.syspath_prepend(str(GAME/'world/regions'))
    data=importlib.import_module('belmonte.mesh_data')
    seam=importlib.import_module('belmonte.seam_data')
    earthworks=importlib.import_module('train.earthworks')
    monkeypatch.setattr(earthworks,'line',lambda:None)
    return data,seam,earthworks


def terrains():
    left=np.array([[-1,0,0],[0,0,0],[0,2,.2],[-1,2,.2]],float)
    right=np.array([[0,0,0],[1,0,0],[1,1,.1],[0,1,.1],[1,2,.2],[0,2,.2]],float)
    result={}
    for owner,p,i in (('SM_BM_NorthApron',left,[0,1,2,0,2,3]),
                      ('SM_BM_NorthCountry',right,[0,1,2,0,2,3,3,2,4,3,4,5])):
        result[owner]=SimpleNamespace(p=list(p),n=list(np.tile([0.,0.,1.],(len(p),1))),
                                     t=[tuple(v[:2]) for v in p],i=i,natural=p[:,2]+10.)
    return result


@pytest.mark.parametrize('lines',[[(0,0.)],[(0,0.),(1,2.),(1,0.)]])
def test_independent_boundary_replay_matches_original_joint_stitch_in_every_array(modules,lines):
    data,seam,earthworks=modules
    original=terrains();expected=deepcopy(original)
    earthworks.stitch(list(expected.values()),[0.,0.,0.],lines,whole_seam=True)
    projected=seam.capture(original,[0.,0.,0.],lines)
    for owner,mesh in original.items():
        actual=seam.apply(mesh,projected[owner],owner=owner)
        for key,value in data.arrays(expected[owner]).items():
            assert data.arrays(actual)[key].tobytes()==value.tobytes(),(owner,key)
        assert data.arrays(mesh)['p'].shape==data.arrays(terrains()[owner])['p'].shape


def test_neighbour_interior_edit_stops_at_unchanged_consumed_boundary(modules):
    _,seam,_=modules
    original=terrains();before=seam.capture(original,[0.,0.,0.],[(0,0.)])
    original['SM_BM_NorthCountry'].p[2][2]+=4.
    assert seam.capture(original,[0.,0.,0.],[(0,0.)])==before
    original['SM_BM_NorthCountry'].p[3][2]+=.01
    changed=seam.capture(original,[0.,0.,0.],[(0,0.)])
    assert changed['SM_BM_NorthApron']!=before['SM_BM_NorthApron']
    assert changed['SM_BM_NorthCountry']==before['SM_BM_NorthCountry']


def test_numeric_construction_data_roundtrip_preserves_exact_storage_and_mtime(tmp_path,modules):
    data,_,_=modules
    for owner,mesh in terrains().items():
        path=tmp_path/(owner+'.npz');data.write(path,mesh,owner=owner)
        before=(path.read_bytes(),path.stat().st_mtime_ns)
        actual=data.read(path,owner=owner)
        assert set(data.arrays(actual))=={'p','n','t','i','natural'}
        for key,value in data.arrays(mesh).items():assert data.arrays(actual)[key].tobytes()==value.tobytes()
        data.write(path,actual,owner=owner)
        assert (path.read_bytes(),path.stat().st_mtime_ns)==before


@pytest.mark.parametrize('fault',['owner','axis','duplicate','nan','link'])
def test_seam_preflight_refuses_before_mesh_or_external_mutation(tmp_path,modules,fault):
    data,seam,_=modules;meshes=terrains();owner='SM_BM_NorthApron'
    value=seam.capture(meshes,[0.,0.,0.],[(0,0.)])[owner]
    before={key:array.tobytes() for key,array in data.arrays(meshes[owner]).items()}
    if fault=='owner':value['owner']='Other'
    if fault=='axis':value['seams'][0]['axis']=2
    if fault=='duplicate':value['seams'][0]['knots']*=2
    if fault=='nan':value['seams'][0]['knots'][0][1]=float('nan')
    outside=tmp_path/'external';outside.write_bytes(b'keep');path=tmp_path/(owner+'.json')
    if fault=='link':path.symlink_to(outside)
    with pytest.raises(ValueError):
        if fault=='link':seam.write(path,value,owner=owner)
        else:seam.apply(meshes[owner],value,owner=owner)
    assert outside.read_bytes()==b'keep'
    assert {key:array.tobytes() for key,array in data.arrays(meshes[owner]).items()}==before


def test_float_triangle_indices_refuse_before_terrain_data_write(tmp_path,modules):
    data,_,_=modules;owner='SM_BM_NorthApron';mesh=terrains()[owner]
    mesh.i=[float(index) for index in mesh.i];mesh.i[0]=.5
    path=tmp_path/(owner+'.npz')
    with pytest.raises(ValueError,match='integer storage'):data.write(path,mesh,owner=owner)
    assert not path.exists()
