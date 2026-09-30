#!/usr/bin/env python3
"""Compare the complete actor schedule after live feedback/condition/score wiring.

The baseline protocol remains unchanged. Version two adds explicit completed
riding/grind/landing/wipeout/prelanding publications and reads public persistent
score, channel and construction owners. All original host and actor methods run
unchanged; no implementation slices, producer callbacks or accessors replace
production. Compile/run only through atelier.safety.
"""
from collections import Counter
import json
from pathlib import Path
import sys
import check_skater_animation_parity as scheduler
from check_graph_parity import attribute
from check_animation_trees_parity import name as attribute_name

base_fixtures=scheduler.fixtures
base_codes=scheduler.operation_codes
base_coverage=scheduler.coverage
base_reader=scheduler.Reader
QUERIES=scheduler.QUERIES+('Crouch','HardTurnCrouch','Manual','AutoPumpAngle','AutoPumpMag','FakieTurn','LeftSlide','RightSlide','GestureSpeed','Y')


def fixtures(case):
    action,motion=base_fixtures(case)
    intent_names=('Crouch','HardTurnCrouch','Manual','AutoPumpAngle','AutoPumpMag','FakieTurn','LeftSlide','RightSlide','GestureSpeed','Y')
    for i,name in enumerate(intent_names):
        action['children'].insert(i,scheduler.behavior('CreateMGIntentFromAGIntent',[
            attribute('AGIntent','push' if i%2 else 'other'),attribute('MGIntent',name),
            attribute('scale',bits=scheduler.bits(.317+case*.03125)),attribute('defaultValue',bits=scheduler.bits(.137))]))
    riding=[scheduler.behavior('UpdateRidingFakie',[
        attribute('timeFromTeleportThreshold',bits=scheduler.bits(.137)),
        attribute('timeSlowlyRollingBackwardsThreshold',bits=scheduler.bits(.113))]),
        scheduler.behavior('SetTurning'),scheduler.behavior('Crouching',[attribute('crouchName','crouch')]),
        scheduler.behavior('SettingBodyTilt'),scheduler.behavior('Pumping'),
        scheduler.behavior('SetSpeed',[attribute('attribute','speed')])]
    if case%2:riding[0],riding[1]=riding[1],riding[0]
    motion['children'][0:0]=riding
    scores=[scheduler.behavior('FilterMotionGraphIntent',[attribute('intent','Y'),attribute('filteredIntent','TweakY'),attribute('blend',bits=scheduler.bits(.317))]),
        scheduler.behavior('ScoringTrick',[attribute('trick','Kickflip')]),
        scheduler.behavior('ScoringGrabs',[attribute('grabName','BaseGrab'),attribute('intentX','TweakX'),attribute('intentY','TweakY'),
            *[attribute(k,v) for k,v in zip(('up','left','down','right'),('UpGrab','LeftGrab','DownGrab','RightGrab'))]]),
        scheduler.behavior('ScoringHandPlants',[attribute('handplantname','BaseHand'),attribute('intentX','TweakX'),attribute('intentY','TweakY'),
            *[attribute(k,v) for k,v in zip(('up','left','down','right'),('UpHand','LeftHand','DownHand','RightHand'))]]),
        scheduler.behavior('TweakProject'),
        scheduler.behavior('SetScoreAugmentation',[attribute('augment','NoseManual'),attribute('mirrorAugment','TailManual')]),
        scheduler.behavior('InitMovingObjects',[attribute('path','Objects/Integration')]),scheduler.behavior('EndShimmy')]
    first_state=next(i for i,child in enumerate(motion['children']) if child['tag']=='state');motion['children'][first_state:first_state]=scores
    for child in motion['children']:
        if child['tag']=='state' and any(a['name']=='name' and a['text']=='active' for a in child['attributes']):
            child['children'][0]['children'].extend([
                scheduler.condition('IsRidingGoofy'),
                scheduler.condition('ComVelCompare',[attribute('axis','x'),attribute('greater',bits=scheduler.bits(0))]),
                scheduler.condition('IsGrindApproach',[attribute('Facing','F')]),
                scheduler.condition('HasLandingType',[attribute('landingType','spin')]),
                scheduler.condition('IsDoneWipingOut'),scheduler.condition('HasTiltToLargeForPreland')])
            child['children'].extend([scheduler.behavior('DisallowPumping'),
                scheduler.behavior('SetTrickHeight',[attribute('from','ANIMTRANSZ'),attribute('rename','height')]),
                scheduler.behavior('SetTrickAttr',[attribute('trick','Kickflip')]),
                scheduler.behavior('ChooseRandomLanding',[attribute('numlandings',bits=scheduler.bits(3))]),
                scheduler.behavior('MovingObject',[attribute('path','Objects\\Integration')])])
        elif child['tag']=='state' and any(a['name']=='name' and a['text']=='idle' for a in child['attributes']):
            # The reset fixtures deliberately clear all live MG values before
            # the active-state height leaf begins. Retain that zero result,
            # and observe changing GestureSpeed at the idle-state entry where
            # the original host still owns the newly published live MG map.
            child['children'].append(scheduler.behavior('SetTrickHeight',[
                attribute('from','ANIMTRANSZ'),attribute('rename','idle_height')]))
    return action,motion


