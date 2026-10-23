"""Seven retained Track packages /28 queries ONLY. No native work runs on import."""
import json
import os
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent;GAME=HERE.parents[1]
sys.path[:0]=[str(HERE),str(GAME/'world'),str(GAME/'tools')]
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atomic_equivalence_io import artifact,canonical,require  # noqa: E402
from track_native_equivalence import actor_scope,bound_inputs,receiving_startup,release_actor,sha  # noqa: E402
from track_query_scope import VIADUCTS  # noqa: E402


def check_rows(rows,controls):
    require(set(rows)==set(controls)==set(VIADUCTS),'Incomplete seven-owner query supplement')
    total=0
    for name in VIADUCTS:
        observed=rows[name]['queries'];expected=controls[name]
        require(len(observed)==len(expected)==4,'Incomplete four-query owner supplement')
        require(canonical([dict(id=r['id'],kind=r['kind'],input=r['input'])for r in observed])==canonical(expected),'Supplement query inputs changed')
        require({r['kind']for r in observed}=={'ray_positive','capsule_positive','ray_negative','capsule_negative'},'Missing supplement query kind')
        require(all(r['selected_component']is True and r['blocking']is r['kind'].endswith('positive')for r in observed),name+' actual supplemental query failed')
        total+=len(observed)
    require(total==28,'Incomplete28 query census');return total


def observed_result(result,component,mesh):
    canonical(result)
    fields={'blocking','query_channel','component','mesh','selected_component'}
    require(type(result.get('blocking'))is bool,'Actual blocking flag missing')
    if result['blocking']:fields|={'position','normal','distance'}
    require(set(result)==fields and result['component']==component and result['mesh']==mesh
        and result['query_channel']=='Pawn' and result['selected_component']is True,'Query refused/escaped selected component')
    if result['blocking']:
        require(all(isinstance(result[k],list) and len(result[k])==3 and all(type(v)in(int,float)for v in result[k])
            for k in ('position','normal')) and type(result['distance'])in(int,float) and result['distance']>=0,'Malformed actual hit result')
    return result


def policy_matches(actual,old,mesh):
    canonical(actual);canonical(old)
    require(actual.get('mesh')==old.get('mesh')==mesh,'Wrong retained query mesh')
    require({k:v for k,v in actual.items()if k!='component'}=={k:v for k,v in old.items()if k!='component'},'Actual query component policy differs from retained observation')


def run(spec_path,spec_sha):
    import unreal as U
    require(not os.environ.get('ATELIER_BUILD_TASK') and not os.environ.get('ATELIER_MESH_REUSE_NONCE'),'Query fixture cannot publish task receipts')
    spec=json.loads(artifact(dict(path=str(Path(spec_path).absolute()),sha256=spec_sha)))
    require(spec['kind']=='track-seven-query-supplement' and set(spec['controls'])==set(VIADUCTS),'Wrong bounded query spec')
    bound_inputs(spec);startup=receiving_startup(spec,U);output=Path(spec['output']);atomic_json(output/'startup-ddc.json',startup)
    require(Path(U.Paths.project_content_dir()).resolve()==Path(spec['content']).resolve(),'Wrong receiving Content')
    api=U.NativeAtomicEquivalence
    require(callable(getattr(api,'probe',None)) and callable(getattr(api,'component_policy',None)),'Compiled query observer missing')
    require(U.EditorLoadingAndSavingUtils.new_blank_map(False)is not None,'Missing isolated query world')
    U.SystemLibrary.execute_console_command(None,'Editor.AsyncStaticMeshCompilation 0')
    require(U.SystemLibrary.get_console_variable_int_value('Editor.AsyncStaticMeshCompilation')==0,'Synchronous retained mesh readiness unavailable')
    editor=U.EditorAssetLibrary;actor_editor=U.get_editor_subsystem(U.EditorActorSubsystem)
    require(actor_editor is not None,'Missing query actor subsystem')
    packages={spec['package']+'/Library/'+name for name in VIADUCTS}
    def clean():
        dirty={p.get_name()for p in U.EditorLoadingAndSavingUtils.get_dirty_content_packages()}
        require(not(dirty&packages),'Retained query package became dirty')
    clean();actors=[];rows={}
    with actor_scope(actors,actor_editor,U.StaticMeshComponent,output,lambda:dict(query_only=True,package_mutation_not_permitted=True,package_byte_validation_pending=True)):
        for index,name in enumerate(VIADUCTS,1):
            package=spec['package']+'/Library/'+name;mesh=editor.load_asset(package)
            require(mesh is not None,'Missing retained unchanged query package')
            actor=actor_editor.spawn_actor_from_class(U.StaticMeshActor,U.Vector(0,0,0));require(actor is not None,'Missing query actor')
            actors.append(actor);component=actor.get_component_by_class(U.StaticMeshComponent)
            require(component is not None,'Missing actual query component')
            component.set_mobility(U.ComponentMobility.MOVABLE);require(component.set_static_mesh(mesh),'Query mesh assignment failed')
            component.set_collision_profile_name('BlockAll');component.set_collision_enabled(U.CollisionEnabled.QUERY_AND_PHYSICS)
            policy=json.loads(api.component_policy(component));require('refusal'not in policy,'Actual policy refused')
            policy['owner_class']=actor.get_class().get_path_name();policy['policy_scope']='fixture'
            old=json.loads(artifact(spec['old_policies'][name]));policy_matches(policy,old,package+'.'+name)
            observed=[]
            for row in spec['controls'][name]:
                q=row['input'];capsule=row['kind'].startswith('capsule');radius=q.get('radius_cm',0.);half=q.get('half_height_cm',0.)
                result=json.loads(api.probe(component,U.Vector(*q['start']),U.Vector(*q['end']),U.Quat(*q.get('orientation',[0.,0.,0.,1.])),radius,half,q['trace_complex']))
                observed_result(result,component.get_path_name(),mesh.get_path_name())
                observed.append(dict(row,**result))
            rows[name]=dict(policy=policy,queries=observed)
            release_actor(actor,actor_editor,U.StaticMeshComponent,actors);actor=component=mesh=None
            clean();print('TRACK RETAINED QUERY '+name+' '+str(index)+'/7',flush=True)
        atomic_json(output/'observations.json',rows)
        check_rows(rows,spec['controls']);bound_inputs(spec);clean()
        atomic_json(output/'actor-cleanup.json',dict(remaining_own_actors=len(actors),query_only=True,packages_saved=False,packages_deleted=False))
    report=output/'queries.json';atomic_json(report,dict(schema=1,rows=rows,queries=28,policy_scope='fixture',imports=0,saves=0,package_deletions=0))
    print('TRACK SEVEN RETAINED QUERY28 COMPLETE '+spec_sha+' '+sha(report),flush=True)


if __name__=='__main__':run(os.environ['ATELIER_TRACK_QUERY_SPEC'],os.environ['ATELIER_TRACK_QUERY_SHA256'])
