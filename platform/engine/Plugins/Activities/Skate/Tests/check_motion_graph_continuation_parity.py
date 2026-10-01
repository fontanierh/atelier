#!/usr/bin/env python3
"""Whole pinned MotionHost factory/constructor/controller continuation proof.

Only root compiles/runs under the shared render lock and memory guard. Original
host modules are byte-preserved, with one appended read-only registration
observer. Completed physical records are explicit inputs to both hosts.
"""
import argparse
from collections import Counter
import copy
import hashlib
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tarfile
from check_gesture_parity import converter, PLUGIN
from check_graph_parity import attribute, element, original_graph
from check_input_parity import Record, fbits
from check_animation_trees_parity import converter as metadata_converter, name
from check_motion_animation_parity import validate_fixture_attributes
from session_parity import REFERENCE_REVISION, digest

CODE = PLUGIN / 'Source/AtelierSkate/Private/Native'
UNITS = ('NativeMath','AnimationName','Intents','Input','InputIntentions','NameId','Settings','StockSettingsReader',
    'Graph','CompiledGraph','GraphController','GraphConditions','GraphGestureOperations','GraphIntentOperations',
    'GraphMotionSliding','AnimationSamples','AnimationMetadata','AnimationPlayback','AnimationPlaybackParameters',
    'AnimationTrees','AnimationChannels','MotionAnimation','MotionAnimationOperations','MotionFrame','GraphMotionName',
    'GraphMotionConditions','GraphMotionPhysicalConditions','GraphMotionSpecialConditions','RidingAnimation','RidingAnimationSettings',
    'GraphMotionFeedbackOperations','GraphMotionScoreOperations','GraphMotionPushOperations','GraphMotionGestureOperations','MotionGraphHost',
    'AnimationRidingAuxiliary','AnimationKickturn','AnimationAirborne','AnimationAirborneSettings','WipeoutOrientation',
    'GraphMotionOffboardTiming','GraphMotionTrickLifecycle','GraphMotionGrindOperations','GraphMotionOffboardWipeoutOperations',
    'GraphMotionToggleBoard','MotionGraphContinuationOperations','MotionGraphContinuationSettings','MotionGraphContinuationHost')
PARAMS = ('GRABBING','TRICKHEIGHT','MANUAL_ANGLE','ABSORBLENGTH','ANTIC_LENGTH','SPIN','AVGVELY','DISTTOCOG',
    'CADENCESTARTPERCENT','ANIMTIME','ANIMTRANSX','ANIMTRANSY','ANIMTRANSZ','BIPEDSTARTANGLE','BIPEDSPEED',
    'BODYTWEAKX','BODYTWEAKY','LEAN','TWIST','WIPEOUTGESTUREX','WIPEOUTGESTUREY','YAW','PITCH','EXTEND',
    'CUSTOM_HEIGHT','GRINDTWIST','GRINDHEIGHT','BUMPX','BUMPY','FAKIE_HEAD')
QUERIES = ('A','TweakX','TweakY','Manual','Grab','KickTurn','Spin','GrindTwist','OB_RetrieveBoard','OB_DropBoard',
    'OB_ThrowBoard','OB_DoAirBodyTweak','OB_AirBodyTweakX','OB_AirBodyTweakY','enable','exit')
CHANNELS = ('fakie','AirBodyTweak','RetrieveBoard','IA_BODYSPIN_OLLIE_FS_0_N','IA_BODYSPIN_OLLIE_BS_0_N')
# The full first exact direct run is an immutable prefix. Only its outer row
# count changes when the real source Begin/Update stimulus below is appended.
PRESERVED_DIRECT_ROWS=5412
PRESERVED_DIRECT_INPUT_BYTES=3978558
PRESERVED_DIRECT_INPUT_SHA256='e28867309cd13f7fc5dd17834319716a58917a671bdd47b53c76faeee53d981c'
PRESERVED_DIRECT_ROWS_SHA256='6e7d0cd27d822dc5f5735b8205f059677d1d31ba4fe8f6121e5b849e716ed7a3'
PRESERVED_DIRECT_OUTPUT_BYTES=34789352
PRESERVED_DIRECT_OUTPUT_SHA256='a6d01fb39e40674def844ec4634cf0ae6af03900e295404dbc38765426adcf0c'
MISSING = ('AirDismounting','EnterSkitchingBehaviour','SkitchingBehaviour','SkitchShimmyingBehaviour')
# Original MotionFactory returns Unsupported for these stock CONDITIONS.
# MISSING's behaviors are instead registered StockGameplay variants whose
# execution reports an absent gameplay producer; keep that distinction exact.
STOCK_UNSUPPORTED_CONDITIONS = Counter({
    'IsArmChannelPlaying':2,'IsDropInWithoutTransition':1,
    'AngleAdjustByAnimationEndLessThan':32,'SkitchingPosition':30,
    'IsSkitchingWithAbsorb':2,'IsSkitchShimmying':4})
NEW_NAMES = ('SetBumpCoefficients','FakieHeadChannel','KickTurnSteering','ControlAirLegExtension','BodySpin',
    'BipedCadence','MatchCadence','MatchAirTime','AddRunoutAttribs','FingerFlipOut','HippyJumpAntic','SetManualAngle',
    'FootPlantAbsorb','SetHandPlantAnticLength','LandOnBoard','StoreLandingData','SetLandingData','CreateGrindAttributes',
    'ControlGrindCrouch','GrindControlFade','OffboardBodyTweakBlend','MatchTwistAndLean','Wipeout','EnableWipeoutGestures','ToggleBoard')


def behavior(n, attrs=(), children=()): return element('behaviour', n, attrs, children)
def condition(n, attrs=()): return element('condition', n, [attribute('mask','always'), *attrs])


