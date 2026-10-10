#!/usr/bin/env python3
"""Bounded live ActionHost gesture registration/selection/lifecycle parity.

Uses the unchanged production Rust ActionHost and Controller staged by the
existing graph baseline. Run compilation through the root's safety guard.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import struct
import subprocess
from check_graph_intents_parity import Record, TraceReader, build_probes, converter, fbits
from check_graph_parity import attribute, element, original_graph
from check_graph_gesture_parity import authored_rows

GROUPS=('Square','Nose','Tail','90Nose','90Tail','N90Nose','N90Tail')


def fixture(group, override):
    attrs=[attribute('group',group)]
    if override is not None:
        attrs.append(attribute('override',override))
    return element('state','root',children=[
        element('state','active',children=[
            element('expression',attributes=[attribute('op','and')],children=[
                element('condition','HasGestureIntent',[attribute('mask','always'),attribute('group',group)]),
                element('expression',attributes=[attribute('op','not')],children=[
                    element('condition','IsInLocomotion',[attribute('mask','always')])])]),
            element('behaviour','CreateTrickIntentFromGesture',attrs)]),
        element('state','idle')])


def query_names():
    names={name for group in authored_rows() for row in group if row[0] in ('Kickflip','N_Kickflip') for name in row[1:3]}
    names.update(('KickflipHold','HeelflipHold','N_KickflipHold','N_HeelflipHold','Shared',''))
    names.update('U_'+name for name in tuple(names))
    names.add('DarkCatch')
    return sorted(names)


def inputs(case,names):
    w=Record();w.words((1,6,len(names)))
    for name in names:
        w.raw(name)
    w.word(64)
    for tick in range(64):
        w.word(tick==63);w.scalar(1/60)
        values=[]
        if 5 <= tick%16 <= 11:
            key='N_Kickflip' if case//3 in (1,3,5) else 'Kickflip'
            values=[((key,key.upper(),key+'\0tail')[case%3],0x7fc12345 if tick%2 else 0)]
            if tick>=32:
                values.append(('Underflip',0))
            if case%3==1:
                values.append(('DarkCatch',0))
        w.word(len(values))
        for name,bits in values:
            w.raw(name);w.word(bits)
        w.word(0 if case%3==2 and tick==5 else 1+2*(case%2))
        w.word(1);w.optional(0.)
    return bytes(w.data)


def decode(data,names,case):
    r=TraceReader(data);assert r.word()==6
    frames=[]
    for tick in range(64):
        frame=dict(tick=tick,dt_bits=r.word(),current=r.word(),last=r.word())
        frame['times']=[r.optional() for _ in range(r.word())]
        frame['active']=[(r.word(),r.word()) for _ in range(r.word())]
        frame['map_size']=r.word();frame['values']={name:r.optional() for name in names};frame['error']=r.text()
        frames.append(frame)
    r.finished()
    assert {1,2} <= {frame['current'] for frame in frames},'Gesture condition never selected both states'
    assert len({handle for frame in frames for _,handle in frame['active']})>=4,'Gesture behavior did not reallocate'
    errors=[frame for frame in frames if frame['error']]
    if case%3==2:
        assert len(errors)==1 and errors[0]['tick']==5 and errors[0]['error']=='CreateTrickIntentFromGesture requires published skater stance'
    else:
        assert not errors
    assert any(frame['map_size']>0 for frame in frames),'Gesture registration emitted no trick'
    holds=sum(any(frame['values'][name] is not None for name in names if name.endswith('Hold')) for frame in frames)
    if case%3==0:
        assert holds>0,'Launch never advanced to a retained hold intent'
    for frame in frames:
        if frame['tick']%16>=12:
            assert frame['map_size']==0,'Gesture End left owned launch/hold/DarkCatch intents'
    assert not frames[-1]['active'] and frames[-1]['map_size']==0,'EndAll did not clean gesture instance'
    return dict(states=[1,2],instances=len({handle for frame in frames for _,handle in frame['active']}),
                emitting_frames=sum(frame['map_size']>0 for frame in frames),hold_frames=holds,missing_stance_errors=len(errors)),frames


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--target-dir',type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    cpp,rust=build_probes(output,args.target_dir)
    settings=output/'settings.simulation';settings.write_bytes(converter.encode_settings(args.assets/'private/stock/skater-collections.json'))
    names=query_names();results=[]
    for case in range(21):
        reference=output/f'host-{case}.reference-graph';reference.write_bytes(original_graph(fixture(GROUPS[case//3],(None,'Shared','')[case%3])))
        simulation=output/f'host-{case}.graph';simulation.write_bytes(converter.encode_graph(converter.read_graph(reference)))
        data=inputs(case,names);(output/f'host-{case}-input.bin').write_bytes(data)
        expected=subprocess.check_output([str(rust),'stream',str(settings),str(args.assets),str(reference)],input=data)
        actual=subprocess.check_output([str(cpp),'stream',str(settings),str(args.assets),str(simulation)],input=data)
        if actual!=expected:
            (output/f'host-{case}-reference.bin').write_bytes(expected);(output/f'host-{case}-cpp.bin').write_bytes(actual)
            first=next((i for i,(a,b) in enumerate(zip(actual,expected)) if a!=b),min(len(actual),len(expected)))
            raise AssertionError(dict(case=case,first_byte=first,reference_bytes=len(expected),cpp_bytes=len(actual)))
        coverage,frames=decode(expected,names,case)
        (output/f'host-{case}-original-trace.json').write_text(json.dumps(frames,indent=2)+'\n')
        results.append(dict(case=case,group=GROUPS[case//3],output_bytes=len(expected),coverage=coverage))
    report=dict(passed=True,fixtures=21,live_ticks=1344,results=results,
                comparison='byte-exact original production ActionHost and Controller; authored registration, membership, launch/hold, reallocation and cleanup',
                limitations='Remaining physical-backed ActionGraph conditions and full actor scheduling remain separate slices.')
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':
    main()
