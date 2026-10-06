"""Braced steel trestle towers under the raised pieces and the connected timber service ascent.

The source scene stays rigid. New geometry is authored in island metres, then
converted to the same park-local frame as the imported ramps.
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
RIDGE = (1293.55, 592.22)  # the top landing on the source ridge, 3.4 m deep
# Source mesh indices (source.json pins them): the low and straight ledges and the flat rail keep their own short
# legs; the medium and small full pipes bear on their bottoms.
SLENDER = (17, 18, 21)
PIPES = (24, 25)


def beam_axes(d, width, depth):
    """Half-width and half-depth vectors across a member along d."""
    d = d/np.linalg.norm(d)
    seed = np.array([0., 0., 1.]) if abs(d[2]) < .9 else np.array([1., 0., 0.])
    u = np.cross(seed, d); u *= width/2/np.linalg.norm(u)
    v = np.cross(d, u); v *= depth/2/np.linalg.norm(v)
    return u, v


@dataclass
class Mesh:
    name: str
    material: str
    vertices: list = field(default_factory=list)
    faces: list = field(default_factory=list)
    uv: list = field(default_factory=list)
    members: list = field(default_factory=list)
    textured: bool = True

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
        u, v = beam_axes(d, width, depth or width)
        self.cuboid([p+s*u+t*v for p in (a, b) for s, t in [(-1, -1), (1, -1), (1, 1), (-1, 1)]])

    def cuboid(self, corners):
        """Six faces from eight corners: a quad at each end, in matching order."""
        corners = np.asarray(corners)
        for face in [(3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]:
            self.face(corners[list(face)])

    def quad(self, points, uv):
        """One face with its own texture coordinates (glTF convention: v grows down the image)."""
        start = len(self.vertices); self.vertices.extend(np.asarray(points, float).tolist())
        self.uv.extend([list(c) for c in uv]); self.faces.append(list(range(start, start+len(points))))

    def box(self, centre, size):
        c = np.asarray(centre, float); self.beam(c-[0, 0, size[2]/2], c+[0, 0, size[2]/2], size[1], size[0])

    def triangle_faces(self):
        return [[f[0], f[k], f[k+1]] for f in self.faces for k in range(1, len(f)-1)]

    def triangles(self):
        return np.asarray(self.vertices)[self.triangle_faces()]


def heights(triangles, x, y, flat=1e-9, edge=1e-7):
    """Vertical intersections, including underside faces; vertical walls have no area."""
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    den = (b[:, 1]-c[:, 1])*(a[:, 0]-c[:, 0])+(c[:, 0]-b[:, 0])*(a[:, 1]-c[:, 1])
    valid = abs(den) > flat; den = np.where(valid, den, np.inf)
    u = ((b[:, 1]-c[:, 1])*(x-c[:, 0])+(c[:, 0]-b[:, 0])*(y-c[:, 1]))/den
    v = ((c[:, 1]-a[:, 1])*(x-c[:, 0])+(a[:, 0]-c[:, 0])*(y-c[:, 1]))/den
    hit = valid & (u >= -edge) & (v >= -edge) & (u+v <= 1+edge)
    return (u*a[:, 2]+v*b[:, 2]+(1-u-v)*c[:, 2])[hit]


def footprints(source):
    """Each source piece's placed plan bounds (lo, hi): conservative, vertical walls included."""
    return [(t.min((0, 1))[:2], t.max((0, 1))[:2]) for t in (L.place(p['vertices'][p['faces']]) for p in source.parts)]


def footprint_gap(points, bounds):
    """Each point's plan distance outside the nearest footprint box, per axis (0 inside one)."""
    points = np.atleast_2d(points); gap = np.full(len(points), np.inf)
    for a, b in bounds:
        gap = np.minimum(gap, np.maximum(np.maximum(a-points, points-b), 0).max(1))
    return gap


def route_distance(points, route):
    """Each plan point's distance to a 3D route's plan polyline."""
    points = np.atleast_2d(points); distance = np.full(len(points), np.inf)
    for a, b in zip(route, route[1:]):
        d = b[:2]-a[:2]; length = d@d
        if length < 1e-8: continue
        t = np.clip((points-a[:2])@d/length, 0, 1)
        distance = np.minimum(distance, np.linalg.norm(points-a[:2]-t[:, None]*d, axis=1))
    return distance


