#!/usr/bin/env python3
"""Exact full-host bridge world construction and four-device input histories.

Root exclusively compiles/executes. --preflight only archives/stages unchanged
source, checks protocol and records hashes. Triangle/rail/platform samples are
explicit external inputs; actual collision_map, collision compiler, static grind
provider, controller/cache/Pad/action owner bodies execute unchanged. This proof
does not establish session/global frame or live operating-system polling parity.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
import math
from pathlib import Path
import random
import re
import shutil
import struct
import subprocess
from camera_reference_build import frozen_sources
from session_parity import PLUGIN, REFERENCE_REVISION, digest

CODE=PLUGIN/'Source/AtelierSkate/Private/Native'
UNITS=('NativeMath','Geometry','GeometrySweep','GeometryFeatures','GeometryPrism',
       'GeometryTriangleFixup','WorldPrimitiveContact','ContactRetention',
       'WorldContactProducer','WorldGeometry','PlayerGrindInputWorld','Input',
       'ControllerInputRuntime','GameplayWorld')
OWNED=(PLUGIN/'Tests/Native/gameplay_world_input_probe.cpp',
       PLUGIN/'Tests/Reference/gameplay_world_input_probe.rs',
       PLUGIN/'Tests/Reference/gameplay_world_input_observer.rs',Path(__file__))
WORLD_OPS={0:'build',1:'query',2:'contacts',3:'clear',4:'observe'}
INPUT_OPS={0:'collect',1:'publish',2:'discard',3:'sample',4:'counter_boundary',5:'observe'}
FRIEND='    friend struct GameplayWorldInputObserver; // test snapshot access only\n'


def bits(v):
    if isinstance(v,dict):return v['bits']
    try:return struct.unpack('<I',struct.pack('<f',v))[0]
    except OverflowError:return 0xff800000 if v<0 else 0x7f800000

def value(w):return struct.unpack('<f',struct.pack('<I',w))[0]
def fs(v):return [bits(x)for x in v]
def wide(v):return [v&0xffffffff,(v>>32)&0xffffffff]
def flatten(rows):return [v for row in rows for v in row]


def encode_snapshot(snapshot):
    out=[len(snapshot['triangles'])]
    for t in snapshot['triangles']:out+=fs(flatten(t))
    out += [len(snapshot['rails'])]
    for rail in snapshot['rails']:out+=[len(rail)]+fs(flatten(rail))
    return out


def xbox(buttons=0,triggers=(0,0),left=(0,0),right=(0,0)):
    return [buttons,*triggers,*[v&0xffffffff for v in(*left,*right)]]


def packet(number=0,subtype=1,**kwargs):return [0,number&0xffffffff,*xbox(**kwargs),subtype]
def error(kind=1,code=0):return [kind,code]
def encode_samples(samples):
    assert len(samples)==4
    return flatten(samples)


def basis(angle=0):
    c,s=math.cos(angle),math.sin(angle)
    return [c,0.,-s,0.,1.,0.,s,0.,c]


def volume(kind=0,center=(0.,.05,0.),body=0,radius=.1,angle=0.,velocity=(0.,0.,0.),material=(.2,.1,.8)):
    if kind==0:p=[0]+fs([*center,radius])
    elif kind==1:p=[1]+fs([*center,*basis(angle)[:3],.25,radius])
    elif kind==2:p=[2]+fs([-.3,0.,-.12,0.,0.,.12,.3,0.,-.12,radius,1.,1.,1.])+[0xe0]+fs([*basis(angle),*center])
    else:p=[3]+fs([*center,*basis(angle),.3,.05,.12,radius])
    return [body]+p+fs([*velocity,*material])


def contact(volumes,capacity=100,threshold=1.e-6,deferred=False,padding=0.,maximum=.1,is_object=False):
    return [2,len(volumes)]+flatten(volumes)+fs([padding,maximum,.95,.0001])+[is_object,capacity,bits(threshold),deferred]


def query(start=(.2,1.,.2),end=(.2,-1.,.2),radius=.03,bounds=None,grind_min=(-10.,-10.,-10.),grind_max=(10.,10.,10.)):
    return [1]+fs([*start,*end,radius])+[bounds is not None]+fs(bounds or [0.]*6)+fs([*grind_min,*grind_max])


def build(snapshot,material=(.731,.517,.137)):
    return [0]+fs(material)+encode_snapshot(snapshot)


def floor(size=2.,height=0.,offset=0.):
    p=[[-size+offset,height,-size],[size+offset,height,-size],[size+offset,height,size],[-size+offset,height,size]]
    return [[p[n]for n in ids]for ids in((0,2,1),(0,3,2))]


def corpus():
    rng=random.Random(0x4957344c);cases=[]
    def add(kind,label,commands,**metadata):
        cases.append(dict(index=len(cases),kind=kind,label=label,commands=commands,operations=[c[0]for c in commands],**metadata))
    valid=dict(triangles=floor(),rails=[[[0.,.2,-2.],[0.,.2,2.]]])
    # Empty/success/late-failure/replacement retain exactly the caller's previous
    # PreparedCollision, never the partly built collision or a seeded provider.
    add(0,'actual bridge retained build success/failure/clear',[
        [4],query(),contact([]),build(dict(triangles=[],rails=[])),query(),contact([]),
        build(valid),query(),contact([volume(k,body=k)for k in range(4)]),
        build(dict(triangles=floor(),rails=[[]])),query(),
        build(dict(triangles=floor(height=.317),rails=[[[0.,0.,0.]]])),
        build(dict(triangles=[[[0.,0.,0.]]*3],rails=[])),query(),
        build(dict(triangles=floor(height=.1),rails=[])),contact([volume()]),[3],query(),[4]])
    # Non-manifold reverse incidents include several equal coplanar maxima;
    # later authored ties and welding thresholds must retain source ordering.
    base=[[0.,0.,0.],[0.,0.,2.],[2.,0.,0.]]
    neighbors=[[[0.,0.,2.],[0.,0.,0.],[-2.,0.,0.]],
               [[0.,0.,2.],[0.,0.,0.],[0.,2.,0.]],
               [[0.,0.,2.],[0.,0.,0.],[-3.,0.,0.]],
               [[0.,0.,2.],[0.,0.,0.],[-2.,-.0317,0.]]]
    for n in range(24):
        order=list(neighbors);rng.shuffle(order)
        triangles=[base,*order]
        if n%3==1:triangles=list(reversed(triangles))
        if n%3==2:triangles+=[copy.deepcopy(base)]
        add(0,'non-manifold reverse edge and last-equal coplanar tie',[
            build(dict(triangles=triangles,rails=[])),query(start=(0.,1.,1.),end=(0.,-1.,1.)),
            contact([volume(k,(0.,.05,1.),body=k)for k in range(4)],threshold=0.)])
    # First-seen welded coordinates affect adjacency only. All narrow original
    # contact vertices must survive even when their welding IDs are equal.
    for width in (value(0x37800000),.00001,.00049,.0005,.00051,.000999, .001,.001001):
        for sign in(-1,1):
            triangles=[[[0.,0.,0.],[0.,0.,2.],[sign*width,0.,0.]],
                       [[0.,0.,2.],[0.,0.,0.],[-1.,0.,0.]]]
            add(0,'welded narrow face keeps original vertices',[
                build(dict(triangles=triangles,rails=[])),query(start=(sign*width*.2,1.,.2),end=(sign*width*.2,-1.,.2)),
                contact([volume(0,(0.,.02,.5),radius=.03)])],width_bits=bits(width))
    for boundary in(value(bits(.0005)-1),value(bits(.0005)),value(bits(.0005)+1)):
        triangles=floor(size=.01)
        triangles += [[[boundary,0.,0.],[-boundary,0.,.01],[.01,0.,0.]]]
        add(0,'f64 one-mm welding midpoint and signed coordinates',[build(dict(triangles=triangles,rails=[])),query()])
    # Portable cluster partition thresholds and independent spatial/source order.
    for count in(1,63,64,65,127,128,129,1024):
        triangles=[]
        for n in range(count):
            x=((n*37)%max(1,count))*.317;y=(n%3)*.0137;z=(n%11)*.731
            triangles.append([[x,y,z],[x,y,z+.25],[x+.25,y,z]])
        queries=[query(start=(x,.5,z),end=(x,-.5,z),bounds=[x-.1,-1.,z-.1,x+.1,1.,z+.1])for x,z in((.001,.001),(1.,1.),(10.,10.),(300.,6.))]
        add(0,'cluster64 boundary and shuffled authored broadphase',[
            build(dict(triangles=triangles,rails=[])),*queries,contact([volume(0,(.05,.1,.05))])],triangles=count)
    # Split imported floors, open ledges, buried sides and partial continuations.
    left=[[[-2.,0.,-2.],[0.,0.,2.],[0.,0.,-2.]],
          [[-2.,0.,-2.],[-2.,0.,2.],[0.,0.,2.]]]
    right=[[[0.,0.,-2.],[0.,0.,2.],[2.,0.,2.]],
           [[0.,0.,-2.],[2.,0.,2.],[2.,0.,-2.]]]
    sides=[[[0.,-1.,-1.],[0.,0.,-1.],[0.,0.,1.]],
           [[0.,-1.,-1.],[0.,0.,1.],[0.,-1.,1.]]]
    for mode in('joined','open','buried','raised','partial','split'):
        triangles=copy.deepcopy(left if mode=='open'else left+right[:1]if mode=='partial'else left+right)
        if mode in('buried','raised'):triangles += [[[x,y+(.2 if mode=='raised'else 0),z]for x,y,z in t]for t in sides]
        if mode=='split':
            for t in triangles[2:]:
                for p in t:p[0]+=.000001
        cmds=[build(dict(triangles=triangles,rails=[]))]
        for x in(-.1,-.05,0.,.05,.1):
            for z in(-1.1,-.5,0.,.5,1.1):
                cmds.append(contact([volume(k,(x,.05,z),body=k,radius=.1)for k in(0,1,3)],threshold=0.,deferred=(x==0.)))
        cmds += [contact([],capacity=0),contact([volume()],capacity=1),query()]
        add(0,'concrete imported floor contacts '+mode,cmds,seam_mode=mode)
    # Full independent triangle arithmetic scales/orientation, without a ported
    # expected normal or edge cosine in the generator.
    for n in range(128):
        scale=rng.choice((.0001,.01,.1,1.,10.,100.,10000.,1.e7))
        triangles=[[[rng.uniform(-4,4)*scale for _ in range(3)]for _ in range(3)]for j in range(1+n%9)]
        if n%4==0:triangles +=copy.deepcopy(triangles[:1])
        center=[sum(p[a]for p in triangles[0])/3 for a in range(3)]
        add(0,'independent finite rotated triangles and material words',[
            build(dict(triangles=triangles,rails=[]),tuple(rng.uniform(-1,2)for _ in range(3))),
            query(start=[center[0],center[1]+scale,center[2]],end=[center[0],center[1]-scale,center[2]],radius=.03*scale),
            contact([volume(n%4,center,body=(0,1,2,3,4,5,6,8,9,10,11,12,13,14,15)[n%15],radius=.01*scale)],capacity=(0,1,4,50,100)[n%5],deferred=n%2==1)])
    # Degenerate/overflow/nonfinite rejection and its earlier retained world.
    for exp in(-40,-30,-20,-10,0,10,15,18,19,20,30,38):
        s=10.**exp
        for vertices in([[[0.,0.,0.],[s,0.,0.],[0.,s,0.]]],
                         [[[s,0.,0.],[s,1.,0.],[s,0.,1.]]],
                         [[[0.,0.,0.],[s,0.,0.],[s*.5,0.,0.]]]):
            add(0,'long/tiny/degenerate face rejects without lost previous output',[
                build(valid),build(dict(triangles=vertices,rails=[])),query(),contact([volume()])])
    for exp in(20,24,28,32,36,38):
        length=10.**exp;width=10.**(12-exp)
        triangles=[[[0.,-0.,0.],[length,0.,0.],[length,width,0.]]]
        add(0,'finite host normal then recovered volume rejection with exact source points',[
            build(valid),build(dict(triangles=triangles,rails=[])),query()])
    for word in(0x7f800000,0xff800000,0x7fc12345,0xffc12345,0x7f812345,0xff812345):
        for lane in range(9):
            triangles=copy.deepcopy(floor());triangles[0][lane//3][lane%3]={'bits':word}
            add(0,'nonfinite authored coordinate and retained construction prefix',[
                build(valid),build(dict(triangles=triangles,rails=[])),query()],exception_word=word,lane=lane)
    # Authored cubics are decoded by the real spline owner. Tiny/duplicate knots
    # are retained; coefficient rounding can differ from source endpoint bits.
    rails=[[[0.,0.,0.],[0.,0.,0.]],[[0.,0.,0.],[0.,1.,0.]],
           [[0.,0.,0.],[0.,.1,value(0x37800000)]],
           [[.137,.317,-.731],[.731,.137,.317],[.731,.137,.317]],
           [[-0.,-0.,-0.],[0.,0.,0.],[-0.,-0.,-0.]]]
    for n in range(96):
        count=2+n%12;scale=rng.choice((.0000001,.001,.137,1.,10000.,1.e10))
        r=[[rng.uniform(-3,3)*scale for _ in range(3)]for j in range(count)]
        if n%5==0:r[1]=copy.deepcopy(r[0])
        rr=[copy.deepcopy(rails[n%len(rails)]),r]
        if n%4==0:rr.append(copy.deepcopy(r))
        add(0,'actual authored cubic chord rounding/GUID/duplicate/tiny rails',[
            build(dict(triangles=floor(),rails=rr)),query(),query(grind_min=(-.2,-.2,-.2),grind_max=(.2,.2,.2)),
            query(grind_min=(0.,0.,0.),grind_max=(0.,0.,0.)),
            query(grind_min=(value(0x37800000),)*3,grind_max=(0.,)*3)])
    dense=[[[float(n%8)*.03,float((n//8)%8)*.02,float(n//64)*.04],[float(n%8)*.03+.0137,float((n//8)%8)*.02,float(n//64)*.04+.0173]]for n in range(192)]
    add(0,'native grind octree cap40 and authored query ordering',[
        build(dict(triangles=floor(),rails=dense)),query(),query(grind_min=(.06,0.,.03),grind_max=(.18,.13,.09)),
        query(grind_min=(-1.,-1.,-1.),grind_max=(1.,1.,1.)),query(grind_min=(9.,9.,9.),grind_max=(10.,10.,10.))])
    for rail in([],[[0.,0.,0.]],[[0.,0.,0.],[1.e38,0.,0.]],[[0.,0.,0.],[1.e20,0.,0.]]):
        add(0,'rail early data/chord failures preserve previous prepared',[build(valid),build(dict(triangles=floor(),rails=[rail])),query()])
    for word in(0x7f800000,0xff800000,0x7fc12345,0xff812345):
        for point in(0,1):
            rail=[[.137,.317,-.731],[.731,.137,.317]];rail[point][point]={'bits':word}
            add(0,'nonfinite authored spline payload failure',[build(valid),build(dict(triangles=floor(),rails=[rail])),query()])
    for later in([],[[0.,0.,0.]],[[0.,0.,0.],[1.e38,0.,0.]],
                 [[0.,0.,0.],[{'bits':0x7fc12345},0.,0.]]):
        rr=[[[0.,0.,0.],[1.e20,0.,0.]],copy.deepcopy(later)]
        add(0,'whole spline coefficient validation precedes any chord decode error',[
            build(valid),build(dict(triangles=floor(),rails=rr)),query()])
    add(0,'uint16 rail table count rejection precedes malformed individual rails',[build(valid),build(dict(triangles=[],rails=[[]for _ in range(65536)])),query()])
    too_many=[[float(n%256)*.01,0.,float(n//256)*.01]for n in range(65537)]
    add(0,'native octree entry capacity after complete authored cubic decoding',[build(valid),build(dict(triangles=[],rails=[too_many])),query()])
    # Line/grind bounds rejection paths come from the actual world/provider.
    queries=[]
    for word in(0,0x80000000,bits(-.1),0x7f800000,0x7fc12345):
        queries.append(query(radius={'bits':word}))
    queries += [query(start=({'bits':0x7fc12345},1.,0.)),query(bounds=[1.]*3+[-1.]*3),
                query(grind_min=({'bits':0x7fc12345},0.,0.)),query(grind_min=(1.,1.,1.),grind_max=(-1.,-1.,-1.))]
    add(0,'actual query invalid domains with prepared owner retained',[build(valid),*queries])
    # Four real devices, no duplicate-packet suppression. Source queue wraps
    # after30 collect calls; no-fresh drain still increments tick and preserves
    # the last published mapped-action array.
    levels=(-32768,-24576,-8193,-8192,-8191,-1,0,1,8191,8192,8193,24576,32767)
    for seed in range(32):
        cmds=[[5],[1],[1]]
        for n in range(144):
            batch=[]
            for d in range(4):
                if (n+d+seed)%11==0:batch.append(error(1+(n+d)%4,0 if(n+d)%4 in(0,3)else(5,1167,0xffffffff)[n%3]))
                else:batch.append(packet(number=(0,1,1,0xffffffff,0)[n%5],subtype=(1,7,7,0,255,2)[(n+d)%6],
                    buttons=(1<<((n//4+d)%16))|((0x0101,0x0102,0x1000,0xf3cf)[(n+seed)%4]),
                    triggers=((0,1,127,128,254,255)[n%6],(0,255,128)[(n+d)%3]),
                    left=(levels[(n+d)%len(levels)],levels[(n//2+d+seed)%len(levels)]),
                    right=(levels[(n//3+d)%len(levels)],levels[(n+2*d)%len(levels)])))
            cmds.append([0,*encode_samples(batch)])
            if n%(2+seed%7)==0 or n in(29,59,143):cmds.append([1])
            if n in(20,60,100):cmds += [[1],[1],[5]]
            if n in(45,95):cmds.append([2])
        cmds += [[1],[1],[2],[5],[1]]
        add(1,'four-device repeat/reconnect/subtype7/raw/cache/latest ring histories',cmds,seed=seed)
    for bursts in(29,30,31,59,60,61,89,90,91):
        cmds=[[0,*encode_samples([packet(buttons=0x1000),error(),error(),error()])],[1]]
        cmds += [[0,*encode_samples([packet(number=7,buttons=0x0103,subtype=7),error(),error(),error()])]for _ in range(bursts)]
        cmds += [[1],[1],[5],[2],[1]]
        add(1,'complete ring overwrite and exact multiple30 emptiness',cmds,burst=bursts)
    for device in range(4):
        cmds=[]
        for n in range(112):
            samples=[error()for _ in range(4)];samples[device]=packet(number=11,subtype=7 if n%3==0 else 1,buttons=0x0100|(1 if n<56 else 2),triggers=(255,255),left=(-32768,32767),right=(32767,-32768))
            cmds += [[0,*encode_samples(samples)],[1]]
        cmds += [[0,*encode_samples([error(2,0xdeadbeef)]*4)],[1],[1],[5]]
        add(1,'device priority/action map/session marker/repeat edges',cmds,device=device)
    for n in range(8):
        maximum=0xffffffffffffffff
        cmds=[[4,*wide(maximum-2+n%2),*wide(maximum-2),*wide(maximum-2)]]
        for k in range(8):cmds += [[3,*xbox(buttons=(1<<k)|0x0100,triggers=(k*31,255),left=(-32768,32767))],[1]]
        cmds += [[2],[5],[1]]
        add(1,'only tick/publication/consumption counters seeded at wrap boundary',cmds)
    return (*encode(cases),cases)


def encode(cases):
    records=[];ranges=[];at=4
    for c in cases:
        words=[c['kind'],len(c['commands'])]+flatten(c['commands']);raw=struct.pack('<'+'I'*len(words),*[int(v)&0xffffffff for v in words]);records.append(raw);ranges.append(dict(index=c['index'],offset=at,bytes=len(raw)));at+=len(raw)
    return struct.pack('<I',len(cases))+b''.join(records),ranges


class Cursor:
    def __init__(self,words,labels=False):self.words=words;self.at=0;self.labels=[]if labels else None
    def take(self,n,label):
        out=self.words[self.at:self.at+n];assert len(out)==n,(label,self.at,n,len(self.words));self.at+=n
        if self.labels is not None:self.labels.extend([label if n==1 else label+'['+str(j)+']'for j in range(n)])
        return out
    def word(self,label):return self.take(1,label)[0]
    def wide(self,label):v=self.take(2,label);return v[0]|(v[1]<<32)
    def text(self,label):n=self.word(label+'.bytes');return bytes(self.take(n,label+'.utf8')).decode()
    def status(self,label):return self.word(label+'.ok'),self.text(label+'.error')
    def finish(self):assert self.at==len(self.words),(self.at,len(self.words))


def validate_protocol(raw,ranges,cases):
    counts=Counter();seen=[]
    for c,r in zip(cases,ranges):
        w=struct.unpack('<'+'I'*(r['bytes']//4),raw[r['offset']:r['offset']+r['bytes']]);i=Cursor(w)
        assert i.word('kind')==c['kind'];assert i.word('commands')==len(c['commands'])
        for cmd in c['commands']:
            start=i.at;op=i.word('op');counts[('world_'if c['kind']==0 else'input_')+(WORLD_OPS if c['kind']==0 else INPUT_OPS)[op]]+=1
            if c['kind']==0:
                if op==0:
                    i.take(3,'material');n=i.word('triangles');i.take(n*9,'vertices');n=i.word('rails')
                    for _ in range(n):p=i.word('points');i.take(p*3,'points')
                elif op==1:i.take(3+3+1+1+6+6,'query')
                elif op==2:
                    n=i.word('volumes')
                    for _ in range(n):
                        i.word('body');kind=i.word('primitive');i.take((4,8,26,16)[kind],'primitive');i.take(6,'velocity_material')
                    i.take(8,'settings')
            else:
                if op==0:
                    for _ in range(4):
                        kind=i.word('sample');i.take(9 if kind==0 else 1,'packet/error')
                elif op==3:i.take(7,'xbox')
                elif op==4:i.take(6,'counters')
            assert list(w[start:i.at])==[int(v)&0xffffffff for v in cmd],(c['index'],op,start,i.at,len(cmd))
        i.finish();seen.append(w)
    restored=struct.pack('<I',len(cases))+b''.join(struct.pack('<'+'I'*len(w),*w)for w in seen)
    assert restored==raw
    for kind,ops in((0,WORLD_OPS),(1,INPUT_OPS)):
        for op in ops:assert counts[('world_'if kind==0 else'input_')+ops[op]]>0
    return dict(counts)


def observer_sections():
    text=OWNED[2].read_text();out={}
    for name in('BRIDGE','INPUT','CONTROLLERS','CORE_HISTORY','CORE_WORLD'):
        begin='// BEGIN '+name+'\n';end='// END '+name+'\n'
        assert text.count(begin)==text.count(end)==1
        out[name]=text.split(begin,1)[1].split(end,1)[0].encode()
    return out


def stage_reference(output,target,*,compile=False):
    source,report=frozen_sources(output);observed=output/'observed-source'
    if observed.exists():shutil.rmtree(observed)
    shutil.copytree(source,observed);crate=observed/'atelier-host';host=source/'crates/skate-host/src';sections=observer_sections()
    extensions={'physics/bridge.rs':sections['BRIDGE'],'input.rs':sections['INPUT'],'input/controllers.rs':sections['CONTROLLERS']};staged={}
    for original in sorted(host.rglob('*.rs')):
        rel=original.relative_to(host).as_posix()
        if rel in('lib.rs','main.rs'):continue
        raw=original.read_bytes();extra=b'\n'+extensions[rel]if rel in extensions else b'';p=crate/'src'/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw+extra)
        assert p.read_bytes()[:len(raw)]==raw
        staged[rel]=dict(original_prefix_bytes=len(raw),original_prefix_sha256=digest(original),append_sha256=hashlib.sha256(extra).hexdigest(),generated_sha256=digest(p))
    core={'crates/skate-core/src/input/history.rs':sections['CORE_HISTORY'],'crates/skate-core/src/physics/board_world.rs':sections['CORE_WORLD']}
    for rel,extra in core.items():p=observed/rel;p.write_bytes((source/rel).read_bytes()+b'\n'+extra)
    shutil.copy2(OWNED[1],crate/'src/migration_probe.rs');cargo=crate/'Cargo.toml'
    cargo.write_text(cargo.read_text()+'''\nskate-core={path="../crates/skate-core"}
skate-data={path="../crates/skate-data"}
skate-net={path="../crates/skate-net"}
half="2.7.1"
bevy={version="0.19",default-features=false,features=["std","multi_threaded","bevy_log"]}
[[bin]]
name="gameplay-world-input-reference"
path="src/migration_probe.rs"
''')
    if compile:subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(cargo),'--target-dir',str(target.resolve()),'--bin','gameplay-world-input-reference'],check=True)
    for rel,sha in report['original_source_sha256'].items():assert digest(source/rel)==sha and(observed/rel).read_bytes()[:len((source/rel).read_bytes())]==(source/rel).read_bytes(),rel
    for rel,row in staged.items():assert digest(crate/'src'/rel)==row['generated_sha256'],rel
    binary=output/'gameplay-world-input-reference'
    if compile:shutil.copy2(target.resolve()/'release/gameplay-world-input-reference',binary)
    report.update(staged_host_original_prefixes=staged,appended_core_observers={rel:dict(original_prefix_bytes=(source/rel).stat().st_size,original_prefix_sha256=digest(source/rel),generated_sha256=digest(observed/rel),append_sha256=hashlib.sha256(b'\n'+extra).hexdigest())for rel,extra in core.items()},probe_sha256=digest(OWNED[1]),observer_sha256=digest(OWNED[2]),binary_sha256=digest(binary)if compile else None,scope='Whole unchanged original bridge/collision compiler/grind provider/controller/platform bodies. Appends contain private read forwarding and explicit raw triangle/rail/sample/counter inputs only. No extracted production algorithm, seeded geometry/contact/query result, normalized error or surrogate callback.')
    (output/'reference-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return binary,report


def header_closure():
    seen=set();pending=[CODE/(u+'.cpp')for u in UNITS]+[OWNED[0]]
    while pending:
        p=pending.pop()
        for name in re.findall(r'^#include "([^"]+)"',p.read_text(),re.M):
            if name in seen:continue
            q=CODE/name;assert q.is_file(),(p,name);seen.add(name);pending.append(q)
    return sorted(seen)


def add_friend(raw,name):
    marker='class '+name+'\n{\n';assert raw.count(marker)==1,(name,raw.count(marker))
    staged=raw.replace(marker,marker+FRIEND,1);assert staged.replace(FRIEND,'')==raw
    return staged


def stage_native(output,*,compile=False):
    snapshot=output/'native-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir();hashes={};adapters={}
    for name in[*header_closure(),*[u+'.cpp'for u in UNITS]]:
        p=CODE/name;shutil.copy2(p,snapshot/name);hashes[name]=digest(p)
    for file,name in(('Input.h','PadHistory'),('ControllerInputRuntime.h','ControllerInputRuntime')):
        p=snapshot/file;raw=p.read_text();p.write_text(add_friend(raw,name));assert p.read_text().replace(FRIEND,'')==raw
        adapters[file]=dict(original_sha256=hashes[file],generated_sha256=digest(p),access='One friend declaration only; stripping it reconstructs byte-identical original header. Private read-only ring/cache observation and tick/publication/consumption counter fixture setter; no stored geometry/controller result inputs.')
    probe=snapshot/OWNED[0].name;shutil.copy2(OWNED[0],probe);binary=output/'gameplay-world-input-native'
    if compile:subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(u+'.cpp'))for u in UNITS],str(probe),'-o',str(binary)],check=True)
    for name,sha in hashes.items():
        if name in adapters:assert hashlib.sha256((snapshot/name).read_text().replace(FRIEND,'').encode()).hexdigest()==sha
        else:assert digest(snapshot/name)==sha
    report=dict(native_source_sha256=hashes,declaration_only_snapshot_adapters=adapters,units=UNITS,probe_sha256=digest(OWNED[0]),binary_sha256=digest(binary)if compile else None)
    (output/'native-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return binary,report


def decode(data,cases):
    w=struct.unpack('<'+'I'*(len(data)//4),data);at=0;out=[]
    for c in cases:
        index,kind,count=w[at:at+3];assert(index,kind)==(c['index'],c['kind']);start=at+3;end=start+count;at=start;n=w[at];at+=1;assert n==len(c['commands']);rows=[]
        for command in c['commands']:
            step,op,count=w[at:at+3];assert(step,op)==(len(rows),command[0]);first=at;at+=3;stop=at+count;blocks={}
            while at<stop:
                tag,size=w[at:at+2];at+=2;assert tag not in blocks;blocks[tag]=dict(words=w[at:at+size],offset=at);at+=size
            assert at==stop and set(blocks)=={0,1};rows.append(dict(step=step,operation=op,blocks=blocks,first_word=first,end_word=stop))
        assert at==end;out.append(rows);c.update(first_output_word=start-3,output_words=end-(start-3))
    assert at==len(w);return out


def read_provider(i,counts):
    n=i.word('grind.primitives.count');counts['grind_primitives']+=n
    for j in range(n):
        p='grind.primitives['+str(j)+']';start=i.take(4,p+'.start');end=i.take(4,p+'.end');i.wide(p+'.owner')
        if start==end:counts['duplicate_chords']+=1
        if i.word(p+'.metadata.present'):
            i.take(4,p+'.metadata.guids');i.word(p+'.metadata.segment');flags=i.word(p+'.metadata.flags');counts['vertical_chords']+=bool(flags&0x80000000)
        if i.word(p+'.guids.present'):i.take(4,p+'.guids')
        if i.word(p+'.source.present'):i.text(p+'.source.file');i.text(p+'.source.asset');i.wide(p+'.source.section');i.wide(p+'.source.offset')
        if i.word(p+'.rail.present'):i.wide(p+'.rail')
        if i.word(p+'.bounds.present'):i.take(6,p+'.bounds')
    for j in range(5):
        if i.word('grind.owner_lookup['+str(j)+'].present'):i.take(4,'grind.owner_lookup['+str(j)+'].guids')
    i.take(8,'grind.invalid_index_lookup')


def read_world_snapshot(words,counts,labels=False):
    i=Cursor(words,labels);present=i.word('prepared.present')
    if present:
        seams=i.word('prepared.imported_floor_seams');assert seams==1;counts['seam_snapshots']+=1;n=i.word('collision.triangles.count');counts['triangles_observed']+=n
        for j in range(n):
            p='collision.triangles['+str(j)+']';i.take(9,p+'.vertices');i.take(3,p+'.normal');i.take(9,p+'.edges');i.word(p+'.flags');i.take(3,p+'.edge_cosines');i.take(3,p+'.edge_lengths');i.word(p+'.fatness');i.take(3,p+'.material');i.word(p+'.tag')
        ok,e=i.status('collision.metadata');assert ok and not e
        n=i.word('collision.metadata.surfaces.count');i.take(n,'collision.metadata.surfaces');n=i.word('collision.metadata.meshes.count');counts['mesh_clusters']+=n
        for j in range(n):
            p='collision.metadata.meshes['+str(j)+']';i.take(2,p+'.triangle_range');i.take(12,p+'.local_to_world');i.take(12,p+'.world_to_local');i.take(6,p+'.bounds');i.take(3,p+'.group_rejection_geometry');i.word(p+'.pool')
        n=i.word('collision.metadata.edges.count');i.take(n*12,'collision.metadata.edges');i.word('collision.metadata.island_flags');i.word('collision.maximum_fatness');n=i.word('collision.triangle_bounds.count');i.take(n*6,'collision.triangle_bounds');read_provider(i,counts)
    i.finish();return i.labels


def read_input_snapshot(words,counts,labels=False):
    i=Cursor(words,labels);tick=i.wide('controller.tick');pub=i.wide('controller.publications');consumed=i.wide('controller.consumed_batches');i.word('controller.active_cache')
    for n in range(4):i.take(7,'controller.raw['+str(n)+']')
    for b in range(2):
        for n in range(4):i.word('controller.cache['+str(b)+']['+str(n)+'].count');i.take(24,'controller.cache['+str(b)+']['+str(n)+'].storage')
    read=i.word('controller.history.read');write=i.word('controller.history.write');counts['ring_wrapped_positions']+=write<read
    for b in range(30):
        for n in range(4):i.word('controller.history['+str(b)+']['+str(n)+'].count');i.take(24,'controller.history['+str(b)+']['+str(n)+'].storage')
    for n in range(4):
        p='controller.device['+str(n)+']';status=i.word(p+'.status');counts['status_'+('unpolled','ready','unavailable')[status]]+=1
        if status==2:i.take(2,p+'.error')
        if i.word(p+'.packet.present'):i.word(p+'.packet.number')
        count=i.word(p+'.pad.count');storage=i.word(p+'.pad.storage_count');assert count<=storage;i.take(storage*4,p+'.pad.records');i.take(18,p+'.mapped_actions');i.take(36,p+'.actions')
    i.wide('published.tick');i.word('published.controller_available');i.take(36,'published.actions');i.take(36,'player_actions');i.take(7,'selected_raw');markers=i.take(3,'session_markers');counts['marker_modifier']+=markers[0];counts['marker_down']+=markers[1];counts['marker_up']+=markers[2];i.finish();return(tick,pub,consumed,i.labels)


def read_world_result(words,op,counts):
    i=Cursor(words);ok,e=i.status('result');counts['world_success'if ok else'world_errors']+=1
    if op==0:
        counts['successful_builds'if ok else'failed_builds']+=1
        if not ok:counts['build_error_'+e.split(':',1)[0].split(' at triangle ',1)[0]]+=1
    if op==1 and ok:
        if i.word('candidate_bounds.present'):i.take(6,'candidate_bounds')
        n=i.word('ranges');i.take(n*2,'ranges');n=i.word('candidates');i.take(n,'candidates');i.status('meshes');n=i.word('mesh_indices');i.take(n,'mesh_indices')
        for label in('thin','swept'):
            success,error=i.status(label);counts['line_errors']+=not success
            if i.word(label+'.hit'):i.take(11,label+'.hit');counts['line_hits']+=1
            else:counts['line_misses']+=1
        success,error=i.status('grind_query');counts['grind_query_errors']+=not success;n=i.word('grind_indices.count');i.take(n,'grind_indices');counts['grind_cap40']+=n==40;counts['grind_query_hits']+=n>0;counts['grind_query_misses']+=n==0
    elif op==2 and ok:
        dropped=i.word('dropped');n=i.word('contacts');counts['contact_drops']+=dropped;counts['contacts']+=n;counts['nonempty_contact_queries'if n else'empty_contact_queries']+=1;i.take(n*64,'contacts')
    i.finish()


def coverage(rows,cases):
    counts=Counter()
    for observed,c in zip(rows,cases):
        prior=None
        for row in observed:
            result=row['blocks'][0]['words'];snapshot=row['blocks'][1]['words'];op=row['operation']
            if c['kind']==0:read_world_result(result,op,counts);read_world_snapshot(snapshot,counts)
            else:
                assert len(result)==1 and result[0]in(0,1);clock=read_input_snapshot(snapshot,counts)[:3]
                if op==1:counts['fresh_publications'if result[0]else'no_fresh_publications']+=1
                if prior is not None and op!=4:
                    for n,name in enumerate(('tick','publications','consumed')):counts[name+'_wraps']+=clock[n]<prior[n]
                prior=clock
    for name in('successful_builds','failed_builds','seam_snapshots','triangles_observed','mesh_clusters','grind_primitives','duplicate_chords','vertical_chords','line_hits','line_misses','line_errors','grind_query_errors','grind_query_hits','grind_query_misses','grind_cap40','contacts','nonempty_contact_queries','empty_contact_queries','status_unpolled','status_ready','status_unavailable','fresh_publications','no_fresh_publications','ring_wrapped_positions','marker_modifier','marker_down','marker_up','tick_wraps','publications_wraps','consumed_wraps'):
        assert counts[name]>0,('Unexercised real owner branch',name)
    return dict(counts)


def first_divergence(expected,actual,cases,rows):
    first=next((n for n,(a,b)in enumerate(zip(expected,actual))if a!=b),min(len(expected),len(actual)));report=dict(passed=False,first_word=first//4,reference_bytes=len(expected),native_bytes=len(actual));candidate=None
    try:candidate=decode(actual,copy.deepcopy(cases))
    except(AssertionError,ValueError,IndexError)as e:report['native_decode_error']=str(e)
    if candidate is not None:
        for c,rr,aa in zip(cases,rows,candidate):
            found=False
            for r,a in zip(rr,aa):
                for tag in(0,1):
                    rw,aw=r['blocks'][tag]['words'],a['blocks'][tag]['words']
                    if rw==aw:continue
                    offset=next((n for n,(x,y)in enumerate(zip(rw,aw))if x!=y),min(len(rw),len(aw)));report.update(case=c['index'],label=c['label'],operation=r['operation'],step=r['step'],block='result'if tag==0 else'owner',block_word=offset,reference_word=rw[offset]if offset<len(rw)else None,native_word=aw[offset]if offset<len(aw)else None,reference_block_words=len(rw),native_block_words=len(aw))
                    if tag==1:
                        counts=Counter();labels=read_world_snapshot(rw,counts,True)if c['kind']==0 else read_input_snapshot(rw,counts,True)[3];report['owner_field']=labels[offset]if offset<len(labels)else'end_of_owner'
                    found=True;break
                if found:break
            if found:break
    return report


def preflight(output,raw,ranges,cases):
    protocol=validate_protocol(raw,ranges,cases);_,rp=stage_reference(output,output/'unused-reference-target',compile=False);_,np=stage_native(output,compile=False)
    report=dict(preflight=True,execution=False,histories=len(cases),world_histories=sum(c['kind']==0 for c in cases),controller_histories=sum(c['kind']==1 for c in cases),operations=sum(len(c['commands'])for c in cases),protocol=protocol,input_bytes=len(raw),input_sha256=hashlib.sha256(raw).hexdigest(),reference_host_prefixes=len(rp['staged_host_original_prefixes']),native_units=UNITS,owned_sha256={str(p.relative_to(PLUGIN)):digest(p)for p in OWNED},production_sha256={p.name:digest(p)for u in('GameplayWorld','ControllerInputRuntime')for p in(CODE/(u+'.h'),CODE/(u+'.cpp'))},closure='Full original host including bridge/collision_map/skate_world/provider/controllers/platform. Native14 concrete TUs. Core append-only privacy observers and native friend declarations only. Actual contact producer + seam flag. No whole session/global/OS poll claim.')
    (output/'owner-freeze.json').write_text(json.dumps(report,indent=2)+'\n');return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--target-dir',type=Path);parser.add_argument('--preflight',action='store_true');args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    raw,ranges,cases=corpus();validate_protocol(raw,ranges,cases);(output/'input.bin').write_bytes(raw);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');(output/'input-ranges.json').write_text(json.dumps(ranges,indent=2)+'\n')
    if args.preflight:print(json.dumps(preflight(output,raw,ranges,cases),indent=2));return
    if args.target_dir is None:parser.error('--target-dir required for guarded execution')
    for name in('result.json','first-divergence.json'):(output/name).unlink(missing_ok=True)
    cpp,_=stage_native(output,compile=True);ref,_=stage_reference(output,args.target_dir,compile=True)
    expected=subprocess.check_output([str(ref)],input=raw);actual=subprocess.check_output([str(cpp)],input=raw);(output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual)
    rows=decode(expected,cases);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    if expected!=actual:
        report=first_divergence(expected,actual,cases,rows);(output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
    summary=coverage(rows,cases);report=dict(passed=True,histories=len(cases),operations=sum(len(c['commands'])for c in cases),exact_words=len(expected)//4,coverage=summary,input_sha256=hashlib.sha256(raw).hexdigest(),output_sha256=hashlib.sha256(expected).hexdigest(),comparison='Every triangle/feature/cosine/material/cluster/pool/bounds and authored grind primitive/GUID/source/metadata/bounds/query order. Actual retained floor-seam contacts. All four-device raw/status/packet/cache/ring/Pad/actions/publications/ticks/retained histories, exact words and diagnostics.',limitations='External raw authored geometry and platform DevicePacket/DeviceError batches are explicit fixture inputs. Windows SDK polling/capability-time cache, complete session construction/configure/frame/global scheduling and dynamic-provider geometry are outside this focused owner proof. Counter fixtures seed only tick/publication/consumption clocks; no geometry/hit/controller output is seeded.')
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
