#!/usr/bin/env python3
"""Whole unchanged render_pose, SkeletonOutput and FootPhysicalOutput owners.

Compilation/execution is reserved for the root render guard. Explicit caller
inputs feed the actual stock evaluator, shared physical/IK/correction/wobble
owners; no finished render, contact or numeric callback is substituted.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import check_plant_air_owner_parity as plant
import check_skater_animation_complete_parity as facade
import check_wipeout_runtime_parity as wipeout
from check_graph_parity import element, original_graph
from session_parity import REFERENCE_REVISION, digest

PLUGIN=plant.PLUGIN
CODE=plant.CODE
TESTS=PLUGIN/'Tests'
UNITS=tuple(dict.fromkeys((*plant.UNITS,*facade.UNITS,*wipeout.UNITS,
    'GraphActionPhysicalConditions','FootPhysicalOutput','SkeletonOutputBoard',
    'SkeletonOutputRuntime','RenderPoseRuntime')))
fs,bits=plant.fs,plant.bits
SECTIONS=(*plant.lifecycle.SECTIONS,'output_owner','foot_owner','render_owner')
FIELDS=(('physicsdeck','DeckWidth',0),('physicsdeck','DeckFrontEndSize',0),
    ('physicsdeck','DeckMidLength',0),('physics_skeletonik','FootOnDeckPadding',0),
    ('physics_skeleton','TruckTiltScalar',1),('physics_skeleton','TruckTiltMaxAngle',1),
    ('physics_skeleton','TruckTiltWobbleScalar',1),('physics_skeleton','TruckDisplacementMax',1),
    ('physicstrucks','TruckYPos',1),('physics_deck_wobble','TiltVsTimeTakeOff',1),
    ('physics_deck_wobble','TiltVsTimeLanding',1),('physics_deck_wobble','SquishVsTimeTakeOff',1),
    ('physics_deck_wobble','SquishVsTimeLanding',1),('physics_deck_wobble','MaxTime',1))
ARRAYS={'FootOnDeckPadding','TiltVsTimeTakeOff','TiltVsTimeLanding','SquishVsTimeTakeOff','SquishVsTimeLanding'}

FOOT_OBSERVER=r'''
impl FootPhysicalOutputs {
 pub(crate)fn migration_render_reset(&mut self){self.state.reset();}
 pub(crate)fn migration_render_observe(&self,o:&mut crate::Output){for v in self.state.previous_local_toes{o.floats(v)}o.float(self.settings.deck_half_width);o.float(self.settings.deck_total_half_length);o.floats(self.settings.padding);for v in self.output.local_velocity{o.floats(v)}for v in self.output.world_velocity{o.floats(v)}for v in self.output.within_deck_box{o.word(v as u32)}}
}
'''
OUTPUT_OBSERVER=r'''
impl SkeletonOutput {
 pub(crate)fn migration_render_observe(&self,o:&mut crate::Output){
  for v in self.pose.bone_indices{o.word(v as u32)}for p in self.pose.geometry.parents{o.word(p.is_some()as u32);if let Some(p)=p{o.word(p as u32)}}for m in self.pose.geometry.inverse_part_frames{o.matrix(m)}
  let b=self.pose.board_bones;for n in [b.front_truck,b.back_truck,b.front_left_wheel,b.front_right_wheel,b.back_left_wheel,b.back_right_wheel]{o.word(n as u32)}
  let b=self.pose.board_settings;o.floats([b.truck_tilt_scalar,b.truck_tilt_max_angle,b.truck_tilt_wobble_scalar,b.truck_displacement_max]);let w=&self.wobble;o.word(w.active as u32);o.word(w.landing as u32);o.float(w.time);o.float(w.amplitude);o.float(w.direction);o.word(w.migration_render_selected()as u32);
  let v=self.deck_wobble;o.word(v.sampled as u32);o.float(v.tilt);o.float(v.squish);o.word(v.remains_active as u32);o.float(self.compression_rest_height);
  for g in [self.wobble_settings.takeoff_tilt,self.wobble_settings.landing_tilt,self.wobble_settings.takeoff_squish,self.wobble_settings.landing_squish]{o.floats(g.x);o.floats(g.y)}o.float(self.wobble_settings.maximum_time);
 }
}
'''
CORE_OBSERVER=b'\nimpl Wobble{pub fn migration_render_selected(&self)->bool{self.selected_landing_curves}}\n'

def text(value):
    data=value.encode();return [len(data),*data]
def f32(value):return struct.unpack('<f',struct.pack('<f',value))[0]
def flatten(value):return plant.numeric.flatten(value)
def record(data,cls,key='default'):
    return next(r for r in data['collections']if r['class']==cls and r['key']==key)
def stock_words(data,cls,name):
    r=record(data,cls)
    while name not in r['fields']:
        assert r.get('parent'),(cls,name);r=record(data,cls,r['parent'])
    raw=r['fields'][name]['data'];return [int(raw[k:k+8],16)for k in range(0,len(raw),8)]
def floats(words):return [struct.unpack('<f',struct.pack('<I',v))[0]for v in words]
def foot_bounds(data):
    width=f32(floats(stock_words(data,'physicsdeck','DeckWidth'))[0]*.5)
    length=f32(floats(stock_words(data,'physicsdeck','DeckFrontEndSize'))[0]+f32(floats(stock_words(data,'physicsdeck','DeckMidLength'))[0]*.5))
    return [f32(a+b)for a,b in zip((width,0,length,0),floats(stock_words(data,'physics_skeletonik','FootOnDeckPadding')))]
def loader_fixtures():
    rows=[dict(label='stock feet',kind=0),dict(label='stock output',kind=1)]
    for index,(cls,name,kind)in enumerate(FIELDS):
        for mode in ('missing','short','type'):
            rows.append(dict(label=mode+' '+name,kind=kind,mode=mode,fields=[index]))
        if name not in ARRAYS:rows.append(dict(label='nonfinite '+name,kind=kind,mode='nonfinite',fields=[index]))
        if index+1<len(FIELDS)and FIELDS[index+1][2]==kind:
            rows.append(dict(label='ordered missing '+name+' then '+FIELDS[index+1][1],kind=kind,mode='missing',fields=[index,index+1]))
    return rows

def prepare(assets,output):
    fixtures=output/'fixtures';fixtures.mkdir(exist_ok=True)
    source=assets/'private/stock/skater-collections.json';stock=json.loads(source.read_text())
    (fixtures/'settings.native').write_bytes(plant.converter.encode_settings(source))
    skeletons=assets/'private/stock/physics-skeletons.json'
    (fixtures/'physics.native').write_bytes(plant.converter.encode_physics_skeletons(skeletons))
    rows=loader_fixtures()
    for index,row in enumerate(rows):
        data=copy.deepcopy(stock)
        for field in row.get('fields',[]):
            cls,name,_=FIELDS[field];fields=record(data,cls)['fields'];mode=row['mode']
            if mode=='missing':fields.pop(name,None)
            elif mode=='short':fields[name]['data']=fields[name]['data'][:-8]
            elif mode=='type':fields[name]['type']='EA::Reflection::Int32'
            elif mode=='nonfinite':fields[name]['data']='7FC12345'
            else:raise AssertionError(mode)
        folder=fixtures/f'case-{index}';original=folder/'private/stock/skater-collections.json'
        original.parent.mkdir(parents=True,exist_ok=True);original.write_text(json.dumps(data))
        (folder/'settings.native').write_bytes(plant.converter.encode_settings(original))
        row.update(original_sha256=digest(original),native_sha256=digest(folder/'settings.native'))
    for kind in ('action','motion'):
        graph=element('state','idle');(fixtures/f'actor.{kind}.reference').write_bytes(original_graph(graph))
        (fixtures/f'actor.{kind}.native').write_bytes(plant.converter.encode_graph(plant.converter.read_graph(fixtures/f'actor.{kind}.reference')))
    (fixtures/'loader-provenance.json').write_text(json.dumps(rows,indent=2)+'\n')
    return fixtures,json.loads(skeletons.read_text())['source_sha256'],stock

def control(j,state=None):
    state=state or (100,201,601,701,500,503,202,400)[j%8]
    flags=0x2000|((j%2)<<20)|((1<<18)if j%4==1 else 0)
    return [20,flags,0,(1<<30)if j%4==3 else 0,8 if j%8 in(3,7)else 0,(1<<18)if j%3 else 0,
        state,state//100*100,bits(.0137*(j%23)),j%7,*fs([.137,1.,-.317,.1731]),j%3]
def toe_matrix(point):
    m=copy.deepcopy(plant.matrix(0));m[0]=[1,0,0,0];m[1]=[0,1,0,0];m[2]=[0,0,1,0];m[3]=list(point);return fs(flatten(m))

def corpus(samples,stock):
    clips=json.loads((samples/'samples-manifest.json').read_text())['clips'][::29]
    names=[c['name']for c in clips];cases=[]
    def add(label,commands,kind=0):
        cases.append(dict(index=len(cases),label=label,commands=commands,world=plant.numeric.authored_query_world(kind,pool=kind)[1:],edges=plant.numeric.edges(kind)))
    for n in range(6):
        commands=[]
        for k in range(64):
            j=n*64+k;clip=names[j%len(names)].split('/',1)[1]
            commands += [control(j),[1,4,*text(clip),bits((0,.0173,.137,.731)[j%4])],
                [4,*fs([math.sin(j*.137)*.1731,math.cos(j*.1731)*.317])]]
            if j%9==0:commands += [[5,j%2,(j//9)%2]]
            commands += [[7,*fs([.137+j*.00173,-.317,.731,.1731]),*fs([0,0,0,0]),1],
                [3,15,*fs(flatten(plant.matrix(j)))],[3,19,*fs(flatten(plant.matrix(j+1)))],
                [10,15,*fs([j*.0173,.731,-.317,.137])],[10,19,*fs([-.137,j*.0317,.517,-.731])]]
            if j%4==0:commands += [[19,*fs([.137+j*.00173,.731,-.317,.1731]),0xffffffff]]
            # Actual live wheel positions excite compression independently of
            # target steering. These are source body-rate caller inputs.
            commands += [[17,j%4,*fs([.0137*j,.037*(j%17),-.0317*j])],[2],[11]]
            if j%7==0:commands += [[6],[8,bits(.0137)],[9],[8,bits(.0173)]]
        commands += [[18,0xffffffff,0xffffffff],[1,0],[2]]
        add('real sampled stock poses and shared physical owners '+str(n),commands,n%3)
    commands=[[3,0,*toe_matrix([0,0,0,0])]]
    bounds=foot_bounds(stock)
    for axis in range(3):
        for sign in (-1,1):
            for delta in (-1,0,1):
                p=[0.,0.,0.,.1731];p[axis]=sign*floats([bits(bounds[axis])+delta])[0]
                commands += [[3,15,*toe_matrix(p)],[3,19,*toe_matrix(p)],[8,bits(.0173)]]
    for dt in (0,0x80000000,1,0x00800000,bits(.0137),0x7f800000,0xff800000,0x7fc01234,0xffc01234):commands += [[8,dt],[9]]
    add('strict toe box boundaries and exact reciprocal IEEE domains',commands)
    for label in ('empty','short','mapped'):
        commands=[control(1),[1,0],[5,1,1],[7,*fs([.317,.137,-.731,.1731]),*fs([0,0,0,0]),1]]
        commands += [[15,0,0xffffffff]]if label=='mapped'else[[14,0 if label=='empty'else 1]]
        commands += [[2],[2],[8,bits(.0173)],[1,0]]
        if label=='mapped':commands += [[13,1,1]]
        commands += [[2]];add('retained source failure prefix '+label,commands)
    commands=[]
    for index,row in enumerate(loader_fixtures()):commands += [[5,index%2,(index//2)%2],[7,*fs([.1731,.731,-.317,.137]),*fs([0,0,0,0]),1],[13,index,row['kind']]]
    commands += [[13,0,0],[13,1,1],[1,0],[2]];add('all settings paths and ordered read failures',commands)
    commands=[]
    for j in range(96):
        count=(-1,0,1,2,4,5)[j%6];detach=(-1,0,2)[j%3];parents=[-1,2,0,1]
        if j%11==0:parents[2]=99;count=4
        if j%12==0:count=4
        parent_count=4 if j%11==0 or j%12==0 else (4,1,0)[j%3]
        matrix_count=4 if j%11==0 or j%12==0 else (4,1,0)[(j//3)%3]
        parents=parents[:parent_count];matrices=[plant.matrix(j+k)for k in range(matrix_count)]
        commands += [[12,count&0xffffffff,detach&0xffffffff,len(parents),*[p&0xffffffff for p in parents],len(matrices),*fs(flatten(flatten(matrices)))]]
    add('full in-place hierarchy validation and forward-parent order',commands)
    prefix=[len(names),*flatten([text(n)for n in names]),len(cases)]
    raw=prefix+flatten([c['world']+c['edges']+[len(c['commands'])]+flatten(c['commands'])for c in cases])
    return struct.pack('<'+'I'*len(raw),*raw),cases,names

def preflight(raw,cases,names):
    words=struct.unpack('<'+'I'*(len(raw)//4),raw);at=0
    assert words[at]==len(names);at+=1
    for name in names:
        v=text(name);assert list(words[at:at+len(v)])==v;at+=len(v)
    assert words[at]==len(cases);at+=1;ranges=[]
    for c in cases:
        start=at;v=c['world']+c['edges']+[len(c['commands'])]+flatten(c['commands'])
        assert list(words[at:at+len(v)])==v;at+=len(v);ranges.append([start*4,at*4])
        for row in c['commands']:
            op=row[0];lengths={0:34,2:1,3:18,4:3,5:3,6:1,7:10,8:2,9:1,10:6,11:1,13:3,14:2,15:3,17:5,18:3,19:6,20:15}
            if op==1:assert len(row)==(4+row[2]if row[1]==4 else 2)
            elif op==12:assert len(row)==5+row[3]+16*row[4+row[3]]
            elif op==16:assert len(row)==(4 if row[2]else 3)
            else:assert len(row)==lengths[op],(op,len(row))
    assert at==len(words)
    for unit in UNITS:assert(CODE/(unit+'.cpp')).is_file(),unit
    return ranges

def build_reference(output,target,*,compile=True):
    output.mkdir(parents=True,exist_ok=True);plant.build_reference(output,target,compile=False)
    source=output/'reference-source';observed=output/'observed-source';crate=observed/'atelier-host'
    # frozen_sources reports its original location explicitly; verify it rather
    # than infer a host extraction path from live third-party sources.
    report=json.loads((output/'reference-provenance.json').read_text())
    if not source.exists():source=output/'original-source'
    assert source.exists(),source
    hp,he=plant.extraction(TESTS/'Reference/handplant_observer.rs','pub(super) fn run(')
    lp,le=plant.extraction(TESTS/'Reference/handplant_lifecycle_observer.rs','pub(super) fn run(')
    observer=TESTS/'Reference/render_pose_runtime_observer.rs'
    extensions={'physics/handplant.rs':b'\n'+hp+lp+observer.read_bytes(),
        'physics.rs':b'\npub(crate)fn migration_render_pose_run(a:&std::path::Path,f:&std::path::Path,i:&mut crate::Input,o:&mut crate::Output)->Result<(),String>{handplant::migration_render_pose_run(a,f,i,o)}\n',
        'physics/foot_physical_output.rs':FOOT_OBSERVER.encode(),
        'physics/skeleton_output.rs':OUTPUT_OBSERVER.encode()}
    for rel,extra in extensions.items():
        original=source/'crates/skate-host/src'/rel;p=crate/'src'/rel;p.write_bytes(original.read_bytes()+extra)
        row=report['staged_host_original_prefixes'][rel]
        row.update(append_sha256=hashlib.sha256(extra).hexdigest(),generated_sha256=digest(p))
    rel='crates/skate-core/src/physics/skeleton_output/wobble.rs';p=observed/rel;original=source/rel
    p.write_bytes(original.read_bytes()+CORE_OBSERVER)
    report['appended_core_observers'][rel]=dict(original_prefix_sha256=digest(original),generated_sha256=digest(p),observer_sha256=hashlib.sha256(CORE_OBSERVER).hexdigest())
    template=TESTS/'Reference/render_pose_runtime_probe.rs';shutil.copy2(template,crate/'src/migration_probe.rs')
    cargo=crate/'Cargo.toml';cargo.write_text(cargo.read_text().replace('name="plant-air-owner-reference"','name="render-pose-runtime-reference"'))
    for rel,sha in report['original_source_sha256'].items():
        assert digest(source/rel)==sha and(observed/rel).read_bytes()[:(source/rel).stat().st_size]==(source/rel).read_bytes(),rel
    for rel,row in report['staged_host_original_prefixes'].items():
        original=source/'crates/skate-host/src'/rel;p=crate/'src'/rel
        assert p.read_bytes()[:original.stat().st_size]==original.read_bytes()and digest(p)==row['generated_sha256'],rel
    binary=output/'render-pose-runtime-reference'
    if compile:
        subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(cargo),'--target-dir',str(target.resolve()),'--bin','render-pose-runtime-reference'],check=True)
        shutil.copy2(target.resolve()/'release/render-pose-runtime-reference',binary)
    report.update(extracted_observer_prefixes=[he,le,*report['extracted_observer_prefixes'][2:]],probe_sha256=digest(template),helper_sha256=digest(observer),binary_sha256=digest(binary)if compile else None,scope='Whole untouched host render_pose/skeleton_output/foot_physical_output and complete core output/board/foot/correction/wobble/IK. Only transport, explicit caller writes and read-only observers append. Full original GamePhysics/SkaterRuntime constructors per stream; no completed numeric callback is substituted.')
    (output/'reference-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return binary

def build_native(output,*,compile=True):
    snapshot=output/'native-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir();hashes={}
    for p in [*sorted(CODE.glob('*.h')),*[CODE/(u+'.cpp')for u in UNITS],TESTS/'Native/handplant_probe.cpp',TESTS/'Native/render_pose_runtime_probe.cpp']:
        shutil.copy2(p,snapshot/p.name);hashes[p.name]=digest(snapshot/p.name)
    prefix,proof=plant.extraction(TESTS/'Native/handplant_lifecycle_probe.cpp','int main(')
    (snapshot/'render_pose_owner_helpers.inc').write_bytes(prefix)
    binary=output/'render-pose-runtime-native'
    if compile:subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(u+'.cpp'))for u in UNITS],str(snapshot/'render_pose_runtime_probe.cpp'),'-o',str(binary)],check=True)
    for name,sha in hashes.items():assert digest(snapshot/name)==sha,name
    (output/'native-provenance.json').write_text(json.dumps(dict(immutable_native_sources=hashes,reused_helper_prefix=proof,units=UNITS,binary_sha256=digest(binary)if compile else None),indent=2)+'\n');return binary

class Reader(plant.numeric.Reader):
    def snapshot(self):
        assert self.word()==len(SECTIONS);out={};self.spans={}
        for section in SECTIONS:
            n=self.word();start=self.at;out[section]=self.take(n);self.spans[section]=[start,self.at]
        return out

def output_owner(raw):
    r=Reader(struct.pack('<'+'I'*len(raw),*raw));out=dict(bones=r.take(24),parents=[])
    for _ in range(24):out['parents'].append(r.word()if r.word()else None)
    out.update(inverse=r.take(384),board_bones=r.take(6),settings=r.take(4),wobble=r.take(6),deck=r.take(4),rest=r.word(),curves=r.take(65))
    assert r.at==len(raw);return out

def render_owner(raw):
    r=Reader(struct.pack('<'+'I'*len(raw),*raw));lo,hi=r.take(2);out=dict(generation=lo|(hi<<32));n=r.word();out['render']=r.take(n*16);n=r.word();out['animation']=r.take(n*12);out['publication']=r.take(31);out['wipeout']=r.word();assert r.at==len(raw);return out

def decode(raw,cases):
    r=Reader(raw);assert r.word()==len(cases);frames=[]
    for c in cases:
        assert r.word()==len(c['commands']);prior=r.snapshot();rows=[]
        for cmd in c['commands']:
            start=r.at;assert r.word()==cmd[0];error=r.status();extra=r.take(r.word());state=r.snapshot()
            rows.append(dict(operation=cmd[0],error=error,extra=extra,state=state,prior=prior,first_word=start,last_word=r.at,spans=r.spans.copy()));prior=state
        frames.append(rows)
    assert r.at==len(r.words);return frames

def coverage(frames,cases):
    counts=Counter();paths=Counter();render=set();feet=set();compressions=set();loaders={};fourth=set();unmapped=0
    for rows,c in zip(frames,cases):
        for row,cmd in zip(rows,c['commands']):
            op=cmd[0];counts[op]+=1;s=row['state'];old=row['prior'];out=output_owner(s['output_owner']);r=render_owner(s['render_owner']);prev=render_owner(old['render_owner']);f=s['foot_owner'];assert len(f)==32
            if op==2:
                compressions.add(tuple(row['extra']));paths['wipeout'if r['wipeout']else'not_wipeout']+=1
                assert r['publication'][3:19]==s['roots'][48:64]
                if row['error']:
                    assert row['error']in('Animation pose and hierarchy bone counts differ','physical pose output does not match the stock animation hierarchy')
                    assert r['generation']==prev['generation']and r['render']==prev['render']
                    assert r['animation']==prev['animation']
                    paths['failed_render_retains_skin_generation']+=1
                    if f!=old['foot_owner']or s['output_owner']!=old['output_owner']or s['physical_record']!=old['physical_record']:paths['earlier_physical_writes_before_render_failure']+=1
                else:
                    assert r['generation']==(prev['generation']+1)&0xffffffffffffffff
                    assert len(r['render'])==36*16 and r['animation']==prev['animation']
                    render.add(tuple(r['render']));feet.add(tuple(f));paths['successful_render']+=1
                    if prev['generation']==0xffffffffffffffff:paths['generation_wrap']+=1
                    fourth.update(r['render'][3::4])
                if out['deck'][0]:paths['sampled_wobble']+=1
            if op==9:
                assert f[:8]==[0]*8 and f[8:]==old['foot_owner'][8:];paths['reset_retains_settings_and_output']+=1
            if op==8:
                feet.add(tuple(f));fourth.update(f[14+3:22:4]);fourth.update(f[22+3:30:4])
                if c['label'].startswith('strict toe'):
                    paths['both_inside'if f[-2:]==[1,1]else'both_outside']+=1
                    assert f[-2:]in([1,1],[0,0])
            if op==13:
                index=cmd[1];loaders[index]=row['error']
                if row['error']:
                    assert s==old;paths['loader_failure_retains_all_owners']+=1
                elif cmd[2]==0:
                    assert f[:8]==[0]*8 and f[14:]==[0]*18;paths['fresh_feet']+=1
                else:
                    assert out['wobble']==[0,0,0,0,bits(1),1]and out['deck']==[0]*4;paths['fresh_output']+=1
            if op==11 and row['error']is None:
                ex=row['extra'];buffers=[];at=0
                for _ in range(4):
                    n=ex[at];at+=1;buffers.append(ex[at:at+n*16]);at+=n*16;assert n==36
                assert at==len(ex);before_globals,before_locals,globals_,locals_=buffers
                mapped=set(out['bones']);board=set(out['board_bones']);assert all(index<n for index in mapped|board)
                for bone in set(range(n))-mapped-board:
                    lanes=slice(bone*16,(bone+1)*16);assert before_globals[lanes]==globals_[lanes]and before_locals[lanes]==locals_[lanes];unmapped+=1
                paths['direct_mapped_publish']+=1
            if op==12 and row['error']is None and cmd[1]==4:paths['successful_forward_parent_hierarchy']+=1
            if op==12 and row['error']:
                name=row['error'].split(' ')[0];assert name in('ShortInput','ShortParents','InvalidParent');paths['hierarchy_'+name]+=1
            if op==19:
                assert row['error']is None;paths['actual_upstream_plant_ik']+=1
    assert paths['successful_render']>=390 and paths['failed_render_retains_skin_generation']==6
    assert paths['earlier_physical_writes_before_render_failure']>=3
    assert paths['generation_wrap']==6 and paths['wipeout']>60 and paths['not_wipeout']>200
    assert paths['sampled_wobble']>200 and paths['actual_upstream_plant_ik']==96
    assert paths['direct_mapped_publish']==384 and unmapped>300
    assert len(render)>300 and len(feet)>300 and len(compressions)>12 and len(fourth-{0})>8
    assert paths['both_inside']==6 and paths['both_outside']>=12
    assert paths['loader_failure_retains_all_owners']>=40
    assert all(paths['hierarchy_'+n]>0 for n in('ShortInput','ShortParents','InvalidParent'))
    assert paths['successful_forward_parent_hierarchy']>=7
    assert set(loaders)==set(range(len(loader_fixtures())))
    return dict(operations=dict(counts),paths=dict(paths),distinct_render_poses=len(render),distinct_foot_states=len(feet),distinct_compressions=len(compressions),distinct_fourth_lane_words=len(fourth),unmapped_bone_observations=unmapped,ordered_loader_results=loaders)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in('assets','samples','metadata','output','target-dir'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--preflight',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    samples=a.samples.resolve()/'native';fixtures,identity,stock=prepare(a.assets.resolve(),out);raw,cases,names=corpus(samples,stock);ranges=preflight(raw,cases,names)
    (out/'input.bin').write_bytes(raw);(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    reference=build_reference(out/'reference',a.target_dir,compile=not a.preflight);native=build_native(out,compile=not a.preflight)
    manifest=dict(cases=len(cases),commands=sum(len(c['commands'])for c in cases),input_bytes=len(raw),input_sha256=hashlib.sha256(raw).hexdigest(),units=len(UNITS),sampled_clips=len(names),loader_fixtures=len(loader_fixtures()),input_ranges=ranges)
    if a.preflight:
        (out/'preflight.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest,indent=2));return
    expected=subprocess.check_output([str(reference),str(a.assets.resolve()),str(fixtures)],input=raw)
    actual=subprocess.check_output([str(native),str(fixtures/'settings.native'),str(fixtures/'physics.native'),str(samples/'rig.skate'),identity,str(a.assets.resolve()),str(a.metadata.resolve()),str(samples),str(fixtures)],input=raw)
    (out/'reference.bin').write_bytes(expected);(out/'native.bin').write_bytes(actual);frames=decode(expected,cases)
    if expected!=actual:
        at=next((k for k,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)));row=next((r for rows in frames for r in rows if r['first_word']<=at//4<r['last_word']),None)
        section=next(((name,at//4-span[0])for name,span in(row['spans'].items()if row else[])if span[0]<=at//4<span[1]),None)
        failure=dict(byte=at,operation=row['operation']if row else'initial',section=section,reference_bytes=len(expected),native_bytes=len(actual));(out/'first-divergence.json').write_text(json.dumps(failure,indent=2)+'\n');raise AssertionError(failure)
    result=dict(passed=True,reference_revision=REFERENCE_REVISION,**manifest,bytes=len(expected),sha256=hashlib.sha256(expected).hexdigest(),coverage=coverage(frames,cases),scope='Complete original render_pose publication plus physical-pose/board/compression/wobble/correction/IK and foot outputs. Real stock clip evaluation, same current physical history and ordered late failure retention. Full caller coordinator and preceding physical state producers remain separate mandatory inputs; no original data parser is present in native production.')
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