def _point_segment(p, a, b):
    ab = b-a; t = np.clip(np.einsum('...i,...i', p-a, ab)/np.maximum(np.einsum('...i,...i', ab, ab), 1e-12), 0, 1)
    return np.linalg.norm(p-(a+t[..., None]*ab), axis=-1)


def _clip(polygon, axis, value, keep_above):
    out = []
    for p, q in zip(polygon, np.roll(polygon, -1, 0)):
        p_in, q_in = (p[axis] >= value) == keep_above, (q[axis] >= value) == keep_above
        if p_in: out.append(p)
        if p_in != q_in: out.append(p+(q-p)*(value-p[axis])/(q[axis]-p[axis]))
    return np.asarray(out).reshape(-1, 3)


def _plan_distance(polygon, a, b):
    """Plan distance between a segment and a convex polygon (zero when they overlap)."""
    edges = list(zip(polygon[:, :2], np.roll(polygon[:, :2], -1, 0)))
    def side(p, q, r): return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    for p, q in edges:
        if side(a, b, p)*side(a, b, q) < 0 and side(p, q, a)*side(p, q, b) < 0: return 0.
    signs = [side(p, q, a) for p, q in edges]
    if len(polygon) > 2 and (min(signs) >= 0 or max(signs) <= 0) and abs(sum(side(polygon[0, :2], p, q) for p, q in edges)) > 1e-12:
        return 0.
    return float(min([_point_segment(a, p, q) for p, q in edges]+[_point_segment(b, p, q) for p, q in edges]
                     + [_point_segment(p, a, b) for p, q in edges]))


def _overlap(p, q):
    """Area shared by two convex plane polygons (2D, either winding)."""
    def cross(a, b): return a[..., 0]*b[..., 1]-a[..., 1]*b[..., 0]
    def ccw(r): return r if cross(r[1]-r[0], r[2]-r[0]) > 0 else r[::-1]
    out, q = ccw(p), ccw(q)
    for a, b in zip(q, np.roll(q, -1, 0)):
        side = cross(b-a, out-a); inside = side >= -1e-12; kept = []
        for i in range(len(out)):
            s, e = out[i-1], out[i]
            if inside[i] != inside[i-1]: kept.append(s+(e-s)*side[i-1]/(side[i-1]-side[i]))
            if inside[i]: kept.append(e)
        if len(kept) < 3: return 0.
        out = np.asarray(kept)
    x, y = out[:, 0], out[:, 1]
    return float(abs(x@np.roll(y, -1)-y@np.roll(x, -1))/2)


def flicker(meshes, area=1e-4):
    """Overlapping coplanar faces that face the same way but shade differently, so the depth test flickers.

    Two faces of one material render the same pixels when it is untextured or their texture frames agree.
    Returns (area m², centre, material, material) for each conflicting pair."""
    planes = {}
    for mesh in meshes:
        points = np.asarray(mesh.vertices)
        for face in mesh.faces:
            p = points[face]; n = np.cross(p[1]-p[0], p[2]-p[0]); n /= np.linalg.norm(n)
            u = (p[1]-p[0])/np.linalg.norm(p[1]-p[0])
            planes.setdefault((*np.round(n, 3)+0., round(float(n@p[0]), 3)+0.), []).append((mesh, p, u, n))
    found = []
    for faces in planes.values():
        if len(faces) < 2: continue
        n = faces[0][3]; e1 = np.cross(n, [0., 0., 1.] if abs(n[2]) < .9 else [1., 0., 0.]); e1 /= np.linalg.norm(e1)
        e2 = np.cross(n, e1); flat = [p@np.column_stack((e1, e2)) for _, p, _, _ in faces]
        for i, (mesh, p, u, _) in enumerate(faces):
            for j in range(i+1, len(faces)):
                other = faces[j][0]
                if mesh.material == other.material and (not mesh.textured or np.allclose(u, faces[j][2], atol=1e-6)):
                    continue
                shared = _overlap(flat[i], flat[j])
                if shared > area: found.append((shared, p.mean(0).round(2).tolist(), mesh.material, other.material))
    return found


