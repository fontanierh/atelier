#!/usr/bin/env python3
"""Exact exported regional-force helper plus unchanged Wipeout regression.

Only the root coordinator compiles or runs this proof. The aliased original
selected_max + force source slice remains byte-identical; the full common.rs
source and exact contiguous slice are independently hashed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import shutil
import struct
import subprocess
from reference_build import build_probe
from check_wipeout_runtime_parity import PLUGIN,UNITS
from check_skeleton_input_runtime_parity import source

def bits(value):return struct.unpack('<I',struct.pack('<f',value))[0]
def corpus():
 rng=random.Random(0x82bd88a0);records=[];cases=[]
 def add(label,words):
  assert len(words)==10;records.append(struct.pack('<10I',*words));cases.append(dict(index=len(cases),label=label,input_words=words))
 for n in range(8192):
  values=[rng.uniform(-1.e5,1.e5)for _ in range(8)]+[rng.uniform(-1.e5,1.e5),rng.uniform(-1.e5,1.e5)]
  if n%4==0:values[8]=values[(0,1,5,4,7,6)[n%6]]
  if n%4==1:values[9]=values[2+n%2]
  add('finite randomized and exact equality thresholds',list(map(bits,values)))
 boundaries=[0,0x80000000,1,0x80000001,0x3f800000,0xbf800000,0x7f7fffff,0xff7fffff,0x7f800000,0xff800000,0x7fc12345,0xffc23456,0x7f812345,0xff812346]
 for lane in range(8):
  for a in boundaries:
   for b in boundaries:
    w=[bits(-2)]*8+[b,b];w[lane]=a;add('single region and exceptional threshold',w)
 for pair in ((0,1),(5,4),(7,6),(2,3)):
  for a in boundaries:
   for b in boundaries:
    w=[bits(-2)]*8+[bits(0),bits(0)];w[pair[0]]=a;w[pair[1]]=b;add('ordered regional pair including NaN peer selection',w)
 return struct.pack('<I',len(records))+b''.join(records),cases

def prepare(output):
 simulation=PLUGIN/'Source/AtelierSkate/Private/Simulation';snapshot=output/'simulation-source'
 if snapshot.exists():shutil.rmtree(snapshot)
 snapshot.mkdir()
 for p in simulation.glob('*.h'):shutil.copy2(p,snapshot/p.name)
 for unit in UNITS:shutil.copy2(simulation/f'{unit}.cpp',snapshot/f'{unit}.cpp')
 probe=snapshot/'wipeout_regional_force_probe.cpp';shutil.copy2(PLUGIN/'Tests/Simulation/wipeout_regional_force_probe.cpp',probe)
 hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in snapshot.iterdir()}
 original=source('crates/skate-core/src/player/wipeout/common.rs');start=original.index('fn selected_max(');end=original.index('pub(super) fn vehicle',start);body=original[start:end]
 assert body in original and body.startswith('fn selected_max(')and body.count('pub(crate) fn force(')==1
 generated=output/'wipeout-regional-force-reference.rs';template=(PLUGIN/'Tests/Reference/wipeout_regional_force_probe.rs').read_text();assert template.count('// ORIGINAL_FORCE')==1;generated.write_text(template.replace('// ORIGINAL_FORCE',body))
 provenance=dict(simulation_source_sha256=hashes,original_common_sha256=hashlib.sha256(original.encode()).hexdigest(),original_contiguous_force_sha256=hashlib.sha256(body.encode()).hexdigest(),source_slice_start=start,source_slice_end=end)
 (output/'simulation-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');return probe,snapshot,generated

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--target-dir',required=True,type=Path);parser.add_argument('--preflight',action='store_true');a=parser.parse_args()
 output=a.output.resolve();output.mkdir(parents=True,exist_ok=True);blob,cases=corpus();(output/'input.bin').write_bytes(blob);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');probe,snapshot,generated=prepare(output)
 summary=dict(cases=len(cases),input_bytes=len(blob),input_sha256=hashlib.sha256(blob).hexdigest(),units=UNITS)
 if a.preflight:print(json.dumps(summary,indent=2));return
 simulation=output/'wipeout-regional-force-cpp';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/f'{u}.cpp')for u in UNITS],str(probe),'-o',str(simulation)],check=True)
 reference=build_probe(output,'wipeout-regional-force-reference',generated,a.target_dir)
 expected=subprocess.check_output([str(reference)],input=blob);actual=subprocess.check_output([str(simulation)],input=blob);(output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual)
 assert len(expected)==4*len(cases)
 if expected!=actual:
  first=next((i for i,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)))//4
  raise AssertionError(dict(first_case=first,case=cases[first],reference_bytes=len(expected),cpp_bytes=len(actual)))
 words=struct.unpack('<'+'I'*len(cases),expected);assert set(words)=={0,1}
 result=dict(passed=True,**summary,exact_words=len(words),true_results=sum(words),output_sha256=hashlib.sha256(expected).hexdigest(),comparison='Unmodified original common::force pair order, subtraction-based selection, strict thresholds and all eight regions; every result bit exact.')
 (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
