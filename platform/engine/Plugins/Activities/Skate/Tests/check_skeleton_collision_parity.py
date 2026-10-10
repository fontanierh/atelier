#!/usr/bin/env python3
"""Exact skeleton collision policy, completed-contact feedback and physical pose-error filters.

All original numerical modules are compiled unchanged. Explicit fixtures supply
completed solver reports and real body ownership; this check does not approximate
the still separate dynamic primitive-pair collision provider.
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
OPERATIONS=('angle','filter','feedback','policy')
FLAG_NAMES=('material_6','noncompliant','compliant','recovering','group_8','nonboard','ragdoll','conflicting','impaled','has_impulse','foot_board','material_10','material_11','material_12','any')
def bits(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def value(w):return struct.unpack('<f',struct.pack('<I',w))[0]
def f(v):return list(map(bits,v))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def corpus():
    rng=random.Random(0x82bd4a30);records=[];cases=[];rejections=[]
    def add(op,payload,label,**meta):
        cases.append(dict(index=len(cases),operation=OPERATIONS[op],label=label,**meta));records.append(struct.pack('<'+'I'*(len(payload)+1),op,*payload))
    def numbers(n,scale=1.):return [rng.uniform(-scale,scale) for _ in range(n)]
    def matrix(phase=0.,position=(0.,0.,0.),carry=False):
        c,s=math.cos(phase),math.sin(phase);cols=[[c,0,-s],[0,1,0],[s,0,c]];out=[]
        for col in cols:out.extend(col+[rng.choice((0.,-0.,1.,.25)) if carry else 0.])
        return f(out+list(position)+[rng.choice((0.,-0.,1.,.25)) if carry else 0.])
    def matrices(n):return [w for i in range(n) for w in matrix(i*.01,position=(i*.01,.5,0.),carry=True)]
    def settings(seed):
        return [seed%2]+f([.5,.3,.4])+[int((seed+n)%3!=0) for n in range(24)]+f([float(n%3) for n in range(24)]+[(.0,.1,.5)[seed%3]])
    def feedback_settings(seed):return settings(seed)+f([15.,.05,.7,1.2,.6,0.,0.,0.,0.,0.,0.,0.,0.,.1,.12])
    def specific(part,seed):return [part]+f([0.,0.,0.,seed*.01,part*.01,.5,0.,0.,.01])+[seed%2,seed%3==0]
    def seed_feedback(seed,plane_count=0):
        raw=f(numbers(24,1.))+f(numbers(24,2.))+[seed%2]*24+[int((seed+n)%3==0) for n in range(24)]
        for n in range(24):raw+=f(numbers(22,1.))+[rng.getrandbits(32),rng.getrandbits(32)]+[int((seed+n+i)%2==0) for i in range(4)]
        for n in range(8):raw+=f(numbers(3,1.))+[rng.randrange(128)]+f(numbers(4))+[(1,3,7,11,17,21,15,19)[n]]
        raw.append(plane_count)
        for n in range(plane_count):
            angle=(n-plane_count*.5)*.07;raw+=f([math.cos(angle),0.,math.sin(angle),rng.choice((0.,.25))])+[n%24]
        raw+=specific(23,seed)+specific(1,seed+1)+f(numbers(16))+f([.04,.3,.2,.1,.2,.3,.5])+[0xffffffd6]+f([.6,.7,.8])+[int((seed+n)%2==0) for n in range(15)]
        assert len(raw)==907+plane_count*5
        return [1]+raw
    def errors(seed):
        e=f(numbers(116,.2))
        if seed%3==0:
            e[23*4:23*4+4]=f([.1,0.,0.,1.]);e[17*4:17*4+4]=f([-.1,0.,0.,-1.])
        return e
    def physical(seed):
        raw=matrices(26)+f(numbers(104))+f([v for part in range(26) for v in (rng.uniform(-2.,2.),.2,-.1,rng.choice((0.,.25)))])+f(numbers(104))
        raw+=f(numbers(8)+[1/60]);assert len(raw)==737;return [1]+raw
    def report(part,normal=(1.,0.,0.,0.),point=None,group=8,material=6,side=True,seed=0):
        if point is None:point=(part*.01,.5,0.,0.)
        a=[4,bits(.5)]+f([1.,0.,0.,rng.choice((0.,.25))])
        b=[1,bits(0.)]+f([3.,2.,1.,rng.choice((0.,.25))]) if seed%3==0 else [6,bits((.1,.5,2.)[seed%3])]+f([3.,2.,1.,rng.choice((0.,.25))])
        if not side:a,b=b,a
        return [part]+f(normal)+f(point)+[((material&31)<<7)|(seed&127),group,int(group==5),(0xffffffff-seed)&0xffffffff]+a+b+[int(side)]+f([.1,.2,.3,rng.choice((0.,.25))])
    def update(seed,reports=(),ragdoll=False,offboard=False,entering=False,disable=True,category=False,partial=False,conflict=False):
        flags=[ragdoll,disable,seed%2,offboard,entering,category,partial]
        frames=matrices(26)
        if conflict:frames[3*16+12:3*16+16]=f([0.,.5,0.,0.]);frames[7*16+12:7*16+16]=f([-.01,.5,0.,0.])
        return f([(0.,1/60,.2)[seed%3],0.,0.,0.,0.,0.,1.,0.,0.,1.,0.,0.,rng.choice((0.,.25)),-.5,.3,.1,0.])+[int(v) for v in flags]+physical(seed)+f([0.]+[1/23]*23)+frames+[len(reports)]+[w for r in reports for w in r]
    def definition(seed):
        return [w for n in range(24) for w in f([.12+.001*n,.2,.4+.005*n])]+[w for n in range(24) for w in [bits(1.),bits(.5),1,0,n%3,bits(1.),1]]+f([200.,.15,.2,.7,.9,.6])+[seed%3,bits(5.)]+[0]
    def simulation(seed):return f([1/60,60.])+[30]+f([.001,0.,-9.81,0.])
    axes=((1.,0.,0.),(0.,1.,0.),(0.,0.,1.),(0.,0.,0.),(-1.,0.,0.))
    for a in axes:
        for b in axes:add(0,f([*a,*b]),'angle axes and zero early return')
    root=math.sqrt(value(0x38d1b717));word=bits(root)
    for w in range(word-3,word+4):
        for b in ((1.,0.,0.),(-1.,0.,0.),(0.,1.,0.)):add(0,f([value(w),0.,0.,*b]),'angle strict squared threshold')
    for _ in range(1024):add(0,f(numbers(6,100.)),'random angle one-refinement dot clamp')
    for seed in range(768):
        count=(0,1,2,3,20,24)[seed%6];axis=(0.,1.,0.,0.) if seed%4 else (0.,0.,0.,1.)
        error=(.1,0.,.2,1.) if seed%3 else (0.,.1,0.,.25)
        add(1,feedback_settings(seed)+seed_feedback(seed,count)+errors(seed)+f([*error,*axis]),'static contact planes, all-lane projection and raw/filtered tie order',planes=count)
    for seed in range(128):
        commands=[]
        commands.append([1])
        mixed=[report(n,normal=(0.,1.,0.,0.) if n%3==0 else (1.,0.,0.,0.),group=(4,5,8,11,6)[n%5],material=(6,10,11,12,5)[n%5],side=n%2==0,seed=seed+n) for n in range(24)]
        commands.append([2]+update(seed,mixed,disable=bool(seed%2),category=bool(seed%4==0)))
        commands.append([3]+f([.2,.1,-.3,.25,0.,1.,0.,0.]));commands.append([10]+f([0.,1.,0.,0.]))
        special=[report(3,point=(0.,.5,0.,0.),group=8,seed=seed),report(7,normal=(-1.,0.,0.,.25),point=(.01,.5,0.,0.),group=11,material=10,seed=seed+1),report(23,group=5,material=11,seed=seed+2),report(1,group=5,material=12,seed=seed+3)]
        commands.append([4]+f([.1]*24+[0.]*24)+[1]*24)
        commands.append([2]+update(seed+1,special,conflict=True));commands.append([2]+update(seed+2,special,ragdoll=True,conflict=True))
        commands.append([2]+update(seed+2,(),ragdoll=True));commands.append([0]);commands.append([6,1]);commands.append([0])
        burst=[report(n%24,group=(4,5,8,11)[n%4],material=(6,10,11,12)[n%4],seed=seed+n) for n in range(40)]
        commands.append([4]+f([.1]*24+[0.]*24)+[1]*24);commands.append([2]+update(seed+3,burst,ragdoll=bool(seed%2),partial=True))
        commands.append([2]+update(seed+4,mixed,offboard=True));commands.append([2]+update(seed+5,mixed,entering=True))
        commands.append([7]);commands.append([8]+f(numbers(12,.1)));commands.append([9]+physical(seed)+matrix(.3)+matrices(24));commands.append([10]+f([0.,1.,0.,0.]))
        commands.append([5]+specific(23,seed)+specific(1,seed+1));commands.append([2]+update(seed+6,(),partial=bool(seed%2)))
        add(2,feedback_settings(seed)+seed_feedback(seed,seed%3)+errors(seed)+[len(commands)]+[w for c in commands for w in c],
            'ordered solver observations, plane cap, specific/region history and pose-error streams',commands=[c[0] for c in commands])
    for seed in range(64):
        commands=[]
        def cmd(op,payload=()):commands.append([op,*payload])
        cmd(0,[2]);cmd(1);cmd(3,[1]);cmd(1);cmd(4);cmd(0,[0]);cmd(1);cmd(4)
        for part,count in ((1,0x80000000),(3,0xffffffff),(4,0x7fffffff),(7,1),(8,2)):
            cmd(11,[part,count,1,0,23,41,*f([.8,.6,.2])]);cmd(1)
        cmd(2,[1,0]);cmd(2,[3,1]);cmd(5,[0]);cmd(6,[3]);cmd(6,[1]);cmd(6,[5]);cmd(6,[6]);cmd(6,[2])
        for part in (0,1,3,7,23,24,25):cmd(14,[part,12 if part%2 else 2,*f(numbers(12,.1)+[.2]),17])
        for mass,inertia in ((False,False),(True,False),(False,True),(True,True)):
            cmd(7,[int(mass),int(inertia),*f([.1,.2,.7,.4,.2,.9,.6,.3])]);cmd(8,[7+(seed+int(mass)+int(inertia))%4])
        reports=[report(3,group=8,seed=seed),report(7,normal=(-1.,0.,0.,0.),group=11,material=12,seed=seed+1)]
        cmd(13,update(seed,reports,ragdoll=True));cmd(10);cmd(12,[0]);cmd(9);cmd(12,[1]);cmd(9);cmd(5,[1]);cmd(4)
        add(3,definition(seed)+matrices(24)+matrix(seed*.07)+simulation(seed)+settings(seed)+[seed%2]+feedback_settings(seed)+seed_feedback(seed,seed%2)+[len(commands)]+[w for c in commands for w in c],
            'whole-body collision modes, signed counters, cached property swaps, culling and reset',commands=[c[0] for c in commands],cull_all=bool(seed%2))
    for part in (24,25,0xffffffff):
        payload=feedback_settings(0)+[0]+errors(0)+[1,2]+update(0,[report(part)])
        rejections.append(dict(part=part,input=struct.pack('<'+'I'*(len(payload)+2),1,2,*payload)))
    return struct.pack('<I',len(records))+b''.join(records),cases,rejections

def build_probes(output):
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip());relative=(PLUGIN/'ThirdParty/skate-runtime/crates/skate-core/src').relative_to(root).as_posix()
    revision=subprocess.check_output(['git','rev-parse',REFERENCE_REVISION],cwd=root,text=True).strip();archive=subprocess.check_output(['git','archive',f'{revision}:{relative}'],cwd=root);source=output/'reference-source'
    if source.exists():shutil.rmtree(source)
    source.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:stream.extractall(source,filter='data')
    originals={p.relative_to(source).as_posix():digest(p) for p in sorted(source.rglob('*.rs'))}
    shared=PLUGIN/'Tests/Reference/skeleton_body_probe.rs';probe=PLUGIN/'Tests/Reference/skeleton_collision_probe.rs';prefix=shared.read_text().split('fn main(){',1)[0]
    main=source/'skeleton-collision-oracle.rs';main.write_text((source/'lib.rs').read_text()+prefix+probe.read_text());reference=output/'skeleton-collision-reference'
    subprocess.run(['rustc','+1.97.1','--edition=2024','-O','-A','dead_code',str(main),'-o',str(reference)],check=True)
    for name,expected in originals.items():
        if digest(source/name)!=expected:raise AssertionError(f'Frozen reference module changed: {name}')
    snapshot=output/'core-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir();core=PLUGIN/'Source/AtelierSkate/Private/Simulation'
    units=('SimulationMath','RigidBody','BodyMass','AggregateMass','DeckGeometry','DriveFrames','ConstraintFrames','ConstraintSolver','JointBuild','DriveBuild','JointRecords',
        'TruckDriveFrames','DrivePreparation','HookDrive','BoardAssembly','ContactBuild','ContactGeneration','BoardPose','ForceQueue','CollisionBody','BoardContactFeedback','BoardStep','BoardRuntime',
        'SkeletonPoseFrames','SkeletonAnimationRecord','SkeletonPhysicalRecord','SkeletonBodyDefinition','SkeletonBody','BoardGroundAngle','SkeletonCollisionMode','SkeletonCollisionFeedback','SkeletonPoseErrors')
    for name in [f'{unit}.{ext}' for unit in units for ext in ('h','cpp')]+['GeometryTypes.h','BoardTypes.h','ContactRetention.h','SkeletonTargets.h','SkeletonDriveFrames.h']:shutil.copy2(core/name,snapshot/name)
    cpp_shared=PLUGIN/'Tests/Simulation/skeleton_body_probe.cpp';cpp_probe=PLUGIN/'Tests/Simulation/skeleton_collision_probe.cpp';prefix=cpp_shared.read_text().split('int main()',1)[0]
    combined=snapshot/'skeleton_collision_probe.cpp';combined.write_text('#pragma clang diagnostic push\n#pragma clang diagnostic ignored "-Wunused-function"\n'+prefix+'\n#pragma clang diagnostic pop\n'+cpp_probe.read_text())
    cpp=output/'skeleton-collision-cpp';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/f'{unit}.cpp') for unit in units],str(combined),'-o',str(cpp)],check=True)
    provenance=dict(reference_revision=revision,source_archive_sha256=hashlib.sha256(archive).hexdigest(),original_source_sha256=originals,
        probe_sha256={p.name:digest(p) for p in (shared,probe,cpp_shared,cpp_probe)},reference_binary_sha256=digest(reference),cpp_binary_sha256=digest(cpp),simulation_source_sha256={p.name:digest(p) for p in sorted(snapshot.iterdir())},
        rust_compiler=subprocess.check_output(['rustc','+1.97.1','-vV'],text=True).strip(),cpp_compiler=subprocess.check_output(['clang++','--version'],text=True).strip())
    (output/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');return cpp,reference

def decode(data,cases):
    words=struct.unpack('<'+'I'*(len(data)//4),data);at=0;rows=[]
    for case in cases:
        index,op,n=words[at:at+3]
        if index!=case['index'] or OPERATIONS[op]!=case['operation']:raise AssertionError('Skeleton collision frame identity changed')
        rows.append(words[at+3:at+3+n]);case.update(first_output_word=at,output_words=n+3);at+=n+3
    if at!=len(words):raise AssertionError('Trailing skeleton collision output')
    return rows
def coverage(rows,cases):
    counts=Counter()
    def feedback(row,at,limited=False):
        n=row[at+840];end=at+907+5*n
        if limited and n>20:raise AssertionError('Contact plane capacity exceeded')
        if end>len(row):raise AssertionError('Missing feedback state')
        for flag,v in zip(FLAG_NAMES,row[end-15:end]):counts[flag]+=bool(v)
        if limited and n==20:counts['full_plane_buffers']+=1
        return end,row[at:end]
    def policy(row,at):
        start=at;at+=2443+913;at,fb=feedback(row,at);return at,row[start:at],fb
    for row,case in zip(rows,cases):
        op=case['operation'];counts[op]+=1
        if op=='angle':
            if len(row)!=1:raise AssertionError('Angle field changed')
        elif op=='filter':
            at,fb=feedback(row,30)
            if at!=len(row) or (len(fb)-907)//5!=case['planes']:raise AssertionError('Filter mutated planes')
        elif op=='feedback':
            at,before=feedback(row,0);before_errors=row[at:at+116];at+=116;n=row[at];at+=1
            if n!=len(case['commands']):raise AssertionError('Feedback command count changed')
            for cmd in case['commands']:
                if row[at]!=cmd:raise AssertionError('Feedback command identity changed')
                at+=1
                if cmd==3:at+=4
                elif cmd==10:at+=26
                at,after=feedback(row,at,limited=cmd==2);after_errors=row[at:at+116];at+=116
                if cmd in (0,1):
                    bp=841+5*before[840];ap=841+5*after[840]
                    if after[ap:ap+24]!=before[bp:bp+24] or after[-1]!=before[-1]:raise AssertionError('Reset changed specific histories/any flag')
                    if cmd==0 and after[48:72]!=before[48:72]:raise AssertionError('Reset changed compliant settings')
                    counts['feedback_resets']+=1
                if cmd==7 and after_errors[:104]!=before_errors[:104]:raise AssertionError('Pose-error reset changed errors')
                if cmd==7 and any(after_errors[104:]):raise AssertionError('Pose-error history reset failed')
                before=after;before_errors=after_errors
            if at!=len(row):raise AssertionError('Feedback stream framing changed')
        else:
            at,before,before_feedback=policy(row,0);n=row[at];at+=1
            if n!=len(case['commands']):raise AssertionError('Policy command count changed')
            for cmd in case['commands']:
                if row[at]!=cmd:raise AssertionError('Policy command identity changed')
                at+=1
                if cmd==6:
                    ok=row[at];at+=1
                    if not ok:
                        error=bytes(row[at+1:at+1+row[at]]).decode();at+=1+row[at]
                        if error!='Skeleton collision selector requires its non-driven physical setup':raise AssertionError(error)
                        counts['selector_errors']+=1
                at,after,after_feedback=policy(row,at)
                if cmd!=14:
                    for part in range(26):
                        b=16+part*49
                        if after[b]!=before[b]:raise AssertionError('Collision group operation changed body activation bits')
                        if after[b+23:b+40]!=before[b+23:b+40]:raise AssertionError('Collision mode changed poses/rates/forces/cooldown')
                counts[f'policy_command_{cmd}']+=1;before=after;before_feedback=after_feedback
            if at!=len(row):raise AssertionError('Policy stream framing changed')
    for key in ('conflicting','impaled','material_6','material_12','foot_board','full_plane_buffers','selector_errors','feedback_resets','policy_command_7','policy_command_9'):
        if not counts[key]:raise AssertionError(f'Uncovered skeleton collision branch: {key}')
    return dict(counts)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json','provenance.json'):(output/name).unlink(missing_ok=True)
    inputs,cases,rejections=corpus();(output/'input.bin').write_bytes(inputs);cpp,reference=build_probes(output)
    expected=subprocess.check_output([str(reference)],input=inputs);actual=subprocess.check_output([str(cpp)],input=inputs);(output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual)
    rows=decode(expected,cases);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    if expected!=actual:
        first=next((i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b),min(len(expected),len(actual)));aligned=first//4*4
        case=next((c for c in cases if c['first_output_word']*4<=first<(c['first_output_word']+c['output_words'])*4),None)
        report=dict(passed=False,first_word=first//4,case=case,reference_length=len(expected),cpp_length=len(actual),reference_hex=expected[max(0,aligned-16):aligned+32].hex(),cpp_hex=actual[max(0,aligned-16):aligned+32].hex())
        (output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
    counts=coverage(rows,cases);rejected=[]
    for item in rejections:
        original=subprocess.run([str(reference)],input=item['input'],capture_output=True);candidate=subprocess.run([str(cpp)],input=item['input'],capture_output=True)
        marker=b'SkeletonCollision report part exceeds native24-part array'
        if original.returncode==0 or marker not in original.stderr or candidate.returncode==0 or marker not in candidate.stderr:raise AssertionError('Report part rejection contract changed')
        filename=f'rejected-report-{item["part"]}.bin';(output/filename).write_bytes(item['input']);rejected.append(dict(part=item['part'],input_file=filename,reference_exit=original.returncode,cpp_exit=candidate.returncode))
    (output/'report-rejections.json').write_text(json.dumps(rejected,indent=2)+'\n')
    report=dict(passed=True,cases=len(cases),coverage=counts,report_rejections=len(rejected),exact_words=len(expected)//4,input_sha256=hashlib.sha256(inputs).hexdigest(),output_sha256=hashlib.sha256(expected).hexdigest(),
        comparison='All collision-mode/body/material/culling state and completed-contact feedback/error-filter words exact; invalid report parts explicitly rejected; no tolerance; numerical source unchanged; geometric pair provider separate')
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
