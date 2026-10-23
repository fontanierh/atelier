"""Selected committed Hippodrome structure."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from hippodrome.structure_data import structure
from hippodrome import layout as L
from hippodrome.planner import main

def construct():
    data,_,info=structure('tote_board',L.STRUCTURES['tote_board'])
    return data,info

if __name__=="__main__":main('SM_HD_ToteBoard',construct)
