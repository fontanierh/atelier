#!/usr/bin/env python3
"""Whole original PlayerState Load/Current/Reset; frame dispatch is separate.

Only root compiles/runs through the render guard. --preflight stages source and
checks protocol/provenance without invoking a compiler or either executable.
Fixtures are generated one at a time, retaining their identity and output.
"""
import argparse
from collections import OrderedDict, Counter
from functools import lru_cache
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import check_player_state_parity as state
import check_state_conditioning_parity as filtered
import check_ground_control_settings_parity as stock
import player_input_protocol as wire
from camera_reference_build import frozen_sources
from check_gesture_parity import PLUGIN, converter
from session_parity import digest

CODE=PLUGIN/'Source/AtelierSkate/Private/Native'
HOST='crates/skate-host/src/'
GROUND='crates/skate-core/src/riding/grounded/state/output.rs'
UNITS=('NameId','Settings','StockSettingsReader','AnimationName','FilteredState','PhysicalPhase','PlayerStateRegistry','PlayerStateRuntime')
QUERIES=tuple((category,'default',name,'float')for category in ('physics_airstates','physics_state_skitching')for name in ('NaturalAirMaxDist','NaturalAirMinDist','NaturalAirTime'))+(('physics_animation','default','MaxDeckZAxisYForAnimatedDeck','float'),)
STATES=filtered.STATES
RENAMES={'SkateboardMotionOutput':'GroundSkateboardMotionOutput','StateRecordOutput':'GroundStateRecordOutput','IntentRecordOutput':'GroundIntentRecordOutput'}

@lru_cache(maxsize=None)
def declarations():
    defs,_,_=state.declarations();selected=OrderedDict((k,defs[k])for k in ('StateSelector','TwoStageThresholds'))
    source=state.trees.source_at_reference(GROUND);ground=OrderedDict()
    for name in ('SkateboardMotionOutput','GroundVelocityProjectionOutput','GroundRecordOutput','StateRecordOutput','IntentRecordOutput','PhysicsGroundOutput'):
        m=re.search(r'\bstruct '+name+r'\s*\{',source);assert m,name
        body=re.sub(r'//[^\n]*','',source[m.end():source.index('\n}',m.end())])
        ground[name]=[(f,re.sub(r'\s+','',k).replace('Vector4','[f32;4]'))for f,k in re.findall(r'^\s*pub\s+(\w+)\s*:\s*([^,\n]+),',body,re.M)]
        assert ground[name]
    return selected,ground

def helpers():
    selected,ground=declarations();cpp,rust=state.helpers(selected)
    cp='\n'.join(f'void Observe(Output&,const {name}&);{name} Read{name}(Input&);'for name in ground)
    rp=''
    for name,fields in ground.items():
        cp+=f'\nvoid Observe(Output& o,const {name}& s){{'+''.join(wire.observe_expr(k,'s.'+f,'cpp')for f,k in fields)+'}'
        cp+=f'\n{name} Read{name}(Input& i){{{name} s;'+''.join('s.'+f+'='+wire.read_expr(k,'cpp')+';'for f,k in fields)+'return s;}'
        rp+=f'\nfn observe_{name}(o:&mut Output,s:&{name}){{'+''.join(wire.observe_expr(k,'s.'+f,'rust')for f,k in fields)+'}'
        rp+=f'\nfn read_{name}(i:&mut Input)->{name}{{{name}{{'+''.join(f+':'+wire.read_expr(k,'rust')+','for f,k in fields)+'}}'
    for old,new in RENAMES.items():cp=re.sub(r'\b'+old+r'\b',new,cp)
    rust='use skate_core::player::{state::PhysicalStateId,selector::{StateSelector,conditions::TwoStageThresholds}};\nuse skate_core::riding::grounded::state::output::*;\n'+rust+rp
    cpp+=cp+'''\nFilteredStateOutput ReadFilteredStateOutput(Input& i){return {FilteredCategory(i.Word()),FilteredCategory(i.Word()),i.Word()!=0,i.Grind(),i.Float()};}\n'''
    rust+='\nfn read_FilteredStateOutput(i:&mut Input)->filtered::FilteredStateOutput{filtered::FilteredStateOutput{category:category(i.word()),previous_category:category(i.word()),grinding:i.word()!=0,grind:i.grind(),last_grind_distance:i.float()}}\n'
    rust+='fn category(v:u32)->filtered::FilteredCategory{use filtered::FilteredCategory::*;match v{0=>Invalid,1=>Ground,2=>Air,3=>Grind,4=>Wipeout,5=>Teleport,6=>Offboard,7=>OffboardAir,_=>panic!("fixture category")}}\n'
    return cpp,rust

