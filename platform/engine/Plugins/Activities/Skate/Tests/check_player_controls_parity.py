#!/usr/bin/env python3
"""Whole frozen physics/controls.rs owner/sampling/camera-remap parity.

Root must run compilation/execution through atelier.safety. --preflight only
generates input, audits original/native source identities and checks protocol.
Physical/camera observations are explicit caller records; no world or complete
frame producer is claimed by this focused controls proof.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import re
import shutil
import struct
import subprocess
from check_camera_runtime_parity import UNITS as CAMERA_UNITS
from check_gesture_parity import converter, PLUGIN
from check_input_parity import Record, from_bits
from reference_build import build_probe
from session_parity import REFERENCE_REVISION

CODE = PLUGIN/'Source/AtelierSkate/Private/Native'
UNITS = tuple(dict.fromkeys((*CAMERA_UNITS, 'BodyMass', 'AggregateMass', 'DeckGeometry', 'Input', 'InputIntentions',
                            'Gestures', 'GestureInputPublication', 'PlayerControls')))
ALIASES = {'atelier-host/src/physics/controls.rs': 'crates/skate-host/src/physics/controls.rs',
           'atelier-host/src/input/gesture_input.rs': 'crates/skate-host/src/input/gesture_input.rs'}
IDENTITY = [[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]
INTENTION_FILES = tuple('crates/skate-core/src/input/'+name+'_intentions.rs'
                        for name in ('riding','manual','wipeout','anticipation','trick'))


def intention_names():
    # Observation names come from the independent frozen producer source,
    # including conditional literal names. Candidate output is never used.
    return {name for relative in INTENTION_FILES
            for name in re.findall(r'"([A-Za-z][A-Za-z0-9_]*)"',
                                   (PLUGIN/'ThirdParty/skate-runtime'/relative).read_text())}


def corpus(sets):
    rng = random.Random(0x82898D20)
    names = sorted({p['name'] for group in sets for p in group['patterns']} | intention_names() | {
        'Trick','GestureSpeed','HoldPattern','LeftPush','RightPush','LeftAirGrab',
        'RightAirGrab','Unrelated','shared','Shared\0tail'})
    records, cases = [], []
    def add(op, label, write, **meta):
        w=Record(); w.word(op); write(w)
        records.append(bytes(w.data)); cases.append(dict(operation=op,label=label,
                                                        input_bytes=len(w.data),**meta))
    def rawmap(w, values, states=None):
        w.scalars(values); w.words(states if states is not None else [int(v!=0) for v in values])
    def reset(loaded): add(0,'loaded recognizers' if loaded else 'default without recognizers',lambda w:w.word(loaded))
    def metadata(flags=0, bumpers=(0,0), preferences=(0,0), ticks=0):
        def write(w):
            w.words((flags,*bumpers,*preferences,ticks&0xffffffff,ticks>>32)); w.words([0]*26)
        add(1,'source public control metadata and wrapping tick',write)
    def frame(w,category,state,object_,caps,dt,threshold,mode,present,basis):
        w.words((category,state,object_,caps)); w.scalars((dt,threshold));w.words((mode,present))
        w.scalars([v for axis in basis for v in axis])
    def update(values,category=500,state=500,object_=0,caps=0,dt=1/60,threshold=.1,
               mode=0,present=True,basis=IDENTITY,states=None,label='live update'):
        def write(w):frame(w,category,state,object_,caps,dt,threshold,mode,present,basis);rawmap(w,values,states)
        add(3,label,write,remap=category==500 and object_==0 and state!=503,
            present=bool(present),category=category,state=state,pole_bits=struct.unpack('<I',struct.pack('<f',basis[2][1]))[0])
    def replay(values,states=None):
        def write(w):
            rawmap(w,values,states); w.word(8)
            for kind,a in [(0,64),(1,64),(0,65),(1,65),(0,66),(1,66),(0,81),(1,81)]:w.words((kind,a))
        add(4,'reuse cached mapping against changed original action packet',write)
    def sample(values,category=100,state=100,present=False,basis=IDENTITY,mode=0):
        def write(w):
            frame(w,category,state,0,0,1/60,.1,mode,present,basis)
            w.words((rng.getrandbits(32),rng.getrandbits(32),rng.randrange(2)));w.scalars(values)
        add(7,'actual source sample system incl gesture scheduling',write,
            remap=category==500 and state!=503,present=bool(present),state=state)
    reset(False)
    for category,state,object_ in [(100,100,0),(500,500,0),(500,501,0),(500,502,0),(500,503,0),(500,500,1),(400,400,0)]:
        for present in (False,True):
            update([.3,-.7]+[0.]*16,category,state,object_,present=present,label='every gate and missing-camera result')
            replay([-.8,.9]+[.25]*16,states=[3]*18)
    metadata(ticks=0xffffffffffffffff)
    update([.5,-.25]+[0.]*16,present=True)
    replay([-.25,.5]+[.75]*16,states=[0]*18)
    # A plain update clears only cached axes; source offboard_direction remains.
    add(2,'plain update clears cached axes but retains public direction',
        lambda w:(w.scalars((1/60,.1)),w.word(0),rawmap(w,[.7,.1]+[0.]*16)),expect_retained_direction=True)
    replay([-.9,.8]+[.5]*16,states=[7]*18)
    sample([0.]*18,category=500,state=500,present=False)
    sample([0.]*18,category=500,state=503,present=False)
    # Actual remap pole branch boundary, including signed zero and degenerate
    # input axes. Full original arithmetic produces the expected words.
    boundary=[from_bits(b) for b in (0,0x80000000,0x3f7d70a3,0x3f7d70a4,0x3f7d70a5,
                                    0xbf7d70a3,0xbf7d70a4,0xbf7d70a5,0x3f800000,0xbf800000)]
    for pole in boundary:
        for x,z in [(1.,0.),(0.,1.),(-1.,-1.),(-0.,0.)]:
            basis=[[.8,.2,-.3],[.1,.9,.2],[.45,pole,.72]]
            update([x,z]+[0.]*16,basis=basis,label='f32 pole comparison and signed input boundary')
            replay([-.1,.2]+[0.]*16,states=[255]*18)
    for tick in range(768):
        if tick%96==0:
            reset(tick%192==0);metadata(flags=(tick//96)*0x1018,
                    bumpers=(tick//96%2,tick//192%2),preferences=(tick//96%2,tick//192%2),ticks=tick)
        values=[rng.uniform(-1,1) for _ in range(18)]
        if tick%17==0:values[0]=from_bits(0x80000000);values[1]=0.
        category=(100,500,500,500,500,400,0)[tick%7]
        state=(500,501,502,503,100)[tick%5];object_=int(tick%23==0)
        basis=[[rng.uniform(-1,1) for _ in range(3)] for _ in range(3)]
        if tick%13==0:basis[2][1]=rng.choice(boundary)
        update(values,category,state,object_,caps=rng.getrandbits(32),dt=(1/60,0.,-.02,.1)[tick%4],
               threshold=(.1,.5,0.,1.)[tick%4],present=tick%11!=0,basis=basis,
               states=[rng.randrange(4) for _ in range(18)],label='generated retained gate/camera/control history')
        if tick%3==0:replay([rng.uniform(-1,1) for _ in range(18)],states=[rng.randrange(256) for _ in range(18)])
        if tick%29==0:add(6,'encoded AG alias prior to next clear',lambda w:(w.raw('Shared\0tail'),w.word(0x80000000)))
        if tick%31==0:add(5,'default/loaded retained gesture owner',lambda w:w.words((tick%3,state)))
    # Preserve the actual sample/update/listener chain on authored PAT streams.
    authored=0
    for group in sets:
        selected=group['patterns'][:2]
        hold=next((p for p in group['patterns'] if p['name'] in {'Kickflip','Heelflip','N_Kickflip','N_Heelflip'}),None)
        if hold is not None and hold not in selected:selected.append(hold)
        for pattern in selected:
            authored+=1;reset(True);metadata()
            values=[0.]*18;sample(values)
            slot=0 if group['stick']==0 else 3
            def pose(point):
                a=[0.]*18;a[slot]=point[0];a[slot+1]=-point[1];return a
            for _ in range(30):sample(pose(pattern['points'][0]))
            for point in pattern['points'][1:]:
                for _ in range(2):sample(pose(point))
            for _ in range(12):sample(pose(pattern['points'][-1]))
            for _ in range(4):sample(values)
    header=Record();header.word(len(names))
    for n in names:header.raw(n)
    header.word(len(records));offset=len(header.data)
    for i,(record,case) in enumerate(zip(records,cases)):
        case['command']=i;case['input_offset']=offset;offset+=len(record)
    return bytes(header.data)+b''.join(records),cases,names,authored


class Reader:
    def __init__(self,data):self.data=data;self.at=0
    def word(self):v,=struct.unpack_from('<I',self.data,self.at);self.at+=4;return v
    def string(self):n=self.word();v=self.data[self.at:self.at+n].decode();self.at+=n;return v


def audit_input(data,cases,names):
    r=Reader(data);assert r.word()==len(names)
    assert [r.string() for _ in names]==names
    assert r.word()==len(cases)
    counts=Counter()
    def words(n):
        result=[r.word() for _ in range(n)];return result
    def frame():
        values=words(17);assert values[7] in (0,1)
    def rawmap():words(36)
    for i,case in enumerate(cases):
        begin=r.at;assert begin==case['input_offset'] and i==case['command']
        op=r.word();assert op==case['operation'];counts[op]+=1
        if op==0:assert r.word() in (0,1)
        elif op==1:words(33)
        elif op==2:words(3);rawmap()
        elif op==3:frame();rawmap()
        elif op==4:
            rawmap()
            for _ in range(r.word()):
                kind,action=words(2);assert kind in (0,1) and 64<=action<=81
        elif op==5:words(2)
        elif op==6:r.string();words(1)
        elif op==7:frame();words(2);assert r.word() in (0,1);words(18)
        else:raise AssertionError(op)
        assert r.at-begin==case['input_bytes']
    assert r.at==len(data)
    return dict(roundtrip_bytes=r.at,commands_by_operation=counts,
                query_names=len(names),frozen_intention_query_names=sorted(intention_names()))


def coverage(data,cases,names):
    r=Reader(data);counts=Counter();intent_names=set();ticks=set();directions=set();prior=None;replays=set()
    for case in cases:
        assert r.word()==case['operation'];ok=r.word();error=r.string()
        extra=[r.word() for _ in range(r.word())]
        trace=[(r.word(),r.word()) for _ in range(r.word())]
        controller=[r.word() for _ in range(26)];present=r.word();direction=tuple(r.word() for _ in range(4)) if present else None
        tick=r.word()|(r.word()<<32);ticks.add(tick)
        metadata=[r.word() for _ in range(5)]
        intentions=[(r.string(),r.word()) for _ in range(r.word())];intent_names.update(n for n,_ in intentions)
        assert all(n in names for n,_ in intentions), 'Unobserved original AG intent key'
        map_size=r.word();values={}
        for n in names:
            if r.word():values[n]=r.word()
        counts['nonempty_AG']+=map_size>0;counts['Trick']+='Trick' in values;counts['HoldPattern']+='HoldPattern' in values
        if direction is not None:directions.add(direction)
        if case['operation'] in (3,7):
            should_fail=case['remap'] and not case['present']
            assert bool(ok)!=should_fail
            if should_fail:
                prefix='Offboard controller publication: ' if case['operation']==7 else ''
                assert error==prefix+'Native offboard input requires a completed presentation camera frame'
                counts['sample_panic' if case['operation']==7 else 'lower_error']+=1
                assert trace==[]
                if prior is not None:assert (controller,direction,tick,metadata,intentions,values)==prior
            else:
                assert not error and bool(present)==case['remap'];counts['remap' if case['remap'] else 'bypass']+=1
                if case['operation']==3 and case['remap']:assert trace[:2]==[(0,64),(0,65)]
        if case['operation']==4:
            assert len(extra)==8;replays.add(tuple(extra));counts['cached_replay']+=(0,64) not in trace;counts['plain_replay']+=(0,64) in trace
        if case.get('expect_retained_direction'):assert prior and direction==prior[1] and present
        counts['tick_wrap']+=tick==0 and prior is not None and prior[2]==0xffffffffffffffff
        prior=(controller,direction,tick,metadata,intentions,values)
    assert r.at==len(data)
    assert all(counts[x]>0 for x in ['remap','bypass','lower_error','sample_panic','cached_replay','plain_replay','tick_wrap','Trick','HoldPattern'])
    assert len(directions)>24 and len(replays)>24 and len(intent_names)>12
    return dict(counts=counts,distinct_directions=len(directions),distinct_replays=len(replays),ordered_intention_names=sorted(intent_names))


def stage_native(output):
    source=output/'native-source';source.mkdir(exist_ok=True)
    files=sorted(CODE.glob('*.h'))+[CODE/(n+'.cpp') for n in UNITS]
    provenance=[]
    for p in files:
        raw=p.read_bytes();(source/p.name).write_bytes(raw)
        provenance.append(dict(path=p.relative_to(PLUGIN).as_posix(),sha256=hashlib.sha256(raw).hexdigest()))
    probe=PLUGIN/'Tests/Native/player_controls_probe.cpp';raw=probe.read_bytes();target=source/probe.name;target.write_bytes(raw)
    (output/'native-source-provenance.json').write_text(json.dumps(dict(files=provenance,probe_sha256=hashlib.sha256(raw).hexdigest()),indent=2)+'\n')
    return source,target


def audit_originals():
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip())
    identities={}
    for relative in (*ALIASES.values(),*INTENTION_FILES):
        path=PLUGIN/'ThirdParty/skate-runtime'/relative;raw=path.read_bytes()
        frozen=subprocess.check_output(['git','show',REFERENCE_REVISION+':'+path.relative_to(root).as_posix()],cwd=root)
        assert raw==frozen, 'Original source differs from pinned revision: '+relative
        identities[relative]=hashlib.sha256(raw).hexdigest()
    return identities


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--target-dir',type=Path);p.add_argument('--preflight',action='store_true');a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    for name in ['result.json','first-divergence.json']:(out/name).unlink(missing_ok=True)
    sets=converter.gesture_sets(a.assets/'private/stock/data/joystick');inputs,cases,names,authored=corpus(sets)
    protocol=audit_input(inputs,cases,names)
    (out/'input.bin').write_bytes(inputs);(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    (out/'settings.native').write_bytes(converter.encode_settings(a.assets/'private/stock/skater-collections.json'))
    (out/'gestures.native').write_bytes(converter.encode_gestures(sets))
    source,probe=stage_native(out)
    originals=audit_originals()
    owned=['Source/AtelierSkate/Private/Native/PlayerControls.h','Source/AtelierSkate/Private/Native/PlayerControls.cpp','Tests/Native/player_controls_probe.cpp','Tests/Reference/player_controls_probe.rs','Tests/check_player_controls_parity.py']
    owned_hashes={relative:hashlib.sha256((PLUGIN/relative).read_bytes()).hexdigest() for relative in owned}
    report=dict(preflight_only=a.preflight,commands=len(cases),authored_sequences=authored,input_bytes=len(inputs),input_sha256=hashlib.sha256(inputs).hexdigest(),original_sources=originals,owned_file_sha256=owned_hashes,native_TUs=len(UNITS),input_protocol=protocol,observations='All26controllerwords,public direction/tick/metadata,ordered intents,every catalog AG value and exact underlying action callback order; hidden gesture/cached-axis lifetime exercised through authored continuation and lazy replay.',boundary='Completed physical/camera values are explicit canonical caller records. This proves controls live methods, stock construction and original sample system, not upstream physical/camera/frame production. Malformed original JSON/PAT construction versus converted-native constructor error/read ordering remains outside this proof; accepted GestureInputPublication loader is unchanged.')
    (out/'freeze.json').write_text(json.dumps(report,indent=2)+'\n')
    if a.preflight:print(json.dumps(report,indent=2));return
    if a.target_dir is None:p.error('--target-dir required outside --preflight')
    reference=build_probe(out,'player-controls-reference',PLUGIN/'Tests/Reference/player_controls_probe.rs',a.target_dir,bevy=True,extra_sources=ALIASES)
    native=out/'player-controls-native'
    subprocess.run(['clang++','-std=c++17','-O2','-fno-exceptions','-fno-rtti','-ffp-contract=off','-fno-fast-math','-Wall','-Wextra','-Werror','-I',str(source),*(str(source/(n+'.cpp')) for n in UNITS),str(probe),'-o',str(native)],check=True)
    expected=subprocess.check_output([str(reference),str(a.assets)],input=inputs);actual=subprocess.check_output([str(native),str(out/'settings.native'),str(out/'gestures.native')],input=inputs)
    (out/'reference.bin').write_bytes(expected);(out/'native.bin').write_bytes(actual)
    if expected!=actual:
        first=next((i for i,(x,y) in enumerate(zip(expected,actual)) if x!=y),min(len(expected),len(actual)))
        mismatch=dict(passed=False,first_byte=first,reference_length=len(expected),native_length=len(actual),reference_hex=expected[max(0,first-20):first+40].hex(),native_hex=actual[max(0,first-20):first+40].hex());(out/'first-divergence.json').write_text(json.dumps(mismatch,indent=2)+'\n');raise AssertionError(mismatch)
    result=dict(passed=True,commands=len(cases),authored_sequences=authored,exact_bytes=len(actual),sha256=hashlib.sha256(actual).hexdigest(),coverage=coverage(expected,cases,names),reference_provenance='player-controls-reference-provenance.json',native_provenance='native-source-provenance.json',limitations=report['boundary'])
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
