#!/usr/bin/env python3
"""Full original MotionHost CharacterGesture/EndGesture/Shove lifecycle parity.

Builds/probes run only by the parent under atelier.safety. Real stock gesture
clips expose catalog and stage transitions; applied parameter observers expose
height/direction. Source modules remain byte-identical in the independent oracle.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
from check_gesture_parity import converter, PLUGIN
from check_graph_parity import attribute, element, original_graph
from check_input_parity import Record, fbits, from_bits
from check_animation_trees_parity import converter as metadata_converter, name
from check_motion_animation_parity import validate_fixture_attributes
from motion_reference_build import build_probes

CHANNELS = ('GestureBoth', 'GestureRight', 'GestureLeft', 'SkitchAntic', 'Shove', 'RetrieveBoard', 'WipeoutPushOff')
PROOFS = ('GESTURE_PROOF_HEIGHT', 'GESTURE_PROOF_ANGLE')


def fixture():
    configs = [element('behaviour', 'CharacterGesture'), element('behaviour', ' CharacterGesture '), element('behaviour', 'EndGesture')]
    for i in range(2):
        configs.append(element('behaviour', 'Shove', [attribute('Selection', f'GESTURE_SHOVE_{i}'), attribute('Antic', f'GESTURE_ANTIC_{i}'),
            *([attribute('SelectionBrd', 'GESTURE_SHOVE_BOARD'), attribute('AnticBrd', 'GESTURE_ANTIC_BOARD')] if i == 0 else [])]))
    return element('state', 'root', children=configs), configs


def fixture_metadata():
    data = dict(version=1, source_bank='GestureFixture.abin', source_sha256='d'*64, source_bytes=1000000,
        clips=[], phase_blends=[], blend_spaces=[], selectors=[], selection_spaces=[], unsupported_trees=[])
    def clip(n, pairs=(), looping=True):
        offset = 48 + len(data['clips'])*4096
        pairs = sorted(pairs, key=lambda item:tuple(name(item[0])))
        attrs = [dict(name=n, type_id=0, begin_bits=fbits(-1), end_bits=fbits(-1), payload_words=[fbits(v)], source_offset=offset+128+i*128) for i,(n,v) in enumerate(pairs)]
        data['clips'].append(dict(name=n, source_offset=offset, fps_bits=fbits(30), frames_bits=fbits(13), base_speed_bits=fbits(1), flags_word=0x10000000 if looping else 0, attributes=attrs))
    for i, (param, proof, tree, lo, hi) in enumerate((('GSTRDISTTOCOG', PROOFS[0], 'GESTURE_HEIGHT_OBSERVER', -2., 2.), ('SHOVEDIRECTION', PROOFS[1], 'GESTURE_ANGLE_OBSERVER', 0., 360.))):
        children = []
        for j,v in enumerate((lo,hi)):
            c = f'{tree}_{j}'
            children.append(c)
            clip(c, [(param,v),(proof,v)])
        data['phase_blends'].append(dict(name=tree, source_offset=100000+i*4096, parameter=param, children=children))
    for n in ('GESTURE_EMPTY', 'GESTURE_SHOVE_0', 'GESTURE_SHOVE_1', 'GESTURE_SHOVE_BOARD', 'GESTURE_ANTIC_0', 'GESTURE_ANTIC_1', 'GESTURE_ANTIC_BOARD'):
        clip(n, looping=False)
    validate_fixture_attributes(data)
    return data


def original_catalog():
    path = PLUGIN/'ThirdParty/skate-runtime/crates/skate-host/src/graph_host/motion_character_gesture.rs'
    names = re.findall(r'"([A-Z0-9_]+)"',path.read_text().split('const NAMES:')[1])
    assert len(names) == 37
    return names


def corpus():
    rows = []
    def add(index, phase=1, *, allocate=0, clear=0, seed=0, available=127, hands=(0,0), keep=0, category=0, board=1, ground=1, offboard=0, suppress=0, bypass=0,
            selections=(0,1,2,3), interaction=0, biped=0, board_ground=0, mirror=0, height=.7, dt=.05, direction=(1.,0.,1.,0.), intents=None):
        rows.append(dict(index=index, phase=phase, allocate=allocate, clear=clear, seed=seed, available=available, hands=hands, keep=keep, category=category, board=board, ground=ground, offboard=offboard,
            suppress=suppress,bypass=bypass,selections=selections,interaction=interaction,biped=biped,board_ground=board_ground,mirror=mirror,height=height,dt=dt,direction=direction,intents=intents or {}))
    # Catalog IDs and all hand variants use actual stock INTO clips.
    starts = ('GestureUpStart','GestureDownStart','GestureLeftStart','GestureRightStart')
    helds = ('GestureUpHeld','GestureDownHeld','GestureLeftHeld','GestureRightHeld')
    for id in range(37):
        for hand in range(3):
            direction = id%4
            selections = list((4,5,6,7));selections[direction] = id
            hands = ((0,0),(0,1),(1,0))[hand]
            add(2, 0, clear=1)
            add(id%2, 0, allocate=1, hands=hands, selections=selections)
            add(id%2, hands=hands, selections=selections, height=(id%7)*.2, intents={starts[direction]:0.,helds[direction]:0.})
            add(id%2, hands=hands, selections=selections, height=(id%7)*.2, intents={helds[direction]:0.})
            add(2, 0)
            add(2, 1, dt=.2)
    # Entry/cycle/exit are source sequences, with retained publication after exit.
    for hand in range(3):
        hands=((0,0),(0,1),(1,0))[hand]
        add(2,0,clear=1)
        add(0,0,allocate=1)
        for tick in range(52):
            intents={'GestureDownHeld':0.} if tick<25 else {}
            if tick==0:intents['GestureDownStart']=0.
            add(0,hands=hands,selections=(0,0,0,0),height=(tick%5)*.25,offboard=tick%7==0,dt=.1,intents=intents)
        add(2,0)
        add(2,2,dt=.2)
    # Missing owner publication order, selection errors and original start gates.
    for available in (126,125,123,119,63,127):
        add(2,0,clear=1)
        add(0,0,allocate=1)
        add(0,available=available,selections=(37,38,39,40) if available==127 else (0,1,2,3),intents={'GestureDownStart':0.})
    for case in range(14):
        add(2,0,clear=1)
        add(0,0,allocate=1)
        values=dict(seed=1 if case==0 else 2 if case==1 else 3 if case==2 else 0,hands=(1,1) if case==3 else (0,0),
            category=6 if case in (4,5) else 7 if case in (6,7) else 0,ground=0 if case in (4,5,6,7) else 1,board=case not in (5,7),
            suppress=case==8,bypass=case==10)
        intents={'GestureUpStart':0.,'GestureDownStart':0.,'GestureLeftStart':0.,'GestureRightStart':0.} if case==11 else {'GestureUpStart':0.}
        if case in (9,10):intents['ForceBrake']=0.
        if case==12:intents['OB_Mount']=0.
        if case==13:intents['OB_Dismount']=0.
        add(0,**values,intents=intents)
    # Switch hand occupancy, direction-held fallback and fresh owner allocation.
    add(2,0,clear=1);add(0,0,allocate=1)
    for intents,hands,clear in (({'GestureLeftStart':0.,'GestureLeftHeld':0.},(0,0),0),({'GestureDownHeld':0.},(0,0),0),({'GestureDownHeld':0.},(1,0),0),({'GestureRightStart':0.},(1,0),0),({},(1,0),1)):
        add(0,intents=intents,hands=hands,clear=clear)
    add(0,allocate=1,intents={'GestureRightStart':0.})
    # Shove zero-vector/quadrants/signed-zero/NaN and mirror arithmetic.
    directions=((0.,0.,0.,0.),(-0.,0.,-0.,0.),(1.,0.,0.,0.),(-1.,0.,0.,0.),(0.,0.,1.,0.),(0.,0.,-1.,0.),(1.,0.,1.,0.),(-1.,0.,1.,0.),(1.,0.,-1.,0.),(-1.,0.,-1.,0.),
        (from_bits(1),0.,1.,0.),(1.,0.,from_bits(1),0.),(from_bits(0x7fc12345),0.,1.,0.),(1.,0.,from_bits(0x7fc12345),0.),(float('inf'),0.,1.,0.),(1.,0.,float('inf'),0.))
    for index in (3,4):
        add(index,0,allocate=1,clear=1)
        for mirror in (0,1):
            for d in directions:
                add(index,mirror=mirror,interaction=1,direction=d,height=.5)
        for biped,board_ground in ((0,0),(1,1),(1,0)):
            add(index,0,allocate=1,clear=1)
            add(index,biped=biped,board_ground=board_ground,intents={'GrabWorld':0.})
            add(index,biped=biped,board_ground=board_ground,interaction=1,direction=(-1.,0.,2.,0.),height=1.25)
            add(index,interaction=0,height=1.75)
            add(index,seed=1,interaction=1)
            add(index,2)
            add(index,0,allocate=1,clear=1)
            add(index,interaction=1)
            add(index,2,keep=1)
            add(index,1,dt=.25)
            add(index,2,keep=0)
            add(index,0,dt=.2)
        for available in (111,95):
            add(index,available=available)
    # All phases for every factory, including original CharacterGesture End no-op.
    for index in range(5):
        for phase in range(3):
            add(index,phase,allocate=phase==0,clear=1 if phase==0 else 0)
    w=Record();w.word(len(rows))
    for r in rows:
        w.words(r[k] for k in ('index','phase','allocate','clear','seed','available'));w.words(r['hands']);w.words(r[k] for k in ('keep','category','board','ground','offboard','suppress','bypass'));w.words(r['selections']);w.words(r[k] for k in ('interaction','biped','board_ground','mirror'))
        w.scalar(r['height']);w.scalar(r['dt'])
        for v in r['direction']:w.scalar(v)
        w.word(len(r['intents']))
        for n,v in r['intents'].items():w.raw(n);w.scalar(v)
    return bytes(w.data),rows


def coverage(data,rows,trace_path):
    at=0
    def word():
        nonlocal at
        v,=struct.unpack_from('<I',data,at);at+=4;return v
    def string():
        nonlocal at
        n=word();s=data[at:at+n].decode();at+=n;return s
    assert word()==len(rows)
    traces=[];effects=Counter();phases={}
    for r in rows:
        error=string();statuses=[(word(),string()) for _ in range(4)]
        assert statuses==[(1,''),(1,''),(1,''),(1,'')],(r,statuses)
        publication=(word(),word()) if word() else None
        channels=[[word(),word(),word(),word()] for _ in CHANNELS]
        attrs=[]
        for _ in range(word()):
            n=tuple(word() for _ in range(5));kind,status,sequence,begin,end=[word() for _ in range(5)];payload=[word() if word() else None for _ in range(6)]
            attrs.append(dict(name=n,kind=kind,status=status,sequence=sequence,begin=begin,end=end,payload=payload))
        clips=[string() for _ in range(word())]
        phases.setdefault(r['index'],set()).add(r['phase'])
        if error:effects['diagnostics']+=1
        if publication:effects['publication']+=1
        traces.append(dict(row=r,error=error,publication=publication,channels=channels,attrs=attrs,clips=clips))
    assert at==len(data);trace_path.write_text(json.dumps(traces,indent=2)+'\n')
    assert all(p=={0,1,2} for p in phases.values()),phases
    ids={p[0] for t in traces if (p:=t['publication']) is not None};assert set(range(37))<=ids,ids
    for i,c in enumerate(CHANNELS[:5]):
        assert any(t['channels'][i][0] for t in traces),c
        assert any(not t['channels'][i][0] for t in traces),c
        effects[c]=sum(t['channels'][i][0] for t in traces)
    assert any(t['publication'] and t['publication'][1] for t in traces)
    assert any(t['publication'] and not t['publication'][1] for t in traces)
    for phase in ('INTO','CYC','OUT'):
        clips={c for t in traces for c in t['clips'] if c.startswith('B_GSTR_') and c.endswith('_'+phase)}
        assert clips,phase;effects['stock_'+phase]=len(clips)
    assert any(any(ch[3] for ch in t['channels'][:3]) for t in traces),'No real gesture sequence transitions'
    for proof in PROOFS:
        values={a['payload'][0] for t in traces for a in t['attrs'] if a['name']==tuple(name(proof))};assert len(values)>=4,(proof,values);effects[proof]=len(values)
    required=('CharacterGesture requires original physical and hostgesture publication','CharacterGesture requires filteredcategory','CharacterGesture requires boardheldbyte311','CharacterGesture requires actualheight',
        'CharacterGesture needs the actual skater gesture selections','Invalid stock gesture selection 38','Shove requires actual interaction output','Shove requires animation stance')
    for n in required:assert any(n in t['error'] for t in traces),n
    for n in ('GESTURE_SHOVE_0','GESTURE_SHOVE_1','GESTURE_SHOVE_BOARD','GESTURE_ANTIC_0','GESTURE_ANTIC_1','GESTURE_ANTIC_BOARD'):
        assert any(n in t['clips'] for t in traces),n
    assert any(t['row']['index']==2 and t['row']['phase']==0 and t['publication'] is None for t in traces)
    assert effects['publication']>0 and effects['diagnostics']>0,effects
    return dict(commands=len(rows),catalog_ids=len(ids),factory_configs=len(phases),observable_effects=dict(effects))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('assets','metadata','output','target-dir'):p.add_argument('--'+n,type=Path,required=True)
    args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for marker in ('result.json','first-divergence.json'):(output/marker).unlink(missing_ok=True)
    sources=('NativeMath','AnimationName','Intents','Input','InputIntentions','NameId','Settings','Graph','GraphController','GraphConditions','GraphGestureOperations',
        'AnimationSamples','AnimationMetadata','AnimationPlayback','AnimationPlaybackParameters','AnimationTrees','AnimationChannels','MotionAnimation','GraphMotionName','GraphMotionGestureOperations')
    cpp,rust=build_probes(output,args.target_dir,'motion_gesture_operations',sources)
    graph,configs=fixture();reference,native=output/'operations.reference-graph',output/'operations.graph';reference.write_bytes(original_graph(graph));native.write_bytes(converter.encode_graph(converter.read_graph(reference)))
    md=fixture_metadata();metadata_json,metadata_native=output/'fixture.json',output/'fixture.skate';metadata_json.write_text(json.dumps(md));metadata_native.write_bytes(metadata_converter.pack_metadata(md));inputs,rows=corpus()
    (output/'input.bin').write_bytes(inputs);(output/'authored-commands.json').write_text(json.dumps(rows,indent=2)+'\n');(output/'source-catalog.json').write_text(json.dumps(original_catalog(),indent=2)+'\n')
    expected=subprocess.check_output([str(rust),str(args.assets),str(reference),str(metadata_json)],input=inputs)
    actual=subprocess.check_output([str(cpp),str(args.metadata/'bank-0.skate'),str(args.metadata/'bank-1.skate'),str(metadata_native),str(native)],input=inputs)
    (output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual)
    if actual!=expected:
        first=next((i for i,(a,b) in enumerate(zip(actual,expected)) if a!=b),min(len(actual),len(expected)));report=dict(passed=False,first_byte=first,reference_length=len(expected),cpp_length=len(actual),reference_hex=expected[max(0,first-16):first+32].hex(),cpp_hex=actual[max(0,first-16):first+32].hex())
        (output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
    result=coverage(expected,rows,output/'original-trace.json');report=dict(passed=True,output_bytes=len(expected),output_sha256=hashlib.sha256(expected).hexdigest(),coverage=result,
        comparison='exact actual original full MotionHost gesture/shove factories, allocation/phases, real 37-entry stock gesture catalog/hand channels/stages, input gating, retained publication, global EndGesture teardown, shove angle/anticipation/interaction/channel lifecycle and actual applied parameters',
        limitations='Full controller registration and live physical producers are separate. Exhaustive malformed parser diagnostics are not covered.',reference_provenance='reference-provenance.json')
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
