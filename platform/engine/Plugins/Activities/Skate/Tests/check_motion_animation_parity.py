#!/usr/bin/env python3
"""Compare the concrete MotionAnimation owner and actual animation graph leaves.

Combines main tree, channels, parameter sources, retained graph attributes,
PlayAnimation/CreateAttribute factories and lifecycle against frozen original
host bodies with exact extraction hashes. Run under atelier.safety.
"""
import argparse
import hashlib
import itertools
import json
import math
import re
import struct
from pathlib import Path
import random
import shutil
import subprocess
import check_animation_trees_parity as trees
import check_animation_channels_parity as channels
from check_animation_playback_parity import attribute,bits
from reference_build import build_probe
PLUGIN=trees.PLUGIN


def bounded(source,begin,end):
    if source.count(begin)!=1 or source.count(end)!=1:raise AssertionError('Frozen arm boundaries changed')
    start=source.index(begin);stop=source.index(end,start);body=source[start:stop]
    raw=source.encode();a=len(source[:start].encode());b=a+len(body.encode())
    if raw[a:b]!=body.encode():raise AssertionError('Frozen arm extraction changed bytes')
    return body,dict(begin=a,end=b,sha256=hashlib.sha256(body.encode()).hexdigest(),begin_marker=begin,end_marker=end)


