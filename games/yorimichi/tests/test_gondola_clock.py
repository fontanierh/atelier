"""The cabin clock stays on the fitted path and never moves during door dwell."""
import math
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'world'))
from gondola.clock import point_at, arc_lengths, state


def test_cyclic_constant_acceleration_and_stationary_dwell():
    points=[[0,0,0],[10,0,0],[10,10,0],[0,0,0]]
    clock={'points':points,'arc':arc_lengths(points),'cycle_s':24.,
           'intervals':[[0.,4.,0.,0.,0.,0.],[4.,14.,0.,10.,0.,.2],[14.,24.,10.,20.,2.,-.2]],
           'stops':[{'start':0.,'end':4.}]}
    for t in (0,1,3.99,24,49):
        result=state(clock,t)
        assert result['speed']==0 and result['stop']==0 and result['point']==points[0]
    assert state(clock,9)['arc']==pytest.approx(2.5)
    assert state(clock,19)['arc']==pytest.approx(17.5)
    assert state(clock,-5)==state(clock,19)


def test_arc_sampling_keeps_vertical_rope_and_closed_boundary():
    points=[[0,0,0],[0,0,5],[5,0,5],[0,0,0]]
    arc=arc_lengths(points)
    assert point_at(points,arc,2.5)==[0.,0.,2.5]
    assert point_at(points,arc,arc[-1])==points[0]
    with pytest.raises(ValueError):arc_lengths([[0,0,0],[0,0,0],[1,0,0],[0,0,0]])


def test_real_kit_circuit_has_four_stopped_berths_and_smooth_cyclic_motion():
    from gondola_kit_fixture import gondola_modules
    from gondola.line import station_frame,closed_circuit
    from gondola.clock import prepare
    import numpy as np
    with gondola_modules('rope',pure=True) as kit:
        loop=kit.rope.station_loop(3.,3.77,3.77,7.6,.045).pts
    a=station_frame((0.,0.),(100.,0.),0.,7.6)
    b=station_frame((100.,0.),(0.,0.),20.,7.6)
    profile=np.array([[.6,3.77],[50.,25.],[99.4,23.77]])
    path=closed_circuit(profile,a,b,loop,6.)
    stations=[]
    for name,frame,mouth in (('a',a,(0.,0.)),('b',b,(100.,0.))):
        origin,along,lateral,z=frame
        stations.append({'id':name,'origin':origin,'along':along,'lateral':lateral,'rope_z':z+3.77,
                         'mouth_grip':[*mouth,z+3.77],'berth_x':3.4,'gauge':6.,'mouth_x':7.6})
    table=prepare(path,stations)
    assert len(table['stops'])==4
    from gondola.clock import spacing
    assert spacing(table,2)['pass']
    with pytest.raises(ValueError,match='headway'):
        spacing(table,32)
    for stop in table['stops']:
        results=[state(table,stop['start']+t) for t in (0.,3.,8.,11.99)]
        assert all(row['speed']==0 and row['arc']==stop['arc'] and row['stop']>=0 for row in results)
    rows=table['intervals']
    for first,last in zip(rows,rows[1:]):
        assert first[1]==pytest.approx(last[0])
        assert first[3]==pytest.approx(last[2])
        assert first[4]+first[5]*(first[1]-first[0])==pytest.approx(last[4],abs=1e-9)
    for row in rows:
        assert abs(row[5])<=.350001 and 0<=row[4]<=5.
