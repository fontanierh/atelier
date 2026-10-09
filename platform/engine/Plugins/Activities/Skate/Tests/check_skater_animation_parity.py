#!/usr/bin/env python3
"""Compare the complete supported simulation actor graph/tree/pose/packet schedule.

The reference calls untouched SkaterAnimation::from_source and ::advance with
the real original ActionHost and MotionHost. Project stock data is used
only by C++; optional override JSON is the project's own format. This bounded
fixture check does not establish complete authored gameplay or session parity.
Run compilation/execution through atelier.safety.
"""
import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tarfile
from check_graph_parity import attribute, element, original_graph
from check_gesture_parity import converter, PLUGIN
from check_animation_playback_parity import Stream,bits
from check_animation_trees_parity import name as attribute_name
from session_parity import REFERENCE_REVISION,digest

CODE=PLUGIN/'Source/AtelierSkate/Private/Simulation'
QUERIES=('A','X','Y','Clock','Const','PriorTrick','PriorBoard','Turn','RawTurn','HardTurn','enable','exit','push','other','TweakX','TweakY','Marker','')
TICKS=128
FIXTURES=12


def behavior(name,values=(),children=()):return element('behaviour',name,values,children)
def condition(name,values=()):return element('condition',name,[attribute('mask','always'),*values])
def expression(conditions):return element('expression',attributes=[attribute('op','and')],children=conditions)
def transition(target,conditions):return element('transition',attributes=[attribute('target',target),attribute('priority','urgent')],children=[expression(conditions)])


def fixtures(case):
    action_root=[behavior('CreateMGIntentFromAGIntent',[attribute('AGIntent','push'),attribute('MGIntent','A'),attribute('scale',bits=bits(.5+case*.125))]),
        behavior('CreateMGIntentFromAGIntent',[attribute('AGIntent','other'),attribute('MGIntent','X'),attribute('defaultValue',bits=bits(.137))]),
        behavior('CreateMGTimeIntentFromAGIntent',[attribute('AGIntent','push'),attribute('MGIntent','Clock')]),
        behavior('CreateConstMGIntent',[attribute('MGIntent','Const'),attribute('value',bits=bits(.137+case*.03125)),attribute('onUpdate',boolean=case%2)])]
    action_trick=element('state','trick',children=[expression([condition('IsTricking')]),
        behavior('CreateConstMGIntent',[attribute('MGIntent','PriorTrick'),attribute('value',bits=bits(1))]),
        transition('idle',[condition('HasAGIntent',[attribute('intent','exit')])])])
    action_board=element('state','board',children=[expression([condition('HasAnimAttribute',[attribute('attribute','ANIMBOARDBACKWARD'),attribute('greaterEqual',bits=0)])]),
        behavior('CreateConstMGIntent',[attribute('MGIntent','PriorBoard'),attribute('value',bits=bits(1))])])
    action_idle=element('state','idle',children=[transition('trick',[condition('IsTricking')]),
        transition('board',[condition('HasAnimAttribute',[attribute('attribute','ANIMBOARDBACKWARD'),attribute('greaterEqual',bits=0)])])])
    action=element('state','root',children=action_root+[action_trick,action_board,action_idle])
    clips=('R_STAND_IDLE2_N_0_CYC','F_FLIP_FS_GRAB_VARIAL_OUT_HIGH','BR_DISMOUNT_DBL_INTO_BR_AIR',
        'BR_DISMOUNT_STALE_INTO_BR_AIR','R_ANTIC_OLLIE_N_0_CYC','360FLIP_D_HIGH_G')
    def play(name,kind='play'):
        return behavior('PlayAnimation',[attribute('anim',name),attribute('transType',kind),attribute('time',bits=bits(.137+case*.015625)),
            attribute('applyPosture',boolean=case%2),attribute('playBackSpeed',bits=bits(.5+case*.125)),
            attribute('switchAnim',clips[(case+1)%6]),attribute('mirrorAnim',clips[(case+2)%6]),attribute('noBoardAnim',clips[(case+3)%6]),
            attribute('blendMatchPhase',boolean=case%3==1)],
            [element('param',attributes=[attribute('from','intent'),attribute('intent','A'),attribute('rename','probe'),attribute('defaultValue',bits=bits(.113))]),
             element('param',attributes=[attribute('from','lastAnim'),attribute('attribute','ANIMTRANSZ'),attribute('rename','lastZ'),attribute('defaultValue',bits=bits(.317))])])
    motion_root=[play('R_STAND_IDLE2_N_0_CYC'),behavior('CreateAttribute',[attribute('attName','Marker'),attribute('always',bits=bits(case*.125))]),
        behavior('AttachIntent',[attribute('intent','A'),attribute('attr','probe'),attribute('set',boolean=1)]),
        behavior('FilterMotionGraphIntent',[attribute('intent','X'),attribute('filteredIntent','TweakX'),attribute('blend',bits=bits(.5))]),
        behavior('UpdateTimeSinceTeleport'),behavior('UpdateTimeSinceKickturn'),behavior('UpdateManualOutTimer')]
    active_ops=[]
    if case>=6:active_ops.extend([behavior('ResetSkaterAnimation'),behavior('ResetToGivenStance')])
    active_ops.extend([play(clips[case%6],('play','blend','sequence','channelblend')[case%4]),
        behavior('IsDoingTrick'),behavior('UpdateIsWeightOnNose'),behavior('SetDark'),behavior('IsAnticipating'),
        behavior('SetGrabType',[attribute('grab',('FS','BS','Nose','Tail')[case%4])]),
        behavior('CreateAttribute',[attribute('attName','Phase'),attribute('begin',bits=bits(.137)),attribute('update',bits=bits(.731)),attribute('end',bits=bits(.317)),attribute('set',boolean=1)]),
        behavior('HandBusy',[attribute('hand','bs' if case%2 else 'fs')]),behavior('ApplyingBodyTilt')])
    motion_active=element('state','active',children=[expression([condition('HasAGIntent',[attribute('intent','enable')])]),*active_ops,
        transition('idle',[condition('HasAGIntent',[attribute('intent','exit')])])])
    motion_idle=element('state','idle',children=[play('R_ANTIC_OLLIE_N_0_CYC',('play','blend')[case%2]),
        behavior('ResetTimeSinceKickturn'),transition('active',[condition('HasAGIntent',[attribute('intent','enable')])])])
    return action,element('state','root',children=motion_root+[motion_active,motion_idle])


