"""Authored hulls keep their complete corner channels, not just collision shape."""
import base64
from copy import deepcopy
import io
import json

import numpy as np
import pytest

from atelier import mesh_collision,mesh_ir


def source():
    return dict(positions=np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]],dtype='<f4'),
        faces=[[0,2,1],[0,1,3],[1,2,3],[2,0,3]],normals=np.array([[0.,-0.,1.]]*12,dtype='<f4'),
        materials=np.zeros(4,dtype='<i4'),smooth=np.zeros(4,dtype=bool),
        uvs=[('UVMap',np.arange(24,dtype='<f4').reshape(-1,2)/8),
             ('Secondary',np.array([[-0.,.125]]*12,dtype='<f4'))],
        colours=[('PointColour','POINT','BYTE_COLOR',np.ones((4,4),dtype='<f4')),
                 ('CornerColour','CORNER','FLOAT_COLOR',np.arange(48,dtype='<f4').reshape(-1,4)/48)],
        selection=dict(uv_active='Secondary',uv_render='UVMap',colour_active='PointColour',colour_render='CornerColour'))


MATRIX=[[0.,-1.,0.,2.],[1.,0.,0.,3.],[0.,0.,1.,4.],[0.,0.,0.,1.]]


def record():return mesh_collision.encode(source(),slots=[],matrix=MATRIX)


def outer(collision):
    piece=source()
    return mesh_ir.encode(piece,key='Rendered',slots=['Paint'],matrix=np.eye(4).tolist(),options={},collisions=[collision])


def repack(value,change):
    arrays=dict(np.load(io.BytesIO(base64.b64decode(value['corner_payload'])),allow_pickle=False))
    change(arrays)
    stream=io.BytesIO();np.savez_compressed(stream,**arrays)
    value['corner_payload']=base64.b64encode(stream.getvalue()).decode('ascii')


def test_complete_material_free_hull_roundtrip_preserves_all_exact_source_fields():
    value=record();assert value==record() and outer(value)==outer(record())
    meta,_=mesh_ir.decode(outer(value));actual=mesh_collision.decode(meta['collisions'][0]);expected=source()
    assert actual['slots']==[] and actual['faces']==expected['faces']
    assert actual['selection']==expected['selection']
    for field in ('positions','normals','materials','smooth'):
        assert actual[field].tobytes()==expected[field].tobytes()
    assert [(label,values.tobytes()) for label,values in actual['uvs']]==[
        (label,values.tobytes()) for label,values in expected['uvs']]
    assert [(label,domain,kind,values.tobytes()) for label,domain,kind,values in actual['colours']]==[
        (label,domain,kind,values.tobytes()) for label,domain,kind,values in expected['colours']]
    assert meta['collisions'][0]['matrix']==MATRIX


def test_real_material_slots_are_not_confused_with_empty_validation_table():
    value=mesh_collision.encode(source(),slots=['AuthoredHullMaterial'],matrix=MATRIX)
    assert mesh_collision.decode(value)['slots']==['AuthoredHullMaterial']
    empty=record();assert mesh_collision.decode(empty)['slots']==[]
    assert value['corner_payload']!=empty['corner_payload']


def test_channel_only_edit_changes_exact_export_input_without_changing_hull_topology():
    before=record();piece=source();piece['uvs'][0][1][0,0]+=.125
    after=mesh_collision.encode(piece,slots=[],matrix=MATRIX)
    assert {key:before[key] for key in mesh_collision.CORE}=={key:after[key] for key in mesh_collision.CORE}
    assert outer(before)!=outer(after)


@pytest.mark.parametrize('fault',['vertex','winding','frame','material','unknown','bad_base64',
    'uv_count','normal_nan','unknown_channel','nested_collision','wrong_owner'])
def test_mismatched_or_incomplete_hull_packet_refuses_before_export(fault):
    value=record()
    if fault=='vertex':value['vertices'][0][0]+=.25
    elif fault=='winding':value['faces'][0].reverse()
    elif fault=='frame':value['matrix']=deepcopy(MATRIX);value['matrix'][0][3]+=.25
    elif fault=='material':value['material_slots']=['Unrecorded']
    elif fault=='unknown':value['unknown']=True
    elif fault=='bad_base64':value['corner_payload']='not base64'
    elif fault=='uv_count':repack(value,lambda arrays:arrays.update(uv0=arrays['uv0'][:-1]))
    elif fault=='normal_nan':
        def corrupt(arrays):arrays['normals'][0,0]=np.nan
        repack(value,corrupt)
    elif fault=='unknown_channel':repack(value,lambda arrays:arrays.update(unrecorded=np.zeros(1)))
    else:
        def corrupt(arrays):
            meta=json.loads(arrays['metadata'].tobytes())
            if fault=='wrong_owner':meta['asset']='Rendered'
            else:meta['collisions']=[{key:deepcopy(value[key]) for key in mesh_collision.CORE}]
            arrays['metadata']=np.frombuffer(json.dumps(meta).encode(),dtype=np.uint8)
        repack(value,corrupt)
    with pytest.raises((ValueError,TypeError)):
        outer(value)


def test_preexisting_explicit_geometry_only_hulls_remain_readable_without_invented_attributes():
    value={key:deepcopy(record()[key]) for key in mesh_collision.CORE}
    meta,_=mesh_ir.decode(outer(value))
    assert meta['collisions']==[value] and 'corner_payload' not in meta['collisions'][0]


def pose():
    return dict(location=[2.,3.,4.],scale=[1.,1.,1.],rotation_mode='XYZ',
        rotation_euler=[0.,0.,1.5707963705062866],rotation_quaternion=[1.,0.,0.,0.],
        rotation_axis_angle=[0.,0.,1.,0.])


def test_original_transform_components_survive_without_matrix_decomposition():
    value=mesh_collision.encode(source(),slots=[],matrix=MATRIX,transform=pose())
    meta,_=mesh_ir.decode(outer(value))
    assert meta['collisions'][0]['transform']==pose()
    assert mesh_collision.decode(meta['collisions'][0])['transform']==pose()


@pytest.mark.parametrize('fault',['mode','scale','missing','nonfinite','bool'])
def test_unsupported_or_invalid_transform_components_refuse(fault):
    value=pose()
    if fault=='mode':value['rotation_mode']='unknown'
    elif fault=='scale':value['scale'][0]=0
    elif fault=='missing':del value['rotation_euler']
    elif fault=='nonfinite':value['location'][0]=float('nan')
    elif fault=='bool':value['location'][0]=True
    with pytest.raises(ValueError):mesh_collision.encode(source(),slots=[],matrix=MATRIX,transform=value)
