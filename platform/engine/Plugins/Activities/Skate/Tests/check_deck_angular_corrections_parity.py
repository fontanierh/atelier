#!/usr/bin/env python3
"""Exact persistent deck accumulator paths. Run through the render lock/guard.

Frozen original full core modules are hash-checked and remain unchanged.
"""
import argparse
from collections import Counter
import hashlib
import io
import json
import math
from pathlib import Path
import random
import shutil
import struct
import subprocess
import tarfile
PLUGIN=Path(__file__).resolve().parents[1]
REFERENCE_REVISION='46513a6'
def bits(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def value(w):return struct.unpack('<f',struct.pack('<I',w))[0]
def f(v):return list(map(bits,v))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def corpus():
    rng=random.Random(0x82c07000);records=[];cases=[]
    def numbers(n,scale=1.):return [rng.uniform(-scale,scale) for _ in range(n)]
    def matrix(seed):
        c,s=math.cos(seed*.013),math.sin(seed*.013);return f([c,0.,-s,0.,1.,0.,s,0.,c])
    def tensor():
        # Strictly positive symmetric tensors exercise the ordered cofactor pair.
        a,b,c=rng.uniform(.1,8.),rng.uniform(.1,8.),rng.uniform(.1,8.);x,y,z=numbers(3,.02)
        return f([a,x,y,x,b,z,y,z,c])
    def body(seed,t=None):
        raw=f(numbers(4))+matrix(seed)+(tensor() if t is None else t)+f(numbers(15,10.))+f([rng.uniform(0.,100.)])+[rng.getrandbits(32)];assert len(raw)==39;return raw
    def add(label,initial,commands,**meta):
        raw=initial+[len(commands)]+[w for c in commands for w in c];cases.append(dict(index=len(cases),label=label,commands=[c[0] for c in commands],**meta));records.append(struct.pack('<'+'I'*len(raw),*raw))
    for seed in range(1536):
        commands=[]
        for repeat in range(6):
            commands += [[4]+f(numbers(3,30.)),[seed%3]+f(numbers(3,.5)),[2]+f(numbers(3,.1)),[3],[1]+f(numbers(3,.3)),[0]+f(numbers(3,.2))]
        commands += [[5]+f(numbers(3,4.))+[123],[6]+tensor(),[7]+matrix(seed+13),[3],[0]+f([0.,0.,0.]),[1]+f([0.,-0.,0.])]
        add('connected torque accumulation, tensor retention, angular braking and ground correction',body(seed),commands)
    minimum=bits(value(0x358637bd))
    lengths=[0.,-0.,1.e-20]+[value(w) for w in range(minimum-4,minimum+5)]+[.01,.02,.1]
    for axis in range(3):
        for length in lengths:
            for velocity in (-6.,0.,1.2,6.):
                request=[0.,0.,0.];request[axis]=length;omega=[0.,0.,0.];omega[axis]=velocity
                add('normal minimum, signed zero, opposite direction and same-axis overshoot',body(axis),[[4]+f(omega),[0]+f(request),[5]+f([0.,-0.,0.])+[17],[1]+f(request),[2]+f(request),[3]])
    identity=f([1.,0.,0.,0.,1.,0.,0.,0.,1.]);step=value(0x3c888889)
    for axis in range(3):
        for velocity in (-3.,3.):
            angular=value(bits(velocity*step));w=bits(angular)
            for near in (w-1,w,w+1):
                request=[0.,0.,0.];request[axis]=value(near);omega=[0.,0.,0.];omega[axis]=velocity
                add('strict remainder and existing-dot clamp boundaries',body(axis,identity),[[4]+f(omega),[1]+f(request),[0]+f(request)])
    for scale in (.0001,.001,.1,1.,10.,1000.):
        for seed in range(32):
            t=[bits(value(w)*scale) for w in tensor()];add('finite very light/heavy inertia pair retains rounded inverse',body(seed,t),[[2]+f(numbers(3,.1)),[3],[0]+f(numbers(3,.1)),[1]+f(numbers(3,.1))])
    return struct.pack('<I',len(records))+b''.join(records),cases
def build_probes(output):
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip());relative=(PLUGIN/'ThirdParty/skate-runtime/crates/skate-core/src').relative_to(root).as_posix()
    revision=subprocess.check_output(['git','rev-parse',REFERENCE_REVISION],cwd=root,text=True).strip();archive=subprocess.check_output(['git','archive',f'{revision}:{relative}'],cwd=root);source=output/'reference-source'
    if source.exists():shutil.rmtree(source)
    source.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:stream.extractall(source,filter='data')
    originals={p.relative_to(source).as_posix():digest(p) for p in sorted(source.rglob('*.rs'))}
    probe=PLUGIN/'Tests/Reference/deck_angular_corrections_probe.rs';main=source/'deck-angular-corrections-oracle.rs';main.write_text((source/'lib.rs').read_text()+probe.read_text());reference=output/'deck-angular-corrections-reference'
    subprocess.run(['rustc','+1.97.1','--edition=2024','-O','-A','dead_code',str(main),'-o',str(reference)],check=True)
    for name,expected in originals.items():
        if digest(source/name)!=expected:raise AssertionError(f'Frozen reference producer changed: {name}')
    snapshot=output/'simulation-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir();simulation=PLUGIN/'Source/AtelierSkate/Private/Simulation';units=('SimulationMath','RigidBody','DeckAngularCorrections')
    for name in [f'{unit}.{ext}' for unit in units for ext in ('h','cpp')]:shutil.copy2(simulation/name,snapshot/name)
    cpp_probe=PLUGIN/'Tests/Simulation/deck_angular_corrections_probe.cpp';shutil.copy2(cpp_probe,snapshot/cpp_probe.name);cpp=output/'deck-angular-corrections-cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/f'{unit}.cpp') for unit in units],str(snapshot/cpp_probe.name),'-o',str(cpp)],check=True)
    provenance=dict(reference_revision=revision,source_archive_sha256=hashlib.sha256(archive).hexdigest(),original_source_sha256=originals,
        probe_sha256={p.name:digest(p) for p in (probe,cpp_probe)},reference_binary_sha256=digest(reference),cpp_binary_sha256=digest(cpp),simulation_source_sha256={p.name:digest(p) for p in sorted(snapshot.iterdir())},
        rust_compiler=subprocess.check_output(['rustc','+1.97.1','-vV'],text=True).strip(),cpp_compiler=subprocess.check_output(['clang++','--version'],text=True).strip())
    (output/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');return cpp,reference

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json'):(output/name).unlink(missing_ok=True)
    inputs,cases=corpus();(output/'input.bin').write_bytes(inputs);cpp,reference=build_probes(output)
    expected=subprocess.check_output([str(reference)],input=inputs);actual=subprocess.check_output([str(cpp)],input=inputs)
    (output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual);words=struct.unpack('<'+'I'*(len(expected)//4),expected);at=0;coverage=Counter()
    for case in cases:
        index,n,size=words[at:at+3];assert index==case['index'] and n==len(case['commands']) and size==39+40*n
        case.update(first_output_word=at,output_words=size+3);previous=words[at+3:at+42];cursor=at+42
        for op in case['commands']:
            assert words[cursor]==op;current=words[cursor+1:cursor+40];cursor+=40;coverage[str(op)]+=1
            if op<4:
                if current[:34]!=previous[:34] or current[37]!=previous[37] or current[38]!=0:raise AssertionError('Deck correction mutated independent body lanes or retained cooldown')
            previous=current
        at+=size+3
    assert at==len(words);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    if expected!=actual:
        first=next((i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b),min(len(expected),len(actual)));aligned=first//4*4;case=next((c for c in cases if c['first_output_word']*4<=first<(c['first_output_word']+c['output_words'])*4),None)
        report=dict(passed=False,first_word=first//4,case=case,reference_length=len(expected),cpp_length=len(actual),reference_hex=expected[max(0,aligned-16):aligned+32].hex(),cpp_hex=actual[max(0,aligned-16):aligned+32].hex());(output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
    result=dict(passed=True,cases=len(cases),exact_words=len(words),groups=dict(Counter(c['label'] for c in cases)),coverage=dict(coverage),input_sha256=hashlib.sha256(inputs).hexdigest(),output_sha256=hashlib.sha256(expected).hexdigest(),comparison='All retained body lanes, ordered cofactor/FMA/tensor/fixed-step paths and cooldown mutations exact; no tolerance; original numerical modules unchanged',limitations='Finite positive, nondegenerate tensor corpus; caller ground/slide scheduling is checked separately.')
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
