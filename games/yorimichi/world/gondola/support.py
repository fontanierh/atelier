"""Complete owned footprint coverage and relief from final terrain triangles."""
import math
import numpy as np
from solid_mesh import signed_area, ear_clip
from gondola.clearance import clip

AREA_TOL=1e-9


def area(poly):
    return abs(signed_area(np.asarray(poly)[:,:2]-np.asarray(poly)[0,:2])) if len(poly)>=3 else 0.


def halfplane(poly,a,b,inside=True):
    augmented=[np.r_[(b[0]-a[0])*(q[1]-a[1])-(b[1]-a[1])*(q[0]-a[0]),q] for q in poly]
    return [q[1:] for q in clip(augmented,0,0,inside)]


def intersection(poly,mask):
    mask=np.asarray(mask,float)
    if signed_area(mask[:,:2]-mask[0,:2])<0:mask=mask[::-1]
    result=list(np.asarray(poly,float))
    for a,b in zip(mask,np.roll(mask,-1,axis=0)):
        if np.linalg.norm(b[:2]-a[:2])<1e-12:continue
        result=halfplane(result,a,b)
        if not result:break
    return result


def subtract(poly,mask):
    """Convex polygon difference as disjoint convex pieces; xyz is retained."""
    mask=np.asarray(mask,float)
    if area(mask)<=AREA_TOL:return [list(poly)]
    if signed_area(mask[:,:2]-mask[0,:2])<0:mask=mask[::-1]
    result=[];remaining=list(poly)
    for a,b in zip(mask,np.roll(mask,-1,axis=0)):
        if np.linalg.norm(b[:2]-a[:2])<1e-12:continue
        outside=halfplane(remaining,a,b,False)
        if area(outside)>AREA_TOL:result.append(outside)
        remaining=halfplane(remaining,a,b)
        if area(remaining)<=AREA_TOL:break
    return result


def rectangle(bounds):
    x0,y0,x1,y1=bounds
    return np.array([[x0,y0],[x1,y0],[x1,y1],[x0,y1]],float)


def candidates(surface,polygon):
    lo,hi=np.asarray(polygon)[:,:2].min(0),np.asarray(polygon)[:,:2].max(0)
    # The Surface's complete nonvertical face bins preserve product identities.
    # Include vertical faces independently: they bound relief but cannot cover.
    ids=set()
    for x in range(math.floor(lo[0]/surface.cell),math.floor(hi[0]/surface.cell)+1):
        for y in range(math.floor(lo[1]/surface.cell),math.floor(hi[1]/surface.cell)+1):
            ids.update(surface.bins.get((x,y),()))
    tri=surface.triangles
    if not hasattr(surface,'_gondola_vertical_ids'):
        surface._gondola_vertical_ids=np.flatnonzero(surface.normals[:,2]==0)
    vertical=surface._gondola_vertical_ids
    if len(vertical):
        values=tri[vertical];low,high=values[:,:,:2].min(1),values[:,:,:2].max(1)
        ids.update(vertical[np.all(high>=lo,axis=1)&np.all(low<=hi,axis=1)])
    return tri[sorted(ids)]


def clipped_coverage(triangles,polygon):
    """Refuse every uncovered interior, independently of corner/centre samples."""
    polygon=np.asarray(polygon,float)
    pending=[list(polygon)];pieces=[]
    for tri in triangles:
        cut=intersection(tri,polygon)
        if not cut:continue
        pieces.append(cut)
        if area(cut)>AREA_TOL and pending:
            pending=[part for old in pending for part in subtract(old,cut)]
    if sum(area(p) for p in pending)>AREA_TOL:
        raise ValueError('Missing owned terrain inside support footprint')
    if not pieces:
        raise ValueError('No owned terrain under support footprint')
    return pieces


def ground_ceiling(triangles,polygon):
    triangles=np.asarray(triangles,float)
    if not len(triangles):raise ValueError('No owned terrain under support footprint')
    lo,hi=np.asarray(polygon).min(0),np.asarray(polygon).max(0)
    low,high=triangles[:,:,:2].min(1),triangles[:,:,:2].max(1)
    pieces=clipped_coverage(triangles[np.all(high>=lo,axis=1)&np.all(low<=hi,axis=1)],polygon)
    return max(float(np.asarray(p)[:,2].max()) for p in pieces)


def owned_triangles(G,polygon,*,contact=True):
    """Partition one convex footprint by declared owners and explicit trail overlay.

    Base coverage is mandatory even under the trail. Trail-covered base portions
    are removed before contact relief is measured; neighbours never fill holes.
    """
    polygon=np.asarray(polygon,float)
    owner_masks={key:[intersection(polygon,rectangle(bounds))] for key,bounds in G.bounds.items()}
    # Apron is explicitly outside Belmonte's own rectangular final product.
    owner_masks['apron']=[part for old in owner_masks['apron'] if area(old)>AREA_TOL
                          for part in subtract(old,rectangle(G.bounds['valley']))]
    pending=[list(polygon)];result=[]
    for key,masks in owner_masks.items():
        for mask in masks:
            if area(mask)<=AREA_TOL:continue
            pending=[part for old in pending for part in subtract(old,mask)]
            base=clipped_coverage(candidates(G.surfaces[key],mask),mask)
            overlays=[intersection(t,mask) for t in candidates(G.trail,mask)] if contact else []
            overlays=[p for p in overlays if area(p)>AREA_TOL]
            if overlays:
                base=[part for old in base for part in _without(old,overlays)]
            for piece in base+overlays:
                result.extend([[piece[0],piece[i],piece[i+1]] for i in range(1,len(piece)-1)])
    if sum(area(p) for p in pending)>AREA_TOL:
        raise ValueError('Footprint leaves the declared terrain owner bands')
    return np.asarray(result,float).reshape(-1,3,3)


def _without(poly,masks):
    pieces=[poly]
    for mask in masks:
        pieces=[part for old in pieces for part in subtract(old,mask)]
    return pieces


def owned_range(G,polygon,*,contact=True):
    values=owned_triangles(G,polygon,contact=contact)[:,:,2]
    if not values.size:raise ValueError('Missing complete owned footprint')
    return float(values.min()),float(values.max())


def floor_intrusion(G,polygon,heights):
    """@cc [owner:fontanierh,label:correctness] complete-access-floor-ground
    Every point of an access floor MUST have final owned ground coverage.
    Intrusion MUST compare that ground against the actual generated floor cap
    triangles at all intersection vertices, including trail-owned contact.
    """
    polygon=np.asarray(polygon,float)
    heights=np.broadcast_to(np.asarray(heights,float),(len(polygon),))
    if polygon.shape!=(len(polygon),2) or len(polygon)<3 or not np.isfinite(polygon).all() or not np.isfinite(heights).all():
        raise ValueError('Invalid access floor geometry')
    if signed_area(polygon-polygon[0])<0:
        polygon=polygon[::-1];heights=heights[::-1]
    ground=owned_triangles(G,polygon)
    worst=-float('inf')
    for indices in ear_clip(polygon):
        indices=list(indices);xy=polygon[indices];z=heights[indices]
        slope=np.linalg.solve(xy[1:]-xy[0],z[1:]-z[0])
        for triangle in ground:
            overlap=intersection(triangle,xy)
            if not overlap:continue
            points=np.asarray(overlap)
            roof=z[0]+(points[:,:2]-xy[0])@slope
            worst=max(worst,float(np.max(points[:,2]-roof)))
    if not math.isfinite(worst):raise ValueError('Missing complete access-floor intersection proof')
    return worst
