"""Site support envelopes over whole final terrain triangles."""
import numpy as np
from solid_mesh import signed_area
from gondola.clearance import clip


def ground_ceiling(triangles, polygon):
    """Bound ground throughout a convex support footprint, including tall edges.

    The caller supplies exactly one owned final terrain product. Complete
    intersecting triangles participate, even when every vertex is outside.
    """
    polygon=np.asarray(polygon,float)
    if signed_area(polygon)<0:
        polygon=polygon[::-1]
    triangles=np.asarray(triangles,float)
    low,high=triangles[:,:,:2].min(1),triangles[:,:,:2].max(1)
    lo,hi=polygon.min(0),polygon.max(0)
    selected=triangles[(high[:,0]>=lo[0])&(low[:,0]<=hi[0])&(high[:,1]>=lo[1])&(low[:,1]<=hi[1])]
    result=-float('inf')
    for triangle in selected:
        cut=list(triangle)
        for a,b in zip(polygon,np.roll(polygon,-1,axis=0)):
            # Reuse the shared dimension-preserving half-plane clipper. Carry
            # world xyz through every intersection, including vertical faces.
            augmented=[np.r_[(b[0]-a[0])*(q[1]-a[1])-(b[1]-a[1])*(q[0]-a[0]),q] for q in cut]
            cut=[q[1:] for q in clip(augmented,0,0,True)]
            if not cut:
                break
        if cut:
            result=max(result,float(np.asarray(cut)[:,2].max()))
    if not np.isfinite(result):
        raise ValueError('No owned terrain under support footprint')
    return result
