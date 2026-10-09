#!/usr/bin/env python3
"""Compare production pose commands, hierarchy, and project-authored overrides.

Stock data uses the already verified project ATSKEL01/ATCLIP01 files.
The override JSON is the project's own body-animation/mod format, not EA data.
The oracle includes the original frozen production host evaluator unchanged.
Run compilation and execution under the shared render lock/memory guard.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import struct
import subprocess
from check_animation_playback_parity import Stream
from check_gesture_parity import PLUGIN
from reference_build import build_probe

SLOTS=['R_ANTIC_OLLIE_N_0_INTO','R_ANTIC_OLLIE_N_0_CYC','R_ANTIC_360SHUVIT_N_0_CYC','360FLIP_D_HIGH_G','360FLIP_D_HIGH_A','360FLIP_D_LOW_G','360FLIP_D_LOW_A']


def rig_names(samples):
    raw=(samples/'simulation/rig.skate').read_bytes();at=8
    def word():
        nonlocal at
        v=struct.unpack_from('<I',raw,at)[0];at+=4;return v
    def string():
        nonlocal at
        n=word();s=raw[at:at+n].decode();at+=n;return s
    n=word();word();names=[]
    for _ in range(n):names.append(string());word();word()
    return names


def matrix(bone,frame,variant):
    angle=(0.137,1.973,3.327,4.792)[(bone+frame+variant)%4];axis=(bone+variant)%3
    q=[0.0,0.0,0.0,math.cos(angle/2)];q[axis]=math.sin(angle/2);x,y,z,w=q;x2,y2,z2=x+x,y+y,z+z
    xx,xy,xz,yy,yz,zz,wx,wy,wz=x*x2,x*y2,x*z2,y*y2,y*z2,z*z2,w*x2,w*y2,w*z2
    out=[1-(yy+zz),xy+wz,xz-wy,0,xy-wz,1-(xx+zz),yz+wx,0,xz+wy,yz-wx,1-(xx+yy),0,(bone%7)*.173+frame*.031+variant*.37,(bone%5)*.113-frame*.003,-bone*.019+frame*.071,1]
    for column in range(3):
        scale=(.973,1.017,1.031)[(bone+column)%3]
        for lane in range(4):out[column*4+lane]*=scale
    return out


class Writer(Stream):
    def commands(self,commands):
        self.word(len(commands))
        for kind,args in commands:
            self.word(kind)
            if kind==0:self.string(args[0]);self.float(args[1]);self.float(args[2]);self.word(args[3])
            elif kind==1:self.float(args)
            elif kind==2:
                self.word(len(args))
                for w in args:self.float(w)
            elif kind==3:self.float(args[0]);self.word(args[1])
            elif kind==4:self.string(args)
            else:self.word(args)


def corpus(samples):
    manifest=json.loads((samples/'simulation/samples-manifest.json').read_text());clips=manifest['clips'];lookup={c['name'].split('/',1)[1]:c for c in clips};names=rig_names(samples);cases=[];counts=Counter();rng=random.Random(0x46513a6)
    def new(op):
        s=Writer();s.word(op);cases.append(s);counts[op]+=1;return s
    def evaluate(cs):new(4).commands(cs)
    def document(slots,variant=0):
        return dict(version=1,bone_names=names,clips={name:dict(fps=30.0,frames=[[matrix(b,f,variant) for b in range(len(names))] for f in range(lookup[name]['frames'])]) for name in slots})
    def load(d):new(0).string(json.dumps(d,separators=(',',':')))
    def install(owner,d):s=new(1);s.string(owner);s.string(json.dumps(d,separators=(',',':')))
    # One complete pose/hierarchy per stock clip covers canonical lookup, both
    # banks, trajectory/no-loop and single-transform application for many loops.
    for i,c in enumerate(clips):
        name=c['name'].split('/',1)[1];evaluate([(0,(name.lower() if i%3==0 else name,.137,.071,(0,1,2,0xffffffff)[i%4]))])
    poses=['RIG_TPOSE','BOARD_BACKWARDS','BOARD_BACKWARDS_IK','POSTURE_STIFF_POSE','POSTURE_SLOUCH_POSE','POSTURE_BUFF_POSE']
    for name in poses:evaluate([(4,name)])
    for mode in (0,1,2,3):
        for name in SLOTS:evaluate([(0,(name,.137,.071,1)),(4,'RIG_TPOSE'),(5,True),(6,mode),(4,'BOARD_BACKWARDS'),(5,False),(4,'BOARD_BACKWARDS_IK'),(5,False)])
    for i in range(96):
        chosen=rng.sample(clips,3);c=[(0,(v['name'].split('/',1)[1],rng.uniform(0,.3),rng.uniform(0,.1),i%3)) for v in chosen]
        if i%3==0:c.extend([(2,[.137,.317,.546]),(4,'RIG_TPOSE'),(5,True)])
        else:c.extend([(3,(.731,bool(i%2))),(1,.317),(4,'RIG_TPOSE'),(5,True)])
        if i%2:c.append((6,i%3))
        evaluate(c)
    # Stack failures preserve exact stock error strings and operand order.
    for cs in ([],[(5,False)],[(6,1)],[(1,.5)],[(4,'RIG_TPOSE'),(1,.5)],[(4,'RIG_TPOSE'),(4,'RIG_TPOSE')],[(2,[])],[(2,[1])],[(0,('MISSING',0,0,0))],[(4,'MISSING')]):evaluate(cs)
    for i in range(128):
        p=lambda:[rng.uniform(.7,1.3),rng.uniform(.7,1.3),rng.uniform(.7,1.3),rng.uniform(.7,1.3),*[rng.uniform(-.7,.7) for _ in range(4)],*[rng.uniform(-3,4) for _ in range(4)]]
        a,b=p(),p();s=new(6);s.sqt(a);s.sqt(b);s.word(i%2)
        if i%2:
            for v in [*[rng.uniform(-1,1) for _ in range(4)],*[rng.uniform(-3,4) for _ in range(3)]]:s.float(v)
        s=new(7);s.sqt(a);s.sqt(b);s.word(i%2)
    for mode,partners in [(0,[-1,1,3,2]),(1,[0,1,3,2]),(2,[0,2,1,3]),(1,[0,2,1,3]),(0,[0,1,9,3]),(1,[0,1,-2,3])]:
        s=new(5);s.word(4)
        for i in range(4):s.sqt([1,1,1,1,.137*i,.317,.731,.517,.317*i,.113,.197*i,.731])
        s.words([0xffffffff,0,1,2]);s.words(partners);s.word(mode)
    # Project-owned authored clip baking is checked through every source frame,
    # including stock board preservation and helper targets in stock board space.
    authored=document(SLOTS);load(authored)
    for name in SLOTS:
        for frame in range(lookup[name]['frames']):evaluate([(0,(name,frame/30,(frame-1)/30,1 if frame==0 else 0))])
    slot0=document([SLOTS[0]],1);slot1=document([SLOTS[1]],2)
    install('Zulu',slot0);evaluate([(0,(SLOTS[0],.137,.071,1))]);install('Alpha',slot0)
    install('Alpha',slot1);install('Middle',document(SLOTS[:2],3))
    install('Zulu',document([SLOTS[0]],4));evaluate([(0,(SLOTS[0],.137,.071,1))])
    new(2).string('Zulu');evaluate([(0,(SLOTS[0],.137,.071,1))]);evaluate([(0,(SLOTS[1],.137,.071,0))]);new(3);evaluate([(0,(SLOTS[1],.137,.071,0))])
    # Empty same-owner installation releases its previous slot reservation.
    install('Zulu',slot0);install('Zulu',document([]));install('Alpha',slot0);evaluate([(0,(SLOTS[0],.137,.071,1))]);new(2).string('Alpha');new(3)
    bad=document([]);bad['version']=2;load(bad)
    bad=document([]);bad['bone_names']=names[:-1];install('Bad',bad)
    bad=document([]);bad['clips']['UNSUPPORTED']=dict(fps=30,frames=[]);install('Bad',bad)
    bad=document([SLOTS[0]]);bad['clips'][SLOTS[0]]['fps']=24;install('Bad',bad)
    bad=document([SLOTS[0]]);bad['clips'][SLOTS[0]]['frames'][0]=[];install('Bad',bad)
    bad=document([SLOTS[0]]);bad['clips'][SLOTS[0]]['frames'][0][1][0]*=3;install('Bad',bad)
    # Strict struct fields and missing values are part of our override format.
    for text in ('{}','{"version":1,"bone_names":[],"clips":{},"unused":0}','{"version":1,"version":1,"bone_names":[],"clips":{}}'):
        s=new(1);s.string('Bad');s.string(text)
    evaluate([(0,(SLOTS[0],.137,.071,1))]);load(document([]));evaluate([(0,(SLOTS[0],.137,.071,1))])
    return cases,clips,dict(counts)


def encoded(cases,clips):
    s=Writer();s.data.extend(b'ATPOSE01');s.word(len(cases));s.word(len(clips))
    for c in clips:s.string(c['name'])
    s.data.extend(b''.join(c.data for c in cases));return bytes(s.data)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',required=True,type=Path);p.add_argument('--samples',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--target-dir',required=True,type=Path);args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    reference=build_probe(output,'animation-pose-reference',PLUGIN/'Tests/Reference/animation_pose_probe.rs',args.target_dir,bevy=True,extra_sources={"crates/skate-host/src/authored_clips.rs":"crates/skate-host/src/animation_pose/authored_clips.rs"})
    live=PLUGIN/'Source/AtelierSkate/Private/Simulation';code=output/'simulation-source';code.mkdir(exist_ok=True);binary=output/'animation-pose-cpp'
    sources=['AnimationPose.cpp','AnimationPoseAuthored.cpp','AnimationPoseJson.cpp','AnimationPlayback.cpp','AnimationSamples.cpp','AnimationName.cpp','SimulationMath.cpp']
    for path in list(live.glob('*.h'))+[live/s for s in sources]:shutil.copyfile(path,code/path.name)
    probe=code/'animation_pose_probe.cpp';shutil.copyfile(PLUGIN/'Tests/Simulation/animation_pose_probe.cpp',probe)
    simulation_snapshot={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(code.iterdir()) if p.is_file()}
    (output/'simulation-source-provenance.json').write_text(json.dumps(simulation_snapshot,indent=2)+'\n')
    subprocess.run(['clang++','-std=c++17','-O2','-fno-exceptions','-ffp-contract=off','-Wall','-Wextra','-Werror','-I',str(code),*[str(code/s) for s in sources],str(probe),'-o',str(binary)],check=True)
    cases,clips,counts=corpus(args.samples);commands=encoded(cases,clips);(output/'input.bin').write_bytes(commands);fixture=output/'authored-fixture'
    def run(exe,source,data):return subprocess.check_output([str(exe),str(source),str(fixture)],input=data)
    expected=run(reference,args.assets.resolve(),commands);actual=run(binary,args.samples.resolve()/'simulation',commands);(output/'reference.bin').write_bytes(expected);(output/'simulation.bin').write_bytes(actual)
    if actual!=expected:
        lo=0;hi=len(cases)
        while hi-lo>1:
            m=(lo+hi)//2;data=encoded(cases[:m],clips)
            if run(reference,args.assets.resolve(),data)==run(binary,args.samples.resolve()/'simulation',data):lo=m
            else:hi=m
        (output/'first-divergence-input.bin').write_bytes(encoded(cases[:hi],clips));first=next((i for i,(a,e) in enumerate(zip(actual,expected)) if a!=e),min(len(actual),len(expected)))
        raise AssertionError(f'Animation pose differs at byte {first}, case {lo}; reproducing prefix saved')
    result=dict(passed=True,cases=len(cases),counts=counts,stock_clips=len(clips),output_bytes=len(actual),output_sha256=hashlib.sha256(actual).hexdigest(),comparison='production command stacks, trajectory/add/mirror, complete poses/hierarchy, project-authored body baking, mod ownership/conflict/precedence/removal',stock_format='ATSKEL01/ATCLIP01; no original stock-data reader in simulation runtime',override_format='project-authored version1 absolute-joint JSON, original production custom/mod format',source='untouched frozen skate-host/animation_pose.rs and authored_clips.rs, independent stock bank reader',simulation_source_provenance_sha256=hashlib.sha256((output/'simulation-source-provenance.json').read_bytes()).hexdigest())
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