def operation(n):
    args = {
        'FingerFlipOut':[attribute('grabintent','Grab')],
        'ControlAirLegExtension':[attribute('bone','LeftToeBase'),attribute('driveDistToCom','CUSTOM_HEIGHT')],
        'SetBumpCoefficients':[attribute('X','BumpX'),attribute('Y','BumpY')],
        'ControlGrindCrouch':[attribute('driveDistToCom','GRINDHEIGHT')],
        'GrindControlFade':[attribute('distBoardToCogAnimAttribute','GRINDHEIGHT'),attribute('twistAnimAttribute','GRINDTWIST'),attribute('twistMGIntent','GrindTwist')],
        'MatchTwistAndLean':[attribute('update','always')],
    }
    return behavior(n, args.get(n, ()))


def fixture(kind):
    play = behavior('PlayAnimation',[attribute('anim','GRIND_MAIN'),attribute('transType','play'),attribute('applyPosture',boolean=0)])
    old = [play, behavior('AttachIntent',[attribute('intent','A'),attribute('attr','probe'),attribute('set',boolean=1)]),
        behavior('FilterMotionGraphIntent',[attribute('intent','A'),attribute('filteredIntent','TweakX'),attribute('blend',bits=fbits(.317))]),
        behavior('UpdateTimeSinceTeleport'),behavior('UpdateTimeSinceKickturn'),behavior('UpdateManualOutTimer'),
        behavior('SetGrabType',[attribute('grab','FS')]),behavior('HandBusy',[attribute('hand','BS')]),
        behavior('CreateAttribute',[attribute('attName','Marker'),attribute('always',bits=fbits(.137))]),
        behavior('ScoringTrick',[attribute('trick','Kickflip')]),behavior('ChooseRandomLanding',[attribute('numlandings',bits=fbits(3))]),
        behavior('PrintText2D'),behavior('UpdateStandingOnCar')]
    extra = [operation(n) for n in NEW_NAMES]
    if kind == 'direct':
        configs = old + extra + [behavior(n) for n in MISSING] + [behavior('ResetSkaterAnimation')]
        return element('state','root',children=configs), configs
    # Alternating old and new operations use one original allocation stream.
    mixed=[]
    for i,v in enumerate(extra):
        mixed.append(v)
        if i < len(old)-1: mixed.append(old[i+1])
    active=element('state','active',children=[element('expression',children=[condition('HasAGIntent',[attribute('intent','enable')]),condition('RandomCond')]),
        behavior('IsDoingTrick'),behavior('IsManualing'),*mixed,
        element('transition',attributes=[attribute('target','idle'),attribute('priority','urgent')],children=[
            element('expression',children=[condition('HasAGIntent',[attribute('intent','exit')])]),
            element('hook','GrabSlide',[attribute('right',boolean=1)]),
            element('hook','OverideNextAnimTransitionHook',[attribute('transType','play')])])])
    idle=element('state','idle',children=[behavior('ResetTimeSinceKickturn'),behavior('SetGrabType',[attribute('grab','BS')]),
        operation('EnableWipeoutGestures'),operation('Wipeout'),behavior('StoreLandingData')])
    g=element('state','root',children=[play,behavior('UpdateTimeSinceTeleport'),active,idle])
    return g, []


def factory_fixtures():
    # Raw-only families precede the trimmed source switch. A single spelling
    # graph compares every resulting original registration without guessing a
    # catalog from the generic native diagnostics.
    variants=[]
    for n in NEW_NAMES:
        # The frozen source dispatch panics for these trimmed/raw mismatches;
        # they are outside the source constructor's returned-error domain.
        if n in ('MatchAirTime','FingerFlipOut','HippyJumpAntic','SetManualAngle','LandOnBoard',
            'CreateGrindAttributes','ControlGrindCrouch','GrindControlFade'):continue
        for pad in (' ', '\t'):
            value=operation(n)
            next(a for a in value['attributes']if a['name']=='name')['text']=pad+n+pad
            variants.append(value)
    fixtures=[('factory-spelling',element('state','root',children=variants),True)]
    bad=[]
    for field in ('distBoardToCogAnimAttribute','twistAnimAttribute','twistMGIntent'):
        value=operation('GrindControlFade')
        value['attributes']=[a for a in value['attributes']if a['name']!=field]
        bad.append(value)
        fixtures.append(('factory-missing-'+field,element('state','root',children=[value]),False))
    for n in range(2):
        fixtures.append(('factory-order-'+str(n),element('state','root',children=[bad[n],bad[n+1]]),False))
    return fixtures


def fixture_metadata():
    data=dict(version=1,source_bank='ContinuationFixture.abin',source_sha256='d'*64,source_bytes=1000000,
        clips=[],phase_blends=[],blend_spaces=[],selectors=[],selection_spaces=[],unsupported_trees=[])
    def clip(n,pairs=()):
        offset=48+len(data['clips'])*4096
        pairs=sorted(pairs,key=lambda x:tuple(name(x[0])))
        attrs=[dict(name=n,type_id=0,begin_bits=fbits(-1),end_bits=fbits(-1),payload_words=[fbits(v)],source_offset=offset+128+i*128)for i,(n,v)in enumerate(pairs)]
        data['clips'].append(dict(name=n,source_offset=offset,fps_bits=fbits(30),frames_bits=fbits(61),base_speed_bits=fbits(1),flags_word=0x10000000,attributes=attrs))
    clip('GRIND_MAIN_LOW',[('GRINDTWIST',-2)]);clip('GRIND_MAIN_HIGH',[('GRINDTWIST',2)])
    data['phase_blends'].append(dict(name='GRIND_MAIN',source_offset=900000,parameter='GRINDTWIST',children=['GRIND_MAIN_LOW','GRIND_MAIN_HIGH']))
    for i,p in enumerate(PARAMS):
        children=[]
        for j,v in enumerate((-200,200)):
            c=f'CONT_OBSERVER_{i}_{j}';children.append(c);clip(c,[(p,v),(f'CONT_PROOF_{i}',v)])
        data['phase_blends'].append(dict(name=f'CONT_OBSERVER_{i}',source_offset=500000+i*4096,parameter=p,children=children))
    validate_fixture_attributes(data);return data