class Writer(Stream):
    def map(self,values):
        self.word(len(values))
        for name,v in values:self.string(name);self.float(v)
    def vector(self,values):
        for v in values:self.float(v)
    def physical(self,case,tick,complete=True,forward_speed=None):
        self.word(complete)
        if complete:self.vector((.731+case,(-1 if tick%2 else 1)*.317 if forward_speed is None else forward_speed,.137+tick*.03125))
        self.word(1);self.word((1,2,5,6)[(tick//13+case)%4]);self.word(tick%11==0);self.string('FiftyFifty' if tick%11==0 else '')
        self.word(1);self.float(tick*.137)
        for v in ((tick//5+case)%2,(tick//7+case)%2):self.word(1);self.word(v)
        self.word(1);self.float(.731);self.word(tick%9==0);self.float(30)
        self.word(0);self.word(0) # State77/State16 are separate physics producers.
        self.vector((.137,.317,.731,.113,.719,-.317))
        self.vector((.113,.731,.137,.317,.719,.03125,.113,1.137+case*.125))
        self.float(.137);self.vector((.317,.731,.113,.719));self.word(tick%7==0);self.vector((.137,.317,.731,.113,.719,.03125,.517,.973))
        self.float(.317);self.float(.731);self.word((1,2)[tick%2])
        self.word((1,2,5,6)[(tick//13+case)%4]);self.word(503);self.word(tick%3==0)
        for vector in ((0,0,1,0),(.137,.317,-.731,0),(.731,.113,.317,0)):self.vector(vector)
        self.float(1.973+case);self.word(tick%2);self.word((tick//3)%2)
        for vector in ((-.137,.317,.731,1),(.137,.317,-.731,1),(0,.317,0,1),(0,1,0,0),(0,0,1,0)):self.vector(vector)
        self.word((tick//17)%2);self.word((tick//9+case)%2);self.word((tick//11+case)%2);self.float(tick*.113)
    def channel(self,case):
        self.word(case%3-1);self.word(case%2);self.word((case//2)%2);self.float(.731+case*.03125);self.float(.137);self.word(case%2);self.float(.317);self.word((case//2)%2);self.word(1)


def corpus(samples):
    manifest=json.loads((samples/'samples-manifest.json').read_text());prefix=Writer();prefix.word(len(manifest['clips']))
    for clip in manifest['clips']:prefix.string(clip['name'])
    prefix.word(len(QUERIES))
    for name in QUERIES:prefix.string(name)
    cases=[];counts=Counter()
    for case in range(FIXTURES):
        ops=[]
        def new(op):s=Writer();s.word(op);ops.append(s);counts[op]+=1;return s
        new(5);new(6).word(case%5);s=new(1);s.word(case%2);s.word(case%4)
        for tick in range(TICKS):
            if tick in (31,79):s=new(1);s.word((case+tick)%2);s.word((case+tick)%5)
            if tick in (9,38,87):new(2).word((case+tick)%3)
            if tick in (16,17,72):
                s=new(3);s.string('Overlay' if tick!=72 else 'SkitchAntic');s.string('R_ANTIC_OLLIE_N_0_CYC');s.channel(case)
            if tick in (34,101):s=new(4);s.string('overlay');s.float(.137);s.word(tick==101)
            if tick in (63,):new(7)
            values=[('push',((tick+case)%11-5)*.125),('other',((tick+case*3)%13-6)*.125)]
            if tick%23<15:values.append(('enable',0))
            if tick%23==11:values.append(('exit',1))
            if tick%7==0:values.append(('WeightOnNose',0))
            s=new(0);s.float((0,1/60,.05,.1)[(tick+case)%4]);s.map(values);s.physical(case,tick,complete=tick not in (45,97))
        encoded=Writer();encoded.word(case);encoded.string(('Loose','Gonzo','Aggressive','')[case%4]);encoded.word(len(ops))
        for s in ops:encoded.data.extend(s.data)
        cases.append(bytes(encoded.data))
    return prefix,cases,counts


def encode(prefix,cases):return b'ATASKTR1'+bytes(prefix.data)+len(cases).to_bytes(4,'little')+b''.join(cases)


def build_reference(output,target):
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip());relative=(PLUGIN/'ThirdParty/skate-runtime').relative_to(root).as_posix();revision=subprocess.check_output(['git','rev-parse',REFERENCE_REVISION],cwd=root,text=True).strip()
    archive=subprocess.check_output(['git','archive',f'{revision}:{relative}'],cwd=root);source=output/'reference-source'
    if source.exists():shutil.rmtree(source)
    source.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:stream.extractall(source,filter='data')
    originals={p.relative_to(source).as_posix():digest(p) for p in sorted(source.rglob('*.rs'))};crate=source/'atelier-host';host=source/'crates/skate-host/src';staged={}
    for original in sorted(host.rglob('*.rs')):
        relative=original.relative_to(host)
        if relative.as_posix() in ('lib.rs','main.rs'):continue
        destination=crate/'src'/relative;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(original,destination);staged[relative.as_posix()]=digest(original);assert digest(destination)==digest(original)
    cargo=crate/'Cargo.toml';cargo.write_text(cargo.read_text()+'\nskate-core={path="../crates/skate-core"}\nskate-data={path="../crates/skate-data"}\nskate-net={path="../crates/skate-net"}\nhalf="2.7.1"\nbevy={version="0.19",default-features=false,features=["std","multi_threaded","bevy_log"]}\n\n[[bin]]\nname="skater-animation-reference"\npath="src/migration_probe.rs"\n')
    probe=PLUGIN/'Tests/Reference/skater_animation_probe.rs';shutil.copyfile(probe,crate/'src/migration_probe.rs')
    subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(cargo),'--target-dir',str(target.resolve()),'--bin','skater-animation-reference'],check=True)
    for p,sha in originals.items():assert digest(source/p)==sha,f'Original implementation changed: {p}'
    for p,sha in staged.items():assert digest(crate/'src'/p)==sha,f'Staged production module changed: {p}'
    binary=output/'skater-animation-reference';shutil.copy2(target.resolve()/'release/skater-animation-reference',binary)
    report=dict(reference_revision=revision,source_archive_sha256=hashlib.sha256(archive).hexdigest(),original_source_sha256=originals,staged_host_modules_sha256=staged,probe_sha256=digest(probe),binary_sha256=digest(binary),cargo_lock_sha256=digest(crate/'Cargo.lock'),compiler=subprocess.check_output(['rustc','+1.97.1','-vV'],text=True).strip(),boundary='Calls original SkaterAnimation::from_source/advance directly with production ActionHost/MotionHost/controllers/PoseEvaluator. No production methods, bodies, callbacks, or modules are substituted.')
    (output/'reference-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return binary


def build_simulation(output):
    live=CODE;code=output/'simulation-source'
    if code.exists():shutil.rmtree(code)
    code.mkdir();files=('SimulationMath','AnimationName','Intents','Input','InputIntentions','NameId','Settings','Graph','CompiledGraph','GraphController','GraphConditions','GraphGestureOperations','GraphIntentOperations','ActionGraphFrame','GraphMotionSliding','AnimationSamples','AnimationMetadata','AnimationPlayback','AnimationPlaybackParameters','AnimationTrees','AnimationChannels','MotionAnimation','MotionAnimationOperations','MotionFrame','GraphMotionName','GraphMotionConditions','GraphMotionPhysicalConditions','GraphMotionSpecialConditions','RidingAnimation','RidingAnimationSettings','GraphMotionFeedbackOperations','GraphMotionScoreOperations','GraphMotionPushOperations','GraphMotionGestureOperations','MotionGraphHost','AnimationPose','AnimationPoseAuthored','AnimationPoseJson','AnimationPublication','SkaterAnimation')
    files=tuple(dict.fromkeys((*files,'StockSettingsReader','AnimationRidingAuxiliary','AnimationKickturn',
        'AnimationAirborne','AnimationAirborneSettings','WipeoutOrientation','GraphMotionOffboardTiming',
        'GraphMotionTrickLifecycle','GraphMotionGrindOperations','GraphMotionOffboardWipeoutOperations',
        'GraphMotionToggleBoard','MotionGraphContinuationOperations','MotionGraphContinuationSettings',
        'MotionGraphContinuationHost')))
    for path in list(live.glob('*.h'))+[live/(f+'.cpp') for f in files]:shutil.copyfile(path,code/path.name)
    probe=code/'skater_animation_probe.cpp';shutil.copyfile(PLUGIN/'Tests/Simulation/skater_animation_probe.cpp',probe);snapshot={p.name:digest(p) for p in sorted(code.iterdir())};(output/'simulation-source-provenance.json').write_text(json.dumps(snapshot,indent=2)+'\n')
    binary=output/'skater-animation-cpp';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(code),*[str(code/(f+'.cpp')) for f in files],str(probe),'-o',str(binary)],check=True);return binary


class Reader:
    def __init__(self,data):self.data=data;self.at=0
    def word(self):v=struct.unpack_from('<I',self.data,self.at)[0];self.at+=4;return v
    def words(self,n):return [self.word() for _ in range(n)]
    def string(self):n=self.word();v=self.data[self.at:self.at+n].decode();self.at+=n;return v
    def optional(self):return self.word() if self.word() else None
    def status(self):return None if self.word() else self.string()
    def matrices(self):n=self.word();values=self.words(n*16);return n,hashlib.sha256(struct.pack('<'+'I'*len(values),*values)).hexdigest()
    def attributes(self):
        out=[]
        for _ in range(self.word()):
            record=self.words(10);payload=[self.optional() for _ in range(6)];out.append((record,payload))
        return out
    def frame(self):
        dt,current,last=self.words(3);times=[self.optional() for _ in range(self.word())];active=[self.words(2) for _ in range(self.word())];return dict(dt=dt,current=current,last=last,times=times,active=active)
    def mapping(self):return dict(size=self.word(),values=dict(zip(QUERIES,[self.optional() for _ in QUERIES])))
    def snapshot(self):
        ticks=self.words(2);stance=self.words(4);ag,mg=self.frame(),self.frame();actiontick=self.words(2);tricking=self.optional();maps=[self.mapping() for _ in range(4)];errors=[self.string(),self.string()];flags=self.words(9);timers=self.words(5);self.words(7)
        animflags=self.optional();orientation=self.words(4);grab=self.optional();posture=self.words(2);name=self.string() if self.word() else None
        clocks=[]
        for _ in range(2):
            error=self.status();clocks.append(dict(error=error,value=self.word() if error is None else None))
        transition=self.word();property=self.words(3);channels=[self.words(4) for _ in range(4)];cached=self.attributes();prior_cached=self.attributes();graph_attrs=[self.words(6) for _ in range(self.word())];packet_attrs=self.attributes();pose_count=self.word();pose=self.words(pose_count*12);count=self.word();hierarchy=self.matrices();local=self.matrices();packet=self.words(11);reset=self.words(39)
        return dict(ticks=ticks[0]|ticks[1]<<32,stance=stance,ag=ag,mg=mg,action_tick=actiontick[0]|actiontick[1]<<32,tricking=tricking,maps=maps,errors=errors,flags=flags,timers=timers,animation_flags=animflags,orientation=orientation,grab=grab,posture=posture,name=name,clocks=clocks,transition=transition,property=property,channels=channels,cached=cached,prior_cached=prior_cached,graph_attributes=graph_attrs,packet_attributes=packet_attrs,pose_count=pose_count,pose_sha256=hashlib.sha256(struct.pack('<'+'I'*len(pose),*pose)).hexdigest(),bone_count=count,hierarchy=hierarchy,local=local,packet=packet,reset=reset)


def coverage(data,counts):
    r=Reader(data);fixtures=[];poses=set();errors=Counter();total=0;successes=0
    for case in range(r.word()):
        steps=r.word();states=[];frames=[r.snapshot()]
        for _ in range(steps):
            # Read the operation from the source corpus so variable result
            # payloads remain independent of candidate-selected state.
            op=counts[case].pop(0);error=r.status()
            if error is not None:errors[error]+=1
            elif op==3:r.word()
            elif op==5:r.matrices()
            snapshot=r.snapshot();frames.append(snapshot);total+=1
            if op==0 and error is None:successes+=1
        advances=[f for f in frames if f['pose_count']]
        poses.update(f['pose_sha256'] for f in advances);agstates={f['ag']['current'] for f in frames};mgstates={f['mg']['current'] for f in frames}
        assert {1,2}<=mgstates,(case,mgstates)
        assert len({f['pose_sha256'] for f in advances})>32,(case,'static pose trace')
        assert all(f['bone_count']==36 and f['hierarchy'][0]==36 and f['local'][0]==36 for f in frames)
        assert any(f['prior_cached'] for f in frames) and any(f['cached'] for f in frames)
        assert any(f['packet_attributes'] for f in frames)
        probe_name=attribute_name('probe');attached=[]
        for f in frames:
            values=[a[5] for a in f['graph_attributes'] if a[:5]==probe_name]
            if values:
                # Attach reads the live MotionAnimation map. EndAll on AG
                # clears its output without republishing/clearing MG or the
                # retained graph packet, so the AG map may already be empty.
                assert values==[f['maps'][2]['values']['A']],(case,'actual AttachIntent probe/value',values)
                attached.extend(values)
        assert len(set(attached))>8,(case,'AttachIntent never emitted changing probe values')
        assert {0,1}<={f['flags'][3] for f in frames}
        assert any(f['channels'][0][0] for f in frames) and any(not f['channels'][0][0] for f in frames)
        assert frames[-1]['ticks']==TICKS-2,(case,frames[-1]['ticks'])
        fixtures.append(dict(case=case,operations=steps,ticks=frames[-1]['ticks'],action_states=sorted(agstates),motion_states=sorted(mgstates),pose_variants=len({f['pose_sha256'] for f in advances}),instances=len({a[1] for f in frames for a in f['mg']['active']}),board_flips=sorted({f['packet'][4] for f in frames}),mirror_values=sorted({f['packet'][5] for f in frames}),switch_values=sorted({f['packet'][6] for f in frames})))
    assert r.at==len(data),(r.at,len(data));assert errors=={'Animation requires completed board speed output':FIXTURES*2},errors
    return dict(fixtures=fixtures,operations=total,successful_advances=successes,pose_variants=len(poses),errors=dict(errors))


def operation_codes(case):
    # Must match corpus construction; no reference or candidate result decides
    # which extra payload to consume. This list is also checked against input.
    codes=[5,6,1]
    for tick in range(TICKS):
        if tick in (31,79):codes.append(1)
        if tick in (9,38,87):codes.append(2)
        if tick in (16,17,72):codes.append(3)
        if tick in (34,101):codes.append(4)
        if tick==63:codes.append(7)
        codes.append(0)
    return codes


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path,required=True);p.add_argument('--samples',type=Path,required=True);p.add_argument('--metadata',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--target-dir',type=Path,required=True);args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    rust=build_reference(output,args.target_dir);simulation=build_simulation(output);settings=output/'settings.simulation';settings.write_bytes(converter.encode_settings(args.assets/'private/stock/skater-collections.json'))
    for case in range(FIXTURES):
        for kind,graph in zip(('action','motion'),fixtures(case)):
            original=output/f'actor-{case}.{kind}.reference';original.write_bytes(original_graph(graph));(output/f'actor-{case}.{kind}.simulation').write_bytes(converter.encode_graph(converter.read_graph(original)))
    prefix,cases,counts=corpus(args.samples);commands=encode(prefix,cases);(output/'input.bin').write_bytes(commands)
    def reference(data):return subprocess.check_output([str(rust),str(args.assets.resolve()),str(output)],input=data)
    def candidate(data):return subprocess.check_output([str(simulation),str(args.samples.resolve()),str(args.metadata.resolve()),str(output),str(settings),str(args.assets.resolve())],input=data)
    expected=reference(commands);actual=candidate(commands);(output/'reference.bin').write_bytes(expected);(output/'simulation.bin').write_bytes(actual)
    if actual!=expected:
        lo=0;hi=len(cases)
        while hi-lo>1:
            mid=(lo+hi)//2;data=encode(prefix,cases[lo:mid])
            if reference(data)==candidate(data):lo=mid
            else:hi=mid
        (output/'first-divergence-input.bin').write_bytes(encode(prefix,cases[lo:hi]));first=next((i for i,(a,e) in enumerate(zip(actual,expected)) if a!=e),min(len(actual),len(expected)));raise AssertionError(f'SkaterAnimation differs at byte {first}, fixture {lo}; isolated input saved')
    report=dict(passed=True,coverage=coverage(expected,[operation_codes(i) for i in range(FIXTURES)]),counts=counts,output_bytes=len(actual),output_sha256=hashlib.sha256(actual).hexdigest(),comparison='Direct original actor initialization and complete AG→MG→parameters→clocks→cache→pose→hierarchy→attributes→selective reset→fixed-step packet publication, with live controllers/channels/stance/checkpoint state and exact matrices.',limitations='Supported graph fixtures only. The simulation physical-backed graph leaves not yet ported retain explicit errors. Actual board/rider producer scheduling and complete authored gameplay/session parity remain pending.',stock_data_format='Project ATSKEL01/ATCLIP01/ATMETA01; original readers exist only in frozen oracle.',override_format='Project-authored custom/mod JSON, not an EA stock data format.',reference_provenance_sha256=digest(output/'reference-provenance.json'),simulation_source_provenance_sha256=digest(output/'simulation-source-provenance.json'))
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
