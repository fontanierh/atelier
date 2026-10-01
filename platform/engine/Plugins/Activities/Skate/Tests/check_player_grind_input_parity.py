#!/usr/bin/env python3
"""Unchanged original grind manager and concrete static-world query proof.

Root exclusively compiles/runs this under the render guard. Converted transport
is compared to actual original StaticProvider::new on independent package/WMET
fixtures. It does not establish complete player-input or global scheduling.
"""
import argparse
from collections import OrderedDict,Counter
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import historical_oracle as historical
import random
import re
import shutil
import struct
import subprocess
import check_animation_trees_parity as trees
import check_physical_simulation_runtime_parity as physical
import check_world_geometry_parity as world
import check_ground_control_settings_parity as settings_probe
import player_input_protocol as protocol
from check_animation_playback_parity import Stream as BaseStream
from check_gesture_parity import PLUGIN,converter
from reference_build import build_probe

HOST='crates/skate-host/src/'
CORE='crates/skate-core/src/'
UNITS=('PlayerGrindSurface','PlayerGrindInputWorld','PlayerGrindContact','PlayerGrindFamilies','PlayerGrindManager','PlayerGrindBalance','PlayerGrindEntry','PlayerGrindControl','PlayerGrindInput','PlayerGrindInputPre','PlayerGrindInputPost','PlayerGrindInputPublication','PlayerGrindMaterials','StockSettingsReader','PlayerInputTypes','SkeletonAttributeDispatch','WipeoutOrientation')

@lru_cache(None)
def source(path):
    return historical.source_text(path)

def struct_fields(raw,name):
    m=re.search(r'\bstruct '+name+r'(?:<[^{}]+>)?\s*\{',raw);assert m,name
    at=m.end();end=at;depth=1
    while depth:
        if raw[end]=='{':depth+=1
        elif raw[end]=='}':depth-=1
        end+=1
    raw=re.sub(r'//[^\n]*','',raw[at:end-1]);fields=[];depth=0;start=0
    for end,c in enumerate(raw+','):
        if c in '[<':depth+=1
        elif c in ']>':depth-=1
        elif c==',' and not depth:
            item=raw[start:end].strip();start=end+1
            if not item:continue
            match=re.fullmatch(r'(?:pub(?:\([^)]*\))?\s+)?(\w+)\s*:\s*(.+)',item,re.S);assert match,(name,item)
            fields.append((match[1],re.sub(r'\s+','',match[2])))
    return fields

def declarations():
    defs=OrderedDict()
    for file,names in [('physics/grind_contact/manager.rs',('JumpGeometry','Jumper','GeometryInput')),('physics/grind_contact/balance.rs',('BalanceState','TargetUpInput','ExitLeanInput','BalanceVectors')),('physics/grind_contact/control.rs',('Control',)),('physics/grind_contact/entry.rs',('Engagement',)),('air/trajectory/grind_surface.rs',('Probe','ProbeHit','InvestigationInput','GrindSurface'))]:
        for name in names:defs[name]=struct_fields(source(CORE+file),name)
    for name in ('PreContext','PostContext'):defs[name]=struct_fields(source(HOST+'physics/player_input/grind.rs'),name)
    for n,fields in defs.items():defs[n]=[(f,k.replace('V','[f32;4]').replace('GeometryType','u32'))for f,k in fields]
    fields=struct_fields(source(HOST+'physics/player_input/grind.rs'),'GrindInputState')
    state=[(f,k.replace('V','[f32;4]').replace('balance::','').replace('entry::','').replace('control::','').replace('manager::',''))for f,k in fields if f!='settings']
    return defs,state

ALIASES={'JumpGeometry':'PlayerGrindJumpGeometry','Jumper':'PlayerGrindJumper','GeometryInput':'PlayerGrindGeometryInput','BalanceState':'PlayerGrindBalanceState','TargetUpInput':'PlayerGrindTargetUpInput','ExitLeanInput':'PlayerGrindExitLeanInput','BalanceVectors':'PlayerGrindBalanceVectors','Control':'PlayerGrindControl','Engagement':'PlayerGrindEngagement','Probe':'PlayerGrindProbe','ProbeHit':'PlayerGrindProbeHit','InvestigationInput':'PlayerGrindSurfaceInput','GrindSurface':'PlayerGrindSurface','PreContext':'PlayerGrindPreContext','PostContext':'PlayerGrindPostContext'}

