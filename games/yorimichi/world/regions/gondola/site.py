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
from gondola.line import centre_profile, closed_circuit, placed, simplify, station_frame, near_rope_tolerance, float32_cm_axes, stored_groove_audit, recover_rope_vertices, tower_saddles
from gondola.products import ground
from gondola.structures import validate as validate_structures
from gondola.clearance import StructureClearance, structure_envelope
from gondola.interactions import walking_link, mesh_vertices, flight_clearance, access_headroom
from gondola.support import owned_range, owned_triangles, floor_intrusion, floor_caps, access_walk_audit
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
        _,ceiling=owned_range(G,poly,contact=False)
        required=max(required,ceiling-min(floor['z1'])+.55)
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
    low,high=owned_range(G,world[:4])
    heights=np.array([low,high])
    low,high=low-frame[3],high-frame[3]
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
    post_section=.28
    for x in np.arange(math.ceil(lo[0]/3)*3,hi[0],3):
        for y in np.arange(math.ceil(lo[1]/3)*3,hi[1],3):
            found=[p for p in floors if W.inside_poly(np.array([x]),np.array([y]),p['poly'])[0]]
            if not found:
                continue
            top=min(min(p['z0']) for p in found)+.04
            post=timber_support(mesh,G,frame,np.array([x,y]),top,post_section)
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
            # Crossheads seat 1cm inside each post face. Ending them at post
            # centres makes perpendicular crossheads share coplanar top faces.
            inset=direction/np.linalg.norm(direction)*(post_section/2-.01)
            mesh.beam((*(np.array(post['xy'])+inset),high),
                      (*(np.array(other['xy'])-inset),high),.22,.25,solid.TIMBER,up=(0,0,1))
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


def rail_bearing(mesh,x,y,direction,across,roof,half_length):
    """A level post seat with a fitted underside embedded in the stringer."""
    centre=np.array([x,y])
    polygon=[centre+a*half_length*direction+b*.075*across for a,b in ((-1,-1),(1,-1),(1,1),(-1,1))]
    top=max(roof(*point) for point in polygon)+.02
    with mesh.tagged('access_stringer'):
        mesh.prism(polygon,lambda x,y:roof(x,y)-.01,top,solid.TIMBER_DARK)
    return top


def emit_access_floor(mesh,surface,thickness=.16):
    """Emit precisely the planar caps consumed by the walking/ground audits."""
    for triangle in floor_caps(surface):
        xy,z=triangle[:,:2],triangle[:,2]
        gradient=np.linalg.solve(xy[1:]-xy[0],z[1:]-z[0])
        def roof(x,y):return float(z[0]+(np.array([x,y])-xy[0])@gradient)
        mesh.prism(xy,lambda x,y:roof(x,y)-thickness,roof,solid.TIMBER_DARK,top=solid.DECK)


FLOOR_RIM_LINK_Z = 701.590
TOWER_LANDING_WORLD = (1331.50, 2494.00, 759.60)
TOWER_PORTAL_WORLD = (1326.90, 2494.00, 759.60)

CRATER_LINK_WAYPOINTS = (
    (1230.09, 2075.43, FLOOR_RIM_LINK_Z, False),
    (1215.00, 2092.00, 702.60, False),
    (1185.00, 2088.00, 703.50, False),
)

CRATER_PLATFORM_LINK_WAYPOINTS = (
    (1188.80, 2059.00, 703.68, False),
    (1191.00, 2061.50, 703.71, False),
)

CRATER_SE_TOWER_WAYPOINTS = (
    (1159.30, 2067.50, 701.14, False),
    (1185.00, 2088.00, 703.50, False),
    (1202.20, 2100.60, 704.90, False),
    (1215.00, 2110.00, 714.74, True),
    (1243.40, 2175.00, 719.80, False),
    (1253.90, 2196.60, 735.97, True),
    (1292.00, 2236.00, 739.80, False),
    (1308.00, 2253.20, 755.48, True),
    (1335.00, 2335.00, 756.80, False),
    (1342.00, 2390.00, 757.60, False),
    (1338.00, 2445.00, 758.60, False),
    (1331.50, 2491.00, 759.60, False),
)

CRATER_NW_TOWER_WAYPOINTS = (
    (508.26, 2765.74, 712.40, False),
    (544.00, 2800.00, 716.30, False),
    (612.00, 2852.00, 718.50, False),
    (695.00, 2894.00, 721.50, False),
    (780.00, 2912.00, 724.50, False),
    (872.00, 2908.00, 728.00, False),
    (960.00, 2894.00, 731.50, False),
    (1050.00, 2884.00, 735.00, False),
    (1132.00, 2844.00, 738.50, False),
    (1192.00, 2774.00, 742.00, False),
    (1248.00, 2700.00, 746.00, False),
    (1292.00, 2620.00, 750.50, False),
    (1322.00, 2555.00, 755.20, False),
    (1331.50, 2497.00, 759.60, False),
)


def floor_rim_link_ground(G):
    """Overlay the level link reception pad under floor_rim's short access stair."""
    from types import SimpleNamespace
    from gondola.products import triangle_surface
    pad = np.array([
        [[1226.5, 2072.0, FLOOR_RIM_LINK_Z], [1233.5, 2072.0, FLOOR_RIM_LINK_Z], [1233.5, 2079.0, FLOOR_RIM_LINK_Z]],
        [[1226.5, 2072.0, FLOOR_RIM_LINK_Z], [1233.5, 2079.0, FLOOR_RIM_LINK_Z], [1226.5, 2079.0, FLOOR_RIM_LINK_Z]],
    ], float)
    tris = np.concatenate([G.trail.triangles, pad], axis=0)
    trail = triangle_surface(tris, G.trail.owner)
    def contact(xy):
        xy = np.asarray(xy, float)
        hit = trail.upper(*xy.T, require=False)
        height, owners = np.empty(len(xy), float), np.empty(len(xy), object)
        if (~hit.covered).any():
            height[~hit.covered], owners[~hit.covered] = G.base(xy[~hit.covered])
        height[hit.covered] = hit.height[hit.covered]
        owners[hit.covered] = trail.owner
        return height, owners
    return SimpleNamespace(surfaces=G.surfaces, bounds=G.bounds, trail=trail, base=G.base, contact=contact)


