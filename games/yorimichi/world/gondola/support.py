"""Complete owned footprint coverage and relief from final terrain triangles."""
import math
import numpy as np
from solid_mesh import signed_area, ear_clip
from gondola.clearance import clip

AREA_TOL=1e-9
ACCESS_SLOPE_DEG=40.


def floor_caps(surface):
    """The shared prism triangulation, with the exact emitted corner heights."""
    xy=np.asarray(surface['poly'],float)
    z=np.broadcast_to(np.asarray(surface.get('z1',surface.get('top')),float),(len(xy),))
    if signed_area(xy-xy[0])<0:xy,z=xy[::-1],z[::-1]
    return np.asarray([np.c_[xy,z][list(ids)] for ids in ear_clip(xy)])


def cap_slope(triangles):
    triangles=np.asarray(triangles,float)
    normal=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
    if not np.isfinite(normal).all():
        raise ValueError('Invalid walking cap triangle')
    # Exact owner clipping can retain a boundary-only zero-area triangle.
    # Nondegenerate vertical faces still refuse as nonwalking surfaces.
    normal=normal[np.linalg.norm(normal,axis=1)>1e-12]
    if not len(normal) or np.any(abs(normal[:,2])<1e-12):
        raise ValueError('Invalid walking cap triangle')
    return float(np.degrees(np.arctan2(np.linalg.norm(normal[:,:2],axis=1),abs(normal[:,2]))).max())


def access_walk_audit(G,frame,head_edge,top,landings,treads,joins,end,direction,across,
                      *,step_limit,tread_min,walk_width,last_tread,tread=.32):
    """@cc [owner:fontanierh,label:correctness] emitted-access-walkability
    Access MUST audit the actual shared cap triangulation, not a smoother
    bilinear intention. Every cap and the minimum-width final-ground continuation
    MUST stay at most forty degrees. Head/landing/tread/join edges MUST meet by
    construction; measured height jumps MUST obey the kit step limit, with the
    full tread minimum and complete final-owned coverage preserved.
    """
    surfaces=landings+treads+joins
    triangles=np.concatenate([floor_caps(surface) for surface in surfaces])
    slope=cap_slope(triangles)
    if slope>ACCESS_SLOPE_DEG+1e-8:
        raise ValueError(f'Access walking cap slope {slope:.6f} exceeds {ACCESS_SLOPE_DEG} degrees')
    if last_tread<tread_min-1e-9:
        raise ValueError('Access final tread is too short or reversed')
    steps=[];gaps=[]
    def meet(a,za,b,zb,*,subset=False):
        a,b=np.asarray(a,float),np.asarray(b,float)
        if subset:
            axis=a[1]-a[0];length=np.linalg.norm(axis);axis/=length
            q=(b-a[0])@axis
            gap=max(float(np.linalg.norm(b-a[0]-q[:,None]*axis,axis=1).max()),
                    max(0.,-float(q.min()),float(q.max())-length))
        else:
            if np.linalg.norm(a-b[::-1],axis=1).max()<np.linalg.norm(a-b,axis=1).max():
                b=b[::-1];zb=np.broadcast_to(np.asarray(zb),(2,))[::-1]
            gap=float(np.linalg.norm(a-b,axis=1).max())
        gaps.append(gap);steps.append(float(np.max(abs(np.asarray(za)-np.asarray(zb)))))
    def landing_edge(surface,name):
        poly=np.asarray(surface['poly'])
        edge=np.asarray(surface.get(name,poly[[0,3] if name=='entry' else [2,3]]))
        # An explicit switchback opening must lie on a real cap boundary.
        errors=[]
        for a,b in zip(poly,np.roll(poly,-1,axis=0)):
            axis=b-a;length=np.linalg.norm(axis);axis/=length
            q=(edge-a)@axis
            errors.append(max(float(np.linalg.norm(edge-a-q[:,None]*axis,axis=1).max()),
                              max(0.,-float(q.min()),float(q.max())-length)))
        gaps.append(min(errors))
        return edge
    if landings:
        meet(head_edge,top,landing_edge(landings[0],'entry'),landings[0]['top'],subset=True)
        for a,b in zip(landings,landings[1:]):
            meet(landing_edge(a,'exit'),a['top'],landing_edge(b,'entry'),b['top'])
        meet(landing_edge(landings[-1],'exit'),landings[-1]['top'],
             np.asarray(treads[0]['poly'])[[0,3]],treads[0]['top'])
    else:
        meet(head_edge,top,np.asarray(treads[0]['poly'])[[0,3]],treads[0]['top'],subset=True)
    for a,b in zip(treads,treads[1:]):
        meet(np.asarray(a['poly'])[[1,2]],a['top'],np.asarray(b['poly'])[[0,3]],b['top'])
    last=treads[-1]
    intervals=[];edge=np.asarray(last['poly'])[[1,2]];axis=edge[1]-edge[0];length=np.linalg.norm(axis);axis/=length
    for surface in joins:
        polygon=np.asarray(surface['poly']);z=np.asarray(surface['z1'])
        meet(edge,last['top'],polygon[[0,3]],z[[0,3]],subset=True)
        intervals.append(sorted(((polygon[[0,3]]-edge[0])@axis).tolist()))
    cursor=0.
    for a,b in sorted(intervals):
        gaps.append(abs(a-cursor));cursor=b
    gaps.append(abs(cursor-length))
    for a,b in zip(joins,joins[1:]):
        meet(np.asarray(a['poly'])[[3,2]],np.asarray(a['z1'])[[3,2]],
             np.asarray(b['poly'])[[0,1]],np.asarray(b['z1'])[[0,1]])
    origin,along,lateral,datum=frame
    def world(points):
        points=np.asarray(points);return origin+points[:,0,None]*along+points[:,1,None]*lateral
    ground_gap=0.
    for surface in joins:
        edge=np.asarray(surface['poly'])[[1,2]];z=np.asarray(surface['z1'])[[1,2]]+datum
        ground_gap=max(ground_gap,float(np.max(abs(G.contact(world(edge))[0]-z))))
    if max(gaps)>1e-4 or ground_gap>1e-4 or max(steps)>step_limit+1e-9:
        raise ValueError(f'Access has an open edge or an excessive height step: edge={max(gaps):.9f}m ground={ground_gap:.9f}m step={max(steps):.9f}m')
    continuation=np.array([end-across*walk_width/2,end+.4*direction-across*walk_width/2,
                           end+.4*direction+across*walk_width/2,end+across*walk_width/2])
    ground=owned_triangles(G,world(continuation))
    ground_slope=cap_slope(ground)
    if ground_slope>ACCESS_SLOPE_DEG+1e-8:
        raise ValueError('Access ends on nonwalkable final ground')
    proof=dict(triangles=len(triangles),maximum_slope_deg=slope,slope_limit_deg=ACCESS_SLOPE_DEG,
                steps_m=steps,maximum_step_m=max(steps),step_limit_m=step_limit,
                minimum_tread_m=min(tread,last_tread) if len(treads)>1 else last_tread,tread_limit_m=tread_min,
                shared_edge_gap_m=max(gaps),ground_edge_gap_m=ground_gap,
                continuation=dict(width_m=walk_width,length_m=.4,triangles=len(ground),
                                  maximum_slope_deg=ground_slope,complete_coverage=True))
    proof['pass']=True
    return proof


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
