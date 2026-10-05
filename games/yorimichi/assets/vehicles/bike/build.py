"""Cairo's bike: a kid-size teal mamachari from the approved Sunburst turnaround.

Metres, +X forward, +Z up, -Y is the drive (right) side; the origin is on the ground under the bottom bracket.
Every moving part is its own mesh with its origin at its pivot, so the game animates them as components:
BK_Frame (static), BK_Steer (local Z is the steering axis), BK_WheelFront / BK_WheelRear (spin about Y),
BK_Crank (spins about Y at the bottom bracket), BK_Pedal (one per side, counter-rotated to stay level),
BK_Kickstand (deployed at 0, stowed by rotating about Y) and BK_RackBoard (the skateboard strapped to the rack).
Vertex alpha is the finish: 0 matte, .5 enamel, 1 chrome. manifest.json records each part's pivot and the
rider contact points (saddle, grips, pedal radius) that the game's rider solve reads.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
import json, math
import bmesh, bpy
from mathutils import Matrix, Vector
from mathutils.geometry import tessellate_polygon

OUT = yori.OUT / 'bike'
# The turnaround's side elevation is the drawing; reference pixels map to metres at this scale.
PX = .00168
GROUND, BBX = 507, 388

def P(x, y, lateral=0.):
    return Vector(((x - BBX) * PX, lateral, (GROUND - y) * PX))

MATTE, ENAMEL, CHROME = 0., .5, 1.
# Colours are matched to the turnaround under the review lighting (dusty blue-green, ivory, tan leather).
TEAL = (.030, .156, .194, ENAMEL); TEAL_DARK = (.026, .114, .140, ENAMEL); TEAL_CASE = (.034, .152, .186, ENAMEL)
CREAM = (.61, .545, .45, ENAMEL); CREAM_DARK = (.44, .39, .32, ENAMEL)
STEEL = (.70, .73, .78, CHROME); STEEL_DARK = (.30, .31, .33, CHROME); SATIN = (.56, .58, .62, .65)
BRIGHT = (.80, .80, .83, .62)   # soft satin chrome: bars, stem and seatpost read light, as drawn
BELL = (.50, .50, .53, .62)     # the dome faces the key light, so it starts darker to land at mid chrome
SPRING = (.16, .16, .17, .62); RIM_LIP = (.12, .12, .13, .62)
TYRE = (.058, .056, .060, MATTE); TYRE_TREAD = (.036, .035, .039, MATTE); TYRE_SIDE = (.075, .073, .076, MATTE)
LEATHER = (.385, .175, .092, MATTE)
WICKER = (.86, .46, .165, MATTE); WICKER_MID = (.60, .30, .095, MATTE); WICKER_DARK = (.25, .115, .032, MATTE)
WICKER_RIM = (.66, .44, .25, MATTE); WICKER_RIM_MID = (.48, .30, .15, MATTE)   # the rim rope is paler and less orange
RED = (.62, .04, .02, ENAMEL); AMBER = (.85, .38, .04, ENAMEL); BLACK = (.03, .03, .035, MATTE)
HOUSING = (.10, .10, .11, MATTE); CABLE = (.20, .20, .22, MATTE)
LENS = (1.0, .94, .78, .35); NAVY = (.025, .035, .085, ENAMEL); PLY = (.45, .25, .10, MATTE)
STRAP = (.42, .22, .09, MATTE); PEDAL = (.072, .072, .078, MATTE); URETHANE = (.86, .80, .64, MATTE)

RA, FA = P(157, 372), P(677, 372)            # axles
BB = P(388, 397)
WHEEL_R = (GROUND + 2 - 372) * PX              # tyre outer radius (sits 2 px into the ground, as drawn)
HEAD_TOP, HEAD_BOTTOM = P(571, 138), P(594, 227)
AXIS = (HEAD_TOP - HEAD_BOTTOM).normalized()   # steering axis, pointing up
CRANK = math.dist((388, 397), (443, 442)) * PX
SADDLE_TOP = P(292, 131)
KICKSTAND = P(140, 386)                        # the stand's pivot bolt, just behind and below the rear axle
STEM = HEAD_TOP + AXIS * .048                  # quill clamp that holds the riser bar
CRANK_Y = .080                                 # crank arm plane, outside the chain case


def frame_along(direction):
    """A rotation whose Z is `direction` and whose X stays in the bike's XZ plane, pointing forward."""
    z = Vector(direction).normalized()
    x = Vector((1, 0, 0)) - z * z.x
    if x.length < 1e-6: x = Vector((0, 0, -1)) - z * -z.z
    x.normalize(); y = z.cross(x)
    return Matrix((x, y, z)).transposed()