def emit_crater_waypoint_hub(mesh, G, frame, wx, wy, wz, radius=2.35):
    """Level 12-gon turn hub raised 2.5 cm above adjoining spans to prevent coplanar caps."""
    c = local_xy([[wx, wy]], frame)[0]
    lz = wz - frame[3]
    poly = [c + np.array([radius * math.cos(2 * math.pi * k / 12), radius * math.sin(2 * math.pi * k / 12)]) for k in range(12)]
    with mesh.tagged('access_landing'):
        mesh.prism(poly, lz - .255, lz + .025, solid.TIMBER_DARK, top=solid.DECK)
    return timber_support(mesh, G, frame, c, lz - .08, .28)


def emit_crater_path_chain(mesh, rail_layout, G, frame, waypoints, width=4.0, end_hubs=(True, True)):
    """Build a 4 m wide terrain-supported path chain (<=8% walking ramps and stairs)."""
    supports = []
    for idx, (wx, wy, wz, _) in enumerate(waypoints):
        if (idx == 0 and not end_hubs[0]) or (idx == len(waypoints) - 1 and not end_hubs[1]):
            continue
        sup = emit_crater_waypoint_hub(mesh, G, frame, wx, wy, wz)
        if sup:
            supports.append(sup)
    rail_inset = .18
    bearing_half_length = .08
    support_section = .20
    for (wx0, wy0, wz0, _), (wx1, wy1, wz1, is_stair) in zip(waypoints[:-1], waypoints[1:]):
        p0 = local_xy([[wx0, wy0]], frame)[0]
        p1 = local_xy([[wx1, wy1]], frame)[0]
        z0, z1 = wz0 - frame[3], wz1 - frame[3]
        if is_stair and z1 > z0:
            p0, p1 = p1, p0
            z0, z1 = z1, z0
        delta = p1 - p0
        full_len = float(np.linalg.norm(delta))
        if full_len <= 3.6:
            direction = delta / max(full_len, 1e-6)
            across = np.array([direction[1], -direction[0]])
            start, end = p0, p1
            span_len = full_len
        else:
            direction = delta / full_len
            across = np.array([direction[1], -direction[0]])
            trim = 1.65
            start = p0 + trim * direction
            end = p1 - trim * direction
            span_len = full_len - 2 * trim
        if is_stair:
            n = max(2, int(round((z0 - z1) / .24)))
            rise = (z0 - z1) / n
            tread = span_len / n
            for k in range(n):
                a, b = k * tread, (k + 1) * tread
                h = z0 - (k + 1) * rise
                poly = [start + a * direction - across * width / 2, start + b * direction - across * width / 2,
                        start + b * direction + across * width / 2, start + a * direction + across * width / 2]
                with mesh.tagged('access_floor'):
                    emit_access_floor(mesh, {'poly': [list(p) for p in poly], 'top': h})
                front = start + a * direction
                with mesh.tagged('access_riser'), mesh.at((*front, 0), math.degrees(math.atan2(direction[1], direction[0]))):
                    mesh.box((.018, 0, h + rise / 2), (.036, width - .04, rise), solid.TIMBER)
        else:
            rail_len = max(.6, span_len - .24)
            n_rail = max(1, math.ceil(rail_len / 6.4))
            bay = rail_len / n_rail
            fl_breaks = [0., *[.12 + (j + .25) * bay for j in range(n_rail)], span_len]
            for s_a, s_b in zip(fl_breaks[:-1], fl_breaks[1:]):
                u0, u1 = s_a / span_len, s_b / span_len
                ca, cb = start + s_a * direction, start + s_b * direction
                za, zb = z0 + (z1 - z0) * u0, z0 + (z1 - z0) * u1
                poly = [ca - across * width / 2, cb - across * width / 2,
                        cb + across * width / 2, ca + across * width / 2]
                surface = {'poly': [list(p) for p in poly], 'z1': [za, zb, zb, za]}
                with mesh.tagged('access_floor'):
                    emit_access_floor(mesh, surface)
        def stringer_top(x, y, s0=start, d0=direction, L0=span_len, za=z0, zb=z1):
            u = float((np.array([x, y]) - s0) @ d0 / max(L0, 1e-6))
            return za + (zb - za) * u + .25
        ext = .20 if full_len > 3.6 else -.05
        rail_spacing = 3.6 if is_stair else 6.4
        rail_len = max(.6, span_len - .24)
        n_rail = max(1, math.ceil(rail_len / rail_spacing))
        bay = rail_len / n_rail
        str_breaks = [-ext, span_len + ext] if is_stair else [-ext, *[.12 + (j + .75) * bay for j in range(n_rail)], span_len + ext]
        for side in (-1, 1):
            offset = side * (width / 2 - rail_inset) * across
            for first_s, last_s in zip(str_breaks[:-1], str_breaks[1:]):
                h = start + offset + first_s * direction
                t = start + offset + last_s * direction
                spoly = [h - across * .09, t - across * .09, t + across * .09, h + across * .09]
                with mesh.tagged('access_stringer'):
                    mesh.prism(spoly, lambda x, y, st=stringer_top: st(x, y) - .55, stringer_top, solid.TIMBER)
            ra = start + offset + .12 * direction
            rb = end + offset - .12 * direction
            if np.linalg.norm(rb - ra) >= .6:
                railing(mesh, rail_layout, [ra, rb], 'timber', spacing=rail_spacing,
                        z0=lambda x, y, st=stringer_top, d0=direction, a0=across: rail_bearing(mesh, x, y, d0, a0, st, bearing_half_length),
                        on=('access_stringer',))
        step_m = 6.0 if is_stair else 12.0
        dists = np.linspace(.6, max(.6, span_len - .6), max(2, int(math.ceil(span_len / step_m)) + 1))
        for dist in dists:
            for side in (-1, 1):
                pt = start + dist * direction + side * (width / 2 - rail_inset) * across
                sup = timber_support(mesh, G, frame, pt, stringer_top(*pt) - .45, support_section)
                if sup:
                    supports.append(sup)
    return supports


