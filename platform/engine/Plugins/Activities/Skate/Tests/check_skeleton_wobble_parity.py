#!/usr/bin/env python3
"""Exact complete original wobble histories and packed observed board poses.

Compile and execute only under the shared render/memory guard. The original
core implementation is copied unchanged with a read-only private observer.
Current physical board records and transition trigger requests are explicit
inputs here; the complete player output schedule is a later integration gate.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import struct
import subprocess
from check_animation_trees_parity import source_at_reference
from check_gesture_parity import PLUGIN,converter
from reference_build import build_probe

SOURCE='crates/skate-core/src/physics/skeleton_output/wobble.rs'
UNITS=('SimulationMath','RigidBody','SkeletonPoseFrames','SkeletonWobble','Settings','NameId','StockSettingsReader')
def bits(f):return struct.unpack('<I',struct.pack('<f',f))[0]
def floats(values):return [bits(v) for v in values]
def matrix(n):
    c,s=math.cos(n*.13),math.sin(n*.13)
    return floats([c,s,0,c,-s,c,0,-s,0,0,1,.731,n*.01,-.317,.13,1])
def corpus():
    rng=random.Random(0x82bf2fb8);programs=[]
    for variant in range(2):
        for landing in range(2):
            for reverse in range(2):
                commands=[[2],[1,landing,reverse]]+[[2] for _ in range(90)]+[[5],[3,1,1,bits(0),bits(.731),bits(-1)],[2],[0],[2]]
                programs.append(dict(label='actual stock or configured takeoff/landing expiry and retained selected curves',variant=variant,settings=floats(sum(([i*.02 for i in range(8)]+[.1*(j+1)*math.sin(i*.5) for i in range(8)] for j in range(4)),[])+[.05]),board=matrix(len(programs)),commands=commands))
    for n in range(120):
        times=[rng.choice((0.,-.05,.01,.05,.15,.3)) for _ in range(8)];times.sort()
        settings=floats(sum((times+[rng.uniform(-.25,.25) for _ in range(8)] for _ in range(4)),[])+[rng.choice((-.01,0.,.016666667,.05,.25,2))])
        commands=[[1,n%2,n%3==0]]
        for k in range(48):
            if k%11==0:commands.append([5])
            if k%7==0:commands.append([3,1,k%2,bits(rng.choice((-.1,-0.,0.,.05,.25))),bits(rng.choice((-1.,-0.,0.,.317,1.,2.))),bits(rng.choice((-1.,0.,1.)))])
            if k%13==0:commands.append([1,k%2,k%3==0])
            if k%5==0:commands.append([4]+matrix(k+n))
            commands.append([2])
        commands.extend([[0],[3,1,0,bits(0),bits(1),bits(1)],[2]])
        programs.append(dict(label='live curve/clock/amplitude and observed board mutation histories',variant=1,settings=settings,board=matrix(n),commands=commands))
    words=[len(programs)]
    for p in programs:words += [p['variant']]+(p['settings'] if p['variant'] else [])+p['board']+[len(p['commands'])]+[w for c in p['commands'] for w in c]
    return struct.pack('<'+'I'*len(words),*words),programs
def inspect(data,programs):
    words=struct.unpack('<'+'I'*(len(data)//4),data);assert words[0]==len(programs);at=1;coverage=Counter();curves=set();variants=set()
    for n,p in enumerate(programs):
        assert words[at]==n;at+=1+65
        previous=words[at:at+26];at+=26;assert previous[:6]==(0,0,0,0,bits(1),1)
        assert words[at]==len(p['commands']);at+=1
        for c in p['commands']:
            assert words[at]==c[0];current=words[at+1:at+27];at+=27;coverage[str(c[0])]+=1;curves.add(current[5]);variants.add(current)
            if c[0]==1:assert current[:6]==(1,int(c[1]),0,bits(1),bits(-1 if c[2] else 1),int(c[1]))
            if c[0]==5:assert current[:6]==(0,0,0,0,bits(1),previous[5])
            if c[0]==2:
                if previous[0]==0:assert current==previous[:6]+(0,0,0,0)+previous[10:];coverage['inactive']+=1
                else:
                    assert current[6]==1 and current[9]==current[0];coverage['sampled']+=1
                    coverage['expired']+=current[0]==0;coverage['board_mutated']+=current[10:]!=previous[10:]
            previous=current
    assert at==len(words) and set(curves)=={0,1} and len(variants)>1000
    assert all(coverage[k]>0 for k in ('inactive','sampled','expired','board_mutated','0','1','2','3','4','5'))
    return dict(coverage)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--target-dir',type=Path,required=True);p.add_argument('--preflight',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    commands,programs=corpus();(out/'input.bin').write_bytes(commands);(out/'cases.json').write_text(json.dumps(programs,indent=2)+'\n')
    if a.preflight:print(json.dumps(dict(programs=len(programs),commands=sum(len(p['commands']) for p in programs),input_bytes=len(commands)),indent=2));return
    for name in ('result.json','first-divergence.json'):(out/name).unlink(missing_ok=True)
    source=source_at_reference(SOURCE);reference_source=out/'skeleton-wobble-reference.rs';prefix=source;reference_source.write_text((PLUGIN/'Tests/Reference/skeleton_wobble_probe.rs').read_text().replace('// ORIGINAL_CORE',prefix));assert prefix in reference_source.read_text()
    reference=build_probe(out,'skeleton-wobble-reference',reference_source,a.target_dir)
    live=PLUGIN/'Source/AtelierSkate/Private/Simulation';snapshot=out/'simulation-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir()
    for path in list(live.glob('*.h'))+[live/(n+'.cpp') for n in UNITS]:shutil.copy2(path,snapshot/path.name)
    probe=snapshot/'skeleton_wobble_probe.cpp';shutil.copy2(PLUGIN/'Tests/Simulation/skeleton_wobble_probe.cpp',probe)
    (out/'simulation-provenance.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in snapshot.iterdir()},indent=2)+'\n');(out/'source-provenance.json').write_text(json.dumps(dict(path=SOURCE,sha256=hashlib.sha256(source.encode()).hexdigest()),indent=2)+'\n')
    simulation=out/'skeleton-wobble-cpp';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(n+'.cpp')) for n in UNITS],str(probe),'-o',str(simulation)],check=True)
    settings=out/'settings.simulation';settings.write_bytes(converter.encode_settings(a.assets/'private/stock/skater-collections.json'))
    expected=subprocess.check_output([str(reference),str(a.assets.resolve())],input=commands);actual=subprocess.check_output([str(simulation),str(settings)],input=commands);(out/'reference.bin').write_bytes(expected);(out/'simulation.bin').write_bytes(actual)
    if expected!=actual:
        at=next((i for i,(x,y) in enumerate(zip(expected,actual)) if x!=y),min(len(expected),len(actual)));report=dict(passed=False,word=at//4,reference_bytes=len(expected),simulation_bytes=len(actual));(out/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
    result=dict(passed=True,programs=len(programs),exact_words=len(expected)//4,sha256=hashlib.sha256(expected).hexdigest(),coverage=inspect(expected,programs),boundary='Real observed board records and transition calls are explicit. Simulation load uses exact consumed stock curve words; all core state, update and packed affine output execute complete unchanged original implementation. Complete physical output scheduling remains unverified.')
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
