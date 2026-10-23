"""Immutable original/current Bike receiving fixture. Run only in the compiled warm project.

All Git/source pinning belongs to prepare_bike_native.py on the host. This script
consumes frozen byte-bound sources and changes only one explicit canary Content root.
Query-enabled fixture geometry and original NoCollision policy scopes stay separate.
"""
import ast
import hashlib
import importlib.util
import json
import math
import os
import shutil
from pathlib import Path
import sys
from types import SimpleNamespace

import unreal

sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))
from bike_native_source import namespace_tree  # noqa: E402
ROOT=Path(os.environ['ATELIER_BIKE_NATIVE_ROOT'])
SPEC=ROOT/'spec.json'
assert hashlib.sha256(SPEC.read_bytes()).hexdigest()==os.environ['ATELIER_BIKE_NATIVE_SPEC_SHA']
S=json.loads(SPEC.read_text())
CURRENT=Path(S['current_receiver']);GAME=CURRENT.parents[2]
sys.path.insert(0,str(GAME/'world'));sys.path.insert(0,str(GAME));sys.path.insert(0,str(CURRENT.parent))
import yori  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from atelier.mesh_geometry import SIDECARS  # noqa: E402
from bike_atomic_products import PARTS,STEERING  # noqa: E402

EAL=unreal.EditorAssetLibrary
CONTENT=Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir()))
PACKAGE='/Game/AtelierValidation/BikeAtomicNativeCanary'
FOLDER=CONTENT/'AtelierValidation/BikeAtomicNativeCanary'
ACTORS=[]


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pinned():
    for path,digest in S['inputs'].items():
        real_directory(Path(path).parent)
        assert Path(path).is_file() and not Path(path).is_symlink() and sha(path)==digest,path


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def material_function(path):
    tree=namespace_tree(Path(path).read_text(),PACKAGE,('/Game/Japan/Materials/M_Bike','/Game/Japan/Materials'))
    scope={};exec(compile(tree,str(path),'exec'),scope);return scope['material']


def settings(mesh,editor):
    build=editor.get_lod_build_settings(mesh,0);body=mesh.get_editor_property('body_setup')
    keys=('use_full_precision_u_vs','use_high_precision_tangent_basis','recompute_normals','recompute_tangents',
          'use_mikk_t_space','use_backwards_compatible_f16_trunc_u_vs','remove_degenerates')
    return dict(build={key:bool(build.get_editor_property(key)) for key in keys},
        trace=str(body.get_editor_property('collision_trace_flag')),uv_channels=editor.get_num_uv_channels(mesh,0),
        allow_cpu_access=bool(mesh.get_editor_property('allow_cpu_access')),lods=mesh.get_num_lods(),
        simple=editor.get_simple_collision_count(mesh),convex=editor.get_convex_collision_count(mesh))


def reload_meshes(paths):
    packages=[EAL.load_asset(path).get_outermost() for path in paths]
    assert all(packages)
    changed,error=unreal.EditorLoadingAndSavingUtils.reload_packages(packages,unreal.ReloadPackagesInteractionMode.ASSUME_POSITIVE)
    assert changed and not str(error),('Actual saved package reload refused',error)
    packages=None;unreal.SystemLibrary.collect_garbage()
    meshes={path.rsplit('/',1)[1]:EAL.load_asset(path) for path in paths};assert all(meshes.values())
    return meshes


def component(mesh,group=None):
    editor=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actor=editor.spawn_actor_from_class(unreal.Actor if group else unreal.StaticMeshActor,unreal.Vector(0,0,0))
    assert actor;ACTORS.append(actor)
    if group:
        value=unreal.BikeMeshComponent.create_evidence_component(actor,mesh,group)
        assert value and isinstance(value,unreal.BikeMeshComponent)
    else:
        value=actor.get_component_by_class(unreal.StaticMeshComponent);assert value
        value.set_mobility(unreal.ComponentMobility.MOVABLE);assert value.set_static_mesh(mesh)
    value.set_generate_overlap_events(False);value.set_collision_enabled(unreal.CollisionEnabled.QUERY_ONLY)
    return value


def read_json(text):
    assert isinstance(text,str) and text
    value=json.loads(text);assert 'refusal' not in value,value
    return value


def anchors(mesh):
    page=read_json(unreal.NativeAtomicEquivalence.snapshot(mesh,'BK_Steer' if mesh.get_name() in STEERING else mesh.get_name(),0,16384,0))
    assert page['render_count']>0
    candidates=[]
    for triangle in page['render']['triangles']:
        points=[corner['position'] for corner in triangle['corners']]
        a,b,c=points;u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
        n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]];length=math.sqrt(sum(x*x for x in n))
        if length>1e-6:candidates.append((length,[sum(p[i] for p in points)/3 for i in range(3)],[x/length for x in n]))
    assert candidates
    return sorted(candidates,key=lambda row:-row[0])[:64]


