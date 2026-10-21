"""Run the physical driver's actual wait branch at early and closing dwell phases."""
import ast
import math
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize('line_index,cabins', [(0,12),(1,12),(2,4)])
@pytest.mark.parametrize('direction', [0,1])
@pytest.mark.parametrize('elapsed,boards', [(2.,True),(9.32,False)])
def test_wait_branch_requires_open_dwell_budget(line_index,cabins,direction,elapsed,boards):
    path=Path(__file__).resolve().parents[1]/'scenarios/gondola_roundtrip_live.py'
    tree=ast.parse(path.read_text())
    functions=[node for node in tree.body if isinstance(node,ast.FunctionDef) and
               node.name in ('aboard','boarding_candidate','step')]
    data={'lines':[{'id':'L'+str(i+1),'cabins':count} for i,count in enumerate((12,12,4))]}
    spec=data['lines'][line_index];station=('a','b')[direction]
    spec['clock']={'cycle_s':400.,'stops':[{'station':station,'side':1,'start':100.,'end':112.}]}
    # Use a nonzero local cabin phase and a cycle wrap. StateJson indices span
    # all lines while each service clock offsets only that line's local index.
    local=cabins-1;first=sum(row['cabins'] for row in data['lines'][:line_index])
    state={'time':100.+elapsed-400.*local/cabins+800.,'riders':[],
           'cabins':[{'index':first+local,'line':spec['id'],'station':station,'side':1,'door':1. if boards else .999175926}]}
    stage='wait_'+station
    S={'direction':direction,'stage':stage,'stage_time':0.,'elapsed':0.,
       'next_record':float('inf'),'next_photo':float('inf'),'board_tail':[[0,0,0],[0,200,0]]}
    def route(points,name):S.update(route=points,stage=name)
    namespace={'math':math,'DATA':data,'SPEC':spec,'LINE':spec['id'],'FIRST':'a','LAST':'b','S':S,
               'PAWN':SimpleNamespace(get_name=lambda:'Rider'),'state':lambda:state,'route':route,
               'live':SimpleNamespace(drive=lambda *args,**kwargs:None),
               'time':SimpleNamespace(monotonic=lambda:0.),'START':0.}
    exec(compile(ast.Module(body=functions,type_ignores=[]),str(path),'exec'),namespace)
    namespace['step'](1/60)
    assert S['stage']==('boarding_'+station if boards else stage)
    if boards:assert S['cabin']==first+local and S['route']==S['board_tail']
