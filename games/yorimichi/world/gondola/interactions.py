"""Preserve the existing air station footpath and flight space."""
import itertools
import math
import numpy as np

from gondola.clearance import StructureClearance, clip


def mesh_vertices(mesh, frame):
    origin,along,lateral,z=frame
    v=np.asarray(mesh.verts,float)
    return np.c_[origin+v[:,0,None]*along+v[:,1,None]*lateral,v[:,2]+z]


def world_triangles(meshes,frame):
    triangles=[]
    for mesh in meshes:
        vertices=mesh_vertices(mesh,frame)
        for face in mesh.faces:
            triangles.extend(vertices[[face[0],face[i],face[i+1]]] for i in range(1,len(face)-1))
    return np.asarray(triangles,float).reshape(-1,3,3)


def path_strip(path,half_width=1.3):
    path=np.asarray(path,float)
    tangent=np.gradient(path,axis=0)
    tangent/=np.linalg.norm(tangent,axis=1)[:,None]
    normal=np.c_[-tangent[:,1],tangent[:,0]]
    return np.concatenate([path-half_width*normal,path+half_width*normal])


def walking_link(G,frame,route,meshes,structures,stone_path,access_surfaces=()):
    """@cc [owner:fontanierh,label:correctness] belmonte-ground-walking-link
    The natural-ground connection MUST preserve the complete existing stone
    path, have complete owned terrain coverage and walkable triangle slopes,
    and refuse static structure or station obstructions across its full width.
    The runtime walking route MUST include this connection, so vegetation
    clearing and the ordinary physical boarding drive use the same path.
    """
    from gondola.support import owned_triangles
    from solid_mesh import ear_clip
    overlays=[]
    for surface in access_surfaces:
        polygon=np.asarray(surface['poly'],float)
        heights=np.broadcast_to(surface['z1'] if 'z1' in surface else surface['top'],(len(polygon),))
        vertices=np.c_[frame[0]+polygon[:,0,None]*frame[1]+polygon[:,1,None]*frame[2],heights+frame[3]]
        overlays.extend(vertices[list(indices)] for indices in ear_clip(polygon))
    geometry=[mesh_vertices(m,frame) for m in meshes]
    low=np.concatenate(geometry).min(0);high=np.concatenate(geometry).max(0)
    strip=path_strip(stone_path)
    separation=float(strip[:,0].min()-high[0])
    if separation<.35:
        raise ValueError('Gondola station obstructs the existing stone footpath')
    origin,along,lateral,z=frame
    local=np.asarray(route,float)
    end=origin+local[-1,0]*along+local[-1,1]*lateral
    previous=origin+local[-2,0]*along+local[-2,1]*lateral
    direction=end-previous;direction/=np.linalg.norm(direction)
    away=end+3*direction
    north=high[1]+4.
    # Join the actual existing spline, north of the station's complete box.
    candidates=np.asarray(stone_path,float)
    join=candidates[np.argmin(abs(candidates[:,1]-north))]
    if join[1]<high[1]+2.:
        raise ValueError('No clear northern join to the existing stone path')
    west=low[0]-3.
    knots=np.array([end,away,[west,away[1]],[west,join[1]],join])
    begin,finish=knots.min(0)-.5,knots.max(0)+.5
    cropped={}
    for key,triangles in structures.arrays.items():
        a,b=structures.extents[key]
        cropped[key]=triangles[(b[:,:2]>=begin).all(1)&(a[:,:2]<=finish).all(1)]
    structures=StructureClearance(cropped,structures.bounds)
    station_faces=world_triangles(meshes,frame)
    station_query=StructureClearance({'visual':station_faces,'collision':station_faces},structures.bounds)
    points=[];maximum_slope=0.;triangles=0
    for a,b in zip(knots,knots[1:]):
        length=float(np.linalg.norm(b-a))
        if length<1e-8:continue
        direction=(b-a)/length;normal=np.array([-direction[1],direction[0]])
        samples=np.linspace(a,b,max(2,math.ceil(length/.5)+1))
        heights=G.contact(samples)[0]
        for index,(c,d) in enumerate(zip(samples,samples[1:])):
            # Square caps conservatively contain the complete swept capsule
            # disc at every endpoint and on the outside of each route turn.
            c0,d0=c-direction*.35,d+direction*.35
            polygon=np.array([c0-normal*.35,d0-normal*.35,d0+normal*.35,c0+normal*.35])
            faces=owned_triangles(G,polygon)
            faces=walking_floor(faces,polygon,overlays)
            cross=np.cross(faces[:,1]-faces[:,0],faces[:,2]-faces[:,0])
            valid=np.linalg.norm(cross,axis=1)>1e-12
            faces,cross=faces[valid],cross[valid]
            if not len(faces):raise ValueError('Missing walking-link floor triangles')
            slopes=np.linalg.norm(cross[:,:2],axis=1)/np.maximum(abs(cross[:,2]),1e-20)
            if slopes.max()>math.tan(math.radians(40.)):
                raise ValueError('Stone-path connection contains unwalkable final ground')
            maximum_slope=max(maximum_slope,float(slopes.max()));triangles+=len(faces)
            try:
                for query in (structures,station_query):
                    walking_headroom(query,faces)
            except ValueError as error:
                raise ValueError(f'Stone-path link obstructed at {c.tolist()}..{d.tolist()}: {error}') from error
            if index%50==0:
                print('GONDOLA WALK LINK',index,'/',len(samples)-1,'segments checked',flush=True)
        points.extend(np.c_[samples[1:],heights[1:]].tolist())
    delta=np.asarray(points)[:,:2]-origin
    local_points=np.c_[delta@along,delta@lateral,np.asarray(points)[:,2]-z]
    return [*route,*local_points.tolist()],{'pass':True,'width_m':.7,'height_m':1.7,
        'complete_coverage':True,'triangles':triangles,'maximum_slope':maximum_slope,
        'stone_path_gap_m':separation,'join':join.tolist(),'knots':knots.tolist()}


