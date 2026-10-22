"""Tiny flat-shaded geometry builder shared by every Brinecove module.

Faces are collected per material, then one Blender mesh is made per module. Keeping the module a single object makes
the per-module GLB and the viewer's show/hide switches simple, and keeps draw calls low.
"""
import math

from brinecove.surface_mapping import MATERIAL_SURFACE


def _surface_scale(mat):
    return MATERIAL_SURFACE.get(mat, (None, 2.0))[1]


def _rot(x, y, yaw):
    a = math.radians(yaw)
    c, s = math.cos(a), math.sin(a)
    return x * c - y * s, x * s + y * c


def _unit(v):
    n = math.sqrt(sum(c * c for c in v))
    if n < 1e-9:
        return (1.0, 0.0, 0.0)
    return tuple(c / n for c in v)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def distinct_corners(points, area=1e-6):
    """Indices of a face's corners without repeats (a cone's apex quad), or None when the face has no area.

    Unreal drops such triangles on import, and the import checks every tile's triangle count against the export."""
    snap = [tuple(round(c, 5) for c in p) for p in points]
    corners = [k for k in range(len(points)) if snap[k] != snap[k - 1]]
    if len(corners) < 3:
        return None
    ring = [points[k] for k in corners]
    n = [0.0, 0.0, 0.0]
    for (x0, y0, z0), (x1, y1, z1) in zip(ring, ring[1:] + ring[:1]):
        n[0] += (y0 - y1) * (z0 + z1)
        n[1] += (z0 - z1) * (x0 + x1)
        n[2] += (x0 - x1) * (y0 + y1)
    return corners if math.sqrt(sum(c * c for c in n)) / 2 >= area else None


