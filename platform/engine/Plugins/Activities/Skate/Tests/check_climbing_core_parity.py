#!/usr/bin/env python3
"""Untouched optional Climbing clips/contact cores and pinned Bevy/glam math.

This is an independent leaf proof. World ledge admission, the sole physical
owner, frame scheduling and successful resume are covered separately. Root
alone builds/executes; --preflight only stages and hashes source/input data.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import struct
import subprocess
import check_animation_trees_parity as source
from session_parity import PLUGIN, REFERENCE_REVISION, digest

CODE=PLUGIN/'Source/AtelierSkate/Private/Native'
UNITS=('ClimbingMath','ClimbingClips','ClimbingContacts')
NAMES=('HIPS','SPINE3','LEFTSHOULDER','RIGHTSHOULDER','LEFTARM','RIGHTARM','LEFTFOREARM','RIGHTFOREARM','LEFTHAND','RIGHTHAND','LEFTFOOT','RIGHTFOOT','SKATEBOARD_ROOT','BOARD_HELPER')
PARENTS=(-1,0,1,1,2,3,4,5,6,7,0,0,0,12)
POSITIONS=((0,1,0),(0,.5,0),(-.12,.1,0),(.12,.1,0),(-.12,0,0),(.12,0,0),(-.32,.03,.02),(.32,.03,.02),(-.28,0,.05),(.28,0,.05),(-.12,-.85,0),(.12,-.85,0),(0,-.8,.4),(.137,.0317,-.0731))
def bits(f):return struct.unpack('<I',struct.pack('<f',f))[0]
def floats(v):return [bits(x)for x in v]
def word(v):return struct.pack('<I',v&0xffffffff)
def text(s):v=s.encode();return word(len(v))+v
def quat(axis,angle):
    length=math.sqrt(sum(x*x for x in axis));s=math.sin(angle*.5)/length
    return [*(x*s for x in axis),math.cos(angle*.5)]
def matrix(position=(0,0,0),angle=0,scale=(1,1,1)):
    c=math.cos(angle);s=math.sin(angle)
    return [c*scale[0],0,-s*scale[0],0,0,scale[1],0,0,s*scale[2],0,c*scale[2],0,*position,1]
def clip(name,n=0):
    frames=[]
    for tick in range(6):
        frame=[]
        for i,p in enumerate(POSITIONS):
            q=quat((.137,.731,-.317),(.07*tick+.0137*n)*(1 if i%2 else -1))
            scale=[1+(n%3)*.00317,1+(i%3)*.00137,1+(tick%3)*.00173]
            translation=[p[0]+(.00731*tick if i in(8,9)else 0),p[1]+(.00517*tick if i in(0,10,11)else 0),p[2]+(.0137*tick if i in(4,5,6,7,8,9)else 0)]
            frame.append([*scale,*q,*translation])
        frames.append(frame)
    return dict(name=name,fps=30+n*3.137,names=list(NAMES),parents=list(PARENTS),frames=frames)
def native(data):
    b=b'SKCLIP1\0'+word(data['version'])+word(len(data['clips']))
    for c in data['clips']:
        b+=text(c['name'])+word(bits(c['fps']))+word(len(c['names']))+b''.join(text(n)for n in c['names'])
        b+=word(len(c['parents']))+b''.join(word(p)for p in c['parents'])+word(len(c['frames']))
        for frame in c['frames']:b+=word(len(frame))+b''.join(word(bits(v))for s in frame for v in s)
    return b
def fixtures():
    stock=dict(version=1,clips=[clip('reach'),clip('mantle',1)])
    rows=[dict(label='optional file absent',data=None,error=''),dict(label='full authored skeleton',data=stock,error='')]
    def add(label,mutate,error):
        data=copy.deepcopy(stock);mutate(data);rows.append(dict(label=label,data=data,error=error))
    add('version rejected before clips',lambda d:d.update(version=2),'Unsupported climbing clip version')
    add('reach absent',lambda d:d['clips'].pop(0),'Missing climbing clip reach')
    add('mantle absent',lambda d:d['clips'].pop(1),'Missing climbing clip mantle')
    for fps in(-.137,0,240.00001525878906):add('fps '+str(fps),lambda d,fps=fps:d['clips'][0].update(fps=fps),'Invalid climbing clip reach')
    add('one frame',lambda d:d['clips'][0].update(frames=d['clips'][0]['frames'][:1]),'Invalid climbing clip reach')
    add('parent count',lambda d:d['clips'][0]['parents'].pop(),'Invalid climbing clip reach')
    for i,p in((0,0),(3,3),(2,-2),(12,99)):add('parent '+str((i,p)),lambda d,i=i,p=p:d['clips'][0]['parents'].__setitem__(i,p),'Invalid climbing clip reach')
    add('duplicate exact bone name',lambda d:d['clips'][0]['names'].__setitem__(13,'HIPS'),'Invalid climbing clip reach')
    add('frame bone count',lambda d:d['clips'][0]['frames'][0].pop(),'Invalid climbing clip reach')
    for lane,value in((0,0),(1,.0001),(2,-1),(3,.5),(6,.98),(6,1.02)):
        add('SQT10 lane '+str((lane,value)),lambda d,lane=lane,value=value:d['clips'][0]['frames'][0][0].__setitem__(lane,value),'Invalid climbing clip reach')
    for i,name in enumerate(NAMES[:13]):add('ordered required bone '+name,lambda d,i=i:d['clips'][0]['names'].__setitem__(i,'UNKNOWN_'+str(i)),'Missing climbing bone '+name)
    add('skeleton names differ',lambda d:d['clips'][1]['names'].__setitem__(13,'BOARD_ALT'),'Climbing clips must share a skeleton')
    add('skeleton parents differ',lambda d:d['clips'][1]['parents'].__setitem__(13,0),'Climbing clips must share a skeleton')
    add('validate unused bad clip before selecting names',lambda d:d['clips'].append(dict(clip('unused'),fps=0)),'Invalid climbing clip unused')
    add('first duplicate reach selected',lambda d:d['clips'].insert(0,clip('reach',7)),'')
    add('UTF8 and embedded NUL transport',lambda d:[c['names'].__setitem__(13,'BOARD_é_日本\0helper')for c in d['clips']],'')
    add('case sensitive names distinct',lambda d:[c['names'].append('hips')or c['parents'].append(0)or [f.append([1,1,1,0,0,0,1,.01,.02,.03])for f in c['frames']]for c in d['clips']],'')
    add('boundary fps240 accepted',lambda d:[c.update(fps=240)for c in d['clips']],'')
    return rows
def corpus(rows):
    rng=random.Random(0x434c494d);commands=[]
    def add(op,args,label):commands.append(dict(op=op,args=args,label=label))
    for n in range(768):
        a=[rng.uniform(-2,2)for _ in range(3)];b=[rng.uniform(-2,2)for _ in range(3)]
        if n%8==0:b=a.copy()
        if n%8==1:b=[-x for x in a]
        q=quat((.137,.731,-.317),(n%31)*.137);r=q.copy()if n%6==0 else[-x for x in q]if n%6==1 else quat((-.317,.137,.731),(n%37)*-.173)
        t=(-.5,0,.0001,.137,.5,.99999994,1,1.00000012,1.5)[n%9]
        m=matrix((.137*n,.731,-.317),.0731*n,(-1 if n%7==0 else 1,1.137,.731));k=matrix((-.317,.731*n,.137),-.0317*n,(1.0137,.731,1.317))
        add(0,floats([*a,*b,*[rng.uniform(-2,2)for _ in range(3)],*q,*r,t,*m,*k]),'pinned glam operation trees, reflection/antiparallel/shortest interpolation')
    add(1,[0],'absent optional clears prior returned owner');add(2,[0,bits(0)],'explicit no authored clips')
    for i,row in enumerate(rows):
        add(1,[1],'stock recovery before loader');add(1,[i],row['label'])
        if row['data']and not row['error']:
            for which in(0,1):
                for time in(-1,0,.0001,1/60,.05,.1,.1666666667,1,100):add(2,[which,bits(time)],'sample/clamp both clips')
    add(1,[1],'full contact owner')
    for n in range(240):
        time=(-.137,0,.016666667,.0731,.137,.317)[n%6];yaw=(n%11-5)*.137;root=matrix((.137,-.317,.731),yaw)
        forward=[math.sin(yaw),0,math.cos(yaw)];anchor=[.137,1.7,.731];landing=[.137,1.685,1.351];palms=[[-.3,1.68,.731],[.3,1.68,.731]];normals=[[0,1,0],[.0137,.9999,.00317]]
        weight=(0,.0137,.137,.5,.731,.99999994,1)[n%7]
        add(3,[n%2,bits(time),*floats([*root,*anchor,*landing,*forward,*palms[0],*palms[1],*normals[0],*normals[1],weight])],'both wrists and retained local hierarchy with blended two-bone IK')
    return commands
def encode(commands):return word(len(commands))+b''.join(word(c['op'])+b''.join(word(w)for w in c['args'])for c in commands)
class Reader:
    def __init__(self,b):self.b=b;self.at=0
    def word(self):v=struct.unpack_from('<I',self.b,self.at)[0];self.at+=4;return v
    def words(self,n):v=struct.unpack_from('<'+'I'*n,self.b,self.at);self.at+=4*n;return v
    def text(self):n=self.word();v=self.b[self.at:self.at+n].decode();self.at+=n;return v
    def status(self):return self.word(),self.text()
    def clip(self):
        name=self.text();fps,duration=self.words(2);names=[self.text()for _ in range(self.word())];parents=self.words(self.word());frames=[self.words(self.word()*10)for _ in range(self.word())]
        return dict(name=name,fps=fps,duration=duration,names=names,parents=parents,frames=frames)
    def owner(self):return [self.clip(),self.clip()]if self.word()else None
    def pose(self):
        locals=self.words(self.word()*10);globals=self.words(self.word()*16);points=self.words(9);return dict(locals=locals,globals=globals,points=points)
def coverage(raw,commands,rows):
    r=Reader(raw);assert r.word()==len(commands);counts=Counter();errors=Counter();poses=set();locals=set();wrists=set();owner=None;loaded=0;retained=0;mathrows=set()
    for c in commands:
        op=r.word();assert op==c['op'];okay,error=r.status();counts[op]+=1
        if op==0:
            first=r.words(10);rest=r.words((3 if first[9]else 0)+135);mathrows.add(first+rest);assert okay and not error
        elif op==1:
            candidate=r.owner();expected=rows[c['args'][0]]['error'];assert error==expected and okay==int(not expected),(c['label'],error,expected)
            if error:errors[error]+=1;assert candidate==owner;retained+=1
            else:owner=candidate;loaded+=bool(owner)
        else:
            if owner is None:assert error=='Missing authored climbing clips'and not okay;continue
            assert okay and not error;p=r.pose();poses.add(p['globals']);locals.add(p['locals'])
            if op==3:wrists.add(r.words(14))
    assert r.at==len(raw)
    assert set(counts)=={0,1,2,3}and len(mathrows)>700 and loaded>40 and retained>30
    assert len(poses)>200 and len(locals)>200 and len(wrists)>5
    assert any('unused'in e for e in errors)and sum(e.startswith('Missing climbing bone')for e in errors)==13
    return dict(operations=dict(counts),loader_errors=dict(errors),successful_loads=loaded,failed_loads_preserving_prior_owner=retained,distinct_glam_outputs=len(mathrows),distinct_global_poses=len(poses),distinct_local_poses=len(locals),distinct_wrist_pairs=len(wrists))
def prepare(output,rows,commands):
    snapshot=output/'native-source';crate=output/'reference-source/climbing-core';fixture_root=output/'fixtures'
    for path in(snapshot,crate,fixture_root):
        if path.exists():shutil.rmtree(path)
        path.mkdir(parents=True)
    headers=('NativeMath.h','ClimbingMath.h','ClimbingClips.h','ClimbingContacts.h','ClimbingTypes.h')
    for p in [CODE/h for h in headers]+[CODE/(u+'.cpp')for u in UNITS]:shutil.copy2(p,snapshot/p.name)
    shutil.copy2(PLUGIN/'Tests/Native/climbing_core_probe.cpp',snapshot/'climbing_core_probe.cpp')
    originals={};modules=crate/'src/climbing';modules.mkdir(parents=True)
    for name in('clip','contacts'):
        relative='crates/skate-host/src/physics/climbing/'+name+'.rs';body=source.source_at_reference(relative);(modules/(name+'.rs')).write_text(body);originals[relative]=hashlib.sha256(body.encode()).hexdigest();assert (modules/(name+'.rs')).read_bytes()==body.encode()
    body=source.source_at_reference('crates/skate-host/src/physics/climbing/mod.rs');smooth,record=source.extract_block(body,'fn smooth(')
    ledge_body=source.source_at_reference('crates/skate-host/src/physics/climbing/ledge.rs');ledge,ledge_record=source.extract_block(ledge_body,'pub(super) struct Ledge {')
    probe=(PLUGIN/'Tests/Reference/climbing_core_probe.rs').read_text().replace('// GENERATED_ORIGINAL_SMOOTH',smooth).replace('// GENERATED_ORIGINAL_LEDGE_DECLARATION','#[derive(Clone, Copy, Debug)]\n'+ledge);(crate/'src/main.rs').write_text(probe)
    (crate/'Cargo.toml').write_text('[package]\nname="climbing-core-reference"\nversion="0.1.0"\nedition="2024"\n[workspace]\n[dependencies]\nbevy={version="=0.19.1",default-features=false,features=["std"]}\nserde={version="1",features=["derive"]}\nserde_json="1"\n')
    lock=source.source_at_reference('atelier-host/Cargo.lock');(crate/'Cargo.lock').write_text(lock)
    for i,row in enumerate(rows):
        path=fixture_root/('case-'+str(i));(path/'private/custom').mkdir(parents=True)
        if row['data'] is not None:
            (path/'private/custom/climbing.json').write_text(json.dumps(row['data'],ensure_ascii=False,allow_nan=False))
            (path/'climbing.skclip').write_bytes(native(row['data']))
    (output/'input.bin').write_bytes(encode(commands));(output/'commands.json').write_text(json.dumps(commands,indent=2)+'\n');(output/'fixtures.json').write_text(json.dumps(rows,indent=2,ensure_ascii=False)+'\n')
    report=dict(reference_revision=REFERENCE_REVISION,original_complete_modules=originals,original_smooth_extraction=record,original_ledge_declaration_extraction=ledge_record,immutable_native_sources={p.name:digest(p)for p in sorted(snapshot.iterdir())},tracked_native_dependency=dict(header='NativeMath.h',sha256=digest(CODE/'NativeMath.h'),usage='Canonical types only, no recovered numerical kernels linked'),arithmetic_backend='Actual pinned glam 0.32.1 AArch64 neon operation tree; other target SIMD backends require separate proof',reference_probe_sha256=digest(crate/'src/main.rs'),initial_cargo_lock_sha256=digest(crate/'Cargo.lock'),input_sha256=digest(output/'input.bin'),commands=len(commands),fixtures=len(rows),scope='Complete original clip.rs and contacts.rs remain byte-identical. The source Ledge data declaration and smooth function are extracted verbatim with byte offsets/hashes. Only stdin/stdout observers are authored. All glam/Bevy arithmetic executes its actual pinned implementation. Native transport encodes the same original JSON typed fields; corrupt JSON/native byte parsers are distinct formats and are not claimed equivalent. This is a leaf proof; no global frame, world admission or physical owner is substituted.')
    (output/'provenance.json').write_text(json.dumps(report,indent=2)+'\n');return snapshot,crate,fixture_root,report
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--target-dir',type=Path,required=True);parser.add_argument('--preflight',action='store_true');args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in('result.json','first-divergence.json'):(output/name).unlink(missing_ok=True)
    rows=fixtures();commands=corpus(rows);snapshot,crate,fixtures_path,report=prepare(output,rows,commands)
    if args.preflight:print(json.dumps(dict(preflight='PASS',commands=len(commands),fixtures=len(rows),input_bytes=len(encode(commands)),input_sha256=report['input_sha256'])));return
    subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(crate/'Cargo.toml'),'--target-dir',str(args.target_dir.resolve()),'--bin','climbing-core-reference'],check=True)
    reference=output/'climbing-core-reference';shutil.copy2(args.target_dir.resolve()/'release/climbing-core-reference',reference)
    candidate=output/'climbing-core-native';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(u+'.cpp'))for u in UNITS],str(snapshot/'climbing_core_probe.cpp'),'-o',str(candidate)],check=True)
    for path,expected in report['original_complete_modules'].items():assert digest(crate/'src/climbing'/Path(path).name)==expected
    raw=(output/'input.bin').read_bytes();values=[]
    for binary,label in((reference,'reference'),(candidate,'native')):
        run=subprocess.run([str(binary),str(fixtures_path)],input=raw,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True);(output/(label+'.bin')).write_bytes(run.stdout);(output/(label+'.stderr')).write_bytes(run.stderr);values.append(run.stdout)
    if values[0]!=values[1]:
        offset=next((i for i,(a,b)in enumerate(zip(*values))if a!=b),min(map(len,values)));(output/'first-divergence.json').write_text(json.dumps(dict(byte_offset=offset,reference_bytes=len(values[0]),native_bytes=len(values[1])),indent=2)+'\n');raise AssertionError('Climbing core first mismatch at byte '+str(offset))
    proof=coverage(values[0],commands,rows);report.update(reference_compiler=subprocess.check_output(['rustc','+1.97.1','-vV'],text=True).strip(),candidate_compiler=subprocess.check_output(['clang++','--version'],text=True).strip(),final_cargo_lock_sha256=digest(crate/'Cargo.lock'),reference_binary_sha256=digest(reference),native_binary_sha256=digest(candidate));(output/'provenance.json').write_text(json.dumps(report,indent=2)+'\n')
    result=dict(result='PASS',commands=len(commands),fixtures=len(rows),exact_bytes=len(values[0]),sha256=hashlib.sha256(values[0]).hexdigest(),coverage=proof);(output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
