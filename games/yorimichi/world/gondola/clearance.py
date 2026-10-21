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


class StructureClearance:
    """@cc [owner:fontanierh,label:correctness] final-world-structure-clearance
    Final visible AND actual collision triangles MUST participate independently.
    Complete static bounding volumes MUST refuse intersections; a support may
    not silently acquire masonry as a bearing surface. Moving proofs MUST cover
    every segment and the full declared horizontal envelope, including loops.
    Ground ownership and its coverage/embedding rules MUST remain separate.
    """
    MARGIN = .05

    def __init__(self, arrays, bounds):
        self.bounds = np.asarray(bounds,float)
        self.arrays = {key:np.asarray(arrays[key],float).reshape(-1,3,3) for key in ('visual','collision')}
        if self.bounds.shape != (4,) or not np.isfinite(self.bounds).all() or any(not np.isfinite(t).all() for t in self.arrays.values()):
            raise ValueError('Invalid final structure query geometry')
        self.extents = {key:(t.min(1),t.max(1)) for key,t in self.arrays.items()}

    def require_bounds(self, low, high):
        if (low[0] < self.bounds[0] or low[1] < self.bounds[1] or
                high[0] > self.bounds[2] or high[1] > self.bounds[3]):
            raise ValueError('Structure query leaves its declared extraction footprint')

    def static(self, vertices, *, require_bounds=False, plan_clear=False):
        vertices = np.asarray(vertices,float)
        if vertices.ndim != 2 or vertices.shape[1] != 3 or not len(vertices) or not np.isfinite(vertices).all():
            raise ValueError('Static structure proof needs complete finite vertices')
        low,high = vertices.min(0)-self.MARGIN,vertices.max(0)+self.MARGIN
        if require_bounds:
            self.require_bounds(low,high)
        counts = {}
        for key,triangles in self.arrays.items():
            lo,hi = self.extents[key]
            dimensions=2 if plan_clear else 3
            indices = np.flatnonzero((hi[:,:dimensions]>=low[:dimensions]).all(1)&
                                     (lo[:,:dimensions]<=high[:dimensions]).all(1))
            count = 0
            for index in indices:
                polygon = list(triangles[index])
                for axis in range(dimensions):
                    polygon = clip(polygon,axis,low[axis],True)
                    if not polygon:break
                    polygon = clip(polygon,axis,high[axis],False)
                    if not polygon:break
                if polygon:
                    raise ValueError(f'Static ropeway volume intersects final {key} structure triangle {index}')
                count += 1
            counts[key] = count
        return {'pass':True,'representation':'complete-expanded-static-box','margin_m':self.MARGIN,
                'bounds_m':[low.tolist(),high.tolist()],'candidates':counts,'plan_clear':plan_clear}

    def path(self, points, *, radius, drop):
        points = np.asarray(points,float)
        if (points.ndim != 2 or points.shape[1] != 3 or len(points)<2 or
                not np.isfinite(points).all() or not np.isfinite(radius) or radius<=0 or
                not np.isfinite(drop) or drop<0):
            raise ValueError('Invalid whole-curve structure envelope')
        self.require_bounds(points[:,:2].min(0)-radius,points[:,:2].max(0)+radius)
        results = {}
        for key,triangles in self.arrays.items():
            low,high = self.extents[key]
            begin,end = points.min(0)-radius,points.max(0)+radius
            selected = triangles[(high[:,:2]>=begin[:2]).all(1)&(low[:,:2]<=end[:2]).all(1)]
            best = float('inf');tested = 0
            for a,b in zip(points,points[1:]):
                length = float(np.linalg.norm(b[:2]-a[:2]))
                if length<=1e-10:
                    raise ValueError('Structure curve has a vertical/duplicate plan segment')
                proof = riding_clearance(selected,a[:2],(b[:2]-a[:2])/length,
                                         np.array([[0,a[2]],[length,b[2]]]),
                                         lateral=radius,half_length=radius,drop=drop)
                tested += proof['triangles_tested']
                if proof['minimum_m'] is not None:
                    best = min(best,proof['minimum_m'])
            if best < self.MARGIN:
                raise ValueError(f'Whole ropeway curve conflicts with final {key} structures: {best:.6f}m')
            results[key] = {'triangles_tested':tested,'minimum_m':best if tested else None}
        return {'pass':True,'representation':'complete-segment-envelope','margin_m':self.MARGIN,
                'segments':len(points)-1,'radius_m':radius,'drop_m':drop,'results':results}

    def span(self, profile, origin, direction, *, radius, gauge, drop):
        """Both full tracks, with complete interior knots and triangle extrema."""
        profile = np.asarray(profile,float)
        origin,direction = np.asarray(origin,float),np.asarray(direction,float)
        ends = origin+profile[[0,-1],0,None]*direction
        self.require_bounds(ends.min(0)-gauge/2-radius,ends.max(0)+gauge/2+radius)
        results = {}
        for key,triangles in self.arrays.items():
            proof = riding_clearance(triangles,origin,direction,profile,
                                     lateral=gauge/2+radius,half_length=radius,drop=drop)
            if proof['minimum_m'] is not None and proof['minimum_m']<6.:
                raise ValueError(f'Ropeway span conflicts with final {key} structures: {proof}')
            results[key] = proof
        return {'pass':True,'representation':'complete-segment-envelope','margin_m':self.MARGIN,
                'segments':len(profile)-1,'radius_m':radius,'drop_m':drop,'required_clearance_m':6.,'results':results}


def structure_envelope(meshes, pivot, door_offsets):
    """Continuous bound for plumb parts and the freely rotating grip.

    hang_frame translates the plumb frame by G*pivot-H*pivot, bounded by
    twice the pivot norm. Heading-only rotation preserves every plumb part's
    horizontal radius and Z extrema. The grip's full 3D radius bounds any
    pitch/roll, and each sliding door adds its complete open displacement.
    Triangle interiors satisfy the same bounds by convexity.
    """
    pivot=np.asarray(pivot,float)
    if pivot.shape!=(3,) or not np.isfinite(pivot).all():
        raise ValueError('Invalid cabin grip pivot envelope')
    shift=2*float(np.linalg.norm(pivot));parts={}
    if not meshes:
        raise ValueError('Incomplete cabin structure envelope')
    for name,mesh in meshes.items():
        vertices=np.asarray(mesh.verts,float)
        if vertices.ndim!=2 or vertices.shape[1]!=3 or not len(vertices) or not np.isfinite(vertices).all():
            raise ValueError('Incomplete cabin structure envelope')
        offset=np.asarray(door_offsets.get(name,[0.,0.,0.]),float)
        if offset.shape!=(3,) or not np.isfinite(offset).all():
            raise ValueError('Invalid sliding-door structure envelope')
        motion=float(np.linalg.norm(offset[:2]));vertical=abs(float(offset[2]))
        if name=='GD_CabinGrip':
            radius=drop=float(np.linalg.norm(vertices,axis=1).max())
            mode='grip'
        else:
            radius=float(np.linalg.norm(vertices[:,:2],axis=1).max())+shift+motion
            drop=max(0.,-float(vertices[:,2].min()))+shift+vertical
            mode='plumb'
        parts[name]={'mode':mode,'radius_m':radius,'drop_m':drop,'door_motion_m':motion,'door_vertical_m':vertical}
    return {'parts':parts,'pivot_shift_m':shift,'margin_m':.3,
            'radius_m':max(p['radius_m'] for p in parts.values())+.3,
            'drop_m':max(p['drop_m'] for p in parts.values())}