def emit_tower_landing_and_hoist_portal(mesh, rail_layout, G, frame):
    """Build the 6x6 m railed timber landing and 3.2x3.2x4.5 m Kiyomizu hoist portal at the tower's east foot."""
    supports = []
    lx0, ly0, wz = TOWER_LANDING_WORLD
    lz = wz - frame[3]
    def L(wx, wy):
        return local_xy([[wx, wy]], frame)[0]
    u_east = L(lx0 + 1., ly0) - L(lx0, ly0)
    u_north = L(lx0, ly0 + 1.) - L(lx0, ly0)
    yaw_east = math.degrees(math.atan2(u_east[1], u_east[0]))
    # 1. 6x6 m railed timber landing (x=1328.5..1334.5, y=2491.0..2497.0)
    land_poly = [L(1328.5, 2491.0), L(1334.5, 2491.0), L(1334.5, 2497.0), L(1328.5, 2497.0)]
    with mesh.tagged('access_landing'):
        mesh.prism(land_poly, lz - .28, lz, solid.TIMBER_DARK, top=solid.DECK)
    for wx, wy in ((1329.1, 2491.6), (1333.9, 2491.6), (1333.9, 2496.4), (1329.1, 2496.4)):
        sup = timber_support(mesh, G, frame, L(wx, wy), lz - .12, .28)
        if sup:
            supports.append(sup)
    rail_runs = (
        (L(1334.32, 2491.18), L(1334.32, 2496.82)),
        (L(1328.68, 2491.18), L(1329.45, 2491.18)),
        (L(1333.55, 2491.18), L(1334.12, 2491.18)),
        (L(1328.68, 2496.82), L(1329.45, 2496.82)),
        (L(1333.55, 2496.82), L(1334.12, 2496.82)),
        (L(1328.68, 2491.38), L(1328.68, 2492.25)),
        (L(1328.68, 2495.75), L(1328.68, 2496.62)),
    )
    for a, b in rail_runs:
        railing(mesh, rail_layout, [a, b], 'timber', spacing=2.0, z0=lz, on=('access_landing',))
    # 2. 3.2x3.2x4.5 m Kiyomizu timber hoist portal (centred at 1326.9, 2494.0)
    px, py, _ = TOWER_PORTAL_WORLD
    apron_poly = [L(1325.2, 2492.3), L(1328.8, 2492.3), L(1328.8, 2495.7), L(1325.2, 2495.7)]
    with mesh.tagged('access_landing'):
        mesh.prism(apron_poly, lz - .34, lz - .04, solid.TIMBER_DARK, top=solid.TIMBER)
    # Visible 2.4x2.4 m lift platform inside the portal frame
    plat_poly = [L(1325.7, 2492.8), L(1328.1, 2492.8), L(1328.1, 2495.2), L(1325.7, 2495.2)]
    with mesh.tagged('access_floor'):
        mesh.prism(plat_poly, lz - .12, lz + .04, solid.TIMBER_DARK, top=solid.DECK)
    c_portal = L(px, py)
    with mesh.at((*c_portal, lz), yaw_east), mesh.grained((0, 0, 1)):
        for sx in (-1.45, 1.45):
            for sy in (-1.45, 1.45):
                mesh.box((sx, sy, 2.15), (.32, .32, 4.70), solid.TIMBER)
        # Kiyomizu nuki tie beams with projecting tenons & iron joint plates on N, S, W faces
        for zn in (2.55, 3.75):
            for sy in (-1.45, 1.45):
                mesh.box((0., sy, zn), (3.23, .20, .22), solid.TIMBER_DARK)
                for sx in (-1.45, 1.45):
                    mesh.box((sx, sy, zn), (.10, .33, .10), solid.IRON)
            mesh.box((-1.45, 0., zn + .03), (.16, 3.23, .18), solid.TIMBER_DARK)
        # Top ring beams & central hoist winch beam
        for sy in (-1.45, 1.45):
            mesh.box((0., sy, 4.34), (3.23, .24, .24), solid.TIMBER_DARK)
        for sx in (-1.45, 1.45):
            mesh.box((sx, 0., 4.37), (.22, 3.23, .20), solid.TIMBER_DARK)
        mesh.box((0., 0., 4.33), (.26, 2.67, .18), solid.TIMBER_DARK)
        # Winch drum, iron flanges, lift bail uprights & vertical hoist rope
        mesh.box((0., 0., 4.105), (.32, .80, .28), solid.IRON)
        mesh.box((0., 0., 4.105), (.33, .50, .33), solid.ROPE)
        for sy in (-1.05, 1.05):
            mesh.box((0., sy, 1.1025), (.12, .12, 2.135), solid.IRON)
        mesh.box((0., 0., 2.235), (.16, 2.11, .14), solid.IRON)
        mesh.box((0., 0., 3.1225), (.08, .08, 1.645), solid.ROPE)
    for wx, wy in ((1325.45, 2492.55), (1328.35, 2492.55), (1328.35, 2495.45), (1325.45, 2495.45)):
        sup = timber_support(mesh, G, frame, L(wx, wy), lz - .15, .32)
        if sup:
            supports.append(sup)
    return supports


