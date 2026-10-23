"""Opaque encoded attributes survive bounded data/export tasks byte for byte."""
import json
from pathlib import Path
import struct
from types import SimpleNamespace

import pytest

from atelier import encoded_glb,export_tasks
from atelier.build import Python,check_modules
from atelier.gltf import glb_parts,glb_pack
from test_gltf_partition import model


def test_full_encoded_corner_storage_survives_packet_and_atomic_export_without_reencoding(tmp_path):
    data=model()
    packet=encoded_glb.encode(data,key='Part',metadata=dict(parent='LogicalParent'))
    identity,payload=encoded_glb.decode(packet,key='Part')
    assert payload==data and identity['triangles']==8
    assert identity['metadata']==dict(parent='LogicalParent')
    source=tmp_path/'Part.mesh';source.write_bytes(packet)
    root=tmp_path/'exported'
    receipt=encoded_glb.export(source,root)
    assert (root/'Part.glb').read_bytes()==data
    assert receipt['metadata']['parent']=='LogicalParent'
    assert export_tasks.validate(root,key='Part')==receipt
    before=(root/'Part.glb').stat().st_mtime_ns
    encoded_glb.export(source,root)
    assert (root/'Part.glb').stat().st_mtime_ns==before
    # All original vertex attributes, material identities, ordered triangle
    # references and optional opaque metadata are retained in identical bytes.
    assert glb_parts((root/'Part.glb').read_bytes())==glb_parts(data)


@pytest.mark.parametrize('fault',['payload','identity','count','bounds','slots','owner'])
def test_corrupt_data_never_reaches_the_destination(tmp_path,fault):
    packet=encoded_glb.encode(model(),key='Part')
    offset=len(encoded_glb.MAGIC)
    size=struct.unpack_from('<I',packet,offset)[0]
    head=json.loads(packet[offset+4:offset+4+size]);data=packet[offset+4+size:]
    if fault=='payload':data=data[:-4]+b'bad!'
    if fault=='identity':head['schema']=2
    if fault=='count':head['triangles']+=1
    if fault=='bounds':head['bounds'][0][0]-=1
    if fault=='slots':head['slots'].reverse()
    if fault=='owner':head['asset']='Another'
    header=json.dumps(head).encode()
    broken=encoded_glb.MAGIC+struct.pack('<I',len(header))+header+data
    source=tmp_path/'Part.mesh';source.write_bytes(broken)
    with pytest.raises((ValueError,KeyError,struct.error)):encoded_glb.export(source,tmp_path/'destination')
    assert not (tmp_path/'destination').exists()


def test_oversized_model_refuses_before_attribute_expansion():
    doc,binary=glb_parts(model())
    index=doc['meshes'][0]['primitives'][0]['indices']
    doc['accessors'][index]['count']=(encoded_glb.TRIANGLE_LIMIT+1)*3
    with pytest.raises(ValueError,match='triangle budget'):
        encoded_glb.encode(glb_pack(doc,binary),key='Huge')


def test_explicit_collision_role_preserves_material_free_authored_bytes(tmp_path):
    doc,binary=glb_parts(model())
    del doc['materials']
    for primitive in doc['meshes'][0]['primitives']:del primitive['material']
    data=glb_pack(doc,binary)
    packet=encoded_glb.encode(data,key='Hull',role='collision')
    value,actual=encoded_glb.decode(packet,key='Hull')
    assert actual==data and value['slots']==[] and value['role']=='collision'
    source=tmp_path/'Hull.mesh';source.write_bytes(packet)
    encoded_glb.export(source,tmp_path/'export')
    assert (tmp_path/'export/Hull.glb').read_bytes()==data
    assert 'materials' not in glb_parts(actual)[0]
    with pytest.raises((ValueError,KeyError)):encoded_glb.encode(data,key='Render')
    with pytest.raises(ValueError,match='material-free'):encoded_glb.encode(model(),key='Hull',role='collision')


@pytest.mark.parametrize('fault',['foreign','link','directory'])
def test_exclusive_membership_and_link_preflight_preserve_foreign_bytes(tmp_path,fault):
    source=tmp_path/'Part.mesh';source.write_bytes(encoded_glb.encode(model(),key='Part'))
    root=tmp_path/'exports';root.mkdir()
    external=tmp_path/'external';external.write_bytes(b'keep')
    if fault=='foreign':(root/'Foreign.glb').write_bytes(b'keep')
    if fault=='link':(root/'Part.glb').symlink_to(external)
    if fault=='directory':(root/'unexpected').mkdir()
    with pytest.raises(ValueError):encoded_glb.export(source,root)
    assert external.read_bytes()==b'keep'
    assert not (root/'export.json').exists()


def test_encoded_tasks_have_separate_python_owners_and_do_not_depend_on_blender_tools(tmp_path):
    assets=[export_tasks.Asset(key,Path(key+'.mesh'),'.glb') for key in ('First','Second')]
    steps=export_tasks.steps(SimpleNamespace(out=tmp_path),prefix='world.region',assets=assets,
                             script=Path('export_encoded.py'),runtime='python')
    check_modules(steps)
    assert len(steps)==2 and all(isinstance(step.commands[0],Python) and step.cache for step in steps)
    assert all(not step.toolchain and step.batch is None for step in steps)
    assert Path('First.mesh') not in steps[1].inputs and Path('Second.mesh') not in steps[0].inputs
    assert steps[0].products[0].paths!=steps[1].products[0].paths
