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
    members: list = field(default_factory=list)

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
        self.members.append({'a': a.tolist(), 'b': b.tolist(), 'width': width,
                             'depth': depth or width, 'first_face': len(self.faces)})
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

    # Main frame footings belong outside the recovered skating footprint.
    # Bounding boxes are intentionally conservative, including vertical walls.
    bounds = [(L.place(p['vertices'][p['faces']]).min((0, 1))[:2],
               L.place(p['vertices'][p['faces']]).max((0, 1))[:2]) for p in source.parts]
    lo = np.min([a for a, b in bounds], axis=0)-8
    hi = np.max([b for a, b in bounds], axis=0)+8
    gx, gy = np.meshgrid(np.arange(lo[0], hi[0]+.5, .5), np.arange(lo[1], hi[1]+.5, .5))
    safe = np.ones(gx.shape, bool)
    for a, b in bounds:
        safe &= ~((gx >= a[0]-.7) & (gx <= b[0]+.7) & (gy >= a[1]-.7) & (gy <= b[1]+.7))
    candidates = np.column_stack((gx[safe], gy[safe]))
    distance, unused = L.access_nearest(candidates[:, 0], candidates[:, 1])
    candidates = candidates[distance > L.WIDTH/2+.7]
    for a, b in zip(stair_route(), stair_route()[1:]):
        d = b[:2]-a[:2]; length = np.dot(d, d)
        if length < 1e-8: continue
        t = np.clip((candidates-a[:2])@d/length, 0, 1)
        candidates = candidates[np.linalg.norm(candidates-a[:2]-t[:, None]*d, axis=1) > 2.]
    frame_footings = {}; closed_edge_footings = []; ride_members = []; feature_legs = []

    def outside_anchor(point, previous=None):
        pool = candidates if previous is None else candidates[np.linalg.norm(candidates-previous, axis=1) >= 4.]
        return pool[int(np.argmin(np.linalg.norm(pool-point[:2], axis=1)))].copy()

    def reserve_frame(anchor, top):
        key = tuple(anchor)
        base = ground(*anchor)-.025
        item = frame_footings.setdefault(key, {'bottom': [*map(float, anchor), base], 'top_m': top})
        item['top_m'] = max(item['top_m'], float(top))
        return item['bottom']

    def bearing(point, triangles):
        cap = heights(triangles, *point[:2])
        thin = len(cap) and cap.max()-cap.min() < .25
        # A narrow contact fits curved undersides and the 30 cm source walls.
        # Thin lips need a short bracket joining their rib from below.
        steel.beam(point+[0, 0, -.09 if thin else .015], point+[0, 0, .005 if thin else .08], .04)

    def rib(a, b, triangles, pipe_floor=None):
        # Thick slabs contain the rib; thin ramp lips need it beneath the
        # original surface. Never connect across a source height discontinuity.
        count = max(1, math.ceil(np.linalg.norm((b-a)[:2])/.25))
        points = np.linspace(a, b, count+1)
        valid = []
        for point in points:
            cap = heights(triangles, *point[:2])
            if pipe_floor is not None:
                usable = len(cap) and float(cap.min()) <= pipe_floor+.6
                valid.append(bool(usable))
                if usable: point[2] = float(cap.min())+.15
                continue
            valid.append(True)
            if len(cap):
                point[2] = float(cap.min())+(.15 if cap.max()-cap.min() >= .25 else -.10)
            else:
                point[2] -= .10  # A gap rib stays below neighbouring floor edges.
        for i, (aa, bb) in enumerate(zip(points, points[1:])):
            if valid[i] and valid[i+1] and abs(bb[2]-aa[2]) < .35:
                steel.beam(aa, bb, .10, .12)

    for group in raised_groups(source):
        triangles = np.concatenate([part[1] for part in group])
        slender = all(part[4] in (17, 18, 21) for part in group)
        p = triangles.reshape(-1, 3); lo, hi = p.min(0), p.max(0)
        xs = np.linspace(lo[0]+.22, hi[0]-.22, max(2, math.ceil((hi[0]-lo[0])/4)+1))
        ys = np.linspace(lo[1]+.22, hi[1]-.22, max(2, math.ceil((hi[1]-lo[1])/4)+1))
        xy = [[x, y] for x in xs for y in (ys[0], ys[-1])]
        xy += [[x, y] for y in ys[1:-1] for x in (xs[0], xs[-1])]
        if slender:
            axis = int(np.argmax(hi[:2]-lo[:2])); centre = (lo[:2]+hi[:2])/2
            xy = [centre.copy(), centre.copy()]
            xy[0][axis] = lo[axis]+.5; xy[1][axis] = hi[axis]-.5
        points = []; bases = []
        for x, y in xy:
            cap = heights(triangles, x, y)
            if not len(cap): continue
            top = float(cap.min())
            below = heights(all_triangles, x, y); below = below[below < top-.03]
            base = max(ground(x, y), float(below.max()) if len(below) else -math.inf)
            if top-base < .08: continue
            points.append([float(x), float(y), top]); bases.append(base)
        if not points: continue
        points = np.asarray(points); bases = np.asarray(bases)
        nodes = [part[0] for part in group]
        if slender:
            # Only the original grind features retain their normal short legs.
            for point, base in zip(points, bases):
                start = len(steel.members)
                foot = post(*point[:2], point[2]+.005, base=base-.025, width=.12)
                feature_legs.extend(range(start, len(steel.members)))
                contacts.append({'nodes': nodes, 'bottom': foot, 'top': point.tolist(), 'kind': 'feature_leg'})
            continue
        pipes = [part for part in group if part[4] in (24, 25)]
        pipe_floor = min(part[2][2] for part in pipes) if pipes else None
        if pipe_floor is not None:
            # A closed full pipe carries its own roof and attached skirts.
            # Bearings belong under its bottom, never inside its riding tube.
            keep = (points[:, 2] >= pipe_floor-.4) & (points[:, 2] <= pipe_floor+.6)
            points, bases = points[keep], bases[keep]
            assert len(points) >= 2, ('full pipe needs bottom bearings', nodes)
            pipe_floor = float(points[:, 2].min())
        start = len(steel.members)
        centre = points[:, :2].mean(0)
        order = np.argsort(np.arctan2(points[:, 1]-centre[1], points[:, 0]-centre[0]))
        for i, j in zip(order, np.roll(order, -1)): rib(points[i], points[j], triangles, pipe_floor)
        for point in points:
            bearing(point, triangles)
        # Low stepped pads can bear on their already closed low edge. Their
        # underside stringers carry the higher end without posts in the bowl.
        low = np.flatnonzero((points[:, 2]-bases < 1.7) & (points[:, 2] < DECK+1.95))
        if len(low) >= 2:
            first = int(low[0]); second = int(low[np.argmax(np.linalg.norm(points[low, :2]-points[first, :2], axis=1))])
            anchors = [points[first], points[second]]; feet = []
            for i in (first, second):
                feet.append(post(*points[i, :2], points[i, 2]+.005, base=bases[i]-.025, width=.4))
                closed_edge_footings.append({'bottom': feet[-1], 'top_m': float(points[i, 2]+.005)})
        else:
            # Two shared exterior piers carry a connected frame for this group.
            # The highest bearings keep the incoming girders above lower decks.
            highest = np.argsort(-points[:, 2]); first = int(highest[0])
            second = int(max(highest[:max(2, len(points)//2)], key=lambda i: np.linalg.norm(points[i, :2]-points[first, :2])))
            anchors = [outside_anchor(points[first])]
            anchors.append(outside_anchor(points[second], anchors[0]))
            if nodes == [267, 268]:
                # Approach this bowl-side platform from below the central pipe;
                # a northward girder would cut through the bowl's roll-in bank.
                anchors = [outside_anchor(np.array([1245., 573.5]))]
                anchors.append(outside_anchor(np.array([1245., 569.5]), anchors[0]))
            elif 576 in nodes:
                # The east-side quarter pipe has a riding lip at 52.6 m;
                # bringing this frame in from the west avoids that lip.
                anchors = [outside_anchor(np.array([1298.5, 542.5]))]
                anchors.append(outside_anchor(np.array([1298.5, 538.5]), anchors[0]))
            feet = []
            for anchor, index in zip(anchors, (first, second)):
                # This sloped group's northern girders pass beneath another
                # ramp skin; their top must stay below that original surface.
                inset = 0. if 477 in nodes else .10
                top = points[index, 2]+inset
                feet.append(reserve_frame(anchor, top))
                target = points[index]+[0, 0, inset]
                if nodes == [267, 268]:
                    west = np.array([anchor[0], 586.5, top])
                    inside = np.array([target[0], 586.5, top])
                    steel.beam([*anchor, top], west, .45, .18)
                    steel.beam(west, inside, .45, .18)
                    steel.beam(inside, target, .45, .18)
                elif 331 in nodes:
                    # Leave the original high drop-in on its outside edge.
                    turn = np.array([target[0], hi[1]+.8, top])
                    steel.beam([*anchor, top], turn, .45, .18)
                    steel.beam(turn, target, .45, .18)
                else:
                    if pipe_floor is not None and 576 not in nodes:
                        low = points[index]-[0, 0, .18]
                        d = anchor-target[:2]; length = np.linalg.norm(d); d /= length
                        turn = target.copy(); turn[:2] += d*min(2., max(.5, length-.2))
                        steel.beam([*anchor, top], turn, .45, .18)
                        steel.beam(turn, low, .45, .18)
                        steel.beam(low, points[index]+[0, 0, .015], .04)
                    else:
                        steel.beam([*anchor, top], target, .45, .18)
        for point in points:
            k = int(np.argmin([np.linalg.norm(point[:2]-np.asarray(foot[:2])) for foot in feet]))
            contacts.append({'nodes': nodes, 'bottom': feet[k], 'top': point.tolist(), 'kind': 'frame'})
        ride_members.extend(range(start, len(steel.members)))

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
    # The bridge uses one shared exterior pier, rather than four poles in bowls.
    anchor = outside_anchor(np.array([1293.55, 600.3, TOP]))
    reserve_frame(anchor, TOP-.28)
    start = len(steel.members)
    for x in (1292.45, 1294.65):
        steel.beam([*anchor, TOP-.28], [x, 600.3, TOP-.28], .4, .35)
        steel.beam([*anchor, TOP-2.5], [x, 600.3, TOP-.28], .22)
    ride_members.extend(range(start, len(steel.members)))
    for item in frame_footings.values():
        start = len(steel.members)
        foot = item['bottom']; post(*foot[:2], item['top_m'], base=foot[2], width=.55)
        ride_members.extend(range(start, len(steel.members)))
    rail([1294.65, 590.52, TOP], [1294.65, 593.92, TOP])
    rail([1292.45, 590.52, TOP], [1294.65, 590.52, TOP])

    metadata = {'inspiration': 'gpt-image-2.5-sunburst, quality high; forest-structure concept',
                'support_contacts': contacts, 'frame_footings': list(frame_footings.values()),
                'closed_edge_footings': closed_edge_footings,
                'ride_support_members': ride_members, 'feature_leg_members': feature_legs, 'flights': FLIGHTS, 'steps_per_flight': STEPS,
                'step_rise_m': rise/STEPS, 'tread_run_m': RUN/STEPS, 'stair_width_m': WIDTH,
                'route_world_m': stair_route().tolist(), 'base_m': DECK, 'top_m': TOP}
    return [steel, timber], metadata