def access_stair(key,layout,G,frame):
    access=layout['access'][0]
    edge=np.asarray(access['edge'],float);start=edge.mean(0)
    across=edge[1]-edge[0];across/=np.linalg.norm(across)
    direction=np.array([across[1],-across[0]])
    if direction@(start-np.asarray(access['point']))<0:
        direction=-direction;across=-across
    width=min(2.2,float(np.linalg.norm(edge[1]-edge[0]))-.10)
    top=float(access['z'])
    mesh=solid.Mesh(f'GD_{key}_Access')
    rail_layout=Station(key,dict(P.DEFAULTS),P.derived(P.DEFAULTS))
    preface=[[*start,top]]
    landing_surfaces=[]
    turn=STATIONS[key].get('access_turn_deg',0.)
    if turn:
        if turn not in (90.,180.):
            raise ValueError('Access landing supports quarter turns and a return flight only')
        old_start=start.copy();old_direction=direction.copy();old_across=across.copy()
        if turn==90.:
            polygon=[start-across*width/2,start+direction*width-across*width/2,
                     start+direction*width+across*width/2,start+across*width/2]
            start=old_start+old_direction*width/2+old_across*width/2
            direction=old_across;across=-old_direction
            surface={'poly':[list(p) for p in polygon],'top':top}
            rails=[(polygon[0],polygon[1]),(polygon[1],polygon[2])]
            preface.extend([[*(old_start+old_direction*width/2),top],[*start,top]])
        else:
            # One flat switchback landing joins the real kit head to a parallel
            # return flight. Its .4m separation clears the 2.4m kit boardwalk,
            # the 2.2m flight and their side rails rather than stacking them.
            separation=width+.4
            far=separation+width/2+.4
            polygon=[start-across*width/2,start+direction*width-across*width/2,
                     start+direction*width+across*far,start+across*far]
            start=old_start+separation*old_across
            direction=-old_direction;across=-old_across
            entry=[old_start-old_across*width/2,old_start+old_across*width/2]
            exit_=[start-across*width/2,start+across*width/2]
            surface={'poly':[list(p) for p in polygon],'top':top,
                     'entry':[list(p) for p in entry],'exit':[list(p) for p in exit_]}
            rails=[(polygon[0],polygon[1]),(polygon[1],polygon[2]),
                   (polygon[2],polygon[3]),(polygon[3],exit_[0])]
            preface.extend([[*(old_start+old_direction*width/2),top],
                            [*(start+old_direction*width/2),top],[*start,top]])
        landing_surfaces.append(surface)
        with mesh.tagged('access_landing'):
            emit_access_floor(mesh,surface,.24)
        for index,(a,b) in enumerate(rails):
            railing(mesh,rail_layout,[a,b],'timber',z0=top,on=('access_landing',),start_post=index==0)
        if turn==180.:
            # The boardwalk supplies the post at the entry; the return flight
            # supplies the other end of this short separator rail.
            railing(mesh,rail_layout,[entry[1],exit_[1]],'timber',z0=top,
                    on=('access_landing',),start_post=False)
    fit=STATIONS[key].get('access_fit')
    join_length=.8;tread=.32
    if fit is not None:
        n,length,join_length=fit['risers'],fit['run_m'],fit['join_m']
        tread=fit.get('tread_m',.32)
        if (type(n) is not int or not 1<=n<=200 or
                not all(type(v) in (int,float) and math.isfinite(v) and v>0 for v in (length,join_length))):
            raise ValueError(f'{key}: invalid authored access fit')
        end=start+length*direction
    else:
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
    flights=fit.get('flights',[n]) if fit else [n]
    landing_length=fit.get('landing_m',1.2) if fit else 1.2
    if (not isinstance(flights,list) or not flights or sum(flights)!=n or
            any(type(v) is not int or v<=0 for v in flights) or
            not math.isfinite(tread) or tread<W.TREAD_MIN or
            not math.isfinite(landing_length) or landing_length<1.2):
        raise ValueError(f'{key}: invalid access flight/landing plan')
    rest_after=set(np.cumsum(flights)[:-1])
    last_tread=length-join_length-(n-1)*tread-len(rest_after)*landing_length
    if last_tread<W.TREAD_MIN-1e-9:
        raise ValueError(f'{key}: access fit reverses or shortens the last tread')
    route=preface
    G_stair=floor_rim_link_ground(G) if key=='floor_rim' and turn==0. else G
    edge_t,edge_z=ground_edge(G_stair,frame,end,across,width)
    bottom=float(max(edge_z))
    rise=(top-bottom)/n
    if not .10<=rise<=.30:
        raise ValueError(f'{key}: fitted final stair riser is invalid')
    surfaces=landing_surfaces[:];treads=[];joins=[]
    cursor=0.;stringer_profile=[[0.,top+.25]]
    for k in range(n):
        a,b=cursor,cursor+tread if k<n-1 else length-join_length
        height=top-(k+1)*rise
        centre=start+(a+b)/2*direction
        poly=[start+a*direction-across*width/2,start+b*direction-across*width/2,
              start+b*direction+across*width/2,start+a*direction+across*width/2]
        surface={'poly':[list(p) for p in poly],'top':height}
        with mesh.tagged('access_floor'):
            emit_access_floor(mesh,surface)
        front=start+a*direction
        with mesh.tagged('access_riser'),mesh.at((*front,0),math.degrees(math.atan2(direction[1],direction[0]))):
            mesh.box((.018,0,height+rise/2),(.036,width,rise),solid.TIMBER)
        surfaces.append(surface);treads.append(surface)
        route.append([*centre,height])
        stringer_profile.append([b,height+.25]);cursor=b
        if k+1 in rest_after:
            a,b=cursor,cursor+landing_length
            polygon=[start+a*direction-across*width/2,start+b*direction-across*width/2,
                     start+b*direction+across*width/2,start+a*direction+across*width/2]
            surface={'poly':[list(p) for p in polygon],'top':height,'rest_landing':True}
            with mesh.tagged('access_floor'):
                emit_access_floor(mesh,surface,.24)
            surfaces.append(surface);treads.append(surface)
            route.append([*(start+(a+b)/2*direction),height])
            stringer_profile.append([b,height+.25]);cursor=b
    # The fitted join shares every terrain triangle-edge knot. Its outer
    # edge is the actual rendered ground profile rather than a flat guessed lip.
    join_start=end-join_length*direction
    for ta,tb,za,zb in zip(edge_t[:-1],edge_t[1:],edge_z[:-1],edge_z[1:]):
        polygon=[join_start+ta*across,end+ta*across,end+tb*across,join_start+tb*across]
        def floor(x,y):
            q=np.array([x,y])-join_start
            u=float(np.clip(q@direction/join_length,0,1))
            v=float(np.clip((q@across-ta)/(tb-ta),0,1))
            return bottom+u*((1-v)*za+v*zb-bottom)
        surface={'poly':[list(p) for p in polygon],'z1':[floor(*p) for p in polygon]}
        with mesh.tagged('access_floor'):
            emit_access_floor(mesh,surface)
        surfaces.append(surface);joins.append(surface)
    walk_proof=access_walk_audit(G_stair,frame,edge,top,landing_surfaces,treads,joins,end,direction,across,
                               step_limit=W.STEP,tread_min=W.TREAD_MIN,walk_width=W.MIN_WIDTH,last_tread=last_tread,tread=tread)
    stringer_profile.append([length,bottom+.25])
    profile=np.asarray(stringer_profile)
    # Every profile bend sits on a tread, riser or landing end plane. A rested
    # stringer is split at its bends, so shift them half a riser thickness down
    # the stair: its split end caps then never lie on those same-facing faces.
    profile[:,0]+=.018
    def stringer_top(x,y):
        distance=float((np.array([x,y])-start)@direction)
        if rest_after:
            return float(np.interp(distance,profile[:,0],profile[:,1]))
        return top-(top-bottom)*distance/length+.25
    support_section=.20
    bearing_half_length=.08
    rail_inset=.18  # Clear the adjoining landing post and the .18m stringer section.
    for side in (-1,1):
        offset=side*(width/2-rail_inset)*across
        a,b=start+offset,end+offset
        # Clear both the .20m support-post end planes and .16m bearing pads.
        extension=max(support_section/2,bearing_half_length)+.02
        breaks=[-extension,length+extension]
        if rest_after:
            slopes=np.diff(profile[:,1])/np.diff(profile[:,0])
            breaks=[-extension,float(profile[0,0]),*[float(profile[i,0]) for i in range(1,len(profile)-1)
                                   if abs(slopes[i]-slopes[i-1])>1e-8],float(profile[-1,0]),length+extension]
        for first,last in zip(breaks,breaks[1:]):
            h=start+offset+first*direction;t=start+offset+last*direction
            polygon=[h-across*.09,t-across*.09,t+across*.09,h+across*.09]
            with mesh.tagged('access_stringer'):
                mesh.prism(polygon,lambda x,y:stringer_top(x,y)-.55,stringer_top,solid.TIMBER)
        railing(mesh,rail_layout,[a,b],'timber',
                z0=lambda x,y:rail_bearing(mesh,x,y,direction,across,stringer_top,bearing_half_length),on=('access_stringer',))
    route.append([*end,float(np.interp(0,edge_t,edge_z))])
    # Validate complete owned footprints against the exact generated cap
    # triangles: sampled corners cannot detect a narrow crest or interior hole.
    floor_limit=.03
    intrusion=[]
    for surface in surfaces:
        polygon=np.asarray(surface['poly'])
        heights=surface['z1'] if 'z1' in surface else np.full(len(polygon),surface['top'])
        value=floor_intrusion(G,world_xy(polygon,frame),np.asarray(heights)+frame[3])
        if value>floor_limit:
            raise ValueError(f'{key}: ground intersects an access floor by {value:.6f}m')
        intrusion.append(value)
    ground_proof={'complete_coverage':True,'surfaces':len(surfaces),
                  'maximum_intrusion_m':max(intrusion),'allowance_m':floor_limit,'pass':True}
    supports=[]
    if turn==180.:
        polygon=np.asarray(landing_surfaces[0]['poly'])
        for point in (polygon[1],polygon[2],polygon[3]):
            support=timber_support(mesh,G,frame,point,top-.23,support_section)
            if support:
                supports.append(support)
    # A post's .8m stone foot stands above the ground, so its axis-aligned
    # footprint must stay behind the stair's end plane, clear of the exit walk.
    foot_reach=.4*(abs(direction[0])+abs(direction[1]))+.02
    for distance in np.arange(0,length+.01,3):
        distance=min(distance,length-foot_reach)
        for side in (-1,1):
            point=start+distance*direction+side*(width/2-rail_inset)*across
            level=stringer_top(*point)-.45
            support=timber_support(mesh,G,frame,point,level,support_section)
            if support:
                supports.append(support)
    if key=='floor_rim':
        supports.extend(emit_crater_path_chain(mesh,rail_layout,G,frame,CRATER_PLATFORM_LINK_WAYPOINTS,width=4.0))
        supports.extend(emit_crater_path_chain(mesh,rail_layout,G,frame,CRATER_LINK_WAYPOINTS,width=4.0))
        supports.extend(emit_crater_path_chain(mesh,rail_layout,G,frame,CRATER_NW_TOWER_WAYPOINTS,width=4.0))
    elif key=='southeast':
        supports.extend(emit_crater_path_chain(mesh,rail_layout,G,frame,CRATER_SE_TOWER_WAYPOINTS,width=4.0,end_hubs=(True,False)))
        supports.extend(emit_tower_landing_and_hoist_portal(mesh,rail_layout,G,frame))
    return mesh,{'route':route,'width':width,'risers':n,'riser':rise,'tread':tread,'flights':flights,'landing_m':landing_length,
                 'run_m':length,'join_m':join_length,'walk_proof':walk_proof,
                 'ground_proof':ground_proof,'rail_seats':rail_layout.seats,'obstacles':rail_layout.proxies,'turn_deg':turn,'ground_edge_tolerance':.0001,'ground_edge':{'t':edge_t.tolist(),'z':edge_z.tolist()},'surfaces':surfaces,'supports':supports}


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
        keep=(hi[:,0]>=low[0])&(lo[:,0]<=high[0])&(hi[:,1]>=low[1])&(lo[:,1]<=high[1])
        tri=tri[keep]
        if len(tri)>4000:
            sub_lo,sub_hi=tri[:,:,:2].min(1),tri[:,:,:2].max(1)
            near=np.zeros(len(tri),bool)
            for first,last,*_ in mesh.parts:
                indices={i for face in mesh.faces[first:last] for i in face}
                pts=world[list(indices)]
                a,b=pts.min(0)-1.0,pts.max(0)+1.0
                near|=(sub_hi[:,0]>=a[0])&(sub_lo[:,0]<=b[0])&(sub_hi[:,1]>=a[1])&(sub_lo[:,1]<=b[1])
            tri=tri[near].copy()
        else:
            tri=tri.copy()
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
    c_lo,c_hi=candidates[:,:,:2].min(1),candidates[:,:,:2].max(1)
    for first,last,*_ in mesh.parts:
        indices={i for face in mesh.faces[first:last] for i in face}
        points=xy[list(indices)];a,b=points.min(0),points.max(0)
        part_candidates=candidates[(c_hi[:,0]>=a[0])&(c_lo[:,0]<=b[0])&(c_hi[:,1]>=a[1])&(c_lo[:,1]<=b[1])]
        if not len(part_candidates):
            continue
        rectangle=[a,[b[0],a[1]],b,[a[0],b[1]]]
        for triangle in part_candidates:
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


