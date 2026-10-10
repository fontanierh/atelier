#!/usr/bin/env python3
"""Exact physical skeleton joint/drive construction, retained channels and real target ownership.

The record adapters are shared with the independently checked skeleton-body probe;
all original numerical modules (including solver packing) are compiled unchanged.
Run through the render lock and memory guard.
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
OPERATIONS=('joints','dynamics','frames','drives')
def bits(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def f(v):return list(map(bits,v))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def corpus():
    rng=random.Random(0x82bea670);records=[];cases=[]
    def add(op,payload,label,**meta):
        cases.append(dict(index=len(cases),operation=OPERATIONS[op],label=label,**meta));records.append(struct.pack('<'+'I'*(len(payload)+1),op,*payload))
    def numbers(n,scale=1.):return [rng.uniform(-scale,scale) for _ in range(n)]
    def matrix(phase=0.,position=None,carry=True,scale=(1.,1.,1.)):
        c,s=math.cos(phase),math.sin(phase);b=[[c,0,-s],[0,1,0],[s,0,c]];out=[]
        for i in range(3):out.extend([x*scale[i] for x in b[i]]+[rng.choice((0.,-0.,.25,1.)) if carry else 0.])
        return f(out+(numbers(3,1.) if position is None else list(position))+[rng.choice((0.,-0.,.25,1.)) if carry else 0.])
    def matrices(n):return [w for _ in range(n) for w in matrix(rng.uniform(-math.pi,math.pi))]
    def quat():
        q=numbers(4);length=math.sqrt(sum(x*x for x in q));return f([x/length for x in q])
    def parents():return [0xffffffff]+[0 if n<12 else 23 for n in range(1,23)]+[0xffffffff]
    def body(phase):
        c,s=math.cos(phase),math.sin(phase);basis=[c,0,-s,0,1,0,s,0,c]
        return [4]+f([0,math.sin(phase*.5),0,math.cos(phase*.5),*basis,2.,0.,0.,0.,3.,0.,0.,0.,4.,*numbers(15,.1),.1])+[15]+f([2.,3.,4.,rng.uniform(.01,1.),.5,30.,30.,0.,0.])
    def definition(seed):
        sizes=[w for n in range(24) for w in f([.12+.001*n,.2,.4+.005*n])]
        bones=[w for n in range(24) for w in [bits(1.),bits(.5),1,0,n%3,bits(1.),1]]
        return sizes+bones+f([200.,.15,.2,.7,.9,.6])+[seed%3,bits(5.)]+[0]
    def simulation(seed):return f([(1/60,1/120,1/30)[seed%3],(60.,120.,30.)[seed%3]])+[30]+f([.001,0.,-9.81,0.])
    def drive_settings(seed):
        return f([*numbers(8,1.),.03,.04,.05,.06,*numbers(12,2.),(.5,1.,2.,4.,25.)[seed%5]])
    def mutate(state):return [state]+f(numbers(12,.1)+[.2])+[17]
    for seed in range(256):
        initial=matrices(24);p=parents();bones=[]
        for n in range(24):bones+=quat()+quat()+matrix(seed*.01+n*.03)+f([rng.uniform(-.1,1.),rng.uniform(-.1,1.)])
        settings=[w for n in range(22) for w in [n%3==0,*f([rng.uniform(-.1,2.),rng.uniform(-.1,2.),.8,.6])]]
        global_settings=f([.1,.2,.3,-.0,.07,.09])+[seed%2,seed%3==0]
        runs=[]
        for flags in ([4]*26,[2]*26,[4 if n%2 else 1 for n in range(26)],[12 if n%3 else 2 for n in range(26)]):
            runs.append([*flags,8+seed%17,bits((1/60,1/120,1/30)[seed%3])])
        add(0,initial+p+bones+[int(w) for w in settings]+global_settings+[w for n in range(26) for w in body(n*.02)]+[len(runs)]+[w for r in runs for w in r],
            '22 original parent/child definitions and ordered active row compilation',valid=True,runs=runs,parents=p)
    for error in ('parent_outside','self_parent','too_many','too_few'):
        for seed in range(8):
            p=parents()
            if error=='parent_outside':p[1]=24+seed
            elif error=='self_parent':p[1]=1
            elif error=='too_many':p[0]=23
            else:p[1]=0xffffffff
            bones=[w for n in range(24) for w in quat()+quat()+matrix(n*.03)+f([.5,.5])]
            settings=[w for n in range(22) for w in [0,*f([1.,1.,1.,1.])]]
            add(0,matrices(24)+p+bones+settings+f([.1]*6)+[0,0],'exact joint construction rejection',valid=False,error=error)
    for seed in range(768):
        settings=drive_settings(seed);channels=[w for n in range(4) for w in [*f(numbers(3,1.)),n%3]]
        initial=channels+[seed%7]+f(numbers(2)+[rng.uniform(-2.,30.)])+[seed%2]
        commands=[]
        for mode,strength in ((0,1.),(1,-1.),(2,.4),(3,.0),(3,.6),(4,.5),(4,.50000006),(4,-.1),(5,.3),(5,.8),(5,-.2),(5,1.),(6,.7),(0,.2),(5,.4),(0xffffffff,.1)):
            commands.append([mode,len(commands)%2,bits(strength)])
        add(1,settings+initial+[len(commands)]+[w for c in commands for w in c],'all modes, half threshold and shared channel transition counter',commands=commands)
    for seed in range(512):add(2,matrices(3)+[1+seed%4],'common frame translation, nonunit orientation and repeated paired preparation',calls=1+seed%4)
    for seed in range(96):
        prefix=definition(seed)+matrices(24)+matrix(seed*.07)+simulation(seed)
        initial=matrices(24);mapped=matrices(24);p=parents();alignment=matrix(seed*.04)
        settings=drive_settings(seed)+[seed%2]+f([.7,.9]+[rng.uniform(-.1,1.1) for n in range(48)])
        commands=[]
        def update(partial,weight):commands.append([0,int(partial),bits(weight)]+matrices(24))
        def build():commands.append([7,8,34,bits((1/60,1/120,1/30)[seed%3])])
        build();build();update(False,1.);build();update(False,.0);build();update(True,.5);build()
        commands.append([1,3,0,0]);commands.append([1,7,1,0]);update(True,.99999994);build()
        commands.append([2,0]+f([.5,.8]));update(False,1.);build();update(False,.25);build()
        commands.append([3,2]+matrix(.3));commands.append([4]+matrices(2));commands.append([5]+f(numbers(3,.05)))
        for distance,teleport in ((.5,False),(1.,False),(1.00000012,False),(.1,True)):
            frames=[matrix(position=(distance,0.,0.)),matrix(),matrix(position=(0,0,0)),matrix(),matrix(),matrix(position=(.5,1.,0)),matrix(position=(.5,1.5,0))]
            commands.append([6]+[w for m in frames for w in m]+[int(teleport)])
        for part in range(26):commands.append([8,part]+mutate(2))
        build();commands.append([9,0]+mutate(4));build();commands.append([8,23]+mutate(4));build()
        commands.append([10,2]);update(False,.1);build()
        add(3,prefix+initial+mapped+p+alignment+settings+[len(commands)]+[w for c in commands for w in c],
            'real static targets, 44 channels, partial collision selection and eligible row order',valid=True,commands=[c[0] for c in commands])
    for error in ('root_parent','hips_parent','missing_pair','outside_parent'):
        p=parents()
        if error=='root_parent':p[0]=23
        elif error=='hips_parent':p[23]=0
        elif error=='missing_pair':p[4]=0xffffffff
        else:p[4]=24
        add(3,definition(0)+matrices(24)+matrix()+simulation(0)+matrices(24)+matrices(24)+p+matrix()+drive_settings(0)+[1]+f([1.]*50),
            'exact drive construction rejection',valid=False,error=error)
    return struct.pack('<I',len(records))+b''.join(records),cases

def build_probes(output):
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip());relative=(PLUGIN/'ThirdParty/skate-runtime/crates/skate-core/src').relative_to(root).as_posix()
    revision=subprocess.check_output(['git','rev-parse',REFERENCE_REVISION],cwd=root,text=True).strip();archive=subprocess.check_output(['git','archive',f'{revision}:{relative}'],cwd=root);source=output/'reference-source'
    if source.exists():shutil.rmtree(source)
    source.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:stream.extractall(source,filter='data')
    originals={p.relative_to(source).as_posix():digest(p) for p in sorted(source.rglob('*.rs'))}
    shared=PLUGIN/'Tests/Reference/skeleton_body_probe.rs';probe=PLUGIN/'Tests/Reference/skeleton_constraint_probe.rs';prefix=shared.read_text().split('fn main(){',1)[0]
    main=source/'skeleton-constraint-oracle.rs';main.write_text((source/'lib.rs').read_text()+prefix+probe.read_text());reference=output/'skeleton-constraint-reference'
    subprocess.run(['rustc','+1.97.1','--edition=2024','-O','-A','dead_code',str(main),'-o',str(reference)],check=True)
    for name,expected in originals.items():
        if digest(source/name)!=expected:raise AssertionError(f'Frozen reference module changed: {name}')
    snapshot=output/'core-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir();core=PLUGIN/'Source/AtelierSkate/Private/Simulation'
    units=('SimulationMath','RigidBody','BodyMass','AggregateMass','DeckGeometry','DriveFrames','ConstraintFrames','ConstraintSolver','JointBuild','DriveBuild','JointRecords',
        'TruckDriveFrames','DrivePreparation','HookDrive','BoardAssembly','ContactBuild','ContactGeneration','BoardPose','ForceQueue','CollisionBody','BoardContactFeedback','BoardStep','BoardRuntime',
        'SkeletonPoseFrames','SkeletonAnimationRecord','SkeletonPhysicalRecord','SkeletonBodyDefinition','SkeletonBody','SkeletonJoints','SkeletonDriveDynamics','SkeletonDriveFrames','SkeletonTargets','SkeletonDrives')
    for name in [f'{unit}.{ext}' for unit in units for ext in ('h','cpp')]+['GeometryTypes.h','BoardTypes.h','ContactRetention.h']:shutil.copy2(core/name,snapshot/name)
    cpp_shared=PLUGIN/'Tests/Simulation/skeleton_body_probe.cpp';cpp_probe=PLUGIN/'Tests/Simulation/skeleton_constraint_probe.cpp'
    prefix=cpp_shared.read_text().split('int main()',1)[0]
    # Shared adapters intentionally include encoders not used by this fragment.
    # Only these test helpers suppress unused-function diagnostics; production
    # translation units retain Wall/Wextra/Werror without suppression.
    combined=snapshot/'skeleton_constraint_probe.cpp';combined.write_text('#pragma clang diagnostic push\n#pragma clang diagnostic ignored "-Wunused-function"\n'+prefix+'\n#pragma clang diagnostic pop\n'+cpp_probe.read_text())
    cpp=output/'skeleton-constraint-cpp';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/f'{unit}.cpp') for unit in units],str(combined),'-o',str(cpp)],check=True)
    provenance=dict(reference_revision=revision,source_archive_sha256=hashlib.sha256(archive).hexdigest(),original_source_sha256=originals,
        probe_sha256={p.name:digest(p) for p in (shared,probe,cpp_shared,cpp_probe)},reference_binary_sha256=digest(reference),cpp_binary_sha256=digest(cpp),simulation_source_sha256={p.name:digest(p) for p in sorted(snapshot.iterdir())},
        rust_compiler=subprocess.check_output(['rustc','+1.97.1','-vV'],text=True).strip(),cpp_compiler=subprocess.check_output(['clang++','--version'],text=True).strip())
    (output/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');return cpp,reference

def decode(data,cases):
    words=struct.unpack('<'+'I'*(len(data)//4),data);at=0;rows=[]
    for case in cases:
        index,op,n=words[at:at+3]
        if index!=case['index'] or OPERATIONS[op]!=case['operation']:raise AssertionError('Skeleton constraint frame identity changed')
        rows.append(words[at+3:at+3+n]);case.update(first_output_word=at,output_words=n+3);at+=n+3
    if at!=len(words):raise AssertionError('Trailing skeleton constraint output')
    return rows
def coverage(rows,cases):
    counts=Counter()
    def snapshot(row,at):
        start=at;at+=2443+348
        for n in range(24):
            present=row[at];at+=1
            if present:at+=53
        at+=76
        if at>len(row):raise AssertionError('Missing skeleton drive snapshot')
        counts['actual_body_snapshots']+=1
        return at,row[start:at]
    for row,case in zip(rows,cases):
        op=case['operation'];counts[op]+=1
        if op in ('joints','drives') and not case['valid']:
            if row[0]:raise AssertionError('Invalid definition accepted')
            error=bytes(row[2:2+row[1]]).decode();counts['definition_errors']+=1
            expected={'parent_outside':'Invalid physical skeleton joint parent','self_parent':'Invalid physical skeleton joint parent','too_many':'Too many physical skeleton joints','too_few':'Physical skeleton requires22 joints'}
            if error!=(expected[case['error']] if op=='joints' else 'Skeleton drives require22 bone pairs and two roots'):raise AssertionError(error)
        elif op=='joints':
            if row[0]!=1:raise AssertionError('Valid joints rejected')
            at=1+22*38;n=row[at];at+=1
            if n!=len(case['runs']):raise AssertionError('Joint run count changed')
            pairs=[(row[1+i*38],row[2+i*38]) for i in range(22)]
            for run in case['runs']:
                eligible=[(p,c) for p,c in pairs if (run[p]|run[c])&4];nr=row[at];at+=1
                if nr!=len(eligible):raise AssertionError('Joint activation gate changed')
                for p,c in eligible:
                    if row[at+96:at+98]!=(run[26]+c,run[26]+p):raise AssertionError('Joint reaction/registration order changed')
                    at+=98;counts['compiled_joint_rows']+=1
            if at!=len(row):raise AssertionError('Joint framing changed')
        elif op=='dynamics':
            width=21;at=width;n=row[at];at+=1
            if n!=len(case['commands']):raise AssertionError('Dynamics command count changed')
            for cmd in case['commands']:counts[f'mode_{cmd[0]}']+=1;at+=width
            if at!=len(row):raise AssertionError('Dynamics framing changed')
        elif op=='frames':
            if row[14]!=case['calls'] or len(row)!=15+14*case['calls']:raise AssertionError('Paired preparation framing changed')
        else:
            if row[0]!=1:raise AssertionError('Valid drive owner rejected')
            at,before=snapshot(row,1);n=row[at];at+=1
            if n!=len(case['commands']):raise AssertionError('Drive stream count changed')
            for cmd in case['commands']:
                if row[at]!=cmd:raise AssertionError('Drive command identity changed')
                at+=1;counts[f'command_{cmd}']+=1
                if cmd==6:
                    counts['continuous_targets' if row[at+28] else 'discontinuous_targets']+=1;at+=29
                elif cmd==7:
                    nr=row[at];at+=1
                    if nr>48:raise AssertionError('Too many skeleton drive rows')
                    last=(-1,-1,-1)
                    for _ in range(nr):
                        kind,index,channel,spy=row[at+98:at+102]
                        if (kind,index,channel)<=last:raise AssertionError('Skeleton drive registration order changed')
                        if spy!=(index>=2 if kind==0 else True):raise AssertionError('Spy subscription changed')
                        last=(kind,index,channel);at+=102;counts['compiled_drive_rows']+=1
                at,after=snapshot(row,at)
                if cmd==6:
                    for part in (24,25):
                        start=16+part*49
                        if after[start+32:start+38]!=before[start+32:start+38]:raise AssertionError('Extra target replaced force/torque')
                before=after
            if at!=len(row):raise AssertionError('Drive stream framing changed')
    for key in ('compiled_joint_rows','compiled_drive_rows','definition_errors','continuous_targets','discontinuous_targets','mode_5','command_10'):
        if not counts[key]:raise AssertionError(f'Uncovered constraint branch: {key}')
    return dict(counts)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json','provenance.json'):(output/name).unlink(missing_ok=True)
    inputs,cases=corpus();(output/'input.bin').write_bytes(inputs);cpp,reference=build_probes(output)
    expected=subprocess.check_output([str(reference)],input=inputs);actual=subprocess.check_output([str(cpp)],input=inputs);(output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual)
    rows=decode(expected,cases);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    if expected!=actual:
        first=next((i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b),min(len(expected),len(actual)));aligned=first//4*4
        case=next((c for c in cases if c['first_output_word']*4<=first<(c['first_output_word']+c['output_words'])*4),None)
        report=dict(passed=False,first_word=first//4,case=case,reference_length=len(expected),cpp_length=len(actual),reference_hex=expected[max(0,aligned-16):aligned+32].hex(),cpp_hex=actual[max(0,aligned-16):aligned+32].hex())
        (output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
    counts=coverage(rows,cases);report=dict(passed=True,cases=len(cases),coverage=counts,exact_words=len(expected)//4,input_sha256=hashlib.sha256(inputs).hexdigest(),output_sha256=hashlib.sha256(expected).hexdigest(),
        comparison='All joint records/error domains, paired drive frames/dynamics, 26 live bodies/four real static targets, registration identities/spy and compiled rows exact; no tolerance; original numerical modules unchanged')
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