def walking_floor(ground,polygon,overlays):
    """The fitted stair's actual walking caps own their footprints at the join.

    Base-ground coverage was already required. Adopting the explicit stair
    surface prevents its intended walking floor being labelled an obstruction;
    posts, rails and all geometry above that floor remain in headroom checks.
    """
    from gondola.support import intersection,subtract,area
    pieces=[list(t) for t in ground];tops=[]
    for triangle in overlays:
        top=intersection(triangle,polygon)
        if area(top)<=1e-9:continue
        pieces=[part for old in pieces for part in subtract(old,np.asarray(top)[:,:2])]
        tops.append(top)
    triangles=[]
    for piece in pieces+tops:
        if area(piece)<=1e-9:continue
        triangles.extend([piece[0],piece[i],piece[i+1]] for i in range(1,len(piece)-1))
    return np.asarray(triangles,float).reshape(-1,3,3)


def walking_headroom(query,floors):
    """Clip against the exact affine ground plane, including sloping joins."""
    from gondola.support import intersection
    for floor in floors:
        low,high=floor.min(0),floor.max(0)
        query.require_bounds(low[:2],high[:2])
        slope=np.linalg.solve(floor[1:,:2]-floor[0,:2],floor[1:,2]-floor[0,2])
        for key,obstacles in query.arrays.items():
            a,b=query.extents[key]
            ids=np.flatnonzero((b[:,:2]>=low[:2]).all(1)&(a[:,:2]<=high[:2]).all(1)&
                               (b[:,2]>=low[2]+.05)&(a[:,2]<=high[2]+1.7))
            for index in ids:
                polygon=intersection(obstacles[index],floor[:,:2])
                if not polygon:continue
                p=np.asarray(polygon)
                relative=p[:,2]-floor[0,2]-(p[:,:2]-floor[0,:2])@slope
                polygon=list(np.c_[p[:,:2],relative])
                polygon=clip(polygon,2,.05,True)
                if polygon:polygon=clip(polygon,2,1.7,False)
                if polygon:
                    raise ValueError(f'Walking headroom intersects final {key} triangle {index}')


def flight_clearance(metadata,manifest,boxes,profile,envelope):
    """A rotating hull column during climb, then complete high cruise legs."""
    ship=np.asarray(metadata['stations'][3]['ship'],float)
    hull=manifest['ZP_Airship']
    corners=np.array(list(itertools.product(*zip(hull['min'],hull['max']))))
    radius=float(np.linalg.norm(corners[:,:2],axis=1).max())
    motors=manifest['ZP_Motors']
    radius=max(radius,math.hypot(max(abs(motors['min'][0]),abs(motors['max'][0])),
                               max(abs(motors['min'][1]),abs(motors['max'][1]))))
    for centre in metadata['propeller_centers']:
        radius=max(radius,math.hypot(*centre[:2])+metadata['propeller_radius'])
    radius+=.3
    minimum=math.inf;ceiling=float(np.asarray(profile)[:,1].max()+envelope['radius_m'])
    for low,high in boxes:
        low,high=np.asarray(low),np.asarray(high)
        distance=float(np.linalg.norm(np.maximum(np.maximum(low[:2]-ship[:2],ship[:2]-high[:2]),0)))
        minimum=min(minimum,distance-radius)
        ceiling=max(ceiling,float(high[2]))
    if minimum<.3:
        raise ValueError('Zeppelin vertical climb/landing envelope intersects the ropeway')
    legs=[]
    for leg in metadata['legs']:
        if 3 not in leg['stops']:continue
        # The native service climbs vertically before translating at leg.height.
        # Its cruise bob is nonnegative; the entire hull stays above this bound.
        other=next(i for i in leg['stops'] if i!=3)
        destination=np.asarray(metadata['stations'][other]['ship'],float)
        clearance=math.inf;overlaps=0
        for low,high in boxes:
            low,high=np.asarray(low,float),np.asarray(high,float)
            if not segment_intersects_box(ship[:2],destination[:2],low[:2]-radius,high[:2]+radius):
                continue
            gap=leg['height']+hull['min'][2]-high[2]
            clearance=min(clearance,float(gap));overlaps+=1
            if gap<6.:
                raise ValueError('Zeppelin cruise hull does not clear the complete ropeway')
        legs.append({'stops':leg['stops'],'overlapping_boxes':overlaps,
                     'minimum_vertical_m':clearance if overlaps else None})
    if len(legs)!=3:raise ValueError('Incomplete Belmonte zeppelin leg roster')
    return {'pass':True,'rotating_radius_m':radius,'climb_plan_gap_m':minimum,
            'ropeway_ceiling_m':ceiling,'legs':legs}


def segment_intersects_box(a,b,low,high):
    start,end=0.,1.
    for axis in (0,1):
        delta=b[axis]-a[axis]
        if abs(delta)<1e-12:
            if not low[axis]<=a[axis]<=high[axis]:return False
        else:
            u,v=sorted(((low[axis]-a[axis])/delta,(high[axis]-a[axis])/delta))
            start,end=max(start,u),min(end,v)
            if start>end:return False
    return True
