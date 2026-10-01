#!/usr/bin/env python3
"""Exact rounded triangle sweep differential checks against reference 46513a6.

Run through atelier.safety; the complete original core module layout is frozen
in the supplied game build directory and compiled without numerical edits.
"""
import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import random
import shutil
import struct
import subprocess
import tarfile

from session_parity import PLUGIN, REFERENCE_REVISION, digest


def bits(value):
    return struct.unpack('<I',struct.pack('<f',value))[0]


def corpus():
    rng=random.Random(0x82adeb70)
    records=[];cases=[]
    def add(label,start,direction,vertices,line_radius,fatness,initial=None):
        if initial is None:
            initial=[bits(v) for v in (101.,-102.,103.,104.,-105.,106.,107.,108.,-109.,110.)]
        words=initial+[bits(v) for v in list(start)+list(direction)+list(vertices)+[line_radius,fatness]]
        assert len(words)==27
        records.append(struct.pack('<27I',*words))
        cases.append(dict(case=len(cases),label=label,initial_words=initial,
                          line_radius_bits=bits(line_radius),fatness_bits=bits(fatness)))
    triangles=([0.,0.,0.,2.,0.,0.,0.,2.,0.], [0.,0.,0.,0.,2.,0.,2.,0.,0.],
               [0.]*9, [0.,0.,0.,1.,0.,0.,2.,0.,0.])
    points=([.5,.5,1.], [0.,0.,1.], [2.,0.,1.], [0.,2.,1.], [1.,0.,1.],
            [0.,1.,1.], [1.,1.,1.], [-1.,-1.,0.], [2.,2.,0.], [.5,.5,0.])
    directions=([0.,0.,-2.],[0.,0.,2.],[0.,0.,0.],[1.,0.,-1.])
    for vertices in triangles:
        for start in points:
            for direction in directions:
                for line_radius in (0.,-0.,.005,.05,.5,1.,-.1):
                    for fatness in (0.,.005,.05,.5,-.005):
                        add('feature/winding/radius boundaries',start,direction,vertices,line_radius,fatness)
    # Sphere accepts an end-of-segment tangent that cylinder rejects. Both
    # source predicates are exercised at equality and neighboring input bits.
    for radius in (.001,.015,.045,.12,.5,1.,2.):
        for height in (0.,radius*.5,radius,1.,2.):
            for travel in (-.000001,0.,.000001,-1.,-2.,-4.):
                for start,label in (([-radius,0.,height],'vertex tangent'),
                                    ([-radius,1.,height],'edge tangent'),
                                    ([-radius*.7,-radius*.7,height],'vertex rounded'),
                                    ([-radius*.5,1.,height],'edge rounded'),
                                    ([.5,.5,height],'face/overlap')):
                    for fatness in (0.,radius*.25):
                        add(label,start,[0.,0.,travel],triangles[0],radius,fatness)
    for _ in range(4096):
        vertices=[rng.uniform(-20.,20.) for _ in range(9)]
        start=[rng.uniform(-20.,20.) for _ in range(3)]
        direction=[rng.uniform(-40.,40.) for _ in range(3)]
        add('random world triangles',start,direction,vertices,rng.uniform(0.,2.),rng.uniform(0.,.1))
    # Concentrate rays around a real triangle, including interior, edge and
    # vertex candidates, both sides, steep/parallel approaches, and long travel.
    for _ in range(4096):
        scale=rng.choice((.001,.01,.1,1.,10.,100.))
        vertices=[v*scale for v in triangles[rng.randrange(2)]]
        radius=rng.uniform(.005,.5)*scale
        start=[rng.uniform(-.6,2.6)*scale,rng.uniform(-.6,2.6)*scale,rng.uniform(-2.,2.)*scale]
        direction=[rng.uniform(-1.,1.)*scale,rng.uniform(-1.,1.)*scale,rng.uniform(-4.,4.)*scale]
        add('scaled face/edge/vertex approaches',start,direction,vertices,radius,rng.uniform(0.,.05)*scale)
    # The caller's untouched fields include opaque payloads, not merely zeroes.
    # Thin misses retain the entire record; rounded misses rewrite selected
    # fields while leaving the position/volume words, including NaNs, intact.
    for _ in range(1024):
        initial=[rng.getrandbits(32) for _ in range(10)]
        add('opaque incoming fields',[5.,5.,5.],[0.,0.,-1.],triangles[0],rng.choice((0.,.1)),0.,initial)
    for value in (float('nan'),float('inf'),-float('inf')):
        for vertices in triangles:
            for start in points:
                add('exceptional radius',start,[0.,0.,-2.],vertices,value,0.)
                add('exceptional fatness',start,[0.,0.,-2.],vertices,.05,value)
    return struct.pack('<I',len(records))+b''.join(records),cases


