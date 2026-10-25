"""Selected committed Hippodrome structure."""
import sys
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[i]) for i in (2,1)]
from hippodrome.structure_data import structure
from hippodrome import layout as L
from hippodrome.planner import main

def construct():
    data,_,info=structure('judges_tower',L.STRUCTURES['judges_tower'])
    return data,info

if __name__=="__main__":main('SM_HD_JudgesTower',construct)
