#!/usr/bin/env python3
"""Compare ordered channel owners with the original frozen host container.

The Rust channel implementation is an exact verbatim source prefix; shared tree
probe scaffolding is reused without changing any implementation file. Guard the
compile and corpus execution through atelier.safety.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import random
import subprocess
import check_animation_trees_parity as trees
from check_animation_playback_parity import attribute,bits
from reference_build import build_probe

PLUGIN=trees.PLUGIN
CHANNEL_SNAPSHOT='''impl MotionChannels {
    pub(super) fn probe_snapshot(&self,out:&mut Vec<u8>) {
        super::word(out,self.channels.len() as u32);for c in &self.channels {
            super::string(out,&c.name);let s=c.playback.settings;
            for v in [s.priority as u32,u32::from(s.keep_alive),u32::from(s.mirrored),s.speed.to_bits(),s.blend_in.to_bits(),u32::from(s.hold_during_blend_in),s.blend_out.to_bits(),u32::from(s.hold_during_blend_out),u32::from(s.use_attributes)] {super::word(out,v);}
            super::word(out,c.playback.weight.to_bits());super::word(out,c.playback.influence.to_bits());super::word(out,u32::from(c.playback.expired()));super::word(out,u32::from(c.playback.can_transition(false)));super::word(out,u32::from(c.playback.can_transition(true)));super::snapshot(out,&c.tree);
        }
    }
}
'''


def strip_functions(source,markers):
    for marker in markers:
        block,_=trees.extract_block(source,marker);source=source.replace(block,'')
    return source


def prepare_sources(output):
    base=trees.oracle_source(output).read_text()
    base=strip_functions(base,('fn run()->','fn main()'))
    prefix=trees.source_at_reference('crates/skate-host/src/graph_host/motion_channels.rs').split('///FakieHeadChannel82BAC778',1)[0]
    module='mod motion_channels {\n'+prefix+'\n}\n'
    if base.count(module)!=1:raise AssertionError('Shared oracle channel boundary changed')
    base=base.replace(module,'mod motion_channels {\n'+prefix+'\n'+CHANNEL_SNAPSHOT+'\n}\n')
    reference=output/'animation-channels-oracle.rs';reference.write_text(base+'\n'+(PLUGIN/'Tests/Reference/animation_channels_probe.rs').read_text())
    simulation=(PLUGIN/'Tests/Simulation/animation_trees_probe.cpp').read_text()
    simulation=strip_functions(simulation,('static bool Operations(','static void OwnerSnapshot(','int main('))
    cpp=output/'animation-channels-probe.cpp';cpp.write_text(simulation+'\n'+(PLUGIN/'Tests/Simulation/animation_channels_probe.cpp').read_text())
    report=dict(channel_implementation_sha256=hashlib.sha256(prefix.encode()).hexdigest(),channel_implementation_begin=0,channel_implementation_end=len(prefix.encode()),
                frozen_extractions=json.loads((output/'host-extraction-provenance.json').read_text()),
                callbacks='Preparation invokes the actual frozen MotionAnimation::prepare_selection_spaces, in original channel order; ParameterInputs trap if invoked; owner channels probe exercises all actual container callbacks',
                reference_probe_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),simulation_probe_sha256=hashlib.sha256(cpp.read_bytes()).hexdigest())
    (output/'channel-extraction-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return reference,cpp


def settings(priority=0,keep=False,mirrored=False,speed=0.731,fade_in=0.031,hold_in=False,fade_out=0.713,hold_out=False,attrs=True):
    return dict(priority=priority,keep=keep,mirrored=mirrored,speed=bits(speed),fade_in=bits(fade_in),hold_in=hold_in,fade_out=bits(fade_out),hold_out=hold_out,attrs=attrs)


class Writer(trees.Writer):
    def settings(self,s):
        for k in ('priority','keep','mirrored','speed','fade_in','hold_in','fade_out','hold_out','attrs'):self.word(s[k])
    def channel_ops(self,ops):
        self.word(len(ops))
        for op,args in ops:
            self.word(op)
            if op==0:self.string(args[0]);self.tree(args[1]);self.settings(args[2])
            elif op==1:self.string(args)
            elif op==2:self.string(args[0]);self.word(args[1]);self.word(args[2])
            elif op in (3,4):self.string(args[0]);self.word(args[1])
            elif op==5:self.string(args[0]);self.tree(args[1]);self.settings(args[2]);self.transition(args[3]);self.word(args[4])
            elif op==7:self.word(args[0]);self.word(args[1])
            elif op in (8,9):self.settable(args)
            elif op==10:
                self.word(len(args[0]))
                for a in args[0]:self.attr(a)
                self.word(args[1])
            elif op==11:self.name(args[0]);self.word(args[1]);self.attr(args[2])
            elif op==12:self.word(args[0]);self.word(args[1])
            elif op==13:
                self.word(len(args))
                for name in args:self.string(name)


def corpus():
    rng=random.Random(0x82d1cf70);cases=[]
    names=['LEFT','left','LEFT\0unused','ABCDEFGHIJKLMNOPQRSTUVWXYZ012345_A','ABCDEFGHIJKLMNOPQRSTUVWXYZ012345_B','MISSING']
    parameters=[(trees.name(chr(65+i)),bits(0.731),False,-1) for i in range(4)]+[(trees.name(chr(88+i)),bits(0.25),False,-1) for i in range(4)]
    base=[dict(attribute(kind=0,seed=7),name=trees.name('A')),dict(attribute(kind=1,seed=8),name=trees.name('B')),dict(attribute(kind=3,seed=9),name=trees.name('C'))]
    def inspect():return [(13,names),(10,(base,15)),(11,(trees.name('A'),15,attribute(kind=3,seed=7))),(11,(trees.name('B'),31,attribute(kind=3,seed=9))),(12,(bits(0.01),True))]
    def add(ops):
        s=Writer();s.channel_ops(ops);cases.append(s)
    # Cartesian lifecycle settings exercise pre-update fades, holds, automatic
    # expiry, channel-first queries and simultaneous ordered priority ties.
    for keep,hold_in,hold_out,attrs,fade_in,fade_out in itertools.product((False,True),(False,True),(False,True),(False,True),(0,0.031,0.713),(0,0.05,0.713)):
        s=settings(keep=keep,hold_in=hold_in,hold_out=hold_out,attrs=attrs,fade_in=fade_in,fade_out=fade_out)
        ops=[(0,('LEFT',trees.clip(0,0.731,flags=0),s)),(0,('left',trees.clip(1,0.25),settings(priority=-1))),(0,('LEFT\0unused',trees.clip(2,0.5),settings(priority=1))),*inspect(),(8,parameters),(9,parameters)]
        for i in range(12):
            ops.extend([(6,None),(7,(bits((0,0.031,0.25)[i%3]),bits(rng.uniform(-0.2,1.2)))),*inspect()])
            if i==3:ops.extend([(1,'left'),(2,('MISSING',bits(0.731),False)),(3,('LEFT',bits(0.37)))])
            if i==5:ops.append((2,('LEFT',bits(0.173),hold_out)))
        ops.extend([(14,None),*inspect()]);add(ops)
    # Duplicate encoded keys and ordering remain significant after transition;
    # transitioning retains the old target without reordering or priority edits.
    for priorities,kind,resurrect in itertools.product(((2,1,2),(-1,-1,-1),(3,2,1)),(2,3,4),(False,True)):
        ops=[]
        for i,priority in enumerate(priorities):ops.append((0,(names[3+i%2],trees.clip(i,i/3),settings(priority=priority))))
        ops.extend([(8,parameters),(9,parameters),(7,(bits(0.031),bits(0.25))),(7,(bits(0.13),bits(0.25))),(2,(names[3],bits(0.731),True)),(7,(bits(0.13),bits(0.25))),(4,(names[3],False)),(4,(names[3],True)),*inspect()])
        for i in range(4):
            tree=dict(kind=1,parameter=trees.name('A'),children=[trees.clip(2,0.25),trees.clip(3,0.731)]) if i%2 else trees.selection(1,True)
            ops.extend([(5,(names[4],tree,settings(priority=99,fade_in=0.25,hold_in=True),trees.transition(kind,seconds=0.05,matching=i),resurrect)),(8,parameters),(9,parameters),(7,(bits(0.13),bits(0.25))),*inspect(),(6,None)])
        add(ops)
    # All authored tree categories enter channels, including nested selection
    # parameter errors and disabled clip evaluation/history commits.
    for kind in range(6):
        tree=trees.clip(0,0.1) if kind==0 else dict(kind=1,parameter=trees.name('A'),children=[trees.selection(1),trees.clip(1,0.731)]) if kind==1 else dict(kind=2,parameters=[trees.name('X')],children=[trees.selection(1),trees.clip(1,0.731)],simplexes=[trees.simplex(1)]) if kind==2 else trees.selection(2,True) if kind==3 else dict(kind=4,**{'from':trees.clip(0,0.1),'to':trees.selection(1)},settings=trees.transition(4)) if kind==4 else dict(kind=5,motion=trees.clip(1,0.5),posture=2,board=True,modes=[1,2],mirror=[(trees.name('LEFT'),trees.name('RIGHT')),(trees.name('RIGHT'),trees.name('LEFT'))])
        add([(0,('TREE',tree,settings())),*inspect(),(8,[]),(9,[]),(8,parameters),(9,parameters),(7,(bits(0.031),bits(0.25))),*inspect(),(1,'TREE'),(7,(bits(0.731),bits(0.25))),*inspect(),(6,None),*inspect()])
    add([*inspect(),(1,'MISSING'),(2,('MISSING',bits(0.731),True)),(3,('MISSING',bits(0.731))),(4,('MISSING',True)),(5,('MISSING',trees.clip(),settings(),trees.transition(),True)),(6,None),(7,(bits(0.031),bits(0.25))),*inspect()])
    return cases


def encoded(cases):return b'ATCCHAN1'+len(cases).to_bytes(4,'little')+b''.join(s.data for s in cases)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--target-dir',required=True,type=Path);args=parser.parse_args()
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True);reference_source,cpp=prepare_sources(output);reference=build_probe(output,'animation-channels-reference',reference_source,args.target_dir)
    fixture=trees.fixture_metadata();fixture_json=output/'fixture.json';fixture_json.write_text(json.dumps(fixture));fixture_simulation=output/'fixture.skate';fixture_simulation.write_bytes(trees.converter.pack_metadata(fixture))
    code=PLUGIN/'Source/AtelierSkate/Private/Simulation';binary=output/'animation-channels-cpp';subprocess.run(['clang++','-std=c++17','-O2','-fno-exceptions','-ffp-contract=off','-Wall','-Wextra','-Werror','-I',str(code),str(code/'AnimationChannels.cpp'),str(code/'AnimationTrees.cpp'),str(code/'AnimationMetadata.cpp'),str(code/'AnimationPlaybackParameters.cpp'),str(code/'AnimationPlayback.cpp'),str(code/'AnimationName.cpp'),str(code/'AnimationSamples.cpp'),str(code/'SimulationMath.cpp'),str(cpp),'-o',str(binary)],check=True)
    cases=corpus();commands=encoded(cases);(output/'input.bin').write_bytes(commands)
    def run(exe,path,data):return subprocess.check_output([str(exe),str(path)],input=data)
    expected=run(reference,fixture_json,commands);actual=run(binary,fixture_simulation,commands);(output/'reference.bin').write_bytes(expected);(output/'simulation.bin').write_bytes(actual)
    if actual!=expected:
        lo=0;hi=len(cases)
        while hi-lo>1:
            middle=(lo+hi)//2;data=encoded(cases[lo:middle])
            if run(reference,fixture_json,data)==run(binary,fixture_simulation,data):lo=middle
            else:hi=middle
        (output/'first-divergence-input.bin').write_bytes(encoded(cases[lo:hi]));first=next((i for i,(a,e) in enumerate(zip(actual,expected)) if a!=e),min(len(actual),len(expected)))
        raise AssertionError(f'Animation channels differ at byte {first}, case {lo}; isolated command saved')
    result=dict(passed=True,cases=len(cases),comparison='ordered live trees/settings/weights, fades, priority and encoded-key ties, transition ownership, partial attributes/errors and pose commands',output_bytes=len(actual),output_sha256=hashlib.sha256(actual).hexdigest(),extraction_provenance_sha256=hashlib.sha256((output/'channel-extraction-provenance.json').read_bytes()).hexdigest())
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
