"""Gondola cabin (gondola_cabin.jpg): a timber cabin with rounded corners, big gasketed windows, a two-leaf sliding
door, a planked roof with steel corner caps, a steel hanger arm and a rope grip with two rollers.

Export frame: the origin is the grip point on the haul-rope axis; +x runs along the rope, z is up, and the door is on
the -y face (the face turned away from the line centre, towards the platform). The hanger kinks out to the door side so
that it passes outside the tower sheave trains and the bullwheel rim. Built in body coordinates (interior floor top at
z = 0, cabin centre at x = y = 0) and lowered by the grip-to-floor distance.
"""
import math

from mathutils import Matrix, Vector

from checks import ROPE_CLEARANCE  # noqa: F401  (re-exported: rope surface to any cabin part outside the jaw zone)
from solid import (BOLT, GASKET, GLASS, IRON, LAMP, PANEL, PLANK, RUBBER, STEEL, TIMBER, TIMBER_DARK, Mesh, rect,
                   rounded_rect, signed_area)

RC = 0.18          # vertical corner radius (exterior)
T = 0.075          # wall thickness
SILL, HEAD = 0.72, 1.97
FLOOR_BOARD = 0.012  # floor boards on the slab; the slab top shows as dark seams between them
COVE_Z, COVE_IN = 2.06, 0.10   # chamfered cove round the ceiling, above the door head
WALL_TOP = 2.12    # top of the walls; roof cap above
CAP_TOP = 2.26     # roof cap crown; planked deck above
SEAT_H, SEAT_D = 0.46, 0.40
DOOR_FRAME = 0.04  # gasket width inside the structural opening
# Detachable grip (export coordinates, rope axis = x axis). The station rail (stations.py) is built from the wheel
# values: its running surface is at wheel_z - wheel_radius, centred on wheel_y, and its underside at rail_bottom_z.
GRIP = {'housing_length': 0.45, 'jaw_cover': 0.035, 'plate_y': (0.10, 0.13), 'plate_z': (-0.10, 0.20),
        'wheel_x': (-0.36, 0.36), 'wheel_y': -0.30, 'wheel_z': 0.16, 'wheel_radius': 0.16, 'wheel_width': 0.07,
        'rail_bottom_z': -0.115, 'post_section': (0.18, 0.10), 'post_y': (-0.03, -0.185),
        'pivot': (0.0, -0.185, -0.13)}
# The grip follows the rope's tangent; everything below the pivot pin (hanger and cabin) hangs plumb from it.
GRIP_MESHES = ('GD_CabinGrip',)


def pose(grip_rows):
    """The cabin's pose for a grip frame (rope.grip_frame rows): the grip mesh follows the rope; the hanger, body
    and doors hang plumb from the pivot pin (rope.hang_frame: heading only, no pitch or roll)."""
    import rope as R
    from solid import Pose
    rows = [list(r) for r in grip_rows]
    return Pose(Matrix(rows), Matrix(R.hang_frame(rows, GRIP['pivot'])), GRIP_MESHES)


