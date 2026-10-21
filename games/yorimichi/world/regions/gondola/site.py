"""Fit the ropeway stations, trestles and contact paths to final owned ground."""
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
WORLD=HERE.parents[1]
KIT=HERE.parents[2]/'assets/vehicles/gondola'
sys.path[:0]=[str(KIT),str(WORLD)]
import hashlib
import json
import math

import numpy as np
import bpy
from mathutils import Vector
import importlib.util
_kit_spec=importlib.util.spec_from_file_location('gondola_kit_builder',KIT/'build.py')
K=importlib.util.module_from_spec(_kit_spec);_kit_spec.loader.exec_module(K)
import checks
import params as P
import rope as R
import solid
import walk as W
from cabin import Cabin, pose
from tower import Tower
from stations import Station, Valley, Rim, Crater, railing
from gondola.line import centre_profile, closed_circuit, placed, simplify, station_frame
from gondola.products import ground
from gondola.support import ground_ceiling
from gondola.validation import site_inputs, validate_site
from regions.gondola.layout import LINES, STATIONS
from regions.craterpark import placement as PARK
import yori

FLOORS={'platform','plaza','boardwalk','stair landing','stair step'}


def local_xy(points,frame):
    origin,along,lateral,z=frame
    delta=np.asarray(points)-origin
    return np.c_[delta@along,delta@lateral]


def world_xy(points,frame):
    origin,along,lateral,z=frame
    q=np.asarray(points,float)
    return origin+q[:,0,None]*along+q[:,1,None]*lateral


def fit_station(key,other,G,layouts):
    spec=STATIONS[key]
    frame=station_frame(spec['mouth'],STATIONS[other]['mouth'],0,7.6)
    layout=layouts[spec['kind']]
    floors=[p for p in layout['obstacles'] if p['name'] in FLOORS]
    if not floors:
        raise ValueError('Station has no exported walking floors')
    required=-float('inf')
    footprint=[]
    owner_surfaces={surface.owner:surface for surface in G.surfaces.values()}
    for floor in floors:
        poly=world_xy(floor['poly'],frame)
        # Stations remain inside one authored owner band. A future seam-spanning
        # station must split the footprint, rather than compare owner heights.
        _,owners=G.base(poly)
        if len(set(owners))!=1:
            raise ValueError('Station support footprint crosses a terrain-owner seam')
        terrain=owner_surfaces[owners[0]].triangles
        required=max(required,ground_ceiling(terrain,poly)-min(floor['z1'])+.55)
        footprint.append(poly.tolist())
    z=required+spec.get('platform_lift_m',0.)
    frame=(*frame[:3],z)
    return {'id':key,'kind':spec['kind'],'name':spec['name'],'mouth':list(spec['mouth']),
            'origin':frame[0].tolist(),'heading':math.degrees(math.atan2(frame[1][1],frame[1][0])),
            'platform_z':z,'footprints':footprint},frame


def timber_support(mesh,G,frame,xy,top,section=.28):
    """One post seats in a stone foot spanning its exact local ground relief."""
    offsets=np.array([[-.4,-.4],[.4,-.4],[.4,.4],[-.4,.4],[0,0]])
    world=world_xy(offsets+xy,frame)
    heights,_=G.contact(world)
    low,high=float(heights.min()-frame[3]),float(heights.max()-frame[3])
    foot_top=high+.18
    if top<=foot_top+.1:
        return None
    with mesh.grained((0,0,1)):
        mesh.box((*xy,(low-.20+foot_top)/2),(.8,.8,foot_top-low+.20),solid.BASALT)
        mesh.box((*xy,(foot_top-.01+top)/2),(section,section,top-foot_top+.01),solid.TIMBER)
    return {'xy':list(map(float,xy)),'base':foot_top-.01,'top':float(top),
            'contact_range':heights.tolist(),'foot_bottom':float(low-.20+frame[3])}


