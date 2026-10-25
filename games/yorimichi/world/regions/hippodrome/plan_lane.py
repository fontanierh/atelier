"""Selected Hippodrome logical geometry."""
import sys
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[i]) for i in (2,1)]
from hippodrome.lane_data import construct as geometry
from hippodrome.mesh_data import encoded_glb
from hippodrome.query_context import height
from hippodrome.planner import main

def construct():
    mesh=geometry(height())
    return encoded_glb('SM_HD_Lane',mesh.p,mesh.n,mesh.t,mesh.i,'HD_Dirt')

if __name__=="__main__":main('SM_HD_Lane',construct)
