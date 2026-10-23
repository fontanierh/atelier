"""Execute the native capture driver against an instrumented API and validate its raw protocol."""
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

GAME=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
capture=load('actual_native_capture_test',GAME/'unreal/Scripts/atomic_equivalence_capture.py')
eq=load('raw_native_equivalence_test',GAME/'tools/atomic_equivalence.py')
IDENTITY=[[1.,0,0,0],[0,1.,0,0],[0,0,1.,0],[0,0,0,1.]]
POINTS=[[[0.,0,0],[1.,0,0],[0,1.,0]],[[1.,0,0],[1.,1.,0],[0,1.,0]]]


def triangle(points,gpu=False):
    return dict(material=0,hard_edges=None if gpu else [True,True,True],corners=[dict(position=p,
        normal=[0.,0,1.,1.] if gpu else [0.,0,1.],tangent=[1.,0,0,0.] if gpu else [1.,0,0,1.],
        uvs=[[p[0],p[1]]],color=[32,64,128,255] if gpu else [.125,.25,.5,1.]) for p in points])


class Mesh:
    def __init__(self,path,points,lods=1):self.path=path;self.points=points;self.lods=lods
    def get_path_name(self):return self.path
    def get_num_lods(self):return self.lods
    def get_editor_property(self,key):
        assert key=='body_setup';return SimpleNamespace(get_editor_property=lambda field:False)


class Component:
    def __init__(self,mesh,name='Part'):self.mesh=mesh;self.name=name
    def get_path_name(self):return '/Engine/Transient.World:Level.'+self.name
    def get_editor_property(self,key):assert key=='static_mesh';return self.mesh
    def get_owner(self):return SimpleNamespace(get_class=lambda:SimpleNamespace(get_path_name=lambda:'/Script/Yorimichi.JapanWorld'))


class API:
    calls=[]
    @staticmethod
    def snapshot(mesh,logical,first,maximum,lod):
        API.calls.append((mesh.path,first,lod))
        points=mesh.points;selected=points[first:first+maximum]
        source=None if lod else dict(kind='mesh_description',uv_count=1,color_encoding='linear_float32',
            triangles=[triangle(p) for p in selected])
        return json.dumps(dict(schema=1,logical=logical,asset=mesh.path,first=first,maximum=maximum,lod=lod,
            source_available=not bool(lod),source_count=0 if lod else len(points),render_count=len(points),cooked_count=0 if lod else len(points),
            bounds=[[0,0,0],[1,1,0]],slots=[dict(name='Painted',material='/Game/M.M')],
            settings=dict(lods=mesh.lods,collision_lod=0,collision_trace=3,complex_proxy='',allow_cpu_access=True,
                full_precision_uvs=True,high_precision_tangents=True,never_cooked=False),source=source,
            render=dict(kind='render_buffers',uv_count=1,color_encoding='srgb_uint8',triangles=[triangle(p,True) for p in selected]),
            cooked=[] if lod else selected,hulls=[],hulls_complete=first==0 and lod==0))
    @staticmethod
    def component_policy(component):
        return json.dumps(dict(component=component.get_path_name(),mesh=component.mesh.path,matrix=IDENTITY,instances=[],
            collision_enabled=1,object_channel=0,responses=[2]*32,cast_shadow=True,min_draw_distance=0,max_draw_distance=0,
            visible=True,materials=1,material_bindings=['/Game/M.M'],mesh_bounds=[[0,0,0],[1,1,0]],wpo_disable_distance=0,
            lighting_channels=[True,False,False],primitive_data=[],tags=[]))
    @staticmethod
    def probe(component,start,end,rotation,radius,halfheight,complex):
        blocked=start[0]<2
        result=dict(component=component.get_path_name(),mesh=component.mesh.path,selected_component=True,blocking=blocked)
        if blocked:result.update(position=[start[0],start[1],0],normal=[0,0,1],distance=1.)
        return json.dumps(result)


def unreal(tmp_path):
    content=tmp_path/'Content';content.mkdir(exist_ok=True)
    return SimpleNamespace(Paths=SimpleNamespace(project_content_dir=lambda:str(content)),
        StaticMeshEditorSubsystem=object,get_editor_subsystem=lambda cls:SimpleNamespace(get_lod_screen_sizes=lambda mesh:[1./(i+1) for i in range(mesh.lods)]),
        AssetRegistryHelpers=SimpleNamespace(create_asset_data=lambda mesh:SimpleNamespace(get_tag_value=lambda key:'False')),
        Vector=lambda *args:list(args),Quat=lambda *args:list(args))