def station_foundation(key,layout,G,frame):
    mesh=solid.Mesh(f'GD_{key}_Foundation')
    floors=[p for p in layout['obstacles'] if p['name'] in FLOORS]
    polys=[p['poly'] for p in floors]
    points=np.concatenate([np.asarray(p,float) for p in polys]);lo,hi=points.min(0),points.max(0)
    posts={}
    for x in np.arange(math.ceil(lo[0]/3)*3,hi[0],3):
        for y in np.arange(math.ceil(lo[1]/3)*3,hi[1],3):
            found=[p for p in floors if W.inside_poly(np.array([x]),np.array([y]),p['poly'])[0]]
            if not found:
                continue
            top=min(min(p['z0']) for p in found)+.04
            post=timber_support(mesh,G,frame,np.array([x,y]),top)
            if post:
                posts[(float(x),float(y))]=post
    for (x,y),post in posts.items():
        for next_ in ((x+3,y),(x,y+3)):
            if next_ not in posts:
                continue
            other=posts[next_]
            high=min(post['top'],other['top'])-.20
            low=max(post['base'],other['base'])+.25
            if high-low<1.:
                continue
            # Crossing diagonals use separate faces of the posts, with their
            # ends embedded in the timber rather than floating at a tuned gap.
            direction=np.array(other['xy'])-post['xy']
            normal=np.array([-direction[1],direction[0]])/np.linalg.norm(direction)
            for index,(a,b) in enumerate(((post,other),(other,post))):
                offset=(index-.5)*.16*normal
                mesh.beam((*(np.array(a['xy'])+offset),low),(*(np.array(b['xy'])+offset),high),.14,.18,solid.TIMBER_DARK,up=(0,0,1))
            mesh.beam((x,y,high),(*next_,high),.22,.25,solid.TIMBER,up=(0,0,1))
    return mesh,list(posts.values())


def ground_edge(G,frame,end,across,width):
    """The exact contact edge knots, including triangle and owner boundaries."""
    origin=world_xy([end],frame)[0]
    direction=frame[1]*across[0]+frame[2]*across[1]
    endpoint=np.array([origin-width/2*direction,origin+width/2*direction])
    low,high=endpoint.min(0)-1e-8,endpoint.max(0)+1e-8
    knots=[-width/2,width/2]
    for surface in [*G.surfaces.values(),G.trail]:
        tri=surface.triangles
        lo,hi=tri[:,:,:2].min(1),tri[:,:,:2].max(1)
        tri=tri[(hi[:,0]>=low[0])&(lo[:,0]<=high[0])&(hi[:,1]>=low[1])&(lo[:,1]<=high[1])]
        for corner in range(3):
            a,b=tri[:,corner,:2],tri[:,(corner+1)%3,:2]
            edge=b-a;delta=origin-a
            cross=lambda u,v:u[...,0]*v[...,1]-u[...,1]*v[...,0]
            denominator=cross(edge,direction)
            valid=abs(denominator)>1e-12
            u=np.divide(cross(delta,direction),denominator,out=np.zeros(len(edge)),where=valid)
            t=np.divide(cross(delta,edge),denominator,out=np.zeros(len(edge)),where=valid)
            keep=valid&(u>=0)&(u<=1)&(t>=-width/2)&(t<=width/2)
            knots.extend(t[keep])
    ordered=sorted(set(round(float(t),10) for t in knots))
    merged=[ordered[0]]
    for value in ordered[1:]:
        if value-merged[-1]>1e-4:
            merged.append(value)
    if ordered[-1]-merged[-1]<=1e-4:
        merged[-1]=ordered[-1]
    knots=np.asarray(merged)
    z=G.contact(origin+knots[:,None]*direction)[0]-frame[3]
    test=np.linspace(-width/2,width/2,401)
    actual=G.contact(origin+test[:,None]*direction)[0]-frame[3]
    if np.max(abs(actual-np.interp(test,knots,z)))>1e-4:
        raise ValueError('Access contact edge does not reproduce the owned terrain profile')
    return knots,z