def export_world(mesh,folder,mats,limit=50000,*,frame=None,G=None,seats=(),riding=None,structures=None):
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
    world_structure = None
    if structures is not None:
        vertices=np.c_[world_xy(np.asarray(mesh.verts)[:,:2],frame),np.asarray(mesh.verts)[:,2]+frame[3]]
        # The Belmonte-side tower must also leave all town walking space clear
        # in plan, independently of paving/roof height. All towers retain the
        # complete3D refusal; distant buried country is not walking space.
        world_structure=structures.static(vertices,require_bounds=True,plan_clear=mesh.name=='GD_L2_0_Tower')
    obj,names=solid.to_object(mesh,mats)
    path=folder/f'{mesh.name}.fbx';solid.export_fbx([obj],path)
    bpy.data.objects.remove(obj,do_unlink=True)
    return {'name':mesh.name,'materials':names,'triangles':mesh.tris(),'closed':proof,
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'coplanar':coplanar,
            'seating':seating,'carried':carried,'riding_plan_clear':frame is not None,
            'world_structure':world_structure}


def recovered_rope_axes(mesh,path,ring_counts):
    """Read the actual emitted FBX before modelling its centimetre vertex buffer."""
    before=set(bpy.data.objects)
    created=[]
    try:
        bpy.ops.import_scene.fbx(filepath=str(path),use_image_search=False,use_anim=False)
        created=[obj for obj in bpy.data.objects if obj not in before]
        meshes=[obj for obj in created if obj.type=='MESH']
        if len(meshes)!=1:raise ValueError('Rope FBX must contain one emitted mesh')
        obj=meshes[0]
        vertices=np.array([tuple(vertex.co) for vertex in obj.data.vertices],float)
        world=np.array([tuple(obj.matrix_world@vertex.co) for vertex in obj.data.vertices],float)
        if not len(vertices) or not np.isfinite(vertices).all() or not np.isfinite(world).all():
            raise ValueError('Incomplete rope FBX control points or world transform')
        actual,indices=np.unique(vertices,axis=0,return_index=True)
        world=world[indices]
        from mathutils.kdtree import KDTree
        tree=KDTree(len(actual))
        for index,point in enumerate(actual):tree.insert(point,index)
        tree.balance()
        recovered,proof=recover_rope_vertices(mesh.verts,actual,world,lambda point:tree.find(point)[1])
        axes=float32_cm_axes(recovered,ring_counts)
        return axes,proof
    finally:
        for obj in created:
            data=obj.data if obj.type=='MESH' else None
            bpy.data.objects.remove(obj,do_unlink=True)
            if data is not None and data.users==0:bpy.data.meshes.remove(data)