def helpers(defs,state):
    # Declaration adapters only. Geometry's enum discriminant is validated by
    # the authored corpus; all numerical methods remain the unchanged source.
    cpp=[];rust=[]
    for name in defs:cpp.extend([f'using {name}={ALIASES[name]};',f'void Observe(Output&,const {name}&);',f'{name} Read{name}(Input&);'])
    for name,fields in defs.items():
        cpp.append(f'void Observe(Output& o,const {name}& s) {{'+''.join(protocol.observe_expr(k,'s.'+f,'cpp') if not(name=='GrindSurface'and f=='kind') else 'o.Word(std::uint32_t(s.kind));'for f,k in fields)+'}')
        cpp.append(f'{name} Read{name}(Input& i) {{{name} s;'+''.join('s.'+f+'='+('PlayerGrindGeometryKind(i.Word())'if name=='GrindSurface'and f=='kind'else protocol.read_expr(k,'cpp'))+';'for f,k in fields)+'return s;}')
        rust.append(f'fn observe_{name}(o:&mut Output,s:&{name}) {{'+''.join(protocol.observe_expr(k,'s.'+f,'rust') if not(name=='GrindSurface'and f=='kind')else 'o.word(s.kind as u32);'for f,k in fields)+'}')
        rust.append(f'fn read_{name}(i:&mut Input)->{name} {{{name}{{'+''.join(f+':'+('geometry_kind(i.word())'if name=='GrindSurface'and f=='kind'else protocol.read_expr(k,'rust'))+','for f,k in fields)+'}}')
    cpp.append('void ObserveState(Output& o,const PlayerGrindInputState& s){'+''.join(protocol.observe_expr(k,'s.'+f,'cpp')for f,k in state)+'}')
    cpp.append('void SeedState(Input& i,PlayerGrindInputState& s){'+''.join('s.'+f+'='+protocol.read_expr(k,'cpp')+';'for f,k in state)+'}')
    private='pub fn observe_state(o:&mut crate::Output,s:&GrindInputState){'+''.join(protocol.observe_expr(k,'s.'+f,'rust').replace('observe_','crate::observe_')for f,k in state)+'}\n'
    private+='pub fn seed_state(i:&mut crate::Input,s:&mut GrindInputState){'+''.join('s.'+f+'='+protocol.read_expr(k,'rust').replace('read_','crate::read_')+';'for f,k in state)+'}\n'
    private+='pub fn observe_pending(o:&mut crate::Output,p:&Pending){crate::observe_GrindInvestigationFields(o,&p.fields);o.word(p.metadata.is_some()as u32);if let Some(m)=p.metadata{o.word(m.spline_guids.is_some()as u32);if let Some(v)=m.spline_guids{for x in v{o.wide(x);}}}o.word(p.geometry.is_some()as u32);if let Some(g)=&p.geometry{crate::observe_InvestigationInput(o,&g.input);o.word(g.plan.is_some()as u32);if let Some(plan)=&g.plan{crate::observe_plan(o,plan);}for h in &g.hits{o.word(h.is_some()as u32);if let Some(h)=h{crate::observe_ProbeHit(o,h);}}}}'
    private+='pub fn observe_settings(o:&mut crate::Output,s:&GrindInputState){for g in[&s.settings.friction,&s.settings.slope_threshold,&s.settings.vertical_help,&s.settings.gravity_vertical,&s.settings.gravity_linear]{for v in g.x.into_iter().chain(g.y){o.float(v);}}for v in s.settings.exit_lean.x.into_iter().chain(s.settings.exit_lean.y){o.float(v);}for v in[s.settings.truck_to_wheel,s.settings.deck_to_truck,s.settings.test_above,s.settings.test_below,s.settings.max_impact]{o.float(v);}}'
    return '\n'.join(cpp),'\n'.join(rust),private

def aliases():
    out={}
    for name in ('history','pre','post','publication','settings','world'):out[f'atelier-host/src/physics/player_input/grind/{name}.rs']=HOST+f'physics/player_input/grind/{name}.rs'
    for name in ('provider','octree','spline'):out[f'atelier-host/src/grind_world/{name}.rs']=HOST+f'grind_world/{name}.rs'
    return out

