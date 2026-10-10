#!/usr/bin/env python3
"""Original host conditioning over the actual shared physical/input/grind owners.

Only root builds and executes under the shared guard. --preflight stages/audits
sources and corpus without compiling or running a probe.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import check_grind_runtime_parity as grind
import check_state_conditioning_parity as core
from check_graph_parity import element,original_graph
from session_parity import digest
PLUGIN=grind.PLUGIN;CODE=grind.CODE;HOST=grind.HOST
UNITS=tuple(dict.fromkeys((*grind.UNITS,'FilteredState','LandingQuality','PlayerStateConditioning','AnimationStatePublication')))
BLOCKS=('shared','grind','conditioning')

def append(path,text):path.write_bytes(path.read_bytes()+text.encode())

def simulation_plan(output):
    snapshot,report=grind.simulation_plan(output)
    for unit in UNITS:shutil.copy2(CODE/(unit+'.cpp'),snapshot/(unit+'.cpp'))
    generated=(snapshot/'grind_runtime_probe.cpp').read_text();prefix=generated[:generated.index('int main(')]
    initialization=generated[generated.index(' if(argc!=6)'):generated.index(' Input i{{')]
    construction=generated[generated.index(' for(unsigned c=0;c<count;++c){')+len(' for(unsigned c=0;c<count;++c){'):generated.index(' const auto provider=')]
    cases=generated[generated.index(' case 0:'):generated.index(' case 6:')]
    # The inherited stream uses actual reset only in initialization, before any
    # conditioner history. All retained conditioning resets use source Reset.
    source=(PLUGIN/'Tests/Simulation/state_conditioning_runtime_probe.cpp').read_text().replace('// GENERATED_SIMULATION_OWNER_PREFIX',prefix).replace('// GENERATED_SIMULATION_OWNER_INITIALIZATION',initialization).replace('// GENERATED_SIMULATION_OWNER_CONSTRUCTION',construction).replace('// GENERATED_SIMULATION_PACKET_RESET_CASES',cases)
    assert source.count('GroundPhaseLifecycle life;')==1
    probe=snapshot/'state_conditioning_runtime_probe.cpp';probe.write_text(source)
    report.update(units=UNITS,immutable_simulation_sources={p.name:digest(p)for p in sorted(snapshot.glob('*.h'))+sorted(snapshot.glob('*.cpp'))},generated_probe_sha256=digest(probe))
    return snapshot,report

def reference_plan(output):
    original,observed,crate,cargo,report=grind.reference_plan(output)
    generated,_=grind.reset.generated_observer();prefix=generated[generated.index('use super::*;'):generated.index('pub(super) fn run(')]
    cases=generated[generated.index(' 0=>'):generated.index(' 2=>')]
    manager=grind.block((PLUGIN/'Tests/Reference/grind_runtime_observer.rs').read_text(),'fn read_manager(')
    observer=(PLUGIN/'Tests/Reference/state_conditioning_runtime_observer.rs').read_text().replace('// GENERATED_ORIGINAL_OWNER_PREFIX',prefix+manager).replace('// GENERATED_ORIGINAL_PACKET_RESET_CASES',cases).replace('// GENERATED_PROVIDER_READER',grind.provider_helpers()[1]).replace('// GENERATED_GRIND_WORLD',grind.world_helpers()[1])
    publication=grind.reset.source(HOST+'player_state/publication.rs');start=publication.index('    let surface = choose_surface(');end=publication.index('\n    skater.player_state.ground_output = output;',start);tail=publication[start:end]
    assert tail.endswith('skater.player_state.filtered_output = Some(filtered);')
    tail_function='\npub(super) fn migration_conditioning(physics:&GamePhysics,skater:&mut SkaterRuntime,output:Option<skate_core::riding::grounded::state::output::PhysicsGroundOutput>)->Result<(),String>{\n    let state=skater.player_state.current();\n'+tail+'\n    Ok(())\n}\n'
    animation=grind.reset.source(HOST+'animation_phase.rs');begin=animation.index('    skater.player_input.physical.scoring.capabilities_204 =');finish=animation.index('    let feedback = skater.animation_feedback.update(',begin);landing=animation[begin:finish]
    graph_adapter='''
pub(super) fn migration_conditioning(o:&mut crate::Output,physical:&PhysicalPlayerInput,filtered:Option<&FilteredStateOutput>,height:f32,mirrored:bool,forward:[f32;3])->Result<(),String>{
 let (state,g,c)=observations(physical,filtered,height,mirrored,forward)?;
 o.word(state.category);o.word(state.grinding as u32);o.word(state.grind_name.len()as u32);o.0.extend(state.grind_name.bytes().map(u32::from));
 o.word(g.grinding as u32);o.words(g.grind_name.0);o.floats(g.ground_axis);o.floats(g.board_axis);o.word(g.ground_flag_273 as u32);o.word(g.animation_mirrored as u32);o.floats([g.height,g.crouch,g.twist]);
 o.word(c.filtered_grinding_80 as u32);o.words([c.blunting_136,c.approach_268,c.trick_out_240]);o.word(c.air_grind_443 as u32);o.float(c.air_time_184);o.word(c.dropping_in_324 as u32);Ok(())
}
'''
    # The private cache read is appended in the original core module. No
    # implementation/declaration is changed; every original byte stays prefix.
    words=['self.category as u32','self.previous_category as u32','self.previous_physics_state as u32','self.air_count as u32','self.nonspecific_count as u32','self.nonspecific_collision_free_count as u32','self.nonspecific_collision_count as u32','self.frames_since_ground_stairs as u32','self.must_change as u32','g.kind as u32','g.scorable_id as u32']+[f'g.name.0[{n}]'for n in range(5)]+[f'g.scoring_name.0[{n}]'for n in range(5)]+['g.on_front as u32','g.crouch.to_bits()','g.pathed_guid as u32','(g.pathed_guid>>32)as u32','g.local_guid as u32','(g.local_guid>>32)as u32']
    cache='\nimpl FilteredState{pub fn migration_conditioning_words(&self)->[u32;27]{let g=self.cached_grind;['+','.join(words)+']}}\n'
    player_observer='''
pub(crate) fn migration_conditioning(p:&GamePhysics,s:&mut SkaterRuntime,output:Option<skate_core::riding::grounded::state::output::PhysicsGroundOutput>)->Result<(),String>{publication::migration_conditioning(p,s,output)}
pub(crate) fn migration_conditioning_observe(o:&mut crate::Output,s:&SkaterRuntime){o.words(s.player_state.filtered.migration_conditioning_words());o.word(s.player_state.filtered_output.is_some()as u32);if let Some(f)=s.player_state.filtered_output{o.words([f.category as u32,f.previous_category as u32,f.grinding as u32]);let g=f.grind;o.words([g.kind as u32,g.scorable_id as u32]);o.words(g.name.0);o.words(g.scoring_name.0);o.word(g.on_front as u32);o.float(g.crouch);o.words([g.pathed_guid as u32,(g.pathed_guid>>32)as u32,g.local_guid as u32,(g.local_guid>>32)as u32]);o.float(f.last_grind_distance);}let l=s.landing_quality;o.floats([l.landing_adjust_80,l.sideways_speed_84,l.forward_speed_88,l.spin_92]);o.words([l.landing_type_96,l.landing_data_167 as u32]);}
'''
    extensions={
        'physics/input_phase.rs':'\n'+observer,
        'physics.rs':'\npub(crate) fn migration_state_conditioning_run(a:&std::path::Path,f:&std::path::Path,i:&mut crate::Input,o:&mut crate::Output)->Result<(),String>{input_phase::migration_state_conditioning_run(a,f,i,o)}\n',
        'physics/player_state/publication.rs':tail_function,
        'physics/player_state.rs':player_observer,
        'physics/animation_phase.rs':'\npub(crate) fn migration_conditioning_landing(physics:&GamePhysics,skater:&mut SkaterRuntime){\n'+landing+'}\npub(crate) fn migration_conditioning_graph(o:&mut crate::Output,p:&skate_core::player::input_phase::PhysicalPlayerInput,f:Option<&skate_core::physics::filtered_state::FilteredStateOutput>,h:f32,m:bool,z:[f32;3])->Result<(),String>{grind::migration_conditioning(o,p,f,h,m,z)}\n',
        'physics/animation_grind.rs':graph_adapter,
    }
    for rel,text in extensions.items():append(crate/'src'/rel,text)
    core_path=observed/'crates/skate-core/src/physics/filtered_state.rs';append(core_path,cache)
    source=(crate/'src/migration_probe.rs').read_text();source=source[:source.index('fn main()')]+(PLUGIN/'Tests/Reference/state_conditioning_runtime_probe.rs').read_text();(crate/'src/migration_probe.rs').write_text(source)
    cargo.write_text(cargo.read_text().replace('name="grind-runtime-reference"','name="state-conditioning-runtime-reference"'))
    report.update(conditioning_extensions={rel:dict(append_sha256=hashlib.sha256(text.encode()).hexdigest(),generated_sha256=digest(crate/'src'/rel))for rel,text in extensions.items()},private_cache_observer_sha256=hashlib.sha256(cache.encode()).hexdigest(),source_fragments=[dict(source=HOST+'player_state/publication.rs',start_byte=start,end_byte=end,fragment_sha256=hashlib.sha256(tail.encode()).hexdigest()),dict(source=HOST+'animation_phase.rs',start_byte=begin,end_byte=finish,fragment_sha256=hashlib.sha256(landing.encode()).hexdigest())],scope='Original completed-publication tail and landing prefix extracted byte-identically; full original constructors, grind/chromosome/board/contact/shared physical owner methods unchanged. Entire animation_grind observations/name adapter executes original source.')
    return original,observed,crate,cargo,report

def build_simulation(output):
    snapshot,report=simulation_plan(output);binary=output/'state-conditioning-runtime-simulation'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(u+'.cpp'))for u in UNITS],str(snapshot/'state_conditioning_runtime_probe.cpp'),'-o',str(binary)],check=True)
    report['binary_sha256']=digest(binary);(output/'simulation-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return binary

def build_reference(output,target):
    original,observed,crate,cargo,report=reference_plan(output);subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(cargo),'--target-dir',str(target.resolve()),'--bin','state-conditioning-runtime-reference'],check=True)
    for rel,sha in report['original_source_sha256'].items():assert digest(original/rel)==sha;raw=(original/rel).read_bytes();assert(observed/rel).read_bytes()[:len(raw)]==raw
    binary=output/'state-conditioning-runtime-reference';shutil.copy2(target.resolve()/'release/state-conditioning-runtime-reference',binary);report['binary_sha256']=digest(binary);(output/'reference-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return binary

def corpus():
    _,baseline=grind.corpus();setup=baseline[0]['commands'][:7];packet=copy.deepcopy(setup[0]);cases=[]
    def completed(state):
        v=copy.deepcopy(packet);v['physical']['state'].update(category_12=state//100*100,state_16=state);v['processed'].update(state_2508=state,category_2512=state//100*100)
        g=v['physical']['grinds'];g['words_136_140']=[0xffffffff,0];g['animation_name_156']=[0]*5;g['scoring_name_176']=[0]*5;g['grinding_316']=0
        return v
    def add(label,commands):cases.append(dict(index=len(cases),label=label,world=1,provider=baseline[0]['provider'],commands=commands))
    for state in core.STATES:
        commands=copy.deepcopy(setup)
        v=completed(state);v['physical']['off_board'].update(flag_320=0 if state==501 else state%2,flag_315=(state//2)%2)
        commands+=[v,dict(op=40,state=state,target=state%2),dict(op=41),dict(op=42),dict(op=43,height=.731,mirrored=state%2)]
        for n in range(8):commands+=[dict(op=41),dict(op=42),dict(op=43,height=.137*n,mirrored=n%2)]
        add('all selected-state completed publication '+str(state),commands)
    for family,state in enumerate((401,400,402,403,404,405)):
        commands=copy.deepcopy(setup)+[dict(op=20,manager=grind.manager(family)),dict(op=10,state=state),dict(op=13),dict(op=14)]
        for n in range(8):commands+=[dict(op=41),dict(op=42),dict(op=43,height=.317+n*.137,mirrored=n%2)]
        commands+=[completed(100),dict(op=40,state=100,target=False),dict(op=41),dict(op=42),dict(op=43,height=.731,mirrored=False),dict(op=40,state=701,target=False),dict(op=41),dict(op=44)]
        add('actual six-family Fill/chromosome/filter graph '+str(family),commands)
    for angle,speed,spin in ((0,3,0),(.06,3,0),(.25,3,-7),(-.25,3,7),(.5,3,7),(-.5,3,-7),(0,0,7),(1,1,7)):
        commands=copy.deepcopy(setup)+[completed(201),dict(op=40,state=201,target=False),dict(op=41),dict(op=28,spin=[.137,spin,.731]),dict(op=48,velocity=[angle*speed,0,speed]),dict(op=34),dict(op=47),dict(op=42),dict(op=40,state=100,target=False),dict(op=41),dict(op=42),dict(op=43,height=.731,mirrored=False),dict(op=42)]
        add('actual board motion landing geometry '+str((angle,speed,spin)),commands)
    commands=copy.deepcopy(setup)+[completed(100),dict(op=40,state=100,target=False),dict(op=41),dict(op=6),dict(op=34),dict(op=47)]
    for n in range(12):commands+=[dict(op=6),dict(op=34),dict(op=47),dict(op=41),dict(op=42),dict(op=43,height=.731,mirrored=n%2)]
    commands += [dict(op=46,flags=n)for n in range(16)];add('real solve/contact/output and all capability contexts',commands)
    for which in ('animation','scoring','family'):
        commands=copy.deepcopy(setup)+[completed(100),dict(op=40,state=100,target=False),dict(op=41),completed(401),dict(op=40,state=401,target=False)]
        if which=='family':commands+=[dict(op=45,lane=2,word=999),dict(op=45,lane=3,word=1)]
        else:commands+=[dict(op=45,lane=2,word=0),dict(op=45,lane=0 if which=='animation'else 1,word=0)]
        commands += [dict(op=41)];add('real partial failure '+which,commands)
    add('missing filtered owner',[dict(op=45,lane=4,word=1),dict(op=43,height=.731,mirrored=False)])
    add('inconsistent filtered publication',copy.deepcopy(setup)+[completed(100),dict(op=40,state=100,target=False),dict(op=41),dict(op=45,lane=4,word=3),dict(op=43,height=.731,mirrored=False)])
    for which,name in [('alphabet',[0xffffffff,0,0,0,0]),('nonterminal',[0,11*79235168,0,0,0])]:
        commands=copy.deepcopy(setup)+[completed(400),dict(op=40,state=400,target=False)]
        commands += [dict(op=45,lane=5+n,word=w)for n,w in enumerate(name)]
        commands += [dict(op=41),dict(op=43,height=.731,mirrored=False)];add('encoded name diagnostic '+which,commands)
    return cases

def encode(cases):
    defs,_=grind.protocol.declarations();w=grind.input_grind.Stream();w.word(len(cases))
    for case in cases:
        w.word(case['world']);grind.input_grind.encode_provider(w,case['provider']);w.word(len(case['commands']))
        for cmd in case['commands']:
            op=cmd['op'];w.word(op)
            if op==0:
                for name,key in (('PlayerInputState','player'),('PhysicalPlayerInput','physical'),('ProcessedPhysicsInput','processed')):grind.protocol.encode(w,name,cmd[key],defs)
            elif op==1:
                for v in cmd['target']:
                    for x in v:w.float(x)
                packet=cmd['packet'];grind.protocol.encode(w,'AnimationPacketFields',packet['publication'],defs);grind.protocol.encode(w,'ExternalPhysicsInput',packet['external_physics_10512'],defs)
                for field,kind in defs['AnimationInputPacket']:
                    if not kind.startswith('&'):grind.protocol.encode(w,kind,packet[field],defs)
                w.word(cmd['pose']);w.word(len(cmd['attributes']))
                for a in cmd['attributes']:
                    for x in a['name']+[a['kind'],a['status'],a['sequence'],a['begin'],a['end']]:w.word(x)
                    for v in a['payload']:
                        w.word(v is not None)
                        if v is not None:w.word(v)
                for x in cmd['actions']:w.float(x)
                w.word(cmd['initial_teleported'])
            elif op==10:w.word(cmd['state'])
            elif op==20:grind.write_manager(w,cmd['manager'])
            elif op==22:w.word(cmd['pose']);w.word(cmd['fakie']);w.word(cmd['jump_fix']);w.float(cmd['pop'])
            elif op==28:
                for v in cmd['spin']:w.float(v)
            elif op==40:w.word(cmd['state']);w.word(cmd['target'])
            elif op==43:w.float(cmd['height']);w.word(cmd['mirrored'])
            elif op==45:w.word(cmd['lane']);w.word(cmd['word'])
            elif op==46:w.word(cmd['flags'])
            elif op==48:
                for v in cmd['velocity']:w.float(v)
    return bytes(w.data)

class Reader(grind.Reader):
    def state(self):
        assert self.word()==len(BLOCKS);values={};self.sections={}
        for name in BLOCKS:n=self.word();at=self.at;values[name]=self.take(n);self.sections[name]=(at,self.at)
        return values

def decode(raw,cases):
    r=Reader(raw);assert r.word()==len(cases);frames=[]
    for case in cases:
        assert r.word()==len(case['commands']);previous=r.state();rows=[]
        for cmd in case['commands']:
            assert r.word()==cmd['op'];error=r.status();extra=r.take(r.word());state=r.state();rows.append(dict(op=cmd['op'],error=error,extra=extra,state=state,previous=previous));previous=state
        frames.append(rows)
    assert r.at==len(r.words);return frames

def conditioned(words):
    r=Reader(struct.pack('<'+'I'*len(words),*words));state=r.take(27);filtered=r.take(22)if r.word()else None;landing=r.take(6);assert r.at==len(words);return dict(state=state,filtered=filtered,landing=landing)

def coverage(frames,cases):
    ops=Counter();errors=Counter();categories=Counter();kinds=Counter();proof=Counter();capabilities=set();velocities=set();names=set();actual_contacts=0
    for rows,case in zip(frames,cases):
        for row,cmd in zip(rows,case['commands']):
            op=cmd['op'];ops[op]+=1;errors.update([row['error']]if row['error']else[]);c=conditioned(row['state']['conditioning']);before=conditioned(row['previous']['conditioning']);packets=grind.reset.packet_observation(grind.shared(row['state']['shared'])['packets']);physical=packets['PhysicalPlayerInput']
            if op==41:
                if not row['error']:
                    assert c['filtered'] and physical['filtered_state_0']==c['filtered'][0] and c['filtered'][-1]==0;categories[c['filtered'][0]]+=1;proof['exact constant-zero distance']+=1
                else:
                    assert c['state']==before['state'] and c['filtered']==before['filtered'];proof['error preserves filter']+=1
                    if row['state']['shared']!=row['previous']['shared']:proof['earlier grind partial writes']+=1
            if op==42:
                assert physical['scoring']['capabilities_204']==0x1c0
                if c['filtered'] and c['filtered'][1]!=1 and c['filtered'][0]==1:
                    assert c['landing'][5]==1;kinds[c['landing'][4]]+=1;proof['actual landing']+=1
                else:assert c['landing']==[0]*6;proof['host resets nonlanding']+=1
            if op==43 and not row['error']:
                e=Reader(struct.pack('<'+'I'*len(row['extra']),*row['extra']));category=e.word();grinding_=e.word();name=bytes(e.take(e.word())).decode();g=e.take(24);assert e.at==len(e.words)
                assert category==physical['filtered_state_0'] and g[0]==grinding_ and g[12]==bool(physical['ground']['flag_273']) and g[13]==bool(cmd['mirrored'])
                assert g[6:9]==physical['skateboard']['vector_80'][:3] and g[14]==core.bits(cmd['height']);velocities.add(tuple(g[6:9]));names.add(name);proof['actual graph publication']+=1
            if op==44:assert c['filtered']is None and c['state'][:9]==[0,0,0,0,0,0,0,0,1];proof['filtered reset']+=1
            if op==46:capabilities.update(row['extra'])
            if op==47 and not row['error']:actual_contacts+=physical['collision']['flag_3477']!=0;proof['real board/contact publication']+=1
    expected_errors=('Missing native grind name reset/publication','Missing native scoring grind name reset/publication','Active grind has invalid native family 999','Grind graph requires the completed filtered state owner','Grind graph received inconsistent completed filtered outputs','Filtered grind name is outside the stock alphabet','Filtered grind name contains a nonterminal NUL')
    assert all(errors[e]>0 for e in expected_errors),errors
    assert {0,1,2,3,4,5,6,7}<=set(categories),categories
    assert {0,1,2,3}<=set(kinds),kinds
    assert proof['earlier grind partial writes']>0 and proof['error preserves filter']>=3
    assert proof['filtered reset']==6 and proof['host resets nonlanding']>100 and proof['actual graph publication']>100
    assert len(velocities)>4 and len(names)>4 and actual_contacts>0
    assert capabilities=={0,0xfffffff7,0xfffff7f7,0x1c0}
    return dict(operations=dict(ops),errors=dict(errors),filtered_categories=dict(categories),landing_kinds=dict(kinds),proofs=dict(proof),actual_contact_publications=actual_contacts,actual_velocity_variants=len(velocities),actual_graph_names=sorted(names),capability_masks=sorted(capabilities))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('assets','samples','output','target-dir'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--preflight',action='store_true');args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json'):(output/name).unlink(missing_ok=True)
    cases=corpus();raw=encode(cases);(output/'input.bin').write_bytes(raw);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    if args.preflight:
        snapshot,simulation=simulation_plan(output);original,observed,crate,cargo,reference=reference_plan(output/'reference')
        for path in (snapshot/'state_conditioning_runtime_probe.cpp',crate/'src/migration_probe.rs',crate/'src/physics/input_phase.rs'):assert 'GENERATED_'not in path.read_text(),path
        for rel,sha in reference['original_source_sha256'].items():assert digest(original/rel)==sha;body=(original/rel).read_bytes();assert(observed/rel).read_bytes()[:len(body)]==body
        (output/'simulation-preflight.json').write_text(json.dumps(simulation,indent=2)+'\n');(output/'reference-preflight.json').write_text(json.dumps(reference,indent=2)+'\n');print(json.dumps(dict(histories=len(cases),callbacks=sum(len(c['commands'])for c in cases),input_bytes=len(raw),units=len(UNITS)),indent=2));return
    fixtures=output/'fixtures';fixtures.mkdir(exist_ok=True);stock=args.assets.resolve()/'private/stock'
    (fixtures/'settings.simulation').write_bytes(grind.reset.foot.converter.encode_settings(stock/'skater-collections.json'));(fixtures/'physics.simulation').write_bytes(grind.reset.foot.converter.encode_physics_skeletons(stock/'physics-skeletons.json'))
    for kind in ('action','motion'):(fixtures/f'actor.{kind}.reference').write_bytes(original_graph(element('state','idle')))
    identity=json.loads((stock/'physics-skeletons.json').read_text())['source_sha256'];reference=build_reference(output/'reference',args.target_dir);simulation=build_simulation(output)
    expected=subprocess.check_output([str(reference),str(args.assets.resolve()),str(fixtures)],input=raw);actual=subprocess.check_output([str(simulation),str(fixtures/'settings.simulation'),str(fixtures/'physics.simulation'),str(args.samples.resolve()/'simulation/rig.skate'),identity,str(args.assets.resolve())],input=raw)
    (output/'reference.bin').write_bytes(expected);(output/'simulation.bin').write_bytes(actual);frames=decode(expected,cases);(output/'reference-trace.json').write_text(json.dumps(frames,indent=2)+'\n')
    if expected!=actual:
        byte=next((i for i,(a,b)in enumerate(zip(expected,actual))if a!=b),min(len(expected),len(actual)));(output/'first-divergence.json').write_text(json.dumps(dict(byte=byte,expected_bytes=len(expected),actual_bytes=len(actual)),indent=2)+'\n');raise AssertionError('Actual host state conditioning differs')
    result=dict(passed=True,histories=len(cases),callbacks=sum(len(c['commands'])for c in cases),exact_output_bytes=len(expected),output_sha256=hashlib.sha256(expected).hexdigest(),coverage=coverage(frames,cases),comparison='Actual shared GamePhysics/SkaterRuntime construction, solve/contact/board motion/stock pose/grind Fill/chromosome producers and exact original filtered publication tail/landing prefix/animation_grind adapter.',boundaries='Selected lifecycle ID, completed input packets, KnownAir targeting field, source Ground output from actual owner, focused grind-manager observations and previously completed animation stance/height are explicit caller boundaries. Entire global frame/selected-state Fill dispatch and complete animation feedback remain separate. Current empirical last-grind distance is original constant zero; RespawnRuntime retains the sole empirical sample counter unchanged.',simulation_provenance_sha256=digest(output/'simulation-provenance.json'),reference_provenance_sha256=digest(output/'reference/reference-provenance.json'))
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__':main()
