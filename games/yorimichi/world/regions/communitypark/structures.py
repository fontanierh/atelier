"""Grounded steel trestles and the connected timber service ascent.

The source scene stays rigid. New geometry is authored in island metres, then
converted to the same park-local frame as the imported ramps. Sunburst's forest
structure concept guides the materials, bracing and switchback stair layout.
"""
from dataclasses import dataclass, field
import math
import numpy as np
from communitypark import layout as L
from communitypark.source import scene

DECK = 48.52
TOP = 85.606
FLIGHTS = 18
STEPS = 14
RUN = 6.3
WIDTH = 2.4


@dataclass
class Mesh:
    name: str
    material: str
    vertices: list = field(default_factory=list)
    faces: list = field(default_factory=list)
    uv: list = field(default_factory=list)

    def face(self, points):
        p = np.asarray(points, float); start = len(self.vertices)
        u = p[1]-p[0]; u /= np.linalg.norm(u)
        n = np.cross(p[1]-p[0], p[2]-p[0]); n /= np.linalg.norm(n)
        v = np.cross(n, u)
        self.vertices.extend(p.tolist()); self.faces.append(list(range(start, start+len(p))))
        self.uv.extend(np.column_stack((p@u, p@v)).tolist())

    def beam(self, a, b, width, depth=None):
        a, b = np.asarray(a, float), np.asarray(b, float); d = b-a
        if np.linalg.norm(d) < 1e-6: return
        d /= np.linalg.norm(d)
        seed = np.array([0., 0., 1.]) if abs(d[2]) < .9 else np.array([1., 0., 0.])
        u = np.cross(seed, d); u *= width/2/np.linalg.norm(u)
        v = np.cross(d, u); v *= (depth or width)/2/np.linalg.norm(v)
        corners = np.array([p+s*u+t*v for p in (a, b) for s, t in [(-1, -1), (1, -1), (1, 1), (-1, 1)]])
        for face in [(3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]:
            self.face(corners[list(face)])

    def box(self, centre, size):
        c = np.asarray(centre, float); self.beam(c-[0, 0, size[2]/2], c+[0, 0, size[2]/2], size[1], size[0])

    def triangle_faces(self):
        return [[f[0], f[k], f[k+1]] for f in self.faces for k in range(1, len(f)-1)]

    def triangles(self):
        return np.asarray(self.vertices)[self.triangle_faces()]


def heights(triangles, x, y):
    """Vertical intersections, including underside faces; vertical walls have no area."""
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    den = (b[:, 1]-c[:, 1])*(a[:, 0]-c[:, 0])+(c[:, 0]-b[:, 0])*(a[:, 1]-c[:, 1])
    valid = abs(den) > 1e-9; den = np.where(valid, den, np.inf)
    u = ((b[:, 1]-c[:, 1])*(x-c[:, 0])+(c[:, 0]-b[:, 0])*(y-c[:, 1]))/den
    v = ((c[:, 1]-a[:, 1])*(x-c[:, 0])+(a[:, 0]-c[:, 0])*(y-c[:, 1]))/den
    hit = valid & (u >= -1e-7) & (v >= -1e-7) & (u+v <= 1+1e-7)
    return (u*a[:, 2]+v*b[:, 2]+(1-u-v)*c[:, 2])[hit]


def stair_route():
    """Centreline waypoints through every flight and landing, ending at the original top ridge."""
    route = [[1300.25, 603.9, DECK], [1302.65, 603.9, DECK],
             [1302.65, 600.3, DECK], [1303.75, 600.3, DECK]]
    rise = (TOP-DECK)/FLIGHTS
    for flight in range(FLIGHTS):
        east = flight % 2 == 0; x = 1303.8 if east else 1310.1; y = 600.3 if east else 603.9
        direction = 1 if east else -1; z = DECK+flight*rise
        for step in range(1, STEPS+1):
            route.append([x+direction*(step-.5)*RUN/STEPS, y, z+step*rise/STEPS])
        end = x+direction*RUN; height = z+rise
        route.extend([[end, y, height], [end+direction*1.15, y, height]])
        if flight+1 < FLIGHTS:
            next_y = 603.9 if east else 600.3
            # The first tread overlaps the landing by 2.5 mm. Stay 5 cm
            # outside its edge until the next waypoint climbs onto its centre.
            route.extend([[end+direction*1.15, next_y, height], [end+direction*.05, next_y, height]])
    route.extend([[1302.65, 600.3, TOP], [1293.55, 600.3, TOP], [1293.55, 592.22, TOP]])
    return np.asarray(route)


def bridge_edges(path, half_width):
    """Mitered outside edges keep the walking line open at both bridge corners."""
    path = np.asarray(path)
    directions = np.diff(path[:, :2], axis=0)
    directions /= np.linalg.norm(directions, axis=1)[:, None]
    normals = np.column_stack((-directions[:, 1], directions[:, 0]))
    offsets = [normals[0]*half_width]
    for a, b in zip(normals, normals[1:]):
        offsets.append((a+b)*half_width/(1+np.dot(a, b)))
    offsets.append(normals[-1]*half_width)
    delta = np.column_stack((offsets, np.zeros(len(path))))
    return path+delta, path-delta


def raised_groups(source):
    """Connected raised pieces share one trestle, instead of a mast under every source tile."""
    parts = []
    for part in source.parts:
        triangles = L.place(part['vertices'][part['faces']])
        if triangles[..., 2].min() > DECK+.4:
            parts.append((part['node'], triangles, triangles.min((0, 1)), triangles.max((0, 1)), part['mesh']))
    parent = list(range(len(parts)))
    def root(k):
        while parent[k] != k: k = parent[k]
        return k
    for i, a in enumerate(parts):
        for j, b in enumerate(parts[:i]):
            if (a[4] in (17, 18, 21)) == (b[4] in (17, 18, 21)) and np.maximum(a[2]-b[3], b[2]-a[3]).max() < .55:
                parent[root(i)] = root(j)
    groups = {}
    for i, part in enumerate(parts): groups.setdefault(root(i), []).append(part)
    return list(groups.values())


def build(base_sampler):
    steel = Mesh('SM_CP_StructureSteel', 'CP_StructureSteel')
    timber = Mesh('SM_CP_ServiceTimber', 'CP_ServiceTimber')
    source = scene(); all_triangles = L.place(source.triangles()); contacts = []

    def ground(x, y):
        return float(L.ground(x, y, base_sampler) if L.inside(x, y) else base_sampler(x, y))

    def post(x, y, top, base=None, width=.26):
        base = ground(x, y)-.08 if base is None else base
        steel.beam([x, y, base], [x, y, top], width)
        foot_width = .3 if width < .2 else .7
        steel.box([x, y, base+.05], [foot_width, foot_width, .1])
        return [x, y, base]

    # Raised source pieces receive their own columns and cross-braced frames.
    # The lower contact is the original surface below, or the actual carved ground.
    for group in raised_groups(source):
        triangles = np.concatenate([part[1] for part in group])
        slender = all(part[4] in (17, 18, 21) for part in group)
        p = triangles.reshape(-1, 3); lo, hi = p.min(0), p.max(0)
        xs = np.linspace(lo[0]+.22, hi[0]-.22, max(2, math.ceil((hi[0]-lo[0])/4)+1))
        ys = np.linspace(lo[1]+.22, hi[1]-.22, max(2, math.ceil((hi[1]-lo[1])/4)+1))
        xy = [[x, y] for x in xs for y in (ys[0], ys[-1])]
        xy += [[x, y] for y in ys[1:-1] for x in (xs[0], xs[-1])]
        if slender:
            # Thin rails and ledges use two legs inset from the long ends.
            axis = int(np.argmax(hi[:2]-lo[:2])); centre = (lo[:2]+hi[:2])/2
            xy = [centre.copy(), centre.copy()]
            xy[0][axis] = lo[axis]+.5; xy[1][axis] = hi[axis]-.5
        supported = []
        for x, y in xy:
            cap = heights(triangles, x, y)
            if not len(cap): continue
            top = float(cap.min())
            below = heights(all_triangles, x, y); below = below[below < top-.03]
            base = max(ground(x, y), float(below.max()) if len(below) else -math.inf)
            if top-base < .08: continue
            # Keep the existing outer-deck riding lane open. Short cantilever
            # brackets carry the last raised ramp pieces from either side.
            anchor_x = x
            if 1247.8 < x < 1252.2 and 570 < y < 606:
                anchor_x = 1247.4 if x < 1250 else 1252.6
            anchor_top = top+.005
            if anchor_x != x:
                anchor_cap = heights(triangles, anchor_x, y)
                anchor_top = min(top, float(anchor_cap.min()) if len(anchor_cap) else top)-.12
                lower = heights(all_triangles, anchor_x, y); lower = lower[lower < anchor_top-.03]
                base = max(ground(anchor_x, y), float(lower.max()) if len(lower) else -math.inf)
            foot = post(anchor_x, y, anchor_top, base=base-.025, width=.12 if slender else .26)
            if anchor_x != x:
                steel.beam([anchor_x, y, anchor_top], [x, y, top-.10], .22)
                steel.beam([x, y, top-.10], [x, y, top+.005], .18)
            contact = {'nodes': [part[0] for part in group], 'bottom': foot, 'top': [float(x), float(y), top]}
            contacts.append(contact); supported.append(contact)
        for a, b in zip(supported, supported[1:]):
            frame = float(lo[2]-.22)
            if max(a['bottom'][2], b['bottom'][2])+.3 < frame:
                aa, bb = np.array(a['bottom']), np.array(b['bottom'])
                aa[2] = bb[2] = frame
                steel.beam(aa, bb, .20)
                steel.beam(np.array(a['bottom'])+[0, 0, .25], bb-[0, 0, .15], .12)

    def rail(a, b, height=1.1):
        a, b = np.array(a, float), np.array(b, float)
        count = max(1, math.ceil(np.linalg.norm(b-a)/1.8))
        for t in np.linspace(0, 1, count+1):
            p = a+t*(b-a); steel.beam(p, p+[0, 0, height], .06)
        steel.beam(a+[0, 0, height], b+[0, 0, height], .07)
        steel.beam(a+[0, 0, height*.5], b+[0, 0, height*.5], .045)

    def landing(east, z, entrance=False, bridge_exit=False):
        x0, x1 = (1310.1, 1312.4) if east else (1301.5, 1303.8)
        timber.box([(x0+x1)/2, 602.1, z-.12], [x1-x0, 6., .24])
        for y in (599.1, 605.1):
            steel.beam([x0, y, z-.27], [x1, y, z-.27], .2)
            rail([x0, y, z], [x1, y, z])
        outside = x1 if east else x0
        steel.beam([outside, 599.1, z-.27], [outside, 605.1, z-.27], .2)
        if bridge_exit:
            # The 2.2 m bridge continues west through the top landing's wall.
            rail([outside, 599.1, z], [outside, 599.2, z])
            rail([outside, 601.4, z], [outside, 605.1, z])
        else:
            rail([outside, 599.1, z], [outside, 602.7 if entrance else 605.1, z])

    # Four continuous posts carry the service tower; braces repeat at every landing.
    tower = [(1301.65, 599.25), (1301.65, 604.95), (1312.25, 599.25), (1312.25, 604.95)]
    for x, y in tower: post(x, y, TOP-.15, width=.32)
    rise = (TOP-DECK)/FLIGHTS; landing(False, DECK, entrance=True)
    for flight in range(FLIGHTS):
        east = flight % 2 == 0; x = 1303.8 if east else 1310.1; y = 600.3 if east else 603.9
        direction = 1 if east else -1; z = DECK+flight*rise
        for step in range(STEPS):
            top = z+(step+1)*rise/STEPS
            timber.box([x+direction*(step+.5)*RUN/STEPS, y, top-.11], [RUN/STEPS+.005, WIDTH, .22])
        for side in (-1, 1):
            a = [x, y+side*(WIDTH/2-.10), z-.20]
            b = [x+direction*RUN, a[1], z+rise-.20]
            steel.beam(a, b, .20, .30)
            rail([x, y+side*WIDTH/2, z], [b[0], y+side*WIDTH/2, z+rise])
        landing(east, z+rise, bridge_exit=flight == FLIGHTS-1)
        for a, b in ((tower[0], tower[1]), (tower[2], tower[3])):
            if flight == 0 and a == tower[0]:
                continue  # The lowest west bay is the service doorway.
            steel.beam([*a, z-.25], [*b, z+rise-.25], .14)

    # The top bridge runs behind the original ramp, then meets its 85.586 m ridge.
    bridge = stair_route()[-4:]
    for corner in bridge[1:-1]:
        timber.box(corner-[0, 0, .12], [2.2, 2.2, .24])
    for a, b in zip(bridge, bridge[1:]):
        direction = b[:2]-a[:2]
        if np.linalg.norm(direction) < .01: continue
        timber.beam(a-[0, 0, .12], b-[0, 0, .12], 2.2, .24)
        n = np.array([-direction[1], direction[0], 0.]); n /= np.linalg.norm(n)
        for side in (-1, 1):
            steel.beam(a+side*n*.95-[0, 0, .28], b+side*n*.95-[0, 0, .28], .2)
    for edge in bridge_edges(bridge, 1.1):
        for a, b in zip(edge, edge[1:]): rail(a, b)
    # A usable top landing touches the source ridge; its west edge is open for drop-in.
    timber.box([1293.55, 592.22, TOP-.12], [2.2, 3.4, .24])
    for x in (1292.5, 1294.6): post(x, 600.3, TOP-.28, width=.32)
    post(1294.55, 590.6, TOP-.28, width=.32); post(1294.55, 593.8, TOP-.28, width=.32)
    rail([1294.65, 590.52, TOP], [1294.65, 593.92, TOP])
    rail([1292.45, 590.52, TOP], [1294.65, 590.52, TOP])

    metadata = {'inspiration': 'gpt-image-2.5-sunburst, quality high; forest-structure concept',
                'support_contacts': contacts, 'flights': FLIGHTS, 'steps_per_flight': STEPS,
                'step_rise_m': rise/STEPS, 'tread_run_m': RUN/STEPS, 'stair_width_m': WIDTH,
                'route_world_m': stair_route().tolist(), 'base_m': DECK, 'top_m': TOP}
    return [steel, timber], metadata