def tower_fit(key,s,height,A,direction,G,p,saddle=None,build=True):
    xy=A+s*direction
    prototype=Tower(p,height)
    feet=np.array([(sx*prototype.hx(.7)+u*.5,sy*prototype.hy(.7)+v*.5)
                   for sx in (-1,1) for sy in (-1,1) for u,v in ((-1,-1),(1,-1),(1,1),(-1,1))])
    lateral=np.array([-direction[1],direction[0]])
    world=xy+feet[:,0,None]*direction+feet[:,1,None]*lateral
    heights=[owned_range(G,world[i:i+4])[1] for i in range(0,len(world),4)]
    broad=xy+np.array([[-3,-3],[3,-3],[3,3],[-3,3]])
    datum=max(owned_range(G,broad,contact=False)[1]+.6,max(heights)+.15)
    frame=(xy,direction,lateral,datum)
    def contact(x,y):
        return float(G.contact(world_xy([[x,y]],frame))[0][0]-datum)
    def footprint(poly):
        low,high=owned_range(G,world_xy(poly,frame))
        return low-datum,high-datum
    tower=Tower(p,height,ground=contact,ground_bounds=footprint,saddle=saddle)
    row={'id':key,'s':s,'height':height,'origin':[float(xy[0]),float(xy[1]),datum],
         'heading':math.degrees(math.atan2(direction[1],direction[0]))}
    if not build:
        return tower,None,frame,row
    mesh=tower.build();mesh.name=f'GD_{key}_Tower'
    return tower,mesh,frame,row


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
        clearance=K.rope_check(cab,path,[frame for i in range(0,len(frames),10) for frame in frames[i:i+2]])
        jaw=K.jaw_contact(cab,path,[frame for i in range(0,len(frames),10) for frame in frames[i:i+2]])
        if not clearance['ok'] or not jaw['ok']:
            raise ValueError(f'{key}: actual cabin/jaw clearance failed: {clearance}, {jaw}')
        minimum=min(minimum,clearance['min_distance_from_rope_axis_m'])
        count+=len(frames)
        print(f'{key} fitted span contact: {min(start+128,len(samples))}/{len(samples)} stations, '
              f'{count} directed poses, {time.monotonic()-t0:.1f}s',flush=True)
    return {'poses':count,'groove_max_mm':maxima,'hardware_min_m':minimum,'pass':True}


