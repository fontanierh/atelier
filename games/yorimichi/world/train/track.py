"""Belmonte railway track: the layout and every mesh as plain arrays, from the route study's route.json.

No Blender here: track_build.py turns these meshes into GLBs (`atelier build yorimichi world.belmonte_track`) and
track.json into the placements Unreal reads; the tests check the layout and the triangle budgets without Blender.
Design and budgets: games/yorimichi/docs/BELMONTE_TRACK.md.

Frame: route.json's, metres, x east, y north, z up. Every mesh is built relative to its own origin (track.json gives
the origin, or the instances' transforms); chunk meshes are bent along the line, so they need no rotation.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1])); import yori  # noqa: E402,F401
import json
import math
from dataclasses import dataclass, field

import numpy as np

from train import route as R

ROUTE = yori.OUT / 'belmonte-train' / 'route' / 'route.json'
OUT = yori.OUT / 'belmonte-track'

GAUGE = 1.435
RAIL_HEIGHT = .15
CHUNK = 100.                # metres of line per ballast-and-rail mesh
SLICES = (4., 10., 25.)     # sweep spacing per LOD
SLEEPER = (2.6, .25, .15)   # length across the track, width along it, depth
SLEEPER_SPACING = .63
BALLAST_TOP = -.20          # below the rail top: the sleepers stand 5 cm proud of the ballast
BALLAST_HALF = 1.7          # half width of the ballast top
BALLAST_TOE = (2.45, -.70)  # shoulder toe, 1:1.5 slope
SKIRT = (2.6, -1.5)         # a steep skirt that hides small gaps to the ground
BUFFER_OFFSET = 1.          # buffer stops this far from each end of the line
STOP_OFFSET = R.STOP_CLEARANCE              # the stopping point: where the run model's head stops
TUNNEL_HALF = 2.6           # horseshoe lining: half width, wall height and the crown's radius above the rail
TUNNEL_WALL = 3.2
TUNNEL_BASE = -.7
TUNNEL_LOAD = 60.           # a tunnel's data layer loads within this distance of either portal
LINING_SLICES = (5., 10.)
LAMP_SPACING = 30.          # wall lamps along a tunnel, alternating sides, the first and last LAMP_SPACING / 2 in
LAMP_HEIGHT = 3.0           # the lamp's bracket on the wall, over the rail top (the wall stands TUNNEL_WALL)
LAMP_REACH = .32            # the globe's centre out from the wall
LIGHT = dict(colour_k=2700, intensity_cd=80., attenuation_m=14., source_radius_m=.08, cast_shadows=False)
VOLUME_HALF = (3.6, 4.2)    # a tunnel volume's half width beyond the line's own bend, and half height
SPAN = 20.                  # viaduct span between pier centres
PIER = 2.5                  # pier thickness along the line
DECK_WIDTH = 5.4
DECK_DEPTH = .7             # deck top under the rail top
CROWN = 1.0                 # stone over the arch's crown
PARAPET = (.4, 1.0)
VIADUCT_PIECE = 100.
ARCH_SEGMENTS = (12, 6, 3)
MARKER_EVERY = 50.
MATERIALS = {               # Blender colour stand-ins; the names are the Unreal material instances the import binds
    'MI_B_gravel': (.36, .34, .31, .95),
    'MI_B_iron': (.16, .15, .14, .45),
    'MI_B_wood': (.20, .14, .09, .85),
    'MI_B_ashlar': (.66, .58, .46, .85),
    'MI_B_stone': (.52, .48, .42, .9),
    'MI_TK_Signal': (.72, .08, .05, .6),
    'MI_TK_Marker': (.95, .45, .05, .6),
    'MI_TK_TunnelLining': (.075, .07, .065, .95),   # soot-blackened stone: the tunnel stays dark between its lamps
    'MI_TK_LampGlow': (1., .72, .38, .3),            # emissive in Unreal (track_build.py lights it in Blender)
    'MI_TK_Bank': (.10, .14, .045, .95),             # the grass of a bank built over ground that is not carved
    # the Belmonte station (station.py)
    'MI_B_flag': (.55, .40, .25, .9),
    'MI_B_cobble': (.55, .38, .22, .9),
    'MI_B_plaster': (.72, .42, .17, .9),
    'MI_B_roof': (.62, .25, .12, .85),
    'MI_B_glass_dark': (.03, .03, .025, .3),
    'MI_ST_Green': (.045, .11, .075, .5),            # painted ironwork
    'MI_ST_Glass': (.20, .26, .30, .25),             # roof glazing, seen from outside and afar
    'MI_ST_Clock': (.86, .81, .67, .6),              # clock dials and lamp globes
    'MI_ST_Coach': (.28, .11, .055, .55),            # the old coaches' varnished teak
    'MI_ST_CoachRoof': (.22, .22, .21, .8),
}
BUDGETS = {                 # triangles per LOD (BELMONTE_TRACK.md)
    'SM_TK_Chunk': (1200, 400, 120),
    'SM_TK_Loop': (2000, 400, 120),           # the loop's own rails, 260 m in one mesh
    'SM_TK_Tunnel': (600, 200),
    'SM_TK_Portal': (2000, 600),
    'SM_TK_Viaduct': (25000, 6000, 2500),     # all pieces together (LOD2, the collision: about 2.5 per metre)
    'SM_TK_Turnout': (3000,),
    'SM_TK_BufferStop': (800,),
    'SM_TK_Sleeper': (12,),
    'SM_TK_TunnelLamp': (120,),
    'SM_TK_Bank': (6000, 1500),                # per 100 m piece
    'SM_ST_Overbridge': (6000, 1500, 800),     # the road over the Belmonte cutting (overbridge.py; LOD2 its collision)
    'SM_ST_Headhouse': (14500, 4200, 1200),    # the Belmonte station (station.py), one mesh each; LOD2 the collision
    'SM_ST_Sheds': (34000, 6000, 2400),
    'SM_ST_Coaches': (2000, 300, 60),
    'SM_ST_Forecourt': (220, 80, 40),
}


# --- meshes ------------------------------------------------------------------------------------------------------


@dataclass
class Mesh:
    """Vertices, polygons (vertex index tuples, any size, counter-clockwise seen from outside) and a material name per
    polygon."""
    verts: list = field(default_factory=list)
    faces: list = field(default_factory=list)
    mats: list = field(default_factory=list)

    def add(self, verts, faces, mat):
        base = len(self.verts)
        self.verts.extend(tuple(float(c) for c in v) for v in verts)
        self.faces.extend(tuple(base + i for i in f) for f in faces)
        self.mats.extend([mat] * len(faces))
        return self

    def extend(self, other):
        base = len(self.verts)
        self.verts.extend(other.verts)
        self.faces.extend(tuple(base + i for i in f) for f in other.faces)
        self.mats.extend(other.mats)
        return self

    @property
    def triangles(self):
        return sum(len(f) - 2 for f in self.faces)

    def bounds(self):
        v = np.asarray(self.verts)
        return v.min(0), v.max(0)


def grid_faces(rows, cols, closed=False):
    """Quads of a rows x cols vertex grid (row-major), optionally closing each row into a ring."""
    faces = []
    for i in range(rows - 1):
        for j in range(cols if closed else cols - 1):
            k = (j + 1) % cols
            faces.append((i * cols + j, (i + 1) * cols + j, (i + 1) * cols + k, i * cols + k))
    return faces


def box(mesh, centre, size, mat, yaw=0., bottom=True):
    """An axis-aligned (then yawed about z) box; `bottom=False` leaves the underside open."""
    cx, cy, cz = centre
    hx, hy, hz = (s / 2 for s in size)
    c, s = math.cos(yaw), math.sin(yaw)
    corners = []
    for z in (-hz, hz):
        for x, y in ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)):
            corners.append((cx + c * x - s * y, cy + s * x + c * y, cz + z))
    faces = [(4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    if bottom:
        faces.append((3, 2, 1, 0))
    return mesh.add(corners, faces, mat)


def cylinder(mesh, a, b, radius, mat, sides=8):
    """A capped cylinder from point a to b."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    axis = (b - a) / np.linalg.norm(b - a)
    u = np.cross(axis, (0, 0, 1) if abs(axis[2]) < .9 else (1, 0, 0))
    u /= np.linalg.norm(u)
    v = np.cross(axis, u)
    ring = [radius * (math.cos(t) * u + math.sin(t) * v) for t in np.linspace(0, 2 * math.pi, sides, endpoint=False)]
    verts = [a + r for r in ring] + [b + r for r in ring]
    faces = [(j, (j + 1) % sides, sides + (j + 1) % sides, sides + j) for j in range(sides)]
    faces += [tuple(range(sides - 1, -1, -1)), tuple(range(sides, 2 * sides))]
    return mesh.add(verts, faces, mat)


