"""Full immutable original Village vs actual production atomic receiving, in private Content.

Host prepares and SHA-binds the spec. This child never invokes Git, subprocesses or a
source producer. Original raw importer/asset finishing are immutable archived bytes;
actual receiving/retirement are the current production functions without path rewriting.
"""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode=True
GAME=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(GAME/'unreal/Scripts'),str(GAME),str(GAME/'world'),str(GAME/'world/regions')]
import unreal  # noqa: E402
import yori  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.build_cache import copy_file  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from atelier.mesh_geometry import SIDECARS  # noqa: E402
from village.catalogue import ASSETS  # noqa: E402


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def unchanged(rows):
    for raw,row in rows.items():
        path=Path(raw);real_directory(path.parent)
        if path.is_symlink() or not path.is_file():raise ValueError('Bound fixture input missing/linked')
        st=path.stat()
        if row!=dict(sha256=sha(path),stat=[st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns]):
            raise ValueError('Bound fixture input changed: '+raw)


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def probe(component,query):
    value=unreal.NativeAtomicEquivalence.probe(component,unreal.Vector(*query['start']),unreal.Vector(*query['end']),
        unreal.Quat(*query.get('orientation',[0.,0.,0.,1.])),query.get('radius_cm',0.),query.get('half_height_cm',0.),query['trace_complex'])
    if not value:raise ValueError('Actual selected-component native probe unavailable')
    return json.loads(value)


def query(point,normal,*,capsule=False):
    result=dict(start=[p+50*n for p,n in zip(point,normal)],end=[p-50*n for p,n in zip(point,normal)],
        channel='selected_component',trace_complex=True)
    if capsule:result.update(radius_cm=.1,half_height_cm=.2,orientation=[0.,0.,0.,1.])
    return result


def controls_for(logical,original,pieces,geometry):
    before=[];after=[];seams=[]
    def pair(key,kind,component,candidates):
        for candidate in candidates:
            value=query(candidate['point'],candidate['normal'],capsule='capsule' in kind)
            if probe(component,value).get('blocking') is True and probe(original,value).get('blocking') is True:break
        else:raise ValueError('No actual positive original/current selected-component control: '+key)
        before.append(dict(id=key,kind=kind,input=value,target=original.get_path_name()))
        after.append(dict(id=key,kind=kind,input=value,target=component.get_path_name()))
        return key
    for key,component in pieces.items():
        for kind in ('ray_positive','capsule_positive'):pair(key+'-'+kind,kind,component,geometry['pieces'][key])
    for index,seam in enumerate(geometry['seams']):
        ids=[]
        for key in (seam['a'],seam['b']):
            for kind in ('seam_ray','seam_capsule'):
                ids.append(pair('seam-'+str(index)+'-'+key+'-'+kind,kind,pieces[key],seam['points'][key]))
        seams.append(dict(a=pieces[seam['a']].get_editor_property('static_mesh').get_path_name(),
            b=pieces[seam['b']].get_editor_property('static_mesh').get_path_name(),controls=ids))
    # The same outside-the-complete-logical-bounds segment must miss each representation.
    for kind in ('ray_negative','capsule_negative'):
        value=query(geometry['negative'],[0.,0.,1.],capsule='capsule' in kind)
        target=next(iter(pieces.values()))
        if probe(original,value).get('blocking') is not False or probe(target,value).get('blocking') is not False:
            raise ValueError('Actual negative collision control unexpectedly blocks')
        before.append(dict(id=kind,kind=kind,input=value,target=original.get_path_name()))
        after.append(dict(id=kind,kind=kind,input=value,target=target.get_path_name()))
    return before,after,seams


def retain_packages(descriptor,root):
    root.mkdir(parents=True)
    rows=[]
    for row in descriptor['saved_packages']:
        source=Path(row['path']);target=root/(hashlib.sha256(row['path'].encode()).hexdigest()+source.suffix)
        copy_file(source,target)
        if sha(source)!=row['sha256'] or sha(target)!=row['sha256']:raise ValueError('Native package changed while retaining exact readback')
        rows.append(dict(path=str(target),sha256=row['sha256']))
    descriptor['saved_packages']=rows
    return descriptor


