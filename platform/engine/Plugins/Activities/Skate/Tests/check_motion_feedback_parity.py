#!/usr/bin/env python3
"""Compare physical animation factories/lifecycle to untouched full MotionHost.

The oracle uses original allocation and Begin/Update/End dispatch, with ordered
calls, independently absent completed producer records and real B_PUMP trees.
Project data is the candidate's only stock input. Observer trees are
synthetic fixture data that expose consumed parameters through public queries;
there are no private accessor substitutes or original-method replacements.
Run builds/execution only through atelier.safety.
"""
import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tarfile
from check_animation_playback_parity import Stream,bits
import check_animation_trees_parity as trees
from check_gesture_parity import converter,PLUGIN
from check_graph_parity import attribute,element,original_graph
from session_parity import REFERENCE_REVISION,digest

KINDS=('SetTurning','Crouching','SettingBodyTilt','UpdateRidingFakie','Pumping','DisallowPumping','SetDeckPitchAndYaw')
FIXTURES=12
TICKS=256


def fixture(case):
    defaults=('ANGLE','DIR','QUICKNESS','SPEEDTUCK','HOLDING','','TILT_X','SKATEYAW','SKATEPITCH')
    names=defaults if case%3==0 else tuple(f'PARAM{i}' for i in range(9)) if case%3==1 else ('SAME','PARAM1','PARAM2','SAME','PARAM4','SAME','PARAM6','SAME','PARAM8')
    values=[[],[],[],[],[],[],[]]
    if case%3:
        values[0]=[attribute(k,v) for k,v in zip(('angleName','dirName','quicknessName','speedName','holdingName'),names[:5])]
        values[1]=[attribute('crouchName',names[5])];values[2]=[attribute('tilt_x',names[6])]
        values[6]=[attribute('skateyaw',names[7]),attribute('skatepitch',names[8])]
        values[3]=[attribute(k,bits=bits(v)) for k,v in zip(('highSpeedThreshold','lowSpeedThreshold','timeSlowlyRollingBackwardsThreshold','timeFromTeleportThreshold'),(2,1,.137,.317))]
    order=list(range(7))
    # Fakie changes live bits used by later Turning; alternate traversal order.
    if case%2:order=[3,0,2,1,6,4,5]
    if case>=6:order=order[::-1]
    graph=element('state','root',children=[element('behaviour',KINDS[i],values[i]) for i in order])
    return graph,list(dict.fromkeys(n for n in names if n)),order


def observer_metadata(names):
    value=dict(version=1,source_bank='FeedbackFixture.abin',source_sha256='b'*64,source_bytes=1000000,clips=[],phase_blends=[],blend_spaces=[],selectors=[],selection_spaces=[],unsupported_trees=[])
    for i,name in enumerate(names):
        children=[]
        for side,endpoint in enumerate((-16.,16.)):
            identity=f'OBS_CLIP{i}_{side}';children.append(identity);offset=48+(i*2+side)*512
            value['clips'].append(dict(name=identity,source_offset=offset,fps_bits=bits(30),frames_bits=bits(61),base_speed_bits=bits(1),flags_word=0x10000000,attributes=[dict(name=name,type_id=0,begin_bits=bits(-1),end_bits=bits(-1),payload_words=[bits(endpoint)],source_offset=offset+128)]))
        value['phase_blends'].append(dict(name=f'OBS_TREE{i}',source_offset=20000+i*512,parameter=name,children=children))
    return value


class Writer(Stream):
    def vector(self,values):
        for v in values:self.float(v)
    def mapping(self,values):
        self.word(len(values))
        for name,v in values:self.string(name);self.float(v)


