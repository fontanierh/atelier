"""Parent-only preparation/admission for the exact failed native-06 fixture cleanup.

No work runs on import. Invoke only at the whole-stopped warm receiver boundary.
`prepare` uses an admitted Python child to archive; `run` admits the native cleanup.
Neither command accepts failed outputs as reusable or certified products.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from atelier import build,engine
from atelier.atomic_files import atomic_json
from atelier.build_inputs import local_imports
from atelier.export_manifest import real_directory
from atelier.harness.safety import guarded

GAME=Path(__file__).resolve().parents[2];REPO=GAME.parents[1]
sys.path[:0]=[str(GAME/'tools'),str(Path(__file__).parent)]
from atomic_equivalence import artifact,guard_binding,require  # noqa: E402
import cleanup_track_fixture as cleanup  # noqa: E402
from track_native_equivalence import bound_inputs,check_input,check_private_launch,private_launch,sha,startup_ddc  # noqa: E402
from run_track_native_equivalence import binding,head,strict_cleanup  # noqa: E402


def stage(failed,output):
    failed=real_directory(Path(failed).absolute());root=real_directory(Path(output).absolute())
    require(root.resolve()==root and not os.path.lexists(root),'Fresh canonical cleanup archive/spec root required')
    manifest_row=binding(failed/'partial-namespace.json');old_spec_row=binding(failed/'spec.json')
    require(manifest_row['sha256']==cleanup.FAILED_MANIFEST and old_spec_row['sha256']==cleanup.FAILED_SPEC,
        'Only the exact frozen native06 failure may be cleaned')
    manifest=json.loads(artifact(manifest_row));old=json.loads(artifact(old_spec_row))
    old_guard=binding(failed/'guard/memory-health-tree.json');old_startup=binding(failed/'startup-ddc.json')
    old_log=binding(old['launch']['startup_log'])
    target=cleanup.validate_custody(old,manifest,json.loads(artifact(old_guard)),json.loads(artifact(old_startup)),
        artifact(old_log).decode(errors='replace'))
    require(Path(old['output'])==failed,'Old spec/output binding differs')
    receiver=Path(old['receiving']);require(Path.cwd().resolve()==receiver.resolve(),'Use the stopped receiver environment')
    require(head(receiver)==old['receiving_head'],'Receiver source changed since failure')
    source_head=head(REPO);old_source=Path(old['source']);current_old_head=head(old_source)
    require(not root.is_relative_to(Path(old['content'])) and not Path(old['content']).is_relative_to(root)
        and not root.is_relative_to(failed) and not failed.is_relative_to(root),'Archive must be independent of Content/old evidence')
    # Prove old namespace-producing body from immutable Git on HOST; never execute it.
    recovered={}
    for name in ('track_native_equivalence.py','run_track_native_equivalence.py'):
        relative='games/yorimichi/tests/native/'+name
        data=subprocess.check_output(['git','show',cleanup.FAILED_SOURCE+':'+relative],cwd=REPO,timeout=10)
        digest=hashlib.sha256(data).hexdigest()
        require(old['inputs'].get(str(old_source/relative))==digest,'Original producing source is not immutable f55')
        recovered[name]=(data,digest)
    engine_root=engine.unreal_root();launch=private_launch(root,'original',engine_root)
    cleanup.scan(target,manifest)  # Nothing is copied or deleted until all frozen files pass.
    root.mkdir();authority=root/'authority';authority.mkdir()
    inputs={}
    def bind(path,digest=None):
        path=Path(path).absolute();digest=sha(path)if digest is None else digest;check_input(path,digest)
        inputs[str(path)]=digest;return dict(path=str(path),sha256=digest)
    for row in (manifest_row,old_spec_row,old_guard,old_startup,old_log):bind(row['path'],row['sha256'])
    old_driver=None
    for name,(data,digest)in recovered.items():
        path=authority/name
        with path.open('xb')as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
        row=bind(path,digest)
        if name=='track_native_equivalence.py':old_driver=row
    archive=cleanup.archive_payloads(target,manifest,root/'payload-archive')
    archive_path=root/'archive-manifest.json';atomic_json(archive_path,archive);archive_row=bind(archive_path)
    for relative,row in archive['files'].items():bind(root/'payload-archive'/relative,row['sha256'])
    roots=(GAME,GAME/'world',GAME/'tools',REPO/'platform/studio')
    for entry in(Path(__file__),Path(cleanup.__file__),Path(__file__).with_name('track_native_equivalence.py'),
        Path(__file__).with_name('run_track_native_equivalence.py'),GAME/'tools/atomic_equivalence.py',GAME/'tools/atomic_equivalence_io.py'):
        bind(entry)
        for path in local_imports(entry,roots):bind(path)
    bind(engine_root/'Engine/Config/BaseEngine.ini')
    (root/'private-ddc').mkdir();phase=root/'original';phase.mkdir();(phase/'user').mkdir()
    spec=dict(schema=1,phase='original',cleanup_only=True,output_certified=False,source=str(REPO),source_head=source_head,
        receiving=str(receiver),receiving_head=old['receiving_head'],package=old['package'],content=old['content'],output=str(phase),
        old_source=str(old_source),old_source_current_head=current_old_head,manifest=manifest_row,failed_spec=old_spec_row,
        old_guard=old_guard,old_startup=old_startup,old_engine_log=old_log,old_driver=old_driver,
        archive_root=str(root/'payload-archive'),archive_manifest=archive_row,inputs=inputs,
        launch=launch)
    require(head(REPO)==source_head and head(old_source)==current_old_head and head(receiver)==old['receiving_head'],
        'Source/receiver changed during archive staging')
    cleanup.scan(target,manifest);cleanup.scan(root/'payload-archive',archive)
    atomic_json(phase/'spec.json',spec);cleanup.sync_directory(authority);cleanup.sync_directory(phase);cleanup.sync_directory(root)
    atomic_json(root/'prepare-result.json',dict(prepared=True,native_launched=False,cleanup_only=True,output_certified=False,
        frozen_manifest_sha256=cleanup.FAILED_MANIFEST,archive_files=317,archive_bytes=49362728,source_head=source_head))
    print('TRACK FAILED317 ARCHIVE/SPEC PREPARED; NO NATIVE LAUNCH',flush=True)


def prepare(failed,output):
    root=Path(output).absolute();guard=root.with_name(root.name+'.prepare.guard')
    require(not os.path.lexists(root)and not os.path.lexists(guard),'Fresh admitted archive preparation required')
    code=guarded.run([sys.executable,str(Path(__file__)),'stage','--failed',str(Path(failed).absolute()),'--output',str(root)],
        guard,timeout=300,queue_seconds=1200,limit_gib=10,kind='job',purpose='Archive exact failed317 Track fixture; no native',
        env=dict(os.environ),progress=15.,track_tree=True)
    whole=root.with_name(root.name+'.prepare-whole.json');atomic_json(whole,dict(exit_code=code,native_launched=False))
    if code:raise SystemExit(code)
    cleanup.terminal_empty(json.loads((guard/'memory-health-tree.json').read_bytes()))
    require('TRACK FAILED317 ARCHIVE/SPEC PREPARED; NO NATIVE LAUNCH'in(guard/'stdout.log').read_text(),'Missing archive marker')


def run(output):
    root=real_directory(Path(output).absolute());phase=root/'original';spec_row=binding(phase/'spec.json')
    payload=artifact(spec_row);spec=json.loads(payload);receiver=Path(spec['receiving']);old_source=Path(spec['old_source'])
    require(Path.cwd().resolve()==receiver.resolve()and head(receiver)==spec['receiving_head']and head(REPO)==spec['source_head']
        and head(old_source)==spec['old_source_current_head'],'Pinned whole-stopped source/receiver required')
    bound_inputs(spec);check_private_launch(spec)
    require(not os.path.lexists(phase/'guard')and not os.path.lexists(phase/'whole-result.json')
        and not os.path.lexists(spec['launch']['startup_log']),'Fresh native cleanup logs/guard required')
    ctx=build.Context('yorimichi');require(ctx.game_dir==receiver/'games/yorimichi','Wrong actual receiving project')
    sys.path.insert(0,str(receiver/'games/yorimichi/tools'))
    from network_review_common import current_native_build
    native=current_native_build(ctx)
    marker='TRACK FAILED317 FIXTURE CLEANUP COMPLETE '+spec_row['sha256']
    command=build.UnrealScript(Path(cleanup.__file__),marker,modules=('Yorimichi',),null_rhi=True,
        args=('-nosound','-noshaderworker',*spec['launch']['args']))
    with command.prepared(ctx)as(argv,overrides):
        require([value for value in argv if value in spec['launch']['args']]==spec['launch']['args'],'Prepared private args changed')
        code=guarded.run(argv,phase/'guard',timeout=900,queue_seconds=1200,limit_gib=10,kind='job',
            purpose='Only retire archived exact failed native06 Track fixture',env=dict(ctx.env(),**dict(overrides),
                ATELIER_TRACK_CLEANUP_SPEC=spec_row['path'],ATELIER_TRACK_CLEANUP_SHA256=spec_row['sha256']),progress=15.,track_tree=True)
    atomic_json(phase/'whole-result.json',dict(exit_code=code,cleanup_only=True,output_certified=False,native=native,argv=argv,launch=spec['launch']))
    if code:raise SystemExit(code)
    evidence=dict(receipt=binding(phase/'guard/memory-health-tree.json'),stdout=binding(phase/'guard/stdout.log'),
        marker=marker,whole_result=binding(phase/'whole-result.json'));guard_binding(evidence)
    require(current_native_build(ctx)==native and head(receiver)==spec['receiving_head']and head(REPO)==spec['source_head']
        and head(old_source)==spec['old_source_current_head'],'Current identities changed')
    bound_inputs(spec);require(artifact(spec_row)==payload,'Cleanup spec changed after launch')
    engine_log=binding(spec['launch']['startup_log'])
    observed=startup_ddc(spec['launch'],artifact(engine_log).decode(errors='replace'))
    startup=json.loads((phase/'startup-ddc.json').read_bytes())
    require(startup['launch']==spec['launch']and all(startup[k]==v for k,v in observed.items()),'Private cleanup startup differs')
    manifest=json.loads(artifact(spec['manifest']));archive=json.loads(artifact(spec['archive_manifest']))
    cleanup.scan(Path(spec['archive_root']),archive)
    result=json.loads((phase/'result.json').read_bytes())
    require(result==dict(cleanup_only=True,output_certified=False,archive_preserved=True,failed_spec_sha256=cleanup.FAILED_SPEC,
        frozen_manifest_sha256=cleanup.FAILED_MANIFEST,retired_packages=317),'Native result exceeded cleanup-only scope')
    record=json.loads((phase/'cleanup.json').read_bytes());remaining=cleanup.scan(Path(manifest['root']),manifest,remaining=True)
    require(remaining==record['remaining'],'Residual census changed after native exit')
    strict_cleanup(spec,record)
    require(not os.path.lexists(manifest['root']),'Failed namespace physically survived')
    cleanup.scan(Path(spec['archive_root']),archive)
    atomic_json(root/'host-result.json',dict(whole_exit=0,guard_empty=True,cleanup_only=True,output_certified=False,
        failed_fixture_physically_absent=True,archive_preserved=True,archive_files=317,archive_bytes=49362728,
        frozen_manifest_sha256=cleanup.FAILED_MANIFEST,spec_sha256=spec_row['sha256'],guard=evidence,engine_log=engine_log,native=native))
    print('TRACK FAILED317 CLEANUP HOST PASS; FAILED OUTPUTS NEVER CERTIFIED',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('prepare','stage','run'))
    parser.add_argument('--failed',type=Path);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.action=='run':run(args.output)
    else:
        require(args.failed is not None,'Original failed phase required')
        (prepare if args.action=='prepare'else stage)(args.failed,args.output)


if __name__=='__main__':main()