class Writer(scheduler.Writer):
    def extra(self,case,tick):
        gate=(tick+case)%7<4
        self.word(31)
        for v in ((.731,.317,.137,0),(1,0,0,0),(0,0,1,0)):self.vector(v)
        self.float(.731);self.float(.719)
        self.word(gate);self.word(4 if gate else 0);self.word(1 if gate else 0);self.word((tick+case)%3);self.word(gate);self.float(.113);self.word(gate)
        self.float(.137);self.float(.317);self.word(2 if gate else 0);self.float(.731)
        self.word(gate);self.float(.137);self.float(.317);self.word((tick+case)%5);self.word(gate);self.word(1);self.float(.731);self.float(.113);self.float(.719)
        self.word(gate);self.float(.731);self.float(.137);self.float(-.317);self.word(0);self.word(0);self.float(.113);self.word(0);self.float(.719);self.float(.731);self.float(.317)


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
            new(8).extra(case,tick)
            s=new(0);s.float((0,1/60,.05,.1)[(tick+case)%4]);s.map(values);s.physical(case,tick,complete=tick not in (45,97))
        encoded=Writer();encoded.word(case);encoded.string(('Loose','Gonzo','Aggressive','')[case%4]);encoded.word(len(ops))
        for s in ops:encoded.data.extend(s.data)
        cases.append(bytes(encoded.data))
    return prefix,cases,counts


def operation_codes(case):return [value for op in base_codes(case) for value in ([8,0] if op==0 else [op])]
def encode(prefix,cases):return b'ATASKTR2'+bytes(prefix.data)+len(cases).to_bytes(4,'little')+b''.join(cases)


class Reader(base_reader):
    def optional_name(self):return self.words(5) if self.word() else None
    def named_vector(self):return self.words(7) if self.word() else None
    def snapshot(self):
        frame=super().snapshot();hand=self.named_vector();grab=self.named_vector();names=[self.optional_name(),self.optional_name()];name=self.optional();flags,pumping,moving=self.words(3)
        construction=[self.words(10) for _ in range(self.word())];channels=[self.words(4) for _ in range(5)]
        frame['feedback']=dict(hand=hand,grab=grab,trick_names=names,name=name,flags=flags,allow_pumping=pumping,moving=moving,construction=construction,pump_channels=channels)
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
        owners=[f['feedback'] for f in frames]
        assert {0,1}=={p['allow_pumping'] for p in owners},(case,'pump suppression did not enter/leave')
        assert {0,1}=={p['moving'] for p in owners},(case,'moving-object owner did not enter/leave')
        assert any(p['flags']&0x01000000 for p in owners),(case,'ScoringTrick never wrote the actual score packet')
        for kind in ('hand','grab'):
            values={tuple(p[kind]) for p in owners if p[kind] is not None}
            assert len(values)>16,(case,kind,'filtered inputs never reached public score vectors')
        assert all(p['trick_names']==[attribute_name('Kickflip')]*2 for p in owners if p['flags']&0x01000000)
        jump_name=attribute_name('JumpHeightOverride');jump_values={a[5] for f in frames for a in f['graph_attributes'] if a[:5]==jump_name}
        assert len(jump_values)>2,(case,'SetTrickHeight never emitted changing live gesture-height output')
        random_name=attribute_name('Random');random_values={tuple(v[5:]) for p in owners for v in p['construction'] if v[:5]==random_name}
        assert len(random_values)>1,(case,'ChooseRandomLanding never advanced the actual random owner')
        proof.append(dict(case=case,hand_vectors=len({tuple(p['hand']) for p in owners if p['hand'] is not None}),grab_vectors=len({tuple(p['grab']) for p in owners if p['grab'] is not None}),jump_height_values=len(jump_values),random_selections=len(random_values),score_flags=sorted({p['flags'] for p in owners}),pump_suppression=sorted({p['allow_pumping'] for p in owners}),moving=sorted({p['moving'] for p in owners})))
    assert r.at==len(data),(r.at,len(data));report['live_owner_proofs']=proof
    return report


def validate_input(data):
    r=base_reader(data);r.at=8
    for _ in range(r.word()):r.string()
    assert [r.string() for _ in range(r.word())]==list(QUERIES)
    assert r.word()==scheduler.FIXTURES
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
            elif code==8:r.words(1+14+7+4+9+11)
    assert r.at==len(data),(r.at,len(data))


def main():
    scheduler.fixtures=fixtures;scheduler.corpus=corpus;scheduler.operation_codes=operation_codes;scheduler.encode=encode;scheduler.QUERIES=QUERIES;scheduler.Reader=Reader;scheduler.coverage=coverage
    scheduler.main()
    args=sys.argv[1:];output=Path(args[args.index('--output')+1]).resolve();path=output/'result.json';result=json.loads(path.read_text())
    result['comparison']='Direct original SkaterAnimation from_source/advance with actual AG/MG controllers and registered live feedback, physical/special conditions and score leaves, through parameters/clocks/cache/channels/full poses/matrices/attributes/stance and fixed-step packet publication.'
    result['feedback_boundary']='Actual completed crouching/turning/tilt/fakie/pump records published before AG. SetSpeed reads crouching.body_164; slide speed remains the distinct fakie publication. Traversal alternates live fakie/turning and graph-owned pump suppression. Extra completed predicate records are supplied explicitly to both public hosts before their next full actor advance.'
    result['limitations']='Supported graph fixtures with supplied completed physical publications. This compares the scheduler and its live records, not the physical producers that created them. Full authored gameplay/session scheduling requires further integration.'
    path.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
