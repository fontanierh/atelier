#!/usr/bin/env python3
"""Exact pinned score ledger, carrier, timers and sequence/line settlement.

This is the complete core accounting owner. Authored scoring data, recognition,
collector gameplay inputs and full frame scheduling are separate host owners.
Only the root coordinator compiles/runs it through the shared render guard.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import shutil
import struct
import subprocess
from check_animation_trees_parity import source_at_reference
from check_gesture_parity import PLUGIN
from reference_build import build_probe

UNITS=('NativeMath','ScoringCore','ScoringTimer','ScoringCarrier','ScoringSession')
CORE='crates/skate-core/src/scoring'
SNAPSHOT_WORDS=720

def bits(value):return struct.unpack('<I',struct.pack('<f',value))[0]
def floats(values):return [bits(v)for v in values]
def pack(words):return struct.pack('<'+'I'*len(words),*words)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def rules(n=0):
    return floats([801+(n%3)*.137,50,1.5,450,2,800,3,799,400,.3 if n%2 else 0])
def create(slot,id=96,category=3,kind=2,points=100,start=0,delay=4,n=0):
    return [16,slot,id,category,kind,points&0xffffffff]+floats([.2+(n%3)*.137,2.25])+[start&0xffffffff,delay,n%2,(n//2)%2]

def corpus():
    rng=random.Random(0x82da6198);cases=[]
    for n in range(24):
        commands=[create(0,start=0xfffffffd,n=n),create(1,id=128,category=4,kind=1,n=n+1)]
        for k in range(160):
            commands.append([0,96,3,2]+floats([.137]))
        commands += [[10,96,3,2],[2],[3],[4]+floats([1.1]),[4]+floats([1.1]),[5]+floats([22])+[1],[7,0],[7,1]]
        for k in range(144):
            id=(k*13+n)%332;category=(0,1,2,3,4,5,6,0xffffffff)[k%8];kind=(0,1,2,5,6,8,9,11,13,14,0xffffffff)[k%11]
            value=rng.uniform(-31.7,731.137)
            commands += [[k%2,id,category,kind]+floats([value]),[22,id,category,kind]]
            if k%7==0:commands += [[2],[4]+floats([.731]),[14]+rules(n)+floats([1.1])+[k%3==0,k%2]]
            if k%13==0:commands += [[9,1],[0,96,3,2]+floats([17]),[9,0],[6]]
            if k%17==0:commands += [[15,k%2,(k//17)%2],[8]]
            if k%19==0:commands += [[3],[5]+floats([73.1])+[k%2],[7,k%2]]
        commands += [[0,332,3,2]+floats([100]),[1,0xffffffff,1,0]+floats([10]),[10,332,3,2],[10,331,3,14]]
        for k in range(48):
            commands += [[13]+floats([(-10,0,1.000002,2,400,1e8)[k%6],(0,1,400,1e6)[k%4]]),[11]+floats([(0,.1,1/60,-.1)[k%4],(0,50,100,-10)[(k//2)%4],(0,1,.731,-1)[(k//3)%4]])+[k%2]]
            commands += [[12]+floats([(1,49,50,400,450,350,800,801,-1000)[k%9]])+rules(k),[21]+floats([(0,-0.,10,100)[k%4]])]
            commands += [[17,0,(0,1,2,0xfffffffc,0xffffffff)[k%5]]+floats([.3]),[18,k%2]+floats([.3])]
            if k%7==0:commands += [create(0,id=96+k,start=0xfffffffd,delay=k,n=k),create(1,id=332 if k%2 else 128,category=4,n=k),[19,0,1]+floats([.3])]
        commands += [[8],[15,1,0],[12]+floats([50])+rules(),[0,96,3,2]+floats([50]),[2],[14]+rules()+floats([1])+[0,1],[0,96,3,2]+floats([10]),[2],[14]+rules()+floats([1])+[0,1],[15,0,1],[15,0,0]]
        cases.append(dict(label='retained accounting, saturation, collector exits, carrier edges, timer expiry and publication',commands=commands))
    # Every float cast boundary, signed zero, infinity and both NaN classes.
    edge=[0,0x80000000,1,0x80000001,bits(.1),bits(-.1),bits(1e17),bits(-1e17),0x7f7fffff,0xff7fffff,0x7f800000,0xff800000,0x7fc12345,0xffc12345,0x7f812345,0xff812345]
    casts=[[20,a,b]for a in edge for b in edge]
    cases.append(dict(label='full saturating f32-to-i64 then wrapping-u32 delay cast',commands=casts))
    timer_commands=[]
    for a in edge:
        for b in edge:
            timer_commands += [[15,1,0],[13,a,b],[21,b],[11,bits(.1),bits(50),bits(1),0]]
    cases.append(dict(label='timer min, division and exceptional operand order',commands=timer_commands))
    holds=[]
    for value in (1.000001,1.000002,1.001,1.1,2,20):
        holds += [[15,1,0],[13]+floats([value,400]),[11]+floats([.1,500,1])+[1],
                  [11]+floats([.1,500,1])+[0],[11]+floats([.1,500,1])+[0]]
    cases.append(dict(label='reachable near-one hold and following expiry-edge reset',commands=holds))
    records=[len(cases)]
    lengths=(5,5,1,1,2,3,1,2,1,2,4,5,12,3,14,3,12,4,3,4,3,2,4)
    for case in cases:
        records.append(len(case['commands']))
        for command in case['commands']:
            assert len(command)==lengths[command[0]],(command,lengths[command[0]])
            records.extend(int(w)&0xffffffff for w in command)
    return pack(records),cases

def prepare(output):
    code=PLUGIN/'Source/AtelierSkate/Private/Native';snapshot=output/'native-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir()
    for filename in ('NativeMath.h','DataReader.h',*[f'{u}.h'for u in UNITS[1:]],*[f'{u}.cpp'for u in UNITS]):
        shutil.copy2(code/filename,snapshot/filename)
    probe=PLUGIN/'Tests/Native/scoring_core_probe.cpp';shutil.copy2(probe,snapshot/probe.name)
    source=source_at_reference(CORE+'.rs');template=PLUGIN/'Tests/Reference/scoring_core_probe.rs';generated=output/'scoring-core-reference.rs'
    raw=template.read_text().replace('// ORIGINAL_SCORING_OWNER',source);assert source in raw;generated.write_text(raw)
    report=dict(original_scoring_owner_sha256=digest(source.encode()),original_child_sha256={n:digest(source_at_reference(CORE+'/'+n+'.rs').encode())for n in('carrier','catalog','conversions','session','timer')},native_snapshot_sha256={p.name:digest(p.read_bytes())for p in snapshot.iterdir()},reference_probe_sha256=digest(template.read_bytes()),observer='Read-only appended original-module observer reads all private retained arrays/flags; complete original source is an unchanged substring.')
    (output/'prepared-provenance.json').write_text(json.dumps(report,indent=2)+'\n')
    return generated,snapshot

def inspect(raw,cases):
    words=struct.unpack('<'+'I'*(len(raw)//4),raw);at=1;assert words[0]==len(cases);coverage=Counter();ops=Counter()
    for index,case in enumerate(cases):
        assert words[at:at+2]==(index,len(case['commands']));at+=2
        initial=words[at:at+SNAPSHOT_WORDS];at+=SNAPSHOT_WORDS
        assert initial[689]==bits(1)and sum(v!=0 for v in initial)==1
        previous=initial
        for command in case['commands']:
            op,result=words[at:at+2];assert op==command[0];at+=2;ops[op]+=1
            s=words[at:at+SNAPSHOT_WORDS];at+=SNAPSHOT_WORDS
            assert len(s)==SNAPSHOT_WORDS
            assert all(v<=127 for v in s[7:685])
            coverage['saturated_history_rows']+=127 in s[7:685]
            coverage['pending_rows']+=bool(s[685]);coverage['suppressed_rows']+=bool(s[686])
            coverage['line_expiry_rows']+=bool(s[691]);coverage['carrier_announced_rows']+=bool(s[701]or s[715])
            coverage['carrier_completed_rows']+=bool(s[702]or s[716]);coverage['carrier_unannounced_rows']+=bool(s[703]or s[717])
            coverage['line_bank_changes']+=s[0]!=previous[0]
            if op==8:assert s[0]==previous[0]and all(v==0 for v in s[1:687]),'Reset retains only lifetime completed-line score'
            if op in(0,1)and previous[686]:assert s[:687]==previous[:687],'Suppressed credit mutates nothing'
            if op==10:coverage['invalid_repetition_results']+=result==0xffffffff
            if op==11:coverage['near_one_holds']+=bool(result)
            if op==17:coverage['announcement_edges']+=bool(result)
            previous=s
    assert at==len(words),(at,len(words));assert set(ops)==set(range(23))
    for key in ('saturated_history_rows','pending_rows','suppressed_rows','line_expiry_rows','carrier_announced_rows','carrier_completed_rows','carrier_unannounced_rows','line_bank_changes','invalid_repetition_results','near_one_holds','announcement_edges'):assert coverage[key]>0,(key,coverage)
    return dict(operations=dict(ops),observations=dict(coverage))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for field in ('output','target-dir'):parser.add_argument('--'+field,type=Path,required=True)
    parser.add_argument('--preflight',action='store_true');args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json'):(output/name).unlink(missing_ok=True)
    inputs,cases=corpus();(output/'input.bin').write_bytes(inputs);generated,snapshot=prepare(output)
    summary=dict(cases=len(cases),commands=sum(len(c['commands'])for c in cases),input_bytes=len(inputs),input_sha256=digest(inputs),snapshot_words=SNAPSHOT_WORDS,units=UNITS)
    if args.preflight:print(json.dumps(summary,indent=2));return
    native=output/'scoring-core-cpp';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(u+'.cpp'))for u in UNITS],str(snapshot/'scoring_core_probe.cpp'),'-o',str(native)],check=True)
    aliases={f'atelier-host/src/original_score/{n}.rs':CORE+'/'+n+'.rs'for n in('carrier','catalog','conversions','session','timer')}
    reference=build_probe(output,'scoring-core-reference',generated,args.target_dir,extra_sources=aliases)
    expected=subprocess.check_output([str(reference)],input=inputs);actual=subprocess.check_output([str(native)],input=inputs);(output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual)
    if expected!=actual:
        first=next((i for i,(a,b)in enumerate(zip(expected,actual))if a!=b),min(len(expected),len(actual)))//4
        failure=dict(first_word=first,reference_bytes=len(expected),cpp_bytes=len(actual),reference=expected[first*4:first*4+4].hex(),cpp=actual[first*4:first*4+4].hex())
        (output/'first-divergence.json').write_text(json.dumps(failure,indent=2)+'\n');raise AssertionError(failure)
    result=dict(passed=True,**summary,exact_bytes=len(expected),output_sha256=digest(expected),coverage=inspect(expected,cases),scope='Complete original Scorable/ScoreHolder/Carrier/PointTimer/ComboTimer/Session with all retained words, core arithmetic, saturating histories, delay casts and publication edges.',boundaries='Recognition, authored catalog/settings/collector tuning, gameplay frame inputs and global scheduling remain separate host composition checks.')
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
