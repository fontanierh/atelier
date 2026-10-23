"""Host-only Bike native fixture preparation and bounded warm-project execution.

Prepare from the source writer after committing. Execute only from the receiving
checkout's own uv environment after its module/observer is compiled and current.
Neither mode builds, compiles, rewrites stamps or runs Git inside Unreal.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

from atelier.atomic_files import atomic_json
from atelier.export_manifest import real_directory

GAME=Path(__file__).resolve().parents[2];REPO=GAME.parents[1]
BASELINE='283329c07ea04bee34587022a3d43827468c66d7'
NATIVE_NAMES=('import_bike.py','mesh_import.py','bike_material.py')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(root,*args):return subprocess.check_output(['git',*args],cwd=root)


def source_head(root):
    if git(root,'status','--porcelain'):raise ValueError('Freeze the entire source checkout before native acceptance')
    return git(root,'rev-parse','HEAD').decode().strip()


def regular(path):
    path=Path(path).absolute();real_directory(path.parent)
    if path.is_symlink() or not path.is_file():raise ValueError('Regular byte-bound native input required: '+str(path))
    return path


def prepare(args):
    root=real_directory(args.output.absolute());receiving=real_directory(args.receiving.absolute())
    if os.path.lexists(root):raise ValueError('Fresh exclusive Bike native proof root required')
    head=source_head(REPO);warm_head=source_head(receiving)
    baseline=real_directory(args.baseline.absolute());current=real_directory(args.current.absolute())
    original_guard=json.loads((baseline.parent/'guard/memory-health-tree.json').read_text())
    assert original_guard['state']=='child_exited' and original_guard['cleanup_complete'] and not original_guard['processes']
    original_whole=json.loads((baseline.parent/'whole-result.json').read_text())
    assert original_whole['exit_code']==0 and original_whole['baseline']==BASELINE
    assert (baseline.parent/'original.py').read_bytes()==git(REPO,'show',BASELINE+':games/yorimichi/assets/vehicles/bike/build.py')
    actual_guard=json.loads((current.parents[1]/'guard/memory-health-tree.json').read_text())
    assert actual_guard['state']=='child_exited' and actual_guard['cleanup_complete'] and not actual_guard['processes']
    root.mkdir();archive=root/'archive';archive.mkdir();frozen={};inputs={};donor={}
    for name in NATIVE_NAMES:
        path=archive/('original_'+name);path.write_bytes(git(REPO,'show',BASELINE+':games/yorimichi/unreal/Scripts/'+name));frozen[name]=path
    old_cpp=archive/'original_BikeComponent.cpp';old_cpp.write_bytes(git(REPO,'show',BASELINE+':games/yorimichi/unreal/Source/Yorimichi/BikeComponent.cpp'))
    warm_game=receiving/'games/yorimichi';scripts=warm_game/'unreal/Scripts'
    sys.path.insert(0,str(Path(__file__).parent))
    from bike_native_source import cpp_pose
    pose=cpp_pose(old_cpp.read_text())
    assert cpp_pose((warm_game/'unreal/Source/Yorimichi/BikeComponent.cpp').read_text())==pose,'Actual runtime Pose body changed; requires a separate behavior proof'
    assert frozen['bike_material.py'].read_bytes()==(scripts/'bike_material.py').read_bytes(),'Native material graph changed; add an independent graph proof'
    def copy(source,target):
        source=regular(source);digest=sha(source);target.parent.mkdir(parents=True,exist_ok=True)
        if os.path.lexists(target):raise ValueError('Native fixture input destination exists')
        shutil.copy2(source,target)
        assert sha(source)==sha(target)==digest
        inputs[str(target)]=digest;donor[str(source)]=digest
    old_manifest=json.loads((baseline/'data/bike/manifest.json').read_text())
    actual_manifest=json.loads((current/'bike/manifest.json').read_text())
    old_data=root/'data/original';new_data=root/'data/current'
    copy(baseline/'data/bike/manifest.json',old_data/'bike/manifest.json')
    for name in old_manifest['parts']:copy(baseline/'data/bike/assets'/(name+'.fbx'),old_data/'bike/assets'/(name+'.fbx'))
    copy(current/'bike/manifest.json',new_data/'bike/manifest.json');copy(current/'bike/assets/manifest.json',new_data/'bike/assets/manifest.json')
    for name in actual_manifest['parts']:copy(current/'bike/assets'/(name+'.fbx'),new_data/'bike/assets'/(name+'.fbx'))
    from atelier.build_inputs import local_imports
    roots=(warm_game,warm_game/'world',scripts,receiving/'platform/studio',receiving/'platform/harness')
    code=set(local_imports(scripts/'import_bike.py',roots))
    code.update(local_imports(scripts/'atomic_equivalence_capture.py',roots))
    code.update(local_imports(Path(__file__).with_name('bike_native_equivalence.py'),(Path(__file__).parent,)))
    code.update((Path(__file__),Path(__file__).with_name('bike_native_equivalence.py'),old_cpp,*frozen.values(),
        warm_game/'tools/atomic_equivalence.py',warm_game/'unreal/Source/Yorimichi/BikeComponent.cpp',
        warm_game/'unreal/Source/Yorimichi/BikeMeshComponent.cpp',warm_game/'unreal/Source/Yorimichi/BikeMeshComponent.h'))
    proof_inputs=(baseline.parent/'whole-result.json',baseline.parent/'guard/memory-health-tree.json',
                  baseline/'result.json',baseline.parent/'original.py',
                  current.parents[1]/'whole-result.json',current.parents[1]/'guard/memory-health-tree.json',
                  current.parent/'result.json')
    for path in (*code,*proof_inputs):inputs[str(regular(path))]=sha(path)
    spec=dict(schema=1,source_head=head,receiving_head=warm_head,receiving=str(receiving),inputs=inputs,donor_inputs=donor,
        content=str(warm_game/'unreal/Content'),original_receiver=str(frozen['import_bike.py']),original_mesh_import=str(frozen['mesh_import.py']),
        original_material=str(frozen['bike_material.py']),current_material=str(scripts/'bike_material.py'),
        current_receiver=str(scripts/'import_bike.py'),original_data=str(old_data),current_data=str(new_data),
        capture=str(scripts/'atomic_equivalence_capture.py'),harness=str(warm_game/'tools/atomic_equivalence.py'),
        fixture=str(Path(__file__).with_name('bike_native_equivalence.py')),baseline_revision=BASELINE,
        unchanged_runtime_pose_sha256=hashlib.sha256(pose.encode()).hexdigest())
    atomic_json(root/'spec.json',spec)
    assert source_head(REPO)==head and source_head(receiving)==warm_head
    print('BIKE NATIVE FIXTURE PREPARED; NO NATIVE LAUNCH',flush=True)
    print(root/'spec.json',flush=True)


def bindings(spec):
    for field in ('inputs','donor_inputs'):
        for path,digest in spec[field].items():assert sha(regular(path))==digest,path


def run(args):
    root=real_directory(args.output.absolute());spec_path=regular(root/'spec.json');raw=spec_path.read_bytes();spec=json.loads(raw)
    receiving=Path(spec['receiving']);assert source_head(REPO)==spec['source_head'] and source_head(receiving)==spec['receiving_head']
    bindings(spec)
    from atelier import build
    from atelier.harness.safety import guarded
    ctx=build.Context('yorimichi')
    if ctx.game_dir!=receiving/'games/yorimichi':raise ValueError('Execute from the receiving checkout uv environment; no source/path overrides')
    sys.path.insert(0,str(ctx.game_dir/'tools'))
    from network_review_common import current_native_build
    native=current_native_build(ctx)  # Refuses a stale/missing compile; never builds it.
    fixture_root=Path(spec['content'])/'AtelierValidation/BikeAtomicNativeCanary'
    real_directory(fixture_root)
    if os.path.lexists(fixture_root):raise ValueError('Native canary root already exists')
    command=build.UnrealScript(Path(spec['fixture']),'BIKE NATIVE ORIGINAL/CURRENT FIXTURE COMPLETE',null_rhi=True,
        modules=('Yorimichi',),args=('-nosound','-noshaderworker'))
    with command.prepared(ctx) as (argv,overrides):
        env=dict(ctx.env(),**dict(overrides),ATELIER_BIKE_NATIVE_ROOT=str(root),
            ATELIER_BIKE_NATIVE_SPEC_SHA=hashlib.sha256(raw).hexdigest(),ATELIER_BUILD_ROOT=str(root/'native-build'))
        for name in ('ATELIER_BUILD_TASK','ATELIER_MESH_REUSE_NONCE'):
            if name in env:raise ValueError('Native fixture must not inherit a normal task/reuse context')
        code=guarded.run(argv,root/'guard',timeout=600,kind='job',purpose='PR575 immutable original/current Bike native acceptance',env=env,progress=15.,track_tree=True)
    atomic_json(root/'whole-result.json',dict(exit_code=code,source_head=spec['source_head'],receiving_head=spec['receiving_head'],native=native))
    if code:raise SystemExit(code)
    guard=json.loads((root/'guard/memory-health-tree.json').read_text())
    assert guard['state']=='child_exited' and guard['cleanup_complete'] and guard['processes']==[] and not guard.get('late_reporters',{}).get('unresolved')
    assert command.marker in (root/'guard/stdout.log').read_text()
    assert spec_path.read_bytes()==raw and source_head(REPO)==spec['source_head'] and source_head(receiving)==spec['receiving_head']
    bindings(spec);assert current_native_build(ctx)==native
    result=json.loads((root/'result.json').read_text());cleanup=json.loads((root/'cleanup.json').read_text())
    assert cleanup['root']==str(fixture_root)
    actual={}
    if fixture_root.exists():
        for path in fixture_root.rglob('*'):
            mode=path.lstat().st_mode;assert not path.is_symlink()
            if stat.S_ISREG(mode):actual[str(path.relative_to(fixture_root))]=sha(path)
            else:assert stat.S_ISDIR(mode)
    assert actual==cleanup['remaining']
    # Supported editor deletion already ran; remove only its exact unchanged residuals
    # after positive whole/empty cleanup and preserve their complete identities above.
    for name in actual:(fixture_root/name).unlink()
    if fixture_root.exists():
        for directory in sorted((p for p in fixture_root.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):directory.rmdir()
        fixture_root.rmdir()
    assert not os.path.lexists(fixture_root)
    module_spec=importlib.util.spec_from_file_location('actual_bike_native_harness',spec['harness'])
    harness=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(harness);comparisons={}
    for logical,record in result['native'].items():
        before=harness.native_raw_set(record['baseline'],logical);after=harness.native_raw_set(record['actual'],logical)
        for field in ('source_lods','render_lods','cooked','hulls','settings','source_presence'):
            assert before[field]==after[field],(logical,'Saved native geometry/policy union differs',field)
        if logical=='BK_Steer':
            # The original runtime disables collision for the whole Bike. Its whole
            # steering mesh does not provide matching query-enabled component hits;
            # preserve that limitation instead of calling isolated-piece parity PASS.
            controls=after['probes']['controls']
            for mesh in after['meshes']:
                selected=[row for row in controls if row['target']==mesh]
                assert {row['kind'] for row in selected}=={'ray_positive','capsule_positive','ray_negative','capsule_negative'}
                for row in selected:
                    assert (row['hit'] is not None)==row['kind'].endswith('_positive')
            probes=dict(current_piece_positive_controls=True,synthetic_original_whole_parity=False)
        else:
            probes=harness.compare_probes(before['probes'],after['probes'],logical,set(after['meshes']),set(before['meshes']),after['seams'])
        comparisons[logical]=dict(source=True,render=True,cooked=True,hulls=True,settings=True,probes=probes)
    atomic_json(root/'host-result.json',dict(whole_exit=0,guard_empty=True,fixture_absent=True,comparisons=comparisons,
        source_head=spec['source_head'],receiving_head=spec['receiving_head'],native=native,
        complete=False,missing=['actual production Bike owner/clip/network invocation','normal task reuse counts','synthetic query-enabled original whole steering versus isolated-piece parity'],
        scope='strict saved/reloaded actual native geometry plus explicit fixture query/NoCollision/posed-bounds and retirement proof'))
    print('BIKE NATIVE SAVED GEOMETRY/QUERY FIXTURE PASS; PRODUCTION RUNTIME/REUSE REMAIN SEPARATE',flush=True)


def main():
    parser=argparse.ArgumentParser();mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare',action='store_true');mode.add_argument('--run',action='store_true')
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--receiving',type=Path)
    parser.add_argument('--baseline',type=Path);parser.add_argument('--current',type=Path);args=parser.parse_args()
    if args.prepare:
        if any(value is None for value in (args.receiving,args.baseline,args.current)):parser.error('Preparation requires receiving, baseline and current roots')
        prepare(args)
    else:run(args)


if __name__=='__main__':main()