def prism(mesh, outline, y0, y1, mat):
    """A polygon in the (x, z) plane, counter-clockwise with x right and z up, extruded from y0 to y1 (a closed
    solid, faces outward)."""
    n = len(outline)
    verts = [(x, y0, z) for x, z in outline] + [(x, y1, z) for x, z in outline]
    faces = [(j, n + j, n + (j + 1) % n, (j + 1) % n) for j in range(n)]
    faces += [tuple(range(n)), tuple(range(2 * n - 1, n - 1, -1))]
    return mesh.add(verts, faces, mat)


# --- the line ----------------------------------------------------------------------------------------------------


class Line:
    """The route's centreline with its rail heights: frames at any chainage."""

    def __init__(self, route=None):
        self.route = route if route is not None else json.loads(ROUTE.read_text())
        self.alignment = R.alignment()
        samples = self.route['samples']
        self.s = np.array([p['s'] for p in samples])
        self.rail = np.array([p['rail_z'] for p in samples])
        self.ground = np.array([p['ground_z'] for p in samples])
        self.kind = [p['class'] for p in samples]
        self.length = float(self.s[-1])
        x, y, _, _ = self.alignment.at(self.s)
        self.mismatch = float(np.hypot(x - [p['x'] for p in samples], y - [p['y'] for p in samples]).max())
        if self.mismatch > .05 or abs(self.alignment.length - self.length) > .05:
            raise ValueError(f'route.py and route.json disagree by {self.mismatch:.2f} m: rerun world.belmonte_train_route')
        loop = self.route['passing_loop']
        self.loop = (loop['start'], loop['end'])
        mid = loop['second_track'][len(loop['second_track']) // 2]
        cx, cy, h, _ = self.alignment.at(mid[0])
        self.loop_side = 1. if (mid[1] - cx) * -math.sin(h) + (mid[2] - cy) * math.cos(h) > 0 else -1.
        self.structures = self.route['summary']['structures']

    def frame(self, s):
        """Position (x, y, rail z), unit tangent and left normal at chainage s (arrays for array s)."""
        s = np.clip(np.asarray(s, float), 0, self.length)
        x, y, h, _ = self.alignment.at(s)
        z = np.interp(s, self.s, self.rail)
        t = np.stack([np.cos(h), np.sin(h), np.zeros_like(h)], -1)
        n = np.stack([-np.sin(h), np.cos(h), np.zeros_like(h)], -1)
        return np.stack([x, y, z], -1), t, n

    def place(self, s, u, v):
        """World points at chainage s, u metres to the left and v above the rail top (broadcast)."""
        p, _, n = self.frame(s)
        return p + np.asarray(u, float)[..., None] * n + np.asarray(v, float)[..., None] * np.array([0., 0., 1.])

    def ground_at(self, s):
        return np.interp(s, self.s, self.ground)

    def heading(self, s):
        return float(self.alignment.at(s)[2])

    def ranges(self, kind):
        return [(st['start'], st['end']) for st in self.structures if st['kind'] == kind]

    def loop_offset(self, s):
        """Centre of the loop track to the left of the main line's (0 outside the loop)."""
        a, b = self.loop
        s = np.asarray(s, float)
        t = np.clip(np.minimum(s - a, b - s) / R.TURNOUT, 0, 1)
        inside = (s >= a) & (s <= b)
        return np.where(inside, self.loop_side * R.TRACK_SPACING * (1 - np.cos(math.pi * t)) / 2, 0.)


def stations(a, b, spacing):
    """Chainages from a to b, about `spacing` apart, both ends included."""
    n = max(1, math.ceil((b - a) / spacing - 1e-9))
    return np.linspace(a, b, n + 1)


# --- ballast and rails -------------------------------------------------------------------------------------------


RAIL_PROFILES = (           # (u, v) around a rail's head centre, open underneath: 8, 4 and 2 points
    [(-.065, -.15), (-.01, -.12), (-.035, -.045), (-.035, 0.), (.035, 0.), (.035, -.045), (.01, -.12), (.065, -.15)],
    [(-.05, -.15), (-.035, 0.), (.035, 0.), (.05, -.15)],
    [(-.035, 0.), (.035, 0.)],
)


def ballast_profile(lod, extra_left=0., extra_right=0.):
    """The ballast bed's section, right to left: skirt, toe, shoulder, top, shoulder, toe, skirt."""
    top, (toe, toe_v), (skirt, skirt_v) = BALLAST_HALF, BALLAST_TOE, SKIRT
    right = [(-skirt - extra_right, skirt_v), (-toe - extra_right, toe_v), (-top - extra_right, BALLAST_TOP)]
    left = [(top + extra_left, BALLAST_TOP), (toe + extra_left, toe_v), (skirt + extra_left, skirt_v)]
    if lod == 2:
        right, left = right[1:], left[:-1]
    return right + left


def sweep(line, mesh, s_values, section, mat, origin, offset=None):
    """A section [(u, v)] (or a function of chainage giving one) swept along the line. Faces point to the left of
    the section's direction of travel: up for a section running right to left over its top."""
    rows = []
    for s in s_values:
        sec = section(s) if callable(section) else section
        u = np.array([p[0] for p in sec]) + (0. if offset is None else float(offset(s)))
        v = np.array([p[1] for p in sec])
        rows.append(line.place(np.full(len(u), s), u, v) - origin)
    cols = len(rows[0])
    verts = np.concatenate(rows)
    faces = [(i * cols + j, (i + 1) * cols + j, (i + 1) * cols + j + 1, i * cols + j + 1)
             for i in range(len(rows) - 1) for j in range(cols - 1)]
    return mesh.add(verts, faces, mat)


def rails(line, mesh, s_values, lod, origin, offset=None):
    for side in (-1., 1.):
        centre = side * (GAUGE / 2 + .035)
        profile = [(centre + u, v) for u, v in RAIL_PROFILES[lod]]
        sweep(line, mesh, s_values, profile, 'MI_B_iron', origin, offset)


def chunks(line):
    """Main-line chunks: (index, start, end)."""
    edges = stations(0., line.length, CHUNK)
    return [(i, float(a), float(b)) for i, (a, b) in enumerate(zip(edges[:-1], edges[1:]))]


def chunk_mesh(line, start, end, lod, origin):
    """Ballast and both rails of the main line from start to end; through the loop the ballast widens under the
    second track."""
    mesh = Mesh()
    s_values = stations(start, end, SLICES[lod])

    def section(s):
        extra = abs(float(line.loop_offset(s)))
        return ballast_profile(lod, *((extra, 0.) if line.loop_side > 0 else (0., extra)))

    sweep(line, mesh, s_values, section, 'MI_B_gravel', origin)
    rails(line, mesh, s_values, lod, origin)
    return mesh


def loop_mesh(line, lod, origin):
    """The loop track's rails (its ballast is the main chunks' widening)."""
    a, b = line.loop
    mesh = Mesh()
    rails(line, mesh, stations(a, b, SLICES[lod]), lod, origin, line.loop_offset)
    return mesh


# --- sleepers and small pieces -----------------------------------------------------------------------------------


def sleeper_mesh():
    """One sleeper, its origin at the centre of its top face, long axis across the track (local y); 10 triangles
    (the underside is never seen)."""
    length, width, depth = SLEEPER
    return box(Mesh(), (0., 0., -depth / 2), (width, length, depth), 'MI_B_wood', bottom=False)


def sleepers(line):
    """Sleeper instances [x, y, z, yaw degrees, length scale] grouped by main chunk. Where the two tracks of the loop
    are closer than a sleeper's length they share long timbers (scaled and shifted towards the loop track)."""
    groups = {i: [] for i, _, _ in chunks(line)}
    s = np.arange(SLEEPER_SPACING / 2, line.length - SLEEPER_SPACING / 2 + 1e-6, SLEEPER_SPACING)
    offset = line.loop_offset(s)
    shared = np.abs(offset) < SLEEPER[0] + .2
    centre = np.where(shared, offset / 2, 0.)
    scale = np.where(shared, (SLEEPER[0] + np.abs(offset)) / SLEEPER[0], 1.)
    pts = line.place(s, centre, np.full(len(s), -RAIL_HEIGHT))
    yaw = np.degrees(line.alignment.at(s)[2])
    index = np.minimum((s // CHUNK).astype(int), len(groups) - 1)
    for k in range(len(s)):
        groups[int(index[k])].append([*np.round(pts[k], 3).tolist(), round(float(yaw[k]), 3), round(float(scale[k]), 4)])
    own = ~shared & (offset != 0)
    pts = line.place(s[own], offset[own], np.full(own.sum(), -RAIL_HEIGHT))
    for k, j in enumerate(np.flatnonzero(own)):
        groups[int(index[j])].append([*np.round(pts[k], 3).tolist(), round(float(yaw[j]), 3), 1.])
    return groups


def buffer_stop_mesh():
    """A buffer stop: local x towards the arriving train, y left, z up, origin on the rail top at the track centre."""
    mesh = Mesh()
    half = GAUGE / 2 + .035
    for side in (-1., 1.):
        box(mesh, (0., side * half, .55), (.3, .3, 1.1), 'MI_B_iron')                  # posts on the rails
        cylinder(mesh, (0., side * .875, 1.05), (.45, side * .875, 1.05), .17, 'MI_B_iron')   # buffers
        cylinder(mesh, (.45, side * .875, 1.05), (.5, side * .875, 1.05), .22, 'MI_B_iron')
        cylinder(mesh, (-.1, side * half, 1.), (-2.6, side * half, .05), .07, 'MI_B_iron', sides=6)   # raking struts
    box(mesh, (0., 0., 1.05), (.35, 2.8, .45), 'MI_TK_Signal')                         # the red beam
    box(mesh, (-.2, 0., 1.6), (.08, .45, .45), 'MI_TK_Signal')                         # the stop lamp board
    return mesh


def stop_board_mesh():
    """The stopping-point board: a post and a plate, origin at the foot of the post, the plate facing local +x."""
    mesh = Mesh()
    box(mesh, (0., 0., 1.), (.1, .1, 2.), 'MI_B_iron')
    box(mesh, (.06, 0., 2.15), (.03, .5, .4), 'MI_TK_Signal')
    return mesh


def turnout_mesh():
    """The points at a turnout: switch stand and lever, rodding and the timbers' tie bar. Origin at the toe on the
    main line's centre, local x along the diverging direction, the loop to the left (+y); mirrored by a negative
    y scale for the right."""
    mesh = Mesh()
    box(mesh, (1.5, -2.2, .35), (.5, .4, .7), 'MI_B_iron')                         # switch stand
    cylinder(mesh, (1.5, -2.2, .7), (1.5, -2.2, 1.6), .03, 'MI_B_iron', sides=6)  # lever
    box(mesh, (1.5, -2.2, 1.6), (.06, .06, .2), 'MI_TK_Signal')
    box(mesh, (1.5, -1.25, -.05), (.06, 1.9, .06), 'MI_B_iron')                    # rodding to the switch blades
    for side in (-1., 1.):                                                          # switch blades lying against the stock rails
        y = side * (GAUGE / 2 - .03)
        cylinder(mesh, (0., y, -.06), (8., y + (.0 if side < 0 else .35), -.06), .035, 'MI_B_iron', sides=6)
    box(mesh, (18., GAUGE / 2 + .9, -.08), (2.4, .18, .12), 'MI_B_iron')            # frog
    return mesh


def marker_mesh():
    mesh = Mesh()
    box(mesh, (0., 0., .75), (.08, .08, 1.5), 'MI_TK_Marker')
    return mesh


# --- tunnels -----------------------------------------------------------------------------------------------------


def horseshoe(points):
    """The lining's inner section from the right base up over the crown to the left base: `points` around the arch."""
    arc = [(TUNNEL_HALF * math.cos(t), TUNNEL_WALL + TUNNEL_HALF * math.sin(t)) for t in np.linspace(0, math.pi, points)]
    return [(-TUNNEL_HALF, TUNNEL_BASE)] + [(-u, v) for u, v in arc] + [(TUNNEL_HALF, TUNNEL_BASE)]


def tunnels(line):
    """(name, start, end) for each tunnel; the one holding the spiral is 'Spiral'."""
    out, spirals = [], line.route['summary'].get('spirals', [])
    for k, (a, b) in enumerate(line.ranges('tunnel')):
        spiral = any(a <= sp['start'] and sp['end'] <= b for sp in spirals)
        out.append(('Spiral' if spiral else f'T{k + 1}', a, b))
    return out


def lining_mesh(line, start, end, lod, origin):
    """The lining from start to end, facing inwards (the section runs right to left, so swept quads face in)."""
    mesh = Mesh()
    section = horseshoe((12, 5)[lod])[::-1]
    return sweep(line, mesh, stations(start, end, LINING_SLICES[lod]), section, 'MI_TK_TunnelLining', origin)


def lamp_mesh():
    """A wall lamp: local x along the tunnel, y out of the wall into the tunnel, z up, origin on the wall at the
    bracket. An iron plate and arm, and an octagonal glowing globe under a small cap."""
    mesh = Mesh()
    box(mesh, (0., .02, 0.), (.16, .04, .26), 'MI_B_iron')                       # wall plate
    box(mesh, (0., LAMP_REACH / 2, .08), (.04, LAMP_REACH, .04), 'MI_B_iron')    # arm
    cylinder(mesh, (0., LAMP_REACH, .07), (0., LAMP_REACH, .11), .09, 'MI_B_iron')  # cap
    cylinder(mesh, (0., LAMP_REACH, -.12), (0., LAMP_REACH, .07), .07, 'MI_TK_LampGlow')
    return mesh


def tunnel_lamps(line, a, b):
    """Lamps of the tunnel from a to b: [x, y, z, yaw degrees, 1] on the wall (local y into the tunnel), and the
    lights' positions [x, y, z] at their globes. Sides alternate, starting on the left."""
    n = max(1, round((b - a) / LAMP_SPACING))
    lamps, lights = [], []
    for k, s in enumerate(a + (np.arange(n) + .5) * (b - a) / n):
        side = 1. if k % 2 == 0 else -1.                   # +1: the left wall
        h = line.heading(s)
        p = line.place(s, side * TUNNEL_HALF, LAMP_HEIGHT)
        yaw = math.degrees(h) + (180. if side > 0 else 0.)
        lamps.append([*_xyz(p), round(yaw, 3), 1.])
        globe = line.place(s, side * (TUNNEL_HALF - LAMP_REACH), LAMP_HEIGHT - .025)
        lights.append(_xyz(globe))
    return lamps, lights


def tunnel_volume(line, p, q):
    """An oriented box over the tunnel from chainage p to q (for the exposure's post-process volume): centre, yaw
    degrees (x along the chord), half extents."""
    s = stations(p, q, 5.)
    pts, _, _ = line.frame(s)
    a, b = pts[0], pts[-1]
    d = b[:2] - a[:2]
    length = float(np.hypot(*d)) or 1.
    tx, ty = d / length
    rel = pts[:, :2] - a[:2]
    along = rel @ np.array([tx, ty])
    across = rel @ np.array([-ty, tx])
    mid_u = (across.max() + across.min()) / 2
    centre = a[:2] + np.array([tx, ty]) * (along.max() + along.min()) / 2 + np.array([-ty, tx]) * mid_u
    z0, z1 = pts[:, 2].min() + TUNNEL_BASE, pts[:, 2].max() + TUNNEL_WALL + TUNNEL_HALF + .5
    return dict(centre=_xyz((centre[0], centre[1], (z0 + z1) / 2)), yaw=round(math.degrees(math.atan2(ty, tx)), 3),
                half_extent=[round((along.max() - along.min()) / 2 + 1., 3),
                             round((across.max() - across.min()) / 2 + VOLUME_HALF[0], 3), round((z1 - z0) / 2, 3)])


def portal_mesh(lod):
    """A stone portal: local x out of the tunnel, y left, z up, origin at the rail top on the centreline. The face
    wall's opening is the lining's section; a coping, the arch ring and two short wing walls."""
    mesh = Mesh()
    width, height = 13., 9.
    opening = horseshoe((12, 5)[lod])
    outline = [(-width / 2, TUNNEL_BASE), *opening, (width / 2, TUNNEL_BASE), (width / 2, height), (-width / 2, height)]
    wall = prism(Mesh(), outline, -.45, .45, 'MI_B_ashlar')        # built as (across, depth, z): swap to (x, y, z)
    mesh.extend(Mesh([(b, a, z) for a, b, z in wall.verts], [f[::-1] for f in wall.faces], wall.mats))
    box(mesh, (0., 0., height + .2), (1.2, width + .4, .4), 'MI_B_stone')                       # coping
    ring = [(u * 1.12, TUNNEL_WALL + (v - TUNNEL_WALL) * 1.12) for u, v in opening[1:-1]]          # arch ring, proud of the face
    for (u0, v0), (u1, v1) in zip(ring[:-1], ring[1:]):
        box(mesh, (.5, (u0 + u1) / 2, (v0 + v1) / 2), (.15, max(abs(u1 - u0), .3), max(abs(v1 - v0), .3)), 'MI_B_stone')
    for side in (-1., 1.):                                                                      # wing walls
        box(mesh, (3., side * (width / 2 - .45), 3.), (6., .9, 6.5), 'MI_B_ashlar', yaw=side * math.radians(-12))
    return mesh


# --- banks over ground the earthworks cannot carve ----------------------------------------------------------------


BANK_SLICES = (5., 10.)
BANK_ACROSS = (1., 2.5)


def bank_ranges(line):
    """Chainage ranges of embankment over Belmonte's own valley, whose committed terrain is not carved, and over the
    apron's seam with it, where the apron's carving eases out (earthworks.SEAM_FADE): there the bank is a mesh of its
    own (elsewhere the terrain itself is raised, train/earthworks.py)."""
    from belmonte import layout as BM
    from train import earthworks as E
    rows = line.route['samples']
    out, start = [], None
    for i, r in enumerate(rows + [None]):
        on = r is not None and r['class'] == 'embankment' and r['rail_z'] - r['ground_z'] > .3 and \
            float(E.seam_weight(r['x'], r['y'], BM.BOUNDS)) < 1.
        if on and start is None:
            start = max(r['s'] - 5., 0.)
        if not on and start is not None:
            out.append((start, min(rows[i - 1]['s'] + 5., line.length)))
            start = None
    return out


def bank_mesh(line, start, end, lod, origin):
    """The bank from start to end: the earthworks' formation and slopes, over the ground as it is shown (the apron
    partly raised by its own carving near the seam, the valley tiles carved along a final cutting into the Belmonte
    station: earthworks.valley_carve_start) by 2 cm, and down to 0.3 m under it beyond the slopes' toes."""
    from belmonte import layout as BM
    from train import earthworks as E
    ln = E.line()
    carved_from = E.valley_carve_start(ln, line.route['samples'])
    mesh = Mesh()
    s_values = stations(start, end, BANK_SLICES[lod])
    reach = E.FLOOR_HALF + E.ROUND + E.RATIO[1] * max(float(np.max(line.rail - line.ground)), 1.) + 4.
    u = np.arange(-reach, reach + 1e-6, BANK_ACROSS[lod])[::-1]

    def section(s):
        p = line.place(np.full(len(u), s), u, 0.)
        g = R.ground(p[:, 0], p[:, 1])
        if carved_from is not None and s >= carved_from:
            g = E.carve(p[:, 0], p[:, 1], g, ln)        # the valley tile is carved there, not natural
        _, lo, _ = E.design(p[:, 0], p[:, 1], ln)
        lo = np.where(np.isfinite(lo), lo, -np.inf)
        shown = g + E.seam_weight(p[:, 0], p[:, 1], BM.BOUNDS) * (np.maximum(lo, g) - g)
        z = np.where(lo > shown - .3, np.maximum(lo, shown + .02), shown - .3)
        rail = float(np.interp(s, line.s, line.rail))
        return list(zip(u, z - rail))

    return sweep(line, mesh, s_values, section, 'MI_TK_Bank', origin)


# --- the viaduct -------------------------------------------------------------------------------------------------


def viaduct_spans(line):
    """Pier chainages of each viaduct, spans as close to SPAN as fits."""
    out = []
    for a, b in line.ranges('viaduct'):
        n = max(1, round((b - a) / SPAN))
        out.append(np.linspace(a, b, n + 1))
    return out


def span_parts(line, s0, s1, lod):
    """One span in (chainage, u, z) points: the spandrel wall over a semicircular arch between two half piers, the
    deck and the parapets; z absolute. Returned as (outline in (a, z), deck z at both ends, springing z)."""
    length = s1 - s0
    deck0, deck1 = (float(np.interp(s, line.s, line.rail)) - DECK_DEPTH for s in (s0, s1))
    radius = (length - PIER) / 2
    spring = min(deck0, deck1) - CROWN - radius
    centre = length / 2
    arch = [(centre - radius * math.cos(t), spring + radius * math.sin(t))
            for t in np.linspace(0, math.pi, ARCH_SEGMENTS[lod] + 1)]
    return arch, (deck0, deck1), spring


def viaduct_mesh(line, piers, lod, origin):
    """The viaduct's spans and piers from pier chainages `piers`, bent along the line: each span's spandrel is a
    solid (deck line on top, the arch underneath) built in (along, across, z) and mapped onto the curve."""
    mesh = Mesh()
    half = DECK_WIDTH / 2
    for s0, s1 in zip(piers[:-1], piers[1:]):
        length = s1 - s0
        arch, (deck0, deck1), spring = span_parts(line, s0, s1, lod)
        outline = [(0., spring), *arch, (length, spring), (length, deck1), (0., deck0)]
        solid = prism(Mesh(), outline, -half, half, 'MI_B_ashlar')
        local = np.asarray(solid.verts)
        world = line.place(s0 + local[:, 0], local[:, 1], 0.)
        world[:, 2] = local[:, 2]
        mesh.add(world - origin, [tuple(f) for f in solid.faces], 'MI_B_ashlar')
        for side in (-1., 1.):                                                  # parapets
            u = side * (half - PARAPET[0] / 2)
            top = -DECK_DEPTH + PARAPET[1]
            sec = [(u - PARAPET[0] / 2, -DECK_DEPTH), (u - PARAPET[0] / 2, top), (u + PARAPET[0] / 2, top),
                   (u + PARAPET[0] / 2, -DECK_DEPTH)]
            sweep(line, mesh, stations(s0, s1, SLICES[lod] * 2), sec, 'MI_B_stone', origin)
    for k, s in enumerate(piers):                                               # piers down to the ground
        near = [span_parts(line, a, b, lod)[2] for a, b in zip(piers[:-1], piers[1:]) if a <= s <= b]
        top = max(near)                                 # into the higher spandrel: no slit at the springing
        bottom = float(line.ground_at(s)) - 1.5
        if top - bottom < .5:
            continue
        p = line.frame(s)[0]
        box(mesh, (p[0] - origin[0], p[1] - origin[1], (top + bottom) / 2 - origin[2]),
            (PIER, DECK_WIDTH + .6, top - bottom), 'MI_B_ashlar', yaw=line.heading(s), bottom=False)
    return mesh


# --- earthwork markers -------------------------------------------------------------------------------------------


def markers(line):
    """Marker posts at the top of each cutting's slope and the toe of each embankment, both sides, every
    MARKER_EVERY metres: [x, y, z, yaw degrees, 1]. Placement only; the terrain is not carved."""
    out = []
    for s in np.arange(MARKER_EVERY / 2, line.length, MARKER_EVERY):
        kind = line.kind[int(np.argmin(np.abs(line.s - s)))]
        if kind not in ('cutting', 'deep cutting', 'embankment'):
            continue
        h = float(np.interp(s, line.s, line.rail) - line.ground_at(s))
        u = R.FORMATION / 2 + R.SLOPE * abs(h)
        for side in (-1., 1.):
            p = line.place(s, side * u, 0.)
            out.append([round(float(p[0]), 3), round(float(p[1]), 3), round(float(line.ground_at(s)), 3),
                        round(math.degrees(line.heading(s)), 3), 1.])
    return out


# --- the layout --------------------------------------------------------------------------------------------------


def _xyz(p):
    return [round(float(c), 3) for c in p]


def layout(line=None):
    """Every mesh (name -> list of LOD meshes) and track.json's content."""
    line = line or Line()
    meshes, placed = {}, {}
    tunnel_list = tunnels(line)

    def in_tunnel(a, b):
        for name, ta, tb in tunnel_list:
            if a >= ta + TUNNEL_LOAD and b <= tb - TUNNEL_LOAD:
                return name
        return None

    chunk_rows = []
    for i, a, b in chunks(line):
        origin = line.frame(a)[0]
        name = f'SM_TK_Chunk_{i:02d}'
        meshes[name] = [chunk_mesh(line, a, b, lod, origin) for lod in range(3)]
        chunk_rows.append(dict(name=name, start=round(a, 2), end=round(b, 2), origin=_xyz(origin), layer=in_tunnel(a, b),
                               collision='LOD2'))
    loop_origin = line.frame(line.loop[0])[0]
    meshes['SM_TK_Loop'] = [loop_mesh(line, lod, loop_origin) for lod in range(3)]
    chunk_rows.append(dict(name='SM_TK_Loop', start=line.loop[0], end=line.loop[1], origin=_xyz(loop_origin), layer=None,
                           collision=None))

    tunnel_rows = []
    portals = []
    lamps, lights = {}, {}
    for name, a, b in tunnel_list:
        pieces = []
        edges = stations(a, b, CHUNK)
        for k, (p, q) in enumerate(zip(edges[:-1], edges[1:])):
            origin = line.frame(p)[0]
            mesh_name = f'SM_TK_Tunnel_{name}_{k:02d}'
            meshes[mesh_name] = [lining_mesh(line, p, q, lod, origin) for lod in range(2)]
            pieces.append(dict(name=mesh_name, start=round(float(p), 2), end=round(float(q), 2), origin=_xyz(origin),
                               collision='LOD1', volume=tunnel_volume(line, p, q)))
        lamps[name], lights[name] = tunnel_lamps(line, a, b)
        ends = []
        for s, outward in ((a, -1.), (b, 1.)):
            p = line.frame(s)[0]
            yaw = math.degrees(line.heading(s)) + (180. if outward < 0 else 0.)
            portals.append([*_xyz(p), round(yaw, 3), 1.])
            ends.append(dict(chainage=round(s, 2), position=_xyz(p), yaw=round(yaw, 3)))
        boxes = []
        for s, inward in ((a, 1.), (b, -1.)):     # load boxes: TUNNEL_LOAD outside the portal to TUNNEL_LOAD inside
            centre = line.frame(s)[0]
            boxes.append(dict(centre=_xyz(centre), half_extent=[TUNNEL_LOAD, 15., 15.],
                              yaw=round(math.degrees(line.heading(s)), 3)))
        tunnel_rows.append(dict(name=name, start=a, end=b, lining=pieces, portals=ends, load_boxes=boxes,
                                chunks=[c['name'] for c in chunk_rows if c['layer'] == name]))
    meshes['SM_TK_Portal'] = [portal_mesh(lod) for lod in range(2)]
    placed['SM_TK_Portal'] = portals
    bank_rows = []
    for a0, b0 in bank_ranges(line):
        edges = stations(a0, b0, CHUNK)
        for a, b in zip(edges[:-1], edges[1:]):
            origin = line.frame(a)[0]
            name = f'SM_TK_Bank_{len(bank_rows):02d}'
            meshes[name] = [bank_mesh(line, a, b, lod, origin) for lod in range(2)]
            bank_rows.append(dict(name=name, start=round(float(a), 2), end=round(float(b), 2), origin=_xyz(origin),
                                  collision='LOD1'))
    meshes['SM_TK_TunnelLamp'] = [lamp_mesh()]
    placed['SM_TK_TunnelLamp'] = lamps

    viaduct_rows = []
    for v, piers in enumerate(viaduct_spans(line)):
        pieces = []
        start = 0
        while start < len(piers) - 1:
            end = start + 1
            while end < len(piers) - 1 and piers[end + 1] - piers[start] <= VIADUCT_PIECE + 1e-6:
                end += 1
            part = piers[start:end + 1]
            origin = line.frame(part[0])[0]
            name = f'SM_TK_Viaduct_{v}{len(pieces)}'
            meshes[name] = [viaduct_mesh(line, part, lod, origin) for lod in range(3)]
            pieces.append(dict(name=name, start=round(float(part[0]), 2), end=round(float(part[-1]), 2),
                               origin=_xyz(origin), collision='LOD2'))
            start = end
        viaduct_rows.append(dict(start=float(piers[0]), end=float(piers[-1]), piers=[round(float(s), 2) for s in piers],
                                 pieces=pieces))

    meshes['SM_TK_Sleeper'] = [sleeper_mesh()]
    placed['SM_TK_Sleeper'] = sleepers(line)
    meshes['SM_TK_BufferStop'] = [buffer_stop_mesh()]
    placed['SM_TK_BufferStop'] = [
        [*_xyz(line.frame(BUFFER_OFFSET)[0]), round(math.degrees(line.heading(BUFFER_OFFSET)), 3), 1.],
        [*_xyz(line.frame(line.length - BUFFER_OFFSET)[0]),
         round(math.degrees(line.heading(line.length - BUFFER_OFFSET)) + 180., 3), 1.]]
    meshes['SM_TK_StopBoard'] = [stop_board_mesh()]
    boards = []
    for s, facing in ((STOP_OFFSET, 0.), (line.length - STOP_OFFSET, 180.)):
        side = 1. if facing == 0. else -1.            # on the driver's side, right of the arriving train
        p = line.place(s, side * 2.6, 0.)
        boards.append([*_xyz((p[0], p[1], p[2] + TUNNEL_BASE)),
                       round(math.degrees(line.heading(s)) + facing, 3), 1.])
    placed['SM_TK_StopBoard'] = boards
    meshes['SM_TK_Turnout'] = [turnout_mesh()]
    turnouts = []
    for s, toward in ((line.loop[0], 0.), (line.loop[1], 180.)):
        p = line.frame(s)[0]
        mirror = line.loop_side if toward == 0. else -line.loop_side    # the loop is to the left of the diverging direction
        turnouts.append([*_xyz(p), round(math.degrees(line.heading(s)) + toward, 3), round(mirror, 1)])
    placed['SM_TK_Turnout'] = turnouts
    meshes['SM_TK_Marker'] = [marker_mesh()]
    placed['SM_TK_Marker'] = markers(line)

    doc = dict(
        version=1, frame=line.route['frame'] + '; meshes are relative to their origin; instances are '
        '[x, y, z, yaw degrees, scale] (scale: sleepers along their length, turnouts the y mirror)',
        route=dict(length_m=round(line.length, 2), loop=list(line.loop), loop_side='left' if line.loop_side > 0 else 'right',
                   mismatch_m=round(line.mismatch, 4)),
        chunks=chunk_rows, tunnels=tunnel_rows, viaducts=viaduct_rows, banks=bank_rows,
        tunnel_lighting=dict(
            lights=lights, light=LIGHT, lamp_spacing_m=LAMP_SPACING,
            exposure=dict(min_ev=-1., max_ev=1., note='a post-process volume per lining piece (tunnels[].lining[].volume) '
                          'pins the auto-exposure so the tunnel reads dark and the lamps carry the light'),
            note='Real dark tunnels: soot-black lining (MI_TK_TunnelLining), the ground keeps 8.6 m over the rail '
                 '(train/earthworks.py HOOD) so no sky reaches in; one warm point light per wall lamp, no shadows, '
                 'spawned with its tunnel\'s data layer (lights and SM_TK_TunnelLamp instances are grouped by tunnel); '
                 'MI_TK_LampGlow is emissive.'),
        instances={name: ({str(k): v for k, v in rows.items()} if isinstance(rows, dict) else rows)
                   for name, rows in placed.items()},
        instance_groups={'SM_TK_Sleeper': 'per main chunk (HISM per chunk, cull 120 m)',
                         'SM_TK_TunnelLamp': 'per tunnel (its data layer)'},
        editor_only=['SM_TK_Marker'],
        stations=dict(Hidamari=dict(buffer_stop=BUFFER_OFFSET, stopping_point=STOP_OFFSET),
                      Belmonte=dict(buffer_stop=round(line.length - BUFFER_OFFSET, 2),
                                    stopping_point=round(line.length - STOP_OFFSET, 2)),
                      note='Belmonte has its station (station.py, station below); Hidamari\'s yard is its own region\'s'),
        materials=list(MATERIALS))
    from train import overbridge        # the road over the final cutting, on a line ending at the station's site
    bridge_meshes, doc['overbridge'] = overbridge.layout(line)
    from train import station           # the Belmonte terminus's buildings, on a line ending at the station's site
    station_meshes, doc['station'] = station.layout(line)
    meshes.update(station_meshes)
    meshes.update(bridge_meshes)
    return meshes, doc


def triangle_report(meshes):
    """Triangles per mesh family and LOD, and the budget checks."""
    families = {}
    for name, lods in meshes.items():
        family = name if name in BUDGETS else '_'.join(name.split('_')[:3])
        families.setdefault(family, []).append([m.triangles for m in lods])
    report = {}
    for family, rows in families.items():
        budget = BUDGETS.get(family)
        if family == 'SM_TK_Viaduct':
            worst = [sum(r[i] for r in rows) for i in range(len(rows[0]))]
        else:
            worst = [max(r[i] for r in rows) for i in range(len(rows[0]))]
        report[family] = dict(count=len(rows), worst_per_lod=worst, total_lod0=sum(r[0] for r in rows),
                              budget=list(budget) if budget else None,
                              ok=budget is None or all(w <= b for w, b in zip(worst, budget)))
    return report