def body_intrusions(triangles, route, radius=.25, low=.4, high=1.95):
    """Triangles reaching into the walking body swept along each route segment, measured exactly in plan.

    Point probes can step over a 6 cm post; this clips every nearby triangle to the body's height band and
    measures its plan footprint against the segment. The 22 cm character capsule gets 3 cm margin.
    Returns (segment, triangle) pairs."""
    route = np.asarray(route, float); lo, hi = triangles[:, :, 2].min(1), triangles[:, :, 2].max(1)
    found = []
    for index, (a, b) in enumerate(zip(route, route[1:])):
        bottom, top = min(a[2], b[2])+low, max(a[2], b[2])+high
        mask = (hi > bottom) & (lo < top)
        mask &= np.all(triangles[:, :, :2].min(1) < np.maximum(a[:2], b[:2])+radius, 1)
        mask &= np.all(triangles[:, :, :2].max(1) > np.minimum(a[:2], b[:2])-radius, 1)
        for k in np.flatnonzero(mask):
            band = _clip(_clip(triangles[k], 2, bottom, True), 2, top, False)
            if len(band) and _plan_distance(band, a[:2], b[:2]) < radius:
                found.append((index, int(k)))
    return found


def flights():
    """Each switchback flight: whether it climbs east, its foot (x, y, z) and its direction along x."""
    rise = (TOP-DECK)/FLIGHTS
    for flight in range(FLIGHTS):
        east = flight % 2 == 0
        yield east, 1303.8 if east else 1310.1, 600.3 if east else 603.9, DECK+flight*rise, 1 if east else -1


def stair_route():
    """Centreline waypoints through every flight and landing, ending at the original top ridge."""
    route = [[1300.25, 603.9, DECK], [1302.65, 603.9, DECK],
             [1302.65, 600.3, DECK], [1303.75, 600.3, DECK]]
    rise = (TOP-DECK)/FLIGHTS
    for flight, (east, x, y, z, direction) in enumerate(flights()):
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
            if (a[4] in SLENDER) == (b[4] in SLENDER) and np.maximum(a[2]-b[3], b[2]-a[3]).max() < .55:
                parent[root(i)] = root(j)
    groups = {}
    for i, part in enumerate(parts): groups.setdefault(root(i), []).append(part)
    return list(groups.values())


