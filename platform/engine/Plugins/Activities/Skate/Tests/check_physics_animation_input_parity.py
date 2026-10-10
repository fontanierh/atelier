#!/usr/bin/env python3
"""Full actual host animation-input loading/dispatch/publication comparison.

Only the coordinator may run these compile/oracle jobs under the shared guard.
All expected numerical/state results execute unchanged pinned Rust modules.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import check_animation_trees_parity as trees
import check_ground_control_settings_parity as settings_probe
from check_animation_playback_parity import Stream,bits,attribute
from check_gesture_parity import PLUGIN,converter
from reference_build import build_probe

CORE='crates/skate-core/src/animation/skeleton_input/'
SOURCES={'ScalarAttributeInputs':'scalar_attributes.rs','AnimationControlOutput':'scalar_attributes.rs','ExtendedAttributes':'extended_attributes.rs','JumpAttributeState':'attribute_finalization.rs','FinalizationInput':'attribute_finalization.rs','ContactEventState':'contact_events.rs'}
MODES=('easy','normal','hardcore','motorized','test')
HOST='crates/skate-host/src/physics/animation_input.rs'
SNAPSHOT_ORDER=('ScalarAttributeInputs','ExtendedAttributes','ContactEventState','AnimationControlOutput','JumpAttributeState','FinalizationInput')

def schema():
    result={}
    for name,path in SOURCES.items():
        source=trees.source_at_reference(CORE+path);start=re.search(r'\bstruct '+name+r'\s*\{',source).end();body=re.sub(r'//[^\n]*','',source[start:source.index('\n}',start)])
        result[name]=[(field,re.sub(r'\s+','',kind)) for field,kind in re.findall(r'^\s*pub\s+(\w+)\s*:\s*([^,\n]+),',body,re.M)]
        assert result[name],name
    return result

def array_type(kind):return re.fullmatch(r'\[(f32|u32);(\d+)\]',kind)

def helpers(defs):
    cpp=[];rust=[]
    for name,fields in defs.items():
        cobs=f'void Observe(Output& o,const {name}& s) {{';robs=f'fn observe_{name}(o:&mut Output,s:&{name}) {{';cread=f'{name} Read{name}(Input& i) {{{name} s;';rread=f'fn read_{name}(i:&mut Input)->{name} {{{name}{{'
        for field,kind in fields:
            if kind=='f32':c=f'o.Float(s.{field});';r=f'o.float(s.{field});';cr='i.Float()';rr='i.float()'
            elif kind in ('u32','i32','bool'):c=f'o.Word(std::uint32_t(s.{field}));';r=f'o.word(s.{field} as u32);';cr='i.Word()' if kind=='u32' else 'i.Word()!=0' if kind=='bool' else 'std::int32_t(i.Word())';rr='i.word()' if kind=='u32' else 'i.word()!=0' if kind=='bool' else 'i.word() as i32'
            else:
                a=array_type(kind);n=a[2] if a else '5';floating=a and a[1]=='f32';assert a or kind=='AttributeName',kind
                c=f'for (auto v:s.{field}) o.'+('Float' if floating else 'Word')+'(v);';r=f'o.'+('floats' if floating else 'words')+f'(s.{field}'+('' if a else '.0')+');';cr=f'i.'+('Floats' if floating else 'Words')+f'<{n}>()';rr=f'i.'+('floats' if floating else 'words')+f'::<{n}>()';rr=rr if a else 'AttributeName('+rr+')'
            cobs+=c;robs+=r;cread+=f's.{field}={cr};';rread+=f'{field}:{rr},'
        cpp.extend([cobs+'}',cread+'return s;}']);rust.extend([robs+'}',rread+'}}'])
    return '\n'.join(cpp),'\n'.join(rust)

def attr(name,value=.731,kind=0,status=5,payload=None):
    a=attribute(kind=kind,status=status);a['name']=trees.name(name);a['payload']=[bits(value),None,None,None,None,None] if payload is None else payload;return a

def command(attrs=(),translation=(3,4,0,99),dt=1/60,flags=0,impulse=False,actions=None,tag=''):
    matrix=[[1,0,0,0],[0,1,0,0],[0,0,1,0],list(translation or (0,0,0,0))]
    return dict(op=4,attrs=list(attrs),hierarchy=[] if translation is None else [matrix],dt=dt,flags=flags,impulse=impulse,actions=actions or [-1.5,.25,0,0,.75]+[0]*13,tag=tag)

def seed(defs):
    out={}
    for name in ('ScalarAttributeInputs','ExtendedAttributes','ContactEventState','AnimationControlOutput'):
        out[name]={}
        for field,kind in defs[name]:
            a=array_type(kind)
            out[name][field]=(.731 if kind=='f32' else True if kind=='bool' else 0xf5a5a5ad if kind=='u32' else -7 if kind=='i32' else [.137,.317,.731,.517][:int(a[2])] if a and a[1]=='f32' else trees.name('INITIAL'))
    out['AnimationControlOutput']['flags']=0xffffffff
    return dict(op=0,values=out,tag='seed')

def corpus(defs):
    catalog=re.findall(r'entry\("([^"]+)"',trees.source_at_reference(CORE+'catalog.rs').split('pub const EVENT_COMPARISONS')[0]);assert len(catalog)==151;programs=[]
    def program(commands,mode='normal',variant=0,label=''):
        programs.append(dict(mode=mode,variant=variant,commands=commands,label=label));return commands
    for mode in MODES:
        commands=program([seed(defs)],mode,label='all scalar catalog retained history')
        for n,name in enumerate(catalog):commands.append(command([attr(name)],flags=(0x08800000,0x12000000,0xffffffff)[n%3],impulse=n%3==1,tag='catalog:'+name))
        commands.extend([dict(op=1,tag='reset'),dict(op=2,tag='finish'),command(tag='empty suffix')])
    for name in catalog:
        program([seed(defs),command([attr('Balance',.5),attr(name,payload=[None]*6),attr('Brake',.125)],tag='missing:'+name)],label='missing payload partial writes')
    for value in (-0.,-1.,0.,1.,1.0000001192092896,float('inf'),float('-inf'),float('nan')):
        program([seed(defs),command([attr('Balance',value),attr('OB_Turn',value),attr('BipedStartAngle',value),attr('TrickHeight',value),attr('JumpHeightOverride',value),attr('jump')],tag='scalar boundary'),dict(op=1,tag='reset')],label='scalar IEEE boundary')
    for kind in (1,2,3,4,255):
        for status in (0,1,4,8,12,15):program([command([attr('Balance',kind=kind,status=status,payload=[None]*6)],tag='kind-status')],label='kind/status routing')
    for variant in (0,1,3):
        for event in ('push_contact','brake_contact','right_hand_grab','left_hand_grab','unknown_contact'):
            for bone in ('RightToeBase','LeftToeBase','righthand','unknown_bone'):
                for strength in (-1.,0.,1.,1.0000001192092896):
                    program([seed(defs),command([attr(event,kind=3,payload=trees.name(bone)+[bits(strength)])],tag='event'),dict(op=1,tag='reset')],variant=variant,label='actual bone event')
    for n in range(6):
        payload=trees.name('RightToeBase')+[bits(1)];payload[n]=None
        program([seed(defs),command([attr('Balance',.5),attr('push_contact',kind=3,payload=payload),attr('Brake',.125)],tag='incomplete event')],label='incomplete event partial writes')
    for translation in (None,(0,0,0,1),(3,4,0,0),(3,4,0,99),(1e-19,0,0,0),(-3,-4,1,.731)):
        for dt in (0.,-0.,1/60,-.125):program([seed(defs),command([attr('push_contact',kind=3,payload=trees.name('RightToeBase')+[bits(1)])],translation,dt,tag='trajectory')],label='trajectory length and failed hierarchy')
    for mode in MODES:
        commands=program([seed(defs)],mode,label='jump cache lifecycle and mode publication')
        for selected in (0,1,2,3,4,99,0xffffffff):
            commands.extend([dict(op=3,mode=selected,tag='select'),dict(op=1,tag='reset'),command([attr('PrepareJump'),attr('JumpHeightOverride',.731),attr('TrickHeight',.25),attr('MinJump',.125),attr('jump'),attr('Revert'),attr('RevertDir',-1)],tag='prepare jump'),dict(op=2,tag='finish'),command([attr('TrickHeight',.125),attr('jump')],tag='reuse jump cache'),command(tag='clear jump cache')])
        commands.extend([command([attr('HippyJumping'),attr('TrickHeight',.317)],tag='hippy override'),command([attr('OB_DroppingBoard'),attr('OB_RetrievingBoard'),attr('LeavingCoffin')],tag='final flags')])
    for variant in (2,):program([],variant=variant,label='missing actual right toe')
    program([],mode='unknown',label='missing actual mode')
    program([command([attr('unknown_scalar'),attr('Balance',kind=2)],tag='unknown name and nonzero kind')],label='unknown source no-op')
    return programs,catalog

def encode_value(w,kind,value):
    a=array_type(kind)
    if kind=='f32':w.float(value)
    elif kind in ('u32','i32','bool'):w.word(int(value))
    else:
        for v in value:(w.float if a and a[1]=='f32' else w.word)(v)

def encode(programs,defs):
    w=Stream();w.word(len(programs))
    for p in programs:
        w.word(p['variant']);w.string(p['mode']);w.word(len(p['commands']))
        for c in p['commands']:
            w.word(c['op'])
            if c['op']==0:
                for name in ('ScalarAttributeInputs','ExtendedAttributes','ContactEventState','AnimationControlOutput'):
                    for field,kind in defs[name]:encode_value(w,kind,c['values'][name][field])
            elif c['op']==3:w.word(c['mode'])
            elif c['op']==4:
                w.attrs(c['attrs']);w.word(len(c['hierarchy']))
                for matrix in c['hierarchy']:
                    for column in matrix:
                        for v in column:w.float(v)
                w.float(c['dt']);w.word(c['flags']);w.word(c['impulse'])
                for v in c['actions']:w.float(v)
    return bytes(w.data)

class Reader:
    def __init__(self,data):self.data=data;self.at=0
    def word(self):v=struct.unpack_from('<I',self.data,self.at)[0];self.at+=4;return v
    def string(self):n=self.word();s=self.data[self.at:self.at+n].decode();self.at+=n;return s
    def words(self,n):return [self.word() for _ in range(n)]
    def value(self,kind):a=array_type(kind);return self.words(int(a[2]) if a else 5) if a or kind=='AttributeName' else self.word()
    def record(self,fields):return {field:self.value(kind) for field,kind in fields}
    def snapshot(self,defs):
        size=self.word()*4;end=self.at+size;out={name:self.record(defs[name]) for name in SNAPSHOT_ORDER};out['modes']=self.words(5);out['toe']=self.word();out['bones']=[self.words(5) for _ in range(self.word())];out['actions']=self.words(self.word());assert self.at==end;return out

def decode(data,programs,defs):
    r=Reader(data);frames=[]
    for p,case in enumerate(programs):
        assert r.word()==p;loaded=r.word();error=r.string();rows=[];initial=r.snapshot(defs) if loaded else None
        for n,c in enumerate(case['commands']):
            assert [r.word(),r.word(),r.word()]==[p,n,c['op']];rows.append(dict(ok=r.word(),error=r.string(),snapshot=r.snapshot(defs)))
        frames.append(dict(loaded=loaded,error=error,initial=initial,rows=rows))
    assert r.at==len(data);return frames

def coverage(frames,programs,catalog):
    names=Counter();errors=Counter();calls=Counter();push=set();bone=set();cache=set();partial=0;types=Counter();reset=finish=0
    for frame,program in zip(frames,programs):
        if not frame['loaded']:errors[frame['error']]+=1;continue
        previous=frame['initial']
        for row,c in zip(frame['rows'],program['commands']):
            s=row['snapshot'];tag=c['tag'];types[c['op']]+=1;errors.update([row['error']] if row['error'] else []);calls.update(s['actions']);push.add(s['ContactEventState']['push_speed']);bone.add(s['ContactEventState']['bone']);cache.add((s['JumpAttributeState']['height_override_active'],s['JumpAttributeState']['height_override']))
            if tag.startswith('catalog:'):assert row['ok'],(tag,row['error']);names[tag[8:]]+=1
            if not row['ok'] and s!=previous and tag in ('incomplete event','trajectory') or (not row['ok'] and tag.startswith('missing:') and s!=previous):partial+=1
            if c['op']==1:
                assert s['ScalarAttributeInputs']['flags2468']==(previous['ScalarAttributeInputs']['flags2468']&8)|0x2000
                assert s['ScalarAttributeInputs']['flags2488']==previous['ScalarAttributeInputs']['flags2488']&0x1fffff
                assert s['ExtendedAttributes']['footstep_strength']==previous['ExtendedAttributes']['footstep_strength']
                assert s['JumpAttributeState']==previous['JumpAttributeState'];reset+=1
            if c['op']==2:
                assert s['AnimationControlOutput']['flags']==previous['AnimationControlOutput']['flags']&0x003fffff and s['AnimationControlOutput']['grind_name']==[0]*5
                assert s['ExtendedAttributes']['footstep_strength']==0 and s['JumpAttributeState']==previous['JumpAttributeState'];finish+=1
            previous=s
    assert set(names)==set(catalog) and set(types)==set(range(5)) and all(calls[k]>0 for k in (64,65))
    assert any(v not in (0,bits(0.)) and (v&0x7f800000)!=0x7f800000 for v in push) and 0 in push and 0xffffffff in bone
    assert any(a for a,h in cache) and any(not a for a,h in cache) and partial>0 and reset>0 and finish>0
    assert any('incomplete payload' in e for e in errors) and any('trajectory bone' in e for e in errors) and any('scalar payload absent' in e for e in errors) and any('UninitializedScalar' in e for e in errors)
    assert 'Stock skeleton is missing RightToeBase' in errors and any('Invalid animation physics mode' in e for e in errors)
    return dict(catalog_names=len(names),commands=dict(types),action_calls=dict(calls),push_speed_words=sorted(push),bone_results=sorted(bone),cache_values=sorted(cache),partial_write_failures=partial,resets=reset,output_finishes=finish,errors=dict(errors))

def prepare_sources(output,defs):
    cpp,rust=helpers(defs);c=output/'physics-animation-input-simulation.cpp';r=output/'physics-animation-input-reference.rs';c.write_text((PLUGIN/'Tests/Simulation/physics_animation_input_probe.cpp').read_text().replace('// GENERATED_PROTOCOL',cpp));host=trees.source_at_reference(HOST);r.write_text((PLUGIN/'Tests/Reference/physics_animation_input_probe.rs').read_text().replace('// GENERATED_PROTOCOL',rust).replace('// ORIGINAL_HOST',host));(output/'source-provenance.json').write_text(json.dumps(dict(host=HOST,host_sha256=hashlib.sha256(host.encode()).hexdigest(),modules=sorted(set(CORE+p for p in SOURCES.values())|{CORE+'process_attributes.rs',CORE+'catalog.rs'})),indent=2)+'\n');return c,r

def build_simulation(output,probe):
    live=PLUGIN/'Source/AtelierSkate/Private/Simulation';n=output/'simulation-source';binary=output/'physics-animation-input-simulation';sources=['NameId','Settings','StockSettingsReader','SimulationMath','AnimationName','AnimationSamples','SkeletonAttributeDispatch','PhysicsAnimationInput']
    if n.exists():shutil.rmtree(n)
    n.mkdir()
    for path in list(live.glob('*.h'))+[live/(s+'.cpp') for s in sources]:shutil.copy2(path,n/path.name)
    copied_probe=n/probe.name;shutil.copy2(probe,copied_probe)
    (output/'simulation-provenance.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(n.iterdir())},indent=2)+'\n')
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(n),*[str(n/(s+'.cpp')) for s in sources],str(copied_probe),'-o',str(binary)],check=True);return binary

def settings_failures(original):
    queries=[('physics_mode',m,'JumpHeightOverrideEnabled','bool') for m in MODES]+[('anim_motion','jumping','clamp_jump','bool'),('anim_motion','jumping','clamp_low_inclusive','float'),('anim_motion','jumping','clamp_high_inclusive','float'),('physics_jump','default','AdjustOnPrepare','bool')];out=[]
    for n,query in enumerate(queries):
        data=copy.deepcopy(original)
        for q in queries[n:]:settings_probe.mutate(data,q,settings_probe.invalid(q))
        out.append((data,settings_probe.expected_invalid(query)))
    for query in queries:
        if query[3]=='float':
            for payload,error in [('7fc00001','Non-finite stock float '),('7f800000','Non-finite stock float ')]:
                data=copy.deepcopy(original);settings_probe.mutate(data,query,dict(type='EA::Reflection::Float',data=payload));out.append((data,error+'/'.join(query[:3])))
    return out

def alternate_settings(original):
    out=[]
    for label,queries in [('live suffix action routing',[('physics_jump','default','AdjustOnPrepare')]),('unclamped jump extremes',[('anim_motion','jumping','clamp_jump')]),('height overrides disabled',[('physics_mode',m,'JumpHeightOverrideEnabled') for m in MODES])]:
        data=copy.deepcopy(original)
        for query in queries:settings_probe.mutate(data,(*query,'bool'),dict(type='EA::Reflection::Bool',data='00'))
        out.append((label,data))
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path,required=True);p.add_argument('--rig',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--target-dir',type=Path,required=True);a=p.parse_args();output=a.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json'):(output/name).unlink(missing_ok=True)
    defs=schema();programs,catalog=corpus(defs);commands=encode(programs,defs);(output/'input.bin').write_bytes(commands);(output/'cases.json').write_text(json.dumps(programs,indent=2)+'\n');cpp,rust=prepare_sources(output,defs);reference=build_probe(output,'physics-animation-input-reference',rust,a.target_dir);simulation=build_simulation(output,cpp);settings=output/'settings.simulation';settings.write_bytes(converter.encode_settings(a.assets/'private/stock/skater-collections.json'))
    expected=subprocess.check_output([str(reference),str(a.assets.resolve()),str(a.assets.resolve())],input=commands);actual=subprocess.check_output([str(simulation),str(settings),str(a.rig.resolve())],input=commands);(output/'reference.bin').write_bytes(expected);(output/'simulation.bin').write_bytes(actual);frames=decode(expected,programs,defs);(output/'reference-trace.json').write_text(json.dumps(frames,indent=2)+'\n')
    if expected!=actual:
        (output/'first-divergence.json').write_text(json.dumps(dict(byte=next(i for i,(x,y) in enumerate(zip(expected,actual)) if x!=y) if expected[:min(len(expected),len(actual))]!=actual[:min(len(expected),len(actual))] else min(len(expected),len(actual))),indent=2)+'\n');raise AssertionError('Actual AnimationInput differs')
    proof=coverage(frames,programs,catalog);original=json.loads((a.assets/'private/stock/skater-collections.json').read_text());negative=[]
    for n,(data,error) in enumerate(settings_failures(original)):
        root=output/f'failure-{n}';path=root/'private/stock/skater-collections.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data));settings.write_bytes(converter.encode_settings(path));cases=[dict(mode='normal',variant=0,commands=[],label='first failed stock read')];blob=encode(cases,defs);x=subprocess.check_output([str(reference),str(a.assets.resolve()),str(root)],input=blob);y=subprocess.check_output([str(simulation),str(settings),str(a.rig.resolve())],input=blob);assert x==y,('settings failure',n);frame=decode(x,cases,defs)[0];assert not frame['loaded'] and frame['error']==error,(n,frame,error);negative.append(dict(fixture=n,error=error))
    alternatives=[];selected=[p for p in programs if p['label'] in ('jump cache lifecycle and mode publication','scalar IEEE boundary')]
    for n,(label,data) in enumerate(alternate_settings(original)):
        root=output/f'alternate-{n}';path=root/'private/stock/skater-collections.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data));settings.write_bytes(converter.encode_settings(path));blob=encode(selected,defs);x=subprocess.check_output([str(reference),str(a.assets.resolve()),str(root)],input=blob);y=subprocess.check_output([str(simulation),str(settings),str(a.rig.resolve())],input=blob);(root/'reference.bin').write_bytes(x);(root/'simulation.bin').write_bytes(y);assert x==y,('alternate actual settings',label);rows=decode(x,selected,defs);actions=Counter(a for f in rows for r in f['rows'] for a in r['snapshot']['actions'])
        if n==0:assert all(actions[a]>0 for a in (64,65,68)),actions
        alternatives.append(dict(label=label,commands=sum(len(p['commands']) for p in selected),output_bytes=len(x),output_sha256=hashlib.sha256(x).hexdigest(),action_calls=dict(actions)))
    (output/'settings-failures.json').write_text(json.dumps(negative,indent=2)+'\n');result=dict(passed=True,programs=len(programs),commands=sum(len(p['commands']) for p in programs),output_bytes=len(expected),output_sha256=hashlib.sha256(expected).hexdigest(),coverage=proof,settings_failures=len(negative),alternate_settings=alternatives,comparison='Entire actual original host AnimationInput and all ordered scalar/event/finalization modules with complete retained state. Actual stock rig names; supplied evaluated hierarchy and input-map values are explicit upstream boundaries.',limitations='Overall Skeleton::ProcessData/adjusted pose/FootIK and complete player-input schedule are separate owners, not proved by this attribute producer comparison.');(output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__':main()