def verified_wire():
    native=PLUGIN/'Tests/Native/state_conditioning_probe.cpp';reference=PLUGIN/'Tests/Reference/state_conditioning_probe.rs'
    cn=native.read_text();begin=cn.index('struct Input\n');end=cn.index('\nint main(');cpp=cn[begin:end]
    cr=reference.read_text();rb=cr.index('struct Input{');re_=cr.index('\nfn main()');rust=cr[rb:re_]
    assert hashlib.sha256(cpp.encode()).hexdigest()=='d875806492650932b21d7e80754d07043ba50a1961ef5a6148aed898d26479a7'
    assert hashlib.sha256(rust.encode()).hexdigest()=='918d928842db7debaf3a7f31837fde0e9548dc5975827b7aaa7a2d7eaec4be70'
    # Exact previously verified wire blocks, followed only by extra wire methods.
    cpp=cpp.replace('    detail::DataReader r;', '''    template<std::size_t N>std::array<std::uint32_t,N> Words(){std::array<std::uint32_t,N> a;for(auto& x:a)x=Word();return a;}
    template<class T,std::size_t N,class F>std::array<T,N> Array(F f){std::array<T,N> a;for(auto& x:a)x=f(*this);return a;}
    template<class T,class F>std::optional<T> Optional(F f){return Word()?std::optional<T>(f(*this)):std::nullopt;}
    std::string String(){const auto n=Word();auto s=r.RawString(n);r.RawString((4-n%4)%4);return s;}
    detail::DataReader r;''')
    rust+='\nimpl Input{fn string(&mut self)->String{let n=self.word()as usize;let s=String::from_utf8(self.bytes[self.at..self.at+n].to_vec()).unwrap();self.at+=((n+3)/4)*4;s}}\n'
    return cpp,rust,dict(native=dict(path=native.relative_to(PLUGIN).as_posix(),file_sha256=digest(native),begin_byte=begin,end_byte=end,block_sha256=hashlib.sha256(cn[begin:end].encode()).hexdigest()),reference=dict(path=reference.relative_to(PLUGIN).as_posix(),file_sha256=digest(reference),begin_byte=rb,end_byte=re_,block_sha256=hashlib.sha256(cr[rb:re_].encode()).hexdigest()))

def header_closure():
    pending=[CODE/(u+'.cpp')for u in UNITS]+[PLUGIN/'Tests/Native/player_state_runtime_probe.cpp'];result={}
    while pending:
        p=pending.pop()
        for name in re.findall(r'^#include\s+"([^"]+)"',p.read_text(),re.M):
            q=CODE/name
            if q.name not in result:assert q.exists(),q;result[q.name]=q;pending.append(q)
    return result