class Writer(Record):
    def string(self,v): self.raw(v)
    def map(self,values):
        self.word(len(values))
        for n,v in values.items(): self.raw(n);self.scalar(v)
    def physical(self,tick,mask=32767):
        t=tick%97; mirror=(tick//11)%2
        self.words((mask,0x08020000 | (mirror<<30) | (((tick//17)%2)<<29),mirror,1,2 if tick%23<15 else 0,500 if tick%29<17 else 100))
        self.scalars((.137+tick*.071,.731*__import__('math').sin(tick*.317),-.317,.1731));self.scalar((t%9)*.113)
        self.scalars(((t%11)*.0317,.1,.2,.3,.137+(t%13)*.037));self.word(tick%2)
        self.scalars((.137+(t%17)*.037,1.137,1.731,.317,-.731,.137))
        self.word(tick%2)
        for v in ((.731+t*.071,-.317,1.137-t*.0317,.1731),(.317+t*.0317,-.731,1.731-t*.0173,.137),(0,1,0,.317),(__import__('math').sin(t*.137),0,__import__('math').cos(t*.137),.137)):self.scalars(v)
        self.word(mirror)
        for v in ((.137,1.137 if tick%19<5 else -.731,.317,.1731),(0,1.731,0,.137),(0,1,0,.317),(.317,.731,0,.137),(-.317,.731,0,.1731)):self.scalars(v)
        self.scalar(.731);self.word(tick%2);self.scalar(.01 if tick%19>13 else 3.17)
        self.word(tick%19>13);self.scalars((.731,.137,-.731));self.words((0,0));self.scalar(.317);self.word(0);self.scalars((.137,.317,.731))
        self.scalars((.137,-.731-(t%17)*.137,.317,.1731,0,1,0,.137))
        self.scalars((.137+(t%7)*.137,-1.731+(t%9)*.317));self.word(tick%4);self.scalar(99)
        self.word(tick%3!=0);self.raw('FsCrooked');self.scalars((.137,.317,-.731,0,0,1));self.word(tick%2);self.scalars((.731,.137+(t%11)*.037,-1.731+(t%13)*.1731))
        self.words((0,tick%53>30,tick%53<=30,0,1));self.scalars((-.731+(t%17)*.113,.137+(t%11)*.037))
        self.word(0);self.scalars((.137,.317));self.words((0,0));self.scalars((-.731+(t%19)*.071,.137+(t%23)*.073))


def prefix():
    w=Writer();w.word(len(QUERIES))
    for q in QUERIES:w.raw(q)
    w.word(len(PARAMS))
    for i in range(len(PARAMS)):w.raw(f'CONT_OBS{i}');w.raw(f'CONT_OBSERVER_{i}')
    w.word(len(CHANNELS))
    for n in CHANNELS:w.raw(n)
    return w


def corpus(kind,configs):
    rows=[]
    def add(code=2,id=0,phase=1,allocate=False,dt=0.,mask=32767,tag='',t=0):
        rows.append(dict(code=code,id=id,phase=phase,allocate=int(allocate),dt=dt,mask=mask,tag=tag,t=t))
    if kind=='direct':
        add(id=0,phase=0,allocate=True,tag='initial-play')
        for tick in range(128):
            for i,n in enumerate(NEW_NAMES):
                id=13+i
                add(id=id,phase=0 if tick==0 or (n=='AddRunoutAttribs'and tick%17==0)else 1,allocate=tick==0,dt=(0,.00317,.004731,.016666667)[tick%4],tag=n,t=tick)
            for id in (2,3,6,7,9,10):add(id=id,phase=0 if id in(7,10)else 1,dt=0.,tag='shared-old-owner',t=tick)
        add(id=len(configs)-1,phase=0,allocate=True,tag='shared-reset',t=129)
        add(id=0,phase=0,allocate=True,tag='play-after-shared-reset',t=129)
        for i,n in enumerate(NEW_NAMES):add(id=13+i,phase=1,dt=.004731,tag='retained-new-owner-after-reset',t=129)
        for i,n in enumerate(NEW_NAMES):
            id=13+i
            for mask in (0,*[32767^(1<<bit)for bit in range(15)],32767):
                for phase in (0,1,2):add(id=id,phase=phase,allocate=phase==0,mask=mask,tag='independent-absence-'+n,t=i)
        for id,n in enumerate(MISSING,13+len(NEW_NAMES)):
            for phase in (0,1,2):add(id=id,phase=phase,allocate=phase==0,tag='source-missing-'+n)
        # Mixed families must consume one allocation sequence. Callbacks are
        # omitted here intentionally so only identity, not a fake leaf, is read.
        for tick in range(3):
            for id in range(len(configs)):add(code=4,id=id,allocate=True,tag='one-allocation-owner',t=tick)
        assert len(rows)==PRESERVED_DIRECT_ROWS
        # ResetSkaterAnimation deliberately removed the observer channels. This
        # fixture-creation opcode invokes the same real new_channel calls used
        # at startup; it sets no parameter, cached output or retained velocity.
        add(code=5,phase=0,tag='restore-source-observers',t=1)
        for t in range(1,9):
            # AVGVELY reads the same live riding owner, not landing's incoming
            # last_good field. A real Store Update must precede each Set Begin.
            add(id=13+NEW_NAMES.index('StoreLandingData'),phase=1,allocate=True,tag='additional-store-landing',t=t)
            add(id=13+NEW_NAMES.index('SetLandingData'),phase=0,allocate=True,tag='additional-set-landing',t=t)
            add(id=13+NEW_NAMES.index('SetBumpCoefficients'),phase=0,allocate=True,tag='additional-bump-begin',t=t)
            add(id=13+NEW_NAMES.index('MatchCadence'),phase=0,allocate=True,tag='additional-cadence-begin',t=t)
            add(id=13+NEW_NAMES.index('MatchCadence'),phase=1,tag='additional-cadence-update',t=t)
    else:
        for tick in range(384):add(code=0,dt=(0,.00317,.004731,.016666667)[tick%4],tag='mixed-controller',t=tick)
        add(code=1,tag='original-shutdown')
    w=prefix();w.word(len(rows))
    for row in rows:
        t=row['t'];w.words(row[k]for k in ('code','id','phase','allocate'));w.scalar(row['dt'])
        action={}
        if t%29<21:action['enable']=0
        if t%29==17:action['exit']=1
        if t%7==0:action['WipeOutRequest']=0
        if t%9<6:action.update(WipeoutGestureX=.317+(t%11)*.071,WipeoutGestureY=-.731+(t%13)*.113)
        action.update(OB_AirBodyTweakX=.517,OB_AirBodyTweakY=-.317)
        w.map(action)
        values={'A':((t%13)-6)*.137,'Manual':__import__('math').sin(t*.317),'KickTurn':__import__('math').sin(t*.137),
            'Spin':((t%17)-8)*.137,'GrindTwist':((t%19)-9)*.071,'OB_AirBodyTweakX':.517,'OB_AirBodyTweakY':-.317,
            'OB_DoAirBodyTweak':0}
        if t%11<7:values['Grab']=0
        if t%53==0:values['OB_RetrieveBoard']=0
        if t%53==34:values['OB_DropBoard']=0
        if t%97==71:values['OB_ThrowBoard']=0
        w.map(values);w.physical(t,row['mask'])
    return bytes(w.data),rows


class Reader:
    def __init__(self,data):self.data=data;self.at=0
    def word(self):v,=struct.unpack_from('<I',self.data,self.at);self.at+=4;return v
    def words(self,n):return [self.word()for _ in range(n)]
    def string(self):n=self.word();s=self.data[self.at:self.at+n].decode();self.at+=n;return s
    def optional(self):return self.word()if self.word()else None
    def status(self):return (self.word(),self.string())
    def scalar(self):return dict(ok=bool(ok),value=self.word()if ok else self.string())if (ok:=self.word())else dict(ok=False,value=self.string())
    def mapping(self):return dict(size=self.word(),values=[self.optional()for _ in QUERIES])
    def attribute(self):return dict(name=self.words(5),header=self.words(5),payload=[self.optional()for _ in range(6)])
    def commands(self):
        out=[]
        for _ in range(self.word()):
            kind=self.word();v=[kind]
            if kind==0:v+=[self.string(),*self.words(3)]
            elif kind==1:v+=[self.word()]
            elif kind==2:v+=[self.words(self.word())]
            elif kind==3:v+=self.words(2)
            elif kind==4:v+=[self.string()]
            elif kind in (5,6):v+=[self.word()]
            else:raise AssertionError(kind)
            out.append(v)
        return out
    def construction(self):
        status=self.status()
        if not status[0]:return dict(status=status)
        registration=self.words(self.word());instances=self.word()
        return dict(status=status,registration=registration,instances=instances)
    def optional_name(self):return self.words(5)if self.word()else None
    def named_vector(self):return self.words(7)if self.word()else None
    def snapshot(self):
        handle=self.word();statuses=[self.status()for _ in range(3)];conditions=self.words(self.word());error=self.string();frame=self.words(3)
        times=[self.optional()for _ in range(self.word())];active=[self.words(2)for _ in range(self.word())]
        maps=[self.mapping(),self.mapping()];flags=self.words(9);timers=self.words(5);hands=self.words(2)
        actor=self.optional();relative,reset=self.words(2);grab=self.optional();controls=self.words(4)
        score=dict(handplant=self.named_vector(),grab=self.named_vector(),tricks=[self.optional_name(),self.optional_name()],name=self.optional(),flags=self.word(),allow_pumping=self.word(),moving=self.word())
        construction=[self.words(10)for _ in range(self.word())]
        packet=[self.words(6)for _ in range(self.word())];cache=[self.attribute()for _ in range(self.word())];prop=self.words(3);clock=[self.scalar(),self.scalar()];transition=self.word()
        channels=[self.words(4)for _ in CHANNELS];pose_status=self.status();pose=self.commands()if pose_status[0]else []
        return dict(handle=handle,statuses=statuses,conditions=conditions,error=error,frame=frame,times=times,active=active,maps=maps,flags=flags,timers=timers,hands=hands,actor=actor,relative=relative,reset=reset,grab=grab,controls=controls,score=score,construction=construction,packet=packet,cache=cache,property=prop,clock=clock,transition=transition,channels=channels,pose_status=pose_status,pose=pose)


def validate_input(data,rows):
    r=Reader(data);assert [r.string()for _ in range(r.word())]==list(QUERIES)
    assert r.word()==len(PARAMS)
    for i in range(len(PARAMS)):assert (r.string(),r.string())==(f'CONT_OBS{i}',f'CONT_OBSERVER_{i}')
    assert [r.string()for _ in range(r.word())]==list(CHANNELS);assert r.word()==len(rows)
    for row in rows:
        assert r.words(4)==[row[k]for k in ('code','id','phase','allocate')];r.word()
        for _ in range(2):
            for _ in range(r.word()):r.string();r.word()
        r.words(6+4+1+12+18+23+11+8+4);r.word();r.string();r.words(6+1+3+7+7)
    assert r.at==len(data),(r.at,len(data))



def preserved_direct_input(data,rows):
    assert len(rows)==PRESERVED_DIRECT_ROWS+41
    old=bytearray(data[:PRESERVED_DIRECT_INPUT_BYTES]);r=Reader(data)
    for _ in range(r.word()):r.string()
    for _ in range(r.word()):r.string();r.string()
    for _ in range(r.word()):r.string()
    at=r.at;assert r.word()==len(rows)
    struct.pack_into('<I',old,at,PRESERVED_DIRECT_ROWS)
    assert hashlib.sha256(old).hexdigest()==PRESERVED_DIRECT_INPUT_SHA256
    old_rows=(json.dumps(rows[:PRESERVED_DIRECT_ROWS],indent=2)+'\n').encode()
    assert hashlib.sha256(old_rows).hexdigest()==PRESERVED_DIRECT_ROWS_SHA256
    validate_input(old,rows[:PRESERVED_DIRECT_ROWS])
    return dict(rows=PRESERVED_DIRECT_ROWS,input_bytes=len(old),input_sha256=PRESERVED_DIRECT_INPUT_SHA256,
        command_rows_sha256=PRESERVED_DIRECT_ROWS_SHA256,only_changed_prefix_word=dict(byte=at,old=PRESERVED_DIRECT_ROWS,new=len(rows)))


def preserved_direct_output(data,rows):
    r=Reader(data);r.construction();at=r.at;assert r.word()==len(rows)
    for _ in range(PRESERVED_DIRECT_ROWS):r.snapshot()
    assert r.at==PRESERVED_DIRECT_OUTPUT_BYTES
    old=bytearray(data[:r.at]);struct.pack_into('<I',old,at,PRESERVED_DIRECT_ROWS)
    assert hashlib.sha256(old).hexdigest()==PRESERVED_DIRECT_OUTPUT_SHA256
    return dict(rows=PRESERVED_DIRECT_ROWS,output_bytes=len(old),output_sha256=PRESERVED_DIRECT_OUTPUT_SHA256,
        only_changed_prefix_word=dict(byte=at,old=PRESERVED_DIRECT_ROWS,new=len(rows)))


def additional_direct_coverage(rows,traces):
    assert len(rows)==PRESERVED_DIRECT_ROWS+41
    def proof_values(snapshot):
        return {p:next((a['payload'][0]for a in snapshot['cache']if a['name']==name(f'CONT_PROOF_{i}')),None)for i,p in enumerate(PARAMS)}
    assert not any(v is not None for v in proof_values(traces[PRESERVED_DIRECT_ROWS-1]).values())
    restored=rows[PRESERVED_DIRECT_ROWS];assert restored['code']==5 and restored['tag']=='restore-source-observers'
    assert all(v is not None for v in proof_values(traces[PRESERVED_DIRECT_ROWS]).values())
    samples=rows[PRESERVED_DIRECT_ROWS+1:];observed=traces[PRESERVED_DIRECT_ROWS+1:]
    pattern=(('StoreLandingData',1,1,'additional-store-landing'),('SetLandingData',0,1,'additional-set-landing'),
        ('SetBumpCoefficients',0,1,'additional-bump-begin'),('MatchCadence',0,1,'additional-cadence-begin'),
        ('MatchCadence',1,0,'additional-cadence-update'))
    velocities=set();parameters={p:set()for p in ('AVGVELY','BUMPX','BUMPY','CADENCESTARTPERCENT')};allocated=[]
    for sample in range(8):
        rr=samples[sample*5:(sample+1)*5];ss=observed[sample*5:(sample+1)*5]
        for row,(n,phase,allocate,tag),snapshot in zip(rr,pattern,ss):
            assert row['code']==2 and row['id']==13+NEW_NAMES.index(n) and row['phase']==phase
            assert row['allocate']==allocate and row['tag']==tag and row['t']==sample+1 and row['mask']==32767
            assert not snapshot['error'],(row,snapshot['error'])
            if allocate:allocated.append(snapshot['handle'])
        assert ss[0]['timers'][3]==ss[1]['timers'][3]
        velocities.add(ss[0]['timers'][3])
        parameters['AVGVELY'].add(proof_values(ss[1])['AVGVELY'])
        for p in ('BUMPX','BUMPY'):parameters[p].add(proof_values(ss[2])[p])
        parameters['CADENCESTARTPERCENT'].add(proof_values(ss[4])['CADENCESTARTPERCENT'])
    assert len(velocities)==8,velocities
    assert all(None not in v and len(v)==8 for v in parameters.values()),parameters
    previous=next(s['handle']for row,s in reversed(list(zip(rows[:PRESERVED_DIRECT_ROWS],traces[:PRESERVED_DIRECT_ROWS])))if row['tag']=='one-allocation-owner')
    assert len(allocated)==32 and allocated[0]==previous+1 and all(b==a+1 for a,b in zip(allocated,allocated[1:])),allocated
    return dict(observer_channels_restored=len(PARAMS),additional_rows=41,real_store_landing_values=len(velocities),
        additional_parameter_values={p:len(v)for p,v in parameters.items()},shared_allocation_identities=len(allocated))


def coverage(data,rows,kind):
    r=Reader(data);construction=r.construction();assert construction['status']==(1,''),construction
    assert all(construction['registration']),construction
    assert r.word()==len(rows);traces=[r.snapshot()for _ in rows];assert r.at==len(data)
    phases={n:set()for n in NEW_NAMES};values={p:set()for p in PARAMS}
    for row,s in zip(rows,traces):
        assert s['statuses']==[(1,''),(1,''),(1,'')],(row,s['statuses'])
        if kind=='direct' and 13<=row['id']<13+len(NEW_NAMES) and row['code']==2:phases[NEW_NAMES[row['id']-13]].add(row['phase'])
        for a in s['cache']:
            for i,p in enumerate(PARAMS):
                if a['name']==name(f'CONT_PROOF_{i}') and a['payload'][0]is not None:values[p].add(a['payload'][0])
    if kind=='direct':
        preservation=preserved_direct_output(data,rows);additional=additional_direct_coverage(rows,traces)
        assert all(v=={0,1,2}for v in phases.values()),phases
        assert any(s['score']['flags']&0x01000000 and all(s['score']['tricks'])for s in traces),'Shared source score packet never published both trick names'
        random_name=name('Random')
        random_values={tuple(v[5:])for s in traces for v in s['construction']if v[:5]==random_name}
        assert len(random_values)==3,random_values
        assert any(any(s['hands'])for s in traces),'Original shared hand owner never acquired a hand'
        reset=next(s for row,s in zip(rows,traces)if row['tag']=='shared-reset')
        assert reset['relative']==0 and reset['reset'] and not any(reset['hands'])
        assert reset['timers'][2:4]==[0,0]
        assert reset['score']['flags']&0x01000000,'Source reset must retain the score packet'
        # This span has no controller allocations between calls. Both old and
        # new instance storage use the identical original counter sequence.
        ids=[s['handle']for row,s in zip(rows,traces)if row['tag']=='one-allocation-owner']
        assert ids and all(b==a+1 for a,b in zip(ids,ids[1:])),ids
        for n in MISSING:assert any('MotionGraph stock gameplay producer '+n+' is not implemented'in s['error']for row,s in zip(rows,traces)if row['tag']=='source-missing-'+n),n
        absent=[s['error']for row,s in zip(rows,traces)if row['tag'].startswith('independent-absence-')]
        for marker in ('completed OffBoard','completed physical','completed','mirror'):
            assert any(marker.lower()in e.lower()for e in absent),marker
        for p in ('MANUAL_ANGLE','AVGVELY','BIPEDSTARTANGLE','BIPEDSPEED','EXTEND','GRINDTWIST','GRINDHEIGHT','BUMPX','BUMPY'):
            assert len(values[p])>3,(p,len(values[p]))
    else:
        preservation=None;additional=None
        assert len({s['frame'][1]for s in traces})>=2,'No actual controller state transition'
        handles={tuple(v)for s in traces for v in s['active']};assert len(handles)>len(NEW_NAMES),'No reallocation through original transitions'
        assert any(s['controls'][1]for s in traces),'EnableWipeoutGestures never reached shared controls'
        assert len({tuple(s['controls'])for s in traces})>2,'Shared wipeout controls never progressed'
    return dict(commands=len(rows),preserved_original_direct=preservation,additional_real_producers=additional,parameter_values={p:len(v)for p,v in values.items()},active_identities=len({tuple(v)for s in traces for v in s['active']}),errors=sum(bool(s['error'])for s in traces),registration=construction,phases={n:sorted(p)for n,p in phases.items()},score_flags=len({s['score']['flags']for s in traces}),construction_values=len({tuple(v)for s in traces for v in s['construction']}))


def stage_reference(output):
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip())
    rel=(PLUGIN/'ThirdParty/skate-runtime').relative_to(root).as_posix();revision=subprocess.check_output(['git','rev-parse',REFERENCE_REVISION],cwd=root,text=True).strip()
    archive=subprocess.check_output(['git','archive',f'{revision}:{rel}'],cwd=root);source=output/'reference-source'
    if source.exists():shutil.rmtree(source)
    source.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive))as stream:stream.extractall(source,filter='data')
    originals={p.relative_to(source).as_posix():digest(p)for p in sorted(source.rglob('*.rs'))}
    crate=source/'atelier-host';host=source/'crates/skate-host/src';staged={};observer=PLUGIN/'Tests/Reference/motion_graph_continuation_observer.rs'
    for original in sorted(host.rglob('*.rs')):
        relative=original.relative_to(host)
        if relative.as_posix()in ('lib.rs','main.rs'):continue
        dest=crate/'src'/relative;dest.parent.mkdir(parents=True,exist_ok=True);body=original.read_bytes();extra=b'\n'+observer.read_bytes()if relative.as_posix()=='graph_host/motion.rs'else b'';dest.write_bytes(body+extra)
        assert dest.read_bytes()[:len(body)]==body
        staged[relative.as_posix()]=dict(original_prefix_bytes=len(body),original_prefix_sha256=digest(original),append_sha256=hashlib.sha256(extra).hexdigest(),generated_sha256=digest(dest))
    probe=PLUGIN/'Tests/Reference/motion_graph_continuation_probe.rs';shutil.copy2(probe,crate/'src/migration_probe.rs')
    cargo=crate/'Cargo.toml';cargo.write_text(cargo.read_text()+'''\nskate-core={path="../crates/skate-core"}
skate-data={path="../crates/skate-data"}
skate-net={path="../crates/skate-net"}
half="2.7.1"
bevy={version="0.19",default-features=false,features=["std","multi_threaded","bevy_log"]}
[[bin]]
name="motion-graph-continuation-reference"
path="src/migration_probe.rs"
''')
    provenance=dict(reference_revision=revision,source_archive_sha256=hashlib.sha256(archive).hexdigest(),original_source_sha256=originals,staged_host_prefixes=staged,probe_sha256=digest(probe),observer_sha256=digest(observer))
    return source,crate,provenance


def build_probes(output,target):
    source,crate,provenance=stage_reference(output);binary=output/'motion-graph-continuation-reference'
    subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(crate/'Cargo.toml'),'--target-dir',str(target.resolve()),'--bin','motion-graph-continuation-reference'],check=True)
    for rel,sha in provenance['original_source_sha256'].items():assert digest(source/rel)==sha,rel
    for rel,row in provenance['staged_host_prefixes'].items():
        staged=crate/'src'/rel;original=source/'crates/skate-host/src'/rel
        assert digest(staged)==row['generated_sha256']and staged.read_bytes()[:original.stat().st_size]==original.read_bytes(),rel
    shutil.copy2(target.resolve()/'release/motion-graph-continuation-reference',binary);provenance.update(binary_sha256=digest(binary),cargo_lock_sha256=digest(crate/'Cargo.lock'),compiler=subprocess.check_output(['rustc','+1.97.1','-vV'],text=True).strip())
    (output/'reference-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    snap=output/'native-source'
    if snap.exists():shutil.rmtree(snap)
    snap.mkdir();hashes={}
    for p in [*sorted(CODE.glob('*.h')),*[CODE/(u+'.cpp')for u in UNITS],PLUGIN/'Tests/Native/motion_graph_continuation_probe.cpp']:
        shutil.copy2(p,snap/p.name);hashes[p.name]=digest(snap/p.name)
    native=output/'motion-graph-continuation-native'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snap),*[str(snap/(u+'.cpp'))for u in UNITS],str(snap/'motion_graph_continuation_probe.cpp'),'-o',str(native)],check=True)
    for name,sha in hashes.items():assert digest(snap/name)==sha,name
    (output/'native-provenance.json').write_text(json.dumps(dict(immutable_native_sources=hashes,units=UNITS,binary_sha256=digest(native)),indent=2)+'\n')
    return native,binary


