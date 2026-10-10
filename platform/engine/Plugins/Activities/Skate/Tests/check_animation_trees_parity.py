#!/usr/bin/env python3
"""Check authored tree construction and persistent simulation tree state exactly.

The Rust oracle includes the untouched frozen core and host builder/selection
modules. Private owner methods and channel-container declarations are extracted
verbatim from the same Git revision, with exact byte boundaries and hashes.
No original implementation file is modified. Run under atelier.safety.
"""
import argparse
from collections import Counter
from functools import lru_cache
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import random
import subprocess
from check_gesture_parity import PLUGIN
from check_animation_playback_parity import Stream,attribute,bits
from reference_build import build_probe
from session_parity import REFERENCE_REVISION

spec=importlib.util.spec_from_file_location('metadata_converter',PLUGIN/'Tools/convert_animation_metadata.py')
converter=importlib.util.module_from_spec(spec);spec.loader.exec_module(converter)


@lru_cache(maxsize=None)
def source_at_reference(relative):
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip())
    path=(PLUGIN/'ThirdParty/skate-runtime'/relative).relative_to(root).as_posix()
    return subprocess.check_output(['git','show',f'{REFERENCE_REVISION}:{path}'],cwd=root).decode('utf-8')


def extract_block(source,marker):
    if source.count(marker)!=1:raise AssertionError(f'Frozen extraction marker must be unique: {marker!r}')
    start=source.index(marker)
    if start and source[start-1]!='\n':raise AssertionError('Extraction must begin at an original line boundary')
    brace=source.index('{',start);depth=1;at=brace+1;string=False;line_comment=False;block_comment=0
    while depth:
        if at>=len(source):raise AssertionError('Unbalanced frozen source extraction')
        c=source[at];next_two=source[at:at+2]
        if line_comment:
            if c=='\n':line_comment=False
        elif block_comment:
            if next_two=='/*':block_comment+=1;at+=1
            elif next_two=='*/':block_comment-=1;at+=1
        elif string:
            if c=='\\':at+=1
            elif c=='"':string=False
        elif next_two=='//':line_comment=True;at+=1
        elif next_two=='/*':block_comment=1;at+=1
        elif c=='"':string=True
        elif c=='{':depth+=1
        elif c=='}':depth-=1
        at+=1
    if source[at:at+1]!='\n':raise AssertionError('Extraction must end before the original line terminator')
    # UTF-8 byte offsets, not Python character positions, define provenance.
    text=source[start:at];raw=text.encode('utf-8');begin=len(source[:start].encode('utf-8'));end=begin+len(raw)
    if source.encode('utf-8')[begin:end]!=raw:raise AssertionError('Extraction boundaries altered source bytes')
    return text,dict(marker=marker,begin=begin,end=end,sha256=hashlib.sha256(raw).hexdigest())