def prepare(output):
    # One archive workspace only; each original byte count/hash is recorded
    # before appending observers. No redundant full-tree copy is needed.
    source,report=frozen_sources(output);original_lengths={p.relative_to(source).as_posix():p.stat().st_size for p in source.rglob('*.rs')}
    report['original_source_bytes']=original_lengths
    cpp,rust=helpers();cp,rp,wire_meta=verified_wire();crate=source/'atelier-host';host=source/HOST
    observer=(PLUGIN/'Tests/Reference/player_state_runtime_observer.rs').read_bytes()
    extensions={'physics/player_state.rs':b'\n'+observer,'physics.rs':b'\npub(crate)fn migration_player_state_run(stock:&skate_data::collections::Collections,fixture:&skate_data::collections::Collections,i:&mut crate::Input,o:&mut crate::Output)->Result<(),String>{player_state::migration_player_state_run(stock,fixture,i,o)}\n'}
    staged={}
    for p in sorted(host.rglob('*.rs')):
        rel=p.relative_to(host).as_posix()
        # The complete original lib declaration prefix is inserted into the
        # probe target below, rather than creating a second automatic library
        # target without the probe-only Input/Output declarations.
        if rel=='lib.rs':continue
        raw=p.read_bytes();extra=extensions.get(rel,b'');dest=crate/'src'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw+extra)
        assert dest.read_bytes()[:len(raw)]==raw
        staged[rel]=dict(original_prefix_bytes=len(raw),original_prefix_sha256=digest(p),append_sha256=hashlib.sha256(extra).hexdigest(),generated_sha256=digest(dest))
    core=source/filtered.FILTERED
    extension='''
pub fn cache(s:&FilteredState)->GrindState{s.cached_grind}
impl FilteredState{pub fn migration_player_state_seed(&mut self,raw:[u32;9],g:GrindState){
    self.cached_grind=g;self.category=migration_player_state_category(raw[0]);self.previous_category=migration_player_state_category(raw[1]);self.previous_physics_state=raw[2]as i32;self.air_count=raw[3]as i32;self.nonspecific_count=raw[4]as i32;self.nonspecific_collision_free_count=raw[5]as i32;self.nonspecific_collision_count=raw[6]as i32;self.frames_since_ground_stairs=raw[7]as i32;self.must_change=raw[8]!=0;
}}
fn migration_player_state_category(v:u32)->FilteredCategory{use FilteredCategory::*;match v{0=>Invalid,1=>Ground,2=>Air,3=>Grind,4=>Wipeout,5=>Teleport,6=>Offboard,7=>OffboardAir,_=>panic!("fixture category")}}
'''
    core.write_bytes(core.read_bytes()+extension.encode())
    template=PLUGIN/'Tests/Reference/player_state_runtime_probe.rs';body=template.read_text().replace('// GENERATED_WHOLE_HOST_MODULE_DECLARATIONS',(host/'lib.rs').read_text()).replace('// GENERATED_VERIFIED_FILTERED_WIRE',rp).replace('// GENERATED_DECLARATION_PROTOCOL',rust)
    probe=crate/'src/migration_probe.rs';probe.write_text(body)
    cargo=crate/'Cargo.toml';cargo.write_text(cargo.read_text()+'''\nskate-core={path="../crates/skate-core"}
skate-data={path="../crates/skate-data"}
skate-net={path="../crates/skate-net"}
half="2.7.1"
bevy={version="0.19",default-features=false,features=["std","multi_threaded","bevy_log"]}
[[bin]]
name="player-state-runtime-reference"
path="src/migration_probe.rs"
''')
    snapshot=output/'native-source';snapshot.mkdir(exist_ok=True)
    headers=header_closure()
    for p in list(headers.values())+[CODE/(u+'.cpp')for u in UNITS]:shutil.copy2(p,snapshot/p.name)
    np=PLUGIN/'Tests/Native/player_state_runtime_probe.cpp';generated=np.read_text().replace('// GENERATED_VERIFIED_FILTERED_WIRE',cp).replace('// GENERATED_DECLARATION_PROTOCOL',cpp);(snapshot/np.name).write_text(generated)
    # Snapshot status is reported, never silently equated with tracked closure.
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip())
    tracked=set(subprocess.check_output(['git','ls-files','--',CODE.relative_to(root).as_posix()],cwd=root,text=True).splitlines())
    untracked=[p.name for p in headers.values()if p.relative_to(root).as_posix()not in tracked]
    report.update(staged_host_original_prefixes=staged,whole_host_module_declarations_sha256=digest(host/'lib.rs'),core_append_sha256=hashlib.sha256(extension.encode()).hexdigest(),verified_filtered_wire=wire_meta,native_units=UNITS,required_untracked_headers=sorted(untracked),immutable_native_source_sha256={p.name:digest(p)for p in sorted(snapshot.iterdir())},generated_reference_probe_sha256=digest(probe),proof_files={p.name:digest(p)for p in (Path(__file__),np,template,PLUGIN/'Tests/Reference/player_state_runtime_observer.rs')},boundary='Whole original host source retained. Only actual PlayerState Load/Current/Reset and registry observations execute; no frame dispatch, conditioning publication, physical Grind or landing stage. Separate native landing retention invariant has no claimed original stage.')
    audit(source,report);(output/'provenance.json').write_text(json.dumps(report,indent=2)+'\n')
    return source,snapshot,cargo,report