def access_stair(key,layout,G,frame):
    access=layout['access'][0]
    edge=np.asarray(access['edge'],float);start=edge.mean(0)
    direction=start-np.asarray(access['point']);direction/=np.linalg.norm(direction)
    across=np.array([-direction[1],direction[0]])
    width=min(2.2,float(np.linalg.norm(edge[1]-edge[0]))-.10)
    top=float(access['z'])
    mesh=solid.Mesh(f'GD_{key}_Access')
    rail_layout=Station(key,dict(P.DEFAULTS),P.derived(P.DEFAULTS))
    preface=[[*start,top]]
    landing_surfaces=[]
    turn=STATIONS[key].get('access_turn_deg',0.)
    if turn:
        if turn!=90.:
            raise ValueError('Access landing supports the authored left quarter turn only')
        old_start=start.copy();old_direction=direction.copy();old_across=across.copy()
        polygon=[start-across*width/2,start+direction*width-across*width/2,
                 start+direction*width+across*width/2,start+across*width/2]
        landing_surfaces.append({'poly':[list(p) for p in polygon],'top':top})
        with mesh.tagged('access_landing'):
            mesh.prism(polygon,top-.24,top,solid.TIMBER_DARK,top=solid.DECK)
        for a,b in ((polygon[0],polygon[1]),(polygon[1],polygon[2])):
            railing(mesh,rail_layout,[a,b],'timber',z0=top,on=('access_landing',))
        start=old_start+old_direction*width/2+old_across*width/2
        direction=old_across;across=-old_direction
        preface.extend([[*(old_start+old_direction*width/2),top],[*start,top]])
    chosen=None
    for n in range(1,201):
        length=(n-1)*.32+1.5
        end=start+length*direction
        z=float(G.contact(world_xy([end],frame))[0][0]-frame[3])
        rise=(top-z)/n
        if .10<=rise<=.27:
            chosen=(n,length,end,z,rise)
            break
    if chosen is None:
        raise ValueError(f'{key}: no descending access flight to final ground')
    n,length,end,bottom,rise=chosen
    route=preface
    edge_t,edge_z=ground_edge(G,frame,end,across,width)
    bottom=float(max(edge_z))
    rise=(top-bottom)/n
    if not .10<=rise<=.30:
        raise ValueError(f'{key}: fitted final stair riser is invalid')
    surfaces=landing_surfaces[:]
    for k in range(n):
        a,b=k*.32,(k+1)*.32 if k<n-1 else length-.8
        height=top-(k+1)*rise
        centre=start+(a+b)/2*direction
        poly=[start+a*direction-across*width/2,start+b*direction-across*width/2,
              start+b*direction+across*width/2,start+a*direction+across*width/2]
        mesh.prism(poly,height-.16,height,solid.TIMBER_DARK,top=solid.DECK)
        front=start+a*direction
        with mesh.at((*front,0),math.degrees(math.atan2(direction[1],direction[0]))):
            mesh.box((.018,0,height+rise/2),(.036,width,rise),solid.TIMBER)
        surfaces.append({'poly':[list(p) for p in poly],'top':height})
        route.append([*centre,height])
    # The last 0.8m landing shares every terrain triangle-edge knot. Its outer
    # edge is the actual rendered ground profile rather than a flat guessed lip.
    join_start=end-.8*direction
    for ta,tb,za,zb in zip(edge_t[:-1],edge_t[1:],edge_z[:-1],edge_z[1:]):
        polygon=[join_start+ta*across,end+ta*across,end+tb*across,join_start+tb*across]
        def floor(x,y):
            q=np.array([x,y])-join_start
            u=float(np.clip(q@direction/.8,0,1))
            v=float(np.clip((q@across-ta)/(tb-ta),0,1))
            return bottom+u*((1-v)*za+v*zb-bottom)
        mesh.prism(polygon,lambda x,y:floor(x,y)-.16,floor,solid.TIMBER_DARK,top=solid.DECK)
        surfaces.append({'poly':[list(p) for p in polygon],'z1':[floor(*p) for p in polygon]})
    def stringer_top(x,y):
        distance=float((np.array([x,y])-start)@direction)
        return top-(top-bottom)*distance/length+.25
    for side in (-1,1):
        offset=side*(width/2-.12)*across
        a,b=start+offset,end+offset
        polygon=[a-across*.09,b-across*.09,b+across*.09,a+across*.09]
        with mesh.tagged('access_stringer'):
            mesh.prism(polygon,lambda x,y:stringer_top(x,y)-.55,stringer_top,solid.TIMBER)
        railing(mesh,rail_layout,[a,b],'timber',z0=stringer_top,on=('access_stringer',))
    route.append([*end,float(np.interp(0,edge_t,edge_z))])
    # Check every generated landing strip against the same final contact query.
    for surface in surfaces:
        polygon=np.asarray(surface['poly'])
        samples=np.vstack((polygon,polygon.mean(0)))
        heights=G.contact(world_xy(samples,frame))[0]-frame[3]
        roof=min(surface.get('z1',[surface.get('top',bottom)]))
        if heights[:-1].max()>roof+.03 and surface is not surfaces[-1]:
            # The conforming join may meet its own sloped edge; ordinary treads
            # must remain above the rendered ground throughout their footprint.
            if 'z1' not in surface:
                raise ValueError(f'{key}: ground intersects an access tread')
    supports=[]
    for distance in np.arange(0,length+.01,3):
        for side in (-1,1):
            point=start+distance*direction+side*(width/2-.12)*across
            level=top-(top-bottom)*distance/length-.20
            support=timber_support(mesh,G,frame,point,level,.20)
            if support:
                supports.append(support)
    return mesh,{'route':route,'width':width,'risers':n,'riser':rise,'tread':.32,
                 'rail_seats':rail_layout.seats,'obstacles':rail_layout.proxies,'turn_deg':turn,'ground_edge_tolerance':.0001,'ground_edge':{'t':edge_t.tolist(),'z':edge_z.tolist()},'surfaces':surfaces,'supports':supports}


