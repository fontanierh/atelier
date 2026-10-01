#!/usr/bin/env python3
"""Compare ControlAirLegExtension/BodySpin to the full frozen MotionHost.

Stock native metadata/settings are the candidate boundary. Original host modules
and arithmetic run unchanged; fixture records and parameter observers expose
consumed values, retained behavior instances and actual stock spin channels.
Compile and execute only under atelier.safety.
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
import check_motion_feedback_parity as feedback
from check_graph_parity import attribute,element,original_graph
from check_gesture_parity import PLUGIN,converter
from check_motion_animation_parity import validate_fixture_attributes
from session_parity import REFERENCE_REVISION,digest

NAMES=('DISTTOCOG','CUSTOM_HEIGHT','EXTEND')
KINDS=('ControlAirLegExtension','ControlAirLegExtension/LeftToe','ControlAirLegExtension/RightToe','ControlAirLegExtension/fallback','BodySpin')


def fixture():
    return element('state','root',children=[
        element('behaviour','ControlAirLegExtension'),
        element('behaviour',' ControlAirLegExtension ',[attribute('bone','LeftToeBase'),attribute('driveDistToCom','custom_height')]),
        element('behaviour','ControlAirLegExtension',[attribute('bone','RightToeBase')]),
        element('behaviour','\u2003ControlAirLegExtension\u2003',[attribute('bone','UnknownBone'),attribute('driveDistToCom','custom_height')]),
        element('behaviour','\u2003BodySpin\u2003')])


def fixture_metadata():
    data=feedback.observer_metadata(NAMES);data['source_bank']='AirborneFixture.abin'
    for index,clipname in enumerate(('AIR_INITIAL_NONE','AIR_INITIAL_FLOAT','AIR_INITIAL_VECTOR','AIR_INITIAL_FULL_VECTOR')):
        offset=50000+index*4096;attrs=[]
        if index:
            scalar=index==1
            attrs=[('DISTTOCOG',0 if scalar else 1,[bits(3.137)] if scalar else [bits(v) for v in (1,2,3,4)]),
                ('CUSTOM_HEIGHT',0 if scalar else 1,[bits(2.731)] if scalar else [bits(v) for v in (5,6,7,8)])]
        if index in (1,3):attrs.append(('FULLEXTENSION',0 if index==1 else 1,[bits(10)] if index==1 else [bits(v) for v in (9,10,11,12)]))
        attrs.sort(key=lambda a:tuple(feedback.trees.name(a[0])))
        data['clips'].append(dict(name=clipname,source_offset=offset,fps_bits=bits(30),frames_bits=bits(31),base_speed_bits=bits(1),flags_word=0x10000000,
            attributes=[dict(name=name,type_id=kind,begin_bits=bits(-1),end_bits=bits(-1),payload_words=payload,source_offset=offset+128+i*128) for i,(name,kind,payload) in enumerate(attrs)]))
    validate_fixture_attributes(data);return data


def corpus():
    rows=[]
    def add(id,phase=1,allocate=0,cache=0,dt=.05,mask=31,category=1,state=500,doing=0,hands=(0,0),mirrored=0,vertical=1,offboard=0,remaining=1,near=0,override=0,spin=0):
        rows.append(dict(id=id,phase=phase,allocate=allocate,cache=cache,dt=dt,mask=mask,category=category,state=state,doing=doing,hands=hands,mirrored=mirrored,
            vertical=vertical,offboard=offboard,remaining=remaining,near=near,override=override,spin=spin))
    # Independent fresh instances observe missing/scalar/non-scalar cached seeds
    # and all ascending, descending, preland/multiplier paths for all bones.
    for id in range(4):
        for cache in range(1,5):
            add(id,0,allocate=1,cache=cache)
            for tick in range(40):
                add(id,vertical=1.137 if tick<6 else 0 if tick==6 else -.731,
                    dt=(0,1/60,.05,.137)[tick%4],offboard=cache%2,remaining=10 if tick<21 else .01,
                    near=tick>=14,override=tick in (14,15),mirrored=tick%2)
            add(id,2)
    # The stock arm curve changes only during its first 0.3 seconds. The longer
    # descending steps above cross that interval in six updates, then clamp at
    # its final knot. Independent short-step descents observe its first segment
    # through the real retained descending_time and parameter/observer tree.
    for id in range(4):
        add(id,0,allocate=1,cache=1)
        for tick in range(32):
            add(id,vertical=-.731,dt=(.00317,.004731)[tick%2],near=0,remaining=10)
        add(id,2)
    # Absence remains an error at its actual first-consumption point. Begin/End
    # keep source no-op semantics even while publications are absent.
    for id in range(4):
        add(id,0,allocate=1,cache=1,mask=0);add(id,mask=30)
        add(id,vertical=-1);add(id,mask=29,vertical=-1);add(id,2,mask=0)
    # Drive all five source BodySpin modes with actual public channel effects.
    # Landed doing-trick enters armed then spinning; airborne retains it; near
    # biped/busy gate disables it; grounded inactive resets before another sign.
    for cycle in range(10):
        add(4,0,allocate=cycle==0,cache=1,mask=0)
        add(4,spin=0)
        add(4,doing=1,spin=.137,mirrored=cycle%2)
        for tick in range(10):add(4,doing=1,spin=(1 if cycle%2==0 else -1)*(.317+tick*.137),mirrored=cycle%3==0)
        for tick in range(8):add(4,category=2,state=503,spin=(-1 if cycle%2==0 else 1)*.973,mirrored=cycle%3==0,vertical=-1,near=tick>=5)
        add(4,category=1,doing=0,spin=0)
        add(4,category=3)
        add(4,category=1)
        add(4,doing=1,spin=.973,hands=(1,0))
        add(4,category=1)
        add(4,doing=1,spin=.137)
        add(4,doing=1,spin=-.973,hands=(1,1)) # mode1 precedence permits2
        add(4,2,mask=0)
    for mask in (27,23,15):add(4,mask=mask)
    add(4,mask=29,category=2,vertical=-1)
    return rows


class Writer(Stream):
    def vector(self,values):
        for value in values:self.float(value)
    def mapping(self,values):
        self.word(len(values))
        for name,value in values:self.string(name);self.float(value)


def encoded(rows):
    w=Writer();w.word(len(NAMES))
    for name in NAMES:w.string(name)
    w.word(len(rows))
    for r in rows:
        for k in ('id','phase','allocate','cache'):w.word(r[k])
        w.float(r['dt']);w.word(r['mask']);w.word(r['category']);w.word(r['state']);w.word(r['doing'])
        for hand in r['hands']:w.word(hand)
        w.word(r['mirrored'])
        for v in ((.137,r['vertical'],.731,0),(.317,3.137,.731,1),(0,.731,.317,0),(.137,.517,.113,1),(-.731,.113,.317,1)):w.vector(v)
        w.float(1.137);w.word(r['offboard']);w.float(r['remaining'])
        w.word(r['override']);w.float(.731);w.float(.137);w.float(r['vertical']);w.word(0);w.word(r['near']);w.float(.137 if r['near'] else 10)
        w.word(0);w.float(.317);w.float(.01 if r['near'] else 10);w.float(.137)
        w.mapping([('BodySpin',r['spin'])])
    return bytes(w.data)


def validate_input(data,rows):
    r=feedback.Reader(data);assert [r.string() for _ in range(r.word())]==list(NAMES);assert r.word()==len(rows)
    for row in rows:
        assert r.word()==row['id'];assert r.word()==row['phase'];r.words(10+23+11)
        for _ in range(r.word()):r.string();r.word()
    assert r.at==len(data),(r.at,len(data))


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
    cargo=crate/'Cargo.toml';cargo.write_text(cargo.read_text()+'\nskate-core={path="../crates/skate-core"}\nskate-data={path="../crates/skate-data"}\nskate-net={path="../crates/skate-net"}\nhalf="2.7.1"\nbevy={version="0.19",default-features=false,features=["std","multi_threaded","bevy_log"]}\n\n[[bin]]\nname="animation-airborne-reference"\npath="src/migration_probe.rs"\n')
    probe=PLUGIN/'Tests/Reference/animation_airborne_probe.rs';shutil.copy2(probe,crate/'src/migration_probe.rs')
    subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(cargo),'--target-dir',str(target.resolve()),'--bin','animation-airborne-reference'],check=True)
    for p,sha in originals.items():assert digest(source/p)==sha
    for p,sha in staged.items():assert digest(crate/'src'/p)==sha
    binary=output/'animation-airborne-reference';shutil.copy2(target.resolve()/'release/animation-airborne-reference',binary)
    report=dict(reference_revision=revision,source_archive_sha256=hashlib.sha256(archive).hexdigest(),original_source_sha256=originals,staged_host_modules_sha256=staged,probe_sha256=digest(probe),binary_sha256=digest(binary),cargo_lock_sha256=digest(crate/'Cargo.lock'),compiler=subprocess.check_output(['rustc','+1.97.1','-vV'],text=True).strip(),boundary='Full untouched MotionHost factories and Allocate/Begin/Update/End call original air-leg/BodySpin state and exact public MotionAnimation parameter/channel/pose APIs. No original method bodies, modules, accessors or callbacks are substituted.')
    (output/'reference-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return binary


def build_native(output):
    live=PLUGIN/'Source/AtelierSkate/Private/Native';code=output/'native-source'
    if code.exists():shutil.rmtree(code)
    code.mkdir();files=('NativeMath','AnimationName','Intents','Input','InputIntentions','NameId','Settings','Graph','GraphConditions','GraphGestureOperations','AnimationSamples','AnimationMetadata','AnimationPlayback','AnimationPlaybackParameters','AnimationTrees','AnimationChannels','MotionAnimation','GraphMotionName','GraphMotionSpecialConditions','AnimationAirborne','AnimationAirborneSettings')
    for path in list(live.glob('*.h'))+[live/(f+'.cpp') for f in files]:shutil.copy2(path,code/path.name)
    probe=code/'animation_airborne_probe.cpp';shutil.copy2(PLUGIN/'Tests/Native/animation_airborne_probe.cpp',probe);(output/'native-source-provenance.json').write_text(json.dumps({p.name:digest(p) for p in sorted(code.iterdir())},indent=2)+'\n')
    binary=output/'animation-airborne-cpp';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(code),*[str(code/(f+'.cpp')) for f in files],str(probe),'-o',str(binary)],check=True);return binary


def coverage(data,rows):
    r=feedback.Reader(data);assert r.word()==len(rows);errors=Counter();queries=[set() for _ in NAMES];channels=[set(),set()];commands=set();seeds={};front_back_signs=set()
    for index,row in enumerate(rows):
        error=r.status()
        if error is not None:errors[error]+=1
        for _ in range(3):assert r.status() is None
        values=[]
        for i,name in enumerate(NAMES):
            assert r.status() is None;assert r.word();header,payload=r.attribute();assert header[:5]==feedback.trees.name(name);queries[i].add(payload[0]);values.append(payload[0])
        state=[tuple(r.words(4)) for _ in range(2)]
        for i,c in enumerate(state):channels[i].add(c)
        front_back_signs.add((state[0][0],state[1][0]));assert r.status() is None;cs=r.commands();commands.add(hashlib.sha256(repr(cs).encode()).hexdigest())
        if row['id']<4 and row['phase']==0 and row['allocate'] and row['cache']:
            assert index+1<len(rows)
        if index and row['id']<4 and rows[index-1]['phase']==0 and rows[index-1]['allocate'] and rows[index-1]['cache']:
            seeds[(row['id'],rows[index-1]['cache'])]=values[row['id']%2]
    assert r.at==len(data),(r.at,len(data))
    assert all(len(v)>8 for v in queries),dict(zip(NAMES,map(len,queries)))
    assert len(commands)>64
    assert all({c[0] for c in states}=={0,1} and len(states)>16 for states in channels)
    assert {(1,0),(0,1)}<=front_back_signs,front_back_signs
    assert all(len({seeds[(id,cache)] for cache in range(1,5)})>=3 for id in range(4)),seeds
    expected=('Air leg extension requires completed physical output','Air leg extension requires actual prelanding output',
        'BodySpin requires physicalcategory','BodySpin requires physicalstate','BodySpin requires animstance','BodySpin airborne branch requires actual prelanding physical outputs')
    assert all(any(e.endswith(text) for e in errors) for text in expected),errors
    return dict(rows=len(rows),errors=dict(errors),consumed_parameter_variants=dict(zip(NAMES,map(len,queries))),initial_seed_variants={str(id):len({seeds[(id,cache)] for cache in range(1,5)}) for id in range(4)},spin_channel_states=list(map(len,channels)),front_back_presence=sorted(front_back_signs),pose_command_variants=len(commands))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',required=True,type=Path);p.add_argument('--metadata',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--target-dir',required=True,type=Path);a=p.parse_args();output=a.output.resolve();output.mkdir(parents=True,exist_ok=True)
    rows=corpus();commands=encoded(rows);validate_input(commands,rows);graph=fixture();original=output/'airborne.reference';original.write_bytes(original_graph(graph));native_graph=output/'airborne.native';native_graph.write_bytes(converter.encode_graph(converter.read_graph(original)))
    metadata=fixture_metadata();fixture_json=output/'observers.json';fixture_json.write_text(json.dumps(metadata));fixture_native=output/'observers.skate';fixture_native.write_bytes(feedback.trees.converter.pack_metadata(metadata));(output/'input.bin').write_bytes(commands)
    reference=build_reference(output,a.target_dir);native=build_native(output);settings=output/'settings.native';settings.write_bytes(converter.encode_settings(a.assets/'private/stock/skater-collections.json'))
    oracle=subprocess.check_output([str(reference),str(a.assets.resolve()),str(original),str(fixture_json)],input=commands)
    candidate=subprocess.check_output([str(native),str(a.metadata.resolve()/'bank-0.skate'),str(a.metadata.resolve()/'bank-1.skate'),str(fixture_native),str(native_graph),str(settings)],input=commands)
    (output/'reference.bin').write_bytes(oracle);(output/'native.bin').write_bytes(candidate)
    if candidate!=oracle:
        first=next((i for i,(x,y) in enumerate(zip(candidate,oracle)) if x!=y),min(len(candidate),len(oracle)));raise AssertionError(f'Airborne differs at byte {first}; all inputs and output streams saved')
    counts=Counter((r['id'],r['phase']) for r in rows)
    result=dict(passed=True,configurations=len(KINDS),callbacks=len(rows),calls_by_operation={f'{KINDS[id]}/{phase}':n for (id,phase),n in counts.items()},coverage=coverage(oracle,rows),output_bytes=len(candidate),output_sha256=hashlib.sha256(candidate).hexdigest(),comparison='Unchanged full original MotionHost factory/allocation/Begin/Update/End, cached absent/scalar/vector seeding, board/left/right/fallback bones, ascending/descending/preland toe multiplier and consumed height/extension, BodySpin persistent five-mode transitions, influence clamps and actual front/back stock channel timing/pose commands.',limitations='Finite stock settings and supplied completed airborne records. No physical producer or live scheduler registration comparison in this isolated slice; complete authored gameplay/session parity remains pending.',fixture_boundary='GameplayConditions state is consumed by BodySpin; all other complete-record fields are explicit unused sentinels. Parameter observer and initial-cache clips are synthetic fixture metadata; spin channels use real stock metadata.',data_boundary='Candidate reads project-native metadata/settings; original fixture JSON exists only in the independent Rust oracle.',reference_provenance_sha256=digest(output/'reference-provenance.json'),native_source_provenance_sha256=digest(output/'native-source-provenance.json'))
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