def audit(source,report):
    for rel,sha in report['original_source_sha256'].items():
        raw=(source/rel).read_bytes();assert hashlib.sha256(raw[:report['original_source_bytes'][rel]]).hexdigest()==sha,rel
    for rel,row in report['staged_host_original_prefixes'].items():assert hashlib.sha256((source/'atelier-host/src'/rel).read_bytes()[:row['original_prefix_bytes']]).hexdigest()==row['original_prefix_sha256'],rel

def zero(kind,defs,n=0):
    a=wire.array(kind);o=wire.option(kind)
    if a:return [zero(a[0],defs,n+j)for j in range(a[1])]
    if o:return None if n%3==0 else zero(o,defs,n+1)
    if kind=='bool':return bool(n%2)
    if kind=='f32':return dict(bits=(0,0x80000000,0x3e0c49ba,0xbea24dd3,0x7fc12345,0xff812345)[n%6])
    if kind in ('u32','i32'):return (0,1,0x7fffffff,0x80000000,0xffffffff,0xdeadbeef)[n%6]
    return {f:zero(k,defs,n+j+1)for j,(f,k)in enumerate(defs[kind])}

def seed(n,ground):
    selector={f:(STATES[n%26]if f=='current_state'and n%2 else None)if f=='current_state'else bool((n+j)%2)if k=='bool'else (n*137+j*317+1)&0xffffffff for j,(f,k)in enumerate(declarations()[0]['StateSelector'])}
    return dict(lifecycle=STATES[n%26],requested=STATES[(n+7)%26],selector=selector,filtered=filtered.seed(n%8,0x7fffffff if n%2 else -1,n,prior=STATES[(n+2)%26]),publication=[n%8,(n+1)%8,n%2]+filtered.grind(n+7)+[0x7fc12345]if n%3 else None,ground=zero('PhysicsGroundOutput',ground,n)if n%2 else None,post=[0x12345678+n,0x7fc12345,0x80000000,0xdeadbeef-n,n+71,n+113,0xffffffff-n,0x7fc12345,n%2,(n+1)%2,n%2,1,(n+1)%2],flags=[(n+j)%2 for j in range(36)],counters=[0xffffffff-n,0x80000000+n],thresholds=[0x7fc12345,0x80000000,0x7f800000,0xff800000,0x3e0c49ba,0xbea24dd3,0xff812345],initialized=n%2)

def corpus():
    _,ground=declarations();cases=[]
    def add(label,commands):cases.append(dict(label=label,commands=commands))
    modes=('', 'normal','hardcore','unregistered mode','\0ignored','日本語 mode')
    add('actual stock construction ignores mode',[dict(op=0,mode=m)for m in modes]+[dict(op=3)])
    for n in range(26):
        add('selective reset retains complete state '+str(STATES[n]),[dict(op=1,seed=seed(n,ground)),dict(op=3),dict(op=2),dict(op=2),dict(op=3),dict(op=1,seed=seed(n+26,ground)),dict(op=4,mode=modes[n%len(modes)]),dict(op=3),dict(op=2),dict(op=0,mode=modes[(n+1)%len(modes)]),dict(op=2)])
    return cases