def world_ground(mesh,frame,G):
    local=np.asarray(mesh.verts,float)
    world=world_xy(local[:,:2],frame)
    low,high=world.min(0)-1,world.max(0)+1
    _,owner=G.base([world.mean(0)])
    surfaces=[surface for surface in G.surfaces.values() if surface.owner==owner[0]]+[G.trail]
    result=[]
    for surface in surfaces:
        tri=surface.triangles
        lo,hi=tri[:,:,:2].min(1),tri[:,:,:2].max(1)
        tri=tri[(hi[:,0]>=low[0])&(lo[:,0]<=high[0])&(hi[:,1]>=low[1])&(lo[:,1]<=high[1])].copy()
        if len(tri):
            xy=local_xy(tri[:,:,:2].reshape(-1,2),frame).reshape(-1,3,2)
            tri[:,:,:2]=xy;tri[:,:,2]-=frame[3]
            result.append(tri)
    return np.concatenate(result) if result else np.empty((0,3,3))


def untouched_riding(mesh,frame,riding):
    if not len(riding):
        return
    vertices=np.asarray(mesh.verts,float)
    xy=world_xy(vertices[:,:2],frame)
    low,high=xy.min(0),xy.max(0)
    lo,hi=riding[:,:,:2].min(1),riding[:,:,:2].max(1)
    candidates=riding[(hi[:,0]>=low[0])&(lo[:,0]<=high[0])&(hi[:,1]>=low[1])&(lo[:,1]<=high[1])]
    if not len(candidates):
        return
    for first,last,*_ in mesh.parts:
        indices={i for face in mesh.faces[first:last] for i in face}
        points=xy[list(indices)];a,b=points.min(0),points.max(0)
        rectangle=[a,[b[0],a[1]],b,[a[0],b[1]]]
        for triangle in candidates:
            polygon=list(triangle[:,:2])
            for u,v in zip(rectangle,rectangle[1:]+rectangle[:1]):
                polygon=solid._shared._clip(polygon,u,v)
                if not polygon:
                    break
            if polygon:
                raise ValueError(f'{mesh.name}: a static support or access part overlaps a riding footprint')


