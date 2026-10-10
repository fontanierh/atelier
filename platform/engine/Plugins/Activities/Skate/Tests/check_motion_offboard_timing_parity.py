#!/usr/bin/env python3
"""Bounded actual original MotionHost cadence/air-time/runout lifecycle parity.

Only parent-run guarded builds/probes. Actual applied parameter observers and
current clock reveal the captured values and source first-update seek schedule.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
from check_gesture_parity import converter
from check_graph_parity import attribute, element, original_graph
from check_input_parity import Record, fbits, from_bits
from check_animation_trees_parity import converter as metadata_converter, name
from check_motion_animation_parity import validate_fixture_attributes
from motion_reference_build import build_probes

PARAMS=('CADENCESTARTPERCENT','ANIMTIME','ANIMTRANSX','ANIMTRANSY','ANIMTRANSZ','BIPEDSTARTANGLE','BIPEDSPEED')
PROOFS=tuple(f'TIMING_PROOF_{i}' for i in range(7))


def fixture():
    names=('BipedCadence','MatchCadence','MatchAirTime','AddRunoutAttribs',' BipedCadence ',' MatchCadence ')
    configs=[element('behaviour',n) for n in names]
    return element('state','root',children=configs),configs


def fixture_metadata():
    data=dict(version=1,source_bank='TimingFixture.abin',source_sha256='e'*64,source_bytes=1000000,clips=[],phase_blends=[],blend_spaces=[],selectors=[],selection_spaces=[],unsupported_trees=[])
    def clip(n,pairs=()):
        offset=48+len(data['clips'])*4096;pairs=sorted(pairs,key=lambda item:tuple(name(item[0])))
        attrs=[dict(name=n,type_id=0,begin_bits=fbits(-1),end_bits=fbits(-1),payload_words=[fbits(v)],source_offset=offset+128+i*128) for i,(n,v) in enumerate(pairs)]
        data['clips'].append(dict(name=n,source_offset=offset,fps_bits=fbits(30),frames_bits=fbits(61),base_speed_bits=fbits(1),flags_word=0x10000000,attributes=attrs))
    clip('TIMING_MAIN')
    for i,param in enumerate(PARAMS):
        tree=f'TIMING_OBSERVER_{i}';children=[]
        for j,v in enumerate((-200.,200.) if i==5 else (-20.,20.)):
            c=f'{tree}_{j}';children.append(c);clip(c,[(param,v),(PROOFS[i],v)])
        data['phase_blends'].append(dict(name=tree,source_offset=100000+i*4096,parameter=param,children=children))
    validate_fixture_attributes(data);return data


def corpus():
    rows=[]
    def add(index,phase=1,*,allocate=None,play=0,inject=0,dt=0.,cadence=.25,air=(.5,1.,(1.,2.,3.,4.)),runout=None):
        rows.append(dict(index=index,phase=phase,allocate=int(phase==0 if allocate is None else allocate),play=play,inject=inject,dt=dt,cadence=cadence,air=air,runout=runout))
    # Update-before-Begin with no main tree still publishes actual air params.
    add(2,cadence=None);add(2,cadence=None,air=(.4,1.,(.25,.5,.75,1.)))
    add(0,play=1)
    for index in range(6):
        for phase in range(3):
            add(index,phase,cadence=None,air=None,runout=None)
    add(2,0,cadence=None)  # Present OffBoard, missing required OffBoard80.
    for index in (0,4):
        for cadence in (0.,.125,.5,1.,-0.,from_bits(0x7fc12345)):
            add(index,cadence=cadence);add(index,cadence=None)
    for index in (1,5):
        add(index,1,allocate=True,cadence=None)
        for value in (.1,.4,.8):
            add(index,0,cadence=value)
            add(index,1,cadence=-5.)
            add(index,0,cadence=None,allocate=False)
            add(index,1,cadence=None)
            add(index,2)
    vectors=((0.,0.,0.,1.),(.005,0.,0.,2.),(.01,0.,0.,3.),(from_bits(fbits(.01)+1),0.,0.,4.),(.5,-.5,1.,2.),(2.,0.,0.,1.),(from_bits(fbits(2.)+1),0.,0.,1.),(3.,4.,0.,2.),
        (from_bits(0x7fc12345),1.,2.,3.),(float('inf'),1.,2.,3.))
    for cadence in (.1,.6):
        add(2,0,cadence=cadence,air=(.9,1.,(9.,8.,7.,6.)),play=1)
        for i,v in enumerate(vectors):
            add(2,cadence=-5.,air=(.8-(i%5)*.2,(0.,-.1,.5,1.,2.,from_bits(0x7fc12345))[i%6],v))
        add(2,2,air=None,cadence=None)
    # Explicit first-update skip then exact seek; dt0 keeps this observable.
    add(2,0,cadence=.3,air=(.8,1.,(.1,.2,.3,0.)),play=1)
    add(2,air=(.25,1.,(.1,.2,.3,0.)))
    add(2,air=(.25,1.,(.1,.2,.3,0.)))
    # Unavailable Begin preserves retained successful runout capture; actual
    # host End republishes. Inject mismatching queued values to prove that call.
    velocities=((0.,0.,0.,0.),(1.,0.,0.,0.),(-1.,0.,0.,0.),(0.,0.,1.,0.),(0.,0.,-1.,0.),(3.,4.,0.,1.),(1.,0.,from_bits(1),2.),(from_bits(0x7fc12345),0.,1.,0.))
    for mirror in (0,1):
        for trajectory in (0,1):
            for i,v in enumerate(velocities):
                p=dict(trajectory=trajectory,offboard=v,velocity=velocities[(i+2)%len(velocities)],up=(0.,1.,0.,0.),forward=(0.,0.,1.,0.),mirror=mirror)
                add(3,0,runout=p)
                add(3,1,runout=None)
                add(3,0,allocate=False,runout=None)
                add(3,2,inject=1,runout=None)
    add(3,2,allocate=True)
    w=Record();w.word(len(rows))
    for r in rows:
        w.words(r[k] for k in ('index','phase','allocate','play','inject'));w.scalar(r['dt']);w.word(r['cadence'] is not None)
        if r['cadence'] is not None:w.scalar(r['cadence'])
        w.word(r['air'] is not None)
        if r['air'] is not None:
            remaining,duration,vector=r['air'];w.scalar(remaining);w.scalar(duration)
            for v in vector:w.scalar(v)
        w.word(r['runout'] is not None)
        if r['runout'] is not None:
            p=r['runout'];w.word(p['trajectory'])
            for n in ('offboard','velocity','up','forward'):
                for v in p[n]:w.scalar(v)
            w.word(p['mirror'])
    return bytes(w.data),rows


def coverage(data,rows,trace_path):
    at=0
    def word():
        nonlocal at
        v,=struct.unpack_from('<I',data,at);at+=4;return v
    def string():
        nonlocal at
        n=word();s=data[at:at+n].decode();at+=n;return s
    def scalar():return dict(ok=ok,value=word() if ok else string()) if (ok:=word()) else dict(ok=0,value=string())
    assert word()==len(rows);traces=[];phases={}
    for r in rows:
        error=string();statuses=[(word(),string()) for _ in range(3)];assert statuses==[(1,''),(1,''),(1,'')],(r,statuses)
        phase=word();clock=[scalar(),scalar()];attrs=[]
        for _ in range(word()):
            n=tuple(word() for _ in range(5));kind,status,sequence,begin,end=[word() for _ in range(5)];payload=[word() if word() else None for _ in range(6)];attrs.append(dict(name=n,kind=kind,status=status,sequence=sequence,begin=begin,end=end,payload=payload))
        phases.setdefault(r['index'],set()).add(r['phase']);traces.append(dict(row=r,error=error,phase=phase,clock=clock,attrs=attrs))
    assert at==len(data);trace_path.write_text(json.dumps(traces,indent=2)+'\n');assert all(p=={0,1,2} for p in phases.values()),phases
    for e in ('MatchAirTime requires completed OffBoard output','MatchAirTime requires completed OffBoard80','AddRunoutAttribs speed12 has no successful Begin observation'):
        assert any(e in t['error'] for t in traces),e
    assert traces[0]['clock'][0]['ok']==0 and any(t['clock'][0]['ok']==1 for t in traces)
    effects={}
    for p in PROOFS:
        values={a['payload'][0] for t in traces for a in t['attrs'] if a['name']==tuple(name(p))};assert len(values)>=3,(p,values);effects[p]=len(values)
    assert len({t['phase'] for t in traces})>=5
    # Find the uniquely authored first-skip/next-seek triplet and verify the
    # original clock before reporting coverage. Float values are source inputs.
    start=next(i for i,t in enumerate(traces) if t['row']['index']==2 and t['row']['phase']==0 and t['row']['cadence']==.3)
    assert traces[start+1]['clock'][0]==dict(ok=1,value=fbits(0.))
    assert traces[start+2]['clock'][0]==dict(ok=1,value=fbits(1.5))
    successful_ends=[t for t in traces if t['row']['index']==3 and t['row']['phase']==2 and t['row']['inject'] and not t['error']]
    assert len(successful_ends)==32
    assert all(next(a['payload'][0] for a in t['attrs'] if a['name']==tuple(name(PROOFS[6])))!=fbits(-1) for t in successful_ends)
    return dict(commands=len(rows),factory_configs=len(phases),observable_values=effects,runout_republished_ends=len(successful_ends))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('assets','metadata','output','target-dir'):p.add_argument('--'+n,type=Path,required=True)
    args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for marker in ('result.json','first-divergence.json'):(output/marker).unlink(missing_ok=True)
    sources=('SimulationMath','AnimationName','Intents','Input','InputIntentions','NameId','Settings','Graph','GraphController','GraphConditions','GraphGestureOperations',
        'AnimationSamples','AnimationMetadata','AnimationPlayback','AnimationPlaybackParameters','AnimationTrees','AnimationChannels','MotionAnimation','GraphMotionName','WipeoutOrientation','GraphMotionOffboardTiming')
    cpp,rust=build_probes(output,args.target_dir,'motion_offboard_timing',sources);graph,configs=fixture();reference,simulation=output/'operations.reference-graph',output/'operations.graph';reference.write_bytes(original_graph(graph));simulation.write_bytes(converter.encode_graph(converter.read_graph(reference)))
    md=fixture_metadata();metadata_json,metadata_simulation=output/'fixture.json',output/'fixture.skate';metadata_json.write_text(json.dumps(md));metadata_simulation.write_bytes(metadata_converter.pack_metadata(md));inputs,rows=corpus()
    (output/'input.bin').write_bytes(inputs);(output/'authored-commands.json').write_text(json.dumps(rows,indent=2)+'\n')
    expected=subprocess.check_output([str(rust),str(args.assets),str(reference),str(metadata_json)],input=inputs);actual=subprocess.check_output([str(cpp),str(args.metadata/'bank-0.skate'),str(args.metadata/'bank-1.skate'),str(metadata_simulation),str(simulation)],input=inputs)
    (output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual)
    if actual!=expected:
        first=next((i for i,(a,b) in enumerate(zip(actual,expected)) if a!=b),min(len(actual),len(expected)));report=dict(passed=False,first_byte=first,reference_length=len(expected),cpp_length=len(actual),reference_hex=expected[max(0,first-16):first+32].hex(),cpp_hex=actual[max(0,first-16):first+32].hex());(output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
    result=coverage(expected,rows,output/'original-trace.json');report=dict(passed=True,output_bytes=len(expected),output_sha256=hashlib.sha256(expected).hexdigest(),coverage=result,
        comparison='exact actual full original MotionHost cadence/air-time/runout factories and lifecycle, optional-owner absence, retained captures, first-update seek and standard sqrt translation bound, original angle projection/wrap, real applied parameters and original End runout republishing',
        limitations='Full controller registration and live physical producers are separate. Exhaustive malformed parser diagnostics are not covered.',reference_provenance='reference-provenance.json');(output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