def corpus(case,names,order):
    w=Writer();w.word(len(names))
    for n in names:w.string(n)
    w.word(TICKS);counts=Counter();lookup={kind:order.index(i) for i,kind in enumerate(KINDS)}
    for tick in range(TICKS):
        w.float((0,1/60,.03125,.137)[(tick+case)%4]);intents=[]
        for i,n in enumerate(('AutoPumpAngle','AutoPumpMag','Crouch','HardTurnCrouch','Manual','FakieTurn','LeftSlide','RightSlide')):
            if (tick+i)%11:intents.append((n,((tick//7+i+case)%9-4)*.173))
        w.mapping(intents);mask=255
        if tick==0 and case%4==0:mask=0
        if 17<=tick<25:mask^=1<<(tick-17)
        w.word(mask);w.word(0x08020000|((tick//7+case)%2<<29)|((tick//11+case)%2<<30));w.word(tick%2);w.word(tick%19<3);w.word(tick%23<7);w.word(tick%29<20)
        for v in (bits(tick*.137),0x80000000 if tick%17==0 else 0,bits(tick*.317),0x40000000 if tick%23==0 else 0,(0x80000000 if tick%2 else 0)|0x40000000):w.word(v)
        w.vector((.137+(tick%9)*.113,.317+(tick%7)*.113,(tick%11)*.087,(tick%11-5)*.137,.137+(tick%17)*.03125,(tick%37)*.731))
        w.vector(((tick%7-3)*.113,(tick%17)*.317,(tick%23)*.137,(tick%13-6)*.317,(tick%11-5)*.317,.113,(tick%5)*.137,.317+case*.03125))
        w.float((tick%13-6)*.137);w.float((tick%9)*.317);w.word((1,2,5)[(tick//5+case)%3])
        w.word(1 if tick>=128 else (1,2,6,5)[(tick//17+case)%4]);w.word(503 if tick%11 else 500);w.word(1)
        w.vector((0,0,1,0));w.vector((.137,.317,(-1,.5,-.5,0)[(tick//9)%4],.731));w.vector((.317,.137,(-1,.5,-.5,0)[(tick//11)%4],.113));w.float((.5,1.5,2.5)[(tick//13+case)%3])
        w.float((0,.317,3.137,7.137,3.137,0,-.137)[(tick//7+case)%7]);w.vector(((tick%13-6)*.137,(tick%17-8)*.113))
        calls=[]
        if tick%64==0:calls.extend((i,0) for i,k in enumerate(order) if k!=5)
        if tick%64 in (16,48):calls.append((lookup['DisallowPumping'],0))
        if tick%64 in (22,55):calls.append((lookup['DisallowPumping'],2))
        calls.extend((i,1) for i in range(7))
        if tick%64==63:calls.extend((i,2) for i in reversed(range(7)))
        w.word(len(calls))
        for i,phase in calls:w.word(i);w.word(phase);counts[(KINDS[order[i]],phase)]+=1
    return bytes(w.data),counts


def validate_input(data,names):
    at=0
    def word():
        nonlocal at
        assert at+4<=len(data);w=struct.unpack_from('<I',data,at)[0];at+=4;return w
    def string():
        nonlocal at
        n=word();s=data[at:at+n].decode();at+=n;return s
    def words(n):
        for _ in range(n):word()
    assert [string() for _ in range(word())]==names;assert word()==TICKS
    for _ in range(TICKS):
        word()
        for _ in range(word()):string();word()
        words(6+5+6+8+3+16+1+2)
        for _ in range(word()):assert word()<7;assert word()<3
    assert at==len(data),(at,len(data))


def build_reference(output,target):
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip());relative=(PLUGIN/'ThirdParty/skate-runtime').relative_to(root).as_posix();revision=subprocess.check_output(['git','rev-parse',REFERENCE_REVISION],cwd=root,text=True).strip()
    archive=subprocess.check_output(['git','archive',f'{revision}:{relative}'],cwd=root);source=output/'reference-source'
    if source.exists():shutil.rmtree(source)
    source.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:stream.extractall(source,filter='data')
    originals={p.relative_to(source).as_posix():digest(p) for p in sorted(source.rglob('*.rs'))};crate=source/'atelier-host';host=source/'crates/skate-host/src';staged={}
    for original in sorted(host.rglob('*.rs')):
        relative=original.relative_to(host)
        if relative.as_posix() in ('lib.rs','main.rs'):continue
        destination=crate/'src'/relative;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(original,destination);staged[relative.as_posix()]=digest(original);assert digest(destination)==digest(original)
    cargo=crate/'Cargo.toml';cargo.write_text(cargo.read_text()+'\nskate-core={path="../crates/skate-core"}\nskate-data={path="../crates/skate-data"}\nskate-net={path="../crates/skate-net"}\nhalf="2.7.1"\nbevy={version="0.19",default-features=false,features=["std","multi_threaded","bevy_log"]}\n\n[[bin]]\nname="motion-feedback-reference"\npath="src/migration_probe.rs"\n')
    probe=PLUGIN/'Tests/Reference/motion_feedback_probe.rs';shutil.copy2(probe,crate/'src/migration_probe.rs')
    subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(cargo),'--target-dir',str(target.resolve()),'--bin','motion-feedback-reference'],check=True)
    for p,sha in originals.items():assert digest(source/p)==sha
    for p,sha in staged.items():assert digest(crate/'src'/p)==sha
    binary=output/'motion-feedback-reference';shutil.copy2(target.resolve()/'release/motion-feedback-reference',binary)
    report=dict(reference_revision=revision,source_archive_sha256=hashlib.sha256(archive).hexdigest(),original_source_sha256=originals,staged_host_modules_sha256=staged,probe_sha256=digest(probe),binary_sha256=digest(binary),cargo_lock_sha256=digest(crate/'Cargo.lock'),compiler=subprocess.check_output(['rustc','+1.97.1','-vV'],text=True).strip(),boundary='Full unchanged MotionHost factory and Allocate/Begin/Update/End with actual core settings, states, MotionAnimation tree parameters, channels, callbacks and pose commands. No original method/body substitutions or private state accessors. MotionPhysical fields other than turning are explicit unused fixture sentinels; the tested leaves only consume its turning field.')
    (output/'reference-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return binary


def build_simulation(output):
    live=PLUGIN/'Source/AtelierSkate/Private/Simulation';code=output/'simulation-source'
    if code.exists():shutil.rmtree(code)
    code.mkdir();files=('SimulationMath','AnimationName','Intents','Input','InputIntentions','NameId','Settings','Graph','AnimationSamples','AnimationMetadata','AnimationPlayback','AnimationPlaybackParameters','AnimationTrees','AnimationChannels','MotionAnimation','GraphMotionName','RidingAnimation','RidingAnimationSettings','GraphMotionFeedbackOperations')
    for path in list(live.glob('*.h'))+[live/(f+'.cpp') for f in files]:shutil.copy2(path,code/path.name)
    probe=code/'motion_feedback_probe.cpp';shutil.copy2(PLUGIN/'Tests/Simulation/motion_feedback_probe.cpp',probe);(output/'simulation-source-provenance.json').write_text(json.dumps({p.name:digest(p) for p in sorted(code.iterdir())},indent=2)+'\n')
    binary=output/'motion-feedback-cpp';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(code),*[str(code/(f+'.cpp')) for f in files],str(probe),'-o',str(binary)],check=True);return binary


class Reader:
    def __init__(self,data):self.data=data;self.at=0
    def word(self):v=struct.unpack_from('<I',self.data,self.at)[0];self.at+=4;return v
    def words(self,n):return [self.word() for _ in range(n)]
    def string(self):n=self.word();v=self.data[self.at:self.at+n].decode();self.at+=n;return v
    def status(self):return None if self.word() else self.string()
    def attribute(self):
        header=self.words(10);payload=[self.word() if self.word() else None for _ in range(6)];return header,payload
    def commands(self):
        cs=[]
        for _ in range(self.word()):
            kind=self.word()
            if kind==0:value=(self.string(),self.words(3))
            elif kind in (1,5,6):value=self.word()
            elif kind==2:value=self.words(self.word())
            elif kind==3:value=self.words(2)
            elif kind==4:value=self.string()
            else:raise AssertionError(kind)
            cs.append((kind,value))
        return cs


def coverage(data,names):
    r=Reader(data);assert r.word()==TICKS;errors=Counter();allow=set();flags=set();pumps=set();queries=[set() for _ in names];command_hashes=set();packet_records=0
    for _ in range(TICKS):
        for _ in range(r.word()):
            error=r.status()
            if error:errors[error]+=1
        allow.add(r.word());flags.add(r.word() if r.word() else None);r.words(5)
        count=r.word();packet_records+=count;r.words(count*6)
        for _ in range(3):assert r.status() is None
        for i in range(len(names)):
            assert r.status() is None;found=r.word();header,payload=r.attribute();assert found and header[:5]==trees.name(names[i]);queries[i].add(payload[0])
        pumps.add(tuple(r.words(4)[0] for _ in range(5)))
        for _ in range(r.word()):r.attribute()
        r.words(3);assert r.status() is None;cs=r.commands();command_hashes.add(hashlib.sha256(repr(cs).encode()).hexdigest())
    assert r.at==len(data);assert allow=={0,1};assert len(command_hashes)>64
    assert errors and any('requires' in e or 'needs actual' in e for e in errors)
    assert max(map(sum,pumps))>0,('no actual pump channel',pumps)
    assert sum(len(q)>2 for q in queries)>=len(queries)-1,('unconsumed factory names',list(zip(names,map(len,queries))))
    return dict(ticks=TICKS,errors=dict(errors),allow_pumping=sorted(allow),animation_flags=len(flags),channel_presence_variants=len(pumps),maximum_simultaneous_pumps=max(map(sum,pumps)),query_value_variants=dict(zip(names,map(len,queries))),pose_command_variants=len(command_hashes),graph_packet_records=packet_records)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',required=True,type=Path);p.add_argument('--metadata',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--target-dir',required=True,type=Path);a=p.parse_args();output=a.output.resolve();output.mkdir(parents=True,exist_ok=True)
    cases=[];counts=Counter()
    for case in range(FIXTURES):
        graph,names,order=fixture(case);commands,calls=corpus(case,names,order);validate_input(commands,names);cases.append((commands,names));counts.update(calls)
        path=output/f'feedback-{case}.reference';path.write_bytes(original_graph(graph));(output/f'feedback-{case}.simulation').write_bytes(converter.encode_graph(converter.read_graph(path)))
        metadata=observer_metadata(names);(output/f'observers-{case}.json').write_text(json.dumps(metadata));(output/f'observers-{case}.skate').write_bytes(trees.converter.pack_metadata(metadata));(output/f'input-{case}.bin').write_bytes(commands)
    reference=build_reference(output,a.target_dir);simulation=build_simulation(output);settings=output/'settings.simulation';settings.write_bytes(converter.encode_settings(a.assets/'private/stock/skater-collections.json'))
    expected=bytearray();actual=bytearray();checks=[]
    for case,(commands,names) in enumerate(cases):
        oracle=subprocess.check_output([str(reference),str(a.assets.resolve()),str(output/f'feedback-{case}.reference'),str(output/f'observers-{case}.json')],input=commands)
        candidate=subprocess.check_output([str(simulation),str(a.metadata.resolve()/'bank-0.skate'),str(a.metadata.resolve()/'bank-1.skate'),str(output/f'observers-{case}.skate'),str(output/f'feedback-{case}.simulation'),str(settings)],input=commands)
        (output/f'reference-{case}.bin').write_bytes(oracle);(output/f'simulation-{case}.bin').write_bytes(candidate)
        if candidate!=oracle:
            first=next((i for i,(x,y) in enumerate(zip(candidate,oracle)) if x!=y),min(len(candidate),len(oracle)));raise AssertionError(f'Motion feedback differs at byte {first}, fixture {case}; full per-fixture commands and results saved')
        checks.append(coverage(oracle,names));expected.extend(oracle);actual.extend(candidate)
    result=dict(passed=True,fixtures=FIXTURES,ticks=FIXTURES*TICKS,behavior_calls=sum(counts.values()),calls_by_operation={f'{name}/{phase}':n for (name,phase),n in counts.items()},coverage=checks,output_bytes=len(actual),output_sha256=hashlib.sha256(actual).hexdigest(),comparison='Original full host factories/allocation and ordered lifecycle, producer absence/partial effects, live fakie/Turning flag visibility, consumed parameters, actual B_PUMP ownership/fades and pose commands.',limitations='Dedicated physical feedback operation boundary. Actual C++ MotionGraphHost registration, complete controller/actor physical producer scheduling and full authored sessions require subsequent integration checks.',data_boundary='Shipping candidate reads ATMETA01 plus the simulation settings. Observer metadata JSON is synthetic original-oracle fixture data, never a runtime EA reader.',reference_provenance_sha256=digest(output/'reference-provenance.json'),simulation_source_provenance_sha256=digest(output/'simulation-source-provenance.json'))
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
