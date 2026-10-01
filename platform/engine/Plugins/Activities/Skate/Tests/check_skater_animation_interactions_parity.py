#!/usr/bin/env python3
"""Direct original actor schedule with accepted push/gesture/shove owners.

Protocol three retains baseline versions one/two and adds explicit completed
interaction records plus public push, gesture and channel observations. Both
implementations run their real AG/MG controllers and evaluate actual stock
channels through the full pose/hierarchy/packet schedule. Guard all builds/runs.
"""
from collections import Counter
import json
from pathlib import Path
import sys
import check_skater_animation_parity as scheduler
import check_skater_animation_feedback_parity as feedback
from check_graph_parity import attribute
from check_animation_trees_parity import name as attribute_name

ALIASES=('Pushing','NewPush','LeftPush','RightPush','GrabWorld','ForceBrake',
    'GestureLeftStart','GestureRightStart','GestureUpStart','GestureDownStart',
    'GestureLeftHeld','GestureRightHeld','GestureUpHeld','GestureDownHeld')
QUERIES=feedback.QUERIES+ALIASES
base_coverage=feedback.coverage


def fixtures(case):
    action,motion=feedback.fixtures(case)
    action['children'][0:0]=[scheduler.behavior('CreateMGIntentFromAGIntent',[
        attribute('AGIntent',name),attribute('MGIntent',name)]) for name in ALIASES]
    first_state=next(i for i,c in enumerate(motion['children']) if c['tag']=='state')
    motion['children'][first_state:first_state]=[
        scheduler.behavior('InitPush'),scheduler.behavior('ComputeTargetCoefsFromSpeedAndStrength',[attribute('regularAttributes',boolean=case%2)]),
        scheduler.behavior('SetPushCoefs',[attribute('onFirstUpdateOnly',boolean=case%3==1)]),
        scheduler.behavior('PushCycle',[attribute('newPushName','RightPush' if case%2 else 'LeftPush')]),
        scheduler.behavior('CharacterGesture')]
    for child in motion['children']:
        if child['tag']!='state':continue
        if any(a['name']=='name' and a['text']=='active' for a in child['attributes']):
            child['children'].extend([
                scheduler.behavior('ComputeFirstPushStrength'),
                scheduler.behavior('ComputeRepushDeadline',[attribute('regularAttributes',boolean=case%2)]),
                scheduler.behavior('PushOut',[attribute('isRightFoot',boolean=case%2)]),
                scheduler.behavior('Shove',[attribute('Selection','SHOVE_SELECTION_SPACE'),attribute('SelectionBrd','SHOVE_OFFB_BRD_SEL_SPACE'),
                    attribute('Antic','R_ANTIC_OLLIE_N_0_CYC'),attribute('AnticBrd','R_ANTIC_OLLIE_N_0_CYC')])])
            if case%2:child['children'].append(scheduler.behavior('MaintainShove'))
        else:child['children'].append(scheduler.behavior('EndGesture'))
    return action,motion


