#!/usr/bin/env python3
"""Compare parameter refresh and PlayAnimation lifecycle with the frozen host.

Read/write callbacks are compared in original order, including consumed graph
overrides, missing context producers, native play refusal and explicit failures.
Run both probe compiles through atelier.safety's render lock and memory guard.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
from check_gesture_parity import PLUGIN
from check_animation_playback_parity import Stream,attribute,bits
from reference_build import build_probe

A=[11*79235168,0,0,0,0]
B=[12*79235168,0,0,0,0]


class Writer(Stream):
    def optional_string(self,value):
        self.word(value is not None)
        if value is not None:self.string(value)
    def values(self,values):
        self.word(len(values))
        for name,value in values:self.string(name);self.word(value)
    def transition(self,s):self.word(s['kind']);self.word(s['seconds']);self.word(s['under']);self.word(s['matching']);self.word(s['channels'])
    def parameter(self,p):
        self.word(p['source'])
        if p['source']==2:self.name(p['name'])
        else:self.string(p['intent'])
        self.word(p['rename'] is not None)
        if p['rename'] is not None:self.name(p['rename'])
        self.word(p['default'] is not None)
        if p['default'] is not None:self.word(p['default'])
        self.word(p['normalized'])
    def parameters(self,values):
        self.word(len(values))
        for value in values:self.parameter(value)
    def host(self,last=(),last_error=None,responses=(1,),motion=(('A',bits(0.731)),('B',bits(2))),filtered=(('A',bits(0.123)),)):
        self.values(motion);self.values(filtered);self.optional_string(last_error);self.word(len(last))
        for a in last:self.attr(a)
        self.word(len(responses))
        for response in responses:
            self.word(response if isinstance(response,int) else 2)
            if not isinstance(response,int):self.string(response)
    def operation(self,kind,variants,parameters):
        self.string('BaseClip');self.optional_string('SwitchClip' if variants&1 else None);self.optional_string('MirrorClip' if variants&2 else None);self.optional_string('NoBoardClip' if variants&4 else None)
        self.word(bits(0.731));self.word(bool(variants&2));self.transition(transition(kind));self.parameters(parameters)
    def context(self,states,override):
        for state in states:self.word(state)
        self.name([0xffffffff,0x80000000,1,2,3]);self.word(override is not None)
        if override is not None:self.transition(override)


def transition(kind):return dict(kind=kind,seconds=bits(0.713),under=17,matching=3,channels=True)


def parameter(source=0,intent='A',rename=None,default=None,normalized=False,name=A):
    return dict(source=source,intent=intent,name=name,rename=rename,default=default,normalized=normalized)


def corpus():
    cases=[];counts={1:0,2:0}
    def new(kind):
        s=Writer();s.word(kind);cases.append(s);counts[kind]+=1;return s
    for source,beginning,rename,default,normalized,kind in itertools.product(range(3),(False,True),(None,B),(None,bits(0.25)),(False,True),(None,0,1,2,3,99,'uninitialized','error')):
        a=attribute(kind=kind if isinstance(kind,int) else 0,seed=3);a['name']=A;a['payload'][0]=0x7fc12345 if kind==2 else bits(-0.0)
        if kind=='uninitialized':a['payload'][0]=None
        s=new(1);s.host(last=[] if kind in (None,'error') else [a],last_error='Last attribute producer unavailable' if kind=='error' else None)
        s.word(beginning);s.parameters([parameter(source,rename=rename,default=default,normalized=normalized),parameter(source,intent='Missing',rename=rename,default=default,normalized=normalized,name=B)])
    # The first write changes the second source in this deterministic host. A
    # resolver that collects all inputs before publishing would diverge here.
    s=new(1);s.host();s.word(True);s.parameters([parameter(rename=B),parameter(intent='B'),parameter(1,default=bits(0.731),normalized=True),parameter(1,intent='Missing',default=bits(0.731),normalized=True)])
    params=[parameter(rename=B),parameter(intent='B'),parameter(1,default=bits(0.731),normalized=True),parameter(2,default=bits(0.5))]
    responses=((1,),(0,1),(0,0),('Primary tree unavailable',),(0,'Fallback tree unavailable'))
    overrides=(None,transition(0),dict(transition(2),seconds=bits(1.125),matching=1,under=99,channels=False),transition(7))
    for kind,variants,states,response in itertools.product(range(7),range(8),itertools.product(range(3),repeat=3),responses):
        s=new(2);a=attribute(kind=0,seed=1);a['name']=A;s.host(last=[a],responses=response);s.operation(kind,variants,params)
        override=overrides[len(cases)%len(overrides)];s.context(states,override)
        s.word(8)
        # Begin, then skip-first Update despite a changed provider, refresh on
        # the following Update, End no-op, and another refresh/new Begin.
        for step in (0,3,1,1,2,1,0,1):
            s.word(step)
            if step==3:s.values([('A',bits(0.731)),('B',bits(1.234))])
    # Parameter failure precedes construction values/override consumption, and
    # failed Begin still marks the first-update skip in native instance state.
    for missing in ('uninitialized','error'):
        s=new(2);a=attribute(kind=0);a['name']=A;a['payload'][0]=None;s.host(last=[a],last_error='Missing last-animation producer' if missing=='error' else None)
        s.operation(1,7,[parameter(2)]);s.context((2,2,1),transition(3));s.word(5)
        for step in (0,1,1,2,0):s.word(step)
    return cases,counts


def encoded(cases):return b'ATPARAM1'+len(cases).to_bytes(4,'little')+b''.join(s.data for s in cases)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--target-dir',required=True,type=Path)
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    reference=build_probe(output,'animation-playback-parameters-reference',PLUGIN/'Tests/Reference/animation_playback_parameters_probe.rs',args.target_dir)
    code=PLUGIN/'Source/AtelierSkate/Private/Native';binary=output/'animation-playback-parameters-cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-fno-exceptions','-ffp-contract=off','-Wall','-Wextra','-Werror','-I',str(code),str(code/'AnimationPlaybackParameters.cpp'),str(code/'AnimationPlayback.cpp'),str(code/'AnimationName.cpp'),str(code/'AnimationSamples.cpp'),str(code/'NativeMath.cpp'),str(PLUGIN/'Tests/Native/animation_playback_parameters_probe.cpp'),'-o',str(binary)],check=True)
    cases,counts=corpus();commands=encoded(cases);(output/'input.bin').write_bytes(commands)
    expected=subprocess.check_output([str(reference)],input=commands);actual=subprocess.check_output([str(binary)],input=commands)
    (output/'reference.bin').write_bytes(expected);(output/'native.bin').write_bytes(actual)
    if actual!=expected:
        lo=0;hi=len(cases)
        while hi-lo>1:
            middle=(lo+hi)//2;data=encoded(cases[lo:middle]);e=subprocess.check_output([str(reference)],input=data);a=subprocess.check_output([str(binary)],input=data)
            if a==e:lo=middle
            else:hi=middle
        (output/'first-divergence-input.bin').write_bytes(encoded(cases[lo:hi]))
        first=next((i for i,(a,e) in enumerate(zip(actual,expected)) if a!=e),min(len(actual),len(expected)))
        raise AssertionError(f'Playback parameters differ at byte {first}, case {lo}; isolated command saved')
    result=dict(passed=True,comparison='exact callbacks, values, request/variant/fallback decisions, consumed overrides and failures',cases=len(cases),case_types=counts,
                output_bytes=len(actual),output_sha256=hashlib.sha256(actual).hexdigest())
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