def stage_assets(assets,output,collections):
    out=output/'assets'
    if out.exists():shutil.rmtree(out)
    stock=out/'private/stock';stock.mkdir(parents=True)
    for p in assets.iterdir():
        if p.name!='private':(out/p.name).symlink_to(p.resolve(),target_is_directory=p.is_dir())
    for p in (assets/'private').iterdir():
        if p.name!='stock':(out/'private'/p.name).symlink_to(p.resolve(),target_is_directory=p.is_dir())
    for p in (assets/'private/stock').iterdir():
        if p.name!='skater-collections.json':(stock/p.name).symlink_to(p.resolve(),target_is_directory=p.is_dir())
    path=stock/'skater-collections.json';path.write_text(json.dumps(collections));return out,path


def loader_fixtures(collections):
    # One actual consumed field from every source constructor, in source order.
    # Paired removals independently prove the boundaries between all families.
    fields=[('anim_motion','pushing','button_time_max'),('anim_motion','grind_twist','twist_smoothing'),
        ('anim_wipeout','default','controlled_drives_thresh'),('anim_motion','bumps','scale_x_acc'),
        ('anim_carving','default','quickMagMap'),('anim_motion','crouching','crouching_max_height'),
        ('anim_motion','body_tilt','body_tilt_bodyspin_factor'),('anim_motion','anim_pump','pump_amplify'),
        ('anim_motion','power_slide','slide_speed_threshold'),('anim_motion','body_spin','spin_map'),
        ('anim_motion','inair_disttocog','lo_air_arm_extend'),('anim_motion','kickturn','kickturn_spin'),
        ('anim_motion','manual','manual_balance'),('anim_motion','hippy_flip','antic_length_to_hippy_height'),
        ('anim_motion','Hash_41DB0C4F82003A15','Hash_E0C1407B688858AD')]
    def record(data,c,k):
        return next((r for r in data['collections']if converter.name_id(r['class'])==converter.name_id(c)and converter.name_id(r['key'])==converter.name_id(k)),None)
    def actual_field(r,name):
        return next((n for n in r['fields']if converter.name_id(n)==converter.name_id(name)),None)
    def erase(data,triple):
        c,k,f=triple;seen=set();removed=0
        while k and converter.name_id(k)not in seen:
            seen.add(converter.name_id(k));r=record(data,c,k)
            assert r is not None,(c,k)
            key=actual_field(r,f)
            if key is not None:del r['fields'][key];removed+=1
            k=r['parent']
        assert removed>0,triple
    result=[]
    for i,field in enumerate(fields):
        data=copy.deepcopy(collections);erase(data,field);result.append((f'missing-{i}',data,False))
    for i in range(len(fields)-1):
        data=copy.deepcopy(collections);erase(data,fields[i]);erase(data,fields[i+1]);result.append((f'ordered-missing-{i}-{i+1}',data,False))
    for i,(c,k,f)in enumerate(fields):
        original=record(collections,c,k);key=actual_field(original,f);assert key is not None,(c,k,f)
        data=copy.deepcopy(collections);r=record(data,c,k);value=r['fields'][key]
        if len(value['data'])>8:
            value['data']=value['data'][:-8];result.append((f'short-{i}',data,False))
            ignored=copy.deepcopy(collections);record(ignored,c,k)['fields'][key]['type']='EA::Reflection::Int32';result.append((f'curve-type-ignored-{i}',ignored,True))
        else:
            value['type']='EA::Reflection::Int32';result.append((f'scalar-type-{i}',data,False))
            nonfinite=copy.deepcopy(collections);record(nonfinite,c,k)['fields'][key]['data']='7fc12345';result.append((f'scalar-nonfinite-{i}',nonfinite,False))
    return result


