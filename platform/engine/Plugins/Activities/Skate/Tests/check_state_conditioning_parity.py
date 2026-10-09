#!/usr/bin/env python3
"""Complete unchanged filtered-state/landing-quality cores and actual stock loader.

Compile and execute only in the coordinator's shared render guard. Core inputs
are explicitly supplied completed records; live host publication is separate.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import random
import shutil
import struct
import subprocess
import check_animation_trees_parity as trees
import check_ground_control_settings_parity as stock
from check_gesture_parity import PLUGIN,converter
from reference_build import build_probe
from session_parity import digest

FILTERED='crates/skate-core/src/physics/filtered_state.rs'
LANDING='crates/skate-core/src/animation/landing_quality.rs'
LOADER='crates/skate-host/src/physics/landing_quality.rs'
LENGTHS={0:0,1:27,2:27,3:6,4:16,5:16,6:0}
STATES=(100,101,102,103,104,105,200,201,202,300,400,401,402,403,404,405,500,501,502,503,600,601,602,700,701,702)

def bits(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def floats(values):return [v['bits'] if isinstance(v,dict) else bits(v) for v in values]
def value(v):return struct.unpack('<f',struct.pack('<I',v))[0]

def grind(n):
    return [n%6,(n*13+7)&0xffffffff,*trees.name(('FS_50_50','BS_SLIDE','NOSE','TAIL')[n%4]),*trees.name('SCORE_'+str(n)),n%2,bits((n-7)*.137),0xabc00000+n,0x12345678,0xdead0000+n,0x87654321]

def seed(cat=0,count=0,n=0,prior=100):return [cat,7,prior,count,count,count,count,count,1]+grind(n)
def update(state,cat=None,n=0,contact=False,surface=1,wall=False,target=False,landed=False,deck=False,distance=.731):
    return [(state//100)*100 if cat is None else cat,state,int(contact),surface,int(wall),int(target),int(landed),int(deck)]+grind(n)+floats([distance])
def landing(previous=2,current=1,normal=(0,1,0,.137),velocity=(1,0,3,.731),forward=(0,0,1,-.317),flipped=False,spin=-3):
    return [previous,current]+floats(normal)+floats(velocity)+[int(flipped)]+floats(forward)+floats([spin])

def corpus():
    rng=random.Random(0x82de5ba0);programs=[]
    def program(label):
        commands=[];programs.append(dict(label=label,commands=commands));return commands
    def add(commands,op,words=(),tag=''):
        words=[w&0xffffffff for w in words];assert len(words)==LENGTHS[op],(op,len(words));commands.append(dict(op=op,words=words,tag=tag))
    for old in range(8):
        c=program(f'all-selected-states from filtered {old}')
        for state in STATES+(-1,0,999,2147483647):
            for mask in range(4):
                add(c,1,seed(old,6,len(c),prior=702 if mask==3 else 100),'seed retained')
                add(c,2,update(state,n=len(c),contact=mask%2!=0,wall=mask==1,target=mask==3,landed=mask%2!=0,deck=mask==2,surface=8 if mask==3 else 1),'state table')
    for stairs in (True,False):
        for contact in (True,False):
            c=program(f'actual counter history stairs={stairs} contact={contact}')
            add(c,2,update(100,surface=8 if stairs else 1),'ground start')
            for n in range(14):add(c,2,update(200,n=n,contact=contact),'air delay')
            for n in range(9):add(c,2,update(201,n=n,contact=contact,target=n<3),'known-air contact delay')
            add(c,2,update(400,n=77),'grind store');add(c,2,update(701,contact=False),'nonspecific retains grind')
            add(c,2,update(100),'clear published grind');add(c,2,update(701,contact=True),'retained cache nongrind');add(c,0,tag='reset all')
    for start in (0,2,3,4,5,6,8,9,10,0x7ffffffe,0x7fffffff,0x80000000,0xffffffff):
        c=program(f'wrapping counters {start}')
        for state in (200,201,701):
            add(c,1,seed(2,start,start&0xff),'counter seed')
            for n in range(3):add(c,2,update(state,n=n,contact=n%2!=0),'wrapping counter')
    curves=floats([0,.2,.6,1,0,.2,.6,1,0,.2,.6,1,0,.2,.6,1])
    c=program('landing retained fields and exact classification thresholds');add(c,5,curves)
    retained=floats([.137,-.317,.731,-.517])+[0xdeadbeef,1]
    for previous in range(8):
        for current in range(8):
            add(c,3,retained,'landing seed');add(c,4,landing(previous,current),'category gating')
    import math
    for orientation in (0,.049999997,.05,.050000004,.19999999,.2,.20000002,.5,-.049999997,-.05,-.050000004,-.19999999,-.2,-.20000002,-.5):
        for speed in (0,1.9999999,2,2.0000002,7):
            for spin in (-7,-.10000001,-.1,-.099999994,0,.099999994,.1,.10000001,7):
                for flipped in (False,True):
                    add(c,4,landing(velocity=(orientation*speed,0,math.sqrt(1-orientation*orientation)*speed,.731),spin=spin,flipped=flipped),'sector boundary')
    for forward in ((0,0,0,0),(0,1,0,.731),(0,0,1e-5,.137),(0,0,1.52587890625e-5,-.317),(0,0,-1,.731)):
        for speed in (0,1e-5,1,2,7):add(c,4,landing(forward=forward,velocity=(speed,0,speed,.137)),'degenerate/tiny/backward')
    for n in range(192):
        add(c,4,landing(normal=tuple(rng.uniform(-2,2) for _ in range(4)),velocity=tuple(rng.uniform(-8,8) for _ in range(4)),forward=tuple(rng.uniform(-2,2) for _ in range(4)),flipped=n%2!=0,spin=rng.uniform(-8,8)),'authored/generated geometry')
    add(c,6,tag='landing reset')
    c=program('landing IEEE boundaries and curve segment degeneracy');add(c,5,curves)
    specials=(0x00000000,0x80000000,0x00000001,0x80000001,0x007fffff,0x00800000,0x7f7fffff,0xff7fffff,0x7f800000,0xff800000,0x7fc12345,0xffc01234,0x7f812345)
    for word in specials:
        for lane in (2,6,11,12,14,15):
            raw=landing();raw[lane]=word;add(c,4,raw,'IEEE operand')
    for x in ((0,0,.5,1),(0,.5,.5,1),(1,.5,.25,0),(0,.25,.5,1)):
        add(c,5,floats(list(x)+[.137,-.317,.731,.517]+list(x)+[-.731,.517,-.137,.317]),'curve boundary graph')
        for spin in (-7,-1,0,1,7):add(c,4,landing(spin=spin),'curve boundary evaluate')
    c=program('stock curves own all arithmetic')
    for n in range(64):add(c,4,landing(velocity=(.137*n,0,(-1 if n%2 else 1)*2.731,.517),spin=(n-32)*.317,flipped=n%3==0),'stock landing')
    c=program('distinct authored grind names retained across nonspecific then reset')
    for n in range(16):
        raw=update(400+n%6,n=n)
        raw[10:15]=trees.name('FS_AUTHORED_GRIND_'+str(n))
        add(c,2,raw,'distinct actual grind name')
        add(c,2,update(701,n=n),'retain exact named grind')
        add(c,2,update(100,n=n),'reset published named grind')
    return programs

def encode(programs):
    words=[len(programs)]
    for p in programs:
        words.append(len(p['commands']))
        for c in p['commands']:words.extend([c['op'],*c['words']])
    return struct.pack('<'+'I'*len(words),*words)

class Reader:
    def __init__(self,data):self.data=data;self.at=0
    def word(self):v=struct.unpack_from('<I',self.data,self.at)[0];self.at+=4;return v
    def words(self,n):return [self.word() for _ in range(n)]
    def string(self):n=self.word();v=self.data[self.at:self.at+n].decode();self.at+=((n+3)//4)*4;return v

def decode(data,programs):
    r=Reader(data);result=dict(loaded=r.word(),error=r.string(),settings=r.words(16),programs=[]);assert r.word()==len(programs)
    for p,program in enumerate(programs):
        rows=[];result['programs'].append(rows)
        for n,c in enumerate(program['commands']):
            assert r.words(3)==[p,n,c['op']]
            state=r.words(27);filtered=r.words(22) if r.word() else None
            rows.append(dict(state=state,filtered=filtered,landing=r.words(6),settings=r.words(16)))
    assert r.at==len(data),(r.at,len(data));return result

def coverage(data,programs):
    assert data['loaded'] and not data['error'];counts=Counter();categories=Counter();kinds=Counter();proof=Counter();curves=set();signs=set();grind_names=set();nonzero=False
    for program,rows in zip(programs,data['programs']):
        previous=dict(state=[0,0,0,0,0,0,0,0,1]+[0xffffffff,0xffffffff]+[0]*10+[0,0]+[0xffffffff]*4,filtered=None,landing=[0]*6,settings=data['settings'])
        for c,row in zip(program['commands'],rows):
            op=c['op'];counts[op]+=1;curves.add(tuple(row['settings']))
            if op==2:
                raw=c['words'];s=row['state'];f=row['filtered'];assert f is not None and s[0]==f[0] and s[1]==f[1] and f[2]==(f[0]==3) and f[-1]==raw[-1]
                categories[f[0]]+=1;grind_names.add(tuple(s[11:16]))
                active=(raw[0]==200,raw[1]==701,raw[1]==701 and not raw[2],raw[1]==701 and bool(raw[2]),not(raw[0]==100 and raw[3]==8))
                for index,enabled in enumerate(active):
                    expected=((previous['state'][3+index]+1)&0xffffffff) if enabled else 0
                    assert s[3+index]==expected,(program['label'],c,s,index,expected)
                    if enabled and previous['state'][3+index]==0x7fffffff:proof['signed counter wrap']+=1
                if raw[1] in range(400,406):assert s[9:]==raw[8:26];proof['cached real grind']+=1
                else:assert s[9:]==previous['state'][9:];proof['cache preserved']+=1
                if not f[2]:assert f[3:]==[0xffffffff,0xffffffff]+[0]*10+[0,0]+[0xffffffff]*4+[raw[-1]];proof['nongrind output reset']+=1
                else:assert f[3:21]==s[9:];proof['published cached grind']+=1
            if op==4:
                prev,cur=c['words'][:2];landing_words=row['landing']
                if prev==1 or cur!=1:assert landing_words==previous['landing'];proof['nonlanding retained all fields']+=1
                else:
                    assert landing_words[5]==1 and landing_words[0]==landing_words[3];proof['landing full publication']+=1;kinds[landing_words[4]]+=1
                    signs.add(landing_words[3]>>31)
                    nonzero|=value(landing_words[1])>0 and abs(value(landing_words[3]))>0
            if op==0:assert row['state']==[0,0,0,0,0,0,0,0,1]+[0xffffffff,0xffffffff]+[0]*10+[0,0]+[0xffffffff]*4 and row['filtered'] is None;proof['complete filter reset']+=1
            if op==6:assert row['landing']==[0]*6;proof['complete landing reset']+=1
            previous=row
    assert set(counts)==set(range(7)) and set(categories)==set(range(8)) and set(kinds)=={0,1,2,3}
    assert proof['signed counter wrap']>=3 and proof['nonlanding retained all fields']==57 and proof['cached real grind']>100 and proof['published cached grind']>100
    assert len(grind_names)>10 and len(curves)>=5 and signs=={0,1} and nonzero
    return dict(operations=dict(counts),filtered_categories=dict(categories),landing_kinds=dict(kinds),proofs=dict(proof),cached_grind_names=len(grind_names),curve_variants=len(curves))

def prepare_reference(output):
    source=(PLUGIN/'Tests/Reference/state_conditioning_probe.rs').read_text();report={}
    for marker,path in [('FILTERED',FILTERED),('LANDING',LANDING),('LOADER',LOADER)]:
        body=trees.source_at_reference(path);report[path]=hashlib.sha256(body.encode()).hexdigest()
        if marker=='LANDING':assert 'use skate_core::animation::landing_quality as landing;'in source
        else:source=source.replace('// ORIGINAL_'+marker,body)
    path=output/'state-conditioning-reference.rs';path.write_text(source);report['probe_sha256']=digest(path)
    (output/'source-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return path

def build_native(output):
    live=PLUGIN/'Source/AtelierSkate/Private/Native';snapshot=output/'native-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir();units=('NativeMath','NameId','Settings','StockSettingsReader','AnimationName','FilteredState','LandingQuality')
    for p in list(live.glob('*.h'))+[live/(u+'.cpp') for u in units]:shutil.copy2(p,snapshot/p.name)
    probe=snapshot/'state_conditioning_probe.cpp';shutil.copy2(PLUGIN/'Tests/Native/state_conditioning_probe.cpp',probe)
    transport=(snapshot/'GrindFilteredOutput.h').read_text();start=transport.index('struct GrindFilteredOutput\n{');end=transport.index('\n};',start)+3;declaration=transport[start:end]
    assert hashlib.sha256(declaration.encode()).hexdigest()=='0a4bdb6d4792e87633638ce03405c10e018edd3fe0b30b2b8307041fe3c0c78c'
    reconstructed=(snapshot/'FilteredState.h').read_text().replace('#include "GrindFilteredOutput.h"','#include "GrindRuntime.h"')
    assert hashlib.sha256(reconstructed.encode()).hexdigest()=='f743fa1cc68c38edc801aa27cda4676fdaa4290a363a12b4fcf183df53864cac'
    report=dict(immutable_sources={p.name:digest(p) for p in sorted(snapshot.iterdir())},grind_transport_extraction=dict(header_sha256=digest(snapshot/'GrindFilteredOutput.h'),declaration_sha256=hashlib.sha256(declaration.encode()).hexdigest(),previous_filtered_header_sha256=hashlib.sha256(reconstructed.encode()).hexdigest(),scope='Existing exact transport reused after declaration-only extraction; no duplicate storage/layout/numerical change.'))
    (output/'native-provenance.json').write_text(json.dumps(report,indent=2)+'\n')
    binary=output/'state-conditioning-native';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(u+'.cpp')) for u in units],str(probe),'-o',str(binary)],check=True);return binary

def settings_fixtures(original):
    fixtures=[dict(label='stock',data=original,error='')];queries=[('physics_animation','default',name,'words') for name in ('LandingSketchyTwistSpin','LandingSketchySideSpeed')]
    for n,query in enumerate(queries):
        data=copy.deepcopy(original)
        for later in queries[n:]:stock.mutate(data,later,dict(type='EA::Reflection::Int32',data='00000000'))
        fixtures.append(dict(label='first-failed read '+str(n),data=data,error='Expected 8 big-endian words, found 8 bytes of hex'))
        data=copy.deepcopy(original);chain,name=stock.resolve(data,query);del chain[-1]['fields'][name];chain[-1]['parent']='';fixtures.append(dict(label='missing '+query[2],data=data,error='Missing stock field '+'/'.join(query[:3])))
        for length in (0,7,9):
            data=copy.deepcopy(original);stock.mutate(data,query,dict(type='EA::Reflection::UInt32',data='00000000'*length));fixtures.append(dict(label='word count '+str(length),data=data,error=f'Expected 8 big-endian words, found {length*8} bytes of hex'))
        for text,error in [('0'*64,''),('G'*64,'Invalid collection payload: invalid digit found in string'),('0'*63,'Expected 8 big-endian words, found 63 bytes of hex'),('\u00a0'+'0'*64+'\u3000',''),('\u2007'+'0'*64+'\n','')]:
            data=copy.deepcopy(original);stock.mutate(data,query,dict(type='EA::Reflection::Text',data=text));fixtures.append(dict(label='text '+query[2]+' '+repr(text[:3]),data=data,error=error))
        for words in ([0x7fc12345]*8,[0,0,0x3f800000,0x3f800000,0x80000000,0x7f800000,0xff800000,0x7fc12345]):
            data=copy.deepcopy(original);stock.mutate(data,query,dict(type='EA::Reflection::Bool',data=''.join(f'{w:08x}' for w in words)));fixtures.append(dict(label='type ignored, raw IEEE curve',data=data,error=''))
    data=copy.deepcopy(original);data['collections']=[r for r in data['collections'] if not(converter.name_id(r['class'])==converter.name_id('physics_animation') and converter.name_id(r['key'])==converter.name_id('default'))];fixtures.append(dict(label='missing collection',data=data,error='Missing stock collection physics_animation/default'))
    return fixtures

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('assets','output','target-dir'):p.add_argument('--'+key,type=Path,required=True)
    args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json'):(output/name).unlink(missing_ok=True)
    programs=corpus();prefix=encode(programs[:-1]);prefix_sha=hashlib.sha256(prefix).hexdigest()
    assert len(programs[:-1])==28 and sum(len(p['commands']) for p in programs[:-1])==4056
    assert prefix_sha=='93bc74fca2fd889bf48fd7d72f47272b1a00b01b7a52ed0d07419689788345c3'
    prefix_audit=dict(histories=28,commands=4056,input_bytes=len(prefix),input_sha256=prefix_sha,scope='All previously frozen commands remain byte-identical; one reachable named-grind history is appended.')
    (output/'corpus-prefix-preservation.json').write_text(json.dumps(prefix_audit,indent=2)+'\n')
    blob=encode(programs);(output/'input.bin').write_bytes(blob);(output/'cases.json').write_text(json.dumps(programs,indent=2)+'\n')
    reference=build_probe(output,'state-conditioning-reference',prepare_reference(output),args.target_dir);native=build_native(output)
    original=json.loads((args.assets/'private/stock/skater-collections.json').read_text());settings=output/'settings.native';results=[];proof=None;total=0
    for n,fixture in enumerate(settings_fixtures(original)):
        folder=output/f'settings-{n}';path=folder/'private/stock/skater-collections.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(fixture['data']));settings.write_bytes(converter.encode_settings(path));commands=blob if n==0 else encode([])
        expected=subprocess.check_output([str(reference),str(folder)],input=commands);actual=subprocess.check_output([str(native),str(settings)],input=commands);(folder/'reference.bin').write_bytes(expected);(folder/'native.bin').write_bytes(actual);total+=len(expected)
        if expected!=actual:
            byte=next((i for i,(a,b) in enumerate(zip(actual,expected)) if a!=b),min(len(actual),len(expected)));(output/'first-divergence.json').write_text(json.dumps(dict(fixture=n,label=fixture['label'],byte=byte,expected_bytes=len(expected),actual_bytes=len(actual)),indent=2)+'\n');raise AssertionError(f'State conditioning differs at fixture {n} byte {byte}')
        decoded=decode(expected,programs if n==0 else []);assert decoded['error']==fixture['error'] and decoded['loaded']==(not fixture['error']),(fixture['label'],decoded)
        if fixture['error']:assert decoded['settings']==floats([-.731,-.317,.137,.731,.517,.113,-.137,.317]*2),'failed loader mutated output'
        if n==0:proof=coverage(decoded,programs);(output/'reference-trace.json').write_text(json.dumps(decoded,indent=2)+'\n')
        results.append(dict(label=fixture['label'],error=decoded['error'],output_bytes=len(expected),output_sha256=hashlib.sha256(expected).hexdigest()))
    report=dict(passed=True,histories=len(programs),commands=sum(len(p['commands']) for p in programs),exact_output_bytes=total,coverage=proof,settings_fixtures=results,corpus_prefix_preservation=prefix_audit,comparison='Entire byte-identical core FilteredState and LandingQuality modules plus complete unchanged actual host landing-quality loader; every retained field, cached grind and curve word observed.',limitations='Explicit core completed-input boundary. Actual physical state Fill/chromosome/animation publication and overall frame scheduling are separate comparisons. Current source last-grind distance is preserved as supplied by the core, with actual host constant-zero producer tested in the subsequent adapter proof.',native_provenance_sha256=digest(output/'native-provenance.json'),source_provenance_sha256=digest(output/'source-provenance.json'))
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':main()