def oracle_source(output):
    host=source_at_reference('crates/skate-host/src/graph_host/motion_animation.rs');channels=source_at_reference('crates/skate-host/src/graph_host/motion_channels.rs')
    methods=[];records=[]
    for marker in ('    fn add_bind_pose(','    pub fn build_tree(','    pub fn advance(','    pub fn apply_parameters(','    pub fn evaluate_pose(','    pub fn refresh_tree_attributes(','    pub fn set_hierarchy('):
        text,record=extract_block(host,marker);methods.append(text);records.append(record)
    suffix='impl MotionAnimation {\n'+'\n'.join(methods)+'\n}\n'
    for marker in ('fn has_transition(','fn prune(','impl PlaybackService for MotionAnimation {'):
        text,record=extract_block(host,marker);suffix+=text+'\n';records.append(record)
    marker='///FakieHeadChannel82BAC778';
    if channels.count(marker)!=1:raise AssertionError('Channel extraction terminator changed')
    prefix=channels[:channels.index(marker)]
    if not prefix.endswith('}\n\n'):raise AssertionError('Channel prefix is not a complete original item sequence')
    suffix+='mod motion_channels {\n'+prefix+'\n}\n'
    path=output/'animation-trees-oracle.rs';path.write_text((PLUGIN/'Tests/Reference/animation_trees_probe.rs').read_text()+'\n'+suffix)
    report=dict(host_source_sha256=hashlib.sha256(host.encode()).hexdigest(),host_extractions=records,
                channels_source_sha256=hashlib.sha256(channels.encode()).hexdigest(),channels_extraction=dict(begin=0,end=len(prefix.encode()),sha256=hashlib.sha256(prefix.encode()).hexdigest()),
                direct_modules=['crates/skate-host/src/graph_host/motion_animation/tree_builder.rs','crates/skate-host/src/graph_host/motion_animation/selection_space_host.rs'],
                dependency_callbacks='MotionIntent, FilteredIntent and LastAttribute trap if invoked; owner AttributeSink uses original core SettableAttributes; actual frozen MotionChannels container is empty in owner fixtures')
    (output/'host-extraction-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return path


def name(text):
    words=[0]*5
    for start in range(0,min(len(text),30),6):
        weight=79235168
        for byte in text[start:start+6].encode():
            digit=byte-86 if byte>=97 else byte-58 if byte>90 else byte-54 if byte>57 else byte-47
            words[start//6]=(words[start//6]+digit*weight)&0xffffffff;weight//=38
    return words


class Writer(Stream):
    def floats(self,values):
        self.word(len(values))
        for value in values:self.word(value)
    def matrix(self,values):
        self.word(len(values))
        for value in values:self.floats(value)
    def transition(self,s):self.word(s['kind']);self.word(s['seconds']);self.word(s['under']);self.word(s['matching']);self.word(s['channels'])
    def construction(self,values):
        self.word(len(values))
        for a,b in values:self.name(a);self.name(b)
    def mirror(self,values):self.construction(values)
    def settable(self,values):
        self.word(len(values))
        for a,value,normalized,sequence in values:self.name(a);self.word(value);self.word(normalized);self.word(sequence)
    def tree(self,t):
        self.word(t['kind'])
        if t['kind']==0:self.string(t['name']);self.clip(t['frames'],t['fps'],t['base'],t['flags'],t['attrs'],t['time'],t['previous'],t['loops'])
        elif t['kind']==1:self.name(t['parameter']);self.children(t['children'])
        elif t['kind']==2:
            self.word(len(t['parameters']))
            for p in t['parameters']:self.name(p)
            self.children(t['children']);self.word(len(t['simplexes']))
            for s in t['simplexes']:self.words(s['children']);self.matrix(s['vertices']);self.matrix(s['normals']);self.floats(s['scales'])
        elif t['kind']==3:
            self.word(len(t['parameters']))
            for p in t['parameters']:self.name(p['name']);self.word(p['mode']);self.word(p['weight']);self.word(p['minimum']);self.word(p['maximum'])
            self.word(len(t['candidates']))
            for c in t['candidates']:self.string(c['name']);self.floats(c['values']);self.tree(c['tree'])
        elif t['kind']==4:self.tree(t['from']);self.tree(t['to']);self.transition(t['settings'])
        else:self.tree(t['motion']);self.word(t['posture']);self.word(t['board']);self.words(t['modes']);self.mirror(t['mirror'])
    def children(self,values):
        self.word(len(values))
        for value in values:self.tree(value)
    def operations(self,values):
        self.word(len(values))
        for op,values in values:
            self.word(op)
            if op in (0,1):self.word(values)
            elif op==2:
                dt,phase,cross,over,remaining=values;self.word(dt);self.word(phase);self.word(cross);self.word(over);self.word(remaining)
            elif op in (3,4):self.settable(values)
            elif op==5:self.word(values[0]);self.word(values[1]);self.word(values[2])
            elif op==6:self.word(values)
            elif op==7:self.name(values[0]);self.word(values[1]);self.attr(values[2])
            elif op==11:self.tree(values[0]);self.transition(values[1])


def transition(kind=2,seconds=0.713,under=0,matching=0,channels=False):return dict(kind=kind,seconds=bits(seconds),under=under,matching=matching,channels=channels)


def clip(index=0,value=0,flags=0x10000000,missing=False):
    attrs=[dict(name=name('A'),kind=0,begin=bits(-1),end=bits(-1),payload=[bits(value)]),dict(name=name('B'),kind=1,begin=bits(0.2),end=bits(0.8),payload=[bits(x) for x in (index+1,-0.0,index/7,1)]),dict(name=name('C'),kind=3,begin=bits(0),end=bits(1),payload=name('LEFT')+[bits(index/3)]),
           dict(name=name('D'),kind=2,begin=bits(-1),end=bits(-1),payload=[0,3,bits(0),bits(0.73+index),bits(30),bits(0.21-index),bits(90),bits(1.37+index)])]
    if missing:attrs=attrs[1:]
    return dict(kind=0,name=f'CLIP_{index}',frames=61+index*7,fps=30+index/3,base=0.731+index/7,flags=flags,attrs=attrs,time=0,previous=0,loops=0)


def simplex(d,indices=None):
    vertices=[[0.0]*d]+[[float(i==j) for j in range(d)] for i in range(d)]
    normals=[[-1.0]*d]+[[float(i==j) for j in range(d)] for i in range(d)]
    return dict(children=list(range(d+1)) if indices is None else indices,vertices=[[bits(v) for v in row] for row in vertices],normals=[[bits(v) for v in row] for row in normals],scales=[bits(1)]*(d+1))


def selection(n=2,duplicates=False):
    parameters=[dict(name=name(chr(88+i)),mode=i%3,weight=bits(0.731+i/7),minimum=bits(-0.5),maximum=bits(1.5)) for i in range(n)]
    candidates=[dict(name='SHARED' if duplicates and i<2 else f'CHILD_{i}',values=[bits((i+1)/(j+2)) for j in range(n)],tree=clip(i,i/3)) for i in range(4)]
    return dict(kind=3,parameters=parameters,candidates=candidates)


def fixture_metadata():
    value=dict(version=1,source_bank='TreesFixture.abin',source_sha256='a'*64,source_bytes=1000000,clips=[],phase_blends=[],blend_spaces=[],selectors=[],selection_spaces=[],unsupported_trees=[])
    for i in range(4):
        c=clip(i,i/3);offset=48+i*4096;attrs=[]
        for j,a in enumerate(c['attrs']):
            attrs.append(dict(name='ABCD'[j],type_id=a['kind'],begin_bits=a['begin'],end_bits=a['end'],payload_words=a['payload'],source_offset=offset+128+j*128))
        value['clips'].append(dict(name=f'CLIP_{i}',source_offset=offset,fps_bits=bits(c['fps']),frames_bits=bits(c['frames']),base_speed_bits=bits(c['base']),flags_word=c['flags'],attributes=attrs))
    value['phase_blends']=[dict(name='PHASE',source_offset=20000,parameter='A',children=['CLIP_3','CLIP_1','CLIP_0','CLIP_2']),dict(name='CYCLE',source_offset=21000,parameter='A',children=['CLIP_0','CYCLE'])]
    value['blend_spaces']=[dict(name='BLEND',source_offset=22000,parameters=['X','Y'],children=['CLIP_0','CLIP_1','CLIP_2','CLIP_3'],simplexes=[dict(children=s['children'],vertex_bits=s['vertices'],normal_bits=s['normals'],scale_bits=s['scales']) for s in [simplex(2),simplex(2,[1,3,2])]])]
    value['selection_spaces']=[dict(name='SELECT',source_offset=24000,parameters=[dict(name='X',mode=2,weight_bits=bits(1),minimum_bits=bits(0),maximum_bits=bits(1))],candidates=[dict(child=f'CLIP_{i}',value_bits=[bits(i/3)]) for i in range(4)])]
    value['selectors']=[dict(name='SELECTOR',source_offset=26000,parameter='Z',default='PHASE',children=['CLIP_2','CLIP_3','SELECT'],values=['B','B','C'])]
    value['unsupported_trees']=[dict(name='UNSUPPORTED',source_offset=28000,type_id=9)]
    return value


def corpus(metadata):
    rng=random.Random(0x46513a6);cases=[];counts=Counter()
    def new(kind):
        s=Writer();s.word(kind);cases.append(s);counts[kind]+=1;return s
    names=sorted({t['name'] for p in sorted((metadata/'decoded').glob('bank-*.json')) for key in ('clips','phase_blends','blend_spaces','selectors','selection_spaces','unsupported_trees') for t in json.loads(p.read_text()).get(key,[])})
    # Every authored effective tree is built with the actual original reader;
    # snapshots include every duplicate candidate/child and clip header state.
    for tree_name in names+['MISSING_ANIMATION','bad-name']:
        s=new(1);s.string(tree_name.lower());s.construction([]);s.word(0)
    params=[(name(chr(65+i)),bits(0.731),False,-1) for i in range(4)]+[(name(chr(88+i)),bits(0.25),False,-1) for i in range(4)]
    def ops(extra=()):
        values=[(6,15),(7,(name('A'),15,attribute(kind=3,seed=7))),(9,None),(4,params),(3,params),(1,bits(0.731)),(0,bits(0.123)),(5,(bits(0.01),True,True)),(6,15),(7,(name('B'),31,attribute(kind=3,seed=9)))]+list(extra)
        for i in range(12):
            attrs=[(n,bits(rng.uniform(-0.2,1.2)),bool(i%2),-1) for n,_,_,_ in params]
            values.extend([(2,(bits(0.731/30),bits(rng.uniform(-0.2,1.2)),True,bits(17),bits(19))),(3,attrs),(5,(bits((0,0.01,0.1)[i%3]),bool(i%2),i%3!=0)),(6,(0,15,31)[i%3]),(7,(name('A'),15,attribute(kind=3,seed=i))), (8,None)])
        values.extend([(10,None),(5,(bits(0.031),False,True))]);return values
    trees=[]
    for flags in (0,0x10000000,0x40000000,0x50000000):trees.append(clip(0,0.731,flags))
    for missing in (False,True):
        trees.append(dict(kind=1,parameter=name('A'),children=[clip(3,1),clip(0,0,missing=missing),clip(1,0.5),clip(2,0.5)]))
    for d in range(1,5):trees.append(dict(kind=2,parameters=[name(chr(88+i)) for i in range(d)],children=[clip(i,i/7) for i in range(d+2)],simplexes=[simplex(d),simplex(d,list(range(1,d+2)))]))
    for n,duplicates in itertools.product(range(4),(False,True)):trees.append(selection(n,duplicates))
    for kind,matching,seconds in itertools.product((2,3,4),range(4),(0,0.031,0.05,0.713)):
        trees.append(dict(kind=4,**{'from':clip(0,0),'to':clip(2,0.5)},settings=transition(kind,seconds,matching=matching,channels=bool(matching%2))))
    for profile,board,modes in itertools.product(range(5),(False,True),([], [1], [2], [1,2])):
        trees.append(dict(kind=5,motion=clip(2,0.5),posture=profile,board=board,modes=modes,mirror=[(name('LEFT'),name('RIGHT')),(name('RIGHT'),name('LEFT'))]))
    # Nested graphs cover cull-driven disabled commits, parameter forwarding,
    # selected-only preparation versus all-candidate prune, and partial misses.
    trees.extend([dict(kind=1,parameter=name('A'),children=[selection(1),clip(0,0.1)]),
                  dict(kind=2,parameters=[name('X')],children=[selection(1),clip(1,0.5)],simplexes=[simplex(1)]),
                  dict(kind=3,parameters=selection(1)['parameters'],candidates=[dict(name='A',values=[bits(0)],tree=dict(kind=4,**{'from':clip(0,0),'to':clip(1,0.1)},settings=transition(seconds=-0.01))),dict(name='B',values=[bits(1)],tree=clip(2,0.5))])])
    for tree in trees:
        s=new(2);s.tree(tree);s.operations(ops())
    for invalid in (dict(kind=1,parameter=name('A'),children=[clip()]),dict(kind=2,parameters=[],children=[clip()],simplexes=[]),dict(kind=3,parameters=[],candidates=[])):
        s=new(2);s.tree(invalid);s.word(0)
    # Requests exercise current clearing on failed kind1 builds, source cycles,
    # posture clearing before failed outer bind, and nested under transitions.
    for profile,bank,flags,mirror_present in itertools.product(range(5),(False,True),(None,0,0x40000000,0x00400000,0x00600000,0xc0400000),(False,True)):
        s=new(3);s.construction([(name('Z'),name('B'))]);s.mirror([(name('LEFT'),name('RIGHT')),(name('RIGHT'),name('LEFT'))] if mirror_present else [])
        s.word(flags is not None)
        if flags is not None:s.word(flags)
        s.word(profile);s.word(True);s.word(bank);steps=[]
        for request_kind,anim,start,under,matching in ((2,'CLIP_0',0.731,0,0),(3,'PHASE',0.123,0,2),(2,'BLEND',0,1,3),(4,'SELECT',0.25,1,0),(1,'CYCLE',0,0,0),(1,'SELECTOR',0.5,0,0),(7,'UNSUPPORTED',0,0,0),(1,'MISSING',0,0,0)):
            steps.extend([(0,(anim,bits(0.731),bits(start),transition(request_kind,under=under,matching=matching))),(2,params),(1,(bits(0.031),bits(0.25))),(3,(bits(0.01),True)),(4,None)])
        s.word(len(steps))
        for op,values in steps:
            s.word(op)
            if op==0:s.string(values[0]);s.word(values[1]);s.word(values[2]);s.transition(values[3])
            elif op==1:s.word(values[0]);s.word(values[1])
            elif op==2:s.settable(values)
            elif op==3:s.word(values[0]);s.word(values[1])
    for profile in (0,1,2,3,4,0xffffffff):
        s=new(4);values=[(0,profile),(1,True),(2,False),(2,True),(0,2),(2,True),(1,True),(2,True),(1,False),(0,3),(2,False)]
        s.word(len(values))
        for op,value in values:s.word(op);s.word(value)
    return cases,dict(counts)


def encoded(cases):return b'ATTREES1'+len(cases).to_bytes(4,'little')+b''.join(s.data for s in cases)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--metadata',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--target-dir',required=True,type=Path)
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True);metadata=args.metadata.resolve()
    source=oracle_source(output);reference=build_probe(output,'animation-trees-reference',source,args.target_dir)
    fixture=fixture_metadata();fixture_json=output/'fixture.json';fixture_json.write_text(json.dumps(fixture));fixture_simulation=output/'fixture.skate';fixture_simulation.write_bytes(converter.pack_metadata(fixture))
    code=PLUGIN/'Source/AtelierSkate/Private/Simulation';binary=output/'animation-trees-cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-fno-exceptions','-ffp-contract=off','-Wall','-Wextra','-Werror','-I',str(code),str(code/'AnimationTrees.cpp'),str(code/'AnimationMetadata.cpp'),str(code/'AnimationPlaybackParameters.cpp'),str(code/'AnimationPlayback.cpp'),str(code/'AnimationName.cpp'),str(code/'AnimationSamples.cpp'),str(code/'SimulationMath.cpp'),str(PLUGIN/'Tests/Simulation/animation_trees_probe.cpp'),'-o',str(binary)],check=True)
    cases,counts=corpus(metadata);commands=encoded(cases);(output/'input.bin').write_bytes(commands)
    def run(exe,paths,data):return subprocess.check_output([str(exe)]+[str(p) for p in paths],input=data)
    originals=[metadata/'decoded/bank-0.json',metadata/'decoded/bank-1.json',fixture_json];binaries=[metadata/'simulation/bank-0.skate',metadata/'simulation/bank-1.skate',fixture_simulation]
    expected=run(reference,originals,commands);actual=run(binary,binaries,commands);(output/'reference.bin').write_bytes(expected);(output/'simulation.bin').write_bytes(actual)
    if actual!=expected:
        lo=0;hi=len(cases)
        while hi-lo>1:
            middle=(lo+hi)//2;data=encoded(cases[lo:middle]);e=run(reference,originals,data);a=run(binary,binaries,data)
            if a==e:lo=middle
            else:hi=middle
        (output/'first-divergence-input.bin').write_bytes(encoded(cases[lo:hi]));first=next((i for i,(a,e) in enumerate(zip(actual,expected)) if a!=e),min(len(actual),len(expected)))
        raise AssertionError(f'Animation trees differ at byte {first}, case {lo}; isolated command saved')
    result=dict(passed=True,comparison='every authored tree, complete recursive clock state, commands, attributes, partial outputs, ownership and errors',cases=len(cases),case_types=counts,
                output_bytes=len(actual),output_sha256=hashlib.sha256(actual).hexdigest(),host_extraction_sha256=hashlib.sha256((output/'host-extraction-provenance.json').read_bytes()).hexdigest(),owner_channels='empty actual original container; channel integration remains separate')
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
