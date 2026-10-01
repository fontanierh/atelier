#!/usr/bin/env python3
"""Full frozen Ground board composition; concrete live host binding is separate.

Generated protocol readers/observers use original type declarations only and go
under build/. Numerical core/source methods are never translated by the oracle.
Only the coordinator may compile or run this through the render/memory guard.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import struct
import subprocess
import check_ground_state_parity as state_probe
import check_ground_control_settings_parity as ground
import check_animation_trees_parity as trees
from check_animation_playback_parity import Stream,bits
from check_gesture_parity import converter,PLUGIN
from reference_build import build_probe

CORE='crates/skate-core/src/'
SOURCES={
 'GroundBoardInput':CORE+'riding/grounded/state/board_types.rs','GroundForceFrame':CORE+'riding/grounded/state/board_types.rs','GroundContactFrame':CORE+'riding/grounded/state/board_types.rs',
 'PhysicsGroundState':CORE+'riding/grounded/state/data.rs','AntiFlipNudgeInput':CORE+'riding/grounded/state/corrections.rs','HangUpInput':CORE+'riding/grounded/state/corrections.rs','HalfpipeWheelCatchInput':CORE+'riding/grounded/state/corrections.rs','PinningInput':CORE+'riding/grounded/state/corrections.rs',
 'SteeringInput':CORE+'riding/steering.rs','SteeringSettings':CORE+'riding/steering.rs','TruckSteeringState':CORE+'riding/steering.rs',
 'SpeedWobbleInput':CORE+'riding/speed_wobble.rs','SpeedWobbleSettings':CORE+'riding/speed_wobble.rs',
 'GroundPropulsionInput':CORE+'riding/grounded/propulsion.rs','GroundPropulsionSettings':CORE+'riding/grounded/propulsion.rs','BrakeSettings':CORE+'riding/braking.rs','LinearDragSettings':CORE+'riding/braking.rs',
 'GroundForceSettings':CORE+'riding/ground_force.rs','SpeedModelInput':CORE+'riding/speed_model.rs','SpeedModelSettings':CORE+'riding/speed_model.rs','SpeedModelState':CORE+'riding/speed_model.rs',
 'SlideFrictionInput':CORE+'riding/slide_friction.rs','SlideFrictionSettings':CORE+'riding/slide_friction.rs','StraightenInput':CORE+'riding/straighten.rs','StraightenSettings':CORE+'riding/straighten.rs','HeadingInput':CORE+'riding/heading.rs','HeadingSettings':CORE+'riding/heading.rs','AntiFlipInput':CORE+'riding/anti_flip.rs','AntiFlipSettings':CORE+'riding/anti_flip.rs',
 'PumpForceInput':CORE+'riding/pumping.rs','ManualInput':CORE+'physics/manual/controller.rs','ManualSettings':CORE+'physics/manual/settings.rs','ManualGains':CORE+'physics/manual/settings.rs','ManualMode':CORE+'physics/manual/settings.rs','ManualState':CORE+'physics/manual/state.rs','GroundDragInput':CORE+'riding/grounded/drag.rs',
 'WallRidePhysical':CORE+'riding/ground_contact_response.rs','CollisionResponsePhysical':CORE+'riding/collision_response.rs',
 'RetailContactMaterial':CORE+'physics/contact.rs','CollisionResponseSettings':CORE+'riding/collision_response.rs',
 'LaunchInfo':CORE+'air/trajectory/types.rs',
 'TrainerTuning':'crates/skate-host/src/tuning.rs','GroundLaunchInfo':'crates/skate-host/src/physics/ground_runtime/launch.rs','GroundSettings':'crates/skate-host/src/physics/ground_runtime/settings.rs',
}
CPP_NAMES={'CollisionResponsePhysical':'RidingCollisionPhysical','CollisionResponseSettings':'RidingCollisionResponseSettings','RetailContactMaterial':'ContactMaterial','LaunchInfo':'AirLaunchInfo'}
CPP_FIELDS={('CollisionResponsePhysical','flags_2472'):'flags',('GroundSettings','slide'):'torque.slide',('GroundSettings','straighten'):'torque.straighten',('GroundSettings','heading'):'torque.heading',('GroundSettings','anti_flip'):'torque.anti_flip'}


def schema():
    result={};sources={}
    for name,path in SOURCES.items():
        source=sources.setdefault(path,trees.source_at_reference(path));match=re.search(r'\bstruct '+name+r'\s*\{',source);assert match,name;start=match.end();end=source.index('\n}',start);body=re.sub(r'//[^\n]*','',source[start:end]);fields=re.findall(r'^\s*(?:pub(?:\([^)]*\))?\s+)?(\w+)\s*:\s*([^,\n]+),',body,re.M);assert fields,name;result[name]=[(field,re.sub(r'\s+','',kind)) for field,kind in fields]
    return result,sources


def is_graph(kind):return re.fullmatch(r'PointGraph<(\d+)>',kind)
def is_array(kind):return re.fullmatch(r'\[(f32|u32);(\d+)\]',kind)
def primitive(kind):return kind in ('f32','u32','i32','u16','bool','Vector3','Vector','Transform','[f32;4]','[[f32;4];4]','AnimationPartTransform') or is_array(kind) or is_graph(kind)


def protocol_helpers(definitions):
    cpp=[];rust=[];done=set()
    def emit(kind):
        if primitive(kind) or kind in done:return
        for _,child in definitions[kind]:emit(child)
        done.add(kind);ctype=CPP_NAMES.get(kind,kind);fields=definitions[kind]
        # Settings have private fields in the original host child module. Its
        # observer is added inside that child, preserving the original module.
        rust_prefix='pub(super) ' if kind=='GroundSettings' else ''
        rust_obs=rust_prefix+f'fn observe_{kind}(o:&mut '+('crate::Output' if kind=='GroundSettings' else 'Output')+f',s:&{kind}) {{\n'
        cpp_obs=f'void Observe(Output& o,const {ctype}& s) {{\n'
        for field,child in fields:
            cfield=CPP_FIELDS.get((kind,field),field);expr=f's.{field}';cexpr=f's.{cfield}'
            if child=='f32':r=f'o.float({expr});';c=f'o.Float({cexpr});'
            elif child in ('u32','i32','u16','bool'):r=f'o.word({expr} as u32);';c=f'o.Word(std::uint32_t({cexpr}));'
            elif child=='Vector3':r=f'o.vector({expr});';c=f'o.Value({cexpr});'
            elif child in ('[[f32;4];4]','AnimationPartTransform','Transform'):r=f'for c in {expr} {{o.floats(c);}}';c=f'o.Value({cexpr});'
            elif child=='Vector':r=f'o.floats({expr});';c=f'o.Value({cexpr});'
            elif is_array(child):r=f'o.'+('floats' if is_array(child)[1]=='f32' else 'words')+f'({expr});';c=f'for (auto v:{cexpr}) o.'+('Float' if is_array(child)[1]=='f32' else 'Word')+'(v);'
            elif is_graph(child):r=f'o.floats({expr}.x);o.floats({expr}.y);';c=f'o.Curve({cexpr});'
            else:r=f'crate::observe_{child}(o,&{expr});' if kind=='GroundSettings' else f'observe_{child}(o,&{expr});';c=f'Observe(o,{cexpr});'
            rust_obs+=r+'\n';cpp_obs+=c+'\n'
        rust_obs+='}\n';cpp_obs+='}\n';cpp.append(cpp_obs)
        if kind!='GroundSettings':rust.append(rust_obs)
        else:host_observer[0]=rust_obs
        if kind=='GroundSettings':return
        cpp_read=f'{ctype} Read{kind}(Input& i) {{{ctype} s;\n';rust_read=f'fn read_{kind}(i:&mut Input)->{kind} {{{kind}{{\n'
        for field,child in fields:
            cfield=CPP_FIELDS.get((kind,field),field)
            if child=='f32':r='i.float()';c='i.Float()'
            elif child in ('u32','u16','i32'):r='i.word()'+(' as '+child if child!='u32' else '');c='i.Word()' if child=='u32' else f'std::'+('int32_t' if child=='i32' else 'uint16_t')+'(i.Word())'
            elif child=='bool':r='i.word()!=0';c='i.Word()!=0'
            elif child=='Vector3':r='i.three()';c='i.Three()'
            elif child in ('[[f32;4];4]','AnimationPartTransform','Transform'):r='i.matrix()';c='i.Matrix()'
            elif child=='Vector':r='i.floats::<4>()';c='i.Floats<4>()'
            elif is_array(child):a=is_array(child);r=f'i.'+('floats' if a[1]=='f32' else 'words')+f'::<{a[2]}>()';c=f'i.'+('Floats' if a[1]=='f32' else 'Words')+f'<{a[2]}>()'
            elif is_graph(child):n=is_graph(child)[1];r=f'i.curve::<{n}>()';c=f'i.Curve<{n}>()'
            else:r=f'read_{child}(i)';c=f'Read{child}(i)'
            cpp_read+=f's.{cfield}={c};\n';rust_read+=f'{field}:{r},\n'
        cpp_read+='return s;}\n';rust_read+='}}\n';cpp.append(cpp_read);rust.append(rust_read)
    host_observer=['']
    for kind in definitions:emit(kind)
    return '\n'.join(cpp),'\n'.join(rust),host_observer[0]


def default_value(kind,defs):
    if kind=='f32':return .25
    if kind in ('u32','i32','u16'):return 0
    if kind=='bool':return False
    if kind=='Vector3':return [.25,.5,1]
    if kind in ('[[f32;4];4]','AnimationPartTransform','Transform'):return [[1,0,0,0],[0,1,0,0],[0,0,1,0],[.125,.25,.5,1]]
    if kind=='Vector':return [.125,.25,.5,0]
    if is_array(kind):return ([.125,.25,.5,.0] if kind=='[f32;4]' else [.25]*int(is_array(kind)[2])) if is_array(kind)[1]=='f32' else [0]*int(is_array(kind)[2])
    if is_graph(kind):n=int(is_graph(kind)[1]);return dict(x=list(range(n)),y=[.25]*n)
    return {field:default_value(child,defs) for field,child in defs[kind]}


def encode_value(w,kind,value,defs):
    if kind=='f32':w.float(value)
    elif kind in ('u32','i32','u16','bool'):w.word(int(value)&0xffffffff)
    elif kind in ('[[f32;4];4]','AnimationPartTransform','Transform'):
        for column in value:
            for v in column:w.float(v)
    elif kind in ('Vector3','Vector') or is_array(kind):
        for v in value:(w.float if kind in ('Vector3','Vector') or is_array(kind)[1]=='f32' else w.word)(v)
    elif is_graph(kind):
        for v in value['x']+value['y']:w.float(v)
    else:
        for field,child in defs[kind]:encode_value(w,child,value[field],defs)


def source_float(data,category,key,name):
    chain,field=ground.resolve(data,(category,key,name,'float'));return struct.unpack('>f',bytes.fromhex(chain[-1]['fields'][field]['data']))[0]


def authored_input(defs,tick,branch,brake_angle):
    x=default_value('GroundBoardInput',defs);balance=1 if branch==3 else (-.5,0,.5)[tick%3];dt=(.003,1/60,.033)[tick%3];velocity=[.125,0,2+tick*.125,0];normal=[0,1,0,0];side=[1,0,0,0];forward=[0,0,1,0]
    x['steering'].update(turn=(-.5,.25,.75)[tick%3],hard_turn=0,absolute_body_speed=5,flipped_controls_scalar=1,balance=balance,truck_tightness=(tick%5)*.25,pushing=tick%2==0)
    x['speed_wobble'].update(tilt=-.125,speed=20,center_of_mass_height=99,truck_tightness=.25,activation_threshold=.125,amplitude_multiplier=.5)
    x.update(truck_flags_2468=(1<<20 if tick%2 else 0),truck_flags_2472=(1<<27 if tick%3 else 1<<26),ground_vector_1216=normal,contact_time_2756=(-.125,.0,.25)[tick%3],trajectory_state_1776_bits=0x80000000 if tick%4==0 else 0)
    x['contact'].update(vector_8032=[0,0,0,.125],vector_8048=[0,.2,0,.25],vector_8064=[0,1,0,0],word_8080=0xabcdef01,flag_8084=branch==1,scalar_2752=.125,scalar_2756=0)
    x['propulsion'].update(flags_2468=(1<<25 if tick%2 else 1<<29),flags_2472=0x1000 if tick%3 else 0,target_speed=7,signed_speed=2,absolute_body_speed=2,scalar_2660=8,timestep=dt,brake_input=.5,push_direction=[0,0,1],brake_direction=[0,0,-1],surface_braking_factor=.75)
    x['ground_force'].update(argument_1_2752=(.0,.125,.5)[tick%3],processed_2776=tick%2,processed_2780=-.25 if tick%3 else .25,previous_state_scalar_56=.5,ground_scalar_1216=.125,ground_scalar_1232=.5,ground_scalar_1236=.25,ground_scalar_1240=.375,balance_2720=balance,surface_speed_2656=3,axis_384=side,velocity_400=([-1,0,2.25,0] if branch==2 and tick==2 else velocity),axis_544=normal)
    x['speed_model'].update(flags_2468=0,flags_2476=(0x40000000 if tick%4==0 else 0),wheel_contact_count=tick%5,frames_2580=10,timestep=dt,signed_speed=2,angle_2652=.5,surface_speed=3,turn_2672=.25,balance=balance,elapsed_without_input=.5,manual_state_276=123,vector_160=forward,vector_352=normal,velocity_416=velocity,normal_464=normal,effective_forward=forward,mass=8)
    x['slide_friction'].update(heading_time=999,normal=normal,velocity=velocity,side_axis=side,surface_speed=3,scalar_2764=.5)
    x['pump_force'].update(flags_2476=0,mode_multiplier=.75,pumping_scalar=.5,input_scalar_2660=8,timestep=dt,direction_432=forward,normal_threshold=[struct.unpack('<f',struct.pack('<I',0x358637bd))[0]]*4)
    x['straighten'].update(heading_time=999,scalar_2764=.5,turn=.25,forward=forward,velocity=velocity,normal=normal)
    x['heading'].update(balance=balance,manual_turn=.25,flags_2472=1<<27,timestep=dt,signed_speed=2,manual_curve_input=3,turn_2712=.25,scalar_2740=.5,velocity=velocity,normal=normal,angular_velocity=[.125,.25,.375,0])
    # The real stock curves have a dead band below these axes' projected tilt.
    # Unit .8/.6 axes cross that band, making the retained nudge counter reach
    # its actual magnitude-scaling callback rather than merely its dot gate.
    x['anti_flip'].update(flags_2468=0,balance=balance,axis_96=[.8,.6,0,0],axis_64=[0,.6,.8,0],projection_axis_544=normal)
    a=brake_angle*math.pi/180;x['manual'].update(balance=balance,flipped_controls=1,procedural_noise_time=tick*.125,absolute_speed=2,animation_noise=.125,timestep=dt,powersliding=True,braking=branch==3,positive_balance_contact=True,negative_balance_contact=True,reversed_point_selection=False,reference_x=side,reference_z=forward,deck_z=[0,math.sin(a),math.cos(a),0] if branch==3 else [.125,0,1,0],velocity_frame_z=forward,angular_velocity_world=[0,0,-1000 if branch==3 else -.25,0],correction_point_7888=[0,-.125,.25,0],correction_point_7952=[0,-.125,-.25,0])
    x['ground_drag'].update(flags_2468=(1<<29 if tick%2 else 0),absolute_body_speed_2616=2,balance_2720=balance,scalar_2724=.125,ground_normal_y=.5)
    x['anti_flip_nudge'].update(deck_speed_2652=.5,deck_axis_96=[1,.25,.125,0]);x['hang_up'].update(flags_1516=0x0c000000,deck_speed_2652=.5,scalar_84=.5,geometry_axis_dot_positive=True);x['halfpipe_wheel_catch'].update(flags_1516=0x08000000,deck_speed_2652=.5,deck_x_axis_y=.1,deck_y_axis_y=.05,signed_deck_distance=.05);x['pinning'].update(flags_2488=0,frames_since_teleport_2584=0,flags_2472=0x00800000)
    return x


def corpus(defs,data):
    brake_angle=source_float(data,'physics_manual','default','BrakeTiltAngle');cases=[]
    for mode in range(5):
        for surface in range(1,6):
            commands=[]
            for tick,branch in enumerate((0,1,2,0,3,0,2,0)):
                commands.append(dict(branch=branch,tick=tick,fail=0,clear=tick in (3,5),binding=0,input=authored_input(defs,tick,branch,brake_angle)))
            cases.append(dict(label='stock mixed branch histories',mode=mode,surface=surface,tuning=(mode+surface)%3,seed=mode*5+surface,preseed=(0,18,20,21)[(mode+surface)%4],commands=commands))
    for binding in (1,2):
        for branch in (0,1,3):cases.append(dict(label='detached inertia binding error',mode=1,surface=1,tuning=0,seed=19,preseed=18,commands=[dict(branch=branch,tick=0,fail=0,clear=False,binding=binding,input=authored_input(defs,0,branch,brake_angle))]))
    for branch in (0,1,2,3):
        for fail in range(1,34):cases.append(dict(label='required service failure partial writes',mode=1,surface=1,tuning=0,seed=19,preseed=18,commands=[dict(branch=branch,tick=0,fail=fail,clear=False,binding=0,input=authored_input(defs,0,branch,brake_angle))]))
    return cases


def initial_state(defs,seed):
    s=default_value('PhysicsGroundState',defs);s.update(steering_push_scalar_2640=1,steering_damped_turn_2644=0,elapsed_2648=.125,collision_countdown_2652=.5,straighten_scale_2672=.75,human_player_2724=True,captured_position_valid_2726=True,captured_position_x_2656=.5,captured_position_z_2660=-.25,controls_latched_2725=False,hang_detection_frames_2740=19,hang_force_frames_2744=2,hung_wipeout_frames_2748=20,anti_flip_nudge_frames_2752=13);return s


def encode(cases,defs):
    w=Stream();w.word(len(cases))
    for case in cases:
        w.word(case['mode']);w.word(case['surface']);t=default_value('TrainerTuning',defs)
        for field,kind in defs['TrainerTuning']:t[field]=((1,.75,1.25)[case['tuning']] if kind=='f32' else case['tuning']==2)
        encode_value(w,'TrainerTuning',t,defs);encode_value(w,'PhysicsGroundState',initial_state(defs,case['seed']),defs);w.word(case['seed']);w.word(case['preseed']);w.word(len(case['commands']))
        for row in case['commands']:
            for field in ('branch','fail','clear','binding'):w.word(row[field])
            encode_value(w,'GroundBoardInput',row['input'],defs)
    return bytes(w.data)


def prepare_sources(output,defs,sources):
    cpp_helpers,rust_helpers,observer=protocol_helpers(defs);launch=trees.source_at_reference(SOURCES['GroundLaunchInfo']);settings=trees.source_at_reference(SOURCES['GroundSettings']);tuning=trees.source_at_reference(SOURCES['TrainerTuning']);surface,record=trees.extract_block(trees.source_at_reference('crates/skate-host/src/physics/ground_runtime/surface.rs'),'pub(crate) fn surface_key(')
    cpp=(PLUGIN/'Tests/Native/ground_board_probe.cpp').read_text();rust=(PLUGIN/'Tests/Reference/ground_board_probe.rs').read_text();assert cpp.count('// GENERATED_PROTOCOL')==1 and rust.count('// GENERATED_PROTOCOL')==1;cpp=cpp.replace('// GENERATED_PROTOCOL',cpp_helpers);rust=rust.replace('// GENERATED_PROTOCOL',rust_helpers)
    rust+='\nmod difficulty {pub const NATIVE_MODES:[&str;5]=["easy","normal","hardcore","motorized","test"];}\nmod tuning {\n'+tuning+'\n}\nmod launch {\n'+launch+'\n}\nmod stock {\n'+surface+'\npub(crate) use settings::{GroundProfiles,GroundSettings};\npub fn observe(o:&mut crate::Output,s:&GroundSettings) {settings::observe_GroundSettings(o,s)}\nmod settings {\n'+settings+'\n'+observer+'\n}\n}\n'
    code=output/'native-source';code.mkdir(exist_ok=True);cpp_path=code/'ground_board_probe.cpp';cpp_path.write_text(cpp);rust_path=output/'ground-board-oracle.rs';rust_path.write_text(rust)
    (output/'protocol-provenance.json').write_text(json.dumps(dict(original_type_declarations=defs,source_sha256={path:hashlib.sha256(source.encode()).hexdigest() for path,source in sources.items()},whole_host_launch_sha256=hashlib.sha256(launch.encode()).hexdigest(),whole_host_settings_sha256=hashlib.sha256(settings.encode()).hexdigest(),surface_helper=record,cpp_probe_sha256=hashlib.sha256(cpp.encode()).hexdigest(),rust_probe_sha256=hashlib.sha256(rust.encode()).hexdigest(),boundary='Readers and observers are generated solely from unchanged original field declarations. Full original core board/ordinary/correction/controller methods execute unchanged. Required service numerics use real original kernels; world/external errors/results are explicitly supplied. Concrete live host bindings and malformed full-profile settings are separate proofs.'),indent=2)+'\n');return cpp_path,rust_path


def build_native(output,probe):
    live=PLUGIN/'Source/AtelierSkate/Private/Native';code=output/'native-source';files=('NativeMath','RigidBody','BodyMass','AggregateMass','DeckGeometry','DriveFrames','ConstraintFrames','ConstraintSolver','JointBuild','DriveBuild','JointRecords','TruckDriveFrames','DrivePreparation','HookDrive','BoardAssembly','ContactBuild','ContactGeneration','BoardPose','ForceQueue','CollisionBody','BoardContactFeedback','BoardStep','BoardRuntime','DeckAngularCorrections','NameId','Settings','StockSettingsReader','GroundControlSettings','Steering','SteeringWobbleSettings','SpeedWobble','GroundForce','Manual','BoardGroundAngle','RidingAngles','RidingCollisionResponse','GroundContactResponse','Braking','Push','GroundPropulsion','SpeedModel','GroundDrag','GroundState','GroundStateCorrections','GroundCorrections','SlideFriction','Straighten','Heading','AntiFlip','GroundTorqueSettings','Pumping','GroundBoard','GroundLaunchInfo','GroundSettings')
    assert all((live/(name+'.cpp')).is_file() for name in files),[name for name in files if not (live/(name+'.cpp')).is_file()]
    for p in list(live.glob('*.h'))+[live/(name+'.cpp') for name in files]:shutil.copyfile(p,code/p.name)
    (output/'native-source-provenance.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(code.iterdir())},indent=2)+'\n');native=output/'ground-board-cpp';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(code),*[str(code/(name+'.cpp')) for name in files],str(probe),'-o',str(native)],check=True);return native


def word_count(kind,defs):
    if kind in ('f32','u32','i32','u16','bool'):return 1
    if kind=='Vector3':return 3
    if kind in ('Vector','[f32;4]'):return 4
    if kind in ('Transform','AnimationPartTransform','[[f32;4];4]'):return 16
    if is_array(kind):return int(is_array(kind)[2])
    if is_graph(kind):return 2*int(is_graph(kind)[1])
    return sum(word_count(child,defs) for _,child in defs[kind])


class Words:
    def __init__(self,words):self.words=words;self.at=0
    def take(self,n):
        result=self.words[self.at:self.at+n];assert len(result)==n,(self.at,n,len(self.words));self.at+=n;return result
    def word(self):return self.take(1)[0]
    def value(self,kind,defs):
        if primitive(kind):return self.word() if word_count(kind,defs)==1 else self.take(word_count(kind,defs))
        return {field:self.value(child,defs) for field,child in defs[kind]}
    def done(self):assert self.at==len(self.words),(self.at,len(self.words))


def payload(words,defs):
    w=Words(words);s={};s['state']=w.value('PhysicsGroundState',defs)
    for name,kind in (('wobble','[u32;8]'),('truck','TruckSteeringState'),('speed','SpeedModelState'),('manual','ManualState'),('heading','f32')):s[name]=w.value(kind,defs)
    s['bodies']=[w.take(49) for _ in range(7)];s['detached']=[w.take(9) for _ in range(w.word())];s['indices']=w.take(w.word());s['queue']=[w.take(7) for _ in range(w.word())];s['processed_velocity']=w.take(4);s['material']=w.value('RetailContactMaterial',defs);s['collision']=w.take(12) if w.word() else None
    if w.word():s['launch']=w.value('GroundLaunchInfo',defs);s['selector']=w.value('LaunchInfo',defs)
    else:s['launch']=s['selector']=None
    s['wipeouts']=w.word();s['commits']=w.word();s['calls']=w.word();trace=Words(w.take(w.word()));s['trace']=[]
    while trace.at<len(trace.words):s['trace'].append(dict(id=trace.word(),args=trace.take(trace.word())))
    trace.done();w.done();assert len(s['trace'])==s['calls'];return s


def decode(data,cases,defs):
    at=0;result=[]
    def word():
        nonlocal at
        v=struct.unpack_from('<I',data,at)[0];at+=4;return v
    for c,case in enumerate(cases):
        assert word()==c;settings=Words([word() for _ in range(word())]);config=dict(settings=settings.value('GroundSettings',defs),packets=[])
        for _ in range(4):config['packets'].append(dict(ground=settings.value('GroundLaunchInfo',defs),selector=settings.value('LaunchInfo',defs)))
        settings.done();frames=[]
        for tick,row in enumerate(case['commands']):
            assert (word(),word())==(c,tick);ok=word();outcome=[word() for _ in range(6)];n=word();error=data[at:at+n].decode();at+=n;values=[word() for _ in range(word())];frames.append(dict(ok=ok,outcome=outcome,error=error,snapshot=payload(values,defs)))
        result.append(dict(config=config,frames=frames))
    assert at==len(data),(at,len(data));return result


SERVICE_NAMES=('COM height','wheel materials','contact response','body torque','animated velocity','processed velocity','construct launch','fill launch','wall jump','commit launch','finalize animation','collision force','collision projection','vector correction','angular correction','manual angle','dot product','scale magnitude','build hang force','apply hang force','world hung result','hung wipeout','wheel catch','apply wheel catch','pin captured position')
SERVICE_ARG_WORDS=(4,3,20,0,4,4,0,70,74,140,0,4,8,4,4,12,8,6,12,4,1,0,0,4,2)
LAUNCH_MAP={'system':'reckoning_transform','inverse_system':'reckoning_inverse','velocity':'start_velocity','angular_velocity':'com_velocity','skeleton_vector_16208':'skeleton_vector_160','skeleton_vector_16240':'skeleton_vector_176','board_position':'board_position','physical_center_of_mass':'animation_com_position','vector_224':'start_position_override','vector_240':'board_position_override','cone_angle_x':'cone_angle_x','cone_angle_z':'cone_angle_z','time_step':'timestep','flag_269':'use_position_override','wall_jump':'player_jumped','flags_270':'trajectory_count'}


def packet_proof(packet):
    assert len(LAUNCH_MAP)==16
    for name,target in LAUNCH_MAP.items():assert packet['ground'][name]==packet['selector'][target],(name,target)


def coverage(frames,cases,defs):
    statuses=Counter();outcomes=Counter();errors=Counter();services=Counter();tags=Counter();fail_stages=Counter();hashes=set();stock_settings=set();manual_modes=Counter();queues=Counter();partial=0;partial_bodies=0;partial_manual=0;retained_collision=0;launches=0;packet_snapshots=0;hang_results=set();reset=set();terminal_queued=set();collision_projection=set();bindings=Counter();failure_groups={}
    for frame,case in zip(frames,cases):
        hashes.add(hashlib.sha256(json.dumps(frame,sort_keys=True).encode()).hexdigest());config=frame['config'];stock_settings.add(json.dumps(config['settings'],sort_keys=True));packets=config['packets']
        for packet in packets:packet_proof(packet);packet_snapshots+=1
        default,authored,filled,jumped=[packet['ground'] for packet in packets]
        assert default['flags_270']==0 and default['flag_269']==0 and default['wall_jump']==0
        assert authored['flag_269']==1 and authored['flags_270']==0x1234
        for name in ('vector_224','vector_240','flag_269'):assert authored[name]==filled[name]==jumped[name],name
        assert filled['flags_270']==jumped['flags_270']==(7 if case['seed']%2 else 1)
        assert filled['wall_jump']==0 and jumped['wall_jump']==1
        assert jumped['velocity']==jumped['angular_velocity']==[bits(v) for v in (2,4,-3,.125)]
        assert filled['velocity']!=filled['angular_velocity']
        for row,meta in zip(frame['frames'],case['commands']):
            s=row['snapshot'];trace=s['trace'];ids=[call['id'] for call in trace];statuses[row['ok']]+=1;queues[len(s['queue'])]+=1;assert len(s['queue'])<=21
            assert ids[:min(len(ids),4)]==[0,1,2,3][:min(len(ids),4)]
            for call in trace:
                ident=call['id'];assert 0<=ident<len(SERVICE_NAMES);services[ident]+=1;assert len(call['args'])==SERVICE_ARG_WORDS[ident],(ident,len(call['args']))
                if ident==20:hang_results.add(call['args'][0])
            for force in s['queue']:tags[force[0]]+=1
            assert len(s['indices'])==7 and len(s['detached'])==(6 if meta['binding']==2 else 7)
            assert all(body[47]==detached[7] for body,detached in zip(s['bodies'],s['detached']))
            if s['launch'] is not None:packet_proof(dict(ground=s['launch'],selector=s['selector']));launches+=1
            if s['collision'] is not None:retained_collision+=1
            if row['ok']:
                assert not row['error'];outcome=row['outcome'];outcomes[outcome[0]]+=1
                if outcome[0]==0:
                    assert ids==list(range(11));assert s['state']['flag_2720']==1 and s['launch']['wall_jump']==1
                    assert all(d[7]==bits(0) for d in s['detached'])
                elif outcome[0]==1:
                    assert ids==[0,1,2,3,11,13,12];assert s['collision'] is not None;assert s['state']['collision_force_2528']==s['collision'][:4]
                    collision_projection.add(s['state']['flag_2722'])
                else:
                    assert outcome[0]==2 and outcome[3]==(7 if outcome[2] else 16);manual_modes[outcome[2]]+=1;reset.add(outcome[5]);terminal_queued.add(outcome[4]);assert s['state']['manual_correction_2732']==outcome[2]
                    assert (15 in ids)==(meta['input']['manual']['balance']!=0) and 16 in ids
                    if outcome[2]:assert 14 not in ids and 13 not in ids
                    else:assert ids.count(14)==2 and ids.count(13)>=2
            else:
                assert row['outcome'][0]==0xffffffff and row['error'];errors[row['error']]+=1
                if meta['binding']:bindings[meta['binding']]+=1;assert row['outcome'][1]==2
                else:
                    assert s['calls']==meta['fail'];fail_stages[tuple(row['outcome'][1:4])]+=1
            if case['label']=='required service failure partial writes':failure_groups.setdefault(meta['branch'],[]).append((row,meta))
    # Every required callback is reached by an actual original core branch.
    assert set(services)==set(range(25)),set(range(25))-set(services)
    assert all(outcomes[k]>0 for k in (0,1,2)) and all(statuses[k]>0 for k in (0,1)),(outcomes,statuses)
    assert set(manual_modes)=={0,1} and set(terminal_queued)=={0,1},(manual_modes,terminal_queued)
    assert queues[21]>0 and all(tags[k]>0 for k in (1,2,3,4,5,6,7,8,15,16,17)),tags
    assert set(bindings)=={1,2} and retained_collision>0 and launches>0 and hang_results=={0,1}
    for branch,group in failure_groups.items():
        successful=[r for r,m in group if r['ok']];assert successful,branch;complete=max(successful,key=lambda r:r['snapshot']['calls']);base=complete['snapshot']['trace'];failed=[r for r,m in group if not r['ok']]
        assert {r['snapshot']['calls'] for r in failed}==set(range(1,len(base)+1)),(branch,len(base))
        for row in failed:
            n=row['snapshot']['calls'];assert row['snapshot']['trace']==base[:n],(branch,n)
            if n>1 and row['snapshot']['state']!=failed[0]['snapshot']['state']:partial+=1
            if n>1 and row['snapshot']['bodies']!=failed[0]['snapshot']['bodies']:partial_bodies+=1
            if n>1 and row['snapshot']['manual']!=failed[0]['snapshot']['manual']:partial_manual+=1
    assert partial>0 and partial_bodies>0 and partial_manual>0 and collision_projection=={0,1} and len(stock_settings)>16 and len(hashes)>25,(partial,partial_bodies,partial_manual,collision_projection,len(stock_settings),len(hashes))
    return dict(statuses=dict(statuses),outcomes=dict(outcomes),required_services={SERVICE_NAMES[k]:services[k] for k in sorted(services)},force_tags=dict(tags),queue_sizes=dict(queues),manual_correction=dict(manual_modes),terminal_enqueue_values=sorted(terminal_queued),speed_reset_values=sorted(reset),collision_projection_values=sorted(collision_projection),failure_stages={str(k):v for k,v in fail_stages.items()},partial_retained_state_failures=partial,partial_body_write_failures=partial_bodies,partial_manual_write_failures=partial_manual,detached_binding_failures=dict(bindings),retained_collision_snapshots=retained_collision,live_launch_snapshots=launches,launch_mapping_snapshots=packet_snapshots,explicit_world_hung_results=sorted(hang_results),distinct_stock_settings=len(stock_settings),distinct_traces=len(hashes))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--target-dir',type=Path,required=True);args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json'):(output/name).unlink(missing_ok=True)
    defs,sources=schema();data=json.loads((args.assets/'private/stock/skater-collections.json').read_text());cases=corpus(defs,data);commands=encode(cases,defs);(output/'input.bin').write_bytes(commands);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');cpp_probe,rust_probe=prepare_sources(output,defs,sources);reference=build_probe(output,'ground-board-reference',rust_probe,args.target_dir);native=build_native(output,cpp_probe);settings=output/'settings.native';settings.write_bytes(converter.encode_settings(args.assets/'private/stock/skater-collections.json'))
    def expected(data):return subprocess.check_output([str(reference),str(args.assets.resolve())],input=data)
    def actual(data):return subprocess.check_output([str(native),str(settings)],input=data)
    oracle=expected(commands);candidate=actual(commands);(output/'reference.bin').write_bytes(oracle);(output/'native.bin').write_bytes(candidate);frames=decode(oracle,cases,defs);(output/'reference-trace.json').write_text(json.dumps(frames,indent=2)+'\n')
    if oracle!=candidate:
        lo=0;hi=len(cases)
        while hi-lo>1:
            mid=(lo+hi)//2
            if expected(encode(cases[lo:mid],defs))==actual(encode(cases[lo:mid],defs)):lo=mid
            else:hi=mid
        (output/'first-divergence-input.bin').write_bytes(encode(cases[lo:hi],defs));(output/'first-divergence.json').write_text(json.dumps(dict(case=lo,record=cases[lo]),indent=2)+'\n');raise AssertionError(f'Ground board composition differs in case {lo}')
    result=dict(passed=True,cases=len(cases),commands=sum(len(c['commands']) for c in cases),coverage=coverage(frames,cases,defs),output_bytes=len(oracle),output_sha256=hashlib.sha256(oracle).hexdigest(),comparison='Full original core Ground board composition and successful actual stock profiles/tuning; numeric services use original geometry/deck/launch kernels.',limitations='Concrete live GroundRuntime/world/skeleton/trajectory binding and malformed whole-profile settings errors remain separate owner comparisons.')
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
