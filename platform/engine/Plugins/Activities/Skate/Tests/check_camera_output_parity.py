#!/usr/bin/env python3
"""Whole unchanged camera publication/output on the actual completed owners.

Only the parent may compile/run under the guard. Preflight is lightweight. The
native runtime reads converted data and borrows canonical live owners. The
oracle constructs full original GamePhysics/SkaterRuntime, fills corresponding
completed records, and invokes unchanged publication and camera advance. This
is a producer/order/failure proof, not preceding whole-game physics scheduling.
"""
import argparse
import ast
from collections import Counter
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import historical_oracle as historical
import re
import shutil
import struct
import subprocess
import camera_probe_schema as schema
import camera_output_reference_build as reference
import camera_reference_build as camera_reference
import check_camera_runtime_parity as camera
import check_physical_simulation_runtime_parity as physics
from check_graph_parity import attribute,element,original_graph
from check_gesture_parity import converter,PLUGIN
from session_parity import REFERENCE_REVISION,digest
CODE=PLUGIN/'Source/AtelierSkate/Private/Native'
STATES=(100,101,102,103,104,105,200,201,202,300,400,401,402,403,404,405,500,501,502,503,600,601,602,700,701,702)

def source_units(file,function):
    tree=ast.parse(file.read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==function)
    for n in ast.walk(fn):
        if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='files' for t in n.targets):return ast.literal_eval(n.value)
    raise AssertionError('Missing exact unit list')

UNITS=tuple(dict.fromkeys((*physics.UNITS,*camera.UNITS,
    *source_units(PLUGIN/'Tests/check_skater_animation_parity.py','build_native'),
    *source_units(PLUGIN/'Tests/check_ground_board_parity.py','build_native'),
    'GroundRuntime','GroundInput','GroundPumpingRuntime','GroundStateRuntime','GroundOutput','GroundLaunchInfo',
    'PhysicsAnimationInput','SkeletonAttributeDispatch','PlayerInputTypes',
    'AirMath','CentreOfMassFilter','PhysicalPhase','CameraPublication','CameraOutputRuntime')))

def fields():
    return reference.output_schemas(historical.source_text)