class Stream(filtered.stock.Stream):
    def float(self,v):self.word(v['bits'])if isinstance(v,dict)else super().float(v)
    def string(self,s):
        b=s.encode();self.word(len(b));self.data.extend(b);self.data.extend(b'\0'*((4-len(b)%4)%4))

def encode(cases):
    selected,ground=declarations();plain=state.plain(selected);w=Stream();w.word(len(cases))
    for c in cases:
        w.word(len(c['commands']))
        for cmd in c['commands']:
            op=cmd['op'];w.word(op)
            if op in(0,4):w.string(cmd['mode'])
            elif op==1:
                s=cmd['seed'];w.word(s['lifecycle']);w.word(s['requested']);wire.encode(w,'StateSelector',s['selector'],plain)
                for v in s['filtered']:w.word(v)
                w.word(s['publication']is not None)
                if s['publication']is not None:
                    for v in s['publication']:w.word(v)
                w.word(s['ground']is not None)
                if s['ground']is not None:wire.encode(w,'PhysicsGroundOutput',s['ground'],ground)
                for v in s['post']+s['flags']+s['counters']+s['thresholds']+[s['initialized']]:w.word(v)
    return bytes(w.data)

def read_snapshot(r):
    selected,ground=declarations();s=dict(current=r.word(),active=r.words(2),requested=r.word(),selector=r.value('StateSelector',state.plain(selected)),filtered=r.words(27),publication=r.words(22)if r.word()else None,ground=r.value('PhysicsGroundOutput',ground)if r.word()else None,post=r.words(13),flags=r.words(36),counters=r.words(2),thresholds=r.words(7),initialized=r.word(),registry=[r.words(4)for _ in STATES]);return s

