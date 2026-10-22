"""Gondola support tower (gondola_tower_pylon.jpg): a tapered four-legged timber lattice with X-braced panels and
steel gusset straps, a doubled timber crossarm with steel knee braces and timber head posts, a sheave train under
each haul rope, a service ladder and landing, four concrete pedestals in a ring of rubble stones, and four guy wires
to concrete anchor blocks.

Tower frame: the origin is the foundation datum on the tower axis (the ground there), +x runs along the line, z is
up. The two haul ropes pass at y = +-gauge/2 with their axes at z = height (the rope saddle). The tower is wider
along the line than across it, as in the painting's two elevations. Everything that a passing cabin could meet stays
inside |y| <= gauge/2 - 1.05 below the cabin roof line, and the head keeps the sheave trains' outer side clear for the
hanger (checked by build.py with the real cabin).
"""
import math

from mathutils import Vector

from checks import TOWER_BODY_MARGIN
from solid import (CONCRETE, IRON, STEEL, STONE, TIMBER, Mesh, proxy_box)

LEG = 0.30
HX_TOP, HY_TOP = 0.85, 0.62        # leg centreline half-widths at the cap
BX, BY = 0.075, 0.060              # batter of the leg centrelines (per metre of height)
GUY_SPREAD = 0.13                   # guy anchors this far (x H) beyond the leg feet, along the line
LEG_FOOT = 0.70                    # leg bottoms stand on steel shoes on the pedestals
GIRT_H, GIRT_D = 0.20, 0.16
BRACE_W, BRACE_D = 0.15, 0.08
SHEAVE_R = 0.24                    # groove radius (the rope rests on it)
SHEAVE_X = (-1.35, -0.6, 0.6, 1.35)


