#!/usr/bin/env python3
"""Complete static-world primitive candidates, contacts, retention and imported floor seams."""
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
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def word(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def value(v):return struct.unpack('<f',struct.pack('<I',v))[0]
def f(v):return [word(x) for x in v]
def corpus():
    rng=random.Random(0x8277b720);records=[];cases=[]
    def basis(angle=0.):
        c=math.cos(angle);s=math.sin(angle);return (c,0.,-s,0.,1.,0.,s,0.,c)
    def triangle(vertices=((-10.,0.,-10.),(0.,0.,10.),(10.,0.,-10.)),fat=0.,flags=0xf0,material=(.8,.6,.2),tag=42):
        return f([v for p in vertices for v in p]+[fat,1.,1.,1.])+[flags]+f(material)+[tag]
    def primitive(kind,center,radius=.1,half=(.25,.05,.12),angle=0.):
        if kind==0:return [kind]+f([*center,radius])
        if kind==1:return [kind]+f([*center,*basis(angle)[:3],half[0],radius])
        if kind==2:
            return [kind]+triangle(((-half[0],0.,-half[2]),(0.,0.,half[2]),(half[0],0.,-half[2])),radius,0xe0)[:14]+f([*basis(angle),*center])
        return [kind]+f([*center,*basis(angle),*half,radius])
    def volume(kind,center,body=0,radius=.1,half=(.25,.05,.12),angle=0.,velocity=(0.,0.,0.),material=(.2,.1,.8)):
        return [body]+primitive(kind,center,radius,half,angle)+f([*velocity,*material])
    def frame(volumes,capacity=100,threshold=1.e-6,deferred=False,padding=0.,maximum=.1,obj=False):
        return [len(volumes)]+[v for row in volumes for v in row]+f([padding,maximum,.95,.0001])+[int(obj),capacity,word(threshold),int(deferred)]
    def metadata(triangles,mesh_size):
        payload=[len(triangles)]+[rng.randrange(65536) for _ in triangles];meshes=[]
        for start in range(0,len(triangles),mesh_size):
            end=min(len(triangles),start+mesh_size);points=[[value(w) for w in row[:9]] for row in triangles[start:end]]
            mins=[min(p[i] for row in points for p in (row[:3],row[3:6],row[6:9])) for i in range(3)]
            maxs=[max(p[i] for row in points for p in (row[:3],row[3:6],row[6:9])) for i in range(3)]
            meshes.append([start,end]+f(mins+maxs)+[rng.getrandbits(32),rng.getrandbits(32),rng.getrandbits(32),rng.randrange(3)])
        return payload+[len(meshes)]+[v for row in meshes for v in row]+[rng.getrandbits(32)]
    def add(triangles,frames,label,authored=False,seams=False,mesh_size=2,pair=None):
        payload=[len(triangles)]+[v for row in triangles for v in row]+[int(authored)]+metadata(triangles,max(1,mesh_size))+[int(seams),len(frames)]+[v for row in frames for v in row]
        cases.append(dict(index=len(cases),label=label,frames=len(frames),triangles=len(triangles),authored=authored,seams=seams,seam_pair=pair))
        records.append(struct.pack('<'+'I'*len(payload),*payload))
    board=[volume(0,(x,.1,z),body=i) for i,(x,z) in enumerate(((.16,.25),(-.16,.25),(.16,-.25),(-.16,-.25)))]
    board += [volume(1,(0.,.08,.25),4,.06,half=(.15,.01,.01)),volume(1,(0.,.08,-.25),5,.06,half=(.15,.01,.01)),volume(3,(0.,.07,0.),6,.02,half=(.3,.05,.1))]
    for copies in (0,1,2,8,64):
        for authored in (False,True):
            if copies==0 and authored:continue
            for capacity in (0,1,3,4,7,16,50,100,1000):
                frames=[frame(board,capacity),frame(board,1000,deferred=True),frame([],1000),frame(board,capacity,threshold=-1.)]
                add([triangle(tag=42+i) for i in range(copies)],frames,'board/deck/truck/wheel reused queries and capacity',authored,mesh_size=1)
    for kind in range(4):
        for body in (0,1,2,3,4,5,6,8,9,27,0xfffffffe,0xffffffff):
            for center in ((0.,.05,0.),(10.,.05,-10.),(0.,-.05,0.),(100.,.05,100.)):
                add([triangle(),triangle(tag=43)],[frame([volume(kind,center,body)],1000,threshold=0.),frame([volume(kind,center,body)],1000,deferred=True)],'primitive/body ID/material/tag order',bool(body&1))
    for tiles in (2,4,8):
        triangles=[]
        for x in range(tiles):
            for z in range(tiles):
                p=(float(x),0.,float(z));q=(float(x+1),0.,float(z));r=(float(x+1),0.,float(z+1));s=(float(x),0.,float(z+1))
                triangles.extend((triangle((p,s,r),tag=len(triangles)),triangle((p,r,q),tag=len(triangles)+1)))
        rng.shuffle(triangles)
        for authored in (False,True):
            for deferred in (False,True):
                moving=[volume(kind,(tiles*.5,.1,tiles*.5),body=kind,radius=.3,half=(.5,.1,.5),angle=.2*kind) for kind in range(4)]
                add(triangles,[frame(moving,1000,deferred=deferred),frame([volume(0,(tiles+10.,.1,tiles+10.))])],'shuffled tiled metadata hierarchy and bounds',authored,mesh_size=1)
    floor_vertices=[((-2.,0.,-2.),(0.,0.,2.),(0.,0.,-2.)),((-2.,0.,-2.),(-2.,0.,2.),(0.,0.,2.)),((0.,0.,-2.),(0.,0.,2.),(2.,0.,2.)),((0.,0.,-2.),(2.,0.,2.),(2.,0.,-2.))]
    sides=[((0.,-1.,-1.),(0.,0.,-1.),(0.,0.,1.)),((0.,-1.,-1.),(0.,0.,1.),(0.,-1.,1.))]
    seam_index=0
    for mode in ('joined','open','buried','raised curb','partial join'):
        geometry=list(floor_vertices[:2] if mode=='open' else floor_vertices if mode!='partial join' else floor_vertices[:3])
        if mode in ('buried','raised curb'):
            geometry+=sides if mode=='buried' else [tuple((x,y+.2,z) for x,y,z in t) for t in sides]
        triangles=[triangle(v,flags=0xe0,tag=i) for i,v in enumerate(geometry)]
        for x in (-.1,-.05,0.,.05,.1):
            for z in (-1.1,-.5,0.,.5,1.1):
                for kind in (0,1,3):
                    frames=[frame([volume(kind,(x,.05,z),radius=.1)],1000,threshold=0.)]
                    for authored in (False,True):
                        for seams in (False,True):add(triangles,frames,'imported floor '+mode,authored,seams,mesh_size=1,pair=seam_index)
                        seam_index+=1
    for _ in range(1024):
        triangles=[]
        for i in range(rng.randrange(1,33)):
            x=rng.uniform(-5.,5.);z=rng.uniform(-5.,5.);size=rng.uniform(.1,4.);height=rng.uniform(-.02,.02)
            triangles.append(triangle(((x-size,height,z-size),(x,height,z+size),(x+size,height,z-size)),rng.uniform(0.,.03),rng.choice((0xe0,0xf0,0x1f0)),[rng.uniform(0.,1.) for _ in range(3)],rng.getrandbits(32)))
        frames=[]
        for _ in range(rng.randrange(1,5)):
            volumes=[volume(rng.randrange(4),(rng.uniform(-5.,5.),rng.uniform(-.1,.5),rng.uniform(-5.,5.)),rng.choice((0,1,4,5,6,8,9,15)),rng.uniform(.01,.4),[rng.uniform(.01,.6) for _ in range(3)],rng.uniform(-math.pi,math.pi),[rng.uniform(-3.,3.) for _ in range(3)],[rng.uniform(0.,1.) for _ in range(3)]) for _ in range(rng.randrange(1,9))]
            frames.append(frame(volumes,rng.choice((0,1,4,16,50,1000)),rng.choice((-1.,0.,1.e-6,.01)),bool(rng.randrange(2)),rng.uniform(0.,.05),rng.uniform(0.,.1),bool(rng.randrange(2))))
        add(triangles,frames,'random full primitive retention query stream',bool(rng.randrange(2)),bool(rng.randrange(2)),rng.randrange(1,5))
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
    probe=PLUGIN/'Tests/Reference/world_contact_producer_probe.rs';main=source/'world-contact-producer-oracle.rs'
    main.write_text((source/'lib.rs').read_text()+probe.read_text().replace('//!','//'));reference=output/'world-contact-producer-reference'
    subprocess.run(['rustc','+1.97.1','--edition=2024','-O','-A','dead_code',str(main),'-o',str(reference)],check=True)
    for name,expected in originals.items():
        if digest(source/name)!=expected:raise AssertionError(f'Frozen reference module changed: {name}')
    snapshot=output/'native-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir();native=PLUGIN/'Source/AtelierSkate/Private/Native'
    sources=('NativeMath.h','NativeMath.cpp','GeometryTypes.h','Geometry.h','Geometry.cpp','GeometrySweep.h','GeometrySweep.cpp','WorldGeometry.h','WorldGeometry.cpp','GeometryFeatures.h','GeometryFeatures.cpp','GeometryPrism.h','GeometryPrism.cpp','GeometryTriangleFixup.h','GeometryTriangleFixup.cpp','WorldPrimitiveContact.h','WorldPrimitiveContact.cpp','ContactRetention.h','ContactRetention.cpp','WorldContactProducer.h','WorldContactProducer.cpp')
    for name in sources:shutil.copy2(native/name,snapshot/name)
    shutil.copy2(PLUGIN/'Tests/Native/world_contact_producer_probe.cpp',snapshot/'world_contact_producer_probe.cpp');cpp=output/'world-contact-producer-cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(snapshot),
        *[str(snapshot/name) for name in ('NativeMath.cpp','Geometry.cpp','GeometrySweep.cpp','WorldGeometry.cpp','GeometryFeatures.cpp','GeometryPrism.cpp','GeometryTriangleFixup.cpp','WorldPrimitiveContact.cpp','ContactRetention.cpp','WorldContactProducer.cpp','world_contact_producer_probe.cpp')],'-o',str(cpp)],check=True)
    provenance=dict(reference_revision=revision,source_archive_sha256=hashlib.sha256(archive).hexdigest(),original_source_sha256=originals,
        probe_sha256=digest(probe),reference_binary_sha256=digest(reference),cpp_binary_sha256=digest(cpp),
        native_source_sha256={p.name:digest(p) for p in sorted(snapshot.iterdir())},
        rust_compiler=subprocess.check_output(['rustc','+1.97.1','-vV'],text=True).strip(),cpp_compiler=subprocess.check_output(['clang++','--version'],text=True).strip())
    (output/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');return cpp,reference

def decode(data,cases):
    words=struct.unpack('<'+'I'*(len(data)//4),data);at=0;rows=[]
    for case in cases:
        if at+2>len(words):raise AssertionError('Missing world contact frame')
        index,n=words[at:at+2]
        if index!=case['index']:raise AssertionError('World contact frame identity changed')
        rows.append(words[at+2:at+2+n]);case.update(first_output_word=at,output_words=n+2);at+=n+2
    if at!=len(words):raise AssertionError('Trailing world contact frame')
    return rows

def coverage(rows,cases):
    counts=Counter();seams={}
    for row,case in zip(rows,cases):
        n=row[0];at=1;contacts=0
        if n!=case['frames']:raise AssertionError('World query frame count changed')
        for _ in range(n):
            dropped,length=row[at:at+2];at+=2;counts['dropped']+=dropped;counts['contacts']+=length;counts['nonempty_frames' if length else 'empty_frames']+=1;contacts+=length
            for _ in range(length):
                record=row[at:at+64];at+=64
                if record[7]!=0xffffffff:raise AssertionError('Static-world contact ID changed')
                if any(record[i] for i in range(64) if i not in (0,1,2,3,4,5,6,7,8,9,10,11,15,19,23)):raise AssertionError('Current-body workspace was prematurely populated')
                counts['attached_contacts']+=8<=record[3]<0xffffffff;counts['board_contacts']+=record[3]<7
                if not all(math.isfinite(value(v)) for v in record[:3]+record[4:7]+record[8:11]):raise AssertionError('Finite geometry produced nonfinite contact seeds')
            counts['frames']+=1
        if at!=len(row):raise AssertionError('Malformed world contact query output')
        if case['seam_pair'] is not None:seams.setdefault(case['seam_pair'],{})[case['seams']]=contacts
        counts['authored_worlds' if case['authored'] else 'canonical_worlds']+=1
    counts['seam_contact_removals']=sum(max(0,p[False]-p[True]) for p in seams.values());counts['seam_pairs']=len(seams)
    if any(p[True]>p[False] for p in seams.values()):raise AssertionError('Seam filter added contact seeds')
    for key in ('contacts','dropped','nonempty_frames','empty_frames','attached_contacts','board_contacts','authored_worlds','canonical_worlds','seam_contact_removals'):
        if not counts[key]:raise AssertionError(f'Unexercised complete world query branch: {key}')
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
    counts=coverage(rows,cases);report=dict(passed=True,cases=len(cases),coverage=counts,exact_words=len(expected)//4,input_sha256=hashlib.sha256(inputs).hexdigest(),output_sha256=hashlib.sha256(expected).hexdigest(),comparison='All published seed words exact; original full public BoardWorld pipeline and numerical modules unchanged',
        indirect_coverage='PrimitiveBounds, candidate padding and per-triangle culling validated through original public query_primitives; private buffer state covered separately by ContactRetention')
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