class Cabin:
    def __init__(self, p, d):
        self.p = p; self.d = d
        self.L, self.W = p['cabin_length'], p['cabin_width']
        self.G = d['grip_to_floor']
        self.deck_top = p['cabin_floor_to_roof']
        self.dw = p['door_clear_width']; self.dh = p['door_clear_height']
        self.seats = []          # (label, x, y, z, embed, probe) in export coordinates
        self.door_x = self.dw / 2 + DOOR_FRAME       # structural opening half-width

    # ---------------------------------------------------------------- perimeter of the rounded body
    def perimeter(self, k=6):
        """Outer loop samples (x, y, nx, ny, s), CCW from the bottom-right corner arc's midpoint."""
        L, W, r = self.L, self.W, RC; pts = []
        corners = {'BR': (L / 2 - r, -W / 2 + r), 'TR': (L / 2 - r, W / 2 - r), 'TL': (-L / 2 + r, W / 2 - r), 'BL': (-L / 2 + r, -W / 2 + r)}

        def arc(c, a0, a1, n):
            return [(c[0] + r * math.cos(math.radians(a)), c[1] + r * math.sin(math.radians(a)), math.cos(math.radians(a)), math.sin(math.radians(a)))
                    for a in [a0 + (a1 - a0) * j / n for j in range(n)]]
        pts += arc(corners['BR'], -45, 0, k // 2)
        pts += [(L / 2, -W / 2 + r, 1, 0)]
        pts += arc(corners['TR'], 0, 90, k)
        pts += [(L / 2 - r, W / 2, 0, 1)]
        pts += arc(corners['TL'], 90, 180, k)
        pts += [(-L / 2, W / 2 - r, -1, 0)]
        pts += arc(corners['BL'], 180, 270, k)
        pts += [(-L / 2 + r, -W / 2, 0, -1)]
        pts += arc(corners['BR'], 270, 315, k // 2)
        # The flat sides' first samples above stand at the start of each side; insert the side ends explicitly so
        # each flat side is one straight segment between its two arc ends.
        out = []
        for i, q in enumerate(pts):
            out.append(q)
        s = 0.0; res = []
        for i, q in enumerate(out):
            if i:
                s += math.hypot(q[0] - out[i - 1][0], q[1] - out[i - 1][1])
            res.append((*q, s))
        close = math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1])
        return res, s + close

    def s_of(self, face, u):
        """Arc length of point u on a flat face ('door' = -y, 'back' = +y, 'east' = +x, 'west' = -x)."""
        per, _ = self.perimeter(); L, W, r = self.L, self.W, RC
        start = {'east': (L / 2, -W / 2 + r), 'back': (L / 2 - r, W / 2), 'west': (-L / 2, W / 2 - r), 'door': (-L / 2 + r, -W / 2)}[face]
        s0 = next(q[4] for q in per if abs(q[0] - start[0]) < 1e-9 and abs(q[1] - start[1]) < 1e-9)
        base = {'east': -W / 2 + r, 'back': L / 2 - r, 'west': W / 2 - r, 'door': -L / 2 + r}[face]
        sign = {'east': 1, 'back': -1, 'west': -1, 'door': 1}[face]
        return s0 + sign * (u - base)

    def subpath(self, sa, sb, inset0=0.0, inset1=T):
        per, total = self.perimeter()
        ring = per + [(*per[0][:4], total)]

        def interp(s):
            for a, b in zip(ring[:-1], ring[1:]):
                if a[4] <= s <= b[4] + 1e-12:
                    t = 0.0 if b[4] == a[4] else (s - a[4]) / (b[4] - a[4])
                    x = a[0] + t * (b[0] - a[0]); y = a[1] + t * (b[1] - a[1])
                    nx, ny = (a[2], a[3]) if t < 1 else (b[2], b[3])
                    if a[2:4] != b[2:4] and 0 < t < 1:   # inside an arc chord: interpolate the normal
                        nx = a[2] + t * (b[2] - a[2]); ny = a[3] + t * (b[3] - a[3]); ln = math.hypot(nx, ny); nx, ny = nx / ln, ny / ln
                    return x, y, nx, ny
            raise ValueError(s)
        samples = [interp(sa)] + [q[:4] for q in ring if sa + 1e-9 < q[4] < sb - 1e-9] + [interp(sb)]
        outer = [(x - inset0 * nx, y - inset0 * ny) for x, y, nx, ny in samples]
        inner = [(x - inset1 * nx, y - inset1 * ny) for x, y, nx, ny in samples]
        return outer, inner

    def openings(self, z0, z1):
        """Perimeter s-intervals that are open between heights z0 and z1."""
        out = []
        if z1 <= self.dh + 0.03 + 1e-9:                            # the door opening runs 3 cm into the head gasket
            out.append((self.s_of('door', -self.door_x), self.s_of('door', self.door_x)))
        if z0 >= SILL - 1e-9 and z1 <= HEAD + 1e-9:                # windows
            for face, a, b in self.windows():
                sa, sb = sorted((self.s_of(face, a), self.s_of(face, b)))
                out.append((sa, sb))
        return sorted(out)

    def windows(self):
        L, W, r = self.L, self.W, RC; dx = self.door_x; post = 0.08
        e = 0.04                                   # corner post beyond the arc
        return [('east', -(W / 2 - r) + e, (W / 2 - r) - e), ('west', -(W / 2 - r) + e, (W / 2 - r) - e),
                ('back', -(L / 2 - r) + e, (L / 2 - r) - e),
                ('door', dx + post, (L / 2 - r) - e), ('door', -((L / 2 - r) - e), -(dx + post))]

    def wall_band(self, m, z0, z1, mat=PANEL):
        per, total = self.perimeter(); ops = self.openings(z0, z1)
        if not ops:
            outer = [(q[0], q[1]) for q in per]; inner = [(q[0] - T * q[2], q[1] - T * q[3]) for q in per]
            m.ring_prism(outer, inner, z0, z1, mat); return
        cuts = [(ops[i][1], ops[(i + 1) % len(ops)][0] + (total if i == len(ops) - 1 else 0)) for i in range(len(ops))]
        for sa, sb in cuts:
            if sb > total:     # the segment wrapping past the loop start: split at s = total
                for a, b in ((sa, total), (0.0, sb - total)):
                    if b - a > 1e-6:
                        o, i_ = self.subpath(a, b); m.band(o, i_, z0, z1, mat)
            else:
                o, i_ = self.subpath(sa, sb); m.band(o, i_, z0, z1, mat)

    def face_frame(self, face, u, z):
        """Wall frame (x along the face, y up, z out) at point u on a flat face, centred in the wall thickness."""
        L, W = self.L, self.W
        if face == 'east':
            return (L / 2 - T / 2, u, z), (1, 0)
        if face == 'west':
            return (-L / 2 + T / 2, u, z), (-1, 0)
        if face == 'back':
            return (u, W / 2 - T / 2, z), (0, 1)
        return (u, -W / 2 + T / 2, z), (0, -1)

    # ---------------------------------------------------------------- body
    def body(self, m):
        L, W = self.L, self.W
        # Floor slab: chamfered underside, planked top (the interior floor).
        rings = []
        for z, ins in ((-self.p['cabin_floor_depth'], 0.12), (-0.16, 0.05), (-0.12, 0.0)):
            rr = rounded_rect(L - 2 * ins, W - 2 * ins, RC - ins, 6)
            rings.append([(x, y, z) for x, y in rr])
        with m.tagged('slab'):
            m.loft(rings, TIMBER)
            m.prism(rounded_rect(L, W, RC, 6), -0.12, -FLOOR_BOARD, TIMBER, top=TIMBER_DARK)
        # Dark iron skirt round the bottom.
        m.ring_prism(rounded_rect(L + 0.03, W + 0.03, RC + 0.015, 6), rounded_rect(L - 0.06, W - 0.06, RC - 0.03, 6), -0.135, -0.015, IRON)
        # Walls in four bands: below the sills, the window posts, above the windows, and a closed top band.
        self.wall_band(m, -FLOOR_BOARD, SILL)
        self.wall_band(m, SILL, HEAD)
        self.wall_band(m, HEAD, self.dh + 0.03)
        self.wall_band(m, self.dh + 0.03, WALL_TOP)
        # Roof cap with a rounded crown (its underside is the ceiling), a planked deck and steel corner caps.
        rings = []
        for z, ins in ((WALL_TOP, 0.0), (2.165, 0.02), (2.205, 0.06), (2.237, 0.11), (CAP_TOP, 0.165)):
            rr = rounded_rect(L - 2 * ins, W - 2 * ins, RC - ins, 6)
            rings.append([(x, y, z) for x, y in rr])
        with m.tagged('cap'):
            m.loft(rings, TIMBER)
        hx, hy = L / 2 - 0.18, W / 2 - 0.18; n = 5; gap = 0.01; bw = (2 * hy - (n - 1) * gap) / n
        with m.tagged('deck'):
            for k in range(n):
                y0 = -hy + k * (bw + gap)
                m.box((0, y0 + bw / 2, (CAP_TOP + self.deck_top) / 2), (2 * hx, bw, self.deck_top - CAP_TOP), PLANK)
                for sx in (-1, 1):
                    self.seat('roof deck board', sx * (hx - 0.02), y0 + bw / 2, CAP_TOP, on=('cap',))
        for sx in (-1, 1):
            for sy in (-1, 1):
                m.box((sx * (hx - 0.05), sy * (hy - 0.05), self.deck_top + 0.02), (0.13, 0.13, 0.04), STEEL, bevel=0.012)
                self.seat('roof corner cap', sx * (hx - 0.05), sy * (hy - 0.05), self.deck_top, on=('deck',))
        # Windows: dark rounded gaskets proud of both wall faces, glass in the middle of the wall.
        for face, a, b in self.windows():
            w = b - a; h = HEAD - SILL; c, nrm = self.face_frame(face, (a + b) / 2, (SILL + HEAD) / 2)
            with m.wall(c, nrm):
                m.ring_prism(rounded_rect(w + 0.1, h + 0.1, 0.13, 4), rounded_rect(w - 0.05, h - 0.05, 0.09, 4), -T / 2 - 0.016, T / 2 + 0.016, GASKET)
                m.box((0, 0, 0), (w + 0.03, h + 0.03, 0.016), GLASS)
        # Door frame: gasket jambs and head round the clear opening, steel threshold plate.
        c, nrm = self.face_frame('door', 0.0, 0.0)
        dx, fw = self.door_x, DOOR_FRAME
        with m.wall(c, nrm):
            for s in (-1, 1):
                m.box((s * (dx - fw / 2 + 0.02), (self.dh - FLOOR_BOARD - 0.005) / 2, 0), (fw + 0.04, self.dh + FLOOR_BOARD + 0.005, T + 0.026), GASKET)
            m.box((0, self.dh + 0.03, 0), (2 * dx + 0.04, 0.06, T + 0.026), GASKET)
        m.prism(rect(-self.dw / 2, -W / 2 - 0.02, self.dw / 2, -W / 2 + T), -FLOOR_BOARD, 0.004, STEEL)
        self.seat('threshold plate', 0.0, -W / 2 + T / 2, -FLOOR_BOARD, on=('slab',))
        # The wall planks (10 cm, horizontal, with dark seams) are in the GD_TimberPanel texture.
        # Dark iron trims over the four rounded corners and round the roof edge, with bolt rows.
        corners = ((L / 2 - RC, -W / 2 + RC, -90), (L / 2 - RC, W / 2 - RC, 0), (-L / 2 + RC, W / 2 - RC, 90), (-L / 2 + RC, -W / 2 + RC, 180))
        for cx, cy, a0 in corners:
            angs = [math.radians(a0 + 27 + 36 * k / 4) for k in range(5)]
            outer = [(cx + (RC + 0.008) * math.cos(t), cy + (RC + 0.008) * math.sin(t)) for t in angs]
            inner = [(cx + (RC - 0.012) * math.cos(t), cy + (RC - 0.012) * math.sin(t)) for t in angs]
            m.band(outer, inner, -0.015, WALL_TOP - 0.045, IRON)
            nx, ny = math.cos(math.radians(a0 + 45)), math.sin(math.radians(a0 + 45))
            for z in (0.1, 0.5, 0.9, 1.3, 1.7):
                p = (cx + (RC + 0.008) * nx, cy + (RC + 0.008) * ny, z)
                with m.wall(p, (nx, ny)):
                    m.box((0, 0, 0.004), (0.04, 0.04, 0.016), BOLT)
        m.ring_prism(rounded_rect(L + 0.02, W + 0.02, RC + 0.01, 6), rounded_rect(L - 0.04, W - 0.04, RC - 0.02, 6), WALL_TOP - 0.045, WALL_TOP + 0.015, IRON)
        for face, width in (('east', W - 2 * RC), ('west', W - 2 * RC), ('back', L - 2 * RC), ('door', L - 2 * RC)):
            n = max(2, int(width / 0.36))
            for k in range(n + 1):
                u = -width / 2 + width * k / n
                if face == 'door' and abs(u) < dx + 0.06:
                    continue
                c, nrm = self.face_frame(face, u, WALL_TOP - 0.015)
                with m.wall(c, nrm):
                    m.box((0, 0, T / 2 + 0.016), (0.035, 0.035, 0.014), BOLT)

    def interior(self, m):
        L, W = self.L, self.W; xi, yi = L / 2 - T, W / 2 - T
        clip = rounded_rect(2 * xi, 2 * yi, RC - T, 6)
        xb = xi - SEAT_D; yb = yi - SEAT_D
        benches = {'east bench': rect(xb, -yi, xi, yi), 'west bench': rect(-xi, -yi, -xb, yi), 'back bench': rect(-xb, yb, xb, yi)}
        for label, poly in benches.items():
            poly = clip_convex(poly, clip)
            x0 = min(p[0] for p in poly); x1 = max(p[0] for p in poly); y0 = min(p[1] for p in poly); y1 = max(p[1] for p in poly)
            # Three seat boards along the bench with 15 mm gaps, a front apron, two backrest boards, dark pedestals.
            gap = 0.015
            if label == 'back bench':
                bw = (y1 - y0 - 2 * gap) / 3
                strips = [rect(x0, y0 + k * (bw + gap), x1, y0 + k * (bw + gap) + bw) for k in range(3)]
                front = rect(x0, y0, x1, y0 + 0.05)
                backs = [clip_convex(rect(x0, yi - 0.05, x1, yi), clip)]
                legs = [((x0 + 0.25, y0 + 0.22)), ((x1 - 0.25, y0 + 0.22))]; leg_s = (0.08, 0.3)
            else:
                sgn = 1 if x0 > 0 else -1
                bw = (x1 - x0 - 2 * gap) / 3
                strips = [rect(x0 + k * (bw + gap), y0, x0 + k * (bw + gap) + bw, y1) for k in range(3)]
                front = rect(x0, y0, x0 + 0.05, y1) if sgn > 0 else rect(x1 - 0.05, y0, x1, y1)
                backs = [clip_convex(rect(xi - 0.05, y0, xi, y1) if sgn > 0 else rect(-xi, y0, -xi + 0.05, y1), clip)]
                xm = (x0 + x1) / 2
                legs = [(xm, -yi + 0.45), (xm, yi - 0.55)]; leg_s = (0.3, 0.08)
            with m.grained((1, 0, 0) if label == 'back bench' else (0, 1, 0)):
                for st in strips:
                    m.prism(clip_convex(st, poly), SEAT_H - 0.06, SEAT_H, PLANK, bevel=0.008)
            m.prism(clip_convex(front, clip), SEAT_H - 0.2, SEAT_H - 0.06, TIMBER)
            for bk in backs:
                m.prism(bk, SEAT_H + 0.07, SEAT_H + 0.17, PLANK, bevel=0.006)
                m.prism(bk, SEAT_H + 0.19, SILL - 0.01, PLANK, bevel=0.006)
            for lx, ly in legs:
                m.box((lx, ly, (SEAT_H - 0.06) / 2), (*leg_s, SEAT_H - 0.06), IRON)
                for dx_, dy_ in ((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)):
                    self.seat(label + ' pedestal', lx + dx_ * leg_s[0], ly + dy_ * leg_s[1], 0.0, on=('floor',))
        # Floor boards along the cabin (x) with dark seams, and a chamfered cove round the ceiling.
        n = 13; gap = 0.008; bw = (2 * yi - (n - 1) * gap) / n
        with m.tagged('floor'):
            for k in range(n):
                y0 = -yi + k * (bw + gap)
                m.prism(clip_convex(rect(-xi, y0, xi, y0 + bw), clip), -FLOOR_BOARD, 0.0, PLANK)
        per, total = self.perimeter(k=6)
        sec = []
        for x, y, nx, ny, _s in per:
            ix, iy = x - T * nx, y - T * ny
            sec.append([(ix, iy, COVE_Z), (ix - COVE_IN * nx, iy - COVE_IN * ny, WALL_TOP), (ix, iy, WALL_TOP)])
        verts = [v for tri in sec for v in tri]; faces = []; N = len(sec)
        for i in range(N):
            j = (i + 1) % N
            for a_, b_ in ((0, 1), (1, 2), (2, 0)):
                faces.append([3 * i + a_, 3 * j + a_, 3 * j + b_, 3 * i + b_])
        m.part(verts, faces, TIMBER)
        # Ceiling board seams and a small inset light near the -x end.
        for y in (-0.62, -0.31, 0.31, 0.62):
            m.box((0, y, WALL_TOP - 0.004), (2 * (xi - COVE_IN) - 0.02, 0.012, 0.008), TIMBER_DARK)
        m.box((-0.62, 0.0, WALL_TOP - 0.009), (0.09, 0.32, 0.018), IRON)
        m.box((-0.62, 0.0, WALL_TOP - 0.0185), (0.06, 0.28, 0.003), LAMP)

    def hanger(self, gm, m):
        """The detachable grip and the hanger (export coordinates; the rope axis is the x axis).

        Grip (monocable detachable): a clamp housing about 0.45 m long and 0.30 m tall straddles the rope. It is a
        top body over the rope between two bolted side plates; the rope runs between the side plates. Inside, a fixed
        jaw (inner side, +y) and a movable jaw (outer, door side, -y) close on the rope from above: their grooves are
        arcs of the rope radius about the rope axis, so the rope sits fully seated and coaxial. Below the rope the
        housing is open, so the tower sheaves and the bullwheel liner run under the rope between the side plates.
        Two large running wheels, one at each end of the housing, on axles across the rope, 0.30 m outboard and with
        their centres 0.16 m above the rope axis (their treads come down to the rope axis height, never to the rope):
        they roll on the station rail (stations.py) after the jaws open; on the line they touch nothing.
        Pivot: a lug under the outer side plate carries a pin across the rope (along y). The grip (mesh gm) follows the
        rope's tangent; the hanger and the cabin (mesh m and the body) hang plumb from the pin, so the floor stays level
        on every grade (cabin.pose, rope.hang_frame).
        Hanger: a chamfered rectangular post from a bolted base plate on the roof, rising nearly vertically, with one
        dogleg 40 % of the way up, ending in a round boss on the pivot pin, outboard of the rope (it never crosses it).
        Load path: rope -> jaws -> housing -> pivot pin -> hanger -> cabin roof.
        """
        z_deck = -self.p['hanger_length']; rr = self.p['rope_radius']
        g = GRIP; L = g['housing_length']; hx = L / 2
        py0, py1 = g['plate_y']; pz0, pz1 = g['plate_z']; jt = rr + g['jaw_cover']; jw = py0 - 0.002
        # Roof mount: base plate and pedestal, bolted.
        m.box((0, -0.03, z_deck + 0.04), (0.62, 0.46, 0.08), STEEL, bevel=0.02)
        m.box((0, -0.03, z_deck + 0.12), (0.34, 0.26, 0.09), STEEL, bevel=0.02)
        for sx in (-1, 1):
            for sy in (-1, 1):
                m.lathe((sx * 0.24, -0.03 + sy * 0.17, z_deck + 0.075), [(0, 0.026), (0.018, 0.026), (0.026, 0.0)], BOLT, n=6)
        self.seat_abs('hanger base plate', 0.0, -0.03, z_deck, on=('deck',))
        # Jaws: (y, z) profiles extruded along the rope, grooves of the rope radius.
        self.groove = []
        arc = [math.radians(a) for a in range(0, 86, 5)] + [math.radians(86)]
        for side in (1, -1):                       # +1 fixed jaw (inner), -1 movable jaw (outer)
            groove = [(side * rr * math.cos(t), rr * math.sin(t)) for t in arc]
            prof = [(side * jw, 0.0), (side * jw, jt - 0.01), (side * (jw - 0.01), jt), (side * 0.003, jt)] + groove[::-1]
            with gm.frame((-(hx - 0.03), 0, 0), (0, 1, 0), (0, 0, 1), (1, 0, 0)), gm.tagged('jaw'):
                gm.prism(prof, 0.0, L - 0.06, IRON)
            for x in (-(hx - 0.03), 0.0, hx - 0.03):
                self.groove += [(x, y, z) for y, z in groove]
        # Housing: top body over the jaws, two side plates with chamfered ends, bolt heads on the plates.
        with gm.tagged('clamp'):
            gm.box((0, 0, (jt - 0.006 + pz1 - 0.01) / 2), (L - 0.02, 2 * py0 + 0.004, pz1 - 0.01 - jt + 0.006), STEEL, bevel=0.02)
        for sy in (-1, 1):
            yc = sy * (py0 + py1) / 2; t = py1 - py0
            ch = 0.05
            outline = [(-hx + ch, pz0), (hx - ch, pz0), (hx, pz0 + ch), (hx, pz1 - ch), (hx - ch, pz1), (-hx + ch, pz1), (-hx, pz1 - ch), (-hx, pz0 + ch)]
            with gm.frame((0, yc - t / 2, 0), (1, 0, 0), (0, 0, 1), (0, 1, 0)):
                gm.prism(outline, 0.0, t, STEEL)
            for x in (-hx + 0.06, -0.12, 0.12, hx - 0.06):
                for z in (pz0 + 0.045, pz1 - 0.045):
                    with gm.frame((x, sy * py1, z), (1, 0, 0), (0, 0, 1), (0, sy, 0)):
                        gm.lathe((0, 0, -0.004), [(0, 0.017), (0.014, 0.017), (0.02, 0.0)], BOLT, n=6)
        # Running wheels: large, grooved tyres, planes parallel to the rope, axles across it, outer side.
        wy, wr, ww, wz = g['wheel_y'], g['wheel_radius'], g['wheel_width'], g['wheel_z']
        for x in g['wheel_x']:
            with gm.tagged('wheel'):
                # Wheel arm: a bolted bar from the outer side plate out to the axle, which stands on it.
                sg = 1 if x > 0 else -1; xa, xb = hx - 0.03, abs(x) + 0.06
                gm.box((sg * (xa + xb) / 2, -(py1 + 0.015), wz), (xb - xa, 0.03, 0.09), STEEL, bevel=0.008)
                gm.lathe((x, -(py1 + 0.02), wz), [(0, 0.032), (-wy + ww / 2 + 0.02 - py1 - 0.02, 0.032)], STEEL, n=10, axis=(0, -1, 0))
                tyre = [(0, wr - 0.03), (0.01, wr), (0.024, wr), (0.031, wr - 0.014), (0.039, wr - 0.014), (0.046, wr), (0.06, wr), (ww, wr - 0.03)]
                gm.lathe((x, wy + ww / 2, wz), tyre, RUBBER, n=24, axis=(0, -1, 0))
                gm.lathe((x, wy + ww / 2 + 0.006, wz), [(0, wr - 0.045), (ww + 0.012, wr - 0.045)], STEEL, n=16, axis=(0, -1, 0))
                gm.lathe((x, wy - ww / 2 - 0.006, wz), [(0, 0.05), (0.02, 0.04), (0.03, 0.0)], IRON, n=8, axis=(0, -1, 0))
                for k in range(5):
                    a = 2 * math.pi * k / 5
                    gm.box((x + 0.07 * math.cos(a), wy - ww / 2 - 0.006, wz + 0.07 * math.sin(a)), (0.022, 0.012, 0.022), BOLT)
        # Hanger post: chamfered rectangular section, vertical, one dogleg (outward) 40 % up, into the outer plate.
        sx_, sy_, c = g['post_section'][0] / 2, g['post_section'][1] / 2, 0.02
        sect = [(sx_ - c, -sy_), (sx_, -sy_ + c), (sx_, sy_ - c), (sx_ - c, sy_), (-sx_ + c, sy_), (-sx_, sy_ - c), (-sx_, -sy_ + c), (-sx_ + c, -sy_)]
        yl, yu = g['post_y']; z0 = z_deck + 0.15; zd = z_deck + 0.4 * self.p['hanger_length']
        px, py, pz = g['pivot']
        rings = [[(x, y + yc, z) for x, y in sect] for yc, z in ((yl, z0), (yl, zd), (yu, zd + 0.16), (yu, pz))]
        m.loft(rings, STEEL)
        # Round boss on the post top, concentric with the pin, so the grip can pitch about it.
        m.lathe((px, yu + sy_ + 0.004, pz), [(0, sx_ + 0.006), (2 * sy_ + 0.008, sx_ + 0.006)], STEEL, n=16, axis=(0, -1, 0))
        # Lug under the outer side plate (inside the plate's faces where they overlap), pin and nut (grip side).
        gm.lathe((px, -py0 - 0.003, pz), [(0, 0.062), (py1 - py0 - 0.006, 0.062)], STEEL, n=16, axis=(0, -1, 0))
        # The pin starts inside the lug (nothing on the rope side); the nut stays 5 mm inside the station rail's edge.
        pin_y0, pin_y1 = -py0 - 0.006, yu - sy_ - 0.009
        gm.lathe((px, pin_y0, pz), [(0, 0.024), (pin_y0 - pin_y1, 0.024)], IRON, n=10, axis=(0, -1, 0))
        gm.lathe((px, pin_y1 + 0.007, pz), [(0, 0.042), (0.009, 0.042), (0.013, 0.0)], BOLT, n=6, axis=(0, -1, 0))
        # Joint plates and bolts at the post foot.
        for zj, yc, h in ((z0 + 0.11, yl, 0.2),):
            for sx in (-1, 1):
                m.box((sx * (sx_ + 0.008), yc, zj), (0.016, 2 * sy_ + 0.02, h), STEEL)
                for dz in (-h / 2 + 0.05, h / 2 - 0.05):
                    with m.frame((sx * (sx_ + 0.016), yc, zj + dz), (0, 1, 0), (0, 0, 1), (sx, 0, 0)):
                        m.lathe((0, 0, -0.004), [(0, 0.016), (0.012, 0.016), (0.018, 0.0)], BOLT, n=6)
        self.grip_info = {'jaw_groove_radius': rr, 'jaw_length': round(L - 0.06, 3), 'jaw_bottom_z': 0.0, 'housing': {'length': L, 'z': [pz0, pz1],
                          'side_plates_y': [py0, py1]},
                          'running_wheels': {'x': list(g['wheel_x']), 'y': wy, 'z': wz, 'radius': wr, 'width': ww,
                                             'bottom_z': round(wz - wr, 4), 'axle': [0, 1, 0]},
                          'hanger_post': {'section': list(g['post_section']), 'y_lower': yl, 'y_upper': yu, 'dogleg_z': round(zd, 3)},
                          'pivot': {'point': list(g['pivot']), 'axis': [0, 1, 0],
                                    'rule': 'the grip mesh follows the rope tangent (rope.grip_frame); the hanger, body and doors '
                                            'hang plumb from the pivot pin (rope.hang_frame: heading only, floor level)'},
                          'station_rail_top_z': round(wz - wr, 4)}

    def door_leaf(self, m, s):
        """One sliding leaf (s = -1 left, +1 right) in the closed pose, in the door opening."""
        W = self.W; half = self.dw / 2; gap = 0.003; leaf = half - gap * 1.5; h = self.dh - 0.012 - 0.01
        y = -W / 2 + T / 2; xc = s * (gap / 2 + leaf / 2)
        with m.wall((xc, y, 0.012), (0, -1)):
            m.box((0, 0.55 / 2, 0), (leaf - 0.12, 0.55, 0.05), PANEL)                        # lower panel
            with m.grained((0, 1, 0)):
                m.box((-leaf / 2 + 0.03, h / 2, 0), (0.06, h, 0.05), TIMBER)                 # stiles
                m.box((leaf / 2 - 0.03, h / 2, 0), (0.06, h, 0.05), TIMBER)
            m.box((0, h - 0.04, 0), (leaf - 0.12, 0.08, 0.05), TIMBER)                        # top rail
            m.box((0, (0.55 + h - 0.08) / 2, 0), (leaf - 0.12, h - 0.08 - 0.55, 0.016), GLASS)
            edge = -s
            m.box((edge * (leaf / 2 - 0.012), h / 2, 0), (0.016, h - 0.004, 0.056), RUBBER)  # meeting-edge seal
            if s > 0:
                m.box((-leaf / 2 + 0.03, 1.0, 0.04), (0.03, 0.42, 0.03), IRON)               # pull handle
        return leaf

    # ---------------------------------------------------------------- registries
    # ---------------------------------------------------------------- registries
    def seat(self, label, x, y, z, embed=0.0, probe=0.15, on=('floor',)):
        self.seats.append((label, round(x, 4), round(y, 4), round(z - self.G, 4), embed, probe, on))

    def seat_abs(self, label, x, y, z, embed=0.0, probe=0.15, on=('deck',)):
        self.seats.append((label, round(x, 4), round(y, 4), round(z, 4), embed, probe, on))

    def build(self):
        body, hanger, grip = Mesh('GD_Cabin'), Mesh('GD_CabinHanger'), Mesh('GD_CabinGrip')
        left, right = Mesh('GD_CabinDoorLeft'), Mesh('GD_CabinDoorRight')
        with body.at((0, 0, -self.G)):
            self.body(body); self.interior(body)
        self.hanger(grip, hanger)
        with left.at((0, 0, -self.G)):
            leaf = self.door_leaf(left, -1)
        with right.at((0, 0, -self.G)):
            self.door_leaf(right, 1)
        info = {'leaves': ['GD_CabinDoorLeft', 'GD_CabinDoorRight'], 'leaf_width': round(leaf, 3),
                'open_offsets': {'GD_CabinDoorLeft': [-round(leaf + 0.03, 3), -0.06, 0.0], 'GD_CabinDoorRight': [round(leaf + 0.03, 3), -0.06, 0.0]},
                'motion': 'each leaf moves 6 cm out, then slides away from the centre along the outside of the door wall'}
        self.door_info = info
        return {'GD_Cabin': body, 'GD_CabinHanger': hanger, 'GD_CabinGrip': grip, 'GD_CabinDoorLeft': left, 'GD_CabinDoorRight': right}, info

    def open_doors(self, meshes):
        """Copies of the two leaves in the open pose."""
        from solid import transformed
        o = self.door_info['open_offsets']
        return [transformed(meshes[k], Matrix.Translation(v), k + 'Open') for k, v in o.items()]

    # ---------------------------------------------------------------- collision and walk layout (export coordinates)
    def proxies(self):
        from solid import proxy, proxy_box, proxy_strip
        L, W, G = self.L, self.W, self.G; zf = -G; P = []
        P.append(proxy('cabin floor', rounded_rect(L, W, RC, 3), zf - self.p['cabin_floor_depth'], zf))
        per, total = self.perimeter(k=4)
        ring = per + [per[0]]
        for a, b in zip(ring[:-1], ring[1:]):
            if a[3] == -1 and b[3] == -1 and abs(a[1] + W / 2) < 1e-9:      # the door side: built below
                continue
            ia = (a[0] - T / 2 * a[2], a[1] - T / 2 * a[3]); ib = (b[0] - T / 2 * b[2], b[1] - T / 2 * b[3])
            P.append(proxy_strip('cabin wall', ia, ib, T + 0.03, zf, zf + WALL_TOP))
        yd = -W / 2 + T / 2
        for s in (-1, 1):
            P.append(proxy_strip('cabin wall', (s * (self.dw / 2 + 0.12), yd), (s * (L / 2 - RC), yd), T + 0.03, zf, zf + WALL_TOP))
        # Door jambs (to the clear opening) and the head.
        dx = self.dw / 2
        for s in (-1, 1):
            P.append(proxy_box('cabin door jamb', s * (dx + 0.06), -W / 2 + T / 2, 0.12, T + 0.04, zf, zf + WALL_TOP))
        P.append(proxy_box('cabin door head', 0, -W / 2 + T / 2, 2 * dx + 0.24, T + 0.04, zf + self.dh, zf + WALL_TOP))
        P.append(proxy('cabin roof', rounded_rect(L, W, RC, 3), zf + WALL_TOP, zf + self.deck_top))
        xi, yi = L / 2 - T, W / 2 - T; xb = xi - SEAT_D; yb = yi - SEAT_D
        P.append(proxy('cabin bench', rect(xb, -yi, xi, yi), zf, zf + SEAT_H))
        P.append(proxy('cabin bench', rect(-xi, -yi, -xb, yi), zf, zf + SEAT_H))
        P.append(proxy('cabin bench', rect(-xb, yb, xb, yi), zf, zf + SEAT_H))
        P.append(proxy_box('hanger', 0, -0.2, 0.3, 0.6, zf + self.deck_top, 0.18))
        return P

    def layout(self):
        L, W = self.L, self.W; xi, yi = L / 2 - T, W / 2 - T
        return {'floor_z': -self.G, 'interior': [list(p) for p in rounded_rect(2 * xi, 2 * yi, RC - T, 4)],
                'door': {'x': [-self.dw / 2, self.dw / 2], 'y_outer': -W / 2, 'y_inner': -W / 2 + T, 'clear_height': self.dh},
                'benches': {'east': [xi - SEAT_D, xi], 'west': [-xi, -xi + SEAT_D], 'back_y': [yi - SEAT_D, yi], 'seat_height': SEAT_H},
                'headroom': WALL_TOP - 0.04}