def station_jump_clearance(points,riding,drop):
    from gondola.clearance import riding_clearance
    low,high=points[:,:2].min(0)-14,points[:,:2].max(0)+14
    lo,hi=riding[:,:,:2].min(1),riding[:,:,:2].max(1)
    candidates=riding[(hi[:,0]>=low[0])&(lo[:,0]<=high[0])&(hi[:,1]>=low[1])&(lo[:,1]<=high[1])]
    best=float('inf');count=0
    for index,point in enumerate(points):
        delta=points[min(len(points)-1,index+1),:2]-points[max(0,index-1),:2]
        delta/=np.linalg.norm(delta)
        result=riding_clearance(candidates,point[:2],delta,[[-13.15,point[2]],[13.15,point[2]]],
                                lateral=13.05,half_length=0,drop=drop)
        count+=result['triangles_tested']
        if result['minimum_m'] is not None:
            best=min(best,result['minimum_m'])
    if best<15.:
        raise ValueError(f'Station-loop cabin jump clearance {best:.3f}m is below15m')
    return {'poses':len(points),'triangles_tested':count,'minimum_m':best if count else None,'pass':True}


def export_world(mesh,folder,mats,limit=50000,*,frame=None,G=None,seats=(),riding=None):
    proof=solid.closed(mesh)
    if proof['open_edges'] or proof['misoriented_edges'] or proof['degenerate_faces'] or mesh.tris()>limit:
        raise ValueError(f'{mesh.name}: invalid or over-budget world mesh: {proof}, {mesh.tris()} triangles')
    coplanar={'count':0,'samples':[]}
    seating=[];carried={'failures':[]}
    if frame is not None:
        untouched_riding(mesh,frame,riding)
        count,samples=solid._shared.coplanar_overlaps([mesh])
        coplanar={'count':count,'samples':samples}
        seating=solid.seats([mesh],seats)
        summary,failures=solid._shared.carried_failures([mesh],world_ground(mesh,frame,G))
        carried={**summary,'failures':failures}
        if count or failures or any(row['status']!='ok' for row in seating):
            raise ValueError(f'{mesh.name}: floating/seating/coplanar proof failed: {coplanar}, {seating}, {carried}')
    obj,names=solid.to_object(mesh,mats)
    path=folder/f'{mesh.name}.fbx';solid.export_fbx([obj],path)
    bpy.data.objects.remove(obj,do_unlink=True)
    return {'name':mesh.name,'materials':names,'triangles':mesh.tris(),'closed':proof,
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'coplanar':coplanar,
            'seating':seating,'carried':carried,'riding_plan_clear':frame is not None}


def tower_fit(key,s,height,A,direction,G,p):
    xy=A+s*direction
    prototype=Tower(p,height)
    feet=np.array([(sx*prototype.hx(.7)+u*.5,sy*prototype.hy(.7)+v*.5)
                   for sx in (-1,1) for sy in (-1,1) for u,v in ((-1,-1),(1,-1),(1,1),(-1,1))])
    lateral=np.array([-direction[1],direction[0]])
    world=xy+feet[:,0,None]*direction+feet[:,1,None]*lateral
    heights,_=G.contact(world)
    broad=xy+np.array([(x,y) for x in (-3,0,3) for y in (-3,0,3)])
    datum=max(float(G.base(broad)[0].max()+.6),float(heights.max()+.15))
    frame=(xy,direction,lateral,datum)
    def contact(x,y):
        return float(G.contact(world_xy([[x,y]],frame))[0][0]-datum)
    tower=Tower(p,height,ground=contact)
    mesh=tower.build();mesh.name=f'GD_{key}_Tower'
    return tower,mesh,frame,{'id':key,'s':s,'height':height,'origin':[float(xy[0]),float(xy[1]),datum],
                           'heading':math.degrees(math.atan2(direction[1],direction[0]))}


