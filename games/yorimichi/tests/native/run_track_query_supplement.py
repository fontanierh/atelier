"""HOST preparation and guarded7/28 query-only runner. Never launch on import."""
import argparse
import json
import os
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent;GAME=HERE.parents[1]
sys.path[:0]=[str(HERE),str(GAME/'tools')]
# Bind receiver-installed build BEFORE original source yori can prepend source/platform.
from atelier import build  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from atomic_equivalence import guard_binding  # noqa: E402
from atomic_equivalence_io import artifact,require  # noqa: E402
from recover_track_native_observations import binding,host_state,read,OLD_SPEC  # noqa: E402
from track_native_equivalence import bound_inputs,check_private_launch,private_launch,sha,startup_ddc  # noqa: E402
from track_query_scope import VIADUCTS  # noqa: E402
from track_query_surface import controls,surface_witness,triangles  # noqa: E402
from track_query_supplement import check_rows  # noqa: E402


def diagnostic_gate(host,data):
    require(host['kind']=='track07-observation-host-final' and host['failed_old_whole']==255
        and host['observation_validation_only']is True and host['cleanup_pending']is True and host['native_complete']is False,
        'Not finalized narrowed failed-native observations')
    d=data['diagnostic']
    require(d['geometry_data_validated']is True and d['geometry_owners']==137 and d['geometry_lods']==362
        and d['query_all_pass']is False and d['query_complete_owner_count']==130
        and d['positive_unproven_owners']==list(VIADUCTS) and len(d['failed_query_rows'])==14
        and d['query_row_count']==540 and d['successful_query_row_count']==526,
        'Missing strict137 geometry / explicit seven-owner noncoverage')


def runtime_code_inputs(receiver):
    """Bind the actually installed receiver helpers, never a shadow source package."""
    receiver=Path(receiver).absolute();studio=receiver/'platform/studio'
    require(Path(build.__file__).resolve()==(studio/'atelier/build.py').resolve(),'Host build is not receiver-installed')
    from atelier.source_imports import local_imports
    roots=(GAME,GAME/'world',GAME/'tools',studio)
    entries=(Path(__file__),HERE/'track_query_supplement.py',HERE/'track_query_surface.py',
             studio/'atelier/unreal_script_guard.py')
    return {path for entry in entries for path in local_imports(entry,roots)}


def prepare(observation_host,workspace):
    root=real_directory(Path(workspace).absolute());require(not os.path.lexists(root),'Fresh seven-query workspace required')
    host_row=binding(observation_host);host=read(host_row);data=read(host['data']);diagnostic_gate(host,data)
    guard_binding(host['new_data_guard'])
    plan=read(data['plan']);old_row=plan['metadata']['spec'];require(old_row['sha256']==OLD_SPEC,'Wrong old native input authority')
    old=read(old_row);current_source=host.get('current_source');current_root=None if current_source is None else current_source['root']
    before=host_state(old,current_root)
    require(before==plan['host_before'] and before['native']==host['native'],'Observed native/source environment changed')
    inputs={}
    def bind(row):
        payload=artifact(row);inputs[row['path']]=row['sha256'];return payload
    bind(host_row);bind(host['data']);bind(data['plan']);bind(old_row)
    for row in host['new_data_guard'].values():
        if isinstance(row,dict):bind(row)
    runtime=read(plan['metadata']['runtime']);query_rows={};witnesses={};policies={};current_packages={}
    for name in VIADUCTS:
        require(len(runtime['meshes'][name]['lods'])==3,'Wrong viaduct authored LOD chain')
        path=str(Path(old['original_track'])/runtime['meshes'][name]['lods'][2])
        source=dict(path=path,sha256=old['inputs'][path]);source_triangles=triangles(bind(source),asset=name+'_LOD2')
        rows,witness=controls(name,source_triangles,suffix='.supplement')
        retained=data['records'][name];pages=[read(row)for row in retained['raw_pages']]
        initial=[page for page in pages if page['lod']==0 and page['first']==0]
        require(len(initial)==1 and len(initial[0]['cooked'])==initial[0]['cooked_count'],'Missing whole bounded cooked witness')
        for row in retained['raw_pages']:bind(row)
        witnesses[name]=dict(source=source,**surface_witness(rows,witness,initial[0]['cooked']))
        query_rows[name]=rows;require(len(retained['component_policies'])==1,'Missing exact old component policy')
        policies[name]=retained['component_policies'][0];bind(policies[name])
        original=read(plan['descriptors'][name]);bind(plan['descriptors'][name])
        require(len(original['saved_packages'])==len(retained['saved_packages']),'Archive/package companion census differs')
        for live,archive in zip(original['saved_packages'],retained['saved_packages']):
            require(live['sha256']==archive['sha256'],'Live/archive saved identity differs')
            bind(live);bind(archive);current_packages[live['path']]=live['sha256']
    for path,digest in old['inputs'].items():
        if Path(path).name in ('NativeAtomicEquivalence.cpp','NativeAtomicEquivalence.h','BelmonteTrack.cpp','BelmonteTrack.h'):
            bind(dict(path=path,sha256=digest))
    for path in runtime_code_inputs(old['receiving']):inputs[str(path.absolute())]=sha(path)
    from track_native_equivalence import check_input
    for path,digest in inputs.items():check_input(path,digest)
    launch=private_launch(root,'original',Path(old['launch']['engine_dir']).parent)
    root.mkdir();(root/'private-ddc').mkdir();output=root/'original';(output/'user').mkdir(parents=True)
    spec=dict(schema=1,kind='track-seven-query-supplement',phase='original',output=str(output),package=old['package'],
        content=old['content'],receiving=old['receiving'],launch=launch,inputs=inputs,controls=query_rows,
        old_policies=policies,surface_witnesses=witnesses,current_packages=current_packages,old_spec=old_row,
        observation_host=host_row,host_before=before,current_source=current_root,old_native=host['native'],
        failed_old_whole=255,cleanup_pending=True,source_input_identity_carry=data['source_input_identity_carry'])
    atomic_json(output/'spec.json',spec)
    require(host_state(old,current_root)==before,'Host identity changed during query preparation')
    print('TRACK SEVEN QUERY SPEC PREPARED '+sha(output/'spec.json')+'; NO NATIVE LAUNCH',flush=True)