def ground_gap(profile,A,direction,G,drop):
    """Whole owned triangles over both tracks and the inflated cabin footprint."""
    from gondola.clearance import riding_clearance
    lateral=np.array([-direction[1],direction[0]])
    best=float('inf');approach=float('inf');count=0
    for start in np.arange(profile[0,0],profile[-1,0],32.):
        end=min(profile[-1,0],start+32.)
        s=np.r_[start,profile[(profile[:,0]>start)&(profile[:,0]<end),0],end]
        piece=np.c_[s,np.interp(s,profile[:,0],profile[:,1])]
        polygon=[A+(start-1.15)*direction-4.3*lateral,A+(end+1.15)*direction-4.3*lateral,
                 A+(end+1.15)*direction+4.3*lateral,A+(start-1.15)*direction+4.3*lateral]
        triangles=owned_triangles(G,polygon)
        proof=riding_clearance(triangles,A,direction,piece,lateral=4.3,half_length=1.15,drop=drop)
        value=proof['minimum_m']
        if value is None:raise ValueError('No complete ground clearance evidence')
        approach=min(approach,value);count+=proof['triangles_tested']
        lo,hi=max(start,35.),min(end,profile[-1,0]-35.)
        if hi>lo:
            knots=np.r_[lo,profile[(profile[:,0]>lo)&(profile[:,0]<hi),0],hi]
            interior=np.c_[knots,np.interp(knots,profile[:,0],profile[:,1])]
            interior_proof=riding_clearance(triangles,A,direction,interior,lateral=4.3,half_length=1.15,drop=drop)
            if interior_proof['minimum_m'] is not None:best=min(best,interior_proof['minimum_m'])
        print(f'GONDOLA complete ground clearance {end:.1f}/{profile[-1,0]:.1f}m, {count} triangles',flush=True)
    if approach<.03:raise ValueError(f'Cabin intersects approach terrain: {approach:.3f}m')
    if best<6.:raise ValueError(f'Cabin-to-final-ground clearance {best:.3f}m is below6m')
    return {'minimum_sampled_m':best,'minimum_approach_m':approach,'station_approach_m':35.,
            'triangles_tested':count,'complete_coverage':True,'pass':True}


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
    structure_receipt=validate_structures(yori.OUT)
    with np.load(yori.OUT/'gondola/world/structures.npz',allow_pickle=False) as arrays:
        structures=StructureClearance(arrays,structure_receipt['inputs']['selection']['bounds_m'])
    layouts={kind:json.loads((yori.OUT/f'gondola/layout_{kind}.json').read_text()) for kind in ('valley','rim','crater')}
    folder=yori.OUT/'gondola/world';assets=folder/'assets';assets.mkdir(parents=True,exist_ok=True)
    mats=solid.make_materials({})
    cabin=Cabin(p,d);meshes,_=cabin.build();cab={'cabin':cabin,'meshes':meshes}
    envelope=structure_envelope(meshes,kit['pieces']['cabin']['grip']['pivot']['point'],
                               kit['pieces']['cabin']['door_frame']['leaves']['open_offsets'])
    structure_radius,structure_drop=envelope['radius_m'],envelope['drop_m']
    riding=PARK.piece_triangles()
    shells={kind:cls(kind,p,d).make() for kind,cls in (('valley',Valley),('rim',Rim),('crater',Crater))}
    stations={};frames={};exports=[];lines=[]
    flight_boxes=[]
    for line in LINES:
        first,last=line['stations']
        for key,other in ((first,last),(last,first)):
            print('GONDOLA SITE station',key,flush=True)
            data,frame=fit_station(key,other,G,layouts)
            scope=structures if line['id']=='L2' else None
            if scope is not None:
                data['structure_static']={}
            for shell in shells[data['kind']].values():
                untouched_riding(shell,frame,riding)
                if scope is not None:
                    vertices=np.c_[world_xy(np.asarray(shell.verts)[:,:2],frame),np.asarray(shell.verts)[:,2]+frame[3]]
                    data['structure_static'][shell.name]=scope.static(vertices,require_bounds=True)
            if scope is not None:
                proxies=layouts[data['kind']]['obstacles']
                vertices=np.array([[x,y,z] for proxy in proxies for edge in ('z0','z1')
                                   for (x,y),z in zip(proxy['poly'],proxy[edge])],float)
                vertices=np.c_[world_xy(vertices[:,:2],frame),vertices[:,2]+frame[3]]
                data['structure_collision']=scope.static(vertices,require_bounds=True)
            data['static_riding_clear']=True
            foundation,posts=station_foundation(key,layouts[data['kind']],G,frame)
            stair,access=access_stair(key,layouts[data['kind']],G,frame)
            if access['turn_deg']==180.:
                access['headroom_proof']=access_headroom(access,[*shells[data['kind']].values(),foundation,stair],layouts[data['kind']],G,frame)
            if key=='belmonte':
                from regions.zeppelin.layout import belmonte_path
                access['route'],data['walking_link']=walking_link(G,frame,access['route'],
                    [*shells[data['kind']].values(),foundation,stair],structures,belmonte_path(),access['surfaces'])
            if scope is not None:
                for mesh in [*shells[data['kind']].values(),foundation,stair]:
                    vertices=mesh_vertices(mesh,frame)
                    flight_boxes.append([vertices.min(0).tolist(),vertices.max(0).tolist()])
            loop=R.station_loop(p['gauge']/2,d['rope_height_above_platform'],d['rope_height_above_platform'],7.6,p['rope_radius'],step=.5).pts
            if scope is not None:
                data['structure_loop']=scope.path(placed(loop,frame),radius=structure_radius,drop=structure_drop)
                curve=placed(loop,frame)
                flight_boxes.append([(curve.min(0)-[structure_radius,structure_radius,structure_drop]).tolist(),
                                     (curve.max(0)+structure_radius).tolist()])
            data['jump']=station_jump_clearance(placed(loop,frame),riding,d['grip_to_floor']+p['cabin_floor_depth'])
            data['posts']=posts;data['access']=access
            data['boarding_routes']=W.station_routes(layouts[data['kind']],data['kind'])
            data['foundation']=export_world(foundation,assets,mats,frame=frame,G=G,riding=riding,structures=scope)
            data['access_mesh']=export_world(stair,assets,mats,frame=frame,G=G,seats=access['rail_seats'],riding=riding,structures=scope)
            exports += [data['foundation'],data['access_mesh']]
            stations[key]=data;frames[key]=frame
        A,B=np.asarray(STATIONS[first]['mouth']),np.asarray(STATIONS[last]['mouth'])
        length=float(np.linalg.norm(B-A));direction=(B-A)/length
        fitted=[]
        for index,(s,height) in enumerate(line['towers']):
            tower,mesh,frame,row=tower_fit(f'{line["id"]}_{index}',s,height,A,direction,G,p,build=False)
            fitted.append((s,height,frame,row))
        supports=[(.6,frames[first][3]+d['rope_height_above_platform'],False)]
        for s,height,frame,row in fitted:
            supports.append((s,frame[3]+height,True))
        supports.append((length-.6,frames[last][3]+d['rope_height_above_platform'],False))
        saddles=[row for row in tower_saddles(supports)]
        towers=[];tower_geometry=[]
        for index,(s,height,frame,row) in enumerate(fitted):
            tower,mesh,frame,row=tower_fit(f'{line["id"]}_{index}',s,height,A,direction,G,p,saddle=saddles[index+1])
            row['mesh']=export_world(mesh,assets,mats,limit=checks.BUDGET['tower'],frame=frame,G=G,seats=tower.seats,riding=riding,
                                     structures=structures if line['id']=='L2' else None)
            exports.append(row['mesh']);towers.append(row);tower_geometry.append((tower,mesh,row))
            if line['id']=='L2':flight_boxes.append(row['mesh']['world_structure']['bounds_m'])
        profile=centre_profile(supports)
        if line['id']=='L2':
            world_profile=np.c_[A+profile[:,0,None]*direction,profile[:,1]]
            # Every source segment is retained in a local box; one global box
            # would give the distant rim's height to the low Belmonte prefix.
            for i in range(0,len(world_profile)-1,100):
                chunk=world_profile[i:i+101]
                low=chunk.min(0)-np.array([p['gauge']/2+structure_radius]*2+[structure_drop])
                high=chunk.max(0)+np.array([p['gauge']/2+structure_radius]*2+[structure_radius])
                flight_boxes.append([low.tolist(),high.tolist()])
            from regions.zeppelin.layout import metadata as zeppelin_metadata
            flight=flight_clearance(zeppelin_metadata(),json.loads((yori.OUT/'zeppelin/manifest.json').read_text()),
                                    flight_boxes,profile,envelope)
        structure_span=(structures.span(profile,A,direction,radius=structure_radius,gauge=p['gauge'],drop=structure_drop)
                        if line['id']=='L2' else None)
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
        near_tolerance=near_rope_tolerance(audit['groove_max_mm'])
        print(f'{line["id"]} fitted rope: groove {audit["groove_max_mm"]:.6f}mm, '
              f'near axis allowance {near_tolerance*1000:.6f}mm',flush=True)
        for lod,(tolerance,sides) in enumerate(((near_tolerance,12),(.015,8),(.05,6))):
            mesh=solid.Mesh(f'GD_{line["id"]}_Rope_LOD{lod}')
            ring_counts=[];reduced_axes=[]
            for side in (-1,1):
                points=np.c_[A+profile[:,0,None]*direction+side*p['gauge']/2*normal,profile[:,1]]
                reduced=simplify(points,tolerance);ring_counts.append(len(reduced));reduced_axes.append(reduced)
                mesh.tube(reduced,p['rope_radius'],solid.STEEL,n=sides)
            row=export_world(mesh,assets,mats,limit=100000)
            row['axis_deviation_m']=tolerance
            row['minimum_view_distance_m']=(0.,1000.,2000.)[lod]
            if lod==0:
                row['groove_bound_mm']=audit['groove_max_mm']+.0005+tolerance*1000
                if row['groove_bound_mm']>2.:raise ValueError('Reduced rope exceeds jaw contact budget')
                stored,readback=recovered_rope_axes(mesh,assets/f'{mesh.name}.fbx',ring_counts)
                extra=max(float(np.linalg.norm(axis-reduced.astype(np.float32).astype(float),axis=1).max())
                          for axis,reduced in zip(stored,reduced_axes))
                local=[]
                for side,axis in zip((-1,1),stored):
                    delta=axis[:,:2]-A-side*p['gauge']/2*normal
                    local.append(np.c_[delta@direction,delta@normal,axis[:,2]])
                contact=stored_groove_audit(profile,local,cabin.groove,R.RopePath,p['rope_radius'])
                contact.update(readback,axis_extra_m=extra,axis_bound_m=tolerance+extra,
                               hardware_bound_m=audit['hardware_min_m']-tolerance-extra)
                row['stored_contact']=contact
                if not contact['pass'] or contact['hardware_bound_m']<.095:
                    raise ValueError(f'Stored rope exceeds contact/clearance budget: {contact}')
                print(f'{line["id"]} stored rope contact: {contact["poses"]} directed poses, '
                      f'{contact["bound_mm"]:.6f}mm bound, {row["triangles"]} triangles',flush=True)
            rope_exports.append(row);exports.append(row)
        lines.append({'id':line['id'],'stations':[first,last],'supports':supports,'towers':towers,
                      'profile':profile.tolist(),'circuit':circuit.tolist(),'ground':gap,'riding':clearance,
                      'structures':structure_span,'span_audit':audit,'rope_meshes':rope_exports})
        print('GONDOLA SITE line complete',line['id'],flush=True)
    result={'inputs':inputs,'stations':stations,'lines':lines,'exports':exports,'failures':[],
            'structure_envelope':envelope,'zeppelin_flight':flight,'kit_source':kit['source_hash']}
    if site_inputs(yori.OUT)!=inputs:
        raise ValueError('Gondola site source or world inputs changed during fitting')
    (folder/'site.json').write_text(json.dumps(result,separators=(',',':'))+'\n')
    validate_site(yori.OUT)
    print('GONDOLA SITE COMPLETE',len(stations),'stations',len(exports),'world meshes',flush=True)


if __name__=='__main__':
    main()