def compare(expected,actual,output,label):
    (output/(label+'-reference.bin')).write_bytes(expected);(output/(label+'-native.bin')).write_bytes(actual)
    if expected!=actual:
        at=next((i for i,(a,b)in enumerate(zip(expected,actual))if a!=b),min(len(expected),len(actual)));report=dict(label=label,byte=at,reference_bytes=len(expected),native_bytes=len(actual),reference_hex=expected[max(0,at-16):at+48].hex(),native_hex=actual[max(0,at-16):at+48].hex());(output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)


def stock_registration_audit(data,source):
    r=Reader(data);audit=r.construction()
    assert audit['status']==(1,'') and r.at==len(data)
    # Binding::from_graph appends operations while walking the source's
    # preorder arena. Recover that same order, including kind and byte offset,
    # independently from the original graph rather than native diagnostics.
    operations=[]
    for element,node in enumerate(converter.read_graph(source)):
        if node['tag']in ('behaviour','condition','hook'):
            operation_name=next((v['text']for v in node['attributes']if v['name']=='name'),'__unknown__')
            operations.append(dict(operation_index=len(operations),element_index=element,
                source_offset=node['source_offset'],kind=node['tag'],name=operation_name))
    assert len(operations)==len(audit['registration'])==8305
    unsupported=[];new=Counter();missing=Counter()
    for operation,registered in zip(operations,audit['registration']):
        n=operation['name'];expected=not(operation['kind']=='condition'and n in STOCK_UNSUPPORTED_CONDITIONS)
        assert registered==int(expected),(operation,registered,expected)
        if not registered:unsupported.append(operation)
        if operation['kind']=='behaviour'and n in NEW_NAMES:
            assert registered==1;new[n]+=1
        if operation['kind']=='behaviour'and n in MISSING:
            assert registered==1;missing[n]+=1
    assert Counter(v['name']for v in unsupported)==STOCK_UNSUPPORTED_CONDITIONS
    assert sum(audit['registration'])==8234 and len(unsupported)==71
    assert set(new)==set(NEW_NAMES) and sum(new.values())==142
    assert missing=={'AirDismounting':5,'EnterSkitchingBehaviour':1,'SkitchingBehaviour':1,'SkitchShimmyingBehaviour':2}
    return dict(**audit,source_sha256=digest(source),unsupported_source_operations=unsupported,
        unsupported_condition_counts=dict(STOCK_UNSUPPORTED_CONDITIONS),new_registered_nodes=dict(new),
        missing_producer_registered_nodes=dict(missing))