def prepare(output):
    defs,state=declarations();base,_=protocol.declarations();cpp0,rust0=protocol.helpers(base);cpp,rust,private=helpers(defs,state)
    native_prefix=(PLUGIN/'Tests/Native/world_geometry_probe.cpp').read_text().split('int main()',1)[0]
    rust_prefix=(PLUGIN/'Tests/Reference/world_geometry_probe.rs').read_text().split('fn main()',1)[0].replace('use math::','use skate_core::math::').replace('use physics::','use skate_core::physics::')
    generated=output/'player-grind-input-native.cpp';generated.write_text('#pragma clang diagnostic push\n#pragma clang diagnostic ignored "-Wunused-function"\n'+native_prefix+'\n#pragma clang diagnostic pop\n'+(PLUGIN/'Tests/Native/player_grind_input_probe.cpp').read_text().replace('// GENERATED_PROTOCOL',cpp0+'\n'+cpp))
    family,_=trees.extract_block(source(HOST+'physics/grind.rs'),'pub(crate) enum Family {')
    ground=source(HOST+'physics/ground.rs');constants='\n'.join(line for line in ground.splitlines()if re.match(r'pub\(crate\) const (HEIGHT|FLOOR_HEIGHT):',line))
    materials='pub mod settings{use skate_core::physics::contact::RetailContactMaterial;pub struct PhysicsSettings{pub standard_wheel_material:RetailContactMaterial,pub wheel_material:RetailContactMaterial,pub truck_material:RetailContactMaterial,pub deck_material:RetailContactMaterial}}pub mod grind_materials{'+source(HOST+'physics/grind_materials.rs')+'}'
    host='mod physics{pub mod ground{'+constants+'}pub mod grind{#[derive(Clone,Copy,Debug,PartialEq,Eq)]#[repr(u32)]'+family+'\npub mod observation{'+source(HOST+'physics/grind/observation.rs')+'}pub(crate) use observation::ManagerObservation;}pub mod player_input{pub mod grind{'+source(HOST+'physics/player_input/grind.rs')+'\n'+private+'}}'+materials+'}\n'
    original=output/'player-grind-input-reference.rs';original.write_text(rust_prefix+host+'\nmod grind_world{'+source(HOST+'grind_world.rs')+'}\n'+(PLUGIN/'Tests/Reference/player_grind_input_probe.rs').read_text().replace('// GENERATED_PROTOCOL',rust0+'\n'+rust))
    (output/'extraction-provenance.json').write_text(json.dumps(dict(source_sha256={p:hashlib.sha256(source(p).encode()).hexdigest()for p in (HOST+'physics/player_input/grind.rs',HOST+'grind_world.rs',HOST+'physics/grind/observation.rs',HOST+'physics/grind.rs',HOST+'physics/ground.rs')},adapters='Declaration/observation only; full original core numerical modules and complete original host grind modules execute unchanged.'),indent=2)+'\n')
    return generated,original

class Stream(BaseStream):
    def float(self,v):self.word(v['bits'])if isinstance(v,dict)else super().float(v)
    def text_words(self,s):self.word(len(s.encode()));[self.word(b)for b in s.encode()]

def encode_provider(w,provider):
    w.word(len(provider['rails']))
    for rail in provider['rails']:
        w.text_words(rail['name']);w.word(rail['closed']);w.word(len(rail['points']))
        for point in rail['points']:
            for v in point:w.float(v)
        raw=rail.get('native');w.word(raw is not None)
        if raw is not None:w.word(len(raw));[w.word(v)for v in raw]
    w.text_words(json.dumps(provider.get('manifest',{})))
    segments=provider['segments'];w.word(len(segments))
    for s in segments:
        for v in s['start']+s['end']:w.float(v)
        w.wide(s['owner']);[w.wide(v)for v in s['guids']];w.word(s['segment']);w.word(s['flags'])
        for v in s['bounds']:w.float(v)
        w.wide(s['rail_index'])
    w.word(len(provider['rails']))
    for guids in provider['guids']:[w.wide(v)for v in guids]
    w.word(len(provider['assets']))
    for source_,indices,identity in provider['assets']:
        w.text_words(source_[0]);w.text_words(source_[1]);w.wide(source_[2]);w.wide(source_[3]);w.word(identity);w.word(len(indices));[w.word(v)for v in indices]

