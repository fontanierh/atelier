"""Conservative sweep against entire obstacle triangles, preserving tall edges."""
import numpy as np


def clip(poly, axis, limit, keep_above):
    out = []
    for a,b in zip(poly,poly[1:]+poly[:1]):
        da,db = a[axis]-limit,b[axis]-limit
        ina,inb = (da >= 0,db >= 0) if keep_above else (da <= 0,db <= 0)
        if ina:
            out.append(a)
        if ina != inb:
            out.append(a+(b-a)*(da/(da-db)))
    return out


def riding_clearance(triangles, origin, direction, profile, *, lateral, half_length, drop):
    """@cc [owner:fontanierh,label:correctness] whole-triangle-riding-clearance
    Every obstacle triangle intersecting the declared corridor and cabin length
    MUST participate, including vertical faces and triangles whose vertices lie
    outside it. Clip complete triangles, never substitute a sampled height grid.
    The reported minimum MUST conservatively bound the supplied linear rope
    profile using its interior knots as well as interval ends.
    The floor is the actual piecewise-linear rope sample minus the complete
    floor/skirt drop. Its minimum across an expanded obstacle interval occurs
    at an existing rope knot or interval end. The clipped triangle's maximum
    occurs at a clipped polygon vertex. Comparing those extrema is conservative
    even when the obstacle and cabin extrema occur at different positions.
    """
    tri = np.asarray(triangles,float)
    direction = np.asarray(direction,float)
    origin,profile = np.asarray(origin,float),np.asarray(profile,float)
    if (tri.ndim != 3 or tri.shape[1:] != (3,3) or not np.isfinite(tri).all() or
            direction.shape != (2,) or not np.isfinite(direction).all() or
            not np.isclose(np.linalg.norm(direction),1.,atol=1e-10,rtol=0) or
            origin.shape != (2,) or not np.isfinite(origin).all() or
            profile.ndim != 2 or profile.shape[1] != 2 or len(profile)<2 or
            not np.isfinite(profile).all() or not np.all(np.diff(profile[:,0])>0) or
            not np.isfinite([lateral,half_length,drop]).all() or
            lateral<=0 or half_length<0 or drop<0):
        raise ValueError('Clearance requires finite triangles, a unit route axis and an ordered rope profile')
    normal = np.array([-direction[1],direction[0]])
    local = np.empty_like(tri)
    delta = tri[:,:,:2]-origin
    local[:,:,0] = delta@direction
    local[:,:,1] = delta@normal
    local[:,:,2] = tri[:,:,2]
    low,high = local.min(1),local.max(1)
    start,end = profile[0,0],profile[-1,0]
    ids = np.flatnonzero((high[:,0]>=start-half_length)&(low[:,0]<=end+half_length)&
                         (high[:,1]>=-lateral)&(low[:,1]<=lateral))
    floor = profile[:,1]-drop
    best = float('inf'); worst = None; tested = 0
    for index in ids:
        polygon = list(local[index])
        for axis,limit,above in [(0,start-half_length,True),(0,end+half_length,False),
                                 (1,-lateral,True),(1,lateral,False)]:
            polygon = clip(polygon,axis,limit,above)
            if not polygon:
                break
        if not polygon:
            continue
        q = np.asarray(polygon)
        lo = max(start,float(q[:,0].min()-half_length))
        hi = min(end,float(q[:,0].max()+half_length))
        a,b = np.searchsorted(profile[:,0],[lo,hi])
        zmin = min(float(np.interp(lo,profile[:,0],floor)),float(np.interp(hi,profile[:,0],floor)))
        if b>a:
            zmin = min(zmin,float(floor[a:b].min()))
        obstacle = float(q[:,2].max())
        gap = zmin-obstacle;tested += 1
        if gap < best:
            best = gap
            worst = dict(triangle=int(index),interval=[lo,hi],floor_min=zmin,obstacle_max=obstacle)
    return dict(triangles_tested=tested,minimum_m=best if tested else None,worst=worst)
