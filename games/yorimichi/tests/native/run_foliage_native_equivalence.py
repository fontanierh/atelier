"""Parent-invoked guarded foliage phase/finalizer. No native work runs on import."""
import argparse
import json
import os
from pathlib import Path
import sys

from atelier import build
from atelier.atomic_files import atomic_json
from atelier.export_manifest import real_directory
from atelier.harness.safety import guarded

GAME=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(GAME/'tools'),str(Path(__file__).parent)]
from atomic_equivalence import artifact,guard_binding,require  # noqa: E402
from foliage_native_equivalence import bound_inputs,compare,require_fixture_context,sha  # noqa: E402
from track_native_equivalence import check_private_launch,startup_ddc  # noqa: E402
from run_track_native_equivalence import binding,head,strict_cleanup  # noqa: E402


def run(workspace,phase):
    require_fixture_context(os.environ)
    root=real_directory(Path(workspace).absolute());output=root/phase;spec_path=output/'spec.json'
    row=binding(spec_path);payload=artifact(row);spec=json.loads(payload)
    require(spec['phase']==phase,'Wrong foliage receiving phase')
    receiver,source=Path(spec['receiving']),Path(spec['source'])
    require(Path.cwd().resolve()==receiver.resolve() and head(receiver)==spec['receiving_head']
        and head(source)==spec['source_head'] and head(Path(spec['producer']))==spec['producer_head'],
        'Pinned clean stopped source/receiver/producer required')
    bound_inputs(spec);launch=check_private_launch(spec)
    require(not os.path.lexists(launch['startup_log']),'Fresh bound full engine log required')
    guard=output/'guard';fixture=Path(spec['content'])/spec['package'].removeprefix('/Game/')
    real_directory(fixture)
    require(not os.path.lexists(guard) and not os.path.lexists(output/'whole-result.json')
        and not os.path.lexists(fixture),'Fresh guard/absent original fixture required')
    if phase=='current':
        original=json.loads((root/'original/host-result.json').read_bytes())
        require(original['whole_exit']==0 and original['guard_empty'] and original['fixture_absent']
            and original['spec_sha256']==sha(root/'original/spec.json'),'Original phase not independently finalized')
        guard_binding(original['guard'])
    ctx=build.Context('yorimichi');require(ctx.game_dir==receiver/'games/yorimichi','Wrong receiving project')
    sys.path.insert(0,str(receiver/'games/yorimichi/tools'))
    from network_review_common import current_native_build
    native=current_native_build(ctx)
    script=Path(__file__).with_name('foliage_native_equivalence.py')
    require(spec['inputs'].get(str(script.absolute()))==sha(script),'Unbound actual native driver')
    marker='FOLIAGE ACTUAL18/84/150 NATIVE FIXTURE COMPLETE '+phase+' '+row['sha256']
    command=build.UnrealScript(script,marker,modules=('Yorimichi',),null_rhi=True,
        args=('-nosound','-noshaderworker','-ForceDPCVars=r.GenerateMeshDistanceFields=0,r.MeshCardRepresentation=0',*launch['args']))
    with command.prepared(ctx)as(argv,overrides):
        require([v for v in argv if v in launch['args']]==launch['args'],'Private launch arguments changed')
        env=dict(ctx.env(),**dict(overrides),ATELIER_FOLIAGE_NATIVE_SPEC=str(spec_path),ATELIER_FOLIAGE_NATIVE_SHA256=row['sha256'])
        code=guarded.run(argv,guard,timeout=900,queue_seconds=1200,limit_gib=10,kind='job',
            purpose='Paired real foliage owners18/84 source packages/150 native LOD pages '+phase,env=env,progress=15.,track_tree=True)
    atomic_json(output/'whole-result.json',dict(exit_code=code,native=native,phase=phase,source_head=spec['source_head'],
        receiving_head=spec['receiving_head'],producer_head=spec['producer_head'],spec_sha256=row['sha256'],launch=launch,argv=argv))
    if code:raise SystemExit(code)
    evidence=dict(receipt=binding(guard/'memory-health-tree.json'),stdout=binding(guard/'stdout.log'),
        marker=marker,whole_result=binding(output/'whole-result.json'))
    guard_binding(evidence)
    require(current_native_build(ctx)==native and head(receiver)==spec['receiving_head'] and head(source)==spec['source_head'] and head(Path(spec['producer']))==spec['producer_head'],
        'Actual native/source/producer identity changed')
    bound_inputs(spec);require(artifact(row)==payload,'Frozen receiving spec changed')
    engine_log=binding(launch['startup_log'])
    ddc=startup_ddc(launch,artifact(engine_log).decode(errors='replace'));observed=json.loads((output/'startup-ddc.json').read_bytes())
    require(observed['launch']==launch and all(observed[k]==v for k,v in ddc.items()),'Private startup evidence differs')
    records=json.loads((output/'native.json').read_bytes());require(set(records)=={phase},'Wrong native phase records')
    strict_cleanup(spec,json.loads((output/'cleanup.json').read_bytes()))
    result=dict(schema=1,complete=False,native_complete=False,whole_exit=0,guard_empty=True,fixture_absent=True,
        phase=phase,spec_sha256=row['sha256'],native=native,guard=evidence,launch=launch,startup_ddc=ddc,engine_log=engine_log,
        source_head=spec['source_head'],receiving_head=spec['receiving_head'])
    atomic_json(output/'host-result.json',result)
    if phase=='current':
        paired=json.loads((root/'original/native.json').read_bytes());paired.update(records)
        original=json.loads((root/'original/host-result.json').read_bytes())
        require(original['native']==native,'Original/current compiled modules differ')
        atomic_json(root/'host-result.json',dict(**compare(paired,spec['manifests']),whole_exit=0,guards_empty=True,fixture_absent=True,
            native=native,source_head=spec['source_head'],receiving_head=spec['receiving_head'],
            original_guard=original['guard'],current_guard=evidence,launches=dict(original=original['launch'],current=launch)))
    print('FOLIAGE GUARDED PHASE FINALIZED '+phase+'; fixture scope only',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--workspace',type=Path,required=True)
    parser.add_argument('--phase',choices=('original','current'),required=True);args=parser.parse_args();run(args.workspace,args.phase)


if __name__=='__main__':main()