class Writer(feedback.Writer):
    def physical(self,case,tick,complete=True):
        # Push reads actor SpeedInputs.forward_speed, independently of Fakie's
        # animation_164. Cross the actual stock low/high clip speed range even
        # when SetPushCoefs intentionally retains its first-update value.
        speed=(((tick*7+case*3)%41)-3)*.317
        super().physical(case,tick,complete,forward_speed=speed)

    def interactions(self,case,tick):
        self.word(3);self.word(tick%17<13);self.word(tick%11==0);self.word(1)
        # Selection is a live skater preference: CharacterGesture reads it for
        # every active publication, independently of the latched channel clip.
        for direction in range(4):self.word((case*3+direction*7+tick)%37)
        self.word(tick%29==7);self.word(case%2)
        # Pulse independently of state-entry and stride periods. Earlier narrow
        # pulses selected the same quadrant at every case-1/9 channel creation;
        # selection spaces correctly latch their first selected stock child.
        directions=((1,0),(1,1),(0,1),(-1,1),(-1,0),(-1,-1),(0,-1),(1,-1))
        x,z=directions[(case+tick//5)%len(directions)]
        self.word(tick%11<4);self.vector((x*.731,0,z*.731,0))
        self.word(tick%3==0);self.word(tick%5==0);self.float(.517+tick*.03125)


def corpus(samples):
    manifest=json.loads((samples/'samples-manifest.json').read_text());prefix=Writer();prefix.word(len(manifest['clips']))
    for clip in manifest['clips']:prefix.string(clip['name'])
    prefix.word(len(QUERIES))
    for name in QUERIES:prefix.string(name)
    cases=[];counts=Counter()
    for case in range(scheduler.FIXTURES):
        ops=[]
        def new(op):s=Writer();s.word(op);ops.append(s);counts[op]+=1;return s
        new(5);new(6).word(case%5);s=new(1);s.word(case%2);s.word(case%4)
        for tick in range(scheduler.TICKS):
            if tick in (31,79):s=new(1);s.word((case+tick)%2);s.word((case+tick)%5)
            if tick in (9,38,87):new(2).word((case+tick)%3)
            if tick in (16,17,72):
                s=new(3);s.string('Overlay' if tick!=72 else 'SkitchAntic');s.string('R_ANTIC_OLLIE_N_0_CYC');s.channel(case)
            if tick in (34,101):s=new(4);s.string('overlay');s.float(.137);s.word(tick==101)
            if tick==63:new(7)
            values=[('push',((tick+case)%11-5)*.125),('other',((tick+case*3)%13-6)*.125)]
            if tick%23<15:values.append(('enable',0))
            if tick%23==11:values.append(('exit',1))
            if tick%7==0:values.append(('WeightOnNose',0))
            if tick%13<7:values.append(('Pushing',(tick%13)*.137))
            if tick%13==9:values.append(('NewPush',0))
            if tick%13<11:values.append(('RightPush' if case%2 else 'LeftPush',0))
            if tick%11<3:values.append(('GrabWorld',0))
            if tick%29==7:values.append(('ForceBrake',0))
            # Reset Begin can consume a one-frame start and clear the current
            # gesture direction. Held alone then cannot restart it. Exercise
            # repeated independent pulses rather than coupling every start to
            # the actor's 32-frame reset/controller cadence.
            direction=((tick//5)+case)%4;stem=('Left','Right','Up','Down')[direction]
            if tick%5==0:values.append(('Gesture'+stem+'Start',0))
            if tick%5<3:values.append(('Gesture'+stem+'Held',0))
            new(8).extra(case,tick);new(9).interactions(case,tick)
            s=new(0);s.float((0,1/60,.05,.1)[(tick+case)%4]);s.map(values);s.physical(case,tick,complete=tick not in (45,97))
        encoded=Writer();encoded.word(case);encoded.string(('Loose','Gonzo','Aggressive','')[case%4]);encoded.word(len(ops))
        for s in ops:encoded.data.extend(s.data)
        cases.append(bytes(encoded.data))
    return prefix,cases,counts


def operation_codes(case):return [v for op in feedback.base_codes(case) for v in ([8,9,0] if op==0 else [op])]
def encode(prefix,cases):return b'ATASKTR3'+bytes(prefix.data)+len(cases).to_bytes(4,'little')+b''.join(cases)


class Reader(feedback.Reader):
    def snapshot(self):
        frame=super().snapshot();push=self.words(9) if self.word() else None;gesture=self.words(2) if self.word() else None
        channels=[self.words(4) for _ in range(7)];query_error=self.status();found=self.word()
        record=self.words(10);payload=[self.optional() for _ in range(6)]
        frame['interactions']=dict(push=push,gesture=gesture,channels=channels,shove_direction_query=dict(error=query_error,found=found,record=record,payload=payload))
        return frame


def coverage(data,codes):
    report=base_coverage(data,[c[:] for c in codes]);r=Reader(data);proof=[]
    for case in range(r.word()):
        steps=r.word();frames=[r.snapshot()];assert steps==len(codes[case])
        for op in codes[case]:
            error=r.status()
            if error is None and op==3:r.word()
            elif error is None and op==5:r.matrices()
            frames.append(r.snapshot())
        owners=[f['interactions'] for f in frames];pushes=[p['push'] for p in owners if p['push'] is not None]
        assert {0,1}=={p[-1] for p in pushes},(case,'live push cycle did not enter holding/release')
        assert len({tuple(p[2:8]) for p in pushes})>8,(case,'push coefficients never followed actual speed/strength')
        assert len({p[0] for p in pushes})>1,(case,'RepushDeadline End did not update shared out factor')
        gestures={tuple(p['gesture']) for p in owners if p['gesture'] is not None}
        assert len(gestures)>1,(case,'live gesture selection/publication did not change')
        assert any(p['gesture'] is None for p in owners),(case,'EndGesture never cleared publication')
        assert any(any(c[0] for c in p['channels'][:3]) for p in owners),(case,'gesture never owned a real stock channel')
        assert any(p['channels'][4][0] for p in owners),(case,'Shove never owned its real selection-space channel')
        queries=[p['shove_direction_query'] for p in owners];assert all(q['error'] is None for q in queries),(case,'live channel direction query failed')
        direction_name=attribute_name('SHOVEDIRECTION');cached={q['payload'][0] for p,q in zip(owners,queries) if p['channels'][4][0] and q['found'] and q['record'][:5]==direction_name and q['payload'][0] is not None}
        assert len(cached)>1,(case,'actual stock shove selection never exposed changing direction')
        assert all(not f['errors'][1] for f in frames),(case,'registered interaction produced graph diagnostics')
        proof.append(dict(case=case,push_coefficient_states=len({tuple(p[2:8]) for p in pushes}),repush_factors=len({p[0] for p in pushes}),gesture_publications=sorted(gestures),shove_direction_values=len(cached),gesture_channels=[i for i in range(3) if any(p['channels'][i][0] for p in owners)]))
    assert r.at==len(data),(r.at,len(data));report['interaction_owner_proofs']=proof;return report


def validate_input(data):
    r=scheduler.Reader(data);r.at=8
    for _ in range(r.word()):r.string()
    assert [r.string() for _ in range(r.word())]==list(QUERIES);assert r.word()==scheduler.FIXTURES
    for case in range(scheduler.FIXTURES):
        assert r.word()==case;r.string();codes=operation_codes(case);assert r.word()==len(codes)
        for code in codes:
            assert r.word()==code
            if code==0:
                r.word()
                for _ in range(r.word()):r.string();r.word()
                if r.word():r.words(3)
                if r.word():r.words(2);r.string()
                for _ in range(3):
                    if r.word():r.word()
                if r.word():r.words(3)
                for _ in range(2):
                    if r.word():r.word()
                r.words(6+8+1+4+1+8+3+16+2+21+3)
            elif code==1:r.words(2)
            elif code in (2,6):r.word()
            elif code==3:r.string();r.string();r.words(9)
            elif code==4:r.string();r.words(2)
            elif code==8:r.words(46)
            elif code==9:r.words(18)
    assert r.at==len(data),(r.at,len(data))


def main():
    scheduler.fixtures=fixtures;scheduler.corpus=corpus;scheduler.operation_codes=operation_codes;scheduler.encode=encode;scheduler.QUERIES=QUERIES;scheduler.Reader=Reader;scheduler.coverage=coverage;feedback.Reader=Reader
    scheduler.main()
    args=sys.argv[1:];output=Path(args[args.index('--output')+1]).resolve();path=output/'result.json';result=json.loads(path.read_text())
    result['comparison']='Direct unchanged original SkaterAnimation from_source/advance, actual AG/MG controllers and live push/gesture/shove owner callbacks, applied real stock channels, full sampled poses/hierarchy/packet, with persistent state and output records.'
    result['interaction_boundary']='Actor-published actual speed/switch/feet feed push. Completed gesture selections/gates and interaction direction/trigger/board/height records are explicitly supplied to both public hosts before full actor advance; original actor does not produce those records itself.'
    result['limitations']='Supported graph fixtures with completed physical publications; physical producer and full authored gameplay/session parity remain pending. No synthetic pose/clip substitutes or implementation methods are used.'
    path.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
