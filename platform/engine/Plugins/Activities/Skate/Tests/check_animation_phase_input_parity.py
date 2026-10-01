#!/usr/bin/env python3
"""Entire actual host animation_phase_packet.rs and stock preference loading.

All records, reset/republish state and failure retention execute the unchanged
original host/core. Only the coordinator may compile/run through the guard.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import player_input_protocol as protocol
import check_animation_trees_parity as trees
import check_ground_control_settings_parity as settings_probe
from check_animation_playback_parity import Stream,bits
from check_gesture_parity import PLUGIN,converter
from reference_build import build_probe
HOST='crates/skate-host/src/physics/animation_phase_packet.rs'
MODES=('easy','normal','hardcore','motorized','test')

def pose(tick,count=2,extent=3):
    def matrix(seed):return [[1,.125*seed,.317,0],[0,1,.517,0],[.731,0,1,0],[seed*.137,.317,.731,1]]
    return dict(bone_count=count,hierarchy=[matrix(tick+j) for j in range(extent)],local=[matrix(tick+j+3) for j in range(extent)],timestep=(.0,1/60,.033,-.125)[tick%4],foot_surface_ids=[0xabcdef01+tick,0xffffffff-tick],flags=(0,0xffffffff,1<<(tick%32))[tick%3],board_flipped=tick%2==0,mirrored=tick%3==0,riding_switch=tick%4==0,riding_fakie=tick%5==0,weight_forwards=tick%3!=0,regular_stance=tick%2!=0,air_dismount_revert_frames=tick-7)

def corpus(defs):
    cases=[]
    for mode_id,mode in enumerate(MODES):
        reset=protocol.default('AnimationAdditionalResetFields',defs,mode_id);profile=protocol.default('AnimationProfile',defs,mode_id);profile.update(physics_mode=mode_id,truck_tightness=.137,wheel_hardness=.731,gesture_selections=[0,1,7,0xffffffff],ignore_respawn_reset_button=255);commands=[dict(op=0,value=reset),dict(op=1,value=profile)]
        for t in range(16):
            commands.extend([dict(op=2,pose=pose(t),actor_flags=(0,4,0xffffffff)[t%3]),dict(op=3,transform=protocol.default('RawMatrix',defs,t),byte=(0,1,2,255)[t%4]),dict(op=4),dict(op=2,pose=pose(t+1),actor_flags=0)])
        commands.extend([dict(op=5,mode='undefined'),dict(op=5,mode=MODES[(mode_id+1)%5]),dict(op=2,pose=pose(21),actor_flags=4)]);cases.append(dict(mode=mode,commands=commands,label='retained reset reply and republish history'))
    for count,extent in ((0,3),(1,3),(3,3),(4,3),(0x80000000,3),(0xffffffff,3)):
        cases.append(dict(mode='normal',label='original pose allocation/reset boundary',commands=[dict(op=0,value=protocol.default('AnimationAdditionalResetFields',defs)),dict(op=2,pose=pose(1,count,extent),actor_flags=0),dict(op=4),dict(op=2,pose=pose(2),actor_flags=0)]))
    for flag in range(32):
        p=pose(flag);p['flags']=1<<flag;cases.append(dict(mode='normal',label='single packet flag publication',commands=[dict(op=2,pose=p,actor_flags=0)]))
    cases.append(dict(mode='undefined',label='undefined profile',commands=[]));return cases

def encode_pose(w,p):
    w.word(p['bone_count'])
    for name in ('hierarchy','local'):
        w.word(len(p[name]))
        for matrix in p[name]:
            for column in matrix:
                for v in column:w.float(v)
    w.float(p['timestep']);w.word(p['foot_surface_ids'][0]);w.word(p['foot_surface_ids'][1]);w.word(p['flags'])
    for name in ('board_flipped','mirrored','riding_switch','riding_fakie','weight_forwards','regular_stance','air_dismount_revert_frames'):w.word(p[name])

def encode(cases,defs):
    w=Stream();w.word(len(cases))
    for c in cases:
        w.string(c['mode']);w.word(len(c['commands']))
        for s in c['commands']:
            op=s['op'];w.word(op)
            if op in (0,1):protocol.encode(w,'AnimationAdditionalResetFields' if op==0 else 'AnimationProfile',s['value'],defs)
            elif op==2:encode_pose(w,s['pose']);w.word(s['actor_flags'])
            elif op==3:protocol.encode(w,'RawMatrix',s['transform'],defs);w.word(s['byte'])
            elif op==5:w.string(s['mode'])
    return bytes(w.data)

def read_pose(r,defs):
    p=dict(bone_count=r.word());p['hierarchy']=[[[r.word() for _ in range(4)] for _ in range(4)] for _ in range(r.word())];p['local']=[[[r.word() for _ in range(4)] for _ in range(4)] for _ in range(r.word())];p['timestep']=r.word();p['foot_surface_ids']=[r.word(),r.word()];p['flags']=r.word()
    for name in ('board_flipped','mirrored','riding_switch','riding_fakie','weight_forwards','regular_stance','air_dismount_revert_frames'):p[name]=r.word()
    return p

def snapshot(r,defs):
    end=r.at+4+r.word()*4;s=dict(profile=r.value('AnimationProfile',defs),reset=r.value('AnimationAdditionalResetFields',defs),publication=r.value('AnimationPacketFields',defs),external=r.value('ExternalPhysicsInput',defs),mirrored=r.word(),weight_forwards=r.word(),flags=r.word(),packet=r.value('AnimationInputPacket',defs),pose=read_pose(r,defs));assert r.at==end;return s

def decode(data,cases,defs):
    r=protocol.Reader(data);out=[]
    for ci,c in enumerate(cases):
        assert r.word()==ci;loaded=r.word();error=r.string();initial=snapshot(r,defs) if loaded else None;rows=[]
        for n,command in enumerate(c['commands']):
            assert [r.word(),r.word(),r.word()]==[ci,n,command['op']];rows.append(dict(ok=r.word(),error=r.string(),snapshot=snapshot(r,defs)))
        out.append(dict(loaded=loaded,error=error,initial=initial,rows=rows))
    assert r.at==len(data);return out

def coverage(frames,cases):
    ops=Counter();errors=Counter();replies=0;republish=0;profiles=set();flags=set();resets=0;failures=0;bytes64=set()
    for frame,c in zip(frames,cases):
        if not frame['loaded']:errors[frame['error']]+=1;continue
        s=frame['initial'];assert s['reset']['requested_physics_mode']==1 and s['publication']['matrix_10704'][3]==[0]*4;assert s['profile']['truck_tightness']==bits(.7) and s['profile']['wheel_hardness']==bits(.7);previous=s;profiles.add(s['profile']['physics_mode'])
        for row,command in zip(frame['rows'],c['commands']):
            op=command['op'];ops[op]+=1;s=row['snapshot'];packet=s['packet'];publication=s['publication'];assert packet['publication']==publication and packet['external_physics_10512']==s['external'];assert packet['use_external_physics_10688']==packet['external_physics_flag_10689']==0;assert s['external']==dict(vectors=[[0]*4 for _ in range(10)],flags=0)
            if row['error']:errors[row['error']]+=1
            if op==2:
                assert row['ok'] and s['flags']==command['pose']['flags']&~((1<<24)|(1<<22));assert packet['flags_10932']==s['flags'];assert publication['matrix_10704'][3]==[0]*4 and publication['flags_10375_10496_10784']==[0,0,0];assert s['reset']['actor_flag_1904_bit23']==0;assert packet['suppress_transition_10376']==int(bool(s['profile']['suppress_transition']) or bool(command['actor_flags']&4));flags.add(s['flags']);republish+=1
            elif op==3:
                assert publication['matrix_10704']==command['transform'] and publication['byte_10768']==command['byte'] and publication['flags_10375_10496_10784'][2]==1;bytes64.add(publication['byte_10768']);replies+=1
            elif op==4:
                assert s['publication']==previous['publication']
                if row['ok']:assert s['reset']['requested_physics_mode']==1 and s['reset']['compression']==bits(.5);resets+=1
                else:assert row['error']=='RangeOutsideAllocation' and s==previous;failures+=1
            elif op==5 and not row['ok']:assert s==previous
            previous=s
    assert set(ops)==set(range(6)) and profiles==set(range(5)) and replies>0 and republish>0 and resets>0 and failures>0 and len(flags)>24 and bytes64=={0,1,2,255},(ops,profiles,replies,republish,resets,failures,len(flags),bytes64)
    assert 'Undefined player physics profile undefined' in errors
    return dict(opcodes=dict(ops),profile_modes=sorted(profiles),external_reset_replies=replies,republishes=republish,resets=resets,retained_allocation_failures=failures,distinct_published_flags=len(flags),external_reset_bytes=sorted(bytes64),errors=dict(errors))

def prepare_sources(output,defs,sources):
    cpp,rust=protocol.helpers(defs);c=output/'animation-phase-input-native.cpp';r=output/'animation-phase-input-reference.rs';c.write_text((PLUGIN/'Tests/Native/animation_phase_input_probe.cpp').read_text().replace('// GENERATED_PROTOCOL',cpp));host=trees.source_at_reference(HOST);r.write_text((PLUGIN/'Tests/Reference/animation_phase_input_probe.rs').read_text().replace('// GENERATED_PROTOCOL',rust).replace('// ORIGINAL_HOST',host));(output/'source-provenance.json').write_text(json.dumps(dict(host=HOST,host_sha256=hashlib.sha256(host.encode()).hexdigest(),declarations={p:hashlib.sha256(s.encode()).hexdigest() for p,s in sources.items()}),indent=2)+'\n');return c,r

def build_native(output,probe):
    live=PLUGIN/'Source/AtelierSkate/Private/Native';n=output/'native-source';binary=output/'animation-phase-input-native';sources=['NameId','Settings','StockSettingsReader','NativeMath','AnimationName','AnimationPublication','AnimationPhaseInput']
    if n.exists():shutil.rmtree(n)
    n.mkdir()
    for path in list(live.glob('*.h'))+[live/(s+'.cpp') for s in sources]:shutil.copy2(path,n/path.name)
    copied_probe=n/probe.name;shutil.copy2(probe,copied_probe)
    (output/'native-provenance.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(n.iterdir())},indent=2)+'\n')
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(n),*[str(n/(s+'.cpp')) for s in sources],str(copied_probe),'-o',str(binary)],check=True);return binary

def failures(original):
    out=[];queries=[('anim_skitching','default','LongSkitchIntoReachTime','float'),('anim_motion','pushing','disable_push_brake_at_slope','float')]
    for n,q in enumerate(queries):
        data=copy.deepcopy(original)
        for remaining in queries[n:]:settings_probe.mutate(data,remaining,settings_probe.invalid(remaining))
        out.append((data,settings_probe.expected_invalid(q)))
        for payload in ('7fc00001','7f800000'):
            data=copy.deepcopy(original);settings_probe.mutate(data,q,dict(type='EA::Reflection::Float',data=payload));out.append((data,'Non-finite stock float '+'/'.join(q[:3])))
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--target-dir',type=Path,required=True);a=p.parse_args();output=a.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json'):(output/name).unlink(missing_ok=True)
    defs,sources=protocol.declarations(extra=True);cases=corpus(defs);blob=encode(cases,defs);(output/'input.bin').write_bytes(blob);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');cpp,rust=prepare_sources(output,defs,sources);reference=build_probe(output,'animation-phase-input-reference',rust,a.target_dir);native=build_native(output,cpp);settings=output/'settings.native';settings.write_bytes(converter.encode_settings(a.assets/'private/stock/skater-collections.json'));expected=subprocess.check_output([str(reference),str(a.assets.resolve())],input=blob);actual=subprocess.check_output([str(native),str(settings)],input=blob);(output/'reference.bin').write_bytes(expected);(output/'native.bin').write_bytes(actual);frames=decode(expected,cases,defs);(output/'reference-trace.json').write_text(json.dumps(frames,indent=2)+'\n')
    if expected!=actual:
        at=next((i for i,(x,y) in enumerate(zip(expected,actual)) if x!=y),min(len(expected),len(actual)));(output/'first-divergence.json').write_text(json.dumps(dict(byte=at),indent=2)+'\n');raise AssertionError(f'Actual animation phase packet differs at byte {at}')
    proof=coverage(frames,cases);original=json.loads((a.assets/'private/stock/skater-collections.json').read_text());negative=[]
    for n,(data,error) in enumerate(failures(original)):
        root=output/f'failure-{n}';path=root/'private/stock/skater-collections.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data));settings.write_bytes(converter.encode_settings(path));case=[dict(mode='normal',commands=[],label='first failed stock load')];blob=encode(case,defs);x=subprocess.check_output([str(reference),str(root)],input=blob);y=subprocess.check_output([str(native),str(settings)],input=blob);assert x==y,('failed profile load',n);f=decode(x,case,defs)[0];assert not f['loaded'] and f['error']==error,(n,f,error);negative.append(dict(fixture=n,error=error))
    result=dict(passed=True,histories=len(cases),commands=sum(len(c['commands']) for c in cases),output_bytes=len(expected),output_sha256=hashlib.sha256(expected).hexdigest(),coverage=proof,settings_failures=negative,comparison='Entire actual pinned host animation_phase_packet.rs profile/load/new/publish/external reply/borrowed packet; unchanged core reset with complete retained storage and failed extents.',limitations='Host explicitly keeps external physics/impulse providers inactive; those source constants are preserved. Overall actor/skeleton/ground scheduler remains separately owned.');(output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__':main()