def run(workspace):
    from atelier.harness.safety import guarded
    root=real_directory(Path(workspace).absolute());output=root/'original';spec_row=binding(output/'spec.json');spec=read(spec_row)
    require(spec['kind']=='track-seven-query-supplement','Wrong query spec')
    require(not os.environ.get('ATELIER_BUILD_TASK') and not os.environ.get('ATELIER_MESH_REUSE_NONCE'),'No task/receipt context allowed')
    require(spec['old_spec']['sha256']==OLD_SPEC,'Wrong sealed original query authority')
    old=read(spec['old_spec'])
    require(spec['package']==old['package'] and spec['content']==old['content'] and spec['receiving']==old['receiving'],
        'Query spec escaped retained original namespace')
    require(host_state(old,spec['current_source'])==spec['host_before'],'Host/source/native changed before query')
    require(Path.cwd().resolve()==Path(spec['receiving']).resolve(),'Run through unchanged receiving checkout')
    bound_inputs(spec);launch=check_private_launch(spec);guard=output/'guard'
    require(not os.path.lexists(guard) and not os.path.lexists(launch['startup_log'])
        and not os.path.lexists(output/'whole-result.json') and not os.path.lexists(output/'queries.json'),'Fresh seven-query caller required')
    ctx=build.Context('yorimichi');require(ctx.game_dir==Path(spec['receiving'])/'games/yorimichi','Wrong receiving context')
    script=HERE/'track_query_supplement.py'
    require(spec['inputs'].get(str(script))==sha(script),'Unbound actual query child')
    marker='TRACK SEVEN RETAINED QUERY28 COMPLETE '+spec_row['sha256']
    command=build.UnrealScript(script,marker,modules=('Yorimichi',),null_rhi=True,args=('-nosound','-noshaderworker',*launch['args']))
    with command.prepared(ctx)as(argv,overrides):
        require([v for v in argv if v in launch['args']]==launch['args'],'Prepared private arguments changed')
        env=dict(ctx.env(),**dict(overrides),ATELIER_TRACK_QUERY_SPEC=str(output/'spec.json'),ATELIER_TRACK_QUERY_SHA256=spec_row['sha256'])
        code=guarded.run(argv,guard,timeout=300,queue_seconds=1200,limit_gib=10,kind='job',
            purpose='Read-only seven retained Track packages /28 queries; no imports or saves',env=env,progress=15.,track_tree=True)
    whole=output/'whole-result.json';atomic_json(whole,dict(exit_code=code,argv=argv,spec=spec_row,work_seconds=300,queue_seconds=1200,memory_gib=10,native=spec['old_native']))
    if code:raise SystemExit(code)
    result_row=binding(output/'queries.json');result=read(result_row)
    from track_guard_stdout import snapshot
    receipt=binding(guard/'memory-health-tree.json');whole_row=binding(whole)
    stdout,stdout_source=snapshot(receipt,whole_row,guard/'stdout.log',root/'query-stdout.snapshot.log',expected_exit=0)
    evidence=dict(receipt=receipt,stdout=stdout,whole_result=whole_row,marker=marker+' '+result_row['sha256'])
    guard_binding(evidence)
    require(host_state(old,spec['current_source'])==spec['host_before'],'Host/source/native changed after query')
    bound_inputs(spec);require(read(spec_row)==spec,'Frozen query spec changed')
    check_rows(result['rows'],spec['controls']);require(result['imports']==result['saves']==result['package_deletions']==0,'Query child mutated ownership')
    cleanup=json.loads((output/'actor-cleanup.json').read_bytes())
    require(cleanup==dict(remaining_own_actors=0,query_only=True,packages_saved=False,packages_deleted=False),'Actor cleanup not positively complete')
    log=binding(launch['startup_log']);ddc=startup_ddc(launch,artifact(log).decode(errors='replace'))
    actual=json.loads((output/'startup-ddc.json').read_bytes())
    require(actual['launch']==launch and all(actual[k]==v for k,v in ddc.items()),'Private startup identity differs')
    atomic_json(root/'host-result.json',dict(schema=1,query_supplement_pass=True,queried_owners=7,queries=28,
        result=result_row,spec=spec_row,guard=evidence,stdout_source_observation=stdout_source,engine_log=log,native=spec['old_native'],old_spec=spec['old_spec'],
        observation_host=spec['observation_host'],source_input_identity_carry=spec['source_input_identity_carry'],
        independent_paired_native_execution=False,current_compiled_main_claim=False,original_current_equivalence=False,
        failed_old_whole=255,cleanup_pending=True,native_complete=False,complete=False,normal_task_reuse=False,
        imports=0,saves=0,package_deletions=0,scope='Seven actual retained fixture query outcomes only; no production runtime/BV1 claim'))
    print('TRACK SEVEN QUERY HOST FINALIZED; retained old failures unchanged',flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','run'))
    p.add_argument('--observation-host',type=Path);p.add_argument('--workspace',type=Path,required=True);a=p.parse_args()
    if a.mode=='prepare':prepare(a.observation_host,a.workspace)
    else:run(a.workspace)


if __name__=='__main__':main()