def prepare_sources(output):
    reference,cpp=channels.prepare_sources(output);base=reference.read_text();base=channels.strip_functions(base,('fn channel_run()->','fn main()'))
    # Probe-owned layout only: match all fields used by the complete original
    # constructor and methods; each tested implementation body remains verbatim.
    needle='    metadata:AnimationMetadata,current:Option<PlaybackTree>'
    replace='    motion_intents:skate_core::graph::intents::IntentMap,filtered_intents:skate_core::graph::intents::IntentMap,motion_attributes:Vec<MotionGraphAttribute>,grab_type:Option<motion_stock_gameplay::GrabType>,natural_stance:u32,relative_stance:u32,requested_stance:u32,reset_action_intents:bool,\n'+needle
    if base.count(needle)!=1:raise AssertionError('Probe owner layout boundary changed')
    base=base.replace(needle,replace);base=channels.strip_functions(base,('impl MotionAnimation {\n    fn new(','impl ParameterInputs for MotionAnimation {','impl AttributeSink for MotionAnimation {'))
    host=trees.source_at_reference('crates/skate-host/src/graph_host/motion_animation.rs');methods=[];records=[]
    for marker in ('    pub fn from_metadata(','    pub fn reset_from_stock(','    pub fn reset_to_given_stance(','    pub fn current_time(','    pub fn current_length(','    pub(super) fn synchronize_air_time(','    pub fn in_transition(','    pub(super) fn jump_into(','    pub fn begin_graph_update(','    pub fn attach(','    pub fn emit_packet(','    pub fn set_grab_type(','    pub fn clear_grab_type(','    pub fn new_channel(','    pub fn transition_channel('):
        body,record=trees.extract_block(host,marker);methods.append(body);records.append(record)
    base+='\nmod actual_owner_methods {use super::*;impl MotionAnimation {\n'+'\n'.join(methods)+'\n}}\n'
    for marker in ('impl ParameterInputs for MotionAnimation {','impl AttributeSink for MotionAnimation {'):
        body,record=trees.extract_block(host,marker);base+=body+'\n';records.append(record)
    gameplay=trees.source_at_reference('crates/skate-host/src/graph_host/motion_stock_gameplay.rs');enum,er=trees.extract_block(gameplay,'pub enum GrabType {');impl,ir=trees.extract_block(gameplay,'impl GrabType {')
    base+='mod motion_stock_gameplay {#[derive(Clone,Copy,Debug,PartialEq,Eq)]\n'+enum+'\n'+impl+'\n}\n'
    base+='#[path="../../crates/skate-host/src/graph_host/outputs.rs"] mod outputs;\n#[path="../../crates/skate-host/src/graph_host/motion_animation/stock_clip_query.rs"] mod actual_stock_query;\n'
    nodes=trees.source_at_reference('crates/skate-host/src/graph_host/motion_nodes.rs');riding=trees.source_at_reference('crates/skate-host/src/graph_host/motion_riding.rs');factory_methods=[];factory_records=[]
    for marker in ('fn key(','fn play(','pub(super) fn transition('):
        body,record=trees.extract_block(nodes,marker);factory_methods.append(body);factory_records.append(record)
    parameter,record=trees.extract_block(nodes,'    fn add_parameter(');factory_records.append(record)
    parse_arm,record=bounded(riding,'            "CreateAttribute" => {','            "SetDistComToBoard" =>');factory_records.append(record)
    execute_arm,record=bounded(riding,'            RidingOperation::CreateAttribute { name, values, set } => {','            RidingOperation::SetDistComToBoard {');factory_records.append(record)
    base+='''mod factory_oracle {use super::*;
#[derive(Clone)] pub enum RidingOperation {CreateAttribute{name:AttributeName,values:[Option<f32>;3],set:bool}}
impl RidingOperation {fn parse(a:&Attributes<'_>)->Option<Self> {Some(match a.text("name")? {
'''+parse_arm+'''_=>return None,})}}
pub enum MotionOperation {Unsupported,Play(PlayAnimation),CreateAttribute(RidingOperation)}
pub struct Factory;impl Factory {
'''+parameter+'''\n}
pub fn add_parameter(operation:&mut MotionOperation,a:&Attributes<'_>)->Result<(),String> {Factory.add_parameter(operation,a)}
'''+ '\n'.join(factory_methods)+'''
pub fn parse(a:&Attributes<'_>)->Result<Option<MotionOperation>,String> {let raw=a.text("name").ok_or("MotionGraph operation has no name")?;if let Some(o)=RidingOperation::parse(a) {return Ok(Some(MotionOperation::CreateAttribute(o)));}let name=raw.trim_matches(|c:char|c.is_whitespace()||c=='\\0');Ok(if name=="PlayAnimation" {Some(MotionOperation::Play(play(a)))}else {None})}
pub fn execute(op:&MotionOperation,instance:&mut PlayAnimationInstance,phase:u8,context:&mut PlaybackContext,animation:&mut MotionAnimation)->Result<(),String> {
 match op {MotionOperation::Play(operation)=>match phase {0=>instance.begin(operation,context,animation)?,1=>instance.update(operation,animation)?,_=>instance.end()},MotionOperation::CreateAttribute(o)=>match o.clone() {
'''+execute_arm+'''},MotionOperation::Unsupported=>return Err("Unsupported MotionAnimation operation".into())}Ok(())}
}\n'''
    base+='\n'+(PLUGIN/'Tests/Reference/motion_animation_probe.rs').read_text();reference=output/'motion-animation-oracle.rs';reference.write_text(base)
    simulation=channels.strip_functions(cpp.read_text(),('int main(',));cpp=output/'motion-animation-probe.cpp';cpp.write_text(simulation+'\n'+(PLUGIN/'Tests/Simulation/motion_animation_probe.cpp').read_text())
    report=dict(owner_implementation_sha256=hashlib.sha256(host.encode()).hexdigest(),owner_extractions=records,grab_enum_extractions=[er,ir],factory_source_sha256=hashlib.sha256(nodes.encode()).hexdigest(),riding_source_sha256=hashlib.sha256(riding.encode()).hexdigest(),factory_extractions=factory_records,baseline_extractions=json.loads((output/'channel-extraction-provenance.json').read_text()),callbacks='Original real IntentMap getters, first cached LastAttribute, original AttributeSink and PlaybackService; actual channel preparation, parameters, fades, poses and retained state. Factory adapter invokes verbatim play/transition/AddParam and CreateAttribute arms; no physics dependencies or substituted producer callbacks.',reference_probe_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),simulation_probe_sha256=hashlib.sha256(cpp.read_bytes()).hexdigest())
    (output/'motion-owner-extraction-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return reference,cpp


class Writer(channels.Writer):
    def graph_attributes(self,values):
        self.word(len(values))
        for name,text,word,boolean in values:self.string(name);self.string(text);self.word(word);self.word(boolean)
    def owner_ops(self,ops):
        self.word(len(ops))
        for op,a in ops:
            self.word(op)
            if op==0:
                self.word(a[0] is not None)
                if a[0] is not None:self.word(a[0])
                for v in a[1:]:self.word(v)
            elif op==1:
                self.word(len(a[0]))
                for n in a[0]:self.string(n)
                self.words(a[1])
            elif op==2:self.string(a[0]);self.word(a[1]);self.word(a[2]);self.transition(a[3])
            elif op==3:self.string(a[0]);self.string(a[1]);self.settings(a[2])
            elif op==4:self.string(a[0]);self.string(a[1]);self.settings(a[2]);self.transition(a[3]);self.word(a[4]);self.word(a[5])
            elif op in (6,8):self.word(a[0]);self.word(a[1])
            elif op==9:self.settable(a)
            elif op==10:self.name(a[0]);self.name(a[1])
            elif op in (11,12):self.string(a[0]);self.word(a[1])
            elif op==13:self.string(a[0]);self.name(a[1]);self.word(a[2])
            elif op==14:self.name(a[0]);self.word(a[1])
            elif op in (15,19,31):self.word(a)
            elif op in (20,27):self.name(a)
            elif op==21:self.string(a[0]);self.string(a[1])
            elif op==23:
                self.string(a[0]);self.word(a[1] is not None)
                if a[1] is not None:self.word(a[1]);self.word(a[2])
            elif op==24:self.string(a[0]);self.word(a[1])
            elif op==25:self.tree(a)
            elif op==26:self.attrs(a)
            elif op==28:
                self.word(len(a))
                for name,value in a:self.string(name);self.word(value)
            elif op in (29,30):self.graph_attributes(a)
            elif op==32:
                for v in a[:3]:self.word(v)
                self.name(a[3]);self.word(a[4] is not None)
                if a[4] is not None:self.transition(a[4])


def attr(name,text='',value=0,boolean=0):return (name,text,bits(value),boolean)


def corpus():
    cases=[];rng=random.Random(0x825310f0);parameter=[(trees.name('A'),bits(.731),False,-1),(trees.name('X'),bits(.317),True,-1),(trees.name('Y'),bits(.137),True,-1)]
    hierarchy=(['LEFT','RIGHT','CENTER'],[1,0,2]);names=['CLIP_0','PHASE','BLEND','SELECT','SELECTOR'];channel_names=['LEFT','left','ABCDEFGHIJKLMNOPQRSTUVWXYZ012345_A','ABCDEFGHIJKLMNOPQRSTUVWXYZ012345_B']
    def inspect():return [(7,None),(8,(bits(.01),True)),(22,None),(27,trees.name('A'))]
    def add(ops):s=Writer();s.owner_ops(ops);cases.append(s)
    def initial(flags=0x11223344):return [(0,(flags,1,0,2,2,True,True)),(1,hierarchy),(11,('A',bits(.731))),(12,('X',bits(.317))),(12,('Y',bits(.137)))]
    for index,(main,kind,mirror,keep,priority) in enumerate(itertools.product(names,(1,2,3,4),(False,True),(False,True),(-1,2))):
        flags=0x80000000|(0x40600000 if mirror else 0);ops=initial(flags)+[(9,parameter),(2,(main,bits(.731),bits(.137),trees.transition(kind))), (5,None),*inspect()]
        for i in range(3):ops.append((3,(channel_names[i],names[(index+i)%len(names)],channels.settings(priority=priority,mirrored=bool(i%2),keep=keep,fade_in=.031,fade_out=.173))))
        ops.extend([(13,('A',trees.name('A'),True)),(14,(trees.name('A'),bits(.317))),(15,index%5),(5,None),*inspect()])
        for tick in range(6):
            attrs=[(a,bits(rng.uniform(-.2,1.2)),bool(tick%2),-1) for a,_,_,_ in parameter]
            ops.extend([(16,None),(9,attrs),(5,None),(6,(bits(.031),bits(.137))),*inspect()])
            if tick==1:ops.append((4,(channel_names[0],names[(index+2)%len(names)],channels.settings(priority=99,speed=.731),trees.transition(3),True,True)))
            if tick==2:ops.extend([(23,(channel_names[1],bits(.173),True)),(24,(channel_names[0],bits(.317)))])
            if tick==3:ops.extend([(20,trees.name('B')),(19,bits(.731))])
        ops.extend([(28,[('LEFT',bits(.13)),('left\0tail',bits(.37))]),(18,None),(17,None),*inspect(),(3,('AFTER_RESET','CLIP_1',channels.settings())),(5,None),(6,(bits(.317),bits(.137))),*inspect()]);add(ops)
    # Original stance enum cases and missing flags; resets preserve requested,
    # natural stance, construction, posture and unrelated retained flags.
    for natural,requested,relative,flags in itertools.product((0,1,2,0xffffffff),(0,1,2),(0,7),(None,0,0xffffffff)):
        add([(0,(flags,natural,relative,requested,3,True,True)),(10,(trees.name('X'),trees.name('Y'))),(11,('A',bits(.731))),(12,('X',bits(.317))),(15,2),(18,None),(17,None),(18,None),*inspect()])
    # Actual parsed PlayAnimation+AddParam lifecycle, with immediate source
    # changes, cached duplicate attrs, normalized flags and consumed overrides.
    for transition,variant,source in itertools.product(('play','blend','sequence','channelblend'),range(5),('intent','lastAnim','filteredIntent','unknown')):
        attrs=[attr('name',' \x00PlayAnimation\u2003'),attr('anim','SELECTOR'),attr('switchAnim','PHASE'),attr('mirrorAnim','BLEND'),attr('noBoardAnim','SELECT'),attr('playBackSpeed',value=.731),attr('transType',transition),attr('blendMatchPhase',boolean=255),attr('time',value=.173),attr('applyPosture',boolean=255)]
        param=[attr('from',source),attr('intent','A'),attr('attribute','A'),attr('filteredIntent','X'),attr('rename','X' if variant%2 else ''),attr('normalize',boolean=255),attr('defaultValue',value=.317)]
        cached=[dict(attribute(kind=0,seed=7),name=trees.name('A')),dict(attribute(kind=1,seed=9),name=trees.name('A'))]
        context=((0,1,2)[variant%3],(0,1,2)[(variant+1)%3],(0,1,2)[(variant+2)%3],trees.name('B'),trees.transition(0) if variant==0 else trees.transition(4,seconds=.031) if variant==4 else None)
        ops=initial()+[(26,cached),(29,attrs),(30,param),(30,[attr('from','lastAnim'),attr('attribute','B'),attr('defaultValue',value=.137),attr('normalize',boolean=255)]),(32,context),(31,0),(5,None),(31,1),(5,None),(6,(bits(.031),bits(.137))),*inspect(),(11,('A',bits(.113))),(12,('X',bits(.713))),(31,1),(5,None),*inspect(),(31,2)]
        add(ops)
    # CreateAttribute early return, absent phases, literal zeros, raw booleans,
    # duplicate first lookup and original no-op AddParam on non-Play leaves.
    for mode,set_byte in itertools.product(range(8),(0,1,255)):
        a=[attr('name','CreateAttribute'),attr('attName','A'),attr('set',boolean=set_byte)]
        if mode==0:a+=[attr('always',value=.731),attr('begin',value=.317),attr('update',value=.137),attr('end',value=.113)]
        elif mode!=1:
            for i,n in enumerate(('begin','update','end')):
                if mode&(1<<i):a.append(attr(n,value=.137+i*.317))
        a.append(attr('attName','SHOULD_NOT_WIN'))
        add(initial()+[(2,('PHASE',bits(1),0,trees.transition(1))),(29,a),(30,[attr('from','intent'),attr('intent','A')]),(31,0),(5,None),*inspect(),(31,1),(5,None),*inspect(),(31,2),(5,None),*inspect()])
    add([(21,('TreesFixture','CLIP_'+str(i))) for i in range(4)]+[(21,('Other','CLIP_0')),(21,('TreesFixture','MISSING')),(21,('TreesFixture','PHASE'))])
    # Missing and unrecognized factory names retain the prior live operation.
    add(initial()+[(29,[]),(29,[attr('name','Unsupported')]),(29,[attr('name','CreateAttribute')]),(29,[attr('name',' CreateAttribute ')]),(31,1)])
    return cases


def encoded(cases):return b'ATMOWNER'+len(cases).to_bytes(4,'little')+b''.join(s.data for s in cases)


def fixture_metadata():
    fixture=trees.fixture_metadata()
    payloads=[[bits(.137)],[bits(.454),bits(.317),bits(-.113),bits(.731)],[0,2,bits(0),bits(.731),bits(30),bits(.317)],trees.name('LEFT')+[bits(1.088)]]
    for i,c in enumerate(fixture['clips']):c['attributes'].append(dict(name='ANIMTRANSZ',type_id=i,begin_bits=bits(.731),end_bits=bits(.731),payload_words=payloads[i],source_offset=c['source_offset']+3000))
    validate_fixture_attributes(fixture)
    return fixture


def validate_fixture_attributes(fixture):
    # Mirror the frozen AnimationMetadata::from_file canonical names, source
    # bounds, clip headers and complete attribute order/arity checks before
    # either compiler is launched; also ensure all exercised curves are whole.
    floating=lambda word:struct.unpack('<f',struct.pack('<I',word))[0]
    for clip in fixture['clips']:
        if not re.fullmatch('[A-Z0-9_]{1,36}',clip['name']):raise AssertionError('Invalid canonical fixture clip')
        for field,minimum in [('fps_bits',0),('frames_bits',1),('base_speed_bits',0)]:
            value=floating(clip[field])
            if not math.isfinite(value) or (value<minimum if minimum else value<=0):raise AssertionError('Invalid fixture header')
        previous=clip['source_offset']
        if not previous<fixture['source_bytes']:raise AssertionError('Fixture clip outside bank')
        for attribute in clip['attributes']:
            if not re.fullmatch('[A-Z0-9_]{1,30}',attribute['name']):raise AssertionError('Invalid canonical fixture attribute')
            if not all(math.isfinite(floating(attribute[field])) for field in ['begin_bits','end_bits']):raise AssertionError('Invalid fixture attribute time')
            if not previous<attribute['source_offset']<fixture['source_bytes']:raise AssertionError('Invalid fixture attribute order')
            previous=attribute['source_offset'];kind=attribute['type_id'];words=attribute['payload_words']
            if len(words)<{0:1,1:4,3:6}.get(kind,0):raise AssertionError('Truncated fixture attribute payload')
            if kind==2 and (len(words)<2 or words[1]==0 or len(words)<2+words[1]*2):raise AssertionError('Incomplete exercised fixture curve')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);p.add_argument('--target-dir',required=True,type=Path);args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True);fixture=fixture_metadata();source,cpp=prepare_sources(output);reference=build_probe(output,'motion-animation-reference',source,args.target_dir)
    fixture=fixture_metadata()
    fixture_json=output/'fixture.json';fixture_json.write_text(json.dumps(fixture));fixture_simulation=output/'fixture.skate';fixture_simulation.write_bytes(trees.converter.pack_metadata(fixture))
    live=PLUGIN/'Source/AtelierSkate/Private/Simulation';code=output/'simulation-source';code.mkdir(exist_ok=True);binary=output/'motion-animation-cpp';files=['MotionAnimation.cpp','MotionAnimationOperations.cpp','GraphMotionName.cpp','Graph.cpp','AnimationChannels.cpp','AnimationTrees.cpp','AnimationMetadata.cpp','AnimationPlaybackParameters.cpp','AnimationPlayback.cpp','AnimationName.cpp','AnimationSamples.cpp','SimulationMath.cpp','Intents.cpp']
    for path in list(live.glob('*.h'))+[live/f for f in files]:shutil.copyfile(path,code/path.name)
    probe=code/'motion-animation-probe.cpp';shutil.copyfile(cpp,probe)
    simulation_snapshot={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(code.iterdir()) if p.is_file()}
    (output/'simulation-source-provenance.json').write_text(json.dumps(simulation_snapshot,indent=2)+'\n')
    subprocess.run(['clang++','-std=c++17','-O2','-fno-exceptions','-ffp-contract=off','-Wall','-Wextra','-Werror','-I',str(code),*[str(code/f) for f in files],str(probe),'-o',str(binary)],check=True)
    cases=corpus();commands=encoded(cases);(output/'input.bin').write_bytes(commands)
    def run(exe,path,data):return subprocess.check_output([str(exe),str(path)],input=data)
    expected=run(reference,fixture_json,commands);actual=run(binary,fixture_simulation,commands);(output/'reference.bin').write_bytes(expected);(output/'simulation.bin').write_bytes(actual)
    if actual!=expected:
        lo=0;hi=len(cases)
        while hi-lo>1:
            m=(lo+hi)//2;data=encoded(cases[lo:m])
            if run(reference,fixture_json,data)==run(binary,fixture_simulation,data):lo=m
            else:hi=m
        (output/'first-divergence-input.bin').write_bytes(encoded(cases[lo:hi]));first=next((i for i,(a,e) in enumerate(zip(actual,expected)) if a!=e),min(len(actual),len(expected)))
        raise AssertionError(f'Motion owner differs at byte {first}, case {lo}; isolated command saved')
    result=dict(passed=True,cases=len(cases),output_bytes=len(actual),output_sha256=hashlib.sha256(actual).hexdigest(),comparison='live combined owner, ordered tree/channel progression/parameters/attrs/pose commands, immediate graph side effects, reset/stance, actual PlayAnimation/CreateAttribute factories/parameters/lifecycle with real service callbacks',extraction_provenance_sha256=hashlib.sha256((output/'motion-owner-extraction-provenance.json').read_bytes()).hexdigest(),simulation_source_provenance_sha256=hashlib.sha256((output/'simulation-source-provenance.json').read_bytes()).hexdigest())
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