def build(base_sampler):
    steel = Mesh('SM_CP_StructureSteel', 'CP_StructureSteel', textured=False)  # a flat indigo
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
    bounds = footprints(source); route = stair_route()
    lo = np.min([a for a, b in bounds], axis=0)-8
    hi = np.max([b for a, b in bounds], axis=0)+8
    gx, gy = np.meshgrid(np.arange(lo[0], hi[0]+.5, .5), np.arange(lo[1], hi[1]+.5, .5))

    def clear(points):
        # Footings and tower legs keep off the pieces, the access path and the stair route.
        points = np.atleast_2d(points); keep = footprint_gap(points, bounds) > .7
        distance, unused = L.access_nearest(points[:, 0], points[:, 1])
        return keep & (distance > L.WIDTH/2+.7) & (route_distance(points, route) > 2.)
    candidates = np.column_stack((gx.ravel(), gy.ravel()))
    candidates = candidates[clear(candidates)]
    corners = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]], float)
    frame_footings = {}; closed_edge_footings = []; ride_members = []

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

    def girder(a, b):
        # A girder leaving its tower is trussed below: the lower chord starts
        # down the tower and tapers to the far end, with a triangulated web.
        a, b = np.asarray(a, float), np.asarray(b, float)
        steel.beam(a, b, .45, .18)
        length = float(np.linalg.norm((b-a)[:2]))
        if length < 2.: return
        count = max(2, math.ceil(length/1.6))
        t = np.linspace(0, 1, count+1)
        upper = a+t[:, None]*(b-a)-[0, 0, .09]
        # Keep the lower chord 3.1 m above any surface below it; the tapered
        # tip is the girder's own depth. Skip the truss when nothing fits.
        def fits(depth):
            for u in np.linspace(0, .85, max(4, math.ceil(length/.25))):
                point = a+u*(b-a)-[0, 0, .09+depth*(1-u)+.08]
                for dx, dy in [(0, 0), (.35, 0), (-.35, 0), (0, .35), (0, -.35)]:
                    hits = heights(all_triangles, point[0]+dx, point[1]+dy); hits = hits[hits < point[2]]
                    if len(hits) and point[2]-hits.max() < 3.1: return False
            return True
        depth = next((d for d in (min(1.5, .3*length), 1.1, .7) if fits(d)), None)
        if depth is None: return
        lower = upper-np.outer(1-t, [0, 0, depth])
        steel.beam(lower[0], lower[-1], .2, .15)
        for i in range(count):
            if i: steel.beam(upper[i], lower[i], .08)
            steel.beam(upper[i+1] if i % 2 else upper[i], lower[i] if i % 2 else lower[i+1], .08)

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
        slender = all(part[4] in SLENDER for part in group)
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
                foot = post(*point[:2], point[2]+.005, base=base-.025, width=.12)
                contacts.append({'nodes': nodes, 'bottom': foot, 'top': point.tolist(), 'kind': 'feature_leg'})
            continue
        pipes = [part for part in group if part[4] in PIPES]
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
            # Girders from two exterior anchors, each on a tower below, carry this group.
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
                    girder([*anchor, top], west)
                    steel.beam(west, inside, .45, .18)
                    steel.beam(inside, target, .45, .18)
                elif 331 in nodes:
                    # Leave the original high drop-in on its outside edge.
                    turn = np.array([target[0], hi[1]+.8, top])
                    girder([*anchor, top], turn)
                    steel.beam(turn, target, .45, .18)
                else:
                    if pipe_floor is not None and 576 not in nodes:
                        low = points[index]-[0, 0, .18]
                        d = anchor-target[:2]; length = np.linalg.norm(d); d /= length
                        turn = target.copy(); turn[:2] += d*min(2., max(.5, length-.2))
                        girder([*anchor, top], turn)
                        steel.beam(turn, low, .45, .18)
                        steel.beam(low, points[index]+[0, 0, .015], .04)
                    else:
                        girder([*anchor, top], target)
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
        # Edge beams run 10 cm past the deck so their end caps never share its side faces.
        for y in (599.1, 605.1):
            steel.beam([x0-.1, y, z-.27], [x1+.1, y, z-.27], .2)
            rail([x0, y, z], [x1, y, z])
        outside = x1 if east else x0
        steel.beam([outside, 599.0, z-.27], [outside, 605.2, z-.27], .2)
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
    for flight, (east, x, y, z, direction) in enumerate(flights()):
        for step in range(STEPS):
            top = z+(step+1)*rise/STEPS
            timber.box([x+direction*(step+.5)*RUN/STEPS, y, top-.11], [RUN/STEPS+.005, WIDTH, .22])
        for side in (-1, 1):
            # Stringers stand 2 cm proud of the tread ends: a shared face z-fights wood through the steel.
            a = [x, y+side*(WIDTH/2-.08), z-.20]
            b = [x+direction*RUN, a[1], z+rise-.20]
            steel.beam(a, b, .20, .30)
            rail([x, y+side*WIDTH/2, z], [b[0], y+side*WIDTH/2, z+rise])
        landing(east, z+rise, bridge_exit=flight == FLIGHTS-1)
        for a, b in ((tower[0], tower[1]), (tower[2], tower[3])):
            if flight == 0 and a == tower[0]:
                continue  # The lowest west bay is the service doorway.
            steel.beam([*a, z-.25], [*b, z+rise-.25], .14)

    # The top bridge runs behind the original ramp, then meets its 85.586 m ridge.
    bridge = route[-4:]
    # Its decking abuts the top landing, the corner and the ridge landing rather than overlapping them:
    # coplanar treads with crossing grain flicker.
    corner = bridge[2]-[0, 0, .12]
    timber.box(corner, [2.2, 2.2, .24])
    timber.beam([1301.5, corner[1], corner[2]], corner+[1.1, 0, 0], 2.2, .24)
    timber.beam(corner-[0, 1.1, 0], [corner[0], RIDGE[1]+1.7, corner[2]], 2.2, .24)
    for a, b in zip(bridge, bridge[1:]):
        direction = b[:2]-a[:2]
        if np.linalg.norm(direction) < .01: continue
        n = np.array([-direction[1], direction[0], 0.]); n /= np.linalg.norm(n)
        for side in (-1, 1):
            steel.beam(a+side*n*.95-[0, 0, .28], b+side*n*.95-[0, 0, .28], .2)
    east_edge, west_edge = bridge_edges(bridge, 1.1)
    # The top flight arrives across the landing's east side; rail only the stairwell drop south of it.
    east_edge[0, 1] = bridge[0, 1]-WIDTH/2
    for edge in (east_edge, west_edge):
        for a, b in zip(edge, edge[1:]): rail(a, b)
    # A usable top landing touches the source ridge; its west edge is open for drop-in.
    timber.box([*RIDGE, TOP-.12], [2.2, 3.4, .24])
    # The bridge rests on one exterior tower, rather than four poles in bowls.
    anchor = outside_anchor(np.array([1293.55, 600.3, TOP]))
    reserve_frame(anchor, TOP-.28)
    start = len(steel.members)
    for x in (1292.45, 1294.65):
        steel.beam([*anchor, TOP-.28], [x, 600.3, TOP-.28], .4, .35)
        steel.beam([*anchor, TOP-2.5], [x, 600.3, TOP-.28], .22)
    ride_members.extend(range(start, len(steel.members)))
    # Each footing becomes a braced four-legged trestle tower, never a lone pole.
    # A girder keeps its audited anchor, which rests on the tower's headstock;
    # the tower stands outward from it, sized to the free ground there.
    towers = []
    for item in sorted(frame_footings.values(), key=lambda item: -item['top_m']):
        anchor = np.asarray(item['bottom'][:2])
        home = next((t for t in towers if np.all(abs(anchor-t['centre']) <= t['half']+.6)), None)
        if home is None:
            best = None
            for half in [np.array([hx, hy]) for hx in (.9, .75, .6, .45, .25) for hy in (.9, .75, .6, .45, .25)]:
                if best is not None and np.prod(half) <= np.prod(best[1]): continue
                offsets = np.stack(np.meshgrid(*[np.linspace(-h, h, 7) for h in half]), -1).reshape(-1, 2)
                offsets = offsets[np.argsort(np.linalg.norm(offsets, axis=1))]
                fits = np.all([clear(anchor+offsets+c*half) for c in corners], axis=0)
                if fits.any(): best = (anchor+offsets[int(np.argmax(fits))], half)
            assert best is not None, ('no room for a support tower', item)
            home = {'centre': best[0], 'half': best[1], 'top': item['top_m'], 'heads': []}
            towers.append(home)
        home['heads'].append((anchor, item['top_m']))
        item['legs'] = [[*map(float, home['centre']+c*home['half']), ground(*(home['centre']+c*home['half']))-.025]
                        for c in corners]
    for tower in towers:
        start = len(steel.members)
        legs = frame_footings[tuple(tower['heads'][0][0])]['legs']; top = tower['top']-.09
        for leg in legs:
            post(*leg[:2], top, base=leg[2], width=.2)
        base = max(leg[2] for leg in legs)+.35
        bays = max(1, math.ceil((top-base)/2.6))
        levels = np.linspace(base, top, bays+1)
        for k, z in enumerate(levels):
            ring = [np.array([*leg[:2], z]) for leg in legs]
            for a, b in zip(ring, ring[1:]+ring[:1]): steel.beam(a, b, *((.3, .18) if k == bays else (.12, .12)))
        for z0, z1 in zip(levels, levels[1:]):
            for a, b in zip(legs, legs[1:]+legs[:1]):
                steel.beam([*a[:2], z0], [*b[:2], z1], .07)
                steel.beam([*b[:2], z0], [*a[:2], z1], .07)
        (x0, y0), (x1, y1) = tower['centre']-tower['half'], tower['centre']+tower['half']
        for anchor, head in tower['heads']:
            # A nearby anchor just beyond the frame gets a short bracket.
            inside = np.clip(anchor, [x0, y0], [x1, y1])
            if x1-x0 >= y1-y0: steel.beam([x0, inside[1], head-.09], [x1, inside[1], head-.09], .3, .18)
            else: steel.beam([inside[0], y0, head-.09], [inside[0], y1, head-.09], .3, .18)
            if np.linalg.norm(anchor-inside) > .01: steel.beam([*inside, head-.09], [*anchor, head-.09], .3, .18)
        ride_members.extend(range(start, len(steel.members)))
    rail([1294.65, 590.52, TOP], [1294.65, 593.92, TOP])
    rail([1292.45, 590.52, TOP], [1294.65, 590.52, TOP])

    metadata = {'support_contacts': contacts, 'frame_footings': list(frame_footings.values()),
                'closed_edge_footings': closed_edge_footings, 'ride_support_members': ride_members,
                'step_rise_m': rise/STEPS, 'tread_run_m': RUN/STEPS, 'stair_width_m': WIDTH,
                'route_world_m': route.tolist(), 'top_m': TOP}
    return [steel, timber], metadata
