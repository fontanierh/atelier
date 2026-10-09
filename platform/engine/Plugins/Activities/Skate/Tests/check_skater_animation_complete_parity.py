#!/usr/bin/env python3
"""Whole original SkaterAnimation facade with complete native MotionHost dispatch.

Root alone builds/runs under the render lock. All production Rust files are
unchanged prefixes. Inputs are actual completed caller-publication records;
this bounded facade proof does not claim the upstream physical coordinator.
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
import check_skater_animation_parity as scheduler
import check_skater_animation_interactions_parity as interactions
import check_motion_graph_continuation_parity as continuation
from check_graph_parity import attribute, element, original_graph
from check_gesture_parity import converter, PLUGIN
from session_parity import REFERENCE_REVISION, digest

CODE = PLUGIN / 'Source/AtelierSkate/Private/Native'
TESTS = PLUGIN / 'Tests'
UNITS = tuple(dict.fromkeys((*continuation.UNITS, 'ActionGraphFrame', 'AnimationPose',
    'AnimationPoseAuthored', 'AnimationPoseJson', 'AnimationPublication', 'SkaterAnimation')))
CHANNELS = ('fakie', 'AirBodyTweak', 'RetrieveBoard', 'IA_BODYSPIN_OLLIE_FS_0_N', 'IA_BODYSPIN_OLLIE_BS_0_N')
INTENTS = ('A','X','Manual','Crouch','KickTurn','Spin','GrindTwist','Grab','GestureSpeed',
    'OB_DoAirBodyTweak','OB_AirBodyTweakX','OB_AirBodyTweakY','OB_RetrieveBoard','OB_DropBoard',
    'OB_ThrowBoard','WipeOutRequest','WipeoutGestureX','WipeoutGestureY')
QUERIES = tuple(dict.fromkeys((*interactions.QUERIES, *INTENTS)))
FAMILIES = (continuation.NEW_NAMES[:3] + continuation.NEW_NAMES[9:17],
    continuation.NEW_NAMES[5:9], continuation.NEW_NAMES[3:5], continuation.NEW_NAMES[17:20],
    continuation.NEW_NAMES[20:], continuation.NEW_NAMES)
CLIPS = ('B_BUMP','IA_IDLE_N_N_CYC','B_LOW_AIR_CYC_D','B_GRIND5050','B_WIPEOUT_FLAIL','B_NOSE_MANUAL')
TICKS = 192

# All twelve first source trace streams remain immutable prefixes. Only case5's
# encoded operation count changes when actual reconstruction/publication rows
# are appended; every old payload and every old output byte is audited.
PRESERVED_ROWS = (883, 883, 883, 883, 883, 883, 146, 0, 14, 14, 14, 14)
PRESERVED_INPUT_BYTES = 1897771
PRESERVED_INPUT_SHA256 = 'd858b9bb108a09b38a63b37e1fb6e164cf1e3f372fc0b5dd079ed2b3271a1b56'
PRESERVED_OUTPUT_BYTES = 55684404
PRESERVED_OUTPUT_SHA256 = 'fe125808199a2fbc5967d7ab5da9a481e67eba362528484ebebcda3aa1d82e35'
PRESERVED_ROWS_SHA256 = '67703853a2a1a5eb4ab8059dba48d0e9496c78b8386d08464bdcf095f23f5661'
PRESERVED_INPUT_STREAMS = (
    (291572, '3221192b54b330810f132168cd7a0617fe9b2ad4dbaa82d2e6568336ef3377c3'),
    (291572, '2862fbfc0adc46c75363956be31060f55cab9f79eaa6fd8434a546fb3a3db1cd'),
    (291577, 'b6bae75ce641dd3dc7446b4462849da7b7e966724f6db46c57dea31a15be6479'),
    (291567, '219d44760ab403288f061becdc3dbad3667007dd7311cee6e1fd2cad5e37a38f'),
    (291572, 'acdc3bc7159b530b025105f233476d0020351a07437cc3bc455a6b30bf376557'),
    (291572, '138ca1abbd7fa0e681411b8a887cb9f7a470f6a9d1883ccd1d82681c171821cb'),
    (28229, '9d67c5b11c583c70c63cfb78ec58f775549e702ee33a016c48234cf5318697ff'),
    (12, '35620c6ab15d72cbb713e74e0dba4881c782f00bee3864062bad13867e463b1a'),
    (4191, '25714182ef4ada656ca7b3e7d99a4d2b532747e027084cc27683df53149db147'),
    (4191, 'cb1d48023d0714731ff360fd01203d434e509df25d515b1c07635344fa593d33'),
    (4196, 'b11dd87c643174c8ecad7bfb47d6bfe36bc4307d6eb3ded6ec9e06e072547c62'),
    (4186, '1eb045cbc867d7df2a2f47cf2a81a9186b11f9b63c24e2a734354eca10b70b17'),
)
PRESERVED_OUTPUT_STREAMS = (
    (8826081, '8058ac8f4203458826d6c23013a52e2ec9076be0e748e4d9ca3f7e80ee305bea'),
    (8854784, 'd58f513e6368903f3bcdea9fa514f23bf85966bee097b31eaa3e6f45342554ed'),
    (9016442, 'e8ae1b0c1fdae97d517115cae39749e264fe3b3bedf307770e4f709715ad8114'),
    (8552243, '37798f3cd11b8d18585dff4e6848e16e14216b4862bc4c05e85a70d18683c178'),
    (9156000, 'f42b407edacadaad2d4fe9a61b6b0e9d6097203c15820d230edf4019f7ff0ab7'),
    (9405154, '4fccea7a35717ae9ee39d1cc5641d8739b43b29517c39b1665d5c395b99c5f12'),
    (1303405, '2280899fdabd7ec3c101260405a3a70cd085656fbb231e0cc3ffa20a09ae0217'),
    (49050, 'ca6820c8c73ae6b9a239619fc5c1ddc3f3560b4f03c023fe80fb626b799ffabe'),
    (130201, 'c5bec46e594cbc92e2da91354eb8f89be7fab2dd9b586e929281d9cbfa537bb0'),
    (130372, 'e2a7986b8ba981e8d6d39e272c2fc64d9d6df1f3b9dba7b22570072735dc0b00'),
    (130277, '051e7b086bce5807e7c94fe00e0c5f6de8446375a6bf1c5cdc76170a174a2cbb'),
    (130391, '25f5dcf6aa2385440b29a7016d5f9cff80ac61987d72b42dd8bf08463681562d'),
)
ABSENCE_BITS = (0,1,2,3,5,6,7,8,9,10,11,12,13,14)



def extra_operation(name):
    op = copy.deepcopy(continuation.operation(name))
    attrs = op['attributes']
    changes = {'ControlAirLegExtension': {'driveDistToCom':'DISTTOCOG'},
        'ControlGrindCrouch': {'driveDistToCom':'DISTTOCOG'},
        'GrindControlFade': {'distBoardToCogAnimAttribute':'DISTTOCOG', 'twistAnimAttribute':'TWIST'}}
    for a in attrs:
        if a['name'] in changes.get(name, {}): a['text'] = changes[name][a['name']]
    return op


def play(name, kind='play'):
    return scheduler.behavior('PlayAnimation', [attribute('anim',name), attribute('transType',kind),
        attribute('applyPosture',boolean=0), attribute('playBackSpeed',bits=scheduler.bits(1))])


def fixtures(case):
    action = element('state','root',children=[scheduler.behavior('CreateMGIntentFromAGIntent',
        [attribute('AGIntent',n),attribute('MGIntent',n)]) for n in INTENTS])
    if case >= 8:
        return action, element('state','root',children=[play('R_STAND_IDLE2_N_0_CYC'),
            scheduler.behavior('UpdateTimeSinceTeleport'), scheduler.behavior(continuation.MISSING[case-8])])
    if case in (6,7):
        return action, element('state','root',children=[play('R_STAND_IDLE2_N_0_CYC'),
            scheduler.behavior('UpdateTimeSinceTeleport')])
    root_ops = [play(CLIPS[case]), scheduler.behavior('UpdateTimeSinceTeleport'),
        scheduler.behavior('AttachIntent',[attribute('intent','A'),attribute('attr','FacadeProbe'),attribute('set',boolean=1)]),
        scheduler.behavior('FilterMotionGraphIntent',[attribute('intent','X'),attribute('filteredIntent','TweakX'),attribute('blend',bits=scheduler.bits(.317))])]
    active = element('state','active',children=[scheduler.expression([scheduler.condition('HasAGIntent',[attribute('intent','enable')])]),
        scheduler.behavior('IsDoingTrick'), scheduler.behavior('IsManualing'),
        scheduler.behavior('HandBusy',[attribute('hand','FS')]), scheduler.behavior('ScoringTrick',[attribute('trick','Kickflip')]),
        *[extra_operation(n) for n in FAMILIES[case]],
        scheduler.transition('idle',[scheduler.condition('HasAGIntent',[attribute('intent','exit')])])])
    idle = element('state','idle',children=[scheduler.behavior('ChooseRandomLanding',[attribute('numlandings',bits=scheduler.bits(3))]),
        scheduler.behavior('ResetTimeSinceKickturn'), scheduler.behavior('SetGrabType',[attribute('grab','BS')]),
        scheduler.transition('active',[scheduler.condition('HasAGIntent',[attribute('intent','enable')])])])
    return action,element('state','root',children=[*root_ops,active,idle])


class Writer(interactions.Writer):
    def publish(self,tick,mask):
        w = continuation.Writer(); w.physical(tick,mask); self.data.extend(w.data)


def corpus(samples,loader_rows,factory_rows):
    manifest=json.loads((samples/'samples-manifest.json').read_text());prefix=Writer();prefix.word(len(manifest['clips']))
    for clip in manifest['clips']: prefix.string(clip['name'])
    prefix.word(len(QUERIES))
    for n in QUERIES: prefix.string(n)
    cases=[];streams=[]
    for case in range(12):
        ops=[];rows=[]
        def new(code,tag='',**info):
            w=Writer();w.word(code);ops.append(w);rows.append(dict(code=code,tag=tag,**info));return w
        def tick(t,mask=32767,complete=True,enabled=True):
            new(8,'base-publication').extra(case,t)
            new(9,'interaction-publication').interactions(case,t)
            new(10,'complete-publication',mask=mask).publish(t,mask)
            values=[(n, (((t*7+i*3)%31)-15)*.071)for i,n in enumerate(INTENTS)
                if n not in ('Grab','OB_RetrieveBoard','OB_DropBoard','OB_ThrowBoard','WipeOutRequest','OB_DoAirBodyTweak')]
            if enabled: values.append(('enable',0))
            if t%29==17: values.append(('exit',1))
            if t%11<7: values.append(('Grab',0))
            if t%53==0: values.append(('OB_RetrieveBoard',0))
            if t%53==34: values.append(('OB_DropBoard',0))
            if t%97==71: values.append(('OB_ThrowBoard',0))
            if t%7==0: values.append(('WipeOutRequest',0))
            if t%13<9: values.append(('OB_DoAirBodyTweak',0))
            s=new(0,'advance',tick=t,mask=mask,complete=complete)
            s.float((0,.00317,.004731,1/60)[t%4]);s.map(values);s.physical(case,t,complete)
        if case==7:
            pass # Whole authored graph construction audit, no invented producers.
        elif case>=8:
            new(5,'initial-pose')
            for t in range(3):tick(t)
            new(7,'source-missing-end')
        elif case==6:
            new(5,'constructor-sentinel-pose')
            for t in range(8):tick(t)
            for i,(_,_,success)in enumerate(loader_rows):
                s=new(11,'constructor-loader',settings=i,replacement=6,expected=success);s.word(6);s.word(i)
            for id,label,settings_id in factory_rows:
                s=new(11,label,settings=settings_id,replacement=id,expected=False);s.word(id);s.word(settings_id)
            s=new(11,'constructor-success-after-failures',settings=0xffffffff,replacement=0,expected=True);s.word(0);s.word(0xffffffff)
            new(5,'new-owner-initial-pose')
            for t in range(12):tick(t)
        else:
            new(5,'initial-pose');new(6,'posture').word(case%3)
            for t in range(TICKS):
                if t in (0,43,103,157):
                    s=new(1,'customisation');s.word((t//43+case)%2);s.word((t//43+case)%5)
                if t in (11,59,131):new(2,'stance-request').word((t+case)%3)
                if t in (21,127):
                    s=new(3,'stock-overlay');s.string('Overlay');s.string('R_ANTIC_OLLIE_N_0_CYC');s.channel(case)
                if t in (39,163):
                    s=new(4,'end-overlay');s.string('Overlay');s.float(.137);s.word(t==163)
                if t in (67,139):new(7,'reallocate-through-endall')
                tick(t,complete=t not in(45,97),enabled=t%29<22)
            # Preserve the original absence stream exactly. Source EndAll
            # retains current/state_times, so later equal-state ticks can have
            # no active callbacks; independent fresh-owner cases follow below.
            for i,bit in enumerate((3,5,6,7,8,9,10,11,12,13,14)):
                new(7,'before-independent-absence')
                tick(200+i,mask=32767^(1<<bit))
                tick(230+i)
            new(7,'final-endall')
            if case==5:
                for bit in ABSENCE_BITS:
                    begin=len(rows)
                    s=new(11,'fresh-absence-owner',replacement=5,settings=0xffffffff,expected=True)
                    s.word(5);s.word(0xffffffff)
                    new(5,'fresh-absence-initial-pose')
                    tick(5,mask=32767^(1<<bit))
                    tick(6,mask=32767^(1<<bit))
                    # A restored packet alone cannot repair a failed Begin.
                    # Observe the SAME retained owner before reconstruction.
                    tick(8)
                    s=new(11,'reconstruct-after-observed-owner',replacement=5,settings=0xffffffff,expected=True)
                    s.word(5);s.word(0xffffffff)
                    new(5,'recovery-initial-pose')
                    tick(8)
                    assert len(rows)-begin==20
                    for row in rows[begin:]:row['independent_absence_bit']=bit
        w=Writer();w.word(case);w.string(('Loose','Gonzo','Aggressive','')[case%4]);w.word(len(ops))
        for op in ops:w.data.extend(op.data)
        cases.append(bytes(w.data));streams.append(dict(case=case,rows=rows))
    return prefix,cases,streams


def encode(prefix,cases): return b'ATASKTR4'+bytes(prefix.data)+len(cases).to_bytes(4,'little')+b''.join(cases)


class Reader(interactions.Reader):
    def mapping(self):return dict(size=self.word(),values=dict(zip(QUERIES,[self.optional()for _ in QUERIES])))
    def snapshot(self):
        start=self.at;v=super().snapshot();registration=self.words(self.word());instances=self.word()
        controls=self.words(4);mask=self.word();pending=[self.words(8)for _ in range(self.word())]
        channels=[self.words(4)for _ in CHANNELS]
        v['complete']=dict(registration=registration,instances=instances,controls=controls,mask=mask,pending=pending,channels=channels)
        v['wire_sha256']=hashlib.sha256(self.data[start:self.at]).hexdigest();return v


def validate_input(data,streams):
    r=Reader(data);r.at=8
    for _ in range(r.word()):r.string()
    assert [r.string()for _ in range(r.word())]==list(QUERIES);assert r.word()==len(streams)
    ranges=[]
    for stream in streams:
        start=r.at;assert r.word()==stream['case'];r.string();count_at=r.at;assert r.word()==len(stream['rows'])
        for row in stream['rows']:
            code=r.word();assert code==row['code']
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
            elif code in(2,6):r.word()
            elif code==3:r.string();r.string();r.words(9)
            elif code==4:r.string();r.words(2)
            elif code==8:r.words(46)
            elif code==9:r.words(18)
            elif code==10:
                mask=r.word();assert mask==row['mask'];r.words(5+4+1+12+18+23+11+8+4);r.word();r.string();r.words(6+1+3+7+7)
            elif code==11:assert r.words(2)==[row['replacement'],row['settings']]
            else:assert code in(5,7),code
        ranges.append(dict(case=stream['case'],start=start,count_at=count_at,end=r.at))
    assert r.at==len(data),(r.at,len(data));return ranges


def preserved_input(data,streams):
    ranges=validate_input(data,streams);retained=bytearray(data[:ranges[0]['start']]);old_rows=[];audit=[]
    for stream,extent,count,(size,sha)in zip(streams,ranges,PRESERVED_ROWS,PRESERVED_INPUT_STREAMS):
        assert len(stream['rows'])==count+(280 if stream['case']==5 else 0)
        old_rows.append(dict(case=stream['case'],rows=stream['rows'][:count]))
        value=bytearray(data[extent['start']:extent['start']+size])
        offset=extent['count_at']-extent['start'];struct.pack_into('<I',value,offset,count)
        assert hashlib.sha256(value).hexdigest()==sha,(stream['case'],'old input stream changed')
        retained.extend(value);audit.append(dict(case=stream['case'],commands=count,bytes=size,sha256=sha))
    assert len(retained)==PRESERVED_INPUT_BYTES and hashlib.sha256(retained).hexdigest()==PRESERVED_INPUT_SHA256
    assert hashlib.sha256(json.dumps(old_rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()==PRESERVED_ROWS_SHA256
    return dict(commands=sum(PRESERVED_ROWS),input_bytes=len(retained),input_sha256=PRESERVED_INPUT_SHA256,streams=audit)


def preserved_output_stream(data,start,count_at,end,case):
    count=PRESERVED_ROWS[case];size,sha=PRESERVED_OUTPUT_STREAMS[case]
    value=bytearray(data[start:end]);struct.pack_into('<I',value,count_at-start,count)
    assert len(value)==size and hashlib.sha256(value).hexdigest()==sha,(case,'old output stream changed')
    return value


def independent_absence_coverage(rows,frames,statuses):
    assert len(rows)==280 and {row['independent_absence_bit']for row in rows}==set(ABSENCE_BITS)
    reports=[];failed_bits=set();restored_bits=set()
    for index,bit in enumerate(ABSENCE_BITS):
        first=index*20;group=rows[first:first+20];owner=frames[first:first+21];status=statuses[first:first+20]
        assert [row['code']for row in group]==[11,5,8,9,10,0,8,9,10,0,8,9,10,0,11,5,8,9,10,0]
        assert all(row['independent_absence_bit']==bit for row in group)
        assert status[0]is None and status[1]is None and status[14]is None and status[15]is None
        assert not owner[1]['mg']['active']and owner[1]['ticks']==0 and owner[1]['pose_count']==0
        assert owner[2]['pose_count']==36 and not owner[2]['mg']['active']
        missing=32767^(1<<bit)
        assert owner[5]['complete']['mask']==missing and owner[9]['complete']['mask']==missing
        absent_errors=[]
        for step in(5,9):
            before=owner[step];after=owner[step+1]
            # New real constructor plus actual selected-state descent makes
            # every one of the25 new leaf callbacks active, even on failure.
            assert after['mg']['current']==1 and set(range(8,33))<={v[0]for v in after['mg']['active']},(bit,step,'missing new-leaf callbacks')
            assert after['mg']['active'] and after['complete']['instances']>=25
            if bit<3:
                assert status[step]is None and after['complete']['mask']==32767,(bit,'source PublishPhysical did not restore its own flag/mirror/board record')
                assert after['animation_flags']is not None and after['animation_flags']&(1<<17),(bit,'completed board availability was not reflected in live actor flags')
                restored_bits.add(bit)
            else:
                assert after['complete']['mask']==missing,(bit,'missing upstream record was fabricated')
                if status[step]is not None:
                    absent_errors.append(status[step]);failed_bits.add(bit)
                    assert after['errors'][1],(bit,'missing producer did not reach MotionHost diagnostics')
                    for field in('ticks','pose_count','pose_sha256','hierarchy','local','packet','reset'):
                        assert after[field]==before[field],(bit,step,'failed Advance published '+field)
                    assert after['mg']!=before['mg'],(bit,step,'failure preceded the actual callback schedule')
        if bit>=3:assert absent_errors,(bit,'real missing record did not fail either reached callback')
        if bit==9:
            assert status[5]and 'BodySpin airborne branch requires actual prelanding physical outputs'in status[5]and 'Air leg extension requires actual prelanding output'not in status[5]
            assert status[9]and 'Air leg extension requires actual prelanding output'in status[9],(bit,'first AirLeg update vs descending prelanding branch')
        assert owner[13]['complete']['mask']==32767
        retained_error=status[13]
        if bit==7:assert retained_error and 'no successful Begin observation'in retained_error
        if bit==12:assert retained_error and 'ControlGrindCrouch Update before Begin'in retained_error and 'GrindControlFade Update before Begin'in retained_error
        if retained_error:
            for field in('ticks','pose_count','pose_sha256','hierarchy','local','packet','reset'):
                assert owner[14][field]==owner[13][field],(bit,'restored packet erased failed Begin '+field)
        # Actual FromSource discards the observed owner, then the genuine full
        # publication/Begin/Update schedule must recover with one new owner.
        assert owner[15]['ticks']==0 and owner[15]['pose_count']==0 and not owner[15]['mg']['active']
        assert status[19]is None and owner[20]['ticks']==1 and owner[20]['pose_count']==36
        assert owner[20]['complete']['mask']==32767 and not owner[20]['complete']['pending']
        assert set(range(8,33))<={v[0]for v in owner[20]['mg']['active']}and owner[20]['errors']==['','']
        reports.append(dict(bit=bit,absent_errors=absent_errors,restored_by_source=bit<3,retained_full_packet_error=retained_error,recovered_tick=owner[20]['ticks'],callback_identities=len(owner[20]['mg']['active'])))
    assert failed_bits==set(ABSENCE_BITS)-{0,1,2}and restored_bits=={0,1,2}
    return reports


def coverage(data,streams,stock_motion):
    r=Reader(data);assert r.word()==len(streams);reports=[];total=0;errors=Counter();all_handles=set();absence=set();constructor=Counter();retained=bytearray(data[:4]);absence_report=[]
    stock_operations=[n for n in converter.read_graph(stock_motion)if n['tag']in('behaviour','condition','hook')]
    stock_registration=[];unsupported=Counter()
    for operation in stock_operations:
        n=next((a['text']for a in operation['attributes']if a['name']=='name'),'__unknown__')
        supported=not(operation['tag']=='condition'and n in continuation.STOCK_UNSUPPORTED_CONDITIONS)
        stock_registration.append(int(supported))
        if not supported:unsupported[n]+=1
    assert len(stock_registration)==8305 and sum(stock_registration)==8234
    assert unsupported==continuation.STOCK_UNSUPPORTED_CONDITIONS
    for stream in streams:
        case=stream['case'];stream_start=r.at;assert r.status()is None;count_at=r.at;assert r.word()==len(stream['rows']);frames=[r.snapshot()];old_end=r.at if not PRESERVED_ROWS[case]else None;successful=[];failed=[];actor_ticks=0;statuses=[]
        for row_index,row in enumerate(stream['rows']):
            error=r.status();statuses.append(error)
            if error is None and row['code']==3:r.word()
            elif error is None and row['code']==5:r.matrices()
            frame=r.snapshot();previous=frames[-1];frames.append(frame);total+=1
            if row_index+1==PRESERVED_ROWS[case]:old_end=r.at
            if error:errors[error]+=1
            if row['code']==11:
                assert (error is None)==row['expected'],(case,row,error)
                constructor['success'if error is None else'failure']+=1
                if error is not None:assert frame['wire_sha256']==previous['wire_sha256'],(row,'failed FromSource overwrote caller owner')
                else:
                    assert frame['ticks']==0 and frame['pose_count']==0 and not frame['mg']['active'],(row,'new actor retained old controller/pose')
                continue
            if row['code']==0:
                if error is None:
                    assert frame['ticks']==previous['ticks']+1,(case,row,'tick publication order');successful.append(frame)
                    assert not frame['complete']['pending'],(case,row,'completed parameter queue not consumed')
                    assert frame['ag']['dt']==frame['mg']['dt'],(case,row,'two graph clocks differ')
                else:
                    assert frame['ticks']==previous['ticks'],(case,row,'failed Advance consumed tick');failed.append(frame)
                    assert frame['pose_sha256']==previous['pose_sha256']and frame['packet']==previous['packet'],(case,row,'failure published pose/packet')
                    if not row['complete']:
                        assert error=='Animation requires completed board speed output',error
                        assert frame['mg']==previous['mg']and frame['ag']==previous['ag'],(case,row,'speed failure ran controllers')
                    elif row['mask']!=32767:
                        absence.add(32767^row['mask'])
            for active in frame['mg']['active']:all_handles.add(tuple(active))
        if case==7:
            assert all(f['complete']['registration']==stock_registration for f in frames),(case,'stock operation registration differs from the original factory')
        else:
            assert all(all(f['complete']['registration'])for f in frames),(case,'fixture operation missing full registration')
        if case<6:
            assert len(successful)>TICKS//2,(case,len(successful))
            assert len({f['pose_sha256']for f in successful})>32,(case,'full new-owner pose stayed static')
            assert {1,2}<={f['mg']['current']for f in frames},(case,'original transitions not reached')
            assert len({v[1]for f in frames for v in f['mg']['active']})>len(FAMILIES[case]),(case,'new instances not reallocated')
            assert any(f['feedback']['flags']&0x01000000 for f in frames),(case,'shared score owner missing')
            assert any(f['flags'][3]for f in frames)and any(not f['flags'][3]for f in frames),(case,'shared graph flags not entered/released')
            assert any(f['maps'][2]['values']['A']is not None for f in frames),(case,'AG output not accepted by live owner')
            if case in(4,5):
                assert len({tuple(f['complete']['controls'])for f in frames})>2,(case,'shared wipeout control owner did not progress')
            if case==3:
                assert any(a[0][:5]==continuation.name('FsCrooked')for f in frames for a in f['packet_attributes']),(case,'real grind packet not published')
        elif case>=8:
            assert len(failed)==3,(case,'source missing-producer callback unexpectedly succeeded')
            expected='MotionGraph stock gameplay producer '+continuation.MISSING[case-8]+' is not implemented'
            actual=[e for row,e in zip(stream['rows'],statuses)if row['code']==0]
            assert all(e and all(line.endswith(expected)for line in e.splitlines())for e in actual),(case,actual)
        elif case==7:
            assert not stream['rows'];assert frames[0]['complete']['instances']>3000
        retained.extend(preserved_output_stream(data,stream_start,count_at,old_end,case))
        if case==5:absence_report=independent_absence_coverage(stream['rows'][PRESERVED_ROWS[case]:],frames[PRESERVED_ROWS[case]:],statuses[PRESERVED_ROWS[case]:])
        reports.append(dict(case=case,commands=len(stream['rows']),successful_advances=len(successful),failed_advances=len(failed),pose_variants=len({f['pose_sha256']for f in successful}),active_identities=len({tuple(v)for f in frames for v in f['mg']['active']}),registered_operations=len(frames[0]['complete']['registration']),instances=frames[0]['complete']['instances']))
    assert r.at==len(data),(r.at,len(data));assert constructor['failure']>=30 and constructor['success']>=10,constructor
    assert len(absence)>=8,absence
    assert len(retained)==PRESERVED_OUTPUT_BYTES and hashlib.sha256(retained).hexdigest()==PRESERVED_OUTPUT_SHA256
    return dict(streams=reports,commands=total,errors=dict(errors),constructor=dict(constructor),absence_masks=sorted(absence),active_identities=len(all_handles),independent_absence=absence_report,preserved_original_output=dict(commands=sum(PRESERVED_ROWS),bytes=len(retained),sha256=PRESERVED_OUTPUT_SHA256))


def extract(path,start,end):
    body=path.read_bytes();a=body.index(start);b=body.index(end,a);assert body.count(start)==1 and body.count(end)==1,(path,start,end)
    value=body[a:b];return value,dict(path=path.relative_to(PLUGIN).as_posix(),source_sha256=digest(path),start=a,end=b,bytes=len(value),sha256=hashlib.sha256(value).hexdigest(),start_marker=start.decode(),end_marker=end.decode())


def stage_reference(output):
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip());rel=(PLUGIN/'ThirdParty/skate-runtime').relative_to(root).as_posix();revision=subprocess.check_output(['git','rev-parse',REFERENCE_REVISION],cwd=root,text=True).strip()
    archive=subprocess.check_output(['git','archive',f'{revision}:{rel}'],cwd=root);source=output/'reference-source'
    if source.exists():shutil.rmtree(source)
    source.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive))as stream:stream.extractall(source,filter='data')
    originals={p.relative_to(source).as_posix():digest(p)for p in sorted(source.rglob('*.rs'))};crate=source/'atelier-host';host=source/'crates/skate-host/src';staged={}
    observer=TESTS/'Reference/skater_animation_complete_observer.rs';ob=observer.read_bytes();marker=b'// [animation]\n';assert ob.startswith(b'// [motion]\n')and ob.count(marker)==1;parts=ob.split(marker)
    additions={'graph_host/motion.rs':parts[0].removeprefix(b'// [motion]\n'),'graph_host/motion_animation.rs':parts[1]}
    for p in sorted(host.rglob('*.rs')):
        path=p.relative_to(host).as_posix()
        if path in('lib.rs','main.rs'):continue
        dest=crate/'src'/path;dest.parent.mkdir(parents=True,exist_ok=True);body=p.read_bytes();extra=b'\n'+additions[path]if path in additions else b'';dest.write_bytes(body+extra);assert dest.read_bytes()[:len(body)]==body
        staged[path]=dict(original_prefix_bytes=len(body),original_prefix_sha256=digest(p),append_sha256=hashlib.sha256(extra).hexdigest(),generated_sha256=digest(dest))
    prefix,base=extract(TESTS/'Reference/skater_animation_probe.rs',b'//! Direct frozen',b'fn run()->Result<(),String> {')
    physical,publication=extract(TESTS/'Reference/motion_graph_continuation_probe.rs',b'fn physical(r:&mut Input,h:&mut MotionHost)',b'fn snapshot(o:&mut Output')
    probe=TESTS/'Reference/skater_animation_complete_probe.rs';generated=crate/'src/migration_probe.rs';generated.write_bytes(prefix+physical+probe.read_bytes())
    assert generated.read_bytes()[:len(prefix)]==prefix and generated.read_bytes()[len(prefix):len(prefix)+len(physical)]==physical
    cargo=crate/'Cargo.toml';cargo.write_text(cargo.read_text()+'''
skate-core={path="../crates/skate-core"}
skate-data={path="../crates/skate-data"}
skate-net={path="../crates/skate-net"}
half="2.7.1"
bevy={version="0.19",default-features=false,features=["std","multi_threaded","bevy_log"]}
[[bin]]
name="skater-animation-complete-reference"
path="src/migration_probe.rs"
''')
    return source,crate,dict(reference_revision=revision,source_archive_sha256=hashlib.sha256(archive).hexdigest(),original_source_sha256=originals,staged_host_prefixes=staged,helper_extractions=[base,publication],probe_sha256=digest(probe),observer_sha256=digest(observer),generated_probe_sha256=digest(generated))


def stage_native(output):
    snap=output/'native-source'
    if snap.exists():shutil.rmtree(snap)
    snap.mkdir()
    for p in[*sorted(CODE.glob('*.h')),*[CODE/(n+'.cpp')for n in UNITS]]:shutil.copy2(p,snap/p.name)
    prefix,base=extract(TESTS/'Native/skater_animation_probe.cpp',b'#include "SkaterAnimation.h"',b'int main(int argc,char** argv)')
    physical,publication=extract(TESTS/'Native/motion_graph_continuation_probe.cpp',b'void Physical(Input &r, MotionGraphContinuationHost &h)',b'void Snapshot(Output &o, MotionGraphContinuationHost &h,')
    (snap/'skater_animation_facade_helpers.h').write_bytes(prefix);(snap/'motion_graph_complete_publication.h').write_bytes(physical)
    probe=TESTS/'Native/skater_animation_complete_probe.cpp';shutil.copy2(probe,snap/probe.name)
    return snap,dict(immutable_native_sources={p.name:digest(p)for p in sorted(snap.iterdir())},units=UNITS,helper_extractions=[base,publication],probe_sha256=digest(probe))


def build_probes(output,target):
    source,crate,reference=stage_reference(output);snap,native=stage_native(output)
    subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(crate/'Cargo.toml'),'--target-dir',str(target.resolve()),'--bin','skater-animation-complete-reference'],check=True)
    for path,sha in reference['original_source_sha256'].items():assert digest(source/path)==sha,path
    for path,row in reference['staged_host_prefixes'].items():
        dest=crate/'src'/path;original=source/'crates/skate-host/src'/path;assert digest(dest)==row['generated_sha256']and dest.read_bytes()[:original.stat().st_size]==original.read_bytes(),path
    rust=output/'skater-animation-complete-reference';shutil.copy2(target.resolve()/'release/skater-animation-complete-reference',rust);reference.update(binary_sha256=digest(rust),cargo_lock_sha256=digest(crate/'Cargo.lock'),compiler=subprocess.check_output(['rustc','+1.97.1','-vV'],text=True).strip())
    binary=output/'skater-animation-complete-native';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snap),*[str(snap/(n+'.cpp'))for n in UNITS],str(snap/'skater_animation_complete_probe.cpp'),'-o',str(binary)],check=True)
    for path,sha in native['immutable_native_sources'].items():assert digest(snap/path)==sha,path
    native['binary_sha256']=digest(binary)
    (output/'reference-provenance.json').write_text(json.dumps(reference,indent=2)+'\n');(output/'native-provenance.json').write_text(json.dumps(native,indent=2)+'\n');return binary,rust


def prepare(output,assets,samples):
    stock=assets/'private/stock';collections=json.loads((stock/'skater-collections.json').read_text());loaders=continuation.loader_fixtures(collections)
    (output/'settings.native').write_bytes(converter.encode_settings(stock/'skater-collections.json'))
    for i,(label,data,success)in enumerate(loaders):
        directory=output/f'settings-{i}';directory.mkdir(exist_ok=True);_,path=continuation.stage_assets(assets,directory,data)
        (output/f'settings-{i}.native').write_bytes(converter.encode_settings(path))
    graphs={i:fixtures(i)for i in range(12)}
    graphs[7]=(stock/'data/state/ActionGraph_OnBoard.stategraph',stock/'data/state/MotionGraph_OnBoard.stategraph')
    bad=extra_operation('GrindControlFade');bad['attributes']=[a for a in bad['attributes']if a['name']!='twistAnimAttribute']
    bad_action=element('state','root',children=[scheduler.behavior('CreateTrickIntentFromGesture',[attribute('group','CompleteUnknown')])])
    good_action,good_motion=fixtures(6)
    graphs[12]=(good_action,element('state','root',children=[bad]))
    graphs[13]=(bad_action,good_motion)
    graphs[14]=(bad_action,element('state','root',children=[bad]))
    factory_rows=[(12,'motion-factory-before-settings',0),(14,'motion-factory-before-action',0xffffffff),
        (13,'settings-before-action',0),(13,'action-factory-after-motion',0xffffffff)]
    for i,pair in graphs.items():
        for kind,g in zip(('action','motion'),pair):
            reference=output/f'actor-{i}.{kind}.reference';reference.write_bytes(g.read_bytes()if isinstance(g,Path)else original_graph(g))
            (output/f'actor-{i}.{kind}.native').write_bytes(converter.encode_graph(converter.read_graph(reference)))
    prefix,cases,streams=corpus(samples,loaders,factory_rows);raw=encode(prefix,cases);preserved_input(raw,streams)
    (output/'input.bin').write_bytes(raw);(output/'commands.json').write_text(json.dumps(streams,indent=2)+'\n')
    return prefix,cases,streams,loaders


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in('assets','samples','metadata','output','target-dir'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--preflight-only',action='store_true');args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    prefix,cases,streams,loaders=prepare(output,args.assets.resolve(),args.samples.resolve());raw=encode(prefix,cases)
    if args.preflight_only:
        _,_,reference=stage_reference(output);_,native=stage_native(output)
        files=[CODE/('SkaterAnimation'+ext)for ext in('.h','.cpp')]+[CODE/'GraphIntentOperations.cpp',TESTS/'check_skater_animation_complete_parity.py',TESTS/'Native/skater_animation_complete_probe.cpp',TESTS/'Reference/skater_animation_complete_probe.rs',TESTS/'Reference/skater_animation_complete_observer.rs']
        report=dict(preflight=True,streams=len(streams),commands=sum(len(s['rows'])for s in streams),units=len(UNITS),loader_fixtures=len(loaders),input_bytes=len(raw),input_sha256=hashlib.sha256(raw).hexdigest(),preserved_original_input=preserved_input(raw,streams),additive_absence_commands=280,frozen_files={p.relative_to(PLUGIN).as_posix():digest(p)for p in files},reference=reference,native=native)
        (output/'preflight.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items()if k not in('reference','native')},indent=2));return
    for marker in('result.json','first-divergence.json'):(output/marker).unlink(missing_ok=True)
    native,rust=build_probes(output,args.target_dir)
    expected=subprocess.check_output([str(rust),str(args.assets.resolve()),str(output)],input=raw)
    actual=subprocess.check_output([str(native),str(args.samples.resolve()),str(args.metadata.resolve()),str(output),str(output/'settings.native'),str(args.assets.resolve())],input=raw)
    (output/'reference.bin').write_bytes(expected);(output/'native.bin').write_bytes(actual)
    if expected!=actual:
        at=next((i for i,(a,b)in enumerate(zip(expected,actual))if a!=b),min(len(expected),len(actual)));report=dict(byte=at,reference_bytes=len(expected),native_bytes=len(actual),reference_hex=expected[max(0,at-16):at+48].hex(),native_hex=actual[max(0,at-16):at+48].hex());(output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
    report=dict(passed=True,coverage=coverage(expected,streams,args.assets/'private/stock/data/state/MotionGraph_OnBoard.stategraph'),streams=len(streams),output_bytes=len(actual),output_sha256=hashlib.sha256(actual).hexdigest(),input_sha256=hashlib.sha256(raw).hexdigest(),preserved_original_input=preserved_input(raw,streams),additive_absence_commands=280,loader_fixtures=len(loaders),comparison='Direct whole unchanged SkaterAnimation::from_source/advance, complete MotionHost constructor and sole original AG/MG controllers, all stock registrations, full sampled stock pose/hierarchy/local matrices/packet, same shared animation/hands/RNG/conditions/allocation identity and retained continuation owners.',physical_boundary='New producer fields are published explicitly before Advance at the original physics/animation_phase boundary; SkaterAnimation PublishPhysical remains unchanged. Absent records remain absent.',limitations='The graph/actor schedule is proved with completed canonical caller-publication records. Their upstream physical producer/global frame and complete gameplay session remain outside this bounded check. The four original missing producers preserve actual failures.',reference_provenance='reference-provenance.json',native_provenance='native-provenance.json')
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