def authored_provider(points,name='authored-independent-rail',closed=False):
    points=[[world.value(world.bits(x))for x in p]for p in points];rail=dict(name=name,closed=closed,points=points);guid=1469598103934665603
    for b in name.encode()+b''.join(struct.pack('>f',v)for p in points for v in p):guid=((guid^b)*1099511628211)&0xffffffffffffffff
    guids=[guid,0x2c7017070007004a];original=points;edges=points+[points[0]]if closed and points[-1]!=points[0]else points
    f=lambda v:world.value(world.bits(v));segments=[]
    for n,(a,b)in enumerate(zip(edges,edges[1:])):
        delta=[f(b[i]-a[i])for i in range(3)];end=[f(f(f(-2*d)+f(3*d))+a[i])for i,d in enumerate(delta)]
        segments.append(dict(start=a+[1.],end=end+[1.],owner=1,guids=guids,segment=n,flags=0x80000000 if abs(end[0]-a[0])<=world.value(0x37800000)and abs(end[2]-a[2])<=world.value(0x37800000)else 0,bounds=[min(a[i],end[i])for i in range(3)]+[max(a[i],end[i])for i in range(3)],rail_index=0))
    return dict(rails=[rail],segments=segments,guids=[guids],assets=[(('', 'host-authored',0,0),list(range(len(segments))),False)])