def audit_span(key,profile,cab,p):
    import time
    extended=np.vstack(([profile[0,0]-.4,profile[0,1]],profile,[profile[-1,0]+.4,profile[-1,1]]))
    path=R.RopePath([(s,0,z) for s,z in extended],p['rope_radius'])
    samples=np.arange(path.s[1],path.s[-2]+1e-8,.2)
    maxima=0.;minimum=float('inf');count=0;t0=__import__('time').monotonic()
    for start in range(0,len(samples),128):
        frames=[]
        for s in samples[start:start+128]:
            for side in (-1,1):
                placement=pose(path.grip_frame(float(s),(0,side,0)))
                if not checks.hanging_ok(placement.C):
                    raise ValueError(f'{key}: cabin floor is not level')
                frames.append((f'{key} arc {s:.3f} side {side}',placement,float(s)))
        groove=K.groove_check(cab,path,frames)
        if not groove['ok']:
            raise ValueError(f'{key}: actual jaw groove failed {groove}')
        maxima=max(maxima,groove['max_error_mm'])
        # Whole actual-mesh distances and signed jaw surfaces also participate;
        # the denser groove sweep retains every .2m pose in both directions.
        clearance=K.rope_check(cab,path,frames[::10])
        jaw=K.jaw_contact(cab,path,frames[::10])
        if not clearance['ok'] or not jaw['ok']:
            raise ValueError(f'{key}: actual cabin/jaw clearance failed: {clearance}, {jaw}')
        minimum=min(minimum,clearance['min_distance_from_rope_axis_m'])
        count+=len(frames)
        print(f'{key} fitted span contact: {min(start+128,len(samples))}/{len(samples)} stations, '
              f'{count} directed poses, {time.monotonic()-t0:.1f}s',flush=True)
    return {'poses':count,'groove_max_mm':maxima,'hardware_min_m':minimum,'pass':True}


def ground_gap(profile,A,direction,G,drop):
    lateral=np.array([-direction[1],direction[0]])
    floor=profile[:,1]-drop
    from collections import deque
    left=np.searchsorted(profile[:,0],profile[:,0]-1.15,side='left')
    right=np.searchsorted(profile[:,0],profile[:,0]+1.15,side='right')
    minimum=np.minimum(np.interp(profile[:,0]-1.15,profile[:,0],floor),
                       np.interp(profile[:,0]+1.15,profile[:,0],floor))
    pending=deque();next_=0
    for index in range(len(profile)):
        while next_<right[index]:
            while pending and floor[pending[-1]]>=floor[next_]:
                pending.pop()
            pending.append(next_);next_+=1
        while pending and pending[0]<left[index]:
            pending.popleft()
        minimum[index]=min(minimum[index],floor[pending[0]])
    indices=np.arange(len(profile))
    best=float('inf');approach=float('inf')
    for start in range(0,len(indices),512):
        ids=indices[start:start+512]
        centres=A+profile[ids,0,None]*direction
        q=centres[:,None,:]+np.linspace(-4.3,4.3,19)[None,:,None]*lateral
        z=G.contact(q.reshape(-1,2))[0].reshape(-1,19).max(1)
        gaps=minimum[ids]-z
        approach=min(approach,float(gaps.min()))
        interior=(profile[ids,0]>=35)&(profile[ids,0]<=profile[-1,0]-35)
        if interior.any():
            best=min(best,float(gaps[interior].min()))
        if start%4096==0:
            print(f'GONDOLA ground clearance {min(start+512,len(indices))}/{len(indices)} longitudinal samples',flush=True)
    if approach<.03:
        raise ValueError(f'Cabin intersects approach terrain: {approach:.3f}m')
    if best<6.:
        raise ValueError(f'Cabin-to-final-ground clearance {best:.3f}m is below6m')
    return {'minimum_sampled_m':best,'minimum_approach_m':approach,'station_approach_m':35.,'longitudinal_step_m':.05,'lateral_samples':19,'pass':True}