def query(value,query,capsule=False):
    result=read_json(unreal.NativeAtomicEquivalence.probe(value,unreal.Vector(*query['start']),unreal.Vector(*query['end']),
        unreal.Quat(0,0,0,1),query.get('radius_cm',0) if capsule else 0,query.get('half_height_cm',0) if capsule else 0,True))
    assert result.get('query_channel')=='Pawn' and result.get('selected_component') is True
    return result


def controls_for(key,before,after):
    for area,point,normal in anchors(after.get_editor_property('static_mesh')):
        # Tiny bidirectional local controls avoid unrelated surfaces in the old whole.
        q=dict(start=[point[i]+normal[i]*.05 for i in range(3)],end=[point[i]-normal[i]*.05 for i in range(3)],
            trace_complex=True,channel='Pawn',radius_cm=.001,half_height_cm=.002)
        observed=[query(component,q,capsule) for component in (before,after) for capsule in (False,True)]
        if all(row['blocking'] for row in observed):break
    else:raise AssertionError(('No actual positive selected-component ray/capsule control',key))
    controls=[]
    for capsule,kind in ((False,'ray_positive'),(True,'capsule_positive')):
        parameters=dict(q)
        if capsule:parameters['orientation']=[0.,0.,0.,1.]
        else:
            parameters.pop('radius_cm');parameters.pop('half_height_cm')
        controls.append(dict(id=key+'.'+kind,kind=kind,input=parameters,target=after.get_path_name()))
    far=dict(start=[1000000,1000000,1000010],end=[1000000,1000000,999990],trace_complex=True,
        channel='Pawn',radius_cm=.001,half_height_cm=.002)
    for kind in ('ray_negative','capsule_negative'):
        parameters=dict(far)
        if 'capsule' in kind:parameters['orientation']=[0.,0.,0.,1.]
        else:
            parameters.pop('radius_cm');parameters.pop('half_height_cm')
        controls.append(dict(id=key+'.'+kind,kind=kind,input=parameters,target=after.get_path_name()))
    return controls


def posed_bounds(original,current,tilt):
    result=[]
    for pitch,yaw,roll,x,y,z in ((0,0,0,0,0,0),(tilt,18,0,100,-50,80),(-22,-18,15,-200,300,50)):
        pose=unreal.Transform(location=unreal.Vector(x,y,z),rotation=unreal.Rotator(pitch,yaw,roll))
        values=[]
        for part in [original,*current]:
            part.set_world_transform(pose,False,False)
            values.append(read_json(unreal.NativeAtomicEquivalence.component_policy(part)))
        assert all(row['component_bounds']==values[0]['component_bounds'] for row in values[1:]),'Actual posed box/true sphere differs'
        result.append(dict(input=dict(pitch=pitch,yaw=yaw,roll=roll,location=[x,y,z]),baseline=values[0],actual=values[1:]))
    for part in [original,*current]:part.set_world_transform(unreal.Transform(),False,False)
    return result


def preserve_packages(descriptor,phase):
    archived=[]
    for row in descriptor['saved_packages']:
        source=Path(row['path']);relative=source.relative_to(CONTENT)
        target=ROOT/'saved-packages'/phase/relative;target.parent.mkdir(parents=True,exist_ok=True)
        assert not target.exists();assert sha(source)==row['sha256']
        shutil.copy2(source,target);assert sha(target)==row['sha256']
        archived.append(dict(path=str(target),sha256=row['sha256']))
    descriptor['saved_packages']=archived
    return descriptor