def prepare(output,assets):
    md=fixture_metadata();mp=output/'fixture.json';mp.write_text(json.dumps(md));mn=output/'fixture.skate';mn.write_bytes(metadata_converter.pack_metadata(md));cases=[]
    for kind in ('direct','controller'):
        g,configs=fixture(kind);gp=output/(kind+'.reference-graph');gp.write_bytes(original_graph(g));gn=output/(kind+'.graph');gn.write_bytes(converter.encode_graph(converter.read_graph(gp)));raw,rows=corpus(kind,configs);validate_input(raw,rows);preserved_direct_input(raw,rows)if kind=='direct'else None;(output/(kind+'-input.bin')).write_bytes(raw);(output/(kind+'-commands.json')).write_text(json.dumps(rows,indent=2)+'\n');cases.append((kind,gp,gn,raw,rows))
    stock=assets/'private/stock/data/state/MotionGraph_OnBoard.stategraph';native=output/'stock.graph';native.write_bytes(converter.encode_graph(converter.read_graph(stock)))
    return mp,mn,cases,stock,native


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('assets','metadata','output','target-dir'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--preflight-only',action='store_true');args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    mp,mn,cases,stock,stockn=prepare(output,args.assets.resolve());settings=output/'settings.skate';settings.write_bytes(converter.encode_settings(args.assets/'private/stock/skater-collections.json'))
    collections=json.loads((args.assets/'private/stock/skater-collections.json').read_text())
    loaders_to_run=loader_fixtures(collections);factories_to_run=factory_fixtures()
    if args.preflight_only:
        _,_,provenance=stage_reference(output);(output/'preflight-reference.json').write_text(json.dumps(provenance,indent=2)+'\n')
        paths=[CODE/(n+ext)for n in ('MotionGraphContinuationOperations','MotionGraphContinuationSettings','MotionGraphContinuationHost')for ext in('.h','.cpp')]+[PLUGIN/'Tests/check_motion_graph_continuation_parity.py',PLUGIN/'Tests/Native/motion_graph_continuation_probe.cpp',PLUGIN/'Tests/Reference/motion_graph_continuation_probe.rs',PLUGIN/'Tests/Reference/motion_graph_continuation_observer.rs']
        for u in UNITS:assert (CODE/(u+'.cpp')).is_file(),u
        report=dict(preflight=True,units=len(UNITS),loader_fixtures=len(loaders_to_run),factory_fixtures=len(factories_to_run),cases=[dict(kind=k,commands=len(rows),input_bytes=len(raw),input_sha256=hashlib.sha256(raw).hexdigest(),preserved_original_direct=preserved_direct_input(raw,rows)if k=='direct'else None)for k,_,_,raw,rows in cases],frozen_files={p.relative_to(PLUGIN).as_posix():digest(p)for p in paths});(output/'preflight.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return
    for marker in ('result.json','first-divergence.json'):(output/marker).unlink(missing_ok=True)
    native,rust=build_probes(output,args.target_dir);reports=[];total=0;sha=hashlib.sha256()
    def run(assets,gp,gn,mode,raw=b'',settings_path=settings):
        expected=subprocess.check_output([str(rust),str(assets),str(gp),str(mp),mode],input=raw)
        actual=subprocess.check_output([str(native),str(args.metadata/'bank-0.skate'),str(args.metadata/'bank-1.skate'),str(mn),str(gn),str(settings_path),mode],input=raw)
        return expected,actual
    expected,actual=run(args.assets,stock,stockn,'construct');compare(expected,actual,output,'stock-registration');audit=stock_registration_audit(expected,stock);reports.append(dict(stock_audit=audit));total+=len(expected);sha.update(expected)
    for kind,gp,gn,raw,rows in cases:
        expected,actual=run(args.assets,gp,gn,'trace',raw);compare(expected,actual,output,kind);reports.append(coverage(expected,rows,kind));total+=len(expected);sha.update(expected)
    factories=[]
    for label,g,success in factories_to_run:
        gp=output/(label+'.reference-graph');gp.write_bytes(original_graph(g));gn=output/(label+'.graph');gn.write_bytes(converter.encode_graph(converter.read_graph(gp)))
        expected,actual=run(args.assets,gp,gn,'construct');compare(expected,actual,output,label);r=Reader(expected);record=r.construction();assert bool(record['status'][0])==success,(label,record);assert r.at==len(expected);factories.append(dict(label=label,**record));total+=len(expected);sha.update(expected)
    loaders=[]
    for label,data,success in loaders_to_run:
        directory=output/label;directory.mkdir(exist_ok=True);fixture_assets,path=stage_assets(args.assets.resolve(),directory,data);native_settings=directory/'settings.skate';native_settings.write_bytes(converter.encode_settings(path));expected,actual=run(fixture_assets,cases[0][1],cases[0][2],'construct',settings_path=native_settings);compare(expected,actual,output,label);r=Reader(expected);record=r.construction();assert bool(record['status'][0])==success,(label,record);assert r.at==len(expected);loaders.append(dict(label=label,status=record['status']));total+=len(expected);sha.update(expected)
    report=dict(passed=True,output_bytes=total,output_sha256=sha.hexdigest(),coverage=reports,factory_fixtures=factories,loader_fixtures=loaders,reference_provenance='reference-provenance.json',native_provenance='native-provenance.json',comparison='Whole unchanged original MotionHost constructor, all stock operation registrations, one actual Controller/allocation stream through old and newly registered leaf owners, retained shared records, packet/cache/property/channel/pose-command order and source missing-producer errors.',limitations='Completed physical records remain explicit caller publications. Individual numeric leaf proofs remain separate. No full physical/frame/gameplay session or unsupported original producers are claimed. Only the eight original panic-only trimmed/raw mismatches for MatchAirTime, FingerFlipOut, HippyJumpAntic, SetManualAngle, LandOnBoard, CreateGrindAttributes, ControlGrindCrouch and GrindControlFade are excluded from returned-error constructor fixtures. The first newly reached panic was padded CreateGrindAttributes at fixture source byte1315: motion_nodes.rs trimmed stock dispatch calls motion_stock_gameplay.rs raw parse, which reaches its unrecognized-operation unreachable at line232. FootPlantAbsorb and SetHandPlantAnticLength retain their nonpanic Unsupported spelling cases.')
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
