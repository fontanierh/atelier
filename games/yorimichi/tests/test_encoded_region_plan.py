"""Encoded source plans retain complete ownership through normal graph expansion."""
import importlib
import importlib.util
import io
import json
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import encoded_glb
from atelier.build import Python,check_modules
from atelier.gltf import glb_pack,glb_parts

GAME=Path(__file__).resolve().parents[1]


def model():
    positions=b''.join(struct.pack('<3f',i+x,0.,-y) for i in range(8)
                       for x,y in ((0.,0.),(.5,0.),(0.,.5)))
    indices=struct.pack('<24H',*range(24))
    doc=dict(asset=dict(version='2.0'),scene=0,scenes=[dict(nodes=[0])],nodes=[dict(mesh=0)],
        meshes=[dict(primitives=[dict(attributes=dict(POSITION=0),indices=1,material=0)])],
        materials=[dict(name='Palette')],buffers=[dict(byteLength=len(positions)+len(indices))],
        bufferViews=[dict(buffer=0,byteOffset=0,byteLength=len(positions)),
                     dict(buffer=0,byteOffset=len(positions),byteLength=len(indices))],
        accessors=[dict(bufferView=0,componentType=5126,count=24,type='VEC3',min=[0.,0.,-.5],max=[7.5,0.,0.]),
                   dict(bufferView=1,componentType=5123,count=24,type='SCALAR')])
    return glb_pack(doc,positions+indices)


@pytest.fixture
def plan(monkeypatch):
    monkeypatch.syspath_prepend(str(GAME/'world'))
    return importlib.import_module('encoded_region_plan')


def parts():
    return [dict(name=key,data=model(),metadata=dict(parent='Logical')) for key in ('Logical_First','Logical_Second')]


def test_complete_plan_and_renamed_piece_retire_only_recorded_owned_data(tmp_path,plan):
    root=tmp_path/'source'
    value=plan.publish(root,parent='Logical',parts=parts())
    assert value['source_triangles']==16 and value['source_render_triangles']==16 and value['source_collision_triangles']==0
    before={p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in root.glob('*.mesh')}
    plan.publish(root,parent='Logical',parts=parts())
    assert before=={p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in root.glob('*.mesh')}
    # A true vertex edit changes only its own export's consumed packet.
    edited=parts();doc,binary=glb_parts(edited[0]['data']);binary=bytearray(binary)
    struct.pack_into('<f',binary,4,1.);doc['accessors'][0]['max'][1]=1.
    edited[0]['data']=glb_pack(doc,bytes(binary))
    plan.publish(root,parent='Logical',parts=edited)
    assert (root/'Logical_First.mesh').read_bytes()!=before['Logical_First.mesh'][0]
    assert ((root/'Logical_Second.mesh').read_bytes(),(root/'Logical_Second.mesh').stat().st_mtime_ns)==before['Logical_Second.mesh']
    changed=parts();changed[1]['name']='Logical_Renamed'
    plan.publish(root,parent='Logical',parts=changed)
    assert {p.name for p in root.iterdir()}=={'plan.json','Logical_First.mesh','Logical_Renamed.mesh'}


def test_parent_runtime_bounds_and_material_groups_do_not_invalidate_leaf_packets(tmp_path,plan,monkeypatch):
    monkeypatch.syspath_prepend(str(GAME/'world/regions'))
    from belmonte.atomic_metadata import metadata,entry
    parent=dict(parent_bounds_m=[[0.,0.,0.],[20.,10.,5.]],parent_material_slots=[0,1])
    def selected():
        return [dict(name=key,data=model(),**metadata(dict(name=key,bounds_m=[[0.,0.,-.5],[7.5,0.,0.]],**parent),[0],True))
                for key in ('Logical_First','Logical_Second')]
    root=tmp_path/'plan';first=plan.publish(root,parent='Logical',parts=selected())
    before={p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in root.glob('*.mesh')}
    parent.update(parent_bounds_m=[[-10.,0.,0.],[20.,10.,5.]],parent_material_slots=[0,1,2])
    current=plan.publish(root,parent='Logical',parts=selected())
    assert first!=current
    assert before=={p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in root.glob('*.mesh')}
    for row in current['pieces']:
        packet,_=encoded_glb.read(root/row['payload'])
        assert 'parent_bounds_m' not in packet['metadata']['entry']
        assert 'parent_material_slots' not in packet['metadata']['entry']
        assert entry(row,packet['metadata'])==dict(packet['metadata']['entry'],**parent)
    exported=tmp_path/'export';encoded_glb.export(root/'Logical_First.mesh',exported)
    primary=(exported/'Logical_First.glb').read_bytes()
    assert primary==model()


@pytest.mark.parametrize('fault',['foreign','link','duplicate','escape','corrupt'])
def test_invalid_source_refuses_without_overwriting_owned_or_foreign_members(tmp_path,plan,fault):
    root=tmp_path/'source';plan.publish(root,parent='Logical',parts=parts())
    before=(root/'plan.json').read_bytes();selected=parts()
    external=tmp_path/'external';external.write_bytes(b'keep')
    if fault=='foreign':(root/'Unexpected.mesh').write_bytes(b'keep')
    if fault=='link':(root/'Logical_First.mesh').unlink();(root/'Logical_First.mesh').symlink_to(external)
    if fault=='duplicate':selected.append(selected[0])
    if fault=='escape':selected[0]['name']='OtherOwner'
    if fault=='corrupt':selected[0]['data']=b'not a complete GLB'
    with pytest.raises((ValueError,KeyError)):plan.publish(root,parent='Logical',parts=selected)
    assert (root/'plan.json').read_bytes()==before and external.read_bytes()==b'keep'


def test_actual_graph_discovers_and_assembles_two_independent_python_exports(tmp_path,plan):
    spec=importlib.util.spec_from_file_location('encoded_region_graph',GAME/'region_exports.py')
    graph=importlib.util.module_from_spec(spec);spec.loader.exec_module(graph)
    root=tmp_path/'planned_exports/testregion/Logical'
    plan.publish(root,parent='Logical',parts=parts())
    script=tmp_path/'plan.py';script.write_text('"""Fixture planner; the completed data above is its controlled output."""\n')
    asset=graph.LogicalAsset('Logical',script,suffix='.glb',encoding='encoded_glb')
    steps=graph.steps(SimpleNamespace(out=tmp_path),region='testregion',assets=[asset])
    check_modules(steps)
    assert isinstance(steps[0].commands[0],Python) and steps[0].heavy and not steps[0].toolchain
    barrier=next(s for s in steps if s.replan);barrier.commands[0].fn(SimpleNamespace(out=tmp_path),io.StringIO())
    exports=[s for s in steps if '.export.' in s.name]
    assert len(exports)==2 and all(isinstance(s.commands[0],Python) and not s.heavy for s in exports)
    assert root/'Logical_Second.mesh' not in exports[0].inputs
    for step in exports:
        args=step.commands[0].args
        encoded_glb.export(Path(args[1]),Path(args[3]))
    steps[-1].commands[0].fn(SimpleNamespace(out=tmp_path),io.StringIO())
    ownership=json.loads((tmp_path/'atomic_regions/testregion/logical-pieces.json').read_text())
    assert ownership['parents']=={'Logical':['Logical_First','Logical_Second']}
    files=tmp_path/'atomic_regions/testregion/assets'
    assert (files/'Logical_First.glb').read_bytes()==model()
    assert (files/'Logical_Second.glb').read_bytes()==model()