def main():
    pinned();real_directory(CONTENT);assert str(CONTENT)==S['content']
    for name in ('prepare_steering_bounds','steering_bounds','validate_part','use_saved_steering_bounds','create_evidence_component'):
        assert callable(getattr(unreal.BikeMeshComponent,name,None)),('Compiled Bike evidence API missing before mutation',name)
    for name in ('snapshot','probe','component_policy'):
        assert callable(getattr(unreal.NativeAtomicEquivalence,name,None)),('Compiled native observer missing',name)
    for parent in (FOLDER,*FOLDER.parents):assert not parent.is_symlink(),parent
    assert not os.path.lexists(FOLDER),'Exclusive fresh native fixture required'
    unreal.SystemLibrary.execute_console_command(None,'Interchange.FeatureFlags.Import.FBX 0')
    unreal.SystemLibrary.execute_console_command(None,'Editor.AsyncStaticMeshCompilation 0')
    assert unreal.EditorLoadingAndSavingUtils.new_blank_map(False),'Fixture world unavailable'
    unreal.load_module('StaticMeshEditor');editor=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem);assert editor
    old_raw=module('immutable_bike_raw_importer',S['original_mesh_import'])
    # Actual immutable import_bike body; only its explicit package namespace is mapped.
    tree=namespace_tree(Path(S['original_receiver']).read_text(),PACKAGE+'/Original',('/Game/Japan/Assets',))
    start=next(i for i,node in enumerate(tree.body) if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='OUT' for t in node.targets))
    scope=dict(yori=SimpleNamespace(OUT=Path(S['original_data'])),unreal=unreal,json=json,import_mesh=old_raw._source_mesh,
        material=material_function(S['original_material']))
    unreal.load_module('MessageLog')
    unreal.SystemLibrary.execute_console_command(None,'MessageLog.DisablePopup 1')
    assert unreal.SystemLibrary.get_console_variable_bool_value('MessageLog.DisablePopup')
    try:exec(compile(ast.Module(body=tree.body[start:],type_ignores=[]),S['original_receiver'],'exec'),scope)
    finally:
        unreal.SystemLibrary.execute_console_command(None,'MessageLog.DisablePopup 0')
        assert not unreal.SystemLibrary.get_console_variable_bool_value('MessageLog.DisablePopup')
    old_manifest=json.loads((Path(S['original_data'])/'bike/manifest.json').read_text())
    original_paths=[PACKAGE+'/Original/Assets/'+name for name in old_manifest['parts']]
    original={name:EAL.load_asset(path) for name,path in zip(old_manifest['parts'],original_paths)}
    assert all(original.values())
    observed_original={name:settings(mesh,editor) for name,mesh in original.items()}
    # Publish observed old policy before current admission: an assertion may reveal a
    # wrong inherited-flag assumption; the original measurements must remain available.
    atomic_json(ROOT/'original-policy.json',observed_original)
    for mesh in original.values():assert EAL.save_loaded_asset(mesh,True)
    scope['mesh']=scope['mat']=None;original.clear();original=reload_meshes(original_paths)
    assert {name:settings(mesh,editor) for name,mesh in original.items()}==observed_original
    current=module('current_production_bike_receiver',CURRENT);current.DESTINATION=PACKAGE+'/Current'
    current.material=material_function(S['current_material'])
    received=current.receive(Path(S['current_data']))
    current_paths=[current.DESTINATION+'/'+name for name in PARTS]
    actual=reload_meshes(current_paths)
    observed_current={name:settings(mesh,editor) for name,mesh in actual.items()}
    for name,row in observed_current.items():assert row==observed_original['BK_Steer' if name in STEERING else name],(name,'actual original native policy differs',row)
    for name,mesh in actual.items():
        assert unreal.BikeMeshComponent.validate_part(mesh,received['parts'][name]['source_triangles'])
        assert not unreal.BikeMeshComponent.validate_part(mesh,0),'Empty source budget admitted'
        assert not unreal.BikeMeshComponent.validate_part(mesh,1),'Truncated source budget admitted'
    original_components={name:component(mesh) for name,mesh in original.items()}
    group=[actual[name] for name in STEERING]
    current_components={name:component(mesh,group if name in STEERING else None) for name,mesh in actual.items()}
    for name in STEERING:assert current_components[name].use_saved_steering_bounds(group),'Saved/reloaded exact group metadata missing'
    poses=posed_bounds(original_components['BK_Steer'],[current_components[name] for name in STEERING],old_manifest['steer_axis_tilt_degrees'])
    emitter=module('actual_native_atomic_capture',S['capture'])
    native={};runtime=[]
    for logical in old_manifest['parts']:
        names=STEERING if logical=='BK_Steer' else (logical,)
        controls=[row for name in names for row in controls_for(name,original_components[logical],current_components[name])]
        old_controls=[dict(row,target=original_components[logical].get_path_name()) for row in controls]
        before=emitter.capture([original_components[logical]],logical,ROOT/'captures/baseline'/logical,
            controls=old_controls,policy_scope='fixture',inputs=[SPEC])
        after=emitter.capture([current_components[name] for name in names],logical,ROOT/'captures/actual'/logical,
            controls=controls,policy_scope='fixture',inputs=[SPEC])
        native[logical]=dict(baseline=preserve_packages(before,'baseline'),actual=preserve_packages(after,'actual'))
        atomic_json(ROOT/'captures/baseline'/logical/'native-descriptor.json',before)
        atomic_json(ROOT/'captures/actual'/logical/'native-descriptor.json',after)
        # NoCollision is the original runtime policy. Keep its actual negative query
        # evidence separate from the explicit query-enabled geometry controls above.
        for part in [original_components[logical],*[current_components[name] for name in names]]:
            part.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        for name in names:
            q=next(row['input'] for row in controls if row['id']==name+'.ray_positive')
            for part in (original_components[logical],current_components[name]):
                policy=read_json(unreal.NativeAtomicEquivalence.component_policy(part))
                rays=[query(part,q,capsule) for capsule in (False,True)]
                assert all(row['blocking'] is False for row in rays),'Original NoCollision runtime scope blocked'
                runtime.append(dict(physical=name,policy=policy,queries=rays))
    # A real saved foreign pointer must block retirement before any old deletion.
    old_parent=EAL.duplicate_asset(original['BK_Steer'].get_path_name(),current.DESTINATION+'/BK_Steer');assert old_parent
    foreign=EAL.duplicate_asset(original['BK_Frame'].get_path_name(),PACKAGE+'/Foreign/ForeignRef');assert foreign
    foreign.set_editor_property('complex_collision_mesh',old_parent);assert EAL.save_loaded_asset(foreign,False)
    foreign_file=FOLDER/'Foreign/ForeignRef.uasset';registry=unreal.AssetRegistryHelpers.get_asset_registry();registry.scan_files_synchronous([str(foreign_file)],True)
    reference=PACKAGE+'/Foreign/ForeignRef';parent=current.DESTINATION+'/BK_Steer'
    assert reference in EAL.find_package_referencers_for_asset(parent,load_assets_to_confirm=True)
    try:current.retire(received,runtime_members=list(PARTS))
    except ValueError as error:assert 'external references' in str(error)
    else:raise AssertionError('Saved foreign pointer did not refuse parent retirement')
    assert EAL.does_asset_exist(parent)
    foreign.set_editor_property('complex_collision_mesh',None);assert EAL.save_loaded_asset(foreign,False)
    registry.scan_files_synchronous([str(foreign_file)],True)
    assert reference not in EAL.find_package_referencers_for_asset(parent,load_assets_to_confirm=True)
    retired=current.retire(received,runtime_members=list(PARTS));assert retired==[parent]
    assert not list((FOLDER/'Current').glob('BK_Steer.*'))
    result=dict(schema=1,source_spec=sha(SPEC),original_policy=observed_original,current_policy=observed_current,
        native=native,posed_bounds=poses,runtime_no_collision=runtime,retirement_refusal=True,retired=retired,
        coverage='Actual immutable raw importer/current receiver; saved reload; fixture geometry and NoCollision policy scopes. Production Bike owner/clip/network invocation and normal task reuse remain separate.')
    atomic_json(ROOT/'result.json',result);pinned()
    # Release only fixture actors/components and packages; no foreign process or shared cache mutation.
    for actor in ACTORS:
        for part in actor.get_components_by_class(unreal.StaticMeshComponent):
            assert part.set_static_mesh(None);assert part.get_editor_property('static_mesh') is None
        assert unreal.get_editor_subsystem(unreal.EditorActorSubsystem).destroy_actor(actor)
    ACTORS.clear();original.clear();actual.clear();original_components.clear();current_components.clear();group.clear()
    scope.clear();foreign=old_parent=part=actor=mesh=None;unreal.SystemLibrary.collect_garbage()
    paths=EAL.list_assets(PACKAGE,recursive=True,include_folder=False)
    expected=set(original_paths+current_paths+[PACKAGE+'/Materials/M_Bike',reference])
    packages={path.split('.')[0] for path in paths};assert packages==expected,('Exact fixture cleanup scope differs',packages^expected)
    for package in packages:
        refs=EAL.find_package_referencers_for_asset(package,load_assets_to_confirm=True)
        assert refs is not None and set(refs)<=packages,(package,'Foreign cleanup reference',refs)
    objects=[EAL.load_asset(path) for path in sorted(packages)];assert all(objects)
    assert unreal.get_editor_subsystem(unreal.EditorAssetSubsystem).delete_loaded_assets(objects)
    assert not EAL.list_assets(PACKAGE,recursive=True,include_folder=False)
    objects.clear();unreal.SystemLibrary.collect_garbage()
    remaining={}
    allowed_files={str(Path(package.removeprefix(PACKAGE+'/')))+suffix for package in packages for suffix in SIDECARS}
    if FOLDER.exists():
        for path in FOLDER.rglob('*'):
            assert not path.is_symlink()
            if path.is_file():
                assert str(path.relative_to(FOLDER)) in allowed_files
                remaining[str(path.relative_to(FOLDER))]=sha(path)
            else:assert path.is_dir()
    atomic_json(ROOT/'cleanup.json',dict(remaining=remaining,allowed_packages=sorted(packages),root=str(FOLDER)))
    print('BIKE NATIVE ORIGINAL/CURRENT FIXTURE COMPLETE',flush=True)


if __name__=='__main__':main()
