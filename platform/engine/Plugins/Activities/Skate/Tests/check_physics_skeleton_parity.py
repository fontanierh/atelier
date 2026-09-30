#!/usr/bin/env python3
"""Verify every physical skeleton word and typed transform against the original loader."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from check_gesture_parity import converter,PLUGIN
from reference_build import build_probe


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--target-dir',type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    reference=build_probe(output,'physics-skeleton-reference',PLUGIN/'Tests/Reference/physics_skeleton_probe.rs',args.target_dir)
    code=PLUGIN/'Source/AtelierSkate/Private/Native';binary=output/'physics-skeleton-cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-I',str(code),str(code/'PhysicsSkeleton.cpp'),str(PLUGIN/'Tests/Native/physics_skeleton_probe.cpp'),'-o',str(binary)],check=True)
    source=args.assets.resolve()/'private/stock/physics-skeletons.json';value=json.loads(source.read_text());identity=value['source_sha256'];native=output/'physics-skeletons.skate'
    encoded=converter.encode_physics_skeletons(source);native.write_bytes(encoded)
    combined=bytearray();queries=0
    for skeleton in value['skeletons']:
        for name in (skeleton['name'],skeleton['name'].lower()):
            expected=subprocess.check_output([str(reference),str(source),identity,name]);actual=subprocess.check_output([str(binary),str(native),identity,name])
            if actual!=expected:raise AssertionError(f'Physical skeleton differs: {name}')
            combined.extend(actual);queries+=1
    for wrong_identity,name in ((identity,'absent'),('wrong-bank',value['skeletons'][0]['name'])):
        for tool,path in ((reference,source),(binary,native)):
            if subprocess.run([str(tool),str(path),wrong_identity,name],capture_output=True).returncode!=2:raise AssertionError('Invalid lookup accepted')
    for i,broken in enumerate((b'',encoded[:12],encoded[:-1],encoded+b'\0')):
        invalid=output/f'invalid-{i}.skate';invalid.write_bytes(broken)
        if subprocess.run([str(binary),str(invalid),identity,value['skeletons'][0]['name']],capture_output=True).returncode!=2:raise AssertionError('Malformed physical skeleton accepted')
    result=dict(passed=True,skeletons=len(value['skeletons']),bones=sum(len(s['bones']) for s in value['skeletons']),queries=queries,native_bytes=len(encoded),sha256=hashlib.sha256(encoded).hexdigest(),output_sha256=hashlib.sha256(combined).hexdigest(),comparison='all 28 words per bone, typed size/rotation/translation, record identities and names')
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