class Mesh:
    """Shared-vertex geometry with per-corner colours, smooth shading and sharp edges by angle."""
    def __init__(self, name):
        self.name, self.verts, self.faces, self.colors = name, [], [], []

    def add(self, points):
        base = len(self.verts); self.verts.extend(Vector(p) for p in points); return base

    def face(self, ids, color):
        self.faces.append(tuple(ids)); self.colors.append(color if isinstance(color, (list, tuple)) and len(color) == 4 and not isinstance(color[0], tuple) else color)

    def grid(self, rings, color, closed=True, cap0=False, cap1=False):
        """Faces between consecutive rings of equal length. `color` may be a function (i, k) -> colour."""
        n = len(rings[0]); ids = [self.add(r) for r in rings]
        span = n if closed else n - 1
        for i in range(len(rings) - 1):
            for k in range(span):
                c = color(i, k) if callable(color) else color
                self.face([ids[i] + k, ids[i] + (k + 1) % n, ids[i + 1] + (k + 1) % n, ids[i + 1] + k], c)
        if cap0: self.face([ids[0] + k for k in range(n)][::-1], color(0, 0) if callable(color) else color)
        if cap1: self.face([ids[-1] + k for k in range(n)], color(0, 0) if callable(color) else color)
        return ids

    def tube(self, points, radius, color, sides=12, caps=True, closed_path=False):
        """A round tube along a polyline with parallel-transported rings; `radius` may vary per point."""
        pts = [Vector(p) for p in points]
        radii = radius if isinstance(radius, (list, tuple)) else [radius] * len(pts)
        tangents = []
        for i in range(len(pts)):
            a = pts[i - 1] if (i > 0 or closed_path) else pts[i]
            b = pts[(i + 1) % len(pts)] if (i < len(pts) - 1 or closed_path) else pts[i]
            tangents.append((b - a).normalized())
        ref = Vector((0, 1, 0)) if abs(tangents[0].y) < .9 else Vector((1, 0, 0))
        normal = (ref - tangents[0] * ref.dot(tangents[0])).normalized()
        rings = []
        for i, (p, t) in enumerate(zip(pts, tangents)):
            if i: normal = (normal - t * normal.dot(t)).normalized()
            binormal = t.cross(normal)
            rings.append([p + radii[i] * (math.cos(a) * normal + math.sin(a) * binormal)
                          for a in (2 * math.pi * k / sides for k in range(sides))])
        if closed_path: rings.append(rings[0])
        return self.grid(rings, color, cap0=caps and not closed_path, cap1=caps and not closed_path)

    def torus(self, center, R, r, color, nu=48, nv=10, axis='Y', arc=(0, 2 * math.pi)):
        """Ring in the plane perpendicular to `axis`; `color` may be a function (u, v)."""
        c = Vector(center); full = abs(arc[1] - arc[0] - 2 * math.pi) < 1e-6
        rings = []
        count = nu if full else nu + 1
        for i in range(count):
            u = arc[0] + (arc[1] - arc[0]) * i / nu
            radial = Vector((math.cos(u), 0, math.sin(u))) if axis == 'Y' else Vector((math.cos(u), math.sin(u), 0))
            side = Vector((0, 1, 0)) if axis == 'Y' else Vector((0, 0, 1))
            rings.append([c + radial * (R + r * math.cos(2 * math.pi * k / nv)) + side * r * math.sin(2 * math.pi * k / nv) for k in range(nv)])
        if full: rings.append(rings[0])
        return self.grid(rings, color, cap0=not full, cap1=not full)

    def lathe(self, center, axis, profile, color, sides=16, caps=(False, False)):
        """Surface of revolution: `profile` is (along, radius) pairs on `axis` through `center`."""
        m = frame_along(axis); c = Vector(center)
        rings = [[c + m @ Vector((r * math.cos(2 * math.pi * k / sides), r * math.sin(2 * math.pi * k / sides), h)) for k in range(sides)] for h, r in profile]
        return self.grid(rings, color, cap0=caps[0], cap1=caps[1])

    def rounded_box(self, center, size, color, radius=.004, rotation=None, segments=2):
        """A box with rounded edges, built as a superellipsoid-like lathe of rounded rectangles."""
        w, d, h = (s / 2 for s in size); r = min(radius, w * .9, d * .9, h * .9)
        def outline(inset):
            pts = []
            for cx, cy, a0 in ((w - r, d - r, 0), (-w + r, d - r, 90), (-w + r, -d + r, 180), (w - r, -d + r, 270)):
                for s in range(segments + 1):
                    a = math.radians(a0 + 90 * s / segments)
                    pts.append((cx + (r - inset) * math.cos(a) if r > inset else cx, cy + (r - inset) * math.sin(a) if r > inset else cy))
            return pts
        rot = rotation or Matrix.Identity(3); c = Vector(center)
        rings = []
        for s in range(segments + 1):
            a = math.radians(-90 + 90 * s / segments); z = -h + r + r * math.sin(a); inset = r - r * math.cos(a)
            rings.append([c + rot @ Vector((x, y, z)) for x, y in outline(inset)])
        for s in range(segments + 1):
            a = math.radians(90 * s / segments); z = h - r + r * math.sin(a); inset = r - r * math.cos(a)
            rings.append([c + rot @ Vector((x, y, z)) for x, y in outline(inset)])
        return self.grid(rings, color, cap0=True, cap1=True)

    def transform(self, matrix):
        self.verts = [matrix @ v for v in self.verts]

    def object(self, material):
        me = bpy.data.meshes.new(self.name)
        me.from_pydata([tuple(v) for v in self.verts], [], self.faces)
        me.validate(clean_customdata=False); me.update()
        me.materials.append(material)
        colors = me.color_attributes.new(name='Color', type='FLOAT_COLOR', domain='CORNER')
        for poly, color in zip(me.polygons, self.colors):
            for li in poly.loop_indices: colors.data[li].color = color
        uv = me.uv_layers.new(name='UVMap')
        for poly in me.polygons:
            drop = max(range(3), key=lambda i: abs(poly.normal[i])); axes = [i for i in range(3) if i != drop]
            for li in poly.loop_indices:
                co = me.vertices[me.loops[li].vertex_index].co; uv.data[li].uv = (co[axes[0]] * 4, co[axes[1]] * 4)
        ob = bpy.data.objects.new(self.name, me); bpy.context.scene.collection.objects.link(ob)
        me.shade_smooth()
        # Faces that meet at a crease or change colour keep a hard edge.
        bm = bmesh.new(); bm.from_mesh(me)
        for e in bm.edges:
            if len(e.link_faces) == 2 and e.link_faces[0].normal.angle(e.link_faces[1].normal, 0) > math.radians(48): e.smooth = False
        bm.to_mesh(me); bm.free()
        return ob