def save_fake_mesh(module,mesh):
    content=Path(module.Paths.project_content_dir());path=content/(mesh.path.split('.')[0][len('/Game/'):]+'.uasset')
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'actual saved fixture package')


def control(kind,target,id=None,x=.25):
    query=dict(start=[x,.25,1.],end=[x,.25,-1.],channel='selected_component',trace_complex=True)
    if 'capsule' in kind:query.update(radius_cm=.1,half_height_cm=.2,orientation=[0,0,0,1])
    return dict(id=id or kind,kind=kind,input=query,target=target.get_path_name())


def collect(tmp_path,root,components,lods=1,seams=()):
    module=unreal(tmp_path)
    for c in components:save_fake_mesh(module,c.mesh)
    controls=[control(kind,components[0],x=99 if kind.endswith('_negative') else .25) for kind in
        ('ray_positive','ray_negative','capsule_positive','capsule_negative')]
    if len(components)>1:
        ids=[]
        for index,c in enumerate(components):
            for kind in ('seam_ray','seam_capsule'):
                id=str(index)+kind;controls.append(control(kind,c,id=id));ids.append(id)
        seams=[dict(a=components[0].mesh.path,b=components[1].mesh.path,controls=ids)]
    return capture.capture(components,'Logical',tmp_path/root,controls=controls,seams=seams,
        policy_scope='production',page_size=1,api=API,unreal_module=module)


def test_emitter_pages_every_lod_from_actual_api_without_fabricating_generated_source(tmp_path):
    API.calls=[];mesh=Mesh('/Game/Before/Whole.Whole',POINTS,lods=2);component=Component(mesh)
    result=collect(tmp_path,'capture',[component])
    assert API.calls==[(mesh.path,0,0),(mesh.path,1,0),(mesh.path,0,1),(mesh.path,1,1)]
    native=eq.native_raw_set(result,'Logical')
    assert set(native['render_lods'])=={0,1} and set(native['source_lods'])=={0}
    assert native['source_presence']=={0:{True},1:{False}} and native['basis_complete']
    assert len(result['raw_pages'])==4 and all(Path(r['path']).is_file() for r in result['saved_packages'])


def test_signed_cell_assets_and_every_supported_present_sidecar_are_observed(tmp_path):
    name='FarHills_cell_-1_2_Piece03';mesh=Mesh('/Game/After/'+name+'.'+name,POINTS)
    component=Component(mesh);module=unreal(tmp_path);save_fake_mesh(module,mesh)
    primary=Path(module.Paths.project_content_dir())/('After/'+name+'.uasset')
    for suffix in ('.m.ubulk','.upayload'):primary.with_suffix(suffix).write_bytes(suffix.encode())
    controls=[control(kind,component,x=99 if kind.endswith('_negative') else .25) for kind in
        ('ray_positive','ray_negative','capsule_positive','capsule_negative')]
    result=capture.capture([component],'Logical',tmp_path/'capture',controls=controls,
        api=API,unreal_module=module)
    assert {Path(row['path']).name for row in result['saved_packages']}=={
        name+'.uasset',name+'.m.ubulk',name+'.upayload'}
    assert eq.native_raw_set(result,'Logical')['basis_complete']


@pytest.mark.parametrize('path',['/Game/After/Foo.Bar','/Game/After/Foo-Bar.Foo-Bar',
    '/Game/After/FarHills_cell_-01_2.FarHills_cell_-01_2','/Game/After/FarHills_cell_01_2.FarHills_cell_01_2'])
def test_noncanonical_native_package_aliases_refuse(tmp_path,path):
    component=Component(Mesh(path,POINTS))
    with pytest.raises(ValueError,match='exact saved project mesh paths'):
        collect(tmp_path,'capture',[component])


def test_original_whole_and_current_children_have_equal_actual_gpu_cook_policy_and_owned_probes(tmp_path):
    original=Component(Mesh('/Game/Before/Whole.Whole',POINTS),'Original')
    parts=[Component(Mesh('/Game/After/A.A',[POINTS[0]]),'A'),Component(Mesh('/Game/After/B.B',[POINTS[1]]),'B')]
    a=collect(tmp_path,'before',[original]);b=collect(tmp_path,'after',parts)
    old=eq.native_raw_set(a,'Logical');new=eq.native_raw_set(b,'Logical')
    for key in ('source_lods','render_lods','cooked','hulls','policy','settings','source_presence'):
        assert old[key]==new[key],key
    assert new['seams']=={(parts[0].mesh.path,parts[1].mesh.path)}
    # Baseline queries use the exact same probe IDs/segments against its whole component.
    probes=eq.json_artifact(b['probes']);baseline=copy.deepcopy(probes)
    for row in baseline['controls']:row['target']=original.mesh.path
    assert eq.compare_probes(baseline,probes,'Logical',set(b['meshes']),set(a['meshes']),new['seams'])==8