def tower_path_audit(tower,mesh,row,profile,cab,p,d):
    at=row['s'];datum=row['origin'][2]
    selected=profile[(profile[:,0]>=at-5)&(profile[:,0]<=at+5)]
    results=[]
    for side in (-1,1):
        path=R.RopePath([(s-at,side*p['gauge']/2,z-datum) for s,z in selected],p['rope_radius'])
        frames=[]
        for arc in np.arange(.5,path.length-.5,.1):
            placement=pose(path.grip_frame(float(arc),(0,side,0)))
            frames.append((f'{row["id"]} {side} arc{arc:.2f}',placement,float(arc)))
        places=[(label,placement) for label,placement,_ in frames]
        hits=solid.clearance([mesh],K.cabin_movers(cab),places)
        envelope=solid.clearance([mesh],[K.envelope(p,d,checks.TOWER_BODY_MARGIN)],places)
        rope=K.static_rope_check([mesh],path,('sheave',),'fitted sheave grooves',row['id'])
        if hits or envelope or any(not rope[key]['ok'] for key in ('intentional','clearance')):
            raise ValueError(f'{row["id"]}: actual tower/cabin/rope contact failed: {hits}, {envelope}, {rope}')
        results.append({'side':side,'poses':len(frames),'contacts':hits,'body_envelope':envelope,'rope':rope})
    return results


