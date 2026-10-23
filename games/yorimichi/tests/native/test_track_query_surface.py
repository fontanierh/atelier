"""Actual indexed Track tessellation/frame controls; no retained/private inputs."""
import copy
from pathlib import Path
import struct
import sys
import pytest
from atelier.gltf import glb_pack
HERE=Path(__file__).resolve().parent;sys.path[:0]=[str(HERE),str(HERE.parents[1]/'tools')]
import track_query_surface as surface


def arch():
    points=[(0,0),(1,0),(2,2),(4,2),(5,0),(6,0),(6,4),(0,4)]
    indices=[0,1,2,0,2,7,2,3,7,3,6,7,3,4,6,4,5,6]
    positions=struct.pack('<24f',*(v for x,z in points for v in (x,z,0)))
    binary=positions+struct.pack('<18H',*indices)
    doc=dict(asset=dict(version='2.0'),nodes=[dict(mesh=0)],scene=0,scenes=[dict(nodes=[0])],
        meshes=[dict(primitives=[dict(attributes=dict(POSITION=0),indices=1)])],buffers=[dict(byteLength=len(binary))],
        bufferViews=[dict(buffer=0,byteOffset=0,byteLength=len(positions)),dict(buffer=0,byteOffset=len(positions),byteLength=36)],
        accessors=[dict(bufferView=0,componentType=5126,count=8,type='VEC3'),dict(bufferView=1,componentType=5123,count=18,type='SCALAR')])
    return doc,binary,[(x*100,0,z*100)for x,z in points]


def test_concave_arch_fan_positive_is_empty_and_serialized_triangle_witness_is_real():
    doc,binary,vertices=arch();rows=surface.triangles(glb_pack(doc,binary));cooked=[r['corners_cm']for r in rows]
    center=[sum(vertices[i][k]for i in (0,5,6))/3 for k in range(3)]
    start=[center[0],-200,center[2]];end=[center[0],200,center[2]]
    assert not any(surface.segment_intersects(start,end,t)for t in cooked)
    controls,witness=surface.controls('SM_TK_Viaduct_00',rows)
    assert surface.surface_witness(controls,witness,cooked)['cooked_triangle_exact']
    assert witness['indices']in [r['indices']for r in rows]
    # Input +Z glTF becomes native +Z, while glTF +Z maps to native +Y.
    assert rows[0]['corners_cm'][2]==[200.,0.,200.]


@pytest.mark.parametrize('fault',['transform','nontriangles','bad_index','wrong_view','wrong_type'])
def test_source_tessellation_refuses_unsupported_frames_and_indices(fault):
    doc,binary,_=arch()
    if fault=='transform':doc['nodes'][0]['translation']=[1,0,0]
    elif fault=='nontriangles':doc['meshes'][0]['primitives'][0]['mode']=5
    elif fault=='bad_index':binary=binary[:-2]+struct.pack('<H',99)
    elif fault=='wrong_view':doc['bufferViews'][0]['byteLength']=4
    else:doc['accessors'][0]['componentType']=5123
    with pytest.raises(ValueError):surface.triangles(glb_pack(doc,binary))


@pytest.mark.parametrize('fault',['missing_triangle','changed_frame','negative_crosses'])
def test_cooked_witness_cannot_substitute_approximate_or_missing_surface(fault):
    doc,binary,_=arch();triangles=surface.triangles(glb_pack(doc,binary));rows,witness=surface.controls('SM_TK_Viaduct_00',triangles)
    cooked=copy.deepcopy([r['corners_cm']for r in triangles])
    if fault=='missing_triangle':cooked=[t for t in cooked if t!=witness['corners_cm']]
    elif fault=='changed_frame':cooked=[[[x+.001,y,z]for x,y,z in t]for t in cooked]
    else:
        positive=rows[0]['input']
        for row in rows:
            if row['kind'].endswith('negative'):row['input'].update(start=positive['start'],end=positive['end'])
    with pytest.raises(ValueError):surface.surface_witness(rows,witness,cooked)


def test_actual_f32_import_frame_and_selected_glb_identity():
    doc,binary,_=arch();doc['nodes'][0]['name']='SM_TK_Test_LOD2'
    p=(.123456789,-.234567891,.345678912);packed=struct.pack('<3f',*p);binary=packed+binary[12:]
    actual=surface.triangles(glb_pack(doc,binary),asset='SM_TK_Test_LOD2')[0]['corners_cm'][0]
    x,y,z=struct.unpack('<3f',packed)
    assert actual==[surface.f32(x*100),surface.f32(z*100),surface.f32(y*100)]
    with pytest.raises(ValueError):surface.triangles(glb_pack(doc,binary),asset='SM_TK_Foreign_LOD2')



@pytest.mark.parametrize('collision',[2,-1])
def test_future_track_preparation_selects_exact_serialized_collision_lod(tmp_path,collision):
    from prepare_track_native_equivalence import controls
    name='SM_TK_Test';level=max(collision,0);asset=name+'_LOD'+str(level)
    doc,binary,_=arch();doc['nodes'][0]['name']=asset
    path=tmp_path/(asset+'.glb');path.write_bytes(glb_pack(doc,binary))
    runtime=dict(meshes={name:dict(lods=['lod0','lod1','lod2'])},pieces=[dict(name=name,collision=collision)],instances=[])
    witnesses={};rows=controls(name,runtime,path,witnesses=witnesses)
    assert witnesses[name]['source']==str(path) and witnesses[name]['triangle']['indices']
    assert len(rows)==(4 if collision>=0 else 2)
    assert {r['kind']for r in rows}==({'ray_positive','capsule_positive','ray_negative','capsule_negative'}if collision>=0 else {'ray_negative','capsule_negative'})
    if collision<0:
        real=surface.triangles(path.read_bytes())
        assert all(any(surface.segment_intersects(row['input']['start'],row['input']['end'],t['corners_cm'])for t in real)for row in rows)
