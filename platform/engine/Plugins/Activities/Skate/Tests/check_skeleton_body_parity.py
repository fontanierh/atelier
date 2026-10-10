#!/usr/bin/env python3
"""Exact skeleton definition, live body ownership, affine maps and COM/history producers.

This is the frozen original public implementation, without numerical adapters.
Run through the shared render lock and memory guard. Joints/drives/collision policy
are separate producers; the integration commands here operate on the actual bodies.
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
OPERATIONS=('hat','weights','bone_masses','frames','mapping','animation_record','physical_record','definition','body')
IDENTITY=[1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,0.]
def bits(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def f(values):return list(map(bits,values))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def corpus():
    rng=random.Random(0x82be4900);records=[];cases=[]
    def add(op,payload,label,**meta):
        cases.append(dict(index=len(cases),operation=OPERATIONS[op],label=label,**meta))
        records.append(struct.pack('<'+'I'*(len(payload)+1),op,*payload))
    def numbers(n,scale=1.):return [rng.uniform(-scale,scale) for _ in range(n)]
    def matrix(phase=0.,position=None,carry=True,scale=(1.,1.,1.),shear=0.):
        c,s=math.cos(phase),math.sin(phase);columns=[[c,0.,-s],[0.,1.,0.],[s,0.,c]]
        out=[]
        for axis in range(3):
            out.extend([scale[axis]*(columns[axis][lane]+(shear*columns[0][lane] if axis==1 else 0.)) for lane in range(3)])
            out.append(rng.choice((0.,-0.,.25,-1.,1.)) if carry else 0.)
        return f(out+(numbers(3,10.) if position is None else list(position))+[rng.choice((0.,-0.,.25,-1.,1.)) if carry else 0.])
    def matrices(n,carry=True):return [w for _ in range(n) for w in matrix(rng.uniform(-math.pi,math.pi),carry=carry)]
    def sizes():return [[rng.uniform(.04,.5),rng.uniform(.04,.5),rng.uniform(.04,1.)] for _ in range(24)]
    def definition(seed,invalid=None):
        dims=sizes();bones=[]
        for n in range(24):
            shape=(n+seed)%3
            if n==0:shape=(3,0xffffffff,2)[seed%3] # root ignores volume type
            if n==1 and seed%2:shape=4 # head with hat has its own sphere branch
            bones.append([bits(rng.uniform(.2,2.)),bits(rng.uniform(.2,2.)),(n+seed)%2,(n+seed)%3==0,shape,bits(rng.uniform(.3,1.4)),n%4])
        if invalid is not None:bones[invalid][4]=3+seed%5
        settings=f([rng.uniform(50.,600.),.15,.2,rng.uniform(.2,1.2),rng.uniform(.2,1.2),rng.uniform(.1,2.)])+[seed%4,bits((.1,1.,5.,30.)[seed%4])]
        hat=[]
        if seed%2:
            t=matrix(seed*.07,position=(.02,.04,-.03),carry=False);basis=[t[i*4+j] for i in range(3) for j in range(3)]
            hat=[bits(rng.uniform(.05,.2)),bits(rng.uniform(.003,.05))]+basis+f([.02,.04,-.03])
        payload=[w for d in dims for w in f(d)]+[int(w) for b in bones for w in b]+settings+[int(bool(hat))]+hat
        return payload
    def simulation(phase):return f([(1/60,1/120,1/30)[phase%3],(60.,120.,30.)[phase%3]])+[30]+f([.001,0.,-9.81,0.])
    for _ in range(384):
        add(0,f([rng.uniform(.01,1.),rng.uniform(.001,.5),*numbers(3,30.),*numbers(3,1.)]),'authored hat Euler power tree')
    for axis in range(3):
        for angle in (0.,-0.,1.e-7,math.pi/4,math.pi/2,math.pi,2*math.pi,1000.):
            angles=[0.]*3;angles[axis]=angle
            add(0,f([.1,.02,*angles,.0,-.0,.1]),'hat trig boundaries')
    for _ in range(512):
        weights=[rng.uniform(.001,10.) if n else rng.choice((0.,-0.)) for n in range(24)]
        if _%3==0:weights[rng.randrange(1,24)]=0.
        add(1,f(weights),'ordered scalar total, single divide and multiply')
    for shape in range(6):
        for hat in (False,True):
            shapes=[shape]*24;shapes[2]=0;dims=sizes()
            add(2,[w for d in dims for w in f(d)]+shapes+[int(hat)],'root zero and head hat weight override',shape=shape,hat=hat)
    for _ in range(384):
        dims=sizes();shapes=[rng.randrange(6) for n in range(24)];shapes[2]=1;hat=bool(_%2)
        add(2,[w for d in dims for w in f(d)]+shapes+[int(hat)],'mixed bone volumes retain box weights',hat=hat)
    for _ in range(768):
        q=numbers(4,2.) if _%3 else [0.,0.,math.sin(_*.01),math.cos(_*.01)]
        a=matrix(_*.03,scale=(.3,2.,1.),shear=.2);b=matrix(_*.07)
        add(3,f(q+numbers(4,10.))+a+b+f(numbers(4,10.)),'forward physical frame, affine all lanes and rigid inverse')
    for _ in range(160):
        count=(0,1,4,24,64)[_%5];indices=[rng.randrange(count) if count else 0 for n in range(24)]
        if _%4==0:indices[rng.randrange(24)]=count
        add(4,[count]+matrices(count)+indices+matrices(24)+matrices(24),'mapping duplicate gathers and prevalidation',valid=count>0 and _%4!=0)
    for _ in range(96):
        initial=[_%2]
        if initial[0]:initial+=matrices(24)+f(numbers(16,10.)+[rng.choice((0.,1.,-.5))])
        weights=f([0.]+[rng.uniform(.001,1.) for n in range(23)])
        commands=[[1]+matrices(24)+matrix(.2),[1]+matrices(24)+matrix(-.4),[0],[1]+matrices(24)+matrix(.1),[0],[0]]
        add(5,initial+weights+[len(commands)]+[w for c in commands for w in c],'animation history reset retains pose/reset scalar',commands=[c[0] for c in commands],seeded=bool(initial[0]))
    for _ in range(96):
        initial=[_%2]
        if initial[0]:initial+=matrices(26)+f(numbers(312,10.)+numbers(8,10.)+[.02])
        fractional=f([0.]+[rng.uniform(.001,.1) for n in range(23)])
        commands=[[1]+matrices(26)+matrix(.3),[1]+matrices(26)+matrix(-.2),[0]+matrices(26),[1]+matrices(26)+matrix(.7),[0]+matrices(26)]
        add(6,initial+fractional+[len(commands)]+[w for c in commands for w in c],'physical root uses board frame; reset preserves COM/delta/timestep',commands=[c[0] for c in commands],seeded=bool(initial[0]))
    for _ in range(512):add(7,definition(_),'density and cached masses, 3 shapes, head compound order, inertia modes',valid=True,hat=bool(_%2),inertia_mode=_%4)
    for invalid in range(2,24):
        for _ in range(4):add(7,definition(_,invalid),'explicit unresolved non-root volume type',valid=False,invalid_part=invalid)
    for _ in range(128):
        authored=[]
        for part in range(24):authored+=matrix(.01*part,position=(.03*part,.06*part,.02*part),scale=(.5,2.,1.),shear=.1,carry=bool(_%2))
        commands=[]
        for part in (0,1,2,23,24,25):
            commands.append([3,part,(4,2,12)[part%3]]+f(numbers(12,.05)+[.1])+[19])
            commands.append([0,part]+matrix(_*.1+part*.03,scale=(.2,2.,1.),shear=.2))
            commands.append([1,part]+f(numbers(4,.003)))
        commands.append([2]+matrix(.5,position=(1.,2.,3.)))
        reactions=[w for n in range(26) for w in f(numbers(12,.0001))]
        commands.append([4]+simulation(_)+reactions)
        commands.append([2]+matrix(-.7,position=(-1.,.4,2.)))
        commands.append([5]);commands.append([2]+matrix(.1))
        add(8,definition(_)+authored+matrix(_*.17,carry=bool(_%2))+simulation(_)+[len(commands)]+[w for c in commands for w in c],
            '26 actual bodies, root/extras setup, live setters, displacements and integrated publication',commands=[c[0] for c in commands],hat=bool(_%2))
    return struct.pack('<I',len(records))+b''.join(records),cases

def build_probes(output):
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip())
    relative=(PLUGIN/'ThirdParty/skate-runtime/crates/skate-core/src').relative_to(root).as_posix()
    revision=subprocess.check_output(['git','rev-parse',REFERENCE_REVISION],cwd=root,text=True).strip()
    archive=subprocess.check_output(['git','archive',f'{revision}:{relative}'],cwd=root);source=output/'reference-source'
    if source.exists():shutil.rmtree(source)
    source.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:stream.extractall(source,filter='data')
    originals={p.relative_to(source).as_posix():digest(p) for p in sorted(source.rglob('*.rs'))}
    probe=PLUGIN/'Tests/Reference/skeleton_body_probe.rs';main=source/'skeleton-body-oracle.rs'
    main.write_text((source/'lib.rs').read_text()+probe.read_text().replace('//!','//'));reference=output/'skeleton-body-reference'
    subprocess.run(['rustc','+1.97.1','--edition=2024','-O','-A','dead_code',str(main),'-o',str(reference)],check=True)
    for name,expected in originals.items():
        if digest(source/name)!=expected:raise AssertionError(f'Frozen reference module changed: {name}')
    snapshot=output/'core-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir();core=PLUGIN/'Source/AtelierSkate/Private/Simulation'
    units=('SimulationMath','RigidBody','BodyMass','AggregateMass','DeckGeometry','DriveFrames','ConstraintFrames','ConstraintSolver','JointBuild','DriveBuild','JointRecords',
        'TruckDriveFrames','DrivePreparation','HookDrive','BoardAssembly','ContactBuild','ContactGeneration','BoardPose','ForceQueue','CollisionBody','BoardContactFeedback','BoardStep','BoardRuntime',
        'SkeletonPoseFrames','SkeletonAnimationRecord','SkeletonPhysicalRecord','SkeletonBodyDefinition','SkeletonBody')
    names=[f'{unit}.{ext}' for unit in units for ext in ('h','cpp')]+['GeometryTypes.h','BoardTypes.h','ContactRetention.h']
    for name in names:shutil.copy2(core/name,snapshot/name)
    shutil.copy2(PLUGIN/'Tests/Simulation/skeleton_body_probe.cpp',snapshot/'skeleton_body_probe.cpp');cpp=output/'skeleton-body-cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(snapshot),
        *[str(snapshot/f'{unit}.cpp') for unit in units],str(snapshot/'skeleton_body_probe.cpp'),'-o',str(cpp)],check=True)
    provenance=dict(reference_revision=revision,source_archive_sha256=hashlib.sha256(archive).hexdigest(),original_source_sha256=originals,
        probe_sha256=digest(probe),reference_binary_sha256=digest(reference),cpp_binary_sha256=digest(cpp),simulation_source_sha256={p.name:digest(p) for p in sorted(snapshot.iterdir())},
        rust_compiler=subprocess.check_output(['rustc','+1.97.1','-vV'],text=True).strip(),cpp_compiler=subprocess.check_output(['clang++','--version'],text=True).strip())
    (output/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');return cpp,reference

def decode(data,cases):
    if len(data)%4:raise AssertionError('Partial skeleton output word')
    words=struct.unpack('<'+'I'*(len(data)//4),data);at=0;rows=[]
    for case in cases:
        index,op,n=words[at:at+3]
        if index!=case['index'] or OPERATIONS[op]!=case['operation']:raise AssertionError('Skeleton output identity changed')
        rows.append(words[at+3:at+3+n]);case.update(first_output_word=at,output_words=n+3);at+=n+3
    if at!=len(words):raise AssertionError('Trailing skeleton frame')
    return rows

def coverage(rows,cases):
    counts=Counter()
    for row,case in zip(rows,cases):
        op=case['operation'];counts[op]+=1
        if op=='definition':
            if bool(row[0])!=case['valid']:raise AssertionError('Definition error domain changed')
            if row[0]:
                if len(row)!=1934:raise AssertionError('Definition field encoding changed')
                counts['compound_heads' if case['hat'] else 'plain_heads']+=1
                counts[f'inertia_mode_{case["inertia_mode"]}']+=1
                for extra in (24,25):
                    p=1+extra*66
                    if row[p]!=1 or row[p+7]:raise AssertionError('Extra body primitive/hat changed')
                    # Both modes receive the same final properties/cached inverse mass.
                    if row[p+22:p+43]!=row[p+43:p+64] or row[p+64]!=row[p+65]:raise AssertionError('Extra body mode properties differ')
            else:
                error=bytes(row[2:2+row[1]]).decode()
                if error!='Unresolved non-root skeleton volume type':raise AssertionError(error)
                counts['explicit_volume_errors']+=1
        elif op=='mapping':
            if bool(row[0])!=case['valid']:raise AssertionError('Mapping bounds error changed')
            counts['valid_mappings' if row[0] else 'mapping_bounds_errors']+=1
        elif op=='animation_record':
            width=404;at=49;before=row[at:at+width];at+=width;n=row[at];at+=1
            if n!=len(case['commands']):raise AssertionError('Animation record stream count changed')
            for cmd in case['commands']:
                after=row[at:at+width];at+=width
                if cmd==0:
                    if after[:384]!=before[:384] or after[400]!=before[400]:raise AssertionError('Animation reset changed pose/reset scalar')
                    if any(after[384:400]):raise AssertionError('Animation reset left history')
                    counts['animation_resets']+=1
                before=after
            if at!=len(row):raise AssertionError('Animation record framing changed')
        elif op=='physical_record':
            width=737;at=width;before=row[:width];n=row[at];at+=1
            if n!=len(case['commands']):raise AssertionError('Physical record stream count changed')
            for cmd in case['commands']:
                after=row[at:at+width];at+=width
                if cmd==0:
                    if after[624:]!=before[624:]:raise AssertionError('Physical reset changed velocity changes/COM/timestep')
                    if any(after[520:624]):raise AssertionError('Physical reset did not clear velocities')
                    if any(after[416+i*4:420+i*4]!=after[12+i*16:16+i*16] for i in range(26)):raise AssertionError('Physical reset positions changed')
                    counts['physical_resets']+=1
                else:
                    if after[-1]!=0x3c888889:raise AssertionError('Physical derivative timestep changed')
                    counts['physical_updates']+=1
                before=after
            if at!=len(row):raise AssertionError('Physical record framing changed')
        elif op=='body':
            width=2443;at=width;before=row[:width];n=row[at];at+=1
            if n!=len(case['commands']):raise AssertionError('Live skeleton stream count changed')
            for cmd in case['commands']:
                after=row[at:at+width];at+=width
                if after[:16]!=before[:16]:raise AssertionError('Live operation changed initial animation alignment')
                if cmd in (0,1,3,4):
                    # Cached observations only change at their explicit publication/reset.
                    record_start=16+26*49+26*16
                    if cmd==0:
                        # SetPartTransform writes precisely one requested record pose.
                        if after[record_start+416:]!=before[record_start+416:]:raise AssertionError('Pose setter changed physical history')
                    elif after[record_start:]!=before[record_start:]:raise AssertionError('Body mutation updated physical history early')
                counts[f'body_command_{cmd}']+=1;before=after
            if at!=len(row):raise AssertionError('Skeleton snapshot framing changed')
    for key in ('compound_heads','plain_heads','explicit_volume_errors','valid_mappings','mapping_bounds_errors','animation_resets','physical_resets','physical_updates','body_command_4'):
        if not counts[key]:raise AssertionError(f'Uncovered skeleton branch: {key}')
    return dict(counts)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json','provenance.json'):(output/name).unlink(missing_ok=True)
    inputs,cases=corpus();(output/'input.bin').write_bytes(inputs);cpp,reference=build_probes(output)
    expected=subprocess.check_output([str(reference)],input=inputs);actual=subprocess.check_output([str(cpp)],input=inputs)
    (output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual);rows=decode(expected,cases);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    if expected!=actual:
        first=next((i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b),min(len(expected),len(actual)));aligned=first//4*4
        case=next((c for c in cases if c['first_output_word']*4<=first<(c['first_output_word']+c['output_words'])*4),None)
        report=dict(passed=False,first_word=first//4,case=case,reference_length=len(expected),cpp_length=len(actual),reference_hex=expected[max(0,aligned-16):aligned+32].hex(),cpp_hex=actual[max(0,aligned-16):aligned+32].hex())
        (output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
    counts=coverage(rows,cases);report=dict(passed=True,cases=len(cases),coverage=counts,exact_words=len(expected)//4,input_sha256=hashlib.sha256(inputs).hexdigest(),output_sha256=hashlib.sha256(expected).hexdigest(),
        comparison='All definition/error, mass caches, transform lanes, COM/history and actual body state words exact; no tolerance; original numerical source unchanged; excludes skeleton constraints/collision policy')
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