def main():
    """@cc [owner:fontanierh,label:correctness] fitted-gondola-world-gates
    Site generation MUST use source-bound canonical kit and final owned ground.
    Static supports/access MUST leave riding geometry untouched. Generation MUST
    refuse failed closure, seating, carrying, contact, level-floor or budgets,
    cabin/ground gaps below6m outside the35m station approaches, approach terrain
    penetration, riding jump gaps below15m and stale source/products.
    """
    inputs=site_inputs(yori.OUT)
    p=dict(P.DEFAULTS);d=P.derived(p)
    kit=json.loads((yori.OUT/'gondola/manifest.json').read_text())
    if kit.get('soft_fail') or kit['failures'] or kit['source_hash']!=K.source_hash():
        raise ValueError('Gondola kit is stale or failed')
    G=ground(yori.OUT)
    layouts={kind:json.loads((yori.OUT/f'gondola/layout_{kind}.json').read_text()) for kind in ('valley','rim','crater')}
    folder=yori.OUT/'gondola/world';assets=folder/'assets';assets.mkdir(parents=True,exist_ok=True)
    mats=solid.make_materials({})
    cabin=Cabin(p,d);meshes,_=cabin.build();cab={'cabin':cabin,'meshes':meshes}
    riding=PARK.piece_triangles()
    shells={kind:cls(kind,p,d).make() for kind,cls in (('valley',Valley),('rim',Rim),('crater',Crater))}
    stations={};frames={};exports=[];lines=[]
    for line in LINES:
        first,last=line['stations']
        for key,other in ((first,last),(last,first)):
            print('GONDOLA SITE station',key,flush=True)
            data,frame=fit_station(key,other,G,layouts)
            for shell in shells[data['kind']].values():
                untouched_riding(shell,frame,riding)
            data['static_riding_clear']=True
            foundation,posts=station_foundation(key,layouts[data['kind']],G,frame)
            stair,access=access_stair(key,layouts[data['kind']],G,frame)
            loop=R.station_loop(p['gauge']/2,d['rope_height_above_platform'],d['rope_height_above_platform'],7.6,p['rope_radius'],step=.5).pts
            data['jump']=station_jump_clearance(placed(loop,frame),riding,d['grip_to_floor']+p['cabin_floor_depth'])
            data['posts']=posts;data['access']=access
            data['foundation']=export_world(foundation,assets,mats,frame=frame,G=G,riding=riding)
            data['access_mesh']=export_world(stair,assets,mats,frame=frame,G=G,seats=access['rail_seats'],riding=riding)
            exports += [data['foundation'],data['access_mesh']]
            stations[key]=data;frames[key]=frame
        A,B=np.asarray(STATIONS[first]['mouth']),np.asarray(STATIONS[last]['mouth'])
        length=float(np.linalg.norm(B-A));direction=(B-A)/length
        supports=[(.6,frames[first][3]+d['rope_height_above_platform'],False)]
        towers=[];tower_geometry=[]
        for index,(s,height) in enumerate(line['towers']):
            tower,mesh,frame,row=tower_fit(f'{line["id"]}_{index}',s,height,A,direction,G,p)
            row['mesh']=export_world(mesh,assets,mats,limit=checks.BUDGET['tower'],frame=frame,G=G,seats=tower.seats,riding=riding)
            exports.append(row['mesh']);towers.append(row);tower_geometry.append((tower,mesh,row))
            supports.append((s,frame[3]+height,True))
        supports.append((length-.6,frames[last][3]+d['rope_height_above_platform'],False))
        profile=centre_profile(supports)
        from gondola.clearance import riding_clearance
        clearance=riding_clearance(riding,A,direction,profile,lateral=16.3,half_length=p['cabin_length']/2,drop=d['grip_to_floor']+p['cabin_floor_depth'])
        if clearance['minimum_m'] is not None and clearance['minimum_m']<15.:
            raise ValueError(f'{line["id"]}: cabin/jump envelope conflicts with riding structure: {clearance}')
        # Both tracks use one profile and the kit's exact, level grip loops.
        loop=R.station_loop(p['gauge']/2,d['rope_height_above_platform'],d['rope_height_above_platform'],7.6,p['rope_radius']).pts
        circuit=closed_circuit(profile,frames[first],frames[last],loop,p['gauge'])
        gap=ground_gap(profile,A,direction,G,d['grip_to_floor']+p['cabin_floor_depth'])
        for tower,mesh,row in tower_geometry:
            row['contact_audit']=tower_path_audit(tower,mesh,row,profile,cab,p,d)
        audit=audit_span(line['id'],profile,cab,p)
        rope_exports=[]
        normal=np.array([-direction[1],direction[0]])
        for lod,(tolerance,sides) in enumerate(((.0005,12),(.015,8),(.05,6))):
            mesh=solid.Mesh(f'GD_{line["id"]}_Rope_LOD{lod}')
            for side in (-1,1):
                points=np.c_[A+profile[:,0,None]*direction+side*p['gauge']/2*normal,profile[:,1]]
                mesh.tube(simplify(points,tolerance),p['rope_radius'],solid.STEEL,n=sides)
            row=export_world(mesh,assets,mats,limit=100000)
            rope_exports.append(row);exports.append(row)
        lines.append({'id':line['id'],'stations':[first,last],'supports':supports,'towers':towers,
                      'profile':profile.tolist(),'circuit':circuit.tolist(),'ground':gap,'riding':clearance,'span_audit':audit,'rope_meshes':rope_exports})
        print('GONDOLA SITE line complete',line['id'],flush=True)
    result={'inputs':inputs,'stations':stations,'lines':lines,'exports':exports,'failures':[],'kit_source':kit['source_hash']}
    if site_inputs(yori.OUT)!=inputs:
        raise ValueError('Gondola site source or world inputs changed during fitting')
    (folder/'site.json').write_text(json.dumps(result,separators=(',',':'))+'\n')
    validate_site(yori.OUT)
    print('GONDOLA SITE COMPLETE',len(stations),'stations',len(exports),'world meshes',flush=True)


if __name__=='__main__':
    main()
