#!/usr/bin/env python3
"""Original contact retention state, full scratch records, publication chunks and material bits."""
import argparse
from collections import Counter
import hashlib
import io
import json
import math
from pathlib import Path
import random
import shutil
import struct
import subprocess
import tarfile

PLUGIN=Path(__file__).resolve().parents[1]
REFERENCE_REVISION='46513a6'
OPERATIONS=('coplanar','selection','buffer','material')
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def word(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def value(v):return struct.unpack('<f',struct.pack('<I',v))[0]
def f(v):return [word(x) for x in v]
def corpus():
    rng=random.Random(0x82779eb0);records=[];cases=[]
    def add(op,payload,label,**extra):
        cases.append(dict(index=len(cases),operation=OPERATIONS[op],label=label,**extra));records.append(struct.pack('<'+'I'*(len(payload)+1),op,*payload))
    def row(point=(0.,0.,0.),depth=.1,normal=(0.,1.,0.),body=0,other=0xffffffff,tag=0):
        r=[rng.getrandbits(32) for _ in range(64)];r[:3]=f(point);r[3]=body;r[4:7]=f([point[0],point[1]-depth,point[2]]);r[7]=other;r[8:11]=f(normal);r[23]=tag
        # Force a signalling payload in copied float workspace, and preserve the same bits as integer tag.
        r[24]=0x7fa12345;r[23]=0x7fa12345 if tag==0xffffffff else tag;return r
    a=row()
    for gap_bits in (0,0x80000000,0x3c23d709,0x3c23d70a,0x3c23d70b,0xbc23d70a):
        for normal_bits in (0x3f7fbe76,0x3f7fbe77,0x3f7fbe78,0x3f800000,0xbf800000):
            for side in (0,4):
                b=row();b[side+1]=gap_bits;b[9]=normal_bits;add(0,a+b,'coplanar smaller gap and normal threshold')
    for _ in range(2048):
        a=row([rng.uniform(-10.,10.) for _ in range(3)]);b=row([rng.uniform(-10.,10.) for _ in range(3)],normal=[rng.uniform(-1.,1.) for _ in range(3)]);add(0,a+b,'random paired-plane predicate')
    for count in (1,2,3,4,5,8,16,50):
        for mode in ('coincident','line','polygon','duplicate polygon'):
            a=[];b=[]
            for i in range(count):
                if mode=='coincident':p=[0.,0.,0.]
                elif mode=='line':p=[float(i),0.,0.]
                else:
                    angle=2*math.pi*(i//2 if mode=='duplicate polygon' else i)/count;p=[math.cos(angle),0.,math.sin(angle)]
                a.extend(p);b.extend([p[0],-.1 if i else -.2,p[2]])
            selected=[rng.getrandbits(32) for _ in range(4)];add(1,[count]+f(a+b+[0.,1.,0.])+selected,'selection degenerate/line/face/ties',initial_selected=selected)
    for _ in range(2048):
        count=rng.randrange(1,51);a=[rng.uniform(-10.,10.) for _ in range(count*3)];b=[v+rng.uniform(-.1,.1) for v in a];selected=[rng.getrandbits(32) for _ in range(4)]
        add(1,[count]+f(a+b+[0.,1.,0.])+selected,'random geometric contact point selection',initial_selected=selected)
    def buffer(initial_count,capacity,commands,label,flushed=0,dropped=0,threshold=.01,allow=1,deferred=0,full=0,groups=1):
        rows=[]
        for i in range(50):
            angle=2*math.pi*i/max(1,initial_count);rows+=row((math.cos(angle),0.,math.sin(angle)),body=i%groups,tag=0xffffffff if i%3==0 else i)
        payload=[initial_count,flushed,capacity,dropped,word(threshold),allow,deferred,full]+rows+[len(commands)]
        for command in commands:
            payload+=[command[0]]
            if command[0]==0:payload+=command[1]+[int(command[2])]
        add(2,payload,label,commands=len(commands),initial_count=initial_count,initial_records=rows,deferred=deferred)
    for count in (0,1,4,5,16,49,50):
        for capacity in (0,1,4,5,50,100,0xffffffff):
            for deferred in (0,1):
                for allow in (0,1):
                    commands=[(0,row((0.,0.,0.)),True),(1,),(0,row((1.,0.,0.)),True),(2,),(0,row((2.,0.,0.)),True),(2,)]
                    buffer(count,capacity,commands,'allocation/capacity/reduce/physical-full/flush',deferred=deferred,allow=allow)
    for count in (0,4,5,50):
        for flushed in (0xfffffffe,0xffffffff):
            for capacity in (0,1,50,0xffffffff):
                buffer(count,capacity,[(0,row(),True),(0,row(),True),(2,)],'wrapping count+flushed/dropped arithmetic',flushed=flushed,dropped=0xffffffff)
    for threshold_bits in (0,0x80000000,0x3c23d70a,0x3c23d709,0x3c23d70b,0xbf800000,0x7f800000,0x7fc12345):
        for deferred in (0,1):
            commands=[]
            for i in range(64):commands.append((0,row((0.,0.,0.),body=i%2),True))
            commands.append((2,));buffer(0,1000,commands,'duplicate strict threshold/deferred bypass',threshold=value(threshold_bits),deferred=deferred)
    for _ in range(512):
        commands=[]
        for _ in range(rng.randrange(1,101)):
            op=rng.choices((0,1,2),(9,1,1))[0]
            if op==0:
                p=(rng.uniform(-2.,2.),0.,rng.uniform(-2.,2.));commands.append((0,row(p,body=rng.randrange(4),tag=rng.getrandbits(32)),bool(rng.randrange(2))))
            else:commands.append((op,))
        buffer(rng.randrange(51),rng.choice((0,4,16,50,100,1000)),commands,'random retained-state command stream',deferred=rng.randrange(2),allow=rng.randrange(2),groups=rng.randrange(1,5))
    boundaries=(0,0x80000000,0x3f800000,0xbf800000,0x7f800000,0xff800000,0x7fc12345,0xffc23456,0x7fa12345,0xffa23456)
    for a in boundaries:
        for b in boundaries:
            for lane in range(3):
                left=f([.5,.3,.7]);right=f([.5,.3,.7]);left[lane]=a;right[lane]=b;add(3,left+right,'ordered material equality/unordered/signalling payload')
    for _ in range(1024):add(3,f([rng.uniform(-1.,2.) for _ in range(6)]),'random material combine')
    return struct.pack('<I',len(records))+b''.join(records),cases

def build_probes(output):
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip())
    relative=(PLUGIN/'ThirdParty/skate-runtime/crates/skate-core/src').relative_to(root).as_posix()
    revision=subprocess.check_output(['git','rev-parse',REFERENCE_REVISION],cwd=root,text=True).strip()
    archive=subprocess.check_output(['git','archive',f'{revision}:{relative}'],cwd=root);source=output/'reference-source'
    if source.exists():shutil.rmtree(source)
    source.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:stream.extractall(source,filter='data')
    originals={p.relative_to(source).as_posix():digest(p) for p in sorted(source.rglob('*.rs'))}
    probe=PLUGIN/'Tests/Reference/contact_retention_probe.rs';main=source/'contact-retention-oracle.rs'
    main.write_text((source/'lib.rs').read_text()+probe.read_text().replace('//!','//'));reference=output/'contact-retention-reference'
    subprocess.run(['rustc','+1.97.1','--edition=2024','-O','-A','dead_code',str(main),'-o',str(reference)],check=True)
    for name,expected in originals.items():
        if digest(source/name)!=expected:raise AssertionError(f'Frozen reference module changed: {name}')
    snapshot=output/'simulation-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir();simulation=PLUGIN/'Source/AtelierSkate/Private/Simulation'
    sources=('SimulationMath.h','SimulationMath.cpp','GeometryTypes.h','ContactRetention.h','ContactRetention.cpp')
    for name in sources:shutil.copy2(simulation/name,snapshot/name)
    shutil.copy2(PLUGIN/'Tests/Simulation/contact_retention_probe.cpp',snapshot/'contact_retention_probe.cpp');cpp=output/'contact-retention-cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(snapshot),
        *[str(snapshot/name) for name in ('SimulationMath.cpp','ContactRetention.cpp','contact_retention_probe.cpp')],'-o',str(cpp)],check=True)
    provenance=dict(reference_revision=revision,source_archive_sha256=hashlib.sha256(archive).hexdigest(),original_source_sha256=originals,
        probe_sha256=digest(probe),reference_binary_sha256=digest(reference),cpp_binary_sha256=digest(cpp),
        simulation_source_sha256={p.name:digest(p) for p in sorted(snapshot.iterdir())},
        rust_compiler=subprocess.check_output(['rustc','+1.97.1','-vV'],text=True).strip(),cpp_compiler=subprocess.check_output(['clang++','--version'],text=True).strip())
    (output/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');return cpp,reference

def decode(data,cases):
    words=struct.unpack('<'+'I'*(len(data)//4),data);at=0;rows=[]
    for case in cases:
        if at+3>len(words):raise AssertionError('Missing contact retention frame')
        index,op,n=words[at:at+3]
        if index!=case['index'] or OPERATIONS[op]!=case['operation']:raise AssertionError('Retention frame identity changed')
        rows.append(words[at+3:at+3+n]);case.update(first_output_word=at,output_words=n+3);at+=n+3
    if at!=len(words):raise AssertionError('Trailing contact retention frame')
    return rows

def coverage(rows,cases):
    counts=Counter()
    for row,case in zip(rows,cases):
        op=case['operation']
        if op=='coplanar':counts['coplanar_yes' if row[0] else 'coplanar_no']+=1
        elif op=='selection':
            counts[f'selection_{row[0]}']+=1
            # The simulation writes the third candidate before deciding a line returns two.
            if row[0]==1 and list(row[2:])!=case['initial_selected'][1:]:raise AssertionError('Selection one-point tail overwritten')
        elif op=='buffer':
            n=row[0];at=1
            for _ in range(n):
                command,exists,index,duplicate,*state=row[at:at+12];at+=12
                counts['allocations' if command==0 and exists else 'allocation_rejections' if command==0 else 'reduce_commands' if command==1 else 'flush_commands']+=1
                counts['duplicate_rejections']+=duplicate;counts['full_states']+=bool(state[7])
            state=row[at:at+8];at+=8;records=row[at:at+3200];at+=3200;chunk_count=row[at];at+=1;counts['published_chunks']+=chunk_count
            counts['published_rows']+=state[1] if state[1]<100000 else 0
            for _ in range(chunk_count):count=row[at];at+=1+count*64
            if at!=len(row):raise AssertionError('Contact buffer output framing changed')
            counts['quieted_float_copies']+=sum(records[i]==0x7fe12345 and case['initial_records'][i]==0x7fa12345 for i in range(3200) if i%64==24)
            counts['integer_payload_tags_retained']+=sum(records[i]==0x7fa12345 for i in range(3200) if i%64==23)
    for key in ('selection_1','selection_2','selection_3','selection_4','allocations','allocation_rejections','duplicate_rejections','published_chunks','quieted_float_copies','integer_payload_tags_retained'):
        if not counts[key]:raise AssertionError(f'Unexercised retention branch: {key}')
    return dict(counts)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json','provenance.json'):(output/name).unlink(missing_ok=True)
    inputs,cases=corpus();(output/'input.bin').write_bytes(inputs);cpp,reference=build_probes(output)
    expected=subprocess.check_output([str(reference)],input=inputs);actual=subprocess.check_output([str(cpp)],input=inputs);(output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual)
    rows=decode(expected,cases);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    if expected!=actual:
        first=next((i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b),min(len(expected),len(actual)));aligned=first//4*4;case=next((c for c in cases if c['first_output_word']*4<=first<(c['first_output_word']+c['output_words'])*4),None)
        report=dict(passed=False,first_word=first//4,case=case,reference_length=len(expected),cpp_length=len(actual),reference_hex=expected[max(0,aligned-16):aligned+32].hex(),cpp_hex=actual[max(0,aligned-16):aligned+32].hex());(output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
    counts=coverage(rows,cases);report=dict(passed=True,cases=len(cases),operations=dict(Counter(c['operation'] for c in cases)),coverage=counts,exact_words=len(expected)//4,input_sha256=hashlib.sha256(inputs).hexdigest(),output_sha256=hashlib.sha256(expected).hexdigest(),comparison='All words exact, including 50 complete records, every state and publication chunk; numerical modules unchanged')
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