def test_complete_comparison_preserves_fixture_only_limit_and_rejects_ambiguous_materials(tmp_path,monkeypatch):
    original=Component(Mesh('/Game/Before/Whole.Whole',POINTS),'Original')
    parts=[Component(Mesh('/Game/After/A.A',[POINTS[0]]),'A'),Component(Mesh('/Game/After/B.B',[POINTS[1]]),'B')]
    a=collect(tmp_path,'before',[original]);b=collect(tmp_path,'after',parts)
    baseline=eq.json_artifact(b['probes'])
    for row in baseline['controls']:row['target']=original.mesh.path
    Path(a['probes']['path']).write_text(json.dumps(baseline));a['probes']=capture.artifact(a['probes']['path'])
    monkeypatch.setattr(eq,'guard_binding',lambda value:None)  # Receipt parser has separate real-shape fault tests.
    value=dict(baseline=a,actual=b,baseline_guard={},actual_guard={})
    assert eq.compare_native(value,'Logical')['complete']
    for descriptor in (a,b):
        descriptor['policy_scope']='fixture'
        for index,binding in enumerate(descriptor['component_policies']):
            row=eq.json_artifact(binding);row['policy_scope']='fixture'
            Path(binding['path']).write_text(json.dumps(row));descriptor['component_policies'][index]=capture.artifact(binding['path'])
    result=eq.compare_native(value,'Logical')
    assert result['geometry_complete'] and not result['complete'] and not result['runtime_policy_complete']
    binding=b['component_policies'][1];row=eq.json_artifact(binding);row['material_bindings']=['/Game/Other.Other']
    Path(binding['path']).write_text(json.dumps(row));b['component_policies'][1]=capture.artifact(binding['path'])
    with pytest.raises(eq.EvidenceError,match='material overrides'):eq.native_raw_set(b,'Logical')


def test_emitter_refuses_claimed_world_channel_filtering(tmp_path):
    module=unreal(tmp_path);component=Component(Mesh('/Game/Before/Whole.Whole',POINTS));save_fake_mesh(module,component.mesh)
    query=control('ray_positive',component);query['input']['channel']='Visibility'
    with pytest.raises(ValueError,match='selected_component'):
        capture.capture([component],'Logical',tmp_path/'capture',controls=[query],api=API,unreal_module=module)


@pytest.mark.parametrize('change',['tangent','binormal','uv','color','missing_lod','dropped_page','cook','saved_bytes'])
def test_native_value_or_coverage_changes_refuse_or_differ(tmp_path,change):
    mesh=Mesh('/Game/Before/Whole.Whole',POINTS,lods=2);result=collect(tmp_path,'readback',[Component(mesh)])
    old=eq.native_raw_set(result,'Logical');changed=copy.deepcopy(result)
    if change=='missing_lod':changed['raw_pages']=[r for r in changed['raw_pages'] if eq.json_artifact(r)['lod']==0]
    elif change=='dropped_page':changed['raw_pages'].pop()
    elif change=='saved_bytes':Path(changed['saved_packages'][0]['path']).write_bytes(b'changed')
    else:
        row=changed['raw_pages'][0];value=eq.json_artifact(row)
        corner=value['render']['triangles'][0]['corners'][0]
        if change=='tangent':corner['tangent'][0]=.5
        elif change=='binormal':corner['normal'][3]=-1.
        elif change=='uv':corner['uvs'][0][0]=.01
        elif change=='color':corner['color'][0]+=1
        else:value['cooked'][0][0][2]=.1
        Path(row['path']).write_text(json.dumps(value));row['sha256']=__import__('hashlib').sha256(Path(row['path']).read_bytes()).hexdigest()
    if change in ('missing_lod','dropped_page','saved_bytes'):
        with pytest.raises(eq.EvidenceError):eq.native_raw_set(changed,'Logical')
    else:
        new=eq.native_raw_set(changed,'Logical')
        field='cooked' if change=='cook' else 'render_lods'
        assert old[field]!=new[field]
