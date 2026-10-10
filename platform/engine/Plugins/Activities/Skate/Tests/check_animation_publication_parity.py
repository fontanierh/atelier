#!/usr/bin/env python3
"""Compare simulation actor stance state and selective evaluated-pose publication.

Original actor state is included unchanged; the two actor stance getter bodies
are extracted verbatim with byte boundaries. Core packet reset/publication use
the untouched frozen implementations. Run this job under atelier.safety.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import random
import shutil
import struct
import subprocess
import check_animation_trees_parity as trees
from check_animation_playback_parity import Stream,bits
from reference_build import build_probe
PLUGIN=trees.PLUGIN


class Writer(Stream):
    def raw(self,value):self.word(len(value));self.data.extend(value)
    def matrices(self,matrices):
        self.word(len(matrices))
        for m in matrices:
            for word in m:self.word(word)
    def publication(self,s):
        for v in s[:11]:self.word(v)
        if s[10]:self.word(s[11]);self.word(s[12])
    def packet(self,p):
        self.word(p['count']);self.matrices(p['hierarchy']);self.matrices(p['local'])
        for v in p['fields']:self.word(v)
    def reset_fields(self,f):
        for v in f:self.word(v)


def prepare_source(output):
    original=trees.source_at_reference('crates/skate-host/src/skater_animation.rs');methods=[];records=[]
    for marker in ('    pub fn checkpoint_stance(','    pub fn request_checkpoint_stance('):
        body,record=trees.extract_block(original,marker);methods.append(body);records.append(record)
    source=output/'animation-publication-oracle.rs';source.write_text((PLUGIN/'Tests/Reference/animation_publication_probe.rs').read_text()+'\nimpl SkaterAnimation {\n'+'\n'.join(methods)+'\n}\n')
    report=dict(actor_source_sha256=hashlib.sha256(original.encode()).hexdigest(),actor_extractions=records,direct_modules=['crates/skate-host/src/skater_animation/state.rs','crates/skate-core/src/animation/output/physics_packet.rs','crates/skate-core/src/animation/output/packet_reset.rs'],callback_boundary='Only actor request_checkpoint_stance writes a matching requested_stance u32 target; no producer callback is stubbed. All actor flag state and packet array/reset/request/signal mutation executes original implementation.',probe_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    (output/'actor-extraction-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return source


def corpus():
    rng=random.Random(0x82b985e8);cases=[];counts={0:0,1:0,2:0,3:0}
    def new(op):s=Writer();s.word(op);cases.append(s);counts[op]+=1;return s
    def matrix():return [rng.getrandbits(32) for _ in range(16)]
    def packet(count=3,hierarchy=5,local=5,flags=None):
        return dict(count=count,hierarchy=[matrix() for _ in range(hierarchy)],local=[matrix() for _ in range(local)],fields=[bits(.731),rng.getrandbits(32),rng.getrandbits(32),rng.getrandbits(32) if flags is None else flags,*[rng.getrandbits(1) for _ in range(6)],rng.getrandbits(32)])
    def reset_fields():return [bits(.137),bits(.317),bits(.731),*[255]*9,bits(.113),bits(.719),*[rng.getrandbits(32) for _ in range(24)],rng.getrandbits(32)]
    for count in (0,1,2,3,7,0x7fffffff,0x80000000,0xffffffff):
        for h,l in itertools.product((0,2,7),(0,2,7)):
            s=new(0);s.packet(packet(count,h,l));s.reset_fields(reset_fields())
    # Every publication flag/request combination plus signed stance enum cases,
    # packet opaque flags and untouched matrix tails after its active prefix.
    times=(0.0,-0.0,1/60,float(struct.unpack('<f',struct.pack('<I',0x3c888889))[0]),.731,1e-40,-1e-40,1e30)
    for flags in range(128):
        for stance in range(8):
            relative=(-1,0,1,2)[stance%4];natural=(-1,0,1,2)[(stance//2)%4];state=[flags&1,(flags>>1)&1,(flags>>2)&1,(flags>>3)&1,relative,natural,(flags>>4)&1,(flags>>5)&1,(flags>>6)&1,rng.getrandbits(32),stance%2,rng.getrandbits(32),255]
            s=new(1);s.publication(state);s.packet(packet(flags%4,5,6));s.matrices([matrix() for _ in range(5)]);s.matrices([matrix() for _ in range(6)]);s.data.extend(struct.pack('<d',times[stance]));s.raw(b'signup\0ignored' if stance%2 else bytes([255,128,127,254])*17)
    for count,h,l,source_h,source_l in ((3,2,3,3,3),(3,3,2,3,3),(3,3,3,2,3),(3,3,3,3,2),(0xffffffff,2,2,2,2),(0x80000000,2,2,2,2)):
        s=new(1);s.publication([1,1,1,1,1,0,1,1,1,-1,1,0xdeadbeef,255]);s.packet(packet(count,h,l));s.matrices([matrix() for _ in range(source_h)]);s.matrices([matrix() for _ in range(source_l)]);s.data.extend(struct.pack('<d',.731));s.raw(b'signup')
    for raw in [b'',b'signup',b'signup\0tail',bytes(range(1,256)),bytes(range(255,0,-1))]+[bytes(rng.getrandbits(8) for _ in range(i)) for i in range(128)]:new(2).raw(raw)
    # Simulation stance events test presence only. Duplicated names toggle once,
    # ordering is retained, and request fields survive until packet publication.
    for natural,relative,local_player in itertools.product((-1,0,1,2),(0,1,2,-1),(False,True)):
        for flag in (0,0xffffffff,0x00318000,0xf8000000):
            state=[1,0,1,0,relative,natural,1,1,1,-7,1,0xdeadbeef,255];s=new(3);s.word(local_player);s.word(0xdeadbeef)
            operations=[(0,None),(2,None),(4,0),(4,1),(4,0xffffffff),(3,None)]
            for events in ([],['animboardbackward'],['mirrored'],['switch'],['switch','switch','mirrored','mirrored','animboardbackward'],['MISSING']):operations.extend([(1,events),(2,None),(3,None)])
            s.word(len(operations))
            for op,a in operations:
                s.word(op)
                if op==0:s.word(flag);s.publication(state);s.float(.731)
                elif op==1:
                    s.word(len(a))
                    for name in a:s.name(trees.name(name))
                elif op==4:s.word(a)
    return cases,counts


def encoded(cases):return b'ATAPUBL1'+len(cases).to_bytes(4,'little')+b''.join(s.data for s in cases)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);p.add_argument('--target-dir',required=True,type=Path);args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    reference=build_probe(output,'animation-publication-reference',prepare_source(output),args.target_dir)
    live=PLUGIN/'Source/AtelierSkate/Private/Simulation';code=output/'simulation-source';code.mkdir(exist_ok=True);files=['AnimationPublication.cpp','AnimationName.cpp']
    for path in list(live.glob('*.h'))+[live/f for f in files]:shutil.copyfile(path,code/path.name)
    probe=code/'animation_publication_probe.cpp';shutil.copyfile(PLUGIN/'Tests/Simulation/animation_publication_probe.cpp',probe)
    snapshot={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(code.iterdir()) if p.is_file()};(output/'simulation-source-provenance.json').write_text(json.dumps(snapshot,indent=2)+'\n')
    binary=output/'animation-publication-cpp';subprocess.run(['clang++','-std=c++17','-O2','-fno-exceptions','-ffp-contract=off','-Wall','-Wextra','-Werror','-I',str(code),*[str(code/f) for f in files],str(probe),'-o',str(binary)],check=True)
    cases,counts=corpus();commands=encoded(cases);(output/'input.bin').write_bytes(commands)
    def run(exe,data):return subprocess.check_output([str(exe)],input=data)
    expected=run(reference,commands);actual=run(binary,commands);(output/'reference.bin').write_bytes(expected);(output/'simulation.bin').write_bytes(actual)
    if actual!=expected:
        lo=0;hi=len(cases)
        while hi-lo>1:
            m=(lo+hi)//2;data=encoded(cases[lo:m])
            if run(reference,data)==run(binary,data):lo=m
            else:hi=m
        (output/'first-divergence-input.bin').write_bytes(encoded(cases[lo:hi]));first=next((i for i,(a,e) in enumerate(zip(actual,expected)) if a!=e),min(len(actual),len(expected)))
        raise AssertionError(f'Animation publication differs at byte {first}, case {lo}; isolated command saved')
    result=dict(passed=True,cases=len(cases),counts=counts,output_bytes=len(actual),output_sha256=hashlib.sha256(actual).hexdigest(),comparison='complete selective packet reset/publication, retained matrix tails and opaque flags, signed/unsigned extents, stance/event/cull state, checkpoint requests and signed-byte signal hashing',extraction_provenance_sha256=hashlib.sha256((output/'actor-extraction-provenance.json').read_bytes()).hexdigest(),simulation_source_provenance_sha256=hashlib.sha256((output/'simulation-source-provenance.json').read_bytes()).hexdigest())
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