class Tower:
    def __init__(self, p, height, ground=None, ground_bounds=None, saddle=None):
        self.ground = ground
        self.ground_bounds = ground_bounds
        # saddle: {m_in, m_out, half} from the fitted line. None keeps the
        # standalone kit's level shave train (build.py's tower review).
        self.saddle = saddle
        if ground is not None and ground_bounds is None:
            raise ValueError('Placed tower requires complete footing coverage/relief')
        self.pedestal_bases = {}
        self.anchor_bounds = {}
        self.p = p; self.H = float(height); self.g = p['gauge']; self.rr = p['rope_radius']
        self.z_cap = self.H - 0.89
        self.seats = []
        span = self.z_cap - 0.95
        n = min(8, max(4, round(2 + span / 3.6))); q = 1.12
        h0 = span * (q - 1) / (q ** n - 1)
        z = self.z_cap; self.levels = [z]
        for i in range(n):
            z -= h0 * q ** i; self.levels.append(z)
        self.levels[-1] = 0.95

    def ground_z(self, x, y):
        """World placement supplies final contact relative to the foundation datum."""
        z = 0.0 if self.ground is None else float(self.ground(x, y))
        if not math.isfinite(z):
            raise ValueError('Tower foundation has no finite final ground contact')
        return z

    def hx(self, z):
        return HX_TOP + BX * (self.z_cap - z)

    def hy(self, z):
        return HY_TOP + BY * (self.z_cap - z)

    def leg_pt(self, sx, sy, z):
        return Vector((sx * self.hx(z), sy * self.hy(z), z))

    def seat(self, label, x, y, z, embed=0.0, probe=0.15, on=('girt',)):
        self.seats.append((label, round(x, 4), round(y, 4), round(z, 4), embed, probe, tuple(on)))

    # ---------------------------------------------------------------- shaft
    def legs(self, m):
        for sx in (-1, 1):
            for sy in (-1, 1):
                rings = []
                for z in (LEG_FOOT, self.z_cap + 0.06):
                    c = self.leg_pt(sx, sy, z)
                    rings.append([(c.x + u, c.y + v, z) for u, v in ((-LEG / 2, -LEG / 2), (LEG / 2, -LEG / 2), (LEG / 2, LEG / 2), (-LEG / 2, LEG / 2))])
                with m.tagged('leg'):
                    m.loft(rings, TIMBER)
                c = self.leg_pt(sx, sy, self.z_cap + 0.06)
                m.box((c.x, c.y, self.z_cap + 0.075), (LEG + 0.04, LEG + 0.04, 0.03), IRON)
                self.seat('leg cap', c.x, c.y, self.z_cap + 0.06, on=('leg',))

    def girts(self, m):
        for i, z in enumerate(self.levels):
            zc = z - GIRT_H / 2 if i == 0 else z
            hx, hy = self.hx(zc), self.hy(zc); e = LEG / 2 - 0.02
            with m.tagged('girt'):
                for s in (-1, 1):
                    m.box((s * hx, 0, zc), (GIRT_D, 2 * (hy - e), GIRT_H), TIMBER)      # x faces (girts along y)
                    m.box((0, s * hy, zc), (2 * (hx - e), GIRT_D, GIRT_H), TIMBER)      # y faces (girts along x)

    def braces(self, m):
        for i in range(len(self.levels) - 1):
            za = self.levels[i] - (GIRT_H if i == 0 else GIRT_H / 2)
            zb = self.levels[i + 1] + GIRT_H / 2
            for face in ('x', 'y'):
                for s in (-1, 1):
                    for k, (u0, u1) in enumerate(((-1, 1), (1, -1))):
                        off = 0.045 if k == 0 else -0.045
                        if face == 'x':
                            a = Vector((s * (self.hx(za) + off), u0 * (self.hy(za) - LEG / 2), za))
                            b = Vector((s * (self.hx(zb) + off), u1 * (self.hy(zb) - LEG / 2), zb))
                            up = (1, 0, 0)
                        else:
                            a = Vector((u0 * (self.hx(za) - LEG / 2), s * (self.hy(za) + off), za))
                            b = Vector((u1 * (self.hx(zb) - LEG / 2), s * (self.hy(zb) + off), zb))
                            up = (0, 1, 0)
                        d = (b - a).normalized()
                        m.beam(a - d * 0.04, b + d * 0.04, BRACE_W, BRACE_D, TIMBER, up=up)

    def straps(self, m):
        """Dark steel gusset straps on both outer faces of every leg at every girt level."""
        for i, z in enumerate(self.levels):
            zc = z - GIRT_H / 2 if i == 0 else z
            for sx in (-1, 1):
                for sy in (-1, 1):
                    c = self.leg_pt(sx, sy, zc)
                    for axis in ('x', 'y'):
                        if axis == 'x':
                            nrm = Vector((sx * 1.0, 0, BX)).normalized()
                            base = c + Vector((sx * LEG / 2, 0, 0))
                        else:
                            nrm = Vector((0, sy * 1.0, BY)).normalized()
                            base = c + Vector((0, sy * LEG / 2, 0))
                        V = Vector((0, 0, 1)); V = (V - nrm * V.dot(nrm)).normalized(); U = V.cross(nrm)
                        with m.frame(base, U, V, nrm):
                            m.box((0, 0, 0.006), (LEG - 0.03, 0.44, 0.012), IRON)

    # ---------------------------------------------------------------- foundation
    def foundation(self, m):
        for sx in (-1, 1):
            for sy in (-1, 1):
                c = self.leg_pt(sx, sy, LEG_FOOT)
                base = -1.0
                if self.ground is not None:
                    heights = self.ground_bounds([(c.x+u*.5,c.y+v*.5) for u,v in ((-1,-1),(1,-1),(1,1),(-1,1))])
                    if max(heights) > .52:
                        raise ValueError('Tower datum buries a pedestal shoe')
                    base = min(heights)-.20
                self.pedestal_bases[(sx,sy)] = base
                rings = [[(c.x + u * s, c.y + v * s, z) for u, v in ((-.5, -.5), (.5, -.5), (.5, .5), (-.5, .5))] for z, s in ((base, 1.0), (0.62, 0.64))]
                with m.tagged('pedestal'):
                    m.loft(rings, CONCRETE)
                with m.tagged('shoe'):
                    m.box((c.x, c.y, 0.66), (0.46, 0.46, 0.08), IRON)
                for u in (-1, 1):
                    for v in (-1, 1):
                        self.seat('leg shoe', c.x + u * 0.2, c.y + v * 0.2, 0.62, on=('pedestal',))
                        self.seat('leg foot', c.x + u * (LEG / 2 - 0.02), c.y + v * (LEG / 2 - 0.02), LEG_FOOT, on=('shoe',))
                # Rubble stones round the pedestal, half buried (ground datum z = 0).
                for k in range(3):
                    a = math.radians(45 * (sx + 2) + 120 * k + 17 * sy); r = 0.8
                    size = (0.26 + 0.05 * ((k * 7) % 3), 0.22 + 0.04 * (k % 2), 0.2)
                    m.rock((c.x + r * math.cos(a), c.y + r * math.sin(a), self.ground_z(c.x+r*math.cos(a),c.y+r*math.sin(a)) + 0.04), size, STONE, seed=int(100 * self.H) + 10 * k + 3 * sx + sy, n=4, m=3)

    def guys(self, m):
        """Four guy wires along the line from the legs to concrete anchors, with turnbuckles."""
        zg = min(self.levels[:-1], key=lambda z: abs(z - 0.72 * self.z_cap))
        for sx in (-1, 1):
            for sy in (-1, 1):
                top = self.leg_pt(sx, sy, zg) + Vector((sx * (LEG / 2 + 0.015), 0, 0))
                ax = sx * (self.hx(0) + GUY_SPREAD * self.H); ay = sy * self.hy(LEG_FOOT)
                ground,base = 0.,-.9
                if self.ground is not None:
                    heights = self.ground_bounds([(ax+u*.45,ay+v*.45) for u,v in ((-1,-1),(1,-1),(1,1),(-1,1))])
                    ground,base = max(heights)-.27,min(heights)-.20
                self.anchor_bounds[(sx,sy)] = (base,ground+.55)
                rings = [[(ax + u * s, ay + v * s, z) for u, v in ((-.5, -.5), (.5, -.5), (.5, .5), (-.5, .5))] for z, s in ((base, 0.9), (ground+0.45, 0.55))]
                with m.tagged('anchor'):
                    m.loft(rings, CONCRETE)
                eye = Vector((ax, ay, ground+0.53))
                m.box((ax, ay, ground+0.47), (0.2, 0.08, 0.04), IRON)
                self.seat('guy anchor plate', ax, ay, ground+0.45, on=('anchor',))
                m.lathe((ax, ay, ground+0.49), [(0, 0.03), (0.08, 0.03)], IRON, n=4)
                d = (top - eye).normalized()
                tb0 = eye + d * 0.5; tb1 = eye + d * 0.95
                m.tube([eye, tb0], 0.014, IRON, n=4)
                m.tube([tb0 - d * 0.02, tb1 + d * 0.02], [0.03, 0.03], IRON, n=4)
                m.tube([tb1, top], 0.012, IRON, n=4)
                # Lug on the leg.
                with m.frame(top - Vector((sx * 0.015, 0, 0)), Vector((0, sx, 0)), Vector((0, 0, 1)), Vector((sx, 0, 0))):
                    m.box((0, 0, 0.01), (0.14, 0.2, 0.02), IRON)
                for k, (dx, dy) in enumerate(((0.55, 0.2), (-0.45, -0.4))):
                    m.rock((ax + dx, ay + dy, self.ground_z(ax+dx,ay+dy)+0.03), (0.2, 0.17, 0.16), STONE, seed=int(10 * self.H) + 50 + k + 7 * sx + 3 * sy, n=5, m=3)

    # ---------------------------------------------------------------- head
    def head(self, m):
        H, g, zc = self.H, self.g, self.z_cap
        ya = g / 2 - 0.12                      # crossarm ends stay inside the hanger's path
        with m.tagged('crossarm'):
            for s in (-1, 1):
                m.box((s * 0.32, 0, zc + 0.17), (0.24, 2 * ya, 0.34), TIMBER)
                for sy in (-1, 1):
                    for dx in (-0.08, 0.08):
                        self.seat('crossarm on cap girt', s * 0.32 + dx, sy * self.hy(zc - GIRT_H / 2), zc, on=('girt',))
        # Keep the whole brace inboard of the passing cabin's clearance envelope.
        # The top joint and its plate share this attachment; taller towers must not widen it.
        knee_y = min(1.9, g / 2 - self.p['cabin_width'] / 2 - TOWER_BODY_MARGIN - 0.05)
        z1 = self.levels[1]
        for sx in (-1, 1):
            for sy in (-1, 1):
                a = Vector((sx * 0.32, sy * knee_y, zc - 0.02)); b = Vector((sx * 0.32, sy * (self.hy(z1) + GIRT_D / 2 + 0.02), z1))
                m.beam(a, b, 0.06, 0.14, IRON, up=(1, 0, 0))
                m.box((sx * 0.32, sy * knee_y, zc - 0.015), (0.3, 0.32, 0.03), IRON)
        def saddle_z(x):
            if not self.saddle:
                return H
            h = 2 * self.saddle.get('half', 1.6)
            mid = .5 * (self.saddle['m_in'] + self.saddle['m_out'])
            k = (self.saddle['m_out'] - self.saddle['m_in']) / (2 * h)
            return H + mid * x + k * x * x

        def saddle_slope(x):
            if not self.saddle:
                return 0.0
            h = 2 * self.saddle.get('half', 1.6)
            mid = .5 * (self.saddle['m_in'] + self.saddle['m_out'])
            k = (self.saddle['m_out'] - self.saddle['m_in']) / (2 * h)
            return mid + 2 * k * x

        for s in (-1, 1):
            yc = s * (g / 2 - 0.11)
            train_half = self.saddle.get('half', 1.6) if self.saddle else 1.6
            sheaves = list(SHEAVE_X)
            extra = 1.35 + 0.75
            while extra <= train_half - 0.25 + 1e-9:
                sheaves += [-extra, extra]
                extra += 0.75
            sheaves = sorted(sheaves)
            # Timber carrier along the rope, following the saddle and resting
            # on both crossarm beams, with steel end straps.
            def carrier_z(x):
                return max(saddle_z(x) - (self.rr + SHEAVE_R), H - 0.375)
            with m.tagged('carrier'):
                # 1.2 m chords hold the beam clear of the rope on the tightest
                # saddle; one piece per sheaf would be several times the cost.
                segments = max(1, math.ceil(2 * train_half / 1.2))
                knots = [-train_half + 2 * train_half * k / segments for k in range(segments + 1)]
                for a, b in zip(knots, knots[1:]):
                    m.beam((a, yc, carrier_z(a)), (b, yc, carrier_z(b)), 0.1, 0.35, TIMBER, up=(0, 0, 1))
            for x in (-train_half, train_half):
                m.box((x, yc - s * 0.055, carrier_z(x)), (0.16, 0.012, 0.37), IRON)
            if train_half > 1.6:
                # A long train needs its own beam and posts; they stay above
                # the passing cabin roof (z_cap is below the hanger line).
                with m.tagged('carrier'):
                    m.beam((-train_half, yc, self.z_cap + 0.05), (train_half, yc, self.z_cap + 0.05),
                           0.12, 0.15, TIMBER, up=(0, 0, 1))
                for x in knots:
                    if abs(x) > 1.6 + 1e-9:
                        m.box((x, yc, (self.z_cap + 0.05 + carrier_z(x) - 0.175) / 2),
                              (0.12, 0.12, carrier_z(x) - 0.175 - self.z_cap - 0.05), TIMBER)
            for x in (-0.32, 0.32):
                self.seat('sheave carrier', x, yc, H - 0.55, on=('crossarm',))
            # Sheaves under the rope: each centre offset along the local rope
            # normal, so the groove stays concentric with a tilted rope.
            for x in sheaves:
                theta = math.atan(saddle_slope(x))
                reach = self.rr + SHEAVE_R
                c = Vector((x + reach * math.sin(theta), s * g / 2, saddle_z(x) - reach * math.cos(theta)))
                # Groove shaped round the rope (never inside it); flanges outside the rope, below the jaws' bottom.
                # The groove is an arc concentric with the rope, 2 mm larger, so its chords stay clear of the rope.
                rr = self.rr; hw = rr + 0.035; rf = SHEAVE_R + 0.6 * rr; rg = rr + 0.002
                groove = [(f * rr, SHEAVE_R + rr - math.sqrt(rg * rg - (f * rr) ** 2)) for f in (-0.9, -0.45, 0.0, 0.45, 0.9)]
                prof = [(-hw, rf)] + groove + [(hw, rf)]
                with m.tagged('sheave'):            # the rope's intentional contact (rope clearance report)
                    # Nine sides with a vertex at the top keep the exact seat.
                    m.lathe(tuple(c + Vector((0, -hw, 0))), [(a + hw, r) for a, r in prof], STEEL,
                            n=9, axis=(0, 1, 0), phase=math.pi / 2)
            # Head posts above the crossarm, inside the rope line, tied by a head beam along the line.
            for x in (-0.32, 0.32):
                m.box((x, s * (g / 2 - 0.5), H - 0.55 + 0.425), (0.22, 0.22, 0.85), TIMBER)
                self.seat('head post', x, s * (g / 2 - 0.5), H - 0.55, on=('crossarm',))
                m.box((x, s * (g / 2 - 0.5), H + 0.315), (0.26, 0.26, 0.03), IRON)
            m.box((0, s * (g / 2 - 0.5), H + 0.16), (1.1, 0.18, 0.2), TIMBER)

    def ladder(self, m):
        """Steel ladder up the -x face (outside the bracing) through a hatch in a railed timber landing that rests
        on brackets from the first girt below the cap."""
        z_land = self.levels[1] + GIRT_H / 2; z0 = 1.0
        off = 0.30                                    # ladder standoff from the leg centreline plane
        def xl(z):
            return -(self.hx(z) + off)
        for y in (-0.22, 0.22):
            m.tube([(xl(z0), y, z0), (xl(z_land + 1.05), y, z_land + 1.05)], 0.025, IRON, n=6)
        n = int((z_land - z0) / 0.5)
        for k in range(1, n + 1):
            z = z0 + k * (z_land - z0) / (n + 0.35)
            m.tube([(xl(z), -0.21, z), (xl(z), 0.21, z)], 0.014, IRON, n=3)
        for z in self.levels[2:]:
            if z0 < z < z_land:
                for y in (-0.22, 0.22):
                    m.beam((xl(z), y, z), (-(self.hx(z) + GIRT_D / 2 - 0.01), y, z), 0.04, 0.04, IRON)
        hx = self.hx(self.levels[1]); xb = -(hx + LEG / 2 + 0.01); xo = -(hx + 1.08); ys, yh = 0.6, 0.27
        xh0 = -(hx + off + 0.16)       # hatch round the ladder
        with m.tagged('deck'):
            for s in (-1, 1):
                m.box(((xo + xb) / 2, s * (ys + yh) / 2, z_land - 0.04), (xb - xo, ys - yh, 0.08), TIMBER)
            m.box(((xo + xh0) / 2, 0, z_land - 0.04), (xh0 - xo, 2 * yh, 0.08), TIMBER)
        for y in (-0.45, 0.45):
            m.box(((-(hx - 0.02)) / 2 + (xo + 0.05) / 2, y, z_land - 0.11), (abs(xo + 0.05 + hx - 0.02), 0.06, 0.06), IRON)
        posts = [(xo + 0.04, -ys + 0.04), (xo + 0.04, ys - 0.04), (xb - 0.04, -ys + 0.04), (xb - 0.04, ys - 0.04)]
        for x, y in posts:
            m.box((x, y, z_land + 0.5), (0.06, 0.06, 1.0), IRON)
            self.seat('landing rail post', x, y, z_land, on=('deck',))
        for a, b in ((posts[0], posts[2]), (posts[1], posts[3])):
            m.box(((a[0] + b[0]) / 2, a[1], z_land + 1.02), (abs(b[0] - a[0]) + 0.06, 0.06, 0.04), IRON)
        m.box((posts[0][0], 0, z_land + 1.02), (0.06, 2 * ys - 0.14, 0.04), IRON)
        self.ladder_info = {'face': '-x', 'bottom_z': z0, 'landing_z': round(z_land, 3), 'landing_outer_x': round(xo, 3),
                            'width': 0.44, 'mode': 'climb-only service ladder through a hatch in the landing'}

    def build(self):
        name = f'GD_Tower_{self.H:g}m'
        m = Mesh(name)
        self.legs(m); self.girts(m); self.braces(m); self.straps(m); self.foundation(m); self.guys(m); self.head(m); self.ladder(m)
        return m

    # ---------------------------------------------------------------- collision, attachment points
    def proxies(self):
        P = []; zs = [LEG_FOOT] + [z for z in self.levels[::-1]][1:]
        for z0, z1 in zip(zs[:-1], zs[1:]):
            hx = self.hx(z0) + LEG / 2; hy = self.hy(z0) + LEG / 2
            P.append(proxy_box('tower shaft', 0, 0, 2 * hx, 2 * hy, z0, z1))
        for sx in (-1, 1):
            for sy in (-1, 1):
                c = self.leg_pt(sx, sy, LEG_FOOT); P.append(proxy_box('pedestal', c.x, c.y, 1.0, 1.0, self.pedestal_bases.get((sx,sy),-1.0), LEG_FOOT))
                ax = sx * (self.hx(0) + GUY_SPREAD * self.H); ay = sy * self.hy(LEG_FOOT)
                bottom,top = self.anchor_bounds.get((sx,sy),(-.9,.55))
                P.append(proxy_box('guy anchor', ax, ay, 0.9, 0.9, bottom, top))
        g = self.g
        P.append(proxy_box('crossarm', 0, 0, 0.9, g - 0.24, self.z_cap, self.z_cap + 0.34))
        for s in (-1, 1):
            P.append(proxy_box('sheave train', 0, s * g / 2 - s * 0.05, 3.5, 0.22, self.H - 0.55, self.H - self.rr))
            P.append(proxy_box('head posts', 0, s * (g / 2 - 0.5), 1.1, 0.26, self.H - 0.55, self.H + 0.33))
        return P

    def attachment(self):
        g = self.g
        return {'height': self.H, 'rope_saddles': [{'side': s, 'centre': [0.0, s * g / 2, self.H],
                                                    'sheaves_x': list(SHEAVE_X), 'sheave_groove_radius': SHEAVE_R,
                                                    'sheave_centre_z': round(self.H - self.rr - SHEAVE_R, 4)} for s in (-1, 1)],
                'crossarm_z': [round(self.z_cap, 3), round(self.z_cap + 0.34, 3)], 'cap_z': round(self.z_cap, 3),
                'base_half_widths': [round(self.hx(LEG_FOOT) + LEG / 2, 3), round(self.hy(LEG_FOOT) + LEG / 2, 3)],
                'top_half_widths': [round(HX_TOP + LEG / 2, 3), round(HY_TOP + LEG / 2, 3)],
                'foundation': {'datum_z': 0.0, 'pedestal_bottom_z': -1.0, 'pedestal_top_z': 0.62,
                               'pedestals_xy': [[round(self.leg_pt(sx, sy, LEG_FOOT).x, 3), round(self.leg_pt(sx, sy, LEG_FOOT).y, 3)] for sx in (-1, 1) for sy in (-1, 1)],
                               'ground_relief_allowed_m': [-0.9, 0.5],
                               'note': 'place with the datum on the rendered ground at the tower axis; each pedestal must have ground between z -0.9 and +0.5'},
                'guy_anchors_xy': [[round(sx * (self.hx(0) + GUY_SPREAD * self.H), 3), round(sy * self.hy(LEG_FOOT), 3)] for sx in (-1, 1) for sy in (-1, 1)],
                'guy_anchor_z': [-0.9, 0.45],
                'panel_levels_z': [round(z, 3) for z in self.levels], 'ladder': self.ladder_info}