def spline(points, n=6):
    """Catmull-Rom through reference points, `n` samples per span."""
    pts = [Vector(p) for p in points]; pts = [2 * pts[0] - pts[1]] + pts + [2 * pts[-1] - pts[-2]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1:i + 3]
        for j in range(n):
            t = j / n
            out.append(.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(pts[-2]); return out


def bezier(p0, p1, p2, p3, n=16):
    p0, p1, p2, p3 = map(Vector, (p0, p1, p2, p3))
    return [(1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t * t * p2 + t ** 3 * p3 for t in (i / n for i in range(n + 1))]


def loop_spline(points, n=4):
    """Closed Catmull-Rom through `points`."""
    pts = [Vector(p) for p in points]; out = []; c = len(pts)
    for i in range(c):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % c], pts[(i + 2) % c]
        for j in range(n):
            t = j / n
            out.append(.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    return out


def resample(points, count, closed=True):
    """`count` points evenly spaced by arc length along a polyline."""
    pts = [Vector(p) for p in points] + ([Vector(points[0])] if closed else [])
    lengths = [0.]
    for a, b in zip(pts, pts[1:]): lengths.append(lengths[-1] + (b - a).length)
    total = lengths[-1]; out = []; j = 0
    for i in range(count):
        s = total * i / (count if closed else count - 1)
        while j < len(lengths) - 2 and lengths[j + 1] < s: j += 1
        f = (s - lengths[j]) / max(lengths[j + 1] - lengths[j], 1e-9)
        out.append(pts[j].lerp(pts[j + 1], min(max(f, 0), 1)))
    return out


def rope(m, path, strands, twists, braid_r, strand_r, colors, samples, closed=True):
    """A braided rope: `strands` strands wound `twists` times around a (horizontal) path."""
    pts = resample(path, samples, closed); n = len(pts)
    for s in range(strands):
        wound = []
        for i, p in enumerate(pts):
            t = (pts[(i + 1) % n] - pts[i - 1]).normalized()
            side = t.cross(Vector((0, 0, 1))).normalized(); up = side.cross(t)
            th = 2 * math.pi * (twists * i / n + s / strands)
            wound.append(p + braid_r * (math.cos(th) * side + math.sin(th) * up))
        m.tube(wound, strand_r, colors[s % len(colors)], sides=6, caps=not closed, closed_path=closed)


def hex_groove(s, t, cell=.0200, groove=.0028):
    """True where (s, t) on the tread lies on a groove between rounded hexagonal lugs."""
    h = cell * .866; r0 = math.floor(t / h); best = []
    for row in range(r0 - 1, r0 + 3):
        off = cell / 2 if row % 2 else 0.; c0 = math.floor((s - off) / cell)
        for col in range(c0 - 1, c0 + 3):
            best.append(math.hypot(s - off - col * cell, t - row * h))
    best.sort()
    return best[1] - best[0] < groove


def wheel(name, hub_half):
    """Balloon tyre (smooth silhouette, rounded hex lugs in the colour), silver rim with a dark inner lip,
    20 evenly spaced spokes, flanged chrome hub."""
    m = Mesh(name)
    R = WHEEL_R; depth, half = 10 * PX, .035
    nu, nv = 320, 36
    rings = []
    for i in range(nu):
        u = 2 * math.pi * i / nu; radial = Vector((math.cos(u), 0, math.sin(u)))
        rings.append([radial * (R - depth + depth * math.cos(2 * math.pi * k / nv)) + Vector((0, half * math.sin(2 * math.pi * k / nv), 0)) for k in range(nv)])
    rings.append(rings[0])
    def tyre(i, k):
        a = 2 * math.pi * (k + .5) / nv; c = math.cos(a)
        if c < .25: return TYRE_SIDE if c < -.6 else TYRE
        # Shallow lugs on the crown only, so the silhouette stays a smooth balloon.
        return TYRE_TREAD if hex_groove(R * 2 * math.pi * (i + .5) / nu, half * a) else TYRE
    m.grid(rings, tyre)
    ro, ri = R - 2 * depth, R - 2 * depth - 13 * PX
    m.lathe((0, 0, 0), (0, 1, 0), [(-.016, ro + .002), (-.018, ro - .002), (-.018, ri + .006), (-.012, ri + .003), (.012, ri + .003), (.018, ri + .006),
                                   (.018, ro - .002), (.016, ro + .002), (-.016, ro + .002)][::-1], SATIN, sides=96)
    m.lathe((0, 0, 0), (0, 1, 0), [(-.0125, ri + .0032), (-.0125, ri + .0005), (.0125, ri + .0005), (.0125, ri + .0032)], RIM_LIP, sides=96)
    f = hub_half - .004
    m.lathe((0, 0, 0), (0, 1, 0), [(-hub_half - .012, .006), (-hub_half - .012, .010), (-f, .010), (-f, .032), (-f + .004, .0336), (-f + .008, .032), (-f + .011, .021),
                                   (f - .011, .021), (f - .008, .032), (f - .004, .0336), (f, .032), (f, .010), (hub_half + .012, .010), (hub_half + .012, .006)], STEEL, sides=24, caps=(True, True))
    for s in range(20):
        side = 1 if s % 2 else -1
        a = 2 * math.pi * s / 20
        hub = Vector((math.cos(a) * .027, side * (f - .004), math.sin(a) * .027))
        rim = Vector((math.cos(a) * (ri + .001), side * .004, math.sin(a) * (ri + .001)))
        m.tube([hub, rim], .0019, STEEL, sides=6, caps=False)
    return m


def axle_nut(m, at, side):
    """Chrome dome nut on a washer."""
    m.lathe(at, (0, side, 0), [(0, 0), (0, .020), (.002, .020), (.003, .016)], STEEL, sides=20)
    m.lathe(at + Vector((0, side * .003, 0)), (0, side, 0), [(0, .015), (.004, .015), (.008, .013), (.011, .009), (.013, .004), (.0135, 0)], STEEL, sides=20)


def frame():
    m = Mesh('BK_Frame')
    r_head, r_seat, r_twin, r_stay = .0235, .0180, .0230, .0125
    L = (HEAD_TOP - HEAD_BOTTOM).length
    m.lathe(HEAD_BOTTOM, AXIS, [(-.004, 0), (-.004, r_head), (L, r_head), (L + .002, 0)], TEAL, sides=20)
    # Slim chrome lower race.
    m.lathe(HEAD_BOTTOM, AXIS, [(-.0085, 0), (-.0085, .0255), (.0065, .0262), (.0085, .0245), (.0085, 0)], STEEL, sides=24)
    # Seat tube: it follows the drawing above the chain case and bends gently into the bottom bracket.
    seat = spline([P(303, 210), P(318, 258), P(334, 304), P(354, 350), P(388, 397)], 5)
    m.tube(seat, r_seat, TEAL, sides=16)
    collar = P(304, 210); up = (P(296, 172) - collar).normalized()
    m.lathe(collar, up, [(-.006, 0), (-.006, .0215), (.002, .0228), (.006, .0215), (.008, .0150), (.008, 0)], STEEL, sides=20)
    m.tube([collar, P(296, 172)], .0150, BRIGHT, sides=18)
    # The mamachari's twin swooping tubes, traced from the turnaround (top edges on the drawing, 25 px thick).
    upper = spline([P(578, 165.5), P(570, 170.5), P(560, 184.5), P(550, 201.5), P(540, 217.5), P(530, 231.5), P(520, 245.5), P(510, 258.5),
                    P(500, 270.5), P(490, 281.5), P(480, 291.5), P(470, 300.5), P(460, 309.5), P(450, 316.5), P(440, 322.5), P(430, 328.5),
                    P(420, 333), P(410, 336.5), P(400, 339.5), P(385, 341.8), P(365, 345.6), P(350, 349)], 3)
    lower = spline([P(586, 226.5), P(570, 240.5), P(560, 256.5), P(550, 270.5), P(540, 285.5), P(530, 298.5), P(520, 311.5), P(510, 321.5),
                    P(500, 331.5), P(490, 340.5), P(480, 348.5), P(470, 354.5), P(460, 361.5), P(450, 367.5), P(440, 372.5), P(425, 379.5),
                    P(410, 386), P(398, 392), P(390, 396)], 3)
    m.tube(upper, r_twin, TEAL, sides=18); m.tube(lower, r_twin, TEAL, sides=18)
    m.lathe(BB, (0, 1, 0), [(-.042, 0), (-.042, .022), (.042, .022), (.042, 0)], TEAL_DARK, sides=18)
    for side in (-1, 1):
        y = side * .056
        m.tube([BB + Vector((0, side * .03, 0)), RA + Vector((0, y, 0))], r_stay, TEAL, sides=12)
        m.tube(spline([P(302, 229, side * .024), P(252, 273, side * .046), RA + Vector((.013, y, .011))], 4), r_stay * 1.16, TEAL, sides=14)
        m.rounded_box(RA + Vector((0, y, 0)), (.036, .012, .036), TEAL_DARK, radius=.007)
        axle_nut(m, RA + Vector((0, side * (.068 if side < 0 else .062), 0)), side)
    m.tube([P(300, 232, -.03), P(300, 232, .03)], r_stay * .9, TEAL, sides=10)
    saddle(m)
    rack(m)
    fender(m, RA, (156, 151), 10, 168, .048, stay_deg=157, depth=(.030, .027), stay_out=-.030, rib=True)
    chain_guard(m)
    # Rear reflector high on the fender tail, facing back: a deep red lens in front of a dark housing.
    m.rounded_box(P(42, 272), (.024, .050, .058), HOUSING, radius=.006)
    m.rounded_box(P(29.5, 272), (.022, .042, .052), RED, radius=.005)
    return m


def saddle(m):
    """A plump sprung saddle: 140 px long, a tall rounded rear about 1.6x the nose's width, a dip in the top,
    rolled edges, one tan leather."""
    rear, nose = 222, 362
    top = spline([(0, 131), (.07, 128), (.25, 130), (.48, 137), (.78, 134), (.94, 135), (1, 137)], 6)
    bottom = spline([(0, 166), (.08, 176), (.3, 181), (.55, 177), (.8, 166), (1, 162)], 6)
    def lookup(curve, t):
        for (t0, y0), (t1, y1) in zip(curve, curve[1:]):
            if t0 <= t <= t1: return y0 + (y1 - y0) * (t - t0) / max(t1 - t0, 1e-9)
        return curve[-1][1]
    top = [(p.x, p.y) for p in top]; bottom = [(p.x, p.y) for p in bottom]
    count, sides = 25, 28
    rings = []
    for i in range(count):
        t = .5 - .5 * math.cos(math.pi * i / (count - 1))
        # A full, squared-off rear and a rounded, tapering nose.
        e = 5 if t < .5 else 3.6
        end = max(1 - abs(2 * t - 1) ** e, 0) ** (1 / e)
        half = (.0860 + (.050 - .0860) * min(1, max(0, (t - .2) / .75)) ** 1.3) * max(end, .02) ** .55
        zt, zb = (GROUND - lookup(top, t)) * PX, (GROUND - lookup(bottom, t)) * PX
        zc, hz = (zt + zb) / 2, (zt - zb) / 2 * max(end, .02) ** .45
        x = (rear + (nose - rear) * t - BBX) * PX
        ring = []
        for k in range(sides):
            a = 2 * math.pi * k / sides; c, s = math.cos(a), math.sin(a)
            # Rolled edges: a domed top, sides that tuck in toward a flatter base.
            y = half * math.copysign(abs(c) ** (.55 if s > 0 else .32), c) * (1 - .10 * max(0, -s) ** 1.5)
            z = zc + hz * math.copysign(abs(s) ** (.55 if s > 0 else .22), s)
            ring.append(Vector((x, y, z)))
        rings.append(ring)
    m.grid(rings, LEATHER, cap0=True, cap1=True)
    # Two pairs of dark coil springs under the back, a rail that tucks under the leather, and the clamp on the post.
    for side in (-1, 1):
        for sx in (253, 263):
            base = P(sx, 203, side * .030)
            turns, height, r = 4, .047, .0090
            coil = [base + Vector((r * math.cos(t), r * math.sin(t), height * t / (2 * math.pi * turns))) for t in (j * .25 for j in range(int(2 * math.pi * turns / .25) + 1))]
            m.tube(coil, .0042, SPRING, sides=8)
        m.tube(spline([P(250, 198, side * .030), P(280, 190, side * .024), P(305, 180, side * .018), P(322, 170, side * .014)], 5), .0042, STEEL, sides=8)
        m.rounded_box(P(260, 172, side * .030), (.044, .022, .006), STEEL_DARK, radius=.002)
    m.lathe(P(296, 179, -.034), (0, 1, 0), [(0, 0), (0, .011), (.068, .011), (.068, 0)], STEEL, sides=12)
    m.rounded_box(P(296, 175), (.030, .030, .016), STEEL_DARK, radius=.004)


def rack(m):
    """Rear carrier: one fat perimeter tube with slats, struts to the axle, a bracket down to the fender, a stay forward."""
    w = .072; zt = zb = P(0, 194).z; xr, xf = P(84, 0).x, P(228, 0).x
    def rounded_rect(z, inset):
        hw, x0, x1, r = w - inset, xr + inset, xf - inset, .022
        pts = []
        for cx, cy, a0 in ((x1 - r, hw - r, 0), (x0 + r, hw - r, 90), (x0 + r, -hw + r, 180), (x1 - r, -hw + r, 270)):
            for s in range(5):
                a = math.radians(a0 + 90 * s / 4); pts.append(Vector((cx + r * math.cos(a), cy + r * math.sin(a), z)))
        return pts
    m.tube(rounded_rect(zt, 0), .0094, TEAL, sides=14, closed_path=True)
    for x in (P(112, 0).x, P(140, 0).x, P(168, 0).x):
        m.tube([Vector((x, -w + .004, zt + .003)), Vector((x, w - .004, zt + .003))], .0055, TEAL, sides=8)
    for y in (-.020, .020):
        m.tube([Vector((xr + .006, y, zt + .004)), Vector((xf - .006, y, zt + .004))], .0050, TEAL, sides=8)
    for side in (-1, 1):
        m.tube([P(100, 197, side * w), RA + Vector((-.006, side * .070, .006))], .0098, TEAL, sides=12)
        m.tube([P(127, 197, side * (w - .002)), RA + Vector((.012, side * .070, .022))], .0072, TEAL, sides=10)
        m.tube([P(222, 196, side * (w - .004)), P(282, 243, side * .034)], .0078, TEAL, sides=10)
    # Bracket from the rear cross rail down to the fender crown.
    m.tube([P(206, 201, -w + .004), P(206, 201, w - .004)], .0062, TEAL, sides=10)
    m.tube([P(206, 201), P(206, 224)], .0090, TEAL, sides=14)
    m.lathe(P(206, 226), (0, 0, 1), [(0, 0), (0, .014), (.003, .013), (.005, .009), (.006, 0)], TEAL, sides=14)


def fender(m, axle, radius_px, start_deg, end_deg, half, stay_deg, depth=.024, stay_out=.012, rib=False):
    """Cream mudguard concentric with the wheel: a deep rounded U with rolled beads, ends rolled round, and one
    chrome stay per side that ends in a cap. `radius_px` and `depth` may be (start, end) pairs: the front guard is
    shallow at its nose and opens out behind. `rib` adds the raised centre crease."""
    r0, r1 = radius_px if isinstance(radius_px, tuple) else (radius_px, radius_px)
    d0, d1 = depth if isinstance(depth, tuple) else (depth, depth)
    R, roll, steps = (r0 + r1) / 2 * PX, 6, 48
    a0, a1 = math.radians(start_deg), math.radians(end_deg)
    cap = .022 / R                                   # angle taken by each rounded end
    def blend(a):
        return min(1, max(0, (a - a0) / (a1 - a0)))
    def radius(a):
        return (r0 + (r1 - r0) * blend(a)) * PX
    def section(a, shrink, r_off, h_off):
        radial = Vector((math.cos(a), 0, math.sin(a))); ring = []; d = d0 + (d1 - d0) * blend(a)
        for k in range(13):
            phi = -math.pi / 2 + math.pi * k / 12
            ring.append(axle + radial * (radius(a) - r_off - d * shrink * (1 - math.cos(phi))) + Vector((0, (half - h_off) * shrink * math.sin(phi), 0)))
        return ring
    stations = [(a0 - cap * math.cos(math.pi / 2 * j / roll), math.sin(math.pi / 2 * j / roll) ** .5) for j in range(1, roll)]
    stations += [(a0 + (a1 - a0) * i / steps, 1.) for i in range(steps + 1)]
    stations += [(a1 + cap * math.sin(math.pi / 2 * j / roll), math.cos(math.pi / 2 * j / roll) ** .5) for j in range(1, roll)]
    stations = [(a, max(f, .08)) for a, f in stations]
    outer = [section(a, f, 0, 0) for a, f in stations]
    inner = [section(a, f, .004, .004) for a, f in stations]
    m.grid(outer, CREAM, closed=False)
    m.grid([r[::-1] for r in inner], CREAM, closed=False)
    m.grid([inner[0], outer[0]], CREAM, closed=False); m.grid([outer[-1], inner[-1]], CREAM, closed=False)
    # Beads thin out round the rolled ends rather than poking past them.
    taper = [.0040 * min(1, f * 1.4) ** .7 for _, f in stations]
    for edge in (0, 12):
        m.tube([r[edge] for r in outer], taper, CREAM, sides=8, caps=True)
    if rib:
        m.tube([r[6] for r in outer], [.0026 * min(1, f * 1.4) ** .7 for _, f in stations], CREAM, sides=8, caps=True)
    a = math.radians(stay_deg); radial = Vector((math.cos(a), 0, math.sin(a)))
    for side in (-1, 1):
        top = axle + radial * (radius(a) + stay_out) + Vector((0, side * (half + .004), 0))
        m.tube([top, axle + Vector((0, side * .066, 0))], .0034, STEEL, sides=8)
        m.lathe(top, radial, [(-.002, .0050), (.002, .0048), (.004, .0030), (.0048, 0)], STEEL, sides=10)


GUARD = [(190, 341), (250, 340), (320, 341), (385, 343), (412, 350), (428, 368), (433, 395), (427, 421), (410, 438), (385, 445),
         (340, 443), (290, 436), (245, 428), (212, 420), (185, 414), (158, 410), (140, 400), (131, 382), (133, 364), (145, 350), (165, 343)]
# Sunburst rays as drawn: (angle in degrees, inner and outer radius in pixels) about the half sun at (310, 418).
RAYS = [(169, 30, 72), (142, 29, 75), (128, 27, 73), (106, 28, 63), (71, 27, 62), (48, 28, 69), (22, 28, 47), (-8, 30, 53)]


def chain_guard(m):
    """Full chain case on the drive side, wrapping the rear hub: a bevelled, raised face with a lip, a dome over the
    hub, a raised ring round the crank, and the cream sunburst."""
    y_face, rise = -.0595, .004
    outline = loop_spline([P(x, z) for x, z in GUARD], 4); n = len(outline)
    def y_back(x):
        # Behind the chain line the case is shallow; round the hub it steps outboard of the spokes.
        return -.031 + (-.050 + .031) * min(1, max(0, (P(232, 0).x - x) / (P(232, 0).x - P(168, 0).x)))
    face = [Vector((p.x, y_face, p.z)) for p in outline]; back = [Vector((p.x, y_back(p.x), p.z)) for p in outline]
    m.grid([back, face], TEAL_CASE)
    inner = []
    for k, p in enumerate(outline):
        t = (outline[(k + 1) % n] - outline[k - 1]).normalized()
        inner.append(Vector((p.x + t.z * .012, y_face - rise, p.z - t.x * .012)))
    m.grid([inner, face], TEAL_CASE)
    # The outline is concave under the hub, so the face is triangulated properly rather than fanned.
    ids = m.add(inner)
    for tri in tessellate_polygon([[(p.x, p.z, 0) for p in inner]]):
        a, b, c = (ids + i for i in tri)
        if ((inner[tri[1]] - inner[tri[0]]).cross(inner[tri[2]] - inner[tri[0]])).y > 0: b, c = c, b
        m.face([a, b, c], TEAL_CASE)
    m.tube(face, .0042, TEAL_CASE, sides=8, closed_path=True)
    m.lathe(RA + Vector((0, y_face - rise, 0)), (0, -1, 0), [(0, .044), (.002, .043), (.004, .038), (.006, .028), (.0075, .016), (.0078, 0)], TEAL_CASE, sides=32)
    m.lathe(Vector((BB.x, y_face - rise, BB.z)), (0, -1, 0), [(0, .036), (.003, .035), (.0048, .031), (.003, .026), (0, .025)], TEAL_CASE, sides=32)
    m.tube([Vector((RA.x + .040, y_face - rise - .002, RA.z - .004)), Vector((P(252, 0).x, y_face - rise - .002, P(0, 377).z))], .0072, TEAL_CASE, sides=12)
    sun = P(310, 418); yd = y_face - rise - .0015
    pts = [Vector((sun.x + 25 * PX * math.cos(math.pi * i / 16), yd, sun.z + 25 * PX * math.sin(math.pi * i / 16))) for i in range(17)]
    base = m.add(pts); c = m.add([Vector((sun.x, yd, sun.z))])
    for i in range(16): m.face([c, base + i, base + i + 1], CREAM)
    for deg, r0, r1 in RAYS:
        a = math.radians(deg); d = Vector((math.cos(a), 0, math.sin(a))); nrm = Vector((-math.sin(a), 0, math.cos(a)))
        w0, w1 = 2.8 * PX, 5.6 * PX * min(1, (r1 - r0) / 34)
        quad = [sun + d * r0 * PX - nrm * w0, sun + d * r1 * PX - nrm * w1, sun + d * r1 * PX + nrm * w1, sun + d * r0 * PX + nrm * w0]
        ids = m.add([Vector((q.x, yd, q.z)) for q in quad]); m.face([ids, ids + 1, ids + 2, ids + 3], CREAM)


def bar_path(side):
    """Riser bar from the quill clamp: out, up to a high bend, then back to the grip (side +1 is the left)."""
    s = side
    return spline([STEM, P(563, 111, s * .045), P(561, 104, s * .078), P(558, 89, s * .094), P(555, 72, s * .103), P(548, 61, s * .114),
                   P(536, 56, s * .133), P(522, 58, s * .154), P(509, 64, s * .170)], 5)


GRIP = ((506, 66, .172), (446, 74, .246))


def steer():
    """Fork, quill stem, riser bar, grips, levers, cables, bell, caliper brake, basket, lamp and front fender.
    Built in bike space, then moved into the steering frame (origin at the head tube's lower race)."""
    m = Mesh('BK_Steer')
    F = frame_along(AXIS)
    m.lathe(HEAD_TOP, AXIS, [(-.004, 0), (-.004, .0262), (.007, .0262), (.009, .0236), (.012, .0236), (.014, .0262), (.024, .0262), (.026, .0215),
                             (.028, .0195), (.028, 0)], STEEL, sides=24)
    crown = HEAD_BOTTOM - AXIS * .017
    m.rounded_box(crown, (.036, .156, .020), TEAL, radius=.009, rotation=F, segments=3)
    for side in (-1, 1):
        y = side * .058
        # Blades drop almost straight, then sweep forward into a round dropout eye on the axle.
        leg = spline([P(597, 239, y), P(604, 262, y), P(611, 282, y), P(618, 300, y), P(628, 320, y), P(639.5, 340, y), P(652, 355, y),
                      P(666, 366, y), FA + Vector((0, y, 0))], 4)
        m.tube(leg, [.0205 - .0045 * (i / (len(leg) - 1)) ** .8 for i in range(len(leg))], TEAL, sides=18)
        m.lathe(FA + Vector((0, y - side * .007, 0)), (0, side, 0), [(0, 0), (0, .0165), (.002, .0175), (.012, .0175), (.014, .0165), (.014, 0)], TEAL, sides=20)
        axle_nut(m, FA + Vector((0, side * .070, 0)), side)
    # Quill stem and the clamp barrel the bar passes through.
    m.tube([HEAD_TOP + AXIS * .020, STEM], .0188, BRIGHT, sides=18)
    m.lathe(STEM + Vector((0, -.032, 0)), (0, 1, 0), [(0, 0), (0, .0150), (.064, .0150), (.064, 0)], BRIGHT, sides=16)
    for side in (-1, 1):
        bar = bar_path(side)
        m.tube(bar, .0140, BRIGHT, sides=14, caps=False)
        g0, g1 = P(*GRIP[0][:2], side * GRIP[0][2]), P(*GRIP[1][:2], side * GRIP[1][2])
        d = (g1 - g0).normalized(); L = (g1 - g0).length
        # Ribbed leather grip, six grooves right round, behind a chrome collar.
        prof = [(-.002, 0), (-.002, .0240), (.003, .0262)]
        for j in range(6):
            z = .006 + (j + .5) * (L - .022) / 6
            prof += [(z - .0045, .0266), (z - .0018, .0260), (z - .0008, .0236), (z + .0008, .0236), (z + .0018, .0260), (z + .0045, .0266)]
        prof += [(L - .014, .0270), (L - .008, .0290), (L - .003, .0280), (L + .002, .020), (L + .004, .010), (L + .0045, 0)]
        m.lathe(g0, d, prof, LEATHER, sides=22)
        m.lathe(g0, d, [(-.014, 0), (-.014, .0180), (-.012, .0200), (-.004, .0200), (-.002, .0180), (-.002, 0)], STEEL_DARK, sides=20)
        # Lever: a small pivot block under the collar and one smooth chrome arc back under the grip, knob at its tip.
        m.rounded_box(P(518, 76, side * .165), (.020, .018, .016), STEEL, radius=.005)
        lever = bezier(P(518, 78, side * .165), P(516, 92, side * .171), P(500, 102, side * .182), P(485, 103, side * .193), 14)
        m.tube(lever, [.0056 - .0012 * i / 14 for i in range(15)], STEEL, sides=10)
        m.lathe(lever[-1] + Vector((0, side * .004, 0)), (0, side, 0), [(-.010, 0), (-.008, .005), (-.004, .0068), (.003, .0066), (.006, .004), (.007, 0)], STEEL, sides=12)
        # Brake cables leave from behind the stem: the right lever's to the front caliper, the left's down the frame.
        if side == -1:
            route = [P(520, 72, -.156), P(538, 70, -.118), P(556, 80, -.070), P(578, 100, -.030), P(604, 150, -.010), P(616, 214, 0)]
        else:
            route = [P(520, 72, .156), P(540, 66, .122), P(556, 66, .080), P(566, 80, .036), P(580, 110, .022), P(592, 140, .024)]
        m.tube(spline(route, 6), .0032, CABLE, sides=6)
        if side == -1:
            # Bell on the right bar: black base ring, a squat round chrome dome, a round black thumb knob toward the rider.
            base = P(530.5, 46, -.150)
            m.rounded_box(P(532, 53.5, -.150), (.020, .022, .026), STEEL_DARK, radius=.005)
            m.lathe(base, (0, 0, 1), [(0, 0), (0, .0270), (.002, .0280), (.013, .0280), (.015, .0260), (.0152, 0)], BLACK, sides=28)
            m.lathe(base + Vector((0, 0, .015)), (0, 0, 1), [(0, 0), (0, .0336), (.008, .0322), (.015, .0285), (.021, .0215), (.025, .0125), (.027, 0)], BELL, sides=32)
            m.tube([P(522, 41, -.150), P(509, 39, -.150)], .0040, BLACK, sides=8)
            m.lathe(P(503.5, 38.5, -.150) + Vector((0, .007, 0)), (0, -1, 0), [(0, 0), (.001, .007), (.004, .0112), (.008, .0118), (.012, .0105), (.014, .006), (.0145, 0)], BLACK, sides=16)
    # Side-pull caliper on the crown's front: a pivot bolt and two arms that reach the rim.
    pivot = P(617, 227)
    m.lathe(pivot + Vector((0, -.020, 0)), (0, 1, 0), [(0, 0), (0, .0065), (.040, .0065), (.040, 0)], STEEL, sides=12)
    for side in (-1, 1):
        m.tube(bezier(pivot + Vector((0, side * .012, 0)), P(622, 236, side * .046), P(628, 255, side * .046), P(632, 268, side * .028), 12), .0042, STEEL, sides=10)
        m.rounded_box(P(634, 275, side * .028), (.020, .010, .034), SATIN, radius=.004)
        for bx, by in ((632, 272), (637, 283)):
            m.lathe(P(bx, by, side * .033), (0, side, 0), [(0, 0), (0, .0042), (.002, .0042), (.003, .002), (.003, 0)], STEEL, sides=8)
    basket(m); lamp(m)
    fender(m, FA, (145, 157), 95, 196, .047, stay_deg=189, depth=(.020, .032), stay_out=-.006)
    to_local = (Matrix.Translation(HEAD_BOTTOM) @ F.to_4x4()).inverted()
    m.transform(to_local)
    return m


def lamp(m):
    """Chrome bullet lamp on a dark post standing on the fender: a deep round bowl, a thick chrome bezel and a domed
    cream lens facing forward. 43 px from the back of the bowl to the lens, as drawn."""
    c = P(698.5, 218.5)
    bowl = [(.010 - .0445 * math.cos(math.radians(t)), .0330 * math.sin(math.radians(t)) ** .85) for t in range(0, 91, 6)]
    m.lathe(c, (1, 0, 0), bowl + [(.016, .0334), (.020, .0336)], STEEL, sides=40)
    m.lathe(c, (1, 0, 0), [(.020, .0336), (.0215, .0362), (.0235, .0372), (.030, .0372), (.0325, .0360), (.0335, .0330), (.0332, .0290)], STEEL, sides=40)
    m.lathe(c, (1, 0, 0), [(.0330, .0290), (.0350, .0240), (.0366, .0160), (.0374, .008), (.0376, 0)], LENS, sides=40)
    m.tube([P(667.5, 200), P(667.5, 226)], .0105, STEEL_DARK, sides=14)
    m.lathe(P(667.5, 199), (0, 0, 1), [(-.004, 0), (-.004, .0125), (.001, .0125), (.002, 0)], STEEL, sides=14)
    m.lathe(P(667.5, 231), (0, 0, 1), [(0, 0), (0, .016), (.003, .015), (.006, .011), (.008, 0)], STEEL_DARK, sides=14)
    m.tube([P(667.5, 216), P(676, 219), c + Vector((-.030, 0, 0))], .0058, STEEL_DARK, sides=10)


def basket(m):
    """Woven wicker basket: a rounded tub whose walls taper in to the base with a slight barrel, horizontal weavers
    over upright stakes, one fat rolled rim and a braided foot."""
    top_c, bot_c = P(657, 107), P(662, 200)
    top_h, bot_h = (.113, .121), (.078, .088)
    rows, per_row, per_block, blocks = 13, 3, 4, 40
    seg = per_block * blocks

    def footprint(t, grow=0., count=seg):
        bulge = .0080 * math.sin(math.pi * min(t, 1)) ** .8   # the walls barrel out a little at mid-height
        hx = bot_h[0] + (top_h[0] - bot_h[0]) * t + grow + bulge; hy = bot_h[1] + (top_h[1] - bot_h[1]) * t + grow + bulge
        c = bot_c.lerp(top_c, t)
        fine = []
        for k in range(720):
            a = 2 * math.pi * k / 720; cx, cy = math.cos(a), math.sin(a)
            fine.append(Vector((c.x + hx * math.copysign(abs(cx) ** .68, cx), hy * math.copysign(abs(cy) ** .68, cy), c.z)))
        return resample(fine, count), c

    def over(i, k):
        # Plain weave: each weaver passes in front of one stake and behind the next, alternating row to row.
        return (k // per_block + min(i // per_row, rows - 1)) % 2 == 0
    rings = []
    for i in range(rows * per_row + 1):
        t = i / (rows * per_row); crest = i % per_row != 0
        pts, c = footprint(t)
        ring = []
        for k, p in enumerate(pts):
            stake = k % per_block == 0
            h = ((1. if over(i, k) else .45) * (.55 if stake else 1.)) if crest else 0.
            radial = Vector((p.x - c.x, p.y, 0)).normalized()
            ring.append(p + radial * .0040 * h)
        rings.append(ring)
    def weave(i, k):
        crest = i % per_row == 1
        if k % per_block == 0 and not over(i, k): return WICKER_DARK
        if over(i, k): return WICKER if crest else WICKER_MID
        return WICKER_MID if crest else WICKER_DARK
    m.grid(rings, weave)
    inner = []
    for i in range(rows + 1):
        pts, c = footprint(i / rows, -.007, 96); inner.append(pts[::-1])
    m.grid(inner, lambda i, k: WICKER_MID if i % 2 else WICKER_DARK)   # weavers seen from inside: plain rows
    floor, c = footprint(0, -.007, 96); ids = m.add(floor); centre = m.add([Vector((c.x, 0, c.z + .002))])
    for k in range(96): m.face([ids + k, ids + (k + 1) % 96, centre], WICKER_DARK)
    under, c = footprint(0, .0, 96); ids = m.add(under); centre = m.add([Vector((c.x, 0, c.z - .002))])
    for k in range(96): m.face([ids + (k + 1) % 96, ids + k, centre], WICKER_DARK)
    # One fat rolled rim on the wall's top edge, about 13 px deep.
    rim, _ = footprint(1, .004, 240); rim = [p + Vector((0, 0, .004)) for p in rim]
    m.tube(rim + [rim[0]], .0085, WICKER_DARK, sides=10, caps=False)
    rope(m, rim, 3, 46, .0062, .0062, [WICKER_RIM, WICKER_RIM_MID, WICKER_RIM], 480)
    foot, _ = footprint(0, .003, 200)
    rope(m, foot, 2, 36, .0042, .0044, [WICKER_MID, WICKER], 260)
    # Mounts: two arms from the back wall to the stem clamp, and two lugs under the floor.
    for side in (-1, 1):
        m.tube([P(592, 134, side * .05), P(580, 130, side * .04), STEM + Vector((.012, side * .026, -.020))], .0040, STEEL_DARK, sides=8)
        m.rounded_box(P(616, 202, side * .050), (.016, .012, .012), STEEL_DARK, radius=.003)


def crank():
    """Spindle, chainring and both crank arms with chrome bosses; the right arm points forward-down when posed."""
    m = Mesh('BK_Crank')
    m.lathe((0, 0, 0), (0, 1, 0), [(-CRANK_Y, 0), (-CRANK_Y, .0085), (CRANK_Y, .0085), (CRANK_Y, 0)], STEEL, sides=12)
    m.lathe((0, -.046, 0), (0, 1, 0), [(-.003, 0), (-.003, .072), (.003, .072), (.003, 0)], STEEL_DARK, sides=32)
    for side, angle in ((-1, 0.), (1, math.pi)):
        d = Vector((math.cos(angle), 0, -math.sin(angle))); y = side * CRANK_Y
        m.tube([Vector((0, y, 0)), d * CRANK + Vector((0, y, 0))], [.0130, .0095], STEEL, sides=12)
        m.lathe(Vector((0, side * (CRANK_Y - .010), 0)), (0, side, 0), [(0, 0), (0, .028), (.008, .028), (.012, .024), (.015, .014), (.016, 0)], STEEL, sides=24)
        m.lathe(Vector((0, side * (CRANK_Y + .005), 0)), (0, side, 0), [(0, .012), (.003, .011), (.0035, 0)], BLACK, sides=16)
        m.lathe(d * CRANK + Vector((0, y, 0)), (0, side, 0), [(-.006, 0), (-.006, .014), (.008, .014), (.008, 0)], STEEL, sides=14)
    return m


def pedal():
    """Chunky block pedal: dark body with two tread lugs on each face, amber reflectors front, back and on the outer end."""
    m = Mesh('BK_Pedal')
    m.lathe((0, 0, 0), (0, -1, 0), [(0, 0), (0, .007), (.100, .007), (.100, 0)], STEEL, sides=8)
    body = Vector((0, -.056, 0))
    m.rounded_box(body, (.084, .090, .036), PEDAL, radius=.007)
    for x in (-.0425, .0425):
        m.rounded_box(body + Vector((x, 0, 0)), (.006, .040, .014), AMBER, radius=.002)
    m.rounded_box(body + Vector((0, -.0445, 0)), (.040, .004, .014), AMBER, radius=.0015)   # outer face, centred
    for z in (-.0185, .0185):
        for y in (-.022, .022):
            m.rounded_box(body + Vector((0, y, z)), (.070, .026, .005), TYRE_SIDE, radius=.002)
    return m


def kickstand():
    """Mamachari centre stand clamped just under the rear hub: a pivot tube with a clamp plate each side, and two
    straight chrome legs that splay out past the tyre to rounded grey rubber feet. Stowed by rotating about Y."""
    m = Mesh('BK_Kickstand')
    drop = KICKSTAND.z
    m.tube([Vector((0, -.060, 0)), Vector((0, .060, 0))], .0068, STEEL, sides=12)
    for side in (-1, 1):
        top = Vector((0, side * .056, 0)); foot = Vector((.044 if side < 0 else -.024, side * .104, -drop + .016))   # splayed fore and aft too
        m.rounded_box(top + Vector((.004, side * .004, .010)), (.034, .007, .040), STEEL, radius=.004)
        m.lathe(top + Vector((0, side * .008, 0)), (0, side, 0), [(0, 0), (0, .0105), (.003, .0100), (.005, .0075), (.006, 0)], STEEL, sides=16)
        leg = [top + Vector((0, side * .002, -.006)), top.lerp(foot, .5), foot]
        m.tube(leg, [.0098, .0092, .0086], STEEL, sides=16)
        # Rounded rubber foot: a short grey boot whose sole rests on the ground.
        m.lathe(foot + Vector((0, 0, .012)), (leg[-1] - leg[0]).normalized(), [(-.004, 0), (-.004, .0110), (.010, .0128), (.018, .0124), (.024, .0094), (.027, .005), (.028, 0)],
                (.30, .30, .31, MATTE), sides=16)
    return m


def rack_board():
    """Cairo's navy skateboard strapped to the rack on its own trucks, wheels down on the rails, nose against the
    saddle: maple edge band, cream wheels, two thick leather straps round deck and rack with chrome buckles."""
    m = Mesh('BK_RackBoard')
    zb = P(0, 160).z; T = .013; z = zb + T / 2
    x0, x1 = P(-14, 0).x, P(214, 0).x; L, W = x1 - x0, .150
    rings = []
    for i in range(33):
        t = i / 32; x = x0 + L * t; e = abs(t - .5)
        kick = .018 * (max(0, e - .36) / .14) ** 1.6
        half = W / 2 * (max(0, 1 - (max(0, e - .40) / .10) ** 2)) ** .5
        half = max(half, .004)
        rings.append([Vector((x, half * math.cos(2 * math.pi * k / 16), z + kick + T / 2 * math.sin(2 * math.pi * k / 16))) for k in range(16)])
    m.grid(rings, lambda i, k: NAVY if 2 <= k <= 6 else PLY, cap0=True, cap1=True)
    rail_top = P(0, 194).z + .0094
    for tx in (P(22, 0).x, P(168, 0).x):
        axle = rail_top + .018
        m.rounded_box(Vector((tx, 0, zb - .004)), (.044, .040, .008), STEEL_DARK, radius=.002)
        m.tube([Vector((tx, 0, zb - .008)), Vector((tx, 0, axle + .004))], .007, STEEL, sides=10)
        m.rounded_box(Vector((tx, 0, axle)), (.020, .086, .013), STEEL, radius=.005)
        for y in (-.046, .046):
            m.lathe(Vector((tx, y - .009, axle)), (0, 1, 0), [(0, 0), (0, .016), (.003, .018), (.015, .018), (.018, .016), (.018, 0)], URETHANE, sides=18)
    # Thick leather straps round deck and rack, buckled on the drive side.
    bottom = P(0, 194).z - .0094 - .004
    for sx in (P(100, 0).x, P(200, 0).x):
        top = zb + T + .003
        loop = [Vector((sx, -W / 2 - .006, top - .004)), Vector((sx, -W / 2 + .010, top)), Vector((sx, W / 2 - .010, top)), Vector((sx, W / 2 + .006, top - .004)),
                Vector((sx, .078, bottom + .006)), Vector((sx, .070, bottom)), Vector((sx, -.070, bottom)), Vector((sx, -.078, bottom + .006))]
        for a, b in zip(loop, loop[1:] + loop[:1]):
            mid = (a + b) / 2; d = b - a
            rot = frame_along(d) if d.length > 1e-6 else None
            m.rounded_box(mid, (.030, .007, d.length + .006), STRAP, radius=.002, rotation=rot)
        buckle = Vector((sx, -W / 2 - .004, (top + bottom) / 2 + .020))
        m.rounded_box(buckle, (.034, .006, .028), STEEL, radius=.003)
        m.rounded_box(buckle + Vector((0, -.002, 0)), (.022, .006, .016), STRAP, radius=.002)
    return m


def material():
    mat = bpy.data.materials.new('BikePalette'); mat.use_nodes = True
    nodes = mat.node_tree.nodes; bsdf = nodes['Principled BSDF']
    vc = nodes.new('ShaderNodeVertexColor'); vc.layer_name = 'Color'
    mat.node_tree.links.new(vc.outputs['Color'], bsdf.inputs['Base Color'])
    # Preview the finish mask as M_Bike renders it (unreal/Scripts/bike_material.py): paint stays dielectric,
    # metallic = saturate((alpha - .5) * 2.5), roughness = lerp(.78, .22, alpha).
    metal = nodes.new('ShaderNodeMapRange'); metal.inputs['From Min'].default_value = .5; metal.inputs['From Max'].default_value = .9
    mat.node_tree.links.new(vc.outputs['Alpha'], metal.inputs['Value']); mat.node_tree.links.new(metal.outputs['Result'], bsdf.inputs['Metallic'])
    ramp = nodes.new('ShaderNodeMapRange'); ramp.inputs['To Min'].default_value = .78; ramp.inputs['To Max'].default_value = .22
    mat.node_tree.links.new(vc.outputs['Alpha'], ramp.inputs['Value']); mat.node_tree.links.new(ramp.outputs['Result'], bsdf.inputs['Roughness'])
    return mat


def export(m, mat):
    ob = m.object(mat)
    bpy.ops.object.select_all(action='DESELECT'); ob.select_set(True); bpy.context.view_layer.objects.active = ob
    path = OUT / 'assets' / f'{m.name}.fbx'
    bpy.ops.export_scene.fbx(filepath=str(path), use_selection=True, apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL',
                             axis_forward='-Y', axis_up='Z', object_types={'MESH'}, mesh_smooth_type='OFF', use_mesh_edges=False,
                             bake_anim=False, use_custom_props=False, colors_type='SRGB')   # M_Bike decodes sRGB
    lo = Vector((min(v.x for v in m.verts), min(v.y for v in m.verts), min(v.z for v in m.verts)))
    hi = Vector((max(v.x for v in m.verts), max(v.y for v in m.verts), max(v.z for v in m.verts)))
    return ob, {'triangles': sum(len(f) - 2 for f in m.faces), 'vertices': len(m.verts),
                'min': [round(c, 4) for c in lo], 'max': [round(c, 4) for c in hi]}


def parts():
    return [frame(), steer(), wheel('BK_WheelFront', .048), wheel('BK_WheelRear', .050), crank(), pedal(), kickstand(), rack_board()]


def layout():
    """Where each part sits on the assembled bike (bike space), and the rider's contact points."""
    tilt = math.degrees(math.atan2(AXIS.x, AXIS.z))   # steering axis lean back from vertical
    grip = lambda s: [round(c, 4) for c in (P(*GRIP[0][:2], s * GRIP[0][2]) + P(*GRIP[1][:2], s * GRIP[1][2])) / 2]
    return {
        'pivots': {'BK_Frame': [0, 0, 0], 'BK_Steer': list(HEAD_BOTTOM), 'BK_WheelFront': list(FA), 'BK_WheelRear': list(RA),
                   'BK_Crank': list(BB), 'BK_Kickstand': list(KICKSTAND), 'BK_RackBoard': [0, 0, 0]},
        'steer_axis_tilt_degrees': round(-tilt, 3),
        'wheel_radius': round(WHEEL_R, 4), 'crank_length': round(CRANK, 4), 'pedal_offset_y': CRANK_Y,
        'kickstand_stowed_degrees': 96,   # about bike +Y: the legs swing back and up under the fender
        'rider': {'saddle_top': [round(c, 4) for c in SADDLE_TOP],
                  'grips': [grip(1), grip(-1)],
                  'bell': [round(c, 4) for c in P(503.5, 38.5, -.150)],   # the thumb knob
                  # Cairo's sword rides in the basket, guard at the front rim, blade down and back, top leaning forward.
                  'basket_bokken': {'tsuba': [round(c, 4) for c in P(712, 98)], 'pitch_degrees': 38},
                  'wheelbase': round((FA - RA).length, 4)},
    }


def assemble(objects, info):
    """Place the exported parts as the assembled bike for review renders: right crank forward-down, as drawn."""
    piv = info['pivots']
    for name, ob in objects.items():
        if name != 'BK_Pedal': ob.matrix_world = Matrix.Translation(piv.get(name, (0, 0, 0)))
    objects['BK_Steer'].matrix_world = Matrix.Translation(HEAD_BOTTOM) @ frame_along(AXIS).to_4x4()
    right = objects['BK_Pedal']; left = right.copy(); left.data = right.data; left.name = 'BK_Pedal.L'
    bpy.context.scene.collection.objects.link(left)
    a = math.radians(-44)
    objects['BK_Crank'].matrix_world = Matrix.Translation(BB) @ Matrix.Rotation(-a, 4, 'Y')
    right.matrix_world = Matrix.Translation(BB + Vector((math.cos(a) * CRANK, -CRANK_Y, math.sin(a) * CRANK)))
    left.matrix_world = Matrix.Translation(BB + Vector((-math.cos(a) * CRANK, CRANK_Y, -math.sin(a) * CRANK))) @ Matrix.Rotation(math.pi, 4, 'Z')


def main():
    (OUT / 'assets').mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mat = material(); manifest = {'parts': {}}; objects = {}
    for m in parts():
        objects[m.name], manifest['parts'][m.name] = export(m, mat)
    manifest.update(layout())
    assemble(objects, manifest)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'Bike.blend'))
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('BIKE BUILD COMPLETE', sum(p['triangles'] for p in manifest['parts'].values()), 'triangles', flush=True)


if __name__ == '__main__':
    main()
