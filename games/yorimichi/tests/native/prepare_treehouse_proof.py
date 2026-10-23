"""Host-only immutable Git authority preflight/postcheck; never run inside a native guard."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from atelier.atomic_files import atomic_json
from atelier.build_inputs import local_imports
from atelier.export_manifest import real_directory

GAME=Path(__file__).resolve().parents[2]
REPO=GAME.parents[1]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(paths):
    result={}
    for path in sorted(set(paths)):
        if path.is_symlink() or not path.is_file():raise ValueError('Missing/linked explicit proof source')
        info=path.stat()
        result[str(path)]=dict(sha256=sha(path),size=info.st_size,device=info.st_dev,inode=info.st_ino,
            mtime_ns=info.st_mtime_ns,ctime_ns=info.st_ctime_ns)
    return result


def revision(root):return subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()


def verify(manifest,native_result=None,guard=None,whole_exit=None):
    value=json.loads(manifest.read_text())
    if value.get('schema')!=1 or not isinstance(value.get('repo'),str):raise ValueError('Foreign proof attestation')
    subject=real_directory(Path(value['repo']))
    if not subject.is_absolute():raise ValueError('Proof subject must be canonical and absolute')
    if revision(subject)!=value['source_head'] or revision(Path(value['donor']))!=value['donor_head']:
        raise ValueError('Proof source/donor Git head changed')
    if subprocess.check_output(['git','status','--porcelain'],cwd=subject,text=True).strip():raise ValueError('Proof source is dirty')
    for field in ('current_source','donor_inputs','archive_files'):
        if snapshot([Path(path) for path in value[field]])!=value[field]:raise ValueError('Proof source bytes/stat identities changed')
    if native_result is not None:
        result=json.loads(native_result.read_text());terminal=json.loads((guard/'memory-health-tree.json').read_text())
        timing=json.loads((guard/'execution-timings.json').read_text())
        if (whole_exit!=0 or result.get('complete') is not True or result.get('source_head')!=value['source_head']
                or result.get('host_attestation_sha256')!=sha(manifest) or terminal.get('state')!='child_exited'
                or terminal.get('cleanup_complete') is not True or terminal.get('processes')!=[]
                or terminal.get('late_reporters',{}).get('unresolved')!=[]
                or type(timing.get('child_lifetime_seconds')) not in (int,float)):
            raise ValueError('Whole native/guard result or final authority is incomplete')
        atomic_json(manifest.parent/'postcheck.json',dict(schema=1,complete=True,whole_exit=0,
            source_head=value['source_head'],attestation_sha256=sha(manifest),native_result_sha256=sha(native_result)))
    return value


def prepare(donor,donor_head,baseline,output):
    if os.path.lexists(output):raise ValueError('Host proof preparation must be fresh')
    real_directory(output.parent)
    if revision(donor)!=donor_head:raise ValueError('Unexpected donor head')
    if subprocess.check_output(['git','status','--porcelain'],cwd=REPO,text=True).strip():raise ValueError('Proof source must be clean')
    import sys
    sys.path.insert(0,str(GAME/'world'))
    from material_specs import MATERIALS
    names=('backpack','barrel','basket','bell','bookshelf','crate_desk','futon','globe','kamado','log_table','planter','stump_kettle','telescope')
    models=[GAME/'assets/treehouse/props'/name/(name+'.glb') for name in names]
    scripts=[GAME/'world/regions/treehouse'/name for name in ('geometry_data.py','plan_surface.py','plan_tree.py',
        'plan_prop.py','canopy_data.py','assemble_atomic.py')]
    scripts.extend([GAME/'treehouse_atomic_build.py',GAME/'treehouse_pieces.py',GAME/'treehouse_surfaces.py',
        GAME/'world/export_region_piece.py',Path(__file__),Path(__file__).with_name('treehouse_atomic_equivalence.py')])
    closure=set(scripts)
    for script in scripts:closure.update(local_imports(script,(GAME/'world',GAME/'world/regions',GAME)))
    closure.update((GAME/'assets/treehouse/export-parameters').glob('*.json'));closure.update(models)
    inputs=[donor/'build/yorimichi/heightmap.npy',*(donor/'build/yorimichi/textures'/row['texture'] for row in MATERIALS.values() if 'texture' in row)]
    current_source=snapshot(list(closure));donor_inputs=snapshot(inputs)
    output.mkdir();archive=output/'baselines';archive.mkdir();baseline_files={}
    for name in ('build','layout','tmesh','trees','props','dressing'):
        relative='games/yorimichi/world/regions/treehouse/'+name+'.py'
        data=subprocess.check_output(['git','show',baseline+':'+relative],cwd=REPO)
        path=archive/(name+'.py');path.write_bytes(data);baseline_files[relative]=sha(path)
    for path in models:
        if subprocess.check_output(['git','show',baseline+':'+str(path.relative_to(REPO))],cwd=REPO)!=path.read_bytes():
            raise ValueError('Committed model differs from immutable original')
    value=dict(schema=1,repo=str(REPO),source_head=revision(REPO),donor=str(donor),donor_head=donor_head,
        baseline_revision=baseline,baseline_files=baseline_files,archive=str(archive),archive_files=snapshot(list(archive.glob('*.py'))),
        current_source=current_source,donor_inputs=donor_inputs)
    path=output/'attestation.json';atomic_json(path,value);verify(path)
    print('HOST TREEHOUSE ATTESTATION',str(path),sha(path),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--donor',type=Path);parser.add_argument('--donor-head');parser.add_argument('--baseline',default='283329c07')
    parser.add_argument('--output',type=Path);parser.add_argument('--verify',type=Path)
    parser.add_argument('--result',type=Path);parser.add_argument('--guard',type=Path);parser.add_argument('--whole-exit',type=int)
    args=parser.parse_args()
    if args.verify:verify(args.verify,args.result,args.guard,args.whole_exit)
    else:prepare(args.donor,args.donor_head,args.baseline,args.output)


if __name__=='__main__':main()
