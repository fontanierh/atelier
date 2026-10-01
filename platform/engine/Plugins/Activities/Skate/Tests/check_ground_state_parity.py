#!/usr/bin/env python3
"""Frozen ground state, correction call ordering and shared inertia writes.

Every state field and callback argument is observed after each command. Query
results are supplied at the original required geometry-service boundary; this
does not claim a full world/physical owner or complete GroundBoard scheduler.
Run builds/probes only through the shared render lock and memory guard.
"""
import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import random
import re
import shutil
import struct
import subprocess
import tarfile
PLUGIN=Path(__file__).resolve().parents[1]
REFERENCE_REVISION='46513a6'
FIELDS=[["v","collision_force_2528"],["v","collision_point_2544"],["u","word_2560"],["u","word_2564"],["v","vector_2592"],["v","vector_2608"],["v","anti_flip_torque_2624"],["f","steering_push_scalar_2640"],["f","steering_damped_turn_2644"],["f","elapsed_2648"],["f","collision_countdown_2652"],["f","captured_position_x_2656"],["f","captured_position_z_2660"],["f","scalar_2664"],["f","scalar_2668"],["f","straighten_scale_2672"],["v","vector_2688"],["f","scalar_2704"],["b","flag_2708"],["b","flag_2720"],["b","flag_2721"],["b","flag_2722"],["b","anti_flip_nudge_applied_2723"],["b","human_player_2724"],["b","controls_latched_2725"],["b","captured_position_valid_2726"],["b","pinning_2727"],["b","was_pinning_2728"],["b","flag_2729"],["b","push_suppressed_2730"],["b","flag_2731"],["b","manual_correction_2732"],["b","manual_opposition_2733"],["i","hang_detection_frames_2740"],["i","hang_force_frames_2744"],["i","hung_wipeout_frames_2748"],["i","anti_flip_nudge_frames_2752"]]
STATE_WORDS=sum(4 if t=='v' else 1 for t,_ in FIELDS)
def bits(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def f(values):return list(map(bits,values))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def corpus():
    rng=random.Random(0x82d38800);records=[];cases=[]
    def seed(**changes):
        values=[]
        for t,name in FIELDS:
            if name in changes:
                v=changes[name]
                values.extend(f(v) if t=='v' else [bits(v) if t=='f' else int(v)&0xffffffff])
            elif t=='v':values.extend(f([rng.uniform(-3,3) for _ in range(4)]))
            elif t=='f':values.append(bits(rng.uniform(-3,3)))
            elif t=='u':values.append(rng.getrandbits(32))
            elif t=='i':values.append(0)
            else:values.append(rng.randrange(2))
        assert len(values)==STATE_WORDS
        return values
    geometry=f([.1,.2,.3,.4,3.,.5,-2.,-.3,1.,2.,3.,.25,0.,1.,0.,.2,0.,0.,1.,-.2])
    def add(label,initial,commands,fill=0):
        words=initial+[fill]+geometry+[len(commands)]+[w for c in commands for w in c]
        cases.append(dict(index=len(cases),label=label,commands=[c[0] for c in commands],input_commands=commands))
        records.append(struct.pack('<'+'I'*len(words),*words))
    for j in range(128):
        commands=[[1],[3,0]+f([1.,2.,3.,.5]),[4]+f([1/60]),[3,1]+f([4.,5.,6.,-.5]),[4]+f([.1]),[3,2]+f([7.,8.,9.,0.]),[2,(101,100,200,0)[j%4]],[3,0]+f([9.,8.,7.,.25]),[0,j%2],[3,1]+f([1.,2.,3.,.5])]
        add('retained entry constructor capture and elapsed boundaries',seed(),commands)
    for j in range(96):
        commands=[[10,0,0]]
        for tick in range(48):
            torque=[0.,0.,0.,.25] if tick in (20,21,22) else [1.,-.5,.25,-.5]
            commands.append([9]+f(torque))
            axis=[(0.,.1,1.,-.5),(1.,1.,.25,.5),(-1.,-1.,-.5,.25),(0.,0.,0.,1.)][(j+tick)%4]
            speed=(.5,1.0999999,1.1,1.1000001)[(tick//12+j)%4]
            commands.append([5]+f([speed]+list(axis)))
        add('persistent anti-flip counters sign lanes threshold and queue capacity',seed(anti_flip_nudge_frames_2752=13),commands,(0,20,21)[j%3])
    for fail in (1,2,3):
        add('nudge partial service errors',seed(anti_flip_torque_2624=[1.,0.,0.,0.],anti_flip_nudge_frames_2752=13),[[10,fail,0],[5]+f([.5,1.,1.,.25,.5])])
    for counter in (0x7fffffff,-0x80000000,-1,12,13):
        add('wrapping anti-flip counters',seed(anti_flip_torque_2624=[1.,0.,0.,0.],anti_flip_nudge_frames_2752=counter),[[5]+f([.5,1.,0.,.25,.5])])
    unordered=float('nan')
    add('unordered anti-flip torque resets counter',seed(anti_flip_torque_2624=[unordered,0.,0.,0.],anti_flip_nudge_frames_2752=13),[[5]+f([.5,1.,0.,.25,.5])])
    add('unordered nudge speed rejects attempt',seed(anti_flip_torque_2624=[1.,0.,0.,0.],anti_flip_nudge_frames_2752=13),[[5]+f([unordered,1.,0.,.25,.5])])
    add('unordered projected nudge axis rejects force',seed(anti_flip_torque_2624=[1.,0.,0.,0.],anti_flip_nudge_frames_2752=13),[[5]+f([.5,unordered,0.,.25,.5])])
    for j in range(48):
        commands=[[10,0,1]]
        for tick in range(64):
            flags=0 if tick==48 else 0x0c000000
            commands.append([6,flags]+f([.5,.3])+[1])
        add('hang build apply countdown geometry and repeated wipeout',seed(hang_detection_frames_2740=0,hang_force_frames_2744=0,hung_wipeout_frames_2748=0),commands)
    for fail in (1,2):
        add('hang force partial errors',seed(hang_detection_frames_2740=19),[[10,fail,0],[6,0x08000000]+f([.5,.3])+[1]])
        add('hang geometry wipeout partial errors',seed(hung_wipeout_frames_2748=20),[[10,fail,1],[6,0x0c000000]+f([.5,0.])+[1]])
    for counter in (0x7fffffff,-0x80000000,-1):
        add('wrapping hang detection and wipeout histories',seed(hang_detection_frames_2740=counter,hung_wipeout_frames_2748=counter),[[10,0,1],[6,0x0c000000]+f([.5,.3])+[1]])
    for speed,scalar in ((unordered,.3),(.5,unordered)):
        add('unordered hang comparisons retain correct counter',seed(hang_detection_frames_2740=19,hung_wipeout_frames_2748=20),[[10,0,1],[6,0x0c000000]+f([speed,scalar])+[1]])
    for j in range(256):
        flags=(0,0x08000000)[j%2];speed=(.5,2.9999998,3.,3.0000002)[(j//2)%4]
        x=(.1,.56999999,.57000005)[(j//8)%3];y=(.01,.11999999,.12)[(j//24)%3]
        distance=(0.,.05,.10999999,.11000001)[(j//72)%4]
        add('wheel catch strict gates',seed(),[[7,flags]+f([speed,x,y,distance])])
    for fail in (0,1,2):
        add('wheel catch actual displacement and errors',seed(),[[10,fail,0],[7,0x08000000]+f([.5,.1,.01,.05])])
    for lane in range(4):
        values=[.5,.1,.01,.05];values[lane]=unordered
        add('unordered wheel-catch scalar rejects',seed(),[[7,0x08000000]+f(values)])
    for j in range(48):
        commands=[]
        for frame in (-1,0,1,29,30,31,89,90,91):
            commands += [[3,1]+f([3.,4.,5.,.25]),[8,j%2,frame&0xffffffff,0x00800000 if j%3 else 0]]
        add('pinning human latch controls captured position and window',seed(human_player_2724=j%2==0,captured_position_valid_2726=True,controls_latched_2725=False,was_pinning_2728=j%3==0),commands)
    add('pinning failed effect retains prior latch',seed(human_player_2724=True,captured_position_valid_2726=True,controls_latched_2725=False,was_pinning_2728=False),[[10,1,0],[8,0,0,0x00800000]])
    for j in range(96):
        ni=j%25;nb=j%9;indices=[n%nb if nb else 0 for n in range(ni)]
        bodies=f([rng.uniform(.1,5.) for _ in range(nb*9)])
        commands=[[13,ni]+indices+[nb]+bodies]
        for selected,part in ((0,0),(1,0),(1,max(0,ni-1)),(1,ni),(1,0xffffffff)):
            for drag in (-0.,0.,.2,1.,10.):commands.append([14,selected,part]+f([drag]))
        for _ in range(16):
            flags=rng.choice((0,0x20000000,0x40000000,0x60000000))
            commands.append([15,flags]+f([rng.uniform(0.,5.),rng.choice((0.,1.,-1.)),rng.choice((0.,1.,-1.)),rng.uniform(-1.,2.),1.,3.,.5,.1]))
        add('shared inertia groups tails invalid selection and retained fields',seed(),commands)
    # An invalid late handle must prevent even earlier valid inertia writes.
    add('all-or-nothing drag storage validation',seed(),[[13,5,0,1,0,1,9,2]+f([1.]*18),[14,0,0]+f([.5])])
    return struct.pack('<I',len(records))+b''.join(records),cases

def build_probes(output):
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip());relative=(PLUGIN/'ThirdParty/skate-runtime/crates/skate-core/src').relative_to(root).as_posix()
    revision=subprocess.check_output(['git','rev-parse',REFERENCE_REVISION],cwd=root,text=True).strip()
    archive=subprocess.check_output(['git','archive',f'{revision}:{relative}'],cwd=root)
    source=output/'reference-source'
    if source.exists():shutil.rmtree(source)
    source.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:stream.extractall(source,filter='data')
    originals={p.relative_to(source).as_posix():digest(p) for p in sorted(source.rglob('*.rs'))}
    probe=PLUGIN/'Tests/Reference/ground_state_probe.rs';main=source/'ground-state-oracle.rs';main.write_text((source/'lib.rs').read_text()+probe.read_text())
    reference=output/'ground-state-reference';subprocess.run(['rustc','+1.97.1','--edition=2024','-O','-A','dead_code',str(main),'-o',str(reference)],check=True)
    for name,expected in originals.items():assert digest(source/name)==expected,name
    native=PLUGIN/'Source/AtelierSkate/Private/Native';snapshot=output/'native-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir();units=('NativeMath','RigidBody','ForceQueue','Braking','GroundCorrections','GroundState','GroundStateCorrections','GroundDrag')
    for unit in units:
        for ext in ('h','cpp'):shutil.copy2(native/f'{unit}.{ext}',snapshot/f'{unit}.{ext}')
    pending=list(snapshot.iterdir());seen=set()
    while pending:
        path=pending.pop()
        if path.name in seen:continue
        seen.add(path.name)
        for name in re.findall(r'^#include "([^"\n]+)"',path.read_text(),re.M):
            target=snapshot/name
            if not target.exists():shutil.copy2(native/name,target)
            pending.append(target)
    cpp_probe=PLUGIN/'Tests/Native/ground_state_probe.cpp';shutil.copy2(cpp_probe,snapshot/cpp_probe.name)
    cpp=output/'ground-state-cpp';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/f'{u}.cpp') for u in units],str(snapshot/cpp_probe.name),'-o',str(cpp)],check=True)
    provenance=dict(reference_revision=revision,original_source_sha256=originals,source_archive_sha256=hashlib.sha256(archive).hexdigest(),reference_binary_sha256=digest(reference),cpp_binary_sha256=digest(cpp),native_source_sha256={p.name:digest(p) for p in sorted(snapshot.iterdir())},probe_sha256={p.name:digest(p) for p in (probe,cpp_probe)})
    (output/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');return cpp,reference

def coverage(data,cases):
    w=struct.unpack('<'+'I'*(len(data)//4),data);at=0;counts=Counter();services=Counter();errors=Counter()
    def frame():
        nonlocal at
        state=w[at:at+STATE_WORDS];at+=STATE_WORDS;n=w[at];at+=1
        queue=w[at:at+n*7];at+=n*7
        assert n<=21
        indices=w[at];at+=1+indices
        bodies=w[at];at+=1+bodies*9
        return state,n,queue
    for case in cases:
        index,commands,size=w[at:at+3];assert(index,commands)==(case['index'],len(case['commands']))
        case.update(first_output_word=at,output_words=size+3);at+=3;end=at+size;frame()
        for cmd in case['commands']:
            op,ok,a,b,error,calls,n=w[at:at+7];at+=7;assert op==cmd
            counts[f'command_{op}']+=1;log_end=at+n
            while at<log_end:
                sid,nargs=w[at:at+2];at+=2+nargs;services[sid]+=1
            assert at==log_end;state,queue_size,queue=frame()
            if not ok:errors[error if error else a]+=1
            if op==5 and ok:
                counts['nudge_attempted']+=a;counts['nudge_queued']+=b
                counts['nudge_capacity_drop']+=bool(a and not b)
            if op==7 and ok:counts['wheel_catch_applied']+=a
            if op==14:counts['drag_success' if ok else 'drag_rejected']+=1
            counts['full_queue_frames']+=queue_size==21
        assert at==end
    assert at==len(w)
    for sid in range(1,10):assert services[sid]>0,(sid,'missing service')
    for sid in range(1,10):assert errors[sid]>0,(sid,'missing partial error')
    for key in ('nudge_attempted','nudge_queued','nudge_capacity_drop','wheel_catch_applied','drag_success','drag_rejected','full_queue_frames'):assert counts[key]>0,key
    assert errors[100]>0 and errors[101]>0
    return dict(commands=dict(counts),service_calls=dict(services),partial_errors=dict(errors))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json'):(output/name).unlink(missing_ok=True)
    inputs,cases=corpus();(output/'input.bin').write_bytes(inputs);cpp,reference=build_probes(output)
    expected=subprocess.check_output([str(reference)],input=inputs);actual=subprocess.check_output([str(cpp)],input=inputs)
    (output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual)
    proof=coverage(expected,cases);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    if expected!=actual:
        first=next((i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b),min(len(expected),len(actual)));aligned=first//4*4
        case=next((c for c in cases if c['first_output_word']*4<=first<(c['first_output_word']+c['output_words'])*4),None)
        report=dict(passed=False,first_word=first//4,case=case,reference_length=len(expected),cpp_length=len(actual),reference_hex=expected[max(0,aligned-16):aligned+32].hex(),cpp_hex=actual[max(0,aligned-16):aligned+32].hex())
        (output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
    report=dict(passed=True,cases=len(cases),exact_words=len(expected)//4,coverage=proof,input_sha256=hashlib.sha256(inputs).hexdigest(),output_sha256=hashlib.sha256(expected).hexdigest(),comparison='All 55 state fields, retained correction histories, nine ordered required service boundaries, partial failures and shared inertia fields exact; no tolerance; original producer source unchanged',limitations='Supplied world geometry result at original mandatory query boundary; actual live world owner, full GroundBoard composition and whole gameplay/session scheduling remain separate.')
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
