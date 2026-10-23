"""Processless Blender stage. Run only through the normal bounded native guard.

The host prepares a SHA-bound job. This stage never checks Git, imports assets,
or accepts source authority. Its sole output is actual serialized FBX observations.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import atomic_equivalence as eq
from atelier.atomic_files import atomic_json


def parse(job_binding, output, *, reader=None):
    """@cc [owner:fontanierh,label:correctness] frozen-processless-fbx-parser
    Read the exact SHA-bound frozen FBX census and emit actual full corner/frame/
    channel/material/hull counters. MUST NOT call Git or start subprocesses. Check
    all input bytes again before publication; no adapter PASS grants acceptance.
    """
    payload=eq.artifact(job_binding);job=json.loads(payload)
    eq.require(set(job)=={'schema','exports'} and job['schema']==1
        and isinstance(job['exports'],list),'Invalid frozen parser job')
    reader=eq.fbx_counter if reader is None else reader
    seen=set();rows=[]
    for row in job['exports']:
        eq.artifact(row);key=(row['path'],row['sha256'])
        eq.require(key not in seen and Path(row['path']).suffix.lower()=='.fbx','Duplicate/unsupported frozen parser input')
        seen.add(key);values,count=reader(Path(row['path']))
        eq.require(set(values)=={'render','collision'} and all(isinstance(v,Counter) for v in values.values()),
            'Incomplete actual parser counters')
        rows.append(dict(input=row,triangles=count,**{k:{digest.hex():int(count) for digest,count in v.items()} for k,v in values.items()}))
        eq.artifact(row)
        print('FBX OBSERVATION '+str(len(rows))+'/'+str(len(job['exports'])),flush=True)
    for row in job['exports']:eq.artifact(row)
    eq.artifact(job_binding)
    result=dict(schema=1,job_sha256=hashlib.sha256(payload).hexdigest(),rows=rows)
    atomic_json(Path(output),result)
    print('ATOMIC FBX OBSERVATIONS '+hashlib.sha256(payload).hexdigest()+' '+hashlib.sha256(Path(output).read_bytes()).hexdigest(),flush=True)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job',type=Path,required=True)
    parser.add_argument('--sha256',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None)
    parse(dict(path=str(args.job.absolute()),sha256=args.sha256),args.output)


if __name__=='__main__':main()
