"""Host-only authority/freeze/finalize stages for independent equivalence.

prepare SPEC WORKSPACE creates a frozen spec and parser-job.json. Run the sibling
atomic_equivalence_parser.py in normally guarded Blender using the printed job
binding. finalize WORKSPACE OBSERVATIONS GUARD verifies positive whole cleanup,
rechecks immutable Git and all original/frozen bytes, then runs full comparison.
GUARD is a JSON file containing the ordinary receipt/stdout/marker/whole_result
binding. This tool deliberately never launches a native process itself.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
import atomic_equivalence as eq
from atelier.atomic_files import atomic_json


def binding(path):
    path=Path(path).absolute()
    row=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    eq.artifact(row)
    return row


def sources(value):
    if isinstance(value,dict):
        if set(value)=={'revision','path','sha256'}:yield value
        else:
            for child in value.values():yield from sources(child)
    elif isinstance(value,list):
        for child in value:yield from sources(child)


def prepare(spec_path, workspace, *, repo=eq.REPO):
    """Freeze exact artifacts only after independent immutable Git validation."""
    root=Path(workspace).absolute();eq.real_directory(root.parent)
    eq.require(not root.exists() and not root.is_symlink(),'Freeze workspace must be fresh')
    original=binding(spec_path);spec=eq.json_artifact(original)
    for row in sources(spec):eq.source_binding(row,repo)
    root.mkdir();originals=[];frozen=[];memo={};active=set()
    def freeze(value):
        if isinstance(value,list):return [freeze(v) for v in value]
        if not isinstance(value,dict):return value
        if set(value)!={'path','sha256'}:return {k:freeze(v) for k,v in value.items()}
        key=(value['path'],value['sha256'])
        eq.require(key not in active,'Cyclic artifact evidence')
        if key in memo:return memo[key]
        active.add(key);payload=eq.artifact(value);originals.append(value)
        # JSON descriptors may contain further SHA-bound artifacts.
        if Path(value['path']).suffix.lower()=='.json':
            payload=eq.canonical(freeze(json.loads(payload)))
        digest=hashlib.sha256(payload).hexdigest()
        target=root/'files'/(hashlib.sha256(value['path'].encode()).hexdigest()+'-'+digest+Path(value['path']).suffix)
        target.parent.mkdir(exist_ok=True);target.write_bytes(payload)
        result=binding(target);frozen.append(result);memo[key]=result;active.remove(key)
        return result
    frozen_spec=freeze(spec)
    spec_file=root/'spec.json';atomic_json(spec_file,frozen_spec)
    exports=[]
    for owner in frozen_spec['regions'].values():
        for asset in owner['assets'].values():
            for key in ('baseline_exports','actual_exports'):
                for row in asset[key]:
                    if Path(row['path']).suffix.lower()=='.fbx' and row not in exports:exports.append(row)
    job=root/'parser-job.json';atomic_json(job,dict(schema=1,exports=exports))
    record=dict(schema=1,original_spec=original,spec=binding(spec_file),originals=originals,
        frozen=frozen,job=binding(job))
    atomic_json(root/'host-record.json',record)
    recheck(record,repo)
    return record


def recheck(record,repo):
    original=eq.json_artifact(record['original_spec'])
    for row in sources(original):eq.source_binding(row,repo)
    for row in [record['spec'],record['job'],*record['originals'],*record['frozen']]:eq.artifact(row)


def observations(record,value):
    job=eq.json_artifact(record['job'])
    eq.require(isinstance(value,dict) and set(value)=={'schema','job_sha256','rows'}
        and value['schema']==1 and value['job_sha256']==record['job']['sha256']
        and isinstance(value['rows'],list),'Unbound parser observation')
    expected={(r['path'],r['sha256']) for r in job['exports']};result={}
    for row in value['rows']:
        eq.require(isinstance(row,dict) and set(row)=={'input','triangles','render','collision'},'Incomplete FBX observation')
        eq.artifact(row['input']);key=(row['input']['path'],row['input']['sha256'])
        eq.require(key in expected and key not in result,'Unexpected/duplicate FBX observation')
        eq.require(type(row['triangles']) is int and row['triangles']>0,'Missing observed FBX triangles')
        counters={}
        for field in ('render','collision'):
            values=row[field]
            eq.require(isinstance(values,dict) and all(isinstance(k,str) and eq.HEX.fullmatch(k)
                and type(v) is int and v>0 for k,v in values.items()),'Invalid complete FBX counter')
            counters[field]=Counter({bytes.fromhex(k):v for k,v in values.items()})
        eq.require(counters['render'],'Missing positive FBX render observation')
        result[key]=(counters,row['triangles'])
    eq.require(set(result)==expected,'Missing FBX observation census rows')
    return result


def finalize(record, observed, guard, *, repo=eq.REPO, native=True, required_groups=eq.MINIMUM_GROUPS):
    """Host independently rechecks authority; guarded parser output is data, never PASS."""
    recheck(record,repo)
    eq.require(guard.get('marker')=='ATOMIC FBX OBSERVATIONS '+record['job']['sha256']+' '+observed['sha256'],
        'Parser guard marker does not bind exact job and observation bytes')
    eq.guard_binding(guard)
    parsed=observations(record,eq.json_artifact(observed))
    result=eq.verify(eq.json_artifact(record['spec']),repo=repo,native=native,
        required_groups=required_groups,observations=parsed)
    eq.artifact(observed);eq.guard_binding(guard);recheck(record,repo)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    first=commands.add_parser('prepare');first.add_argument('spec',type=Path);first.add_argument('workspace',type=Path)
    last=commands.add_parser('finalize');last.add_argument('workspace',type=Path);last.add_argument('observations',type=Path)
    last.add_argument('guard',type=Path);last.add_argument('--record-sha256',required=True);last.add_argument('--exporter-only',action='store_true')
    args=parser.parse_args()
    if args.command=='prepare':
        record=prepare(args.spec,args.workspace)
        print(json.dumps(dict(job=record['job'],record=binding(args.workspace/'host-record.json'))),flush=True);return 0
    record=eq.json_artifact(dict(path=str((args.workspace/'host-record.json').absolute()),sha256=args.record_sha256))
    result=finalize(record,binding(args.observations),
        json.loads(args.guard.read_bytes()),native=not args.exporter_only)
    atomic_json(args.workspace/'result.json',result)
    return 0 if (result['exporter_complete'] if args.exporter_only else result['complete']) else 1


if __name__=='__main__':raise SystemExit(main())
