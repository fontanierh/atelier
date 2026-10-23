"""Selected Hippodrome logical geometry."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from hippodrome.track_data import track as geometry
from hippodrome.mesh_data import encoded_glb
from hippodrome.query_context import height
from hippodrome.planner import main

def construct():
    mesh=geometry()
    return encoded_glb('SM_HD_Track',mesh.p,mesh.n,mesh.t,mesh.i,'HD_Dirt')

if __name__=="__main__":main('SM_HD_Track',construct)