class Builder:
    def __init__(self, name):
        self.name = name
        self.verts = []
        self.uvs = []
        self.faces = []
        self.mats = []
        self.keys = self.mats
        self.foliage_roles = {}
        # Optional per-vertex normals: foliage cards point away from their crown so a canopy shades as one mass.
        # None for a vertex means the flat face normal.
        self.normals = None
        # Optional per-face anchors (x, y): a rigid object's faces share one, so the collar moves it as one piece.
        self.anchor = None
        self.anchors = None

    def face(self, points, mat, uvs=None, normals=None):
        points = tuple(tuple(float(c) for c in p) for p in points)
        # Box-project each face in world metres.  Every face owns its vertices,
        # so a projected seam never drags a neighbouring wall's UVs with it.
        # Leaf cards pass an explicit atlas cell instead.
        if uvs is not None:
            uvs = [(float(u), float(v)) for u, v in uvs]
        elif len(points) >= 3:
            ax = abs((points[1][1] - points[0][1]) * (points[2][2] - points[0][2])
                     - (points[1][2] - points[0][2]) * (points[2][1] - points[0][1]))
            ay = abs((points[1][2] - points[0][2]) * (points[2][0] - points[0][0])
                     - (points[1][0] - points[0][0]) * (points[2][2] - points[0][2]))
            az = abs((points[1][0] - points[0][0]) * (points[2][1] - points[0][1])
                     - (points[1][1] - points[0][1]) * (points[2][0] - points[0][0]))
            scale = max(0.05, _surface_scale(mat))
            if az >= ax and az >= ay:
                uvs = [(p[0] / scale, p[1] / scale) for p in points]
            elif ax >= ay:
                uvs = [(p[1] / scale, p[2] / scale) for p in points]
            else:
                uvs = [(p[0] / scale, p[2] / scale) for p in points]
        else:
            uvs = [(0.0, 0.0) for _ in points]
        i = len(self.verts)
        if normals is not None and self.normals is None:
            self.normals = [None] * i
        if self.normals is not None:
            self.normals.extend(normals if normals is not None else [None] * len(points))
        self.verts.extend(points)
        self.uvs.extend(uvs)
        self.faces.append(tuple(range(i, i + len(points))))
        self.mats.append(mat)
        role=getattr(mat,'foliage_key',None)
        if role is not None:self.foliage_roles[len(self.faces)-1]=role
        if self.anchor is not None and self.anchors is None:
            self.anchors = [None] * (len(self.faces) - 1)
        if self.anchors is not None:
            self.anchors.append(self.anchor)

    def tri(self, a, b, c, mat):
        self.face((a, b, c), mat)

    def quad(self, a, b, c, d, mat, uvs=None):
        self.face((a, b, c, d), mat, uvs)

    def card(self, center, normal, width, height, mat, uvs, up_hint=(0.0, 0.0, 1.0), normal_from=None, lift=0.0):
        """A rectangular leaf card centred at center, facing normal."""
        nx, ny, nz = _unit(normal)
        ux, uy, uz = up_hint
        rx = uy * nz - uz * ny
        ry = uz * nx - ux * nz
        rz = ux * ny - uy * nx
        if abs(rx) + abs(ry) + abs(rz) < 1e-5:
            ux, uy, uz = (0.0, 1.0, 0.0)
            rx = uy * nz - uz * ny
            ry = uz * nx - ux * nz
            rz = ux * ny - uy * nx
        rx, ry, rz = _unit((rx, ry, rz))
        sx = ny * rz - nz * ry
        sy = nz * rx - nx * rz
        sz = nx * ry - ny * rx
        sx, sy, sz = _unit((sx, sy, sz))
        hw, hh = width * 0.5, height * 0.5
        cx, cy, cz = center
        corners = []
        for du, dv in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)):
            corners.append((cx + rx * du + sx * dv, cy + ry * du + sy * dv, cz + rz * du + sz * dv))
        normals = None
        if normal_from is not None:
            # Shade the card as part of a rounded mass centred at normal_from, biased upward by lift.
            normals = [_unit((p[0] - normal_from[0], p[1] - normal_from[1], p[2] - normal_from[2] + lift))
                       for p in corners]
        self.face(tuple(corners), mat, uvs, normals)

    def box(self, center, size, mat, yaw=0.0, top=None):
        cx, cy, cz = center
        sx, sy, sz = size
        hx, hy, hz = sx / 2, sy / 2, sz / 2
        pts = []
        for dz, sc in ((-hz, 1.0), (hz, 1.0 if top is None else top)):
            for dx, dy in ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)):
                rx, ry = _rot(dx * sc, dy * sc, yaw)
                pts.append((cx + rx, cy + ry, cz + dz))
        b, t = pts[:4], pts[4:]
        self.quad(b[3], b[2], b[1], b[0], mat)
        self.quad(t[0], t[1], t[2], t[3], mat)
        self.quad(b[0], b[1], t[1], t[0], mat)
        self.quad(b[1], b[2], t[2], t[1], mat)
        self.quad(b[2], b[3], t[3], t[2], mat)
        self.quad(b[3], b[0], t[0], t[3], mat)

    def beam(self, a, b, width, mat, depth=None):
        """A square-ish timber from a to b, useful for posts, rails, rigging and rope."""
        depth = width if depth is None else depth
        a = tuple(float(c) for c in a); b = tuple(float(c) for c in b)
        d = _unit(tuple(b[i] - a[i] for i in range(3)))
        up = (0.0, 0.0, 1.0)
        if abs(d[2]) > 0.94:
            up = (0.0, 1.0, 0.0)
        u = _unit(_cross(d, up))
        v = _unit(_cross(d, u))
        hu, hv = width / 2, depth / 2
        p = []
        for point in (a, b):
            for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                p.append((point[0] + u[0] * hu * su + v[0] * hv * sv,
                          point[1] + u[1] * hu * su + v[1] * hv * sv,
                          point[2] + u[2] * hu * su + v[2] * hv * sv))
        self.quad(p[3], p[2], p[1], p[0], mat)
        self.quad(p[4], p[5], p[6], p[7], mat)
        for i in range(4):
            j = (i + 1) % 4
            self.quad(p[i], p[j], p[4 + j], p[4 + i], mat)

    def cylinder(self, a, b, radius, mat, sides=8, radius_b=None, caps=True):
        radius_b = radius if radius_b is None else radius_b
        a = tuple(float(c) for c in a); b = tuple(float(c) for c in b)
        d = _unit(tuple(b[i] - a[i] for i in range(3)))
        up = (0.0, 0.0, 1.0)
        if abs(d[2]) > 0.94:
            up = (0.0, 1.0, 0.0)
        u = _unit(_cross(d, up)); v = _unit(_cross(d, u))
        ring_a, ring_b = [], []
        for i in range(sides):
            ang = 2 * math.pi * i / sides
            cu, sv = math.cos(ang), math.sin(ang)
            ring_a.append((a[0] + (u[0] * cu + v[0] * sv) * radius,
                           a[1] + (u[1] * cu + v[1] * sv) * radius,
                           a[2] + (u[2] * cu + v[2] * sv) * radius))
            ring_b.append((b[0] + (u[0] * cu + v[0] * sv) * radius_b,
                           b[1] + (u[1] * cu + v[1] * sv) * radius_b,
                           b[2] + (u[2] * cu + v[2] * sv) * radius_b))
        for i in range(sides):
            j = (i + 1) % sides
            self.quad(ring_a[i], ring_a[j], ring_b[j], ring_b[i], mat)
        if caps:
            self.face(tuple(reversed(ring_a)), mat)
            self.face(tuple(ring_b), mat)

    def sphere(self, center, radius, mat, scale=(1.0, 1.0, 1.0), subdiv=1):
        """Low-poly icosphere, scaled; flat facets are the point."""
        t = (1.0 + math.sqrt(5.0)) / 2.0
        base = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0),
                (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
                (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
        faces = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11),
                 (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8),
                 (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9),
                 (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]
        verts = [_unit(v) for v in base]
        for _ in range(subdiv):
            cache, new_faces = {}, []

            def mid(i, j):
                key = (min(i, j), max(i, j))
                if key not in cache:
                    a, b = verts[i], verts[j]
                    cache[key] = len(verts)
                    verts.append(_unit(tuple((a[k] + b[k]) / 2 for k in range(3))))
                return cache[key]

            for a, b, c in faces:
                ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
                new_faces.extend(((a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)))
            faces = new_faces
        cx, cy, cz = center
        points = [(cx + v[0] * radius * scale[0], cy + v[1] * radius * scale[1], cz + v[2] * radius * scale[2])
                  for v in verts]
        for f in faces:
            self.face(tuple(points[i] for i in f), mat)

    def _yaw_since(self, start, cx, cy, yaw):
        if yaw:
            a = math.radians(yaw)
            c, s = math.cos(a), math.sin(a)
            for i in range(start, len(self.verts)):
                x, y, zz = self.verts[i]
                dx, dy = x - cx, y - cy
                self.verts[i] = (cx + dx * c - dy * s, cy + dx * s + dy * c, zz)

    def panel(self, a, b, c, d, mat, under=None, thick=0.06):
        """@cc [owner:fontanierh,label:correctness] brinecove-two-sided-sheet
        A thin two-sided sheet (awning, lean-to, canopy, hanging cloth): both faces and its edges. A sheet MUST be
        emitted as a closed slab (top, back and four edge faces), so it never vanishes when seen from beneath, and a
        sloped sheet's top MUST face up.

        A bare quad is one-sided, so seen from beneath an awning vanished (playtest note 10). A sloped sheet always
        faces up; the back face sits thick behind it along the normal.
        """
        pts = [tuple(float(c) for c in p) for p in (a, b, c, d)]
        n = _unit(_cross(tuple(pts[1][k] - pts[0][k] for k in range(3)), tuple(pts[3][k] - pts[0][k] for k in range(3))))
        if n[2] < -0.1:
            pts.reverse()
            n = (-n[0], -n[1], -n[2])
        low = [tuple(p[k] - n[k] * thick for k in range(3)) for p in pts]
        self.quad(*pts, mat)
        self.quad(low[3], low[2], low[1], low[0], under or mat)
        for i in range(4):
            j = (i + 1) % 4
            self.quad(low[i], low[j], pts[j], pts[i], under or mat)

    def roof_pitch(self, width, depth, rise, overhang=0.8, ridge='x', hip=False):
        """Rise per metre of a roof's slopes; eave details (rafter tails) follow it down."""
        if hip:
            return rise / (min(width, depth) / 2 + overhang)
        return rise / ((depth if ridge == 'x' else width) / 2 + overhang)

    def gable_roof(self, center, width, depth, z, rise, mat, yaw=0.0, ridge='x', overhang=0.8, gable='planks',
                   soffit='wood', thick=0.14):
        """@cc [owner:fontanierh,label:correctness] brinecove-roof-seated-solid
        Gable roof seated on a wall plate at z: deep eaves, a planked soffit, closed gables, ridge along x or y.
        The slopes' underside MUST meet the wall top at the wall line (no gap above the walls), and the soffit and
        gable infill MUST close the roof from below, so no sky shows through it from the street.

        The roof is a slab: the slopes' underside passes through the wall top at the wall line, so no roof floats
        above its walls, and the soffit and gable infill keep it solid from below (playtest notes 6-8 and 12).
        """
        cx, cy, _ = center
        start = len(self.verts)
        U, V = (width / 2, depth / 2) if ridge == 'x' else (depth / 2, width / 2)
        Ua, Va, t = U + overhang, V + overhang, thick
        ze = z + t - rise * overhang / Va
        top = ze + rise

        def F(pts, m, flip=False):
            # Local (u along the ridge, v across); swapping axes for a y ridge mirrors, so the winding flips too.
            pts = [(cx + u, cy + v, h) if ridge == 'x' else (cx + v, cy + u, h) for u, v, h in pts]
            self.face(tuple(pts if (ridge == 'x') != flip else reversed(pts)), m)

        for s in (-1, 1):
            slope = [(-Ua, s * Va, ze), (Ua, s * Va, ze), (Ua, 0, top), (-Ua, 0, top)]
            F(slope, mat, s > 0)
            F([(u, v, h - t) for u, v, h in slope], soffit, s < 0)
            F([(-Ua, s * Va, ze - t), (Ua, s * Va, ze - t), (Ua, s * Va, ze), (-Ua, s * Va, ze)], 'wood_dark', s > 0)
            for e in (-1, 1):
                F([(e * Ua, s * Va, ze - t), (e * Ua, s * Va, ze), (e * Ua, 0, top), (e * Ua, 0, top - t)],
                  'wood_dark', e * s < 0)
            self.beam(*[(cx + u, cy + s * Va, ze - t / 2) if ridge == 'x' else (cx + s * Va, cy + u, ze - t / 2)
                        for u in (-Ua, Ua)], 0.2, 'wood_dark')
        # Gable infill at each end wall, up to the soffit, from both sides.
        for e in (-1, 1):
            tri = [(e * U, -V, z), (e * U, 0, top - t), (e * U, V, z)]
            F(tri, gable, e > 0)
            F(tri, gable, e < 0)
        # Ridge cap in fired clay; grey slate battens striped every terracotta roof.
        cap = 'roof_slate' if mat == 'roof_slate' else 'clay'
        if ridge == 'x':
            self.beam((cx - Ua, cy, top), (cx + Ua, cy, top), 0.3, cap)
        else:
            self.beam((cx, cy - Ua, top), (cx, cy + Ua, top), 0.3, cap)
        self._yaw_since(start, cx, cy, yaw)

    def hip_roof(self, center, width, depth, z, rise, mat, yaw=0.0, overhang=0.8, soffit='wood', thick=0.14):
        """Hip roof seated on a wall plate at z, all four slopes at one pitch, with a soffit and eave edges.

        Equal pitches put every eave's underside on the wall top, so no side gaps open above the walls.
        """
        cx, cy, _ = center
        start = len(self.verts)
        w, d = width / 2 + overhang, depth / 2 + overhang
        t = thick
        run = min(w, d)
        ze = z + t - rise * overhang / run
        top = ze + rise
        e = [(cx - w, cy - d, ze), (cx + w, cy - d, ze), (cx + w, cy + d, ze), (cx - w, cy + d, ze)]
        k = max(0.05, abs(w - d))
        cap = 'roof_slate' if mat == 'roof_slate' else 'clay'
        if w >= d:
            r1 = (cx - k, cy, top); r2 = (cx + k, cy, top)
            faces = [(e[0], e[1], r2, r1), (e[3], r1, r2, e[2]), (e[0], r1, e[3]), (e[1], e[2], r2)]
        else:
            r1 = (cx, cy - k, top); r2 = (cx, cy + k, top)
            faces = [(e[0], r1, r2, e[3]), (e[1], e[2], r2, r1), (e[0], e[1], r1), (e[3], r2, e[2])]
        for f in faces:
            self.face(f, mat)
            self.face(tuple((p[0], p[1], p[2] - t) for p in reversed(f)), soffit)
        self.beam(r1, r2, 0.3, cap)
        # Hip rafters down each corner, eave edges and a fascia board.
        for i in range(4):
            j = (i + 1) % 4
            p, q = e[i], e[j]
            self.quad((p[0], p[1], ze - t), (q[0], q[1], ze - t), q, p, 'wood_dark')
            near = r1 if math.dist(p, r1) < math.dist(p, r2) else r2
            self.beam(p, near, 0.2, cap)
            self.beam((p[0], p[1], ze - t / 2), (q[0], q[1], ze - t / 2), 0.18, 'wood_dark')
        self._yaw_since(start, cx, cy, yaw)

    def rope(self, a, b, sag=1.0, radius=0.09, mat='rope', segments=8):
        a = tuple(float(c) for c in a); b = tuple(float(c) for c in b)
        prev = a
        for i in range(1, segments + 1):
            t = i / segments
            p = tuple(a[k] + (b[k] - a[k]) * t for k in range(3))
            p = (p[0], p[1], p[2] - sag * math.sin(math.pi * t))
            self.beam(prev, p, radius, mat)
            prev = p

    def ring(self, center, radius, tube, mat, axis='z', sides=10, tube_sides=6):
        cx, cy, cz = center
        pts = []
        for i in range(sides):
            ang = 2 * math.pi * i / sides
            if axis == 'z':
                pts.append((cx + math.cos(ang) * radius, cy + math.sin(ang) * radius, cz))
            elif axis == 'x':
                pts.append((cx, cy + math.cos(ang) * radius, cz + math.sin(ang) * radius))
            else:
                pts.append((cx + math.cos(ang) * radius, cy, cz + math.sin(ang) * radius))
        for i in range(sides):
            self.cylinder(pts[i], pts[(i + 1) % sides], tube, mat, tube_sides, caps=False)

    def triangle_fan(self, center, points, mat):
        for i in range(len(points)):
            self.tri(center, points[i], points[(i + 1) % len(points)], mat)