def fixture(t,case,defs):
    f=schema.zero_value('CameraOwnerFixture',defs)
    state=STATES[(t//7+case)%len(STATES)];category=state//100*100;alt=t%41>=23
    pos=[.137+case*.317+.13*__import__('math').sin(t*.071),.37+(t%7)*.0317,t*.027+.731,0]
    root=camera.matrix([pos[0]+.17,pos[1]+.73,pos[2]-.11,.317],.137+case*.13)
    f.update(ticks=t+1,selected_state=state,state_flag_81=bool(t%13<5),output_present=True,output_tick=t,output_state=state,
      ground_normal=[.137,.983,.071],predicted_position=[pos[0]+.73,pos[1]+.137,pos[2]+1.37],toolkit_present=True,
      board_transform=camera.matrix(pos,.173+case*.11),effective_basis=[[1,0,.137],[.0317,1,.071],[-.137,.0317,1]],
      skeleton_root=root,bone_positions=[[pos[0]+b*.00317,pos[1]+b*.0431,pos[2]-b*.00731,(b+t)%7*.0317] for b in range(26)],
      physical_state=state,physical_category=category,surface_height=.731+(t%19)*.0317,
      processed_state=STATES[(t+3)%len(STATES)],processed_category=(1,2,3,4,5,6,7)[t%7]*100,
      flags_2468=((1<<25) if t%11<5 else 0)|((1<<18) if t%83>67 else 0)|((1<<22) if t%17<8 else 0)|((1<<20) if t%5==0 else 0),
      flags_2472=(1<<10) if t==0 or t%61==0 else 0,flags_2476=4 if (t//9+case)%2 else 0,
      flags_2480=((1<<2) if t%13<7 else 0)|((1<<11) if t%19<9 else 0),flags_2484=(1<<24) if t%23<8 else 0,
      state_variant=t%5,spin=.137+(t%7)*.0317,input_age=0 if (t//9)%2==0 else .731,
      deck_speed=(-1 if t%7<3 else 1)*((t%31)*.731),state_timer=(t%37)*.01731,
      axis_464=[0,1,0,.137],velocity_608=[.317,.137,-.731,.517],
      centre_of_mass=[pos[0],pos[1]+.73,pos[2],.731],reckoning_up=[.071,.983,-.137,.317],
      board_velocity=[(t%7)*.1731,-.731,(t%23)*.317,.137],board_angular_velocity=[-.317,t*.001731,.137,-.731],last_ground_up=[-.071,.983,.137,.517],
      air_valid=(t//5)%2,air_reckoning=(t//7)%2,slow_motion_air_duration=.731+(t%7)*.131,
      capabilities=(0,4,0xffffffff)[t%3],profile=(0,1,2,4,7,11)[t%6],hippy_jump=int(t%29<13),
      animation_flags=(0x80000000,0xe0000000,0xc0000000,0xa0000000)[(t//11)%4],packet_fakie=bool(t%5<3),
      balance=(0,-.317,.731)[t%3],turn=(-.731,.317,.0)[t%3],look=[-.0 if t%17==0 else .317,__import__('math').sin(t*.071)*.731],
      intents=((1<<28) if t%7==0 else 0)|((1<<27) if t%17<5 else 0)|((1<<22) if t%31<15 else 0),
      conditioned_turn=[(t%11-5)*.0317+j*.071 for j in range(8)],pumping=(t%13-6)*.137,
      com_reset=t==0 or t%79==0,com_input_position=[pos[0]+.137,pos[1]+.73,pos[2]-.317,.517+t*.0017],com_input_velocity=[.1731,.0317,.731,.137],
      preferences=dict(invert_look=[bool(t%2),bool(t%3==0)],shake_variant=(t//7)%2,value_32=.137+(t%17)*.0317),
      context=case+7,publication_tick=t,override_broken_duration=.731 if t%3 else 0,override_ground_scalar=(t%19)*.137)
    f['air'].update(apex_0=[pos[0]+.137,2.317,pos[2]+1.137,.137],landing_position_16=[pos[0]+.731,.17,pos[2]+2.731,.317],landing_normal_32=[.137,.983,.071,.731],launch_position_48=[pos[0]-.317,.13,pos[2]-.731,-.137],heading_80=[.317,.0,.731,.517],time_176=(t%17)*.0317,duration_180=1.731,apex_time_196=.731,flag_440=255)
    f['offboard'].update(duration_92=2.137,time_152=(t%17)*.0173,apex_time_156=1.137,launch_normal_160=[-.137,.953,.071,-.317],launch_position_176=[pos[0]-.731,.23,pos[2]-1.137,.731],landing_normal_192=[-.173,.917,.231,.731],landing_position_208=[pos[0]+1.137,.31,pos[2]+3.137,.317],heading_224=[-.517,.0317,.731,-.731],apex_240=[pos[0]+.731,3.731,pos[2]+2.137,.517],object_held_304=(t//11)%2,hurdle_317=int(t%37<13),use_trajectory_331=int(alt),dropping_in_334=int(t%29<15))
    f['grinds'].update(direction_0=[.317,.0317,.731,.137],camera_target_96=[pos[0]+.137,pos[1]+.517,pos[2]+.317,.731],grinding_316=int(t%41<11))
    return f

def cases(defs):
    out=[]
    for c in range(6):
        rows=[dict(op=1,fixture=fixture(t,c,defs),label='completed actual owner histories') for t in range(192)]
        out.append(dict(camera=c%2,world=c%3,rows=rows))
    rows=[];base=fixture(9,7,defs);base['com_reset']=True
    for label,changes in [('missing completed exchange',{'output_present':False}),('first completed tick underflow',{'ticks':0}),('stale completed tick',{'ticks':11}),('stale selected state',{'output_state':701}),('missing actual toolkit',{'toolkit_present':False})]:
        f=copy.deepcopy(base);f.update(changes);rows.append(dict(op=1,fixture=f,label=label))
    targets=('centre_of_mass','reckoning_up','com_input_position','ground_normal','skeleton_root','head','left_foot','right_foot','hips','board_velocity','board_angular_velocity')
    for target in targets:
        f=copy.deepcopy(base)
        if target=='skeleton_root':f[target][0][0]=float('nan')
        elif target in ('head','left_foot','right_foot','hips'):f['bone_positions'][{'head':1,'left_foot':15,'right_foot':19,'hips':23}[target]][0]=float('inf')
        else:f[target][0]=float('nan')
        rows.append(dict(op=1,fixture=f,label='nonfinite '+target))
    for target in ('centre_of_mass','reckoning_up','com_input_position','skeleton_root','head','left_foot','right_foot','hips','board_velocity','board_angular_velocity'):
        f=copy.deepcopy(base)
        if target=='skeleton_root':f[target][0][3]=float('nan')
        elif target in ('head','left_foot','right_foot','hips'):f['bone_positions'][{'head':1,'left_foot':15,'right_foot':19,'hips':23}[target]][3]=float('inf')
        else:f[target][3]=float('nan')
        rows.append(dict(op=0,fixture=f,label='nonfinite W accepted '+target))
    out.append(dict(camera=0,world=1,rows=rows))
    rows=[]
    for t in range(96):
        f=fixture(t,8,defs);rows.append(dict(op=2,fixture=f,label='full publication engine preference fields'))
    for t in (95,94,94):
        f=fixture(t,8,defs);rows.append(dict(op=1,fixture=f,label='monotonic consumption rejection'))
    out.append(dict(camera=1,world=0,rows=rows))
    return out


def world(kind):
    w=camera.Writer();triangles=[]
    if kind!=2:
        y=-.035;corners=[[-20,y,-20],[20,y,-20],[20,y,20],[-20,y,20]]
        triangles=[([corners[i] for i in ids],tag) for ids,tag in (((0,2,1),1),((0,3,2),12))]
        if kind==1:triangles += [([[-3,0,3],[3,0,3],[3,3,3]],10),([[-3,0,3],[3,3,3],[-3,3,3]],11)]
    w.word(len(triangles))
    for vertices,tag in triangles:
        for vertex in vertices:
            for lane in vertex:w.float(lane)
        w.float(0)
        for _ in range(3):w.float(1)
        w.word(0x10 if tag in (1,12) else 0)
        for lane in (.731,.517,.137):w.float(lane)
        w.word(tag)
    return bytes(w.data)


def encode(cases,defs):
    w=camera.Writer();w.word(len(cases))
    for c in cases:
        w.data.extend(world(c['world']));w.word(c['camera']);w.word(len(c['rows']))
        for row in c['rows']:w.word(row['op']);schema.encoded_value(w,'CameraOwnerFixture',row['fixture'],defs)
    return bytes(w.data)

def cpp_protocol(defs):
    item=defs['CameraOwnerFixture'];declaration='struct CameraOwnerFixture{'+''.join(schema.cpp_type(kind)+' '+field+';' for field,kind in item['fields'])+'};\n'
    declarations=[];bodies=[];reads=[];wanted=reference.readable_types(defs)
    for item in defs.values():
        name=schema.cpp_name(item['name']);declarations.append(f'void WriteValue(Output&,const {name}&);')
        body=''.join(f'output.Word(std::uint32_t(value.{field}));' if kind=='usize' else f'WriteValue(output,value.{"state" if field=="0" else field});' for field,kind in item['fields']);bodies.append(f'void WriteValue(Output& output,const {name}& value){{{body}}}')
        if item['name'] in wanted:
            declarations.append(f'template<> {name} ReadValue<{name}>(Input& input);');body=''.join(f'value.{field}=ReadValue<{schema.cpp_type(kind)}>(input);' for field,kind in item['fields']);reads.append(f'template<> {name} ReadValue<{name}>(Input& input){{{name} value;{body}return value;}}')
    return declaration,'\n'.join(declarations)+'\n'+schema.CPP_GENERIC_WRITERS+'\n'+'\n'.join(bodies+reads)

def native_probe(output,defs):
    snapshot=output/'native-source';snapshot.mkdir(exist_ok=True);hashes={}
    for p in sorted(CODE.glob('*.h')):shutil.copy2(p,snapshot/p.name);hashes[p.name]=digest(snapshot/p.name)
    for unit in UNITS:p=CODE/(unit+'.cpp');shutil.copy2(p,snapshot/p.name);hashes[p.name]=digest(snapshot/p.name)
    template=PLUGIN/'Tests/Native/camera_output_probe.cpp';fixture,observers=cpp_protocol(defs);text=template.read_text();assert text.count('// @OWNER_FIXTURE_CPP@')==text.count('// @CPP_OBSERVERS@')==1
    generated=snapshot/template.name;generated.write_text(text.replace('// @OWNER_FIXTURE_CPP@',fixture).replace('// @CPP_OBSERVERS@',observers));hashes[generated.name]=digest(generated)
    binary=output/'camera-output-native';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(u+'.cpp'))for u in UNITS],str(generated),'-o',str(binary)],check=True)
    (output/'native-provenance.json').write_text(json.dumps(dict(immutable_native_sources=hashes,template_sha256=digest(template),units=UNITS),indent=2)+'\n');return binary

def fixtures(assets,output,package):
    out=output/'fixtures';out.mkdir(exist_ok=True);stock=assets/'private/stock'
    (out/'settings.native').write_bytes(converter.encode_settings(stock/'skater-collections.json'))
    (out/'physics.native').write_bytes(converter.encode_physics_skeletons(stock/'physics-skeletons.json'))
    for kind in ('action','motion'):
        graph=element('state','idle');original=out/f'actor.{kind}.reference';original.write_bytes(original_graph(graph));(out/f'actor.{kind}.native').write_bytes(converter.encode_graph(converter.read_graph(original)))
    for i in range(2):
        folder=out/f'camera-{i}'
        for relative in (camera.COLLECTION,camera.GRAPH,*camera.SHAKES):
            path=folder/relative;path.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(assets/relative,path)
        graph_path=folder/camera.GRAPH
        if i==1:graph_path.write_bytes(original_graph(camera.transition_graph()))
        (folder/'graph.native').write_bytes(converter.encode_graph(converter.read_graph(graph_path)))
        (folder/'camera.native').write_bytes(package)
    return out

def decode(data,cases,defs,label_at=None):
    r=camera.Reader(data,defs,label_at);assert r.word('cases')==len(cases);result=[]
    for i,c in enumerate(cases):
        assert r.word(f'case[{i}].rows')==len(c['rows']);rows=[]
        for j,source in enumerate(c['rows']):
            path=f'case[{i}].row[{j}].{source["label"]}';assert r.word(path+'.operation')==source['op']
            publication=r.value('CameraPublicationInputs',path+'.publication');okay,error=r.status(path+'.snapshot')
            snapshot=r.value('CameraSubjectSnapshot',path+'.snapshot') if okay else None
            advanced,advance_error=r.status(path+'.advance') if source['op']==1 else (None,None)
            state=r.runtime(path+'.runtime');com=r.value('[[f32;4];3]',path+'.COM');rows.append(dict(publication=publication,snapshot=snapshot,error=error,advanced=advanced,advance_error=advance_error,state=state,com=com))
        result.append(rows)
    assert r.at==len(data),(r.at,len(data));return result,r.labels

def bit(value):return struct.unpack('<I',struct.pack('<f',value))[0]
def coverage(frames,cases):
    errors=Counter();states=set();alt=set();valid=set();mirrors=set();pushable=set();positions=set();shots=set();rate_sizes=set();derived_bits=Counter();successes=0;w_checked=0;unchanged=0;order=0
    for ci,(rows,c) in enumerate(zip(frames,cases)):
        prior=None
        for row,source in zip(rows,c['rows']):
            f=source['fixture'];p=row['publication'];s=row['snapshot'];states.add(f['selected_state'])
            assert p['tick']==f['publication_tick'] and p['state']['flag_81']==f['state_flag_81']
            assert p['animation']['conditioned_turn']==list(map(bit,f['conditioned_turn']))
            assert p['animation']['stance_155']==f['packet_fakie'] and p['animation']['stance_155']!=255
            assert p['offboard']['object_held_304']==f['offboard']['object_held_304'] and p['events']['capabilities_204']==f['capabilities']
            assert p['damped_com_80']==row['com'][2] and p['ground_up_80']==[*map(bit,f['ground_normal']),0]
            assert p['collision_look_target_64']==[*map(bit,f['predicted_position']),0]
            for flag,shift in (('physically_pushing_55',25),('wiping_out_59',18)):
                expected=(f['flags_2468']>>shift)&1;assert p['state'][flag]==expected;derived_bits[(flag,expected)]+=1
            assert p['air']['flag_440']==(f['flags_2468']>>22)&1
            if source['op']!=2:assert p['events']['broken_bone_duration_200']==0 and p['ground_scalar_288']==0
            if source['label'].startswith('nonfinite W accepted'):assert s is not None,(ci,source['label'],row['error']);w_checked+=1
            if source['label'].startswith('nonfinite ') and not source['label'].startswith('nonfinite W'):assert row['error'] is not None,(ci,source['label'])
            if s is not None:
                rig=s['subject']['rig'];a=f['offboard']['use_trajectory_331']!=0;alt.add(a);valid.add(rig['trajectory_valid']);mirrors.add(bool(f['flags_2476']&4));pushable.add(rig['at_pushable_speed'])
                assert rig['in_ground_physics']==(f['physical_category']==100) and rig['off_board']==(f['physical_category']==500)
                assert rig['trajectory_valid']==(1 if a else f['air_valid']) and rig['air_flag_452']==f['air_reckoning']
                assert s['subject']['launch_normal']==(p['offboard']['launch_normal_160'] if a else list(map(bit,f['last_ground_up'])))
                assert s['subject']['launch_position']==(p['offboard']['launch_position_176'] if a else p['air']['launch_position_48'])
                assert s['subject']['trajectory_duration']==(p['offboard']['duration_92'] if a else p['air']['duration_180'])
                assert s['subject']['direction_424']==p['grinds']['direction_0'] and s['anchors']['board_acceleration']==list(map(bit,f['board_angular_velocity']))
                assert s['reference_points']['board']==s['pose']['skeleton_root'][3] and s['anchors']['board_position']==s['pose']['physical_transform'][3]
                assert s['subject']['rig']['reference_positions']==[[0]*4 for _ in range(10)] and s['subject']['compass']==[0]*9
                assert s['subject']['special_effect']==s['subject']['rig']['subject_flag_328']==0
                positions.add(tuple(s['pose']['physical_transform'][3]));assert s['graph']['onboard_air']==(f['physical_category']==200)
                for col in (0,2):
                    expected=list(map(bit,f['skeleton_root'][col]));expected=[x^0x80000000 for x in expected] if f['flags_2476']&4 else expected
                    assert s['pose']['skeleton_root'][col]==expected
            if row['error']:errors[row['error']]+=1
            if row['advance_error']:errors[row['advance_error']]+=1
            if source['op']==1 and row['advanced']:
                successes+=1;assert row['state']['latest']['tick']==f['output_tick'];assert row['state']['subject']['last_tick']==f['output_tick'];assert row['state']['frame'] is not None
                shots.add(row['state']['manager']['shots']['current']['definition']['name'])
            if source['op']==1 and not row['advanced'] and prior is not None:assert row['state']==prior;unchanged+=1
            rates=row['state']['rates'];rate_sizes.add(len(rates))
            if len(rates)>=2 and rates[-2]['ticks']==0 and rates[-1]['ticks']!=0:order+=1
            prior=row['state']
        if ci<6:assert all(row['advanced'] for row in rows),(ci,[r['advance_error'] for r in rows if not r['advanced']])
    assert states==set(STATES) and alt=={False,True} and valid=={0,1} and mirrors=={False,True} and pushable=={0,1}
    assert len(positions)>128 and successes>1000 and w_checked==10 and unchanged>=8
    assert all(derived_bits[(name,v)] for name in ('physically_pushing_55','wiping_out_59') for v in (0,1))
    assert any('stale physical output' in e for e in errors) and any('before the first completed tick' in e for e in errors)
    assert any('requires the completed player input toolkit' in e for e in errors) and any('completed physical output snapshot' in e for e in errors)
    assert any('not monotonic' in e for e in errors) and len(rate_sizes)>8 and order>4
    return dict(advances=successes,distinct_positions=len(positions),all_selected_states=sorted(states),trajectory_branches=sorted(alt),trajectory_validity=sorted(valid),pushable_values=sorted(pushable),accepted_nonfinite_W=w_checked,unchanged_camera_failures=unchanged,distinct_rate_queue_sizes=len(rate_sizes),ordered_end_then_begin=order,shots=sorted(shots),errors=dict(errors))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path,required=True);p.add_argument('--samples',type=Path,required=True);p.add_argument('--metadata',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--target-dir',type=Path,required=True);p.add_argument('--preflight',action='store_true');args=p.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True);defs=fields();spec=cases(defs);inputs=encode(spec,defs)
    for u in UNITS:assert (CODE/(u+'.cpp')).is_file(),u
    cpp_protocol(defs);(out/'input.bin').write_bytes(inputs)
    if args.preflight:print(json.dumps(dict(cases=len(spec),rows=sum(len(c['rows']) for c in spec),input_bytes=len(inputs),units=len(UNITS),schema_types=len(defs)),indent=2));return
    rust,defs=reference.build_output_probe(out/'reference',args.target_dir)
    data_probe=camera_reference.build_data_probe(out/'data',args.target_dir);base=out/'stock-camera';subprocess.run([str(data_probe),str(args.assets.resolve()),str(base),'camera-output-stock:'+digest(args.assets/camera.COLLECTION)],check=True)
    module_spec=importlib.util.spec_from_file_location('camera_conversion',PLUGIN/'Tools/convert_camera_data.py');module=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(module);package=module.pack_camera(json.loads(base.with_suffix('.json').read_text()));assert package==base.with_suffix('.raw').read_bytes()
    folder=fixtures(args.assets.resolve(),out,package);native=native_probe(out,defs);identity=json.loads((args.assets/'private/stock/physics-skeletons.json').read_text())['source_sha256']
    expected=subprocess.check_output([str(rust),str(args.assets.resolve()),str(folder)],input=inputs)
    actual=subprocess.check_output([str(native),str(folder),str(args.samples.resolve()/'native'),str(args.metadata.resolve()),str(args.assets.resolve()),identity],input=inputs)
    (out/'reference.bin').write_bytes(expected);(out/'native.bin').write_bytes(actual)
    if expected!=actual:
        at=next((i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b),min(len(expected),len(actual)));labels=[]
        try:_,labels=decode(expected,spec,defs,at)
        except Exception:pass
        failure=dict(byte=at,labels=labels,reference_bytes=len(expected),native_bytes=len(actual),reference_hex=expected[max(0,at-16):at+32].hex(),native_hex=actual[max(0,at-16):at+32].hex());(out/'first-divergence.json').write_text(json.dumps(failure,indent=2)+'\n');raise AssertionError(failure)
    frames,_=decode(expected,spec,defs);proof=coverage(frames,spec)
    result=dict(passed=True,reference_revision=REFERENCE_REVISION,cases=len(spec),rows=sum(len(c['rows']) for c in spec),bytes=len(expected),sha256=hashlib.sha256(expected).hexdigest(),input_sha256=hashlib.sha256(inputs).hexdigest(),coverage=proof,boundary='Entire actual publication/output producers on canonical completed owners, full original constructors, original Ground output, complete CameraRuntime histories/controller/output/ordered requests, actual geometry and source StaticWorld=0/region type1. Runtime native settings/graphs/camera/rig/metadata/physical skeleton only. Actual preceding physics/input/scoring production and global state/session scheduling are separate owners; no producer is replaced by a camera snapshot. Custom preference intermediate records exercise publication; Advance always uses original fixed preferences and ordering.')
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':historical.run_cli(main)