def stock_provider():
    f=lambda v:world.value(world.bits(v));rails=[];segments=[];guids=[];records=[];asset_indices=[[],[]]
    for rail_index in range(3):
        asset=rail_index%2;identity=('fixture-stream.pkg',f'fixture-section-{asset}',asset+7,256+asset*4096);source_rail=rail_index+11;name=f'{identity[1]}_{identity[2]}_{source_rail}';ids=[0x1122334455667788,0x8877665544332211+rail_index];guids.append(ids);count=24
        header=[ids[0]&0xffffffff,ids[0]>>32,ids[1]&0xffffffff,ids[1]>>32,0x104+rail_index,0xf100+rail_index,count];raw=list(header)
        for j in range(count):
            x=f((j%4-1.5)*.16);z=f((j//4-2.5)*.18);a=[f(.011*(rail_index+1)),0.,f(-.013),0.];b=[f(-.021),0.,f(.027),0.];c=[f(.04),0.,f(.12),0.];d=[x,f(-.06-.002*rail_index),z,1.];end=[f(f(a[i]+b[i])+f(c[i]+d[i]))for i in range(4)];bounds=[f(min(d[i],end[i])-.037)for i in range(3)]+[f(max(d[i],end[i])+.043)for i in range(3)];words=[world.bits(v)for v in a+b+c+d+[0.]*4+bounds[:3]+[0.]+bounds[3:]+[0.]]+[0xabcdef00+j,rail_index];assert len(words)==30;raw+=words
            asset_indices[asset].append(len(segments));segments.append(dict(start=d,end=end,owner=rail_index+1,guids=ids,segment=j,flags=0,bounds=bounds,rail_index=source_rail))
        rails.append(dict(name=name,closed=False,points=[],native=raw));records.append(dict(stream_file=identity[0],asset_id=identity[1],section_index=identity[2],section_offset=identity[3],rail_index=source_rail,spline_id=f'{ids[0]:016x}',type_signature=f'{ids[1]:016x}',segment_count=count,flags=header[4],trailing_word=header[5],closed=False))
    return dict(rails=rails,segments=segments,guids=guids,assets=[(('fixture-stream.pkg',f'fixture-section-{a}',a+7,256+a*4096),indices,True)for a,indices in enumerate(asset_indices)],manifest=dict(grind_coordinate_policy=dict(mode='world_space'),grind_splines=records))

def corpus():
    defs,state=declarations();canon,_=protocol.declarations();all_defs=OrderedDict(canon);all_defs.update(defs);programs=[]
    def processed(seed=0):
        p=protocol.default('ProcessedPhysicsInput',canon,seed)
        p.update(flags_2468=0x2000,flags_2472=0,flags_2476=0,flags_2480=0,flags_2484=0,flags_2488=0,state_2504=100,state_2508=100,category_2512=100,category_2516=100,scalar_2652=3.,state_timer_2664=.5,timestep_2604=1/60,wheel_count_2556=2,actor_query_2948=91,actor_query_2952=0xffffffff,grind_words_2532_2536=[0,0])
        p['vectors_400_416'][0]=[world.bits(x)for x in (0,0,3,0)];p['vectors_544_560_592_608'][0]=[0,world.bits(1),0,0];p['vectors_544_560_592_608'][3]=[0,0,world.bits(3),0];p['vectors_464_480_496_512_528'][0]=[world.bits(1),0,0,0]
        return p
    def context(angle=0,height=0):
        import math
        c,s=math.cos(angle),math.sin(angle)
        return dict(board=[[c,0,-s,0],[0,1,0,0],[s,0,c,0],[0,height,0,1]],air_counter=20,tip_state=100,air_targeting_grind_9653=False,balance_2720=0.,translation_2796=0.,stability_nudge_2800=0.,up_down_2804=0.,grab_min_height_2808=0.)
    for seed in range(32):
        provider=authored_provider([[0,-.03,-3],[0,-.03,3]])
        if seed%4==1:provider=authored_provider([[-3,-.015,0],[3,-.015,0]])
        if seed%4==2:provider=authored_provider([[-.3,-.01,-3],[-.3,-.01,3],[.3,-.01,3],[.3,-.01,-3]],closed=True)
        if seed%4==3:provider=authored_provider([[0,-.24,-3],[0,.3,0],[0,-.24,3]])
        commands=[]
        for n in range(18):
            p=processed(seed+n);state_id=(100,201,400,401,402,403,404,701,300)[(n//2)%9];p['state_2508']=state_id;p['category_2512']=state_id//100*100 if state_id!=701 else 700;p['state_2504']=(100,402,404)[n%3]
            c=context((0,.2,.9,1.57)[seed%4],(-.06,-.025,0.,.02,.04,.12)[(seed+n)%6]);c['tip_state']=p['state_2504'];c['translation_2796']=(0.,.731,-.731)[n%3];c['balance_2720']=(0.,.3,-.3)[(n//3)%3];c['air_targeting_grind_9653']=n%3==1
            if n in(6,12):commands.append(dict(op=2))
            if n==8:p['grind_words_2532_2536']=[3,2]
            commands.append(dict(op=0,p=p,c=c,fail=0));post={key:value for key,value in c.items()if key in dict(defs['PostContext'])};post['up_down_2804']=(.4,-.4)[n%2]
            fresh=dict(p);fresh['state_2504']=403 if n%3==0 else p['state_2504'];commands.append(dict(op=1,p=fresh,c=post,fail=0))
        programs.append(dict(label='complete original pre/post with fresh producers and real authored geometry',provider=provider,world=seed%5,commands=commands))
    # Failed source callbacks use the same live query implementation before the
    # injected error. They preserve all earlier original manager mutations.
    for fail in range(1,9):
        p=processed();c=context();programs.append(dict(label='material/surface partial-failure prefix',provider=authored_provider([[0,-.05,-3],[0,-.05,3]]),world=0,commands=[dict(op=0,p=p,c=c,fail=fail)]))
    witnesses=[('fifty-fifty',[[0,-.08,-3],[0,-.08,3]],context(height=.0),0,0,401),
        ('boardslide',[[-3,-.015,0],[3,-.015,0]],context(),0,0,400),
        ('tipslide',[[-3,0,.34],[3,0,.34]],context(height=.02),0,0,402),
        ('one-truck',[[0,-.08,-3],[0,-.08,.1]],context(),0,0,403),
        ('backslash',[[-3,-.03,.34],[3,-.03,.34]],context(height=.0),5,0,402),
        ('darkslide',[[-3,-.015,0],[3,-.015,0]],context(),0,0x200000,400)]
    for label,points,c,terrain,flags,state_id in witnesses:
        p=processed();p['state_2508']=state_id;p['category_2512']=400;p['flags_2484']=flags
        if label=='backslash':c['board'][3][2]=.6
        if label=='darkslide':c['board'][1]=[0,-1,0,0];c['board'][2]=[0,0,-1,0]
        post={key:value for key,value in c.items()if key in dict(defs['PostContext'])}
        programs.append(dict(label='explicit authored '+label+' witness',provider=authored_provider(points),world=terrain,commands=[dict(op=0,p=p,c=c,fail=0),dict(op=1,p=p,c=post,fail=0)]*4))
    for word in (0,1,0x7fffffff,0x80000000,0xffffffff,152,153):
        values={f:protocol.default(k,all_defs,0)for f,k in state};values.update(previous_state=403,engagement_counter=word,cooldown=word,grind_history=word,secondary_history=word,grounded_frames=word,air_frames=word,low_wheel_frames=word,previous_proximity=True,previous_air_target=True)
        values['balance'].update(elapsed=1.,exit_angle_degrees=20.,entry_delay=.1,frames_away=word if word<0x80000000 else word-0x100000000)
        values['jumper'].update(family=3,energy=.5,cooldown=word)
        p=processed();p['state_2508']=403;p['category_2512']=400;c=context()
        programs.append(dict(label='exact signed/wrapping histories and reset retaining child controllers',provider=authored_provider([[0,-.05,-3],[0,-.05,3]]),world=0,commands=[dict(op=3,state=values),dict(op=0,p=p,c=c,fail=0),dict(op=1,p=p,c={key:value for key,value in c.items()if key in dict(defs['PostContext'])},fail=0),dict(op=2)]))
    for angle in (world.bits(15),world.bits(15)+1,world.bits(28),world.bits(28)+1):
        for fail in(0,1):
            values={f:protocol.default(k,all_defs,0)for f,k in state};values.update(previous_state=403,engagement_counter=0,cooldown=0,grind_history=0,secondary_history=0)
            values['balance'].update(elapsed=0.,exit_angle_degrees=dict(bits=angle),entry_delay=2.,frames_away=21)
            values['jumper'].update(family=3,energy=.6,cooldown=0)
            p=processed();p.update(state_2508=403,category_2512=400);c=context();post={key:value for key,value in c.items()if key in dict(defs['PostContext'])}
            programs.append(dict(label='exact force-exit open/closed interval and failed nearest-world query',provider=authored_provider([[30,0,-3],[30,0,3]]),world=1,commands=[dict(op=3,state=values),dict(op=0,p=p,c=c,fail=0),dict(op=1,p=p,c=post,fail=fail)]))
    for terrain in range(6):
        p=processed();p.update(state_2508=401,category_2512=400);c=context();post={key:value for key,value in c.items()if key in dict(defs['PostContext'])}
        programs.append(dict(label='complete WMET provenance, repeated GUIDs, authored bounds and capacity40 octree order',provider=stock_provider(),world=terrain,commands=[dict(op=0,p=p,c=c,fail=0),dict(op=1,p=p,c=post,fail=0)]*4))
    return programs,all_defs,state

def encode(programs,defs,state):
    w=Stream();w.word(len(programs))
    for case in programs:
        encode_provider(w,case['provider']);w.word(case['world']);w.word(len(case['commands']))
        for command in case['commands']:
            op=command['op'];w.word(op)
            if op in(0,1):protocol.encode(w,'ProcessedPhysicsInput',command['p'],defs);protocol.encode(w,'PreContext'if op==0 else 'PostContext',command['c'],defs);w.word(command['fail'])
            elif op==3:
                for f,k in state:protocol.encode(w,k,command['state'][f],defs)
    return bytes(w.data)

def preflight():
    programs,defs,state=corpus();blob=encode(programs,defs,state)
    cpp,rust,private=helpers(declarations()[0],state)
    assert all((PLUGIN/f'Source/AtelierSkate/Private/Native/{unit}.cpp').is_file()for unit in UNITS)
    return blob,programs

def decode(data,programs):
    defs,state=declarations();canonical,_=protocol.declarations();all_defs=OrderedDict(canonical);all_defs.update(defs);r=protocol.Reader(data);frames=[]
    def text():return bytes(r.word()for _ in range(r.word())).decode()
    def snapshot():return {f:r.value(k,all_defs)for f,k in state}
    def provider():
        values=[]
        for _ in range(r.word()):
            edge=dict(start=r.value('[f32;4]',all_defs),end=r.value('[f32;4]',all_defs),owner=r.wide(),guids=[r.wide(),r.wide()],segment=r.word(),flags=r.word(),bounds=r.value('[f32;6]',all_defs),stream=text(),asset=text(),section=r.wide(),offset=r.wide(),rail=r.wide());values.append(edge)
        return values
    def plan():return dict(center=r.value('[f32;4]',all_defs),up=r.value('[f32;4]',all_defs),direction=r.value('[f32;4]',all_defs),probes=[r.value('Probe',all_defs)for _ in range(r.word())])
    def pending():
        f=r.value('GrindInvestigationFields',all_defs);metadata=None
        if r.word():metadata=[r.wide(),r.wide()]if r.word()else None
        geometry=None
        if r.word():geometry=dict(input=r.value('InvestigationInput',all_defs),plan=plan()if r.word()else None,hits=[r.value('ProbeHit',all_defs)if r.word()else None for _ in range(7)])
        return dict(fields=f,metadata=metadata,geometry=geometry)
    def trace(end):
        calls=[]
        while r.at<end:
            op=r.word();call=dict(op=op)
            if op==1:call['mode']=r.word()
            elif op==2:call.update(actor=[r.word(),r.word()],index=r.word(),probe=r.value('Probe',all_defs),hit=r.value('ProbeHit',all_defs)if r.word()else None)
            elif op==3:call.update(actor=[r.word(),r.word()],start=r.value('[f32;4]',all_defs),end=r.value('[f32;4]',all_defs),hit=r.value('[f32;4]',all_defs)if r.word()else None)
            else:raise AssertionError(op)
            calls.append(call)
        assert r.at==end;return calls
    for index,case in enumerate(programs):
        assert r.word()==index;size=r.word();end=r.at+size*4;initial=dict(provider=provider(),query=[r.word()for _ in range(r.word())],state=snapshot(),materials=[r.word()for _ in range(10)]);assert r.at==end
        assert r.word()==len(case['commands']);rows=[]
        for command in case['commands']:
            size=r.word();end=r.at+size*4;op=r.word();assert op==command['op'];row=dict(op=op,ok=r.word(),error=text(),calls=r.word());length=r.word();row['trace']=trace(r.at+length*4)
            row.update(state=snapshot(),processed=r.value('ProcessedPhysicsInput',all_defs),materials=[r.word()for _ in range(10)],pending=pending()if r.word()else None)
            if r.word():
                row['reasons']=[r.word()for _ in range(r.word())];row['observation']=[r.word()for _ in range((end-r.at)//4)]
            assert r.at==end,(index,op,r.at,end);rows.append(row)
        frames.append(dict(initial=initial,rows=rows))
    assert r.at==len(data),(r.at,len(data));return frames

def coverage(data,programs):
    frames=decode(data,programs);calls=Counter();families=Counter();post_families=Counter();modes=Counter();errors=Counter();histories=set();hits=0;reset_proofs=0;partial_proofs=0
    for case,frame in zip(programs,frames):
        assert len(frame['initial']['provider'])==len(case['provider']['segments'])
        prior=frame['initial']['state']
        for command,row in zip(case['commands'],frame['rows']):
            calls.update(c['op']for c in row['trace']);modes.update(c['mode']for c in row['trace']if c['op']==1);hits+=sum(bool(c.get('hit'))for c in row['trace'])
            histories.add(tuple(row['processed']['grind']['direction_1136']))
            if row['pending']and row['pending']['fields']['valid_1488']:families[row['pending']['fields']['family_1248']]+=1
            if row['processed']['grind']['valid_1488']:post_families[row['processed']['grind']['family_1248']]+=1
            if not row['ok']:errors[row['error']]+=1;partial_proofs+=row['state']!=prior
            if row['op']==2:
                assert row['state']['balance']==prior['balance']and row['state']['jumper']==prior['jumper']and row['state']['control']==prior['control']
                assert row['state']['secondary_history']==prior['secondary_history'];reset_proofs+=1
            if command.get('fail')and not row['ok']:assert row['calls']==command['fail'],(command,row)
            prior=row['state']
    assert calls[1]>100 and calls[2]>100 and calls[3]>0,calls
    assert modes[0]and modes[1]and modes[2],modes
    assert all(families[f]>0 for f in(0,1,2,3,5))and post_families[4]>0,(families,post_families)
    assert hits>10 and len(histories)>4 and reset_proofs>=60 and partial_proofs>=6,(hits,len(histories),reset_proofs,partial_proofs)
    assert all(errors[f'injected callback {i}']for i in range(1,8)),errors
    assert max(len(f['initial']['query'])for f in frames)==40
    return dict(calls=dict(calls),materials=dict(modes),pre_families=dict(families),post_families=dict(post_families),hit_observations=hits,reset_child_retention=reset_proofs,partial_writes=partial_proofs,errors=dict(errors),distinct_published_directions=len(histories))

def build(output,target):
    cpp,rust=prepare(output);reference=build_probe(output,'player-grind-input-reference',rust,target,bevy=True,extra_sources=aliases())
    live=PLUGIN/'Source/AtelierSkate/Private/Native';snapshot=output/'native-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir();units=tuple(dict.fromkeys(physical.UNITS+UNITS))
    for p in live.glob('*.h'):shutil.copy2(p,snapshot/p.name)
    for u in units:shutil.copy2(live/f'{u}.cpp',snapshot/f'{u}.cpp')
    copied=snapshot/cpp.name;shutil.copy2(cpp,copied);native=output/'player-grind-input-cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/f'{u}.cpp')for u in units],str(copied),'-o',str(native)],check=True)
    (output/'native-provenance.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in sorted(snapshot.iterdir())},indent=2)+'\n');return native,reference

def settings_failures(original):
    import copy
    queries=[('physics_grinds','default','ExitLeanAngleVsTime','words')]+[('physics_grinds','default',name,'words')for name in('FrictionVsTime','DVEntryThreshScalarVsSinSlope','VertEngagementHelpVsVelY','TimeOfGravityReliefVsVerticalSpeed','GravityReliefTimeVsLinearSpeed')]+[('physics_grinds','default',name,'float')for name in('TruckToWheel','DeckCenterToTruck','TestDepthEpsilon','TestDepth')]+[('physics_wipeout','default','Wipeout_AirMaxSpeedIntoCollisionNearGrind','float')]
    for at,query in enumerate(queries):
        value=copy.deepcopy(original)
        for next_ in queries[at:]:settings_probe.mutate(value,next_,dict(type='EA::Reflection::Int32',data='00000000')if next_[3]=='float'else dict(type='EA::Reflection::Float',data='00000000'))
        yield query,value

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--target-dir',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    for n in('result.json','first-divergence.json'):(out/n).unlink(missing_ok=True)
    blob,programs=preflight();(out/'input.bin').write_bytes(blob);(out/'cases.json').write_text(json.dumps(programs,indent=2)+'\n');native,reference=build(out,a.target_dir)
    settings=out/'settings.native';settings.write_bytes(converter.encode_settings(a.assets/'private/stock/skater-collections.json'))
    expected=subprocess.check_output([str(reference),str(a.assets.resolve())],input=blob);actual=subprocess.check_output([str(native),str(settings)],input=blob);(out/'reference.bin').write_bytes(expected);(out/'native.bin').write_bytes(actual)
    if expected!=actual:
        at=next((i for i,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)));(out/'first-divergence.json').write_text(json.dumps(dict(byte=at,reference_length=len(expected),native_length=len(actual)),indent=2)+'\n');raise AssertionError('Player grind input differs')
    proof=coverage(expected,programs);negative=[];original=json.loads((a.assets/'private/stock/skater-collections.json').read_text())
    for n,(query,fixture)in enumerate(settings_failures(original)):
        root=out/f'settings-failure-{n}';json_path=root/'private/stock/skater-collections.json';json_path.parent.mkdir(parents=True,exist_ok=True);json_path.write_text(json.dumps(fixture));settings.write_bytes(converter.encode_settings(json_path))
        x=subprocess.check_output([str(reference),str(root),'--settings-only']);y=subprocess.check_output([str(native),str(settings),'--settings-only']);assert x==y,(query,x,y);r=protocol.Reader(x);assert r.word()==0;error=bytes(r.word()for _ in range(r.word())).decode();assert error and r.at==len(x);negative.append(dict(query=query,error=error))
    result=dict(passed=True,programs=len(programs),commands=sum(len(p['commands'])for p in programs),exact_bytes=len(expected),sha256=hashlib.sha256(expected).hexdigest(),coverage=proof,settings_failures=negative,boundary='Complete original grind pre/post manager and real world queries. Global player scheduling, moving grind providers and native converter parser are separate boundaries.');(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':historical.run_cli(main)
