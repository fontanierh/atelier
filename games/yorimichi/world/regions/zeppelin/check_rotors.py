"""Validate the complete rotor sweep against the actual generated hull mesh."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import json, math, sys
from pathlib import Path
import bpy
import numpy as np

ROOT=yori.REGIONS
from zeppelin.layout import PROPELLER_CENTERS, PROPELLER_RADIUS

def check():
    hull=np.array([tuple(v.co) for v in bpy.data.objects['ZP_Airship'].data.vertices])
    rotor=np.array([tuple(v.co) for v in bpy.data.objects['ZP_Propeller'].data.vertices])
    radius=float(np.linalg.norm(rotor[:,1:],axis=1).max())
    assert abs(radius-PROPELLER_RADIUS)<1e-5
    results=[]
    for x,y,z in PROPELLER_CENTERS:
        side=1 if y>0 else -1
        hull_edge=float((side*hull[:,1]).max())
        # A separating plane proves clearance at EVERY angle, including edges and
        # face interiors. It is more conservative than an angle-sampled collision test.
        guaranteed_clearance=abs(y)-radius-hull_edge
        assert guaranteed_clearance>.30, f'Rotor sweep approaches hull: {guaranteed_clearance}'
        sampled_clearance=math.inf
        for a in np.linspace(0,math.tau,720,endpoint=False):
            rotated_y=y+rotor[:,1]*math.cos(a)-rotor[:,2]*math.sin(a)
            sampled_clearance=min(sampled_clearance,float((side*rotated_y).min())-hull_edge)
        assert sampled_clearance>=guaranteed_clearance-1e-6
        results.append(dict(center=[x,y,z],guaranteed_hull_clearance_m=guaranteed_clearance,
                            sampled_clearance_m=sampled_clearance,angles_checked=720))
    report=dict(passed=True,radius_m=radius,rotors=results,
                method='Continuous swept cylinder separated from every hull vertex; also sampled every half degree')
    (yori.OUT/'zeppelin/rotor-clearance.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
    return report

if __name__=='__main__':check()
