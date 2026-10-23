"""Original continuous rotor clearance proof over complete independently planned source data."""
import json
import math
from pathlib import Path
import numpy as np
from atelier import mesh_ir
from atelier.atomic_files import atomic_json
from region_mesh_parts import validate
from zeppelin.layout import PROPELLER_CENTERS,PROPELLER_RADIUS


def points(root):
    value=validate(root);rows=[]
    for row in value['pieces']:
        meta,piece=mesh_ir.decode((Path(root)/row['payload']).read_bytes())
        matrix=np.asarray(meta['matrix'])
        rows.append(piece['positions']@matrix[:3,:3].T+matrix[:3,3])
    return np.concatenate(rows)


def check(out):
    out=Path(out);root=out/'planned_exports'/'zeppelin'
    hull=points(root/'ZP_Airship');rotor=points(root/'ZP_Propeller')
    radius=float(np.linalg.norm(rotor[:,1:],axis=1).max())
    assert abs(radius-PROPELLER_RADIUS)<1e-5
    results=[]
    for x,y,z in PROPELLER_CENTERS:
        side=1 if y>0 else -1;hull_edge=float((side*hull[:,1]).max())
        clearance=abs(y)-radius-hull_edge
        assert clearance>.30,f'Rotor sweep approaches hull: {clearance}'
        sampled=math.inf
        for angle in np.linspace(0,math.tau,720,endpoint=False):
            rotated_y=y+rotor[:,1]*math.cos(angle)-rotor[:,2]*math.sin(angle)
            sampled=min(sampled,float((side*rotated_y).min())-hull_edge)
        assert sampled>=clearance-1e-6
        results.append(dict(center=[x,y,z],guaranteed_hull_clearance_m=clearance,sampled_clearance_m=sampled,angles_checked=720))
    atomic_json(out/'zeppelin_rotor_clearance.json',dict(passed=True,radius_m=radius,rotors=results,
        method='Continuous swept cylinder separated from every hull vertex; also sampled every half degree'))