def clip_convex(poly, clip):
    """Sutherland-Hodgman: poly (any) clipped by a convex CCW polygon."""
    out = list(poly)
    if signed_area(out) < 0:
        out = out[::-1]
    for i in range(len(clip)):
        a, b = clip[i], clip[(i + 1) % len(clip)]; inp = out; out = []
        if not inp:
            break
        for j in range(len(inp)):
            p, q = inp[j], inp[(j + 1) % len(inp)]
            sp = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
            sq = (b[0] - a[0]) * (q[1] - a[1]) - (b[1] - a[1]) * (q[0] - a[0])
            if sp >= 0:
                out.append(p)
            if (sp >= 0) != (sq >= 0):
                t = sp / (sp - sq); out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    # Drop near-duplicate points.
    res = []
    for p in out:
        if not res or math.hypot(p[0] - res[-1][0], p[1] - res[-1][1]) > 1e-5:
            res.append(p)
    if len(res) > 1 and math.hypot(res[0][0] - res[-1][0], res[0][1] - res[-1][1]) < 1e-5:
        res.pop()
    return res


def fillet(path, r, seg):
    """Round the interior corners of a 3D polyline with circular arcs."""
    P = [Vector(p) for p in path]; out = [P[0]]
    for i in range(1, len(P) - 1):
        a, b, c = P[i - 1], P[i], P[i + 1]
        u = (a - b).normalized(); v = (c - b).normalized()
        ang = math.acos(max(-1.0, min(1.0, u.dot(v))))
        if ang > math.pi - 1e-3:
            out.append(b); continue
        t = r / math.tan(ang / 2); t = min(t, (a - b).length * 0.45, (c - b).length * 0.45)
        p0 = b + u * t; p1 = b + v * t
        for k in range(seg + 1):
            s = k / seg
            q = (1 - s) ** 2 * p0 + 2 * (1 - s) * s * b + s * s * p1     # quadratic Bezier through the corner
            out.append(q)
    out.append(P[-1])
    return [tuple(p) for p in out]


def solid_profile(length, zb, zt):
    """A side plate outline in a wall frame (x along, y up): rounded ends, from zb to zt."""
    h = zt - zb; r = h / 2; pts = []
    for cx, a0 in ((length / 2 - r, -90), (-length / 2 + r, 90)):
        for k in range(7):
            a = math.radians(a0 + 180 * k / 6)
            pts.append((cx + r * math.cos(a), zb + r + r * math.sin(a)))
    return pts
