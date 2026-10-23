"""Fault injection for independent immutable-baseline export/native equivalence."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

import numpy as np
import pytest

from atelier import mesh_ir

GAME=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('independent_equivalence',GAME/'tools/atomic_equivalence.py')
eq=importlib.util.module_from_spec(spec);spec.loader.exec_module(eq)
MATRIX=np.eye(4).tolist()


def piece():
    return dict(positions=np.asarray([[0,0,0],[1,0,0],[0,1,0],[1,0,0],[1,1,0],[0,1,0]],dtype='<f4'),
        faces=[[0,1,2],[3,4,5]],normals=np.tile([0,0,1],(6,1)).astype('<f4'),
        materials=np.asarray([0,1],dtype='<i4'),smooth=np.asarray([False,True]),
        uvs=[('UVMap',np.asarray([[0,0],[1,0],[0,1],[1,0],[1,1],[0,1]],dtype='<f4')),
             ('Fade',np.tile([.25,.5],(6,1)).astype('<f4'))],
        colours=[('Color','POINT','FLOAT_COLOR',np.tile([.125,.25,.5,1],(6,1)).astype('<f4'))],
        selection=dict(uv_active='UVMap',uv_render='UVMap',colour_active='Color',colour_render='Color'))


def artifact(tmp_path,name,payload):
    path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(payload)
    return dict(path=str(path),sha256=hashlib.sha256(payload).hexdigest())


def packet(tmp_path,name,value=None,*,matrix=MATRIX,hulls=()):
    data=mesh_ir.encode(piece() if value is None else value,key=name,slots=['Rock','Wood'],matrix=matrix,options={},collisions=hulls)
    return artifact(tmp_path,name+'.npz',data)


def selected(value,face):
    value=copy.deepcopy(value);ids=value['faces'][face]
    value['positions']=value['positions'][ids];value['faces']=[[0,1,2]]
    value['normals']=value['normals'][face*3:face*3+3]
    value['materials']=value['materials'][face:face+1];value['smooth']=value['smooth'][face:face+1]
    value['uvs']=[(name,values[face*3:face*3+3]) for name,values in value['uvs']]
    value['colours']=[(name,domain,kind,values[ids]) for name,domain,kind,values in value['colours']]
    return value


def geometry(packets):return dict(packets=packets,query_stage='final')


def test_complete_piece_union_preserves_every_corner_field_and_multiplicity(tmp_path):
    whole=eq.geometry_set(geometry([packet(tmp_path,'Original')]),bounded=False)
    current=eq.geometry_set(geometry([packet(tmp_path,'PartA',selected(piece(),0)),packet(tmp_path,'PartB',selected(piece(),1))]),bounded=True)
    assert current==whole
    assert current['triangles']==2 and current['polygons']==2


@pytest.mark.parametrize('kind',['dropped','duplicated','winding','normal','uv','color','color_type','material','pivot','natural_for_final'])
def test_each_loss_or_semantic_change_fails_exact_conservation(tmp_path,kind):
    baseline=eq.geometry_set(geometry([packet(tmp_path,'Original')]),bounded=False)
    data=piece();matrix=copy.deepcopy(MATRIX)
    if kind=='dropped':data=selected(data,0)
    elif kind=='duplicated':
        data['faces'][1]=data['faces'][0][:]
        data['materials'][1]=data['materials'][0];data['smooth'][1]=data['smooth'][0]
        data['normals'][3:]=data['normals'][:3]
        data['uvs']=[(name,np.concatenate((v[:3],v[:3]))) for name,v in data['uvs']]
    elif kind=='winding':data['faces'][0].reverse()
    elif kind=='normal':data['normals'][0]*=-1
    elif kind=='uv':data['uvs'][1][1][0,0]+=.01
    elif kind=='color':data['colours'][0][3][0,0]+=.01
    elif kind=='color_type':data['colours'][0]=('Color','POINT','BYTE_COLOR',data['colours'][0][3])
    elif kind=='material':data['materials'][0]=1
    elif kind=='pivot':matrix[0][3]=1
    else:data['positions'][0,2]=-.2
    changed=eq.geometry_set(geometry([packet(tmp_path,'Changed',data,matrix=matrix)]),bounded=True)
    assert changed!=baseline


def hull():
    return dict(vertices=[[0,0,0],[1,0,0],[0,1,0],[0,0,1]],
        faces=[[0,2,1],[0,1,3],[1,2,3],[2,0,3]],matrix=MATRIX)


@pytest.mark.parametrize('kind',['missing','extra','moved','split'])
def test_whole_hull_count_and_frame_cannot_silently_change(kind):
    baseline=eq.hull_counter([hull()]);current=[hull()]
    if kind=='missing':current=[]
    elif kind=='extra':current.append(hull())
    elif kind=='moved':current[0]['matrix']=copy.deepcopy(MATRIX);current[0]['matrix'][0][3]=1
    else:
        current[0]['vertices'][1][0]=.5
        second=hull();second['vertices'][0][0]=.5;current.append(second)
    assert eq.hull_counter(current)!=baseline


def test_cooked_complex_winding_and_multiplicity_are_compared():
    original=[[[0,0,0],[1,0,0],[0,1,0]]]
    assert eq.triangles_counter(original)==eq.triangles_counter([[[1,0,0],[0,1,0],[0,0,0]]])
    assert eq.triangles_counter(original)!=eq.triangles_counter([[[0,0,0],[0,1,0],[1,0,0]]])
    assert eq.triangles_counter(original)!=eq.triangles_counter(original*2)


def probe(kind,id,target='Original'):
    hit=None if kind.endswith('_negative') else dict(logical='Logical',blocking=True,position=[0,0,0],normal=[0,0,1],distance=1.)
    query=dict(start=[0,0,1],end=[0,0,-1],channel='Visibility',trace_complex=True)
    if 'capsule' in kind:query.update(radius_cm=.1,half_height_cm=.2,orientation=[0,0,0,1])
    return dict(id=id,kind=kind,input=query,target=target,hit=hit)


def probes(target='Original'):
    return dict(logical='Logical',controls=[probe(kind,kind,target) for kind in
        ('ray_positive','ray_negative','capsule_positive','capsule_negative')],seams=[])


def test_native_requires_positive_negative_owned_controls_and_compares_results():
    before=probes();after=probes('PartA')
    assert eq.compare_probes(before,after,'Logical',{'PartA'},{'Original'})==4
    changed=copy.deepcopy(after);changed['controls'][0]['hit']['distance']=1.001
    with pytest.raises(eq.EvidenceError,match='differs'):eq.compare_probes(before,changed,'Logical',{'PartA'},{'Original'})
    changed=copy.deepcopy(after);changed['controls'][0]['hit']['logical']='OtherGeometry'
    with pytest.raises(eq.EvidenceError,match='Owned positive'):eq.compare_probes(before,changed,'Logical',{'PartA'},{'Original'})
    changed=copy.deepcopy(after);changed['controls'].pop()
    with pytest.raises(eq.EvidenceError,match='coverage'):eq.compare_probes(before,changed,'Logical',{'PartA'},{'Original'})


def test_split_native_union_needs_both_neighbor_ray_and_capsule_seam_controls():
    before=probes();after=probes('A')
    for target in ('A','B'):
        for kind in ('seam_ray','seam_capsule'):
            id=target+kind;before['controls'].append(probe(kind,id));after['controls'].append(probe(kind,id,target))
    after['seams']=[dict(a='A',b='B',controls=[r['id'] for r in after['controls'] if r['kind'].startswith('seam_')])]
    assert eq.compare_probes(before,after,'Logical',{'A','B'},{'Original'})==8
    changed=copy.deepcopy(after);changed['seams'][0]['controls'].pop()
    with pytest.raises(eq.EvidenceError,match='neighbor'):eq.compare_probes(before,changed,'Logical',{'A','B'},{'Original'})
    with pytest.raises(eq.EvidenceError,match='native mesh|seam coverage'):eq.compare_probes(probes(),probes('A'),'Logical',{'A','B'},{'Original'})


def test_artifacts_refuse_links_and_changed_bytes(tmp_path):
    row=artifact(tmp_path,'data.json',b'{}')
    assert eq.artifact(row)==b'{}'
    Path(row['path']).write_bytes(b'[]')
    with pytest.raises(eq.EvidenceError,match='bytes differ'):eq.artifact(row)
    real=tmp_path/'real';real.write_bytes(b'{}');Path(row['path']).unlink();Path(row['path']).symlink_to(real)
    with pytest.raises(eq.EvidenceError,match='linked'):eq.artifact(row)


def test_no_native_or_scope_coverage_never_claims_aggregate_success():
    result=eq.verify(dict(schema=1,scope={},regions={}))
    assert not result['complete'] and not result['exporter_complete'] and not result['native_complete']
    assert result['errors']
    with pytest.raises(eq.EvidenceError,match='absent'):eq.compare_native(None,'Missing')


def test_natural_query_stage_refuses_even_with_identical_mesh_bytes(tmp_path):
    value=geometry([packet(tmp_path,'Same')]);value['query_stage']='raw'
    with pytest.raises(eq.EvidenceError,match='final canonical'):eq.geometry_set(value,bounded=True)


def test_immutable_source_is_recovered_from_git_not_new_split_tree(tmp_path):
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    source=tmp_path/'original.py';source.write_text('original = 1\n')
    subprocess.run(['git','-C',str(tmp_path),'add','original.py'],check=True)
    subprocess.run(['git','-C',str(tmp_path),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid',
                    'commit','-qm','original'],check=True)
    revision=subprocess.run(['git','-C',str(tmp_path),'rev-parse','HEAD'],check=True,capture_output=True,text=True).stdout.strip()
    row=dict(revision=revision,path='original.py',sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    source.write_text('new_split = 999\n')
    assert eq.source_binding(row,tmp_path)==row
    row['sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
    with pytest.raises(eq.EvidenceError,match='identity differs'):eq.source_binding(row,tmp_path)


def glb_data():
    import struct
    from atelier.gltf import glb_pack
    value=piece();blob=bytearray();views=[];accessors=[]
    def add(values,code,width,kind,normalized=False):
        values=np.asarray(values).reshape(-1,width)
        blob.extend(b'\0'*(-len(blob)%4));offset=len(blob)
        for row in values:blob.extend(struct.pack('<'+code*width,*row))
        views.append(dict(buffer=0,byteOffset=offset,byteLength=len(blob)-offset))
        component={'f':5126,'H':5123,'B':5121}[code]
        accessors.append(dict(bufferView=len(views)-1,componentType=component,count=len(values),type=kind,normalized=normalized))
        return len(accessors)-1
    attrs={'POSITION':add(value['positions'],'f',3,'VEC3'),'NORMAL':add(value['normals'],'f',3,'VEC3'),
        'TEXCOORD_0':add(value['uvs'][0][1],'f',2,'VEC2'),'TEXCOORD_1':add(value['uvs'][1][1],'f',2,'VEC2'),
        'COLOR_0':add(np.tile([32,64,128,255],(6,1)),'B',4,'VEC4',True)}
    indices=add([0,1,2,3,4,5],'H',1,'SCALAR')
    doc=dict(asset=dict(version='2.0'),buffers=[dict(byteLength=len(blob))],bufferViews=views,accessors=accessors,
        nodes=[dict(mesh=0,name='Original')],scenes=[dict(nodes=[0])],scene=0,
        materials=[dict(name='Rock',pbrMetallicRoughness=dict(baseColorFactor=[.1,.2,.3,1]))],
        meshes=[dict(primitives=[dict(attributes=attrs,indices=indices,material=0,mode=4)])])
    return glb_pack(doc,bytes(blob))


def test_encoded_glb_union_preserves_every_attribute_byte_type_material_and_winding(tmp_path):
    from atelier.gltf_partition import split
    from atelier import encoded_glb
    original=glb_data();parts=split(original,(-2,-2,2,2),triangle_limit=1)
    assert len(parts)==2
    expected,count=eq.glb_counter(original);assert count==2
    observed=dict(render=eq.Counter(),collision=eq.Counter())
    rows=[]
    for index,part in enumerate(parts):
        counters,triangles=eq.glb_counter(part['data']);assert triangles==1
        for kind in observed:observed[kind].update(counters[kind])
        data=encoded_glb.encode(part['data'],key='Piece'+str(index))
        rows.append(artifact(tmp_path,'Piece'+str(index)+'.mesh',data))
    assert observed==expected
    baseline=eq.geometry_set(geometry([artifact(tmp_path,'Original.glb',original)]),bounded=False)
    actual=eq.geometry_set(geometry(rows),bounded=True)
    assert actual==baseline


@pytest.mark.parametrize('kind',['uv','normal','color','material','pivot','missing_channel'])
def test_glb_does_not_drop_change_or_retype_a_serialized_channel(kind):
    from atelier.gltf import glb_parts,glb_pack
    original=glb_data();doc,binary=glb_parts(original);blob=bytearray(binary)
    attrs=doc['meshes'][0]['primitives'][0]['attributes']
    if kind in ('uv','normal','color'):
        key={'uv':'TEXCOORD_1','normal':'NORMAL','color':'COLOR_0'}[kind]
        accessor=doc['accessors'][attrs[key]];view=doc['bufferViews'][accessor['bufferView']]
        offset=view.get('byteOffset',0);blob[offset]^=1
    elif kind=='material':doc['materials'][0]['name']='Different'
    elif kind=='pivot':doc['nodes'][0]['translation']=[1,0,0]
    else:del attrs['TEXCOORD_1']
    changed=glb_pack(doc,bytes(blob))
    if kind=='pivot':
        with pytest.raises(eq.EvidenceError,match='frame'):eq.glb_counter(changed)
    else:assert eq.glb_counter(changed)!=eq.glb_counter(original)


def test_native_seam_census_is_derived_from_actual_shared_source_edges(tmp_path):
    rows=[packet(tmp_path,'A',selected(piece(),0)),packet(tmp_path,'B',selected(piece(),1))]
    assert eq.seam_adjacency(geometry(rows),['A','B'])=={('A','B')}
    moved=selected(piece(),1);moved['positions']+=3
    other=packet(tmp_path,'Moved',moved)
    assert eq.seam_adjacency(geometry([rows[0],other]),['A','Moved'])==set()


def write_json(tmp_path,name,value):return artifact(tmp_path,name,json.dumps(value).encode())


def guarded_fixture(tmp_path):
    return dict(receipt=write_json(tmp_path,'guard.json',dict(state='child_exited',cleanup_complete=True,
        processes=[],footprint_bytes=0,late_reporters=dict(unresolved=[],unresolved_pids=[],scan_failed=False))),
        stdout=artifact(tmp_path,'stdout.log',b'FIXTURE COMPLETE\n'),marker='FIXTURE COMPLETE',
        whole_result=write_json(tmp_path,'whole.json',dict(exit_code=0)))


@pytest.mark.parametrize('kind',['cleanup','processes','footprint','late','whole','marker'])
def test_guarded_evidence_requires_positive_whole_and_actual_empty_cleanup(tmp_path,kind):
    row=guarded_fixture(tmp_path);eq.guard_binding(row)
    receipt=eq.json_artifact(row['receipt'])
    if kind=='cleanup':receipt['cleanup_complete']=False
    elif kind=='processes':receipt['processes']=[dict(pid=999)]
    elif kind=='footprint':receipt['footprint_bytes']=1
    elif kind=='late':receipt['late_reporters']['unresolved']=['unknown reporter']
    elif kind=='whole':row['whole_result']=write_json(tmp_path,'failed.json',dict(exit_code=1))
    else:row['marker']='ABSENT'
    if kind in ('cleanup','processes','footprint','late'):row['receipt']=write_json(tmp_path,'bad-guard.json',receipt)
    with pytest.raises(eq.EvidenceError):eq.guard_binding(row)


def test_full_native_snapshot_has_complete_saved_meshes_cook_hulls_policy_and_seams(tmp_path):
    guard=guarded_fixture(tmp_path)
    value=piece();baseline=geometry([packet(tmp_path,'Original',value)])
    actual=geometry([packet(tmp_path,'A',selected(value,0)),packet(tmp_path,'B',selected(value,1))])
    settings=dict(logical='Logical',placements=[[0,0,0,0,1]],cull=dict(start_cm=0,end_cm=0),
        shadow=True,fade=dict(mode=0),collision='complex_as_simple',materials=['Rock','Wood'])
    policy=write_json(tmp_path,'policy.json',settings)
    cooked=write_json(tmp_path,'cooked.json',value['positions'][np.asarray(value['faces'])].tolist())
    hulls=write_json(tmp_path,'hulls.json',[])
    before=probes();after=probes('A')
    for target in ('A','B'):
        for kind in ('seam_ray','seam_capsule'):
            id=target+kind;before['controls'].append(probe(kind,id));after['controls'].append(probe(kind,id,target))
    after['seams']=[dict(a='A',b='B',controls=[r['id'] for r in after['controls'] if r['kind'].startswith('seam_')])]
    original=dict(render=baseline,cooked=cooked,hulls=hulls,policy=policy,
        probes=write_json(tmp_path,'before-probes.json',before),meshes=['Original'],packet_owners=['Original'])
    current=dict(render=actual,cooked=cooked,hulls=hulls,policy=policy,
        probes=write_json(tmp_path,'after-probes.json',after),meshes=['A','B'],packet_owners=['A','B'])
    with pytest.raises(eq.EvidenceError,match='tangent/binormal'):
        eq.compare_native(dict(baseline=original,actual=current,baseline_guard=guard,actual_guard=guard),'Logical')
    changed=copy.deepcopy(current);changed['packet_owners']=['A','A']
    with pytest.raises(eq.EvidenceError,match='omit'):eq.native_set(changed,'Logical')
    changed=copy.deepcopy(current);changed['probes']=write_json(tmp_path,'missing-seam.json',dict(after,seams=[]))
    with pytest.raises(eq.EvidenceError,match='tangent/binormal|seam census'):
        eq.compare_native(dict(baseline=original,actual=changed,baseline_guard=guard,actual_guard=guard),'Logical')


def test_global_scope_requires_all_mandatory_groups_and_every_original_owner_model(tmp_path):
    repo=tmp_path/'repo';subprocess.run(['git','init','-q',str(repo)],check=True)
    source=repo/'build.py';source.write_text('original_recipe = True\n')
    subprocess.run(['git','-C',str(repo),'add','build.py'],check=True)
    subprocess.run(['git','-C',str(repo),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','recipe'],check=True)
    revision=subprocess.run(['git','-C',str(repo),'rev-parse','HEAD'],check=True,capture_output=True,text=True).stdout.strip()
    source_row=dict(revision=revision,path='build.py',sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    census=dict(complete=True,groups={name:['world.original'] for name in eq.MINIMUM_GROUPS},
        owners={'world.original':dict(models=['A','B'],captures={name:dict(source_triangles=1,exported=True) for name in ('A','B')})})
    row=dict(recipe=source_row,census=write_json(tmp_path,'census.json',census),guard=guarded_fixture(tmp_path))
    assert eq.validate_scope(row,repo)==census
    omitted=copy.deepcopy(census);del omitted['groups']['southwest']
    row['census']=write_json(tmp_path,'missing-group.json',omitted)
    with pytest.raises(eq.EvidenceError,match='environment owner census'):eq.validate_scope(row,repo)
    row['census']=write_json(tmp_path,'census-complete.json',census)
    result=eq.verify(dict(schema=1,scope=row,regions={}),repo=repo)
    assert not result['complete'] and any('omits' in error for error in result['errors'])
    # A region's partial new manifest cannot shrink the immutable captured model roster.
    partial=dict(baseline_sources=[source_row],actual_sources=[source_row],baseline_inputs=[],actual_inputs=[],
        baseline_guard=row['guard'],actual_guard=row['guard'],assets={'A':{}})
    result=eq.verify(dict(schema=1,scope=row,regions={'world.original':partial}),repo=repo)
    assert not result['complete'] and any('logical model coverage' in error for error in result['errors'])


def test_exporter_status_remains_separate_when_native_evidence_is_missing(tmp_path):
    repo=tmp_path/'repository';subprocess.run(['git','init','-q',str(repo)],check=True)
    source=repo/'build.py';source.write_text('original_recipe = True\n')
    subprocess.run(['git','-C',str(repo),'add','build.py'],check=True)
    subprocess.run(['git','-C',str(repo),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','baseline'],check=True)
    revision=subprocess.run(['git','-C',str(repo),'rev-parse','HEAD'],check=True,capture_output=True,text=True).stdout.strip()
    code=dict(revision=revision,path='build.py',sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    payload=glb_data();model=artifact(tmp_path,'Original.glb',payload)
    settings=dict(logical='Logical',placements=[],cull=dict(start_cm=0,end_cm=0),shadow=True,
        fade=dict(mode=0),collision='complex_as_simple',materials=['Rock'])
    state=write_json(tmp_path,'runtime-policy.json',settings);guard=guarded_fixture(tmp_path)
    census=dict(complete=True,groups={'fixture':['world.fixture']},owners={'world.fixture':dict(models=['Logical'],
        captures={'Logical':dict(source_triangles=2,exported=True)})})
    scope=dict(recipe=code,census=write_json(tmp_path,'original-census.json',census),guard=guard)
    asset=dict(baseline=geometry([model]),actual=geometry([model]),baseline_exports=[model],actual_exports=[model],
        baseline_policy=state,actual_policy=state)
    owner=dict(baseline_sources=[code],actual_sources=[code],baseline_inputs=[],actual_inputs=[],
        baseline_guard=guard,actual_guard=guard,assets={'Logical':asset})
    value=dict(schema=1,scope=scope,regions={'world.fixture':owner})
    result=eq.verify(value,repo=repo,required_groups=('fixture',))
    assert result['exporter_complete'] and not result['native_complete'] and not result['complete']
    assert result['regions']['world.fixture']['Logical']['exporter_complete']
    assert result['native_errors'] and not result['exporter_errors']
    only=eq.verify(value,repo=repo,required_groups=('fixture',),native=False)
    assert only['exporter_complete'] and not only['native_complete'] and not only['complete']
    assert not only['errors']


def fbx_tree():
    from types import SimpleNamespace
    def n(key,props=(),children=()):return SimpleNamespace(id=key,props=list(props),elems=list(children))
    def property(key,value):return n(key,[value])
    def p(key,value):return n(b'P',[key,b'Number',b'',b'',value])
    normal=n(b'LayerElementNormal',[0],[property(b'Name',b''),property(b'ReferenceInformationType',b'Direct'),
        property(b'MappingInformationType',b'ByPolygonVertex'),property(b'Normals',[0.,0.,1.]*3)])
    uv=n(b'LayerElementUV',[0],[property(b'Name',b'UVMap'),property(b'ReferenceInformationType',b'Direct'),
        property(b'MappingInformationType',b'ByPolygonVertex'),property(b'UV',[0.,0.,1.,0.,0.,1.])])
    geometry=n(b'Geometry',[1,b'Mesh'],[property(b'Vertices',[0.,0.,0.,1.,0.,0.,0.,1.,0.]),
        property(b'PolygonVertexIndex',[0,1,-3]),normal,uv])
    model=n(b'Model',[2,b'Original\x00\x01Model',b'Mesh'],[n(b'Properties70',children=[
        n(b'P',[b'Lcl Translation',b'Lcl Translation',b'',b'A',0.,0.,0.]),
        n(b'P',[b'RotationPivot',b'Vector3D',b'',b'A',0.,0.,0.])])])
    material=n(b'Material',[3,b'Rock\x00\x01Material',b''])
    global_settings=n(b'GlobalSettings',children=[n(b'Properties70',children=[p(key,value) for key,value in
        ((b'UpAxis',2),(b'UpAxisSign',1),(b'FrontAxis',1),(b'FrontAxisSign',-1),
         (b'CoordAxis',0),(b'CoordAxisSign',1),(b'UnitScaleFactor',100.))])])
    return n(b'',children=[n(b'Objects',children=[geometry,model,material]),
        n(b'Connections',children=[n(b'C',[b'OO',1,2]),n(b'C',[b'OO',3,2])]),global_settings])


@pytest.mark.parametrize('change',['unit','axis','pivot','normal','uv','winding','material'])
def test_serialized_fbx_binds_global_units_axes_pivots_and_all_corner_values(monkeypatch,change):
    from types import SimpleNamespace
    import sys
    tree=fbx_tree()
    monkeypatch.setitem(sys.modules,'io_scene_fbx',SimpleNamespace(parse_fbx=SimpleNamespace(parse=lambda path:(tree,7400))))
    original,count=eq.fbx_counter('observed.fbx');assert count==1
    objects=next(n for n in tree.elems if n.id==b'Objects')
    geometry,model,material=objects.elems
    if change in ('unit','axis'):
        glob=next(n for n in tree.elems if n.id==b'GlobalSettings').elems[0]
        row=next(n for n in glob.elems if n.props[0]==(b'UnitScaleFactor' if change=='unit' else b'UpAxis'))
        row.props[4]=1. if change=='unit' else 1
    elif change=='pivot':model.elems[0].elems[1].props[4]=1.
    elif change=='normal':next(n for n in geometry.elems if n.id==b'LayerElementNormal').elems[-1].props[0][0]=.1
    elif change=='uv':next(n for n in geometry.elems if n.id==b'LayerElementUV').elems[-1].props[0][0]=.1
    elif change=='winding':next(n for n in geometry.elems if n.id==b'PolygonVertexIndex').props[0]=[0,2,-2]
    else:material.props[1]=b'Other\x00\x01Material'
    assert eq.fbx_counter('observed.fbx')[0]!=original


def test_native_primitives_keep_type_and_reject_invalid_or_missing_dimensions():
    sphere=dict(kind='sphere',geometry=dict(matrix=MATRIX,radius=1.))
    box=dict(kind='box',geometry=dict(matrix=MATRIX,size=[1.,2.,3.]))
    capsule=dict(kind='capsule',geometry=dict(matrix=MATRIX,radius=1.,length=0.))
    assert sum(eq.native_hulls([sphere,box,capsule]).values())==3
    assert eq.native_hulls([sphere])!=eq.native_hulls([capsule])
    for invalid in (dict(kind='sphere',geometry=dict(matrix=MATRIX,radius=-1.)),
                    dict(kind='box',geometry=dict(matrix=MATRIX,size=[1.,2.])),
                    dict(kind='capsule',geometry=dict(matrix=MATRIX,radius=1.))):
        with pytest.raises(eq.EvidenceError):eq.native_hulls([invalid])


def test_unused_hull_vertex_is_still_part_of_the_complete_authored_convex_geometry():
    old=hull();changed=hull();changed['vertices'].append([99,99,99])
    assert eq.hull_counter([old])!=eq.hull_counter([changed])


def test_complete_rich_collision_channels_bind_actual_materials_uvs_normals_and_core():
    import base64
    value=selected(piece(),0)
    # A tetra has four vertices; this fixture uses its complete four triangles/corners.
    shape=hull();positions=np.asarray(shape['vertices'],dtype='<f4');faces=shape['faces'];loops=sum(map(len,faces))
    value=dict(positions=positions,faces=faces,normals=np.tile([0,0,1],(loops,1)).astype('<f4'),
        materials=np.zeros(len(faces),dtype='<i4'),smooth=np.zeros(len(faces),dtype=bool),
        uvs=[('UVMap',np.tile([.25,.5],(loops,1)).astype('<f4'))],colours=[],
        selection=dict(uv_active='UVMap',uv_render='UVMap',colour_active=None,colour_render=None))
    def rich(data):
        payload=mesh_ir.encode(data,key='Collision',slots=['ValidationOnly'],matrix=MATRIX,options={},collisions=[])
        return dict(shape,material_slots=[],corner_payload=base64.b64encode(payload).decode())
    original=rich(value);same=rich(copy.deepcopy(value))
    assert eq.hull_counter([original])==eq.hull_counter([same])
    changed=copy.deepcopy(value);changed['uvs'][0][1][0,0]+=.1
    assert eq.hull_counter([original])!=eq.hull_counter([rich(changed)])
    moved=copy.deepcopy(original);moved['vertices'][0][0]=99
    with pytest.raises(eq.EvidenceError,match='disagree'):eq.hull_counter([moved])
    assert eq.hull_counter([original])!=eq.hull_counter([shape]), 'Missing original corner coverage is not an exemption'