def main():
    """@cc [owner:fontanierh,label:correctness] isolated-full-village-native-equivalence
    Compare ALL immutable original12 saved meshes with ALL current19 actual owner imports.
    Capture complete real source/GPU/cooked/hull/material fields and selected-component
    positive/negative/seam probes. Never substitute source counts or generated controls for
    unavailable native data. Original finishing remains exact; production receive/retire
    remain unchanged. Foreign references MUST refuse the combined plan before any deletion.
    Fixture components MUST NOT claim production runtime policy or ordinary cache reuse.
    """
    spec_file=Path(os.environ['ATELIER_VILLAGE_NATIVE_SPEC'])
    if sha(spec_file)!=os.environ['ATELIER_VILLAGE_NATIVE_SPEC_SHA256']:raise ValueError('Unbound native spec')
    spec=json.loads(spec_file.read_text())
    if spec.get('schema')!=1 or spec.get('region')!='village-native':raise ValueError('Foreign native spec')
    content=Path(unreal.Paths.project_content_dir()).absolute()
    if content!=Path(spec['content']):raise ValueError('Native project is not the explicit private receiving Content')
    real_directory(content);out=Path(spec['out']);output=Path(spec['output']);real_directory(output.parent)
    if os.path.lexists(output):raise ValueError('Fresh native output required')
    for rows in (spec['source_files'],spec['frozen_files']):unchanged(rows)
    for root in ('Japan/Assets','Japan/Materials','Experiments/VillageAtomic','VillageNativeForeign'):
        if os.path.lexists(content/root):raise ValueError('Private fixture owner root is occupied: '+root)
    yori.OUT=out;yori.GAME=content.parent.parent
    # Shader/import functions load after private output/game binding. Their source root stays real.
    library=unreal.EditorAssetLibrary
    assert unreal.EditorLoadingAndSavingUtils.new_blank_map(False) is not None
    unreal.load_module('MessageLog')
    unreal.SystemLibrary.execute_console_command(None,'MessageLog.DisablePopup 1')
    assert unreal.SystemLibrary.get_console_variable_bool_value('MessageLog.DisablePopup') is True
    unreal.SystemLibrary.execute_console_command(None,'Interchange.FeatureFlags.Import.FBX 0')
    unreal.SystemLibrary.execute_console_command(None,'Editor.AsyncStaticMeshCompilation 0')
    archive=Path(spec['archive']);old=load('immutable_village_raw',archive/'mesh_import.py')
    prior_atmosphere=sys.modules.pop('atmosphere',None)
    atmosphere=load('atmosphere',archive/'atmosphere.py');sys.modules['atmosphere']=atmosphere
    original=load('immutable_village_native',archive/'import_village.py')
    if prior_atmosphere is not None:sys.modules['atmosphere']=prior_atmosphere
    original.ROOT=out;original.OUT=out/'village-original'
    material=original.material();assert material is not None
    scope=dict(unreal=unreal,OUT=out/'village-original',EAL=library,import_mesh=old._source_mesh,
        assets=None,manifest=json.loads((out/'village-original/manifest.json').read_text()),mat=material,report={})
    exec(compile(ast.parse((archive/'finish.py').read_text()),str(archive/'finish.py'),'exec'),scope)
    scope['finish_original']()
    for parent in ASSETS:
        mesh=library.load_asset('/Game/Japan/Assets/'+parent)
        assert mesh is not None and library.save_loaded_asset(mesh,True)
    unreal.SystemLibrary.execute_console_command(None,'MessageLog.DisablePopup 0')
    assert unreal.SystemLibrary.get_console_variable_bool_value('MessageLog.DisablePopup') is False
    import import_village_atomic as owner
    import atomic_equivalence_capture as capture
    from village_atomic_products import read,DESTINATION
    groups=read(out)
    # Owned obsolete child is present BEFORE actual receiving inventories previous membership.
    obsolete=DESTINATION+'/Village_Sign_cell_999_999'
    assert library.duplicate_asset('/Game/Japan/Assets/Village_Sign',obsolete) is not None
    assert library.save_asset(obsolete)
    received=owner.receive(out)
    assert len(received['groups'])==12 and sum(map(len,received['groups'].values()))==19
    actor_system=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actors=[]
    def component(mesh):
        actor=actor_system.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(0.,0.,0.))
        assert actor is not None;actors.append(actor);part=actor.static_mesh_component
        part.set_static_mesh(mesh);part.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS)
        part.set_collision_response_to_all_channels(unreal.CollisionResponse.ECR_BLOCK)
        return part
    output.mkdir();evidence={};geometry=json.loads((out/'native-probe-geometry.json').read_text())
    for parent in ASSETS:
        original_component=component(library.load_asset('/Game/Japan/Assets/'+parent))
        pieces={row['name']:component(library.load_asset(row['asset'])) for row in received['groups'][parent]}
        before,after,seams=controls_for(parent,original_component,pieces,geometry[parent])
        baseline=capture.capture([original_component],parent,output/parent/'original',controls=before,
            policy_scope='fixture',inputs=[spec_file,*map(Path,spec['frozen_files'])])
        actual=capture.capture(pieces.values(),parent,output/parent/'actual',controls=after,seams=seams,
            policy_scope='fixture',inputs=[spec_file,*map(Path,spec['frozen_files'])])
        baseline=retain_packages(baseline,output/parent/'retained-original')
        actual=retain_packages(actual,output/parent/'retained-actual')
        atomic_json(output/parent/'original/native-descriptor.json',baseline)
        atomic_json(output/parent/'actual/native-descriptor.json',actual)
        evidence[parent]=dict(baseline=baseline,actual=actual)
        print('VILLAGE NATIVE FULL CAPTURE '+parent,flush=True)
    for actor in actors:
        part=actor.static_mesh_component;assert part.set_static_mesh(None)
        assert part.get_editor_property('static_mesh') is None and actor_system.destroy_actor(actor)
    actors.clear();part=actor=original_component=pieces=mesh=None;scope.clear()
    unreal.SystemLibrary.collect_garbage()
    foreign='/Game/VillageNativeForeign/ForeignReference'
    ref=library.duplicate_asset('/Game/Japan/Assets/Village_Sign',foreign);assert ref is not None
    ref.set_editor_property('complex_collision_mesh',library.load_asset('/Game/Japan/Assets/Village_Planting'))
    assert library.save_loaded_asset(ref,True)
    registry=unreal.AssetRegistryHelpers.get_asset_registry()
    foreign_file=str(content/'VillageNativeForeign/ForeignReference.uasset')
    registry.scan_files_synchronous([foreign_file],True)
    assert foreign in library.find_package_referencers_for_asset('/Game/Japan/Assets/Village_Planting',load_assets_to_confirm=True)
    members={parent:[row['asset'] for row in rows] for parent,rows in received['groups'].items()}
    retired=['/Game/Japan/Assets/'+parent for parent in ASSETS]+[obsolete]
    before_retirement={path:sha(content/(path.removeprefix('/Game/')+'.uasset')) for path in retired}
    try:owner.retire(received,runtime_members=members)
    except ValueError as error:
        if 'external references' not in str(error):raise
    else:raise ValueError('Foreign reference failed to refuse complete retirement')
    assert before_retirement=={path:sha(content/(path.removeprefix('/Game/')+'.uasset')) for path in retired}
    ref.set_editor_property('complex_collision_mesh',None);assert library.save_loaded_asset(ref,True)
    registry.scan_files_synchronous([foreign_file],True)
    assert owner.retire(received,runtime_members=members)==sorted(retired)
    for path in retired:
        assert not library.does_asset_exist(path)
        stem=content/path.removeprefix('/Game/')
        assert not any(stem.with_suffix(suffix).exists() for suffix in SIDECARS)
    repeated=owner.receive(out);assert repeated['groups']==received['groups']
    assert owner.retire(repeated,runtime_members=members)==[]
    current=[path for paths in members.values() for path in paths]
    cleanup=[*current,foreign,'/Game/Japan/Materials/M_Village']
    ref=material=None;unreal.SystemLibrary.collect_garbage()
    loaded=[library.load_asset(path) for path in cleanup]
    assert all(loaded) and library.delete_loaded_assets(loaded)
    loaded.clear();unreal.SystemLibrary.collect_garbage()
    for path in cleanup:
        assert not library.does_asset_exist(path)
        stem=content/path.removeprefix('/Game/')
        assert not any(stem.with_suffix(suffix).exists() for suffix in SIDECARS)
    for rows in (spec['source_files'],spec['frozen_files']):unchanged(rows)
    atomic_json(output/'result.json',dict(schema=1,complete=True,source_head=spec['source_head'],
        spec_sha256=sha(spec_file),parents=evidence,current_count=19,foreign_reference_refused=True,
        physical_retirement=retired,repeat_membership=True,fixture_assets_absent=cleanup,policy_scope='fixture',
        scope='full original12/current19 saved native capture; independent host field comparison still required'))
    print('VILLAGE NATIVE EQUIVALENCE CAPTURE COMPLETE',flush=True)


if __name__=='__main__':main()
