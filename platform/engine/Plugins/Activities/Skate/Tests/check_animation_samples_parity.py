#!/usr/bin/env python3
"""Convert all animation samples and verify C++ reconstruction against original decoding.

Native tracks collapse only bit-identical constant values. This is data conversion,
not animation evaluation; interpolation and runtime blend behavior need later tests.
Run through atelier.safety because both code and animation export execute here.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from check_gesture_parity import converter,PLUGIN
from reference_build import build_probe


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--target-dir',type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    exporter=build_probe(output,'animation-samples-reference',PLUGIN/'Tests/Reference/animation_samples_export.rs',args.target_dir)
    raw=output/'decoded';native=output/'native'
    subprocess.run([str(exporter),str(args.assets.resolve()),str(raw)],check=True)
    report=converter.convert_animation_samples(raw,native)
    code=PLUGIN/'Source/AtelierSkate/Private/Native';binary=output/'animation-samples-cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-I',str(code),
                    str(code/'AnimationSamples.cpp'),str(PLUGIN/'Tests/Native/animation_samples_probe.cpp'),'-o',str(binary)],check=True)
    actual=subprocess.check_output([str(binary),'rig',str(native/'rig.skate'),str(raw)])
    if actual!=(raw/'rig.raw').read_bytes():raise AssertionError('Native animation hierarchy or reference poses differ')
    actual=subprocess.check_output([str(binary),'all',str(native),str(raw)],input=(raw/'clips.txt').read_bytes())
    if int(actual)!=len(report['clips']):raise AssertionError('Not every exported clip was compared')
    first=native/'clips'/f'{report["clips"][0]["name"]}.skate'
    for mode,path in [('clip',first),('rig',native/'rig.skate')]:
        valid=path.read_bytes()
        for index,data in enumerate((b'',valid[:11],valid[:-1],valid+b'\0')):
            bad=output/f'invalid-{mode}-{index}.skate';bad.write_bytes(data)
            if subprocess.run([str(binary),mode,str(bad),str(raw)],capture_output=True).returncode!=2:
                raise AssertionError('Malformed native animation data was accepted')
    entries=report['clips']
    result=dict(passed=True,comparison='every original decoded word, every frame/bone, weights, loop transforms, hierarchy and poses',
                clips=len(entries),frames=sum(c['frames'] for c in entries),bone_samples=sum(c['frames']*c['bones'] for c in entries),
                constant_tracks=sum(c['constant_tracks'] for c in entries),tracks=sum(c['tracks'] for c in entries),
                original_decoded_bytes=sum(c['source_bytes'] for c in entries),native_bytes=sum(c['native_bytes'] for c in entries),
                rig_sha256=report['rig_sha256'],manifest_sha256=hashlib.sha256((native/'samples-manifest.json').read_bytes()).hexdigest())
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