class Reader(wire.Reader):
    def words(self,n):return [self.word()for _ in range(n)]
    def string(self):
        n=self.word();s=self.data[self.at:self.at+n].decode();self.at+=((n+3)//4)*4;return s

def decode(raw,cases):
    r=Reader(raw);assert r.word()==len(cases);histories=[]
    for c,case in enumerate(cases):
        assert r.word()==c;initial=read_snapshot(r);assert r.word()==len(case['commands']);rows=[]
        for n,cmd in enumerate(case['commands']):
            assert r.words(3)==[c,n,cmd['op']];rows.append(dict(loaded=r.word(),error=r.string(),state=read_snapshot(r)))
        histories.append(dict(initial=initial,rows=rows))
    assert r.at==len(raw);return histories

def defaults(s):
    assert s['current']==700 and s['active'][0]==700 and s['requested']==700
    assert s['selector']=={f:None if f=='current_state'else 0 for f,_ in declarations()[0]['StateSelector']}
    assert s['filtered']==[0]*8+[1]+[0xffffffff,0xffffffff]+[0]*10+[0,0]+[0xffffffff]*4
    assert s['publication']is None and s['ground']is None
    assert s['post']==[0]*4+[1000,0,100,0]+[0]*5
    assert s['flags']==[0]*36 and s['counters']==[0,0]and s['initialized']==0
    assert {r[0]for r in s['registry']if not r[1]}=={104,105,202}

def coverage(histories,cases,error):
    proof=Counter();currents=set();retained=set();modes=set()
    for h,c in zip(histories,cases):
        prior=h['initial'];defaults(prior)
        for row,cmd in zip(h['rows'],c['commands']):
            s=row['state'];op=cmd['op'];assert s['current']==s['active'][0];currents.add(s['current'])
            if op in(0,4):
                modes.add(cmd['mode']);expected=error if op==4 else '';assert row['error']==expected and row['loaded']==(not expected)
                if expected:assert s==prior;proof['failed construction retains full owner']+=1
                else:defaults(s);proof['full construction']+=1
                if op==0:assert s['thresholds']==h['initial']['thresholds'],'mode changed original default-key settings'
            if op==2:
                assert s['filtered']==h['initial']['filtered']and s['publication']is None and s['ground']is None
                expected=copy.deepcopy(prior);expected.update(filtered=h['initial']['filtered'],publication=None,ground=None)
                for f in ('nonspecific_collision_free_frames','nonspecific_collision_frames','something_colliding_frames','two_wheel_counter','three_wheel_counter','post_grind_jump_counter','air_frames','skitch_exit_countdown'):expected['selector'][f]=0
                expected['selector']['teleport_countdown']=10;expected['post'][11]=0
                assert s==expected,(c['label'],cmd,s,expected)
                proof['selective reset']+=1;retained.add(tuple(s['post'][:11]+s['post'][12:]))
            if op==3:assert s==prior;proof['current is read only']+=1
            prior=s
    assert currents==set(STATES)and len(retained)>20 and len(modes)==6
    assert proof['selective reset']>=100 and proof['current is read only']>=75
    if error:assert proof['failed construction retains full owner']==26
    return dict(proof,distinct_current_states=len(currents),distinct_retained_post_histories=len(retained),ignored_modes=len(modes))

def minimal(original):
    selected={};allowed={}
    for q in QUERIES:
        chain,name=stock.resolve(original,q)
        for r in chain:selected[(r['class'],r['key'])]=r
        allowed.setdefault((chain[-1]['class'],chain[-1]['key']),set()).add(name)
    data=copy.deepcopy(original);data['collections']=[]
    for key,r in selected.items():
        r=copy.deepcopy(r);r['fields']={k:v for k,v in r['fields'].items()if k in allowed.get(key,set())};data['collections'].append(r)
    return data

def settings_specs():
    specs=[dict(label='stock',kind='stock',error='')]
    for n,q in enumerate(QUERIES):
        path='/'.join(q[:3]);specs.append(dict(label='ordered first failure '+str(n),kind='ordered',index=n,error='Expected float at '+path))
        for kind,error in (('missing','Missing stock field '+path),('short','Expected 1 big-endian words, found 0 bytes of hex'),('long','Expected 1 big-endian words, found 16 bytes of hex'),('nan','Non-finite stock float '+path),('inf','Non-finite stock float '+path),('negative_inf','Non-finite stock float '+path)):
            specs.append(dict(label=kind+' '+path,kind=kind,index=n,error=error))
    for category in ('physics_airstates','physics_state_skitching','physics_animation'):specs.append(dict(label='missing collection '+category,kind='collection',category=category,error='Missing stock collection '+category+'/default'))
    specs += [dict(label='valid raw finite edge scalars',kind='finite',error=''),dict(label='numeric identities and inheritance',kind='aliases',error='')]
    return specs

def fixture(base,spec):
    data=copy.deepcopy(base);kind=spec['kind']
    if kind=='ordered':
        for q in QUERIES[spec['index']:]:stock.mutate(data,q,dict(type='EA::Reflection::UInt32',data='deadbeef'))
    elif kind in('missing','short','long','nan','inf','negative_inf'):
        q=QUERIES[spec['index']]
        if kind=='missing':chain,name=stock.resolve(data,q);del chain[-1]['fields'][name];chain[-1]['parent']=''
        else:stock.mutate(data,q,dict(type='EA::Reflection::Float',data={'short':'','long':'0000000000000000','nan':'7fc12345','inf':'7f800000','negative_inf':'ff800000'}[kind]))
    elif kind=='collection':data['collections']=[r for r in data['collections']if converter.name_id(r['class'])!=converter.name_id(spec['category'])]
    elif kind=='finite':
        for q,w in zip(QUERIES,(0,0x80000000,1,0x80000001,0x7f7fffff,0xff7fffff,0x00800000)):stock.mutate(data,q,dict(type='EA::Reflection::Float',data=f'{w:08x}'))
    elif kind=='aliases':
        for r in list(data['collections']):
            parent=copy.deepcopy(r);parent['key']='inherited-'+r['key'];parent['fields']={f'Hash_{converter.name_id(n):016X}':v for n,v in parent['fields'].items()};parent['parent']='';r['parent']=parent['key'];r['fields']={};data['collections'].append(parent)
    return data

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--target-dir',type=Path);p.add_argument('--preflight',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    for n in('result.json','first-divergence.json'):(out/n).unlink(missing_ok=True)
    cases=corpus();blob=encode(cases);(out/'input.bin').write_bytes(blob);(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');(out/'settings-specs.json').write_text(json.dumps(settings_specs(),indent=2)+'\n')
    source,snapshot,cargo,report=prepare(out);report.update(histories=len(cases),commands=sum(len(c['commands'])for c in cases),input_bytes=len(blob),input_sha256=hashlib.sha256(blob).hexdigest());(out/'provenance.json').write_text(json.dumps(report,indent=2)+'\n')
    if a.preflight:print(json.dumps(dict(preflight=True,histories=report['histories'],commands=report['commands'],input_sha256=report['input_sha256'],native_units=UNITS,native_headers=len(header_closure()),original_modules=len(report['original_source_sha256']),host_modules=len(report['staged_host_original_prefixes']),required_untracked_headers=report['required_untracked_headers']),indent=2));return
    assert a.assets and a.target_dir,'guarded run requires --assets and --target-dir'
    subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(cargo),'--target-dir',str(a.target_dir.resolve()),'--bin','player-state-runtime-reference'],check=True);audit(source,report)
    reference=out/'player-state-runtime-reference';shutil.copy2(a.target_dir.resolve()/'release/player-state-runtime-reference',reference)
    native=out/'player-state-runtime-native';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(u+'.cpp'))for u in UNITS],str(snapshot/'player_state_runtime_probe.cpp'),'-o',str(native)],check=True)
    base=minimal(json.loads((a.assets/'private/stock/skater-collections.json').read_text()));live=out/'fixture/private/stock/skater-collections.json';live.parent.mkdir(parents=True,exist_ok=True);stock_path=out/'stock/private/stock/skater-collections.json';stock_path.parent.mkdir(parents=True,exist_ok=True);stock_path.write_text(json.dumps(base));stock_native=out/'stock.native';stock_native.write_bytes(converter.encode_settings(stock_path));results=[];total=0
    for n,spec in enumerate(settings_specs()):
        data=fixture(base,spec);live.write_text(json.dumps(data));bank=out/'fixture.native';bank.write_bytes(converter.encode_settings(live));expected=subprocess.check_output([str(reference),str(stock_path.parents[2]),str(live.parents[2])],input=blob);actual=subprocess.check_output([str(native),str(stock_native),str(bank)],input=blob);folder=out/f'result-{n}';folder.mkdir(exist_ok=True);(folder/'reference.bin').write_bytes(expected);(folder/'native.bin').write_bytes(actual);total+=len(expected)
        if expected!=actual:
            at=next((i for i,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)));(out/'first-divergence.json').write_text(json.dumps(dict(fixture=n,label=spec['label'],byte=at,reference_bytes=len(expected),native_bytes=len(actual)),indent=2)+'\n');raise AssertionError('PlayerState Load/reset differs')
        histories=decode(expected,cases);proof=coverage(histories,cases,spec['error']);results.append(dict(label=spec['label'],error=spec['error'],fixture_sha256=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest(),output_bytes=len(expected),output_sha256=hashlib.sha256(expected).hexdigest(),coverage=proof))
    audit(source,report)
    final=dict(passed=True,histories=len(cases),commands=report['commands'],settings_fixtures=results,exact_output_bytes=total,provenance_sha256=digest(out/'provenance.json'),native_binary_sha256=digest(native),reference_binary_sha256=digest(reference),scope=report['boundary'],native_only_invariant='ResetForTeleport leaves separately seeded landing_settings and landing_quality byte-identical; no original landing-stage equivalence claimed.')
    (out/'result.json').write_text(json.dumps(final,indent=2)+'\n');print(json.dumps(final,indent=2))

if __name__=='__main__':main()