def build_probes(output):
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip())
    relative=(PLUGIN/'ThirdParty/skate-runtime/crates/skate-core/src').relative_to(root).as_posix()
    revision=subprocess.check_output(['git','rev-parse',REFERENCE_REVISION],cwd=root,text=True).strip()
    archive=subprocess.check_output(['git','archive',f'{revision}:{relative}'],cwd=root)
    source=output/'reference-source'
    if source.exists():shutil.rmtree(source)
    source.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:stream.extractall(source,filter='data')
    originals={p.relative_to(source).as_posix():digest(p) for p in sorted(source.rglob('*.rs'))}
    # Root module declarations remain verbatim and retain Rust's directory
    # resolution. The added binary probe calls only the original public API.
    main=source/'geometry-sweep-oracle.rs'
    probe=PLUGIN/'Tests/Reference/geometry_sweep_probe.rs'
    main.write_text((source/'lib.rs').read_text()+probe.read_text().replace('//!','//'))
    reference=output/'geometry-sweep-reference'
    subprocess.run(['rustc','+1.97.1','--edition=2024','-O','-A','dead_code',str(main),'-o',str(reference)],check=True)
    for name,expected in originals.items():
        if digest(source/name)!=expected:raise AssertionError(f'Frozen numerical reference module changed: {name}')
    code=output/'native-source'
    if code.exists():shutil.rmtree(code)
    code.mkdir()
    original=PLUGIN/'Source/AtelierSkate/Private/Native'
    for name in ('NativeMath.h','NativeMath.cpp','Geometry.h','Geometry.cpp','GeometrySweep.h','GeometrySweep.cpp'):
        shutil.copy2(original/name,code/name)
    shutil.copy2(PLUGIN/'Tests/Native/geometry_sweep_probe.cpp',code/'geometry_sweep_probe.cpp')
    cpp=output/'geometry-sweep-cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-Wall','-Wextra','-Werror',
                    '-I',str(code),str(code/'NativeMath.cpp'),str(code/'Geometry.cpp'),str(code/'GeometrySweep.cpp'),
                    str(code/'geometry_sweep_probe.cpp'),'-o',str(cpp)],check=True)
    provenance=dict(reference_revision=revision,source_archive_sha256=hashlib.sha256(archive).hexdigest(),
        original_source_sha256=originals,probe_sha256=digest(probe),reference_binary_sha256=digest(reference),
        cpp_binary_sha256=digest(cpp),native_source_sha256={p.name:digest(p) for p in sorted(code.iterdir())},
        rust_compiler=subprocess.check_output(['rustc','+1.97.1','-vV'],text=True).strip(),
        cpp_compiler=subprocess.check_output(['clang++','--version'],text=True).strip())
    (output/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    return cpp,reference


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json','provenance.json'):(output/name).unlink(missing_ok=True)
    inputs,cases=corpus();(output/'input.bin').write_bytes(inputs);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    cpp,reference=build_probes(output)
    expected=subprocess.check_output([str(reference)],input=inputs);actual=subprocess.check_output([str(cpp)],input=inputs)
    (output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual)
    if len(expected)!=len(cases)*48:raise AssertionError('Incomplete reference sweep output')
    if expected!=actual:
        first=next((i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b),min(len(expected),len(actual)))
        index=first//48
        report=dict(passed=False,first_byte=first,first_word=first//4,case=cases[index] if index<len(cases) else None,
                    field_word=(first%48)//4,reference_length=len(expected),cpp_length=len(actual),
                    reference_hex=expected[index*48:(index+1)*48].hex(),cpp_hex=actual[index*48:(index+1)*48].hex())
        (output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
    hits=0;miss_position_retained=0;miss_volume_retained=0;miss_normal_changed=0;miss_fraction_changed=0
    for case in cases:
        row=struct.unpack_from('<12I',expected,case['case']*48)
        if row[0]!=case['case']:raise AssertionError('Missing sweep output marker')
        hits+=row[1]
        if not row[1]:
            old=case['initial_words']
            miss_position_retained+=list(row[2:5])==old[:3]
            miss_normal_changed+=list(row[5:8])!=old[3:6]
            miss_fraction_changed+=row[8]!=old[6]
            miss_volume_retained+=list(row[9:12])==old[7:10]
    if not hits or not miss_position_retained or not miss_normal_changed or not miss_fraction_changed:
        raise AssertionError('Sweep success/failure side effects were unexercised')
    report=dict(passed=True,cases=len(cases),groups=dict(Counter(c['label'] for c in cases)),hits=hits,misses=len(cases)-hits,
        misses_retaining_position=miss_position_retained,misses_retaining_volume=miss_volume_retained,
        misses_rewriting_normal=miss_normal_changed,misses_rewriting_fraction=miss_fraction_changed,
        output_words=len(expected)//4,comparison='all hit, position, normal, fraction, volume and untouched payload words; exact bits',
        inputs_sha256=hashlib.sha256(inputs).hexdigest(),outputs_sha256=hashlib.sha256(expected).hexdigest())
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
