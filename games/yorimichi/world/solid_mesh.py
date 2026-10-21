"""The shared closed-solid mesh builder: plan-outline prisms, lofts, boxes, beams, tubes, lathes and tori, every part a
closed solid with outward normals, built in nested local frames and turned into a Blender object by to_object.

Vehicle and building kits build on this one implementation (the ferry and its terminals today). A kit keeps its own
materials and passes them in; it does not copy these primitives.
"""
import bisect
import math
import sys
from contextlib import contextmanager

import bpy
from mathutils import Matrix, Vector


def signed_area(pts):
    return 0.5 * sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))


def is_convex(pts):
    n = len(pts); sgn = 0
    for i in range(n):
        a, b, c = pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        cr = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        if abs(cr) < 1e-12:
            continue
        s = 1 if cr > 0 else -1
        if sgn and s != sgn:
            return False
        sgn = s
    return True

def ear_clip(pts):
    """Triangulate a simple CCW polygon; returns index triples."""
    idx = list(range(len(pts))); tris = []

    def inside(p, a, b, c):
        d1 = (p[0] - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (p[1] - b[1])
        d2 = (p[0] - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (p[1] - c[1])
        d3 = (p[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (p[1] - a[1])
        return not ((d1 < -1e-12 or d2 < -1e-12 or d3 < -1e-12) and (d1 > 1e-12 or d2 > 1e-12 or d3 > 1e-12))

    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1; n = len(idx); found = False
        for k in range(n):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % n]
            a, b, c = pts[i0], pts[i1], pts[i2]
            if (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) <= 1e-12:
                continue
            if any(inside(pts[j], a, b, c) for j in idx if j not in (i0, i1, i2)):
                continue
            tris.append((i0, i1, i2)); idx.pop(k); found = True
            break
        if not found:
            raise ValueError('ear clipping failed (self-intersecting outline?)')
    tris.append(tuple(idx))
    return tris

def offset_loop(pts, d):
    """Offset a CCW loop outward by d (negative insets) with mitred corners."""
    n = len(pts); out = []
    for i in range(n):
        p0, p1, p2 = Vector(pts[i - 1]), Vector(pts[i]), Vector(pts[(i + 1) % n])
        e1, e2 = (p1 - p0).normalized(), (p2 - p1).normalized()
        n1, n2 = Vector((e1.y, -e1.x)), Vector((e2.y, -e2.x))
        m = (n1 + n2) / max(0.25, 1 + n1.dot(n2))
        out.append(tuple(p1 + m * d))
    return out


def resample(pts, step, closed=True):
    out = []
    n = len(pts)
    for i in range(n if closed else n - 1):
        a, b = Vector(pts[i]), Vector(pts[(i + 1) % n])
        k = max(1, math.ceil((b - a).length / step))
        out += [tuple(a.lerp(b, j / k)) for j in range(k)]
    if not closed:
        out.append(tuple(pts[-1]))
    return out


def circle(r, n=12, phase=0.0, sx=1.0, sy=1.0, c=(0.0, 0.0)):
    return [(c[0] + sx * r * math.cos(phase + 2 * math.pi * k / n), c[1] + sy * r * math.sin(phase + 2 * math.pi * k / n)) for k in range(n)]


def rounded_rect(w, h, r, k=3, c=(0.0, 0.0)):
    pts = []
    for cx, cy, a0 in [(w / 2 - r, -h / 2 + r, -90), (w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90), (-w / 2 + r, -h / 2 + r, 180)]:
        for j in range(k + 1):
            a = math.radians(a0 + 90 * j / k)
            pts.append((c[0] + cx + r * math.cos(a), c[1] + cy + r * math.sin(a)))
    return pts


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _caller():
    """'file.py:line' of the first frame outside this module (the kit line that asked for a part)."""
    f = sys._getframe(2)
    while f and f.f_code.co_filename == __file__:
        f = f.f_back
    return f'{f.f_code.co_filename.rsplit("/", 1)[-1]}:{f.f_lineno}' if f else '?'


class Mesh:
    """@cc [owner:fontanierh,label:correctness] solid-part-transform-and-metadata
    Each primitive MUST call part once per closed solid. part MUST apply the current
    frame to every vertex, reverse winding under a reflection, preserve face materials
    and append its contiguous face interval. Kit metadata MAY extend that interval
    after its first two indices; shared audits MUST preserve and ignore those additions.
    """
    def __init__(self, name, default_mat=None):
        self.name = name; self.verts = []; self.faces = []; self.mats = []; self.parts = []
        self.origins = []                  # the kit source line that built each part (for audit reports)
        self.seats = []                    # fitting bases registered with fitting(): see seat_failures
        self.xf = Matrix.Identity(4)
        self.default_mat = default_mat     # the cap material of a prism whose side material is per-edge

    @contextmanager
    def _push(self, m):
        old = self.xf; self.xf = old @ m
        try:
            yield
        finally:
            self.xf = old

    def at(self, pos=(0, 0, 0), yaw=0.0):
        return self._push(Matrix.Translation(Vector(pos)) @ Matrix.Rotation(math.radians(yaw), 4, 'Z'))

    def mirrored(self, on=True, axis='y'):
        return self._push(Matrix.Scale(-1, 4, {'x': (1, 0, 0), 'y': (0, 1, 0)}[axis]) if on else Matrix.Identity(4))

    def frame(self, origin, U, V, A):
        r = Matrix((tuple(U), tuple(V), tuple(A))).transposed().to_4x4()
        return self._push(Matrix.Translation(Vector(origin)) @ r)

    def wall(self, origin, normal):
        """Local frame on a wall: x along the wall, y up, z out of the wall."""
        A = Vector((normal[0], normal[1], 0)).normalized(); V = Vector((0, 0, 1)); U = V.cross(A)
        return self.frame(origin, U, V, A)

    def part(self, verts, faces, mats):
        M = self.xf; flip = M.to_3x3().determinant() < 0
        base = len(self.verts)
        self.verts.extend(tuple(M @ Vector(v)) for v in verts)
        start = len(self.faces)
        for k, f in enumerate(faces):
            f = [base + i for i in f]
            self.faces.append(tuple(reversed(f)) if flip else tuple(f))
            self.mats.append(mats[k] if isinstance(mats, list) else mats)
        self.parts.append((start, len(self.faces)))
        self.origins.append(_caller())
        return len(self.parts) - 1

    @contextmanager
    def fitting(self, label, embed=0.06, direction=(0, 0, -1), gap=None, spread=None):
        """Register what is built inside the block as one fitting seated on something: append its base points
        (local coordinates) to the yielded list. seat_failures ray-casts each base along direction (local; down by
        default, onto what carries it) onto everything else. gap is the most open the seat may be (None: SEAT_GAP);
        spread is how far round each base the side rays go (None: seat_failures' default; 0: the base point only, for
        a seat under a slope, where side rays would land at other heights)."""
        start = len(self.parts); bases = []
        yield bases
        d = tuple((self.xf.to_3x3() @ Vector(direction)).normalized())
        for p in bases:
            self.seats.append({'label': label, 'at': tuple(self.xf @ Vector(p)), 'embed': embed, 'dir': d, 'gap': gap,
                               'spread': spread, 'own': (self.name, start, len(self.parts))})

    # ---- primitives (all closed)
    def prism(self, outline, z0, z1, side, top=None, bottom=None, bevel=0.0, step=None, triangulate_caps=False):
        pts = [tuple(p) for p in outline]
        if step:
            pts = resample(pts, step)
        if signed_area(pts) < 0:
            pts = pts[::-1]
        f0 = z0 if callable(z0) else (lambda x, y, c=z0: c)
        f1 = z1 if callable(z1) else (lambda x, y, c=z1: c)
        if bevel > 0:
            inner = offset_loop(pts, -bevel)
            rings = [(inner, f0, 0.0), (pts, f0, bevel), (pts, f1, -bevel), (inner, f1, 0.0)]
        else:
            rings = [(pts, f0, 0.0), (pts, f1, 0.0)]
        n = len(pts); verts = []
        for ring, fz, dz in rings:
            verts += [(x, y, fz(x, y) + dz) for x, y in ring]
        faces = [list(reversed(range(n))), [(len(rings) - 1) * n + k for k in range(n)]]
        mats = [bottom or (side if isinstance(side, str) else self.default_mat), top or (side if isinstance(side, str) else self.default_mat)]
        if triangulate_caps and (not is_convex(pts) or callable(z0) or callable(z1)):
            cap_materials = mats
            faces, mats = [], []
            last = (len(rings) - 1) * n
            for a, b, c in ear_clip(rings[0][0]):
                faces.extend(([c, b, a], [last + a, last + b, last + c]))
                mats.extend(cap_materials)
        for r in range(len(rings) - 1):
            for k in range(n):
                k2 = (k + 1) % n
                faces.append([r * n + k, r * n + k2, (r + 1) * n + k2, (r + 1) * n + k])
                if callable(side):
                    mats.append(side((pts[k][0] + pts[k2][0]) / 2, (pts[k][1] + pts[k2][1]) / 2))
                else:
                    mats.append(side)
        return self.part(verts, faces, mats)

    def loft_prism(self, outline, f0, f1, side, top=None, bottom=None, bevel=0.0, dx=0.5):
        """Solid over an x-monotone plan outline, lofted through x stations so a top that follows the sheer is
        built from quads across the deck (no non-planar n-gon caps)."""
        pts = [tuple(p) for p in outline]; xmin = min(p[0] for p in pts); xmax = max(p[0] for p in pts)
        xs = sorted({round(p[0], 5) for p in pts} | {round(xmin + k * dx, 5) for k in range(int((xmax - xmin) / dx) + 1)})
        xs = [x for x in xs if xmin <= x <= xmax]; xs[0] = xmin + 1e-4; xs[-1] = xmax - 1e-3
        rings = []
        for x in xs:
            ys = []
            for k in range(len(pts)):
                (x0, y0), (x1, y1) = pts[k], pts[(k + 1) % len(pts)]
                if (x0 - x) * (x1 - x) <= 0 and x0 != x1:
                    ys.append(y0 + (y1 - y0) * (x - x0) / (x1 - x0))
            lo, hi = min(ys), max(ys)
            b = min(bevel, (hi - lo) * 0.3)
            rings.append([(x, lo, f0(x, lo)), (x, hi, f0(x, hi)), (x, hi, f1(x, hi) - b), (x, hi - b, f1(x, hi)), (x, lo + b, f1(x, lo)), (x, lo, f1(x, lo) - b)])
        sm = side if callable(side) else (lambda x, y: side)
        verts = [v for r in rings for v in r]; faces = []; mats = []; n = 6
        for i in range(len(rings) - 1):
            xm = (rings[i][0][0] + rings[i + 1][0][0]) / 2
            for k in range(n):
                j = (k + 1) % n
                faces.append([i * n + k, (i + 1) * n + k, (i + 1) * n + j, i * n + j])
                if k == 0:
                    mats.append(bottom or sm(xm, 0))
                elif k == 3:
                    mats.append(top or sm(xm, 0))
                else:
                    mats.append(sm(xm, rings[i][1][1] if k in (1, 2) else rings[i][0][1]))
        faces.append(list(range(n))); mats.append(sm(xs[0], 0))
        last = (len(rings) - 1) * n; faces.append([last + k for k in range(n)][::-1]); mats.append(sm(xs[-1], 0))
        return self.part(verts, faces, mats)

    def ring_prism(self, outer, inner, z0, z1, mat):
        """Closed band between two CCW loops of equal count (a frame, rim or valance)."""
        n = len(outer); verts = [(*p, z0) for p in outer] + [(*p, z0) for p in inner] + [(*p, z1) for p in outer] + [(*p, z1) for p in inner]
        O0, I0, O1, I1 = 0, n, 2 * n, 3 * n; faces = []
        for k in range(n):
            j = (k + 1) % n
            faces += [[O1 + k, O1 + j, I1 + j, I1 + k], [O0 + k, I0 + k, I0 + j, O0 + j],
                      [O0 + k, O0 + j, O1 + j, O1 + k], [I0 + k, I1 + k, I1 + j, I0 + j]]
        return self.part(verts, faces, mat)

    def box(self, c, s, mat, bevel=0.0, top=None, bottom=None):
        x, y, z = c; w, d, h = s
        return self.prism(rect(x - w / 2, y - d / 2, x + w / 2, y + d / 2), z - h / 2, z + h / 2, mat, top=top, bottom=bottom, bevel=bevel)

    def beam(self, a, b, w, d, mat, up=None, bevel=0.0):
        a, b = Vector(a), Vector(b); A = b - a; L = A.length
        if L < 1e-6:
            return
        A.normalize(); ref = Vector(up) if up is not None else (Vector((0, 0, 1)) if abs(A.z) < 0.9 else Vector((1, 0, 0)))
        U = (ref.cross(A) if up is not None else A.cross(ref)).normalized(); V = A.cross(U)
        with self.frame(a, U, V, A):
            return self.prism(rect(-w / 2, -d / 2, w / 2, d / 2), 0.0, L, mat, bevel=bevel)

    def tube(self, path, r, mat, n=6, star=1.0, twist=0.0, phase=0.0, sx=1.0, sy=1.0):
        P = [Vector(p) for p in path]; N = len(P)
        radii = r if isinstance(r, (list, tuple)) else [r] * N
        T = [(P[min(i + 1, N - 1)] - P[max(i - 1, 0)]).normalized() for i in range(N)]
        ref = Vector((0, 0, 1)) if abs(T[0].z) < 0.9 else Vector((1, 0, 0))
        nrm = [(ref - T[0] * ref.dot(T[0])).normalized()]
        for i in range(1, N):
            q = nrm[-1] - T[i] * nrm[-1].dot(T[i])
            nrm.append(q.normalized() if q.length > 1e-6 else nrm[-1])
        verts = []
        for i in range(N):
            B = T[i].cross(nrm[i])
            for k in range(n):
                a = phase + twist * i + 2 * math.pi * k / n; rr = radii[i] * (1.0 if k % 2 == 0 else star)
                verts.append(tuple(P[i] + rr * (sx * math.cos(a) * nrm[i] + sy * math.sin(a) * B)))
        faces = []
        for i in range(N - 1):
            for k in range(n):
                j = (k + 1) % n
                faces.append([i * n + k, i * n + j, (i + 1) * n + j, (i + 1) * n + k])
        faces.append(list(reversed(range(n)))); faces.append([(N - 1) * n + k for k in range(n)])
        return self.part(verts, faces, mat)

    def lathe(self, c, profile, mat, n=12, sx=1.0, sy=1.0, phase=0.0, axis=None):
        """Revolve [(z, r), ...] (bottom to top) around a local z axis through c. r=0 ends close to a point."""
        if axis is not None:
            A = Vector(axis).normalized(); ref = Vector((0, 0, 1)) if abs(A.z) < 0.9 else Vector((1, 0, 0))
            U = ref.cross(A).normalized(); V = A.cross(U)
            with self.frame(c, U, V, A):
                return self.lathe((0, 0, 0), profile, mat, n=n, sx=sx, sy=sy, phase=phase)
        cx, cy, cz = c; verts = []; rings = []
        for z, r in profile:
            if r <= 0:
                rings.append([len(verts)]); verts.append((cx, cy, cz + z))
            else:
                rings.append(list(range(len(verts), len(verts) + n)))
                verts += [(cx + sx * r * math.cos(phase + 2 * math.pi * k / n), cy + sy * r * math.sin(phase + 2 * math.pi * k / n), cz + z) for k in range(n)]
        faces = []; mats = []
        band = (lambda i: mat[i]) if isinstance(mat, list) else (lambda i: mat)
        for i in range(len(rings) - 1):
            a, b = rings[i], rings[i + 1]
            for k in range(n):
                j = (k + 1) % n
                if len(a) == 1:
                    faces.append([a[0], b[j], b[k]])
                elif len(b) == 1:
                    faces.append([a[k], a[j], b[0]])
                else:
                    faces.append([a[k], a[j], b[j], b[k]])
                mats.append(band(i))
        if len(rings[0]) > 1:
            faces.append(list(reversed(rings[0]))); mats.append(band(0))
        if len(rings[-1]) > 1:
            faces.append(list(rings[-1])); mats.append(band(len(rings) - 2))
        return self.part(verts, faces, mats)

    def torus(self, c, R, r, mat, n=16, m=6, mats=None):
        cx, cy, cz = c; verts = []
        for i in range(n):
            a = 2 * math.pi * i / n
            for j in range(m):
                b = 2 * math.pi * j / m; rr = R + r * math.cos(b)
                verts.append((cx + rr * math.cos(a), cy + rr * math.sin(a), cz + r * math.sin(b)))
        faces = []; fm = []
        for i in range(n):
            for j in range(m):
                i2, j2 = (i + 1) % n, (j + 1) % m
                faces.append([i * m + j, i2 * m + j, i2 * m + j2, i * m + j2]); fm.append(mats(i) if mats else mat)
        return self.part(verts, faces, fm)


    def band(self, outer, inner, z0, z1, mat):
        """Closed solid between two open plan paths of equal count (outer runs CCW round the inside), with end caps:
        a wall segment between openings."""
        n = len(outer)
        verts = [(*p, z0) for p in outer] + [(*p, z0) for p in inner] + [(*p, z1) for p in outer] + [(*p, z1) for p in inner]
        O0, I0, O1, I1 = 0, n, 2 * n, 3 * n; faces = []
        for k in range(n - 1):
            j = k + 1
            faces += [[O1 + k, O1 + j, I1 + j, I1 + k], [O0 + k, I0 + k, I0 + j, O0 + j],
                      [O0 + k, O0 + j, O1 + j, O1 + k], [I0 + k, I1 + k, I1 + j, I0 + j]]
        faces.append([O0, O1, I1, I0]); faces.append([O0 + n - 1, I0 + n - 1, I1 + n - 1, O1 + n - 1])
        return self.part(verts, faces, mat)

    def cylinder(self, a, b, r, mat, n=12):
        A = Vector(b) - Vector(a)
        return self.lathe(a, [(0, r), (A.length, r)], mat, n=n, axis=tuple(A))

    def torus_arc(self, c, R, r, a0, a1, mat, n=24, m=6, z=0.0):
        """Closed swept circle along a horizontal arc of radius R round c (angles in radians), capped at both ends."""
        path = [(c[0] + R * math.cos(a0 + (a1 - a0) * k / n), c[1] + R * math.sin(a0 + (a1 - a0) * k / n), z) for k in range(n + 1)]
        return self.tube(path, r, mat, n=m)

    def loft(self, rings, mat, caps=True):
        """Closed solid through equal-count 3D loops (CCW seen from the end the loft runs towards)."""
        n = len(rings[0]); verts = [v for r in rings for v in r]; faces = []
        for i in range(len(rings) - 1):
            for k in range(n):
                j = (k + 1) % n
                faces.append([i * n + k, i * n + j, (i + 1) * n + j, (i + 1) * n + k])
        faces.append(list(reversed(range(n)))); last = (len(rings) - 1) * n; faces.append([last + k for k in range(n)])
        return self.part(verts, faces, mat)

    def rock(self, c, size, mat, seed, n=7, m=5, embed=0.0):
        """Rounded low-poly stone: a squashed, jittered ellipsoid (closed)."""
        import random
        rnd = random.Random(seed); sx, sy, sz = size; prof = []
        for i in range(m + 1):
            t = i / m; phi = -math.pi / 2 + math.pi * t
            prof.append((math.sin(phi), math.cos(phi)))
        verts = [(c[0], c[1], c[2] - sz)]; rings = []
        for i in range(1, m):
            zr, rr = prof[i]; ring = []
            for k in range(n):
                a = 2 * math.pi * (k + 0.5 * (i % 2)) / n; j = 0.82 + 0.3 * rnd.random()
                ring.append(len(verts)); verts.append((c[0] + sx * rr * j * math.cos(a), c[1] + sy * rr * j * math.sin(a), c[2] + sz * zr * (0.85 + 0.2 * rnd.random())))
            rings.append(ring)
        top = len(verts); verts.append((c[0], c[1], c[2] + sz * 0.92)); faces = []
        for k in range(n):
            faces.append([0, rings[0][(k + 1) % n], rings[0][k]])
        for i in range(len(rings) - 1):
            a, b = rings[i], rings[i + 1]
            for k in range(n):
                j = (k + 1) % n
                faces.append([a[k], a[j], b[j]]); faces.append([a[k], b[j], b[k]])
        for k in range(n):
            faces.append([rings[-1][k], rings[-1][(k + 1) % n], top])
        return self.part(verts, faces, mat)

    def tris(self):
        return sum(len(f) - 2 for f in self.faces)

def to_object(m, mats, order, sharp_degrees=38.0):
    """A Blender object from a Mesh: materials in the kit's order, smooth shading split at sharp_degrees, planar UVs
    in half metres. Returns the object and its material names."""
    names = sorted(set(m.mats), key=list(order).index)
    data = bpy.data.meshes.new(m.name)
    data.from_pydata(m.verts, [], [list(f) for f in m.faces]); data.update()
    for n in names:
        data.materials.append(mats[n])
    index = {n: i for i, n in enumerate(names)}
    data.polygons.foreach_set('material_index', [index[n] for n in m.mats])
    data.polygons.foreach_set('use_smooth', [True] * len(data.polygons))
    data.set_sharp_from_angle(angle=math.radians(sharp_degrees))
    uv = data.uv_layers.new(name='UVMap')
    for face in data.polygons:
        drop = max(range(3), key=lambda i: abs(face.normal[i])); axes = [i for i in range(3) if i != drop]
        for li in face.loop_indices:
            co = data.vertices[data.loops[li].vertex_index].co
            uv.data[li].uv = (co[axes[0]] * 0.5, co[axes[1]] * 0.5)
    data.update()
    obj = bpy.data.objects.new(m.name, data); bpy.context.collection.objects.link(obj)
    return obj, names


def closed(m):
    """Every part closed; any inward-wound part is flipped. Returns a report."""
    edges = {}
    for f in m.faces:
        for a, b in zip(f, f[1:] + f[:1]):
            k = (min(a, b), max(a, b)); edges[k] = edges.get(k, 0) + 1
    open_edges = sum(1 for c in edges.values() if c != 2)
    flipped = 0; V = m.verts; degenerate = 0
    for part in m.parts:
        start, end = part[:2]
        vol = 0.0
        for f in m.faces[start:end]:
            a = Vector(V[f[0]])
            for i in range(1, len(f) - 1):
                vol += a.dot(Vector(V[f[i]]).cross(Vector(V[f[i + 1]]))) / 6
        if vol < 0:
            flipped += 1
            for i in range(start, end):
                m.faces[i] = tuple(reversed(m.faces[i]))
    directed = {}
    for f in m.faces:
        for a, b in zip(f, f[1:] + f[:1]):
            directed[(a, b)] = directed.get((a, b), 0) + 1
    misoriented = sum(1 for c in directed.values() if c > 1)
    for f in m.faces:
        a = Vector(V[f[0]]); area = Vector((0, 0, 0))
        for i in range(1, len(f) - 1):
            area += (Vector(V[f[i]]) - a).cross(Vector(V[f[i + 1]]) - a)
        if area.length < 1e-9:
            degenerate += 1
    return {'open_edges': open_edges, 'misoriented_edges': misoriented, 'flipped_parts': flipped, 'parts': len(m.parts), 'degenerate_faces': degenerate}


# ------------------------------------------------------------------ audits shared by every kit on this builder
SEAT_GAP = 0.01        # m: a fitting base may stand at most this far above what carries it
SEAT_SLACK = 0.005     # m: beyond its declared embedding, how much deeper a base may sit
CARRY_TOUCH = 0.01     # m: two loose parts touch when a vertex of one lies this close to the other's faces


def _triangles(meshes):
    """((a, b, c), (mesh name, part index, origin)) for every triangle of the given meshes."""
    out = []
    for m in meshes:
        for pi, part in enumerate(m.parts):
            start, end = part[:2]
            org = m.origins[pi] if pi < len(m.origins) else '?'
            for f in m.faces[start:end]:
                for i in range(1, len(f) - 1):
                    out.append(((m.verts[f[0]], m.verts[f[i]], m.verts[f[i + 1]]), (m.name, pi, org)))
    return out


def _clip(poly, a, b):
    """Keep the part of a 2D polygon left of the directed line a->b."""
    out = []

    def side(p):
        return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
    for i in range(len(poly)):
        p, q = poly[i], poly[(i + 1) % len(poly)]
        sp, sq = side(p), side(q)
        if sp >= 0:
            out.append(p)
        if (sp >= 0) != (sq >= 0):
            t = sp / (sp - sq); out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


def coplanar_overlaps(meshes, d_tol=0.0015, min_area=2e-4, limit=60):
    """Same-facing coplanar faces of different parts that overlap: they z-fight. Returns (count, samples), one sample
    per pair of kit source lines."""
    tris = _triangles(meshes); buckets = {}
    for idx, ((a, b, c), key) in enumerate(tris):
        A, B, C = Vector(a), Vector(b), Vector(c); n = (B - A).cross(C - A)
        if n.length < 1e-10:
            continue
        n.normalize(); d = n.dot(A)
        k = (round(n.x * 300), round(n.y * 300), round(n.z * 300), math.floor(d / d_tol))
        buckets.setdefault(k, []).append((idx, n, d))
    count = 0; samples = []; seen = set()
    for k, items in buckets.items():
        pool = items + buckets.get((k[0], k[1], k[2], k[3] + 1), [])
        if len(pool) < 2:
            continue
        for ii, (i, n, d) in enumerate(items):
            for (j, n2, d2) in pool[ii + 1:]:
                ki, kj = tris[i][1], tris[j][1]
                if ki == kj or abs(d - d2) > d_tol or n.dot(n2) < 0.9995:
                    continue
                U = n.orthogonal().normalized(); W = n.cross(U)
                P = [(Vector(v).dot(U), Vector(v).dot(W)) for v in tris[i][0]]
                Q = [(Vector(v).dot(U), Vector(v).dot(W)) for v in tris[j][0]]
                if (max(p[0] for p in P) <= min(q[0] for q in Q) or max(q[0] for q in Q) <= min(p[0] for p in P) or
                        max(p[1] for p in P) <= min(q[1] for q in Q) or max(q[1] for q in Q) <= min(p[1] for p in P)):
                    continue
                P = P if signed_area(P) >= 0 else P[::-1]
                Q = Q if signed_area(Q) >= 0 else Q[::-1]
                poly = P
                for e in range(3):
                    poly = _clip(poly, Q[e], Q[(e + 1) % 3])
                    if not poly:
                        break
                ar = abs(signed_area(poly)) if len(poly) >= 3 else 0.0
                if ar > min_area:
                    count += 1
                    pair = tuple(sorted((ki[2], kj[2])))
                    if len(samples) < limit and pair not in seen:
                        seen.add(pair)
                        cen = [round(sum(v[t] for v in tris[i][0]) / 3, 3) for t in range(3)]
                        samples.append({'at': cen, 'area_m2': round(ar, 5), 'parts': [list(ki), list(kj)]})
    return count, samples


def seat_failures(meshes, extra_tris=(), probe=0.3, reach=3.0, spread=0.06):
    """Every fitting registered with Mesh.fitting: rays cast along its direction (down unless it says otherwise)
    through each base (its centre and four points spread round it, so a base over a plank gap still finds the planks)
    onto everything else: the given meshes less the fitting's own parts, plus extra_tris (e.g. the exported ground).
    Each ray starts probe before the base; a hit's gap is its distance past the base along the direction (positive
    open, negative overlapping). Every surface a ray passes counts, so a post run through a deck to the pier below is
    carried by the pier. A base is ok when some hit's gap lies between minus its declared embedding (+ SEAT_SLACK) and
    its allowed gap (SEAT_GAP unless it declares one); otherwise it is floating (nearest hit beyond the gap), sunk
    (nearest overlapping) or carried by nothing. Returns (rows, failures)."""
    from mathutils.bvhtree import BVHTree
    verts, faces, owner = [], [], []
    for m in meshes:
        for pi, part in enumerate(m.parts):
            start, end = part[:2]
            for f in m.faces[start:end]:
                base = len(verts); verts += [m.verts[i] for i in f]; faces.append(list(range(base, base + len(f))))
                owner.append((m.name, pi))
    for t in extra_tris:
        base = len(verts); verts += [tuple(v) for v in t]; faces.append([base, base + 1, base + 2]); owner.append(('world', -1))
    bvh = BVHTree.FromPolygons(verts, faces)
    rows, bad = [], []
    for m in meshes:
        for s in m.seats:
            name, p0, p1 = s['own']; x, y, z = s['at']
            d = Vector(s.get('dir', (0, 0, -1)))
            gap_max = SEAT_GAP if s.get('gap') is None else s['gap']
            if abs(d.z) > 0.9:          # vertical: spread in plan
                U, W = Vector((1, 0, 0)), Vector((0, 1, 0))
            else:
                U = d.orthogonal().normalized(); W = d.cross(U)
            hits = []; sp = spread if s.get('spread') is None else s['spread']
            for dx, dy in ((0, 0), (sp, 0), (-sp, 0), (0, sp), (0, -sp))[:5 if sp > 0 else 1]:
                P = Vector((x, y, z)) + U * dx + W * dy
                o = P - d * probe; left = reach
                for _ in range(64):
                    loc, _n, idx, dist = bvh.ray_cast(o, d, left)
                    if loc is None:
                        break
                    who = owner[idx]
                    if not (who[0] == name and p0 <= who[1] < p1):
                        hits.append(((loc - P).dot(d), who[0]))
                    left -= dist + 1e-4; o = loc + d * 1e-4
            row = {'label': s['label'], 'mesh': name, 'at': [round(x, 3), round(y, 3), round(z, 4)], 'embed_allowed_m': s['embed']}
            if s.get('gap') is not None or d.z > -0.9999:
                row.update(direction=[round(c, 3) for c in d], gap_allowed_m=gap_max)
            seated = [h for h in hits if -(s['embed'] + SEAT_SLACK) <= h[0] <= gap_max]
            if seated:
                g, on = min(seated, key=lambda h: abs(h[0])); row.update(gap_m=round(g, 4), on=on, status='ok')
            elif not hits:
                row['status'] = 'nothing under the base'
            else:
                beyond = [h for h in hits if h[0] > gap_max]
                g, on = min(beyond) if beyond else max(hits)
                row.update(gap_m=round(g, 4), on=on, status='floating' if beyond else 'sunk')
            rows.append(row)
            if row['status'] != 'ok':
                bad.append(row)
    return rows, bad



def _islands(m):
    """The loose islands of a Mesh (faces connected through shared vertices), as lists of face indices."""
    parent = list(range(len(m.verts)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for f in m.faces:
        r = find(f[0])
        for v in f[1:]:
            q = find(v)
            if q != r:
                parent[q] = r
    out = {}
    for fi, f in enumerate(m.faces):
        out.setdefault(find(f[0]), []).append(fi)
    return list(out.values())


def mesh_triangles(meshes):
    """Every triangle of the given meshes as three points (to pass a mesh as world, e.g. in fixtures)."""
    return [(m.verts[f[0]], m.verts[f[i]], m.verts[f[i + 1]]) for m in meshes for f in m.faces for i in range(1, len(f) - 1)]


def carried_failures(meshes, world_tris, touch=CARRY_TOUCH, reach=0.5):
    """Every loose part must be carried, through a chain of parts that touch, by the exported world. Each mesh is split
    into loose islands; two islands touch when a vertex of one lies within touch of the other's faces or their
    triangles intersect; touching islands are joined into contact groups (union-find), and a group is carried when one
    of its islands touches world_tris the same way. Only world_tris count: pass the exported ground and solids, never
    the ship. Returns (summary, failures): each failure is an uncarried group with its size, meshes, kit source lines
    and the nearest thing to it (gap, what, where) within reach."""
    from mathutils.bvhtree import BVHTree
    isl = []                                     # (mesh, [face indices], [vertex indices])
    verts, polys, owner = [], [], []
    for m in meshes:
        base = len(verts); verts += [tuple(v) for v in m.verts]
        starts = [p[0] for p in m.parts]
        for faces in _islands(m):
            k = len(isl); vs = sorted({v for fi in faces for v in m.faces[fi]})
            parts = sorted({bisect.bisect_right(starts, fi) - 1 for fi in faces})
            isl.append((m, parts, [base + v for v in vs]))
            for fi in faces:
                polys.append([base + v for v in m.faces[fi]]); owner.append(k)
    n = len(isl)
    if not n:
        return {'islands': 0, 'groups': 0}, []
    kit = BVHTree.FromPolygons(verts, polys, epsilon=0.0)
    world = BVHTree.FromPolygons([v for t in world_tris for v in t], [[3 * i, 3 * i + 1, 3 * i + 2] for i in range(len(world_tris))],
                                 epsilon=0.0) if len(world_tris) else None
    parent = list(range(n)); grounded = [False] * n

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i

    def join(i, j):
        a, b = find(i), find(j)
        if a != b:
            parent[b] = a
    for k, (_m, _p, vs) in enumerate(isl):
        for vi in vs:
            v = Vector(verts[vi])
            for _loc, _nrm, idx, _d in kit.find_nearest_range(v, touch):
                if owner[idx] != k:
                    join(k, owner[idx])
            if world is not None and not grounded[k] and world.find_nearest(v, touch)[0] is not None:
                grounded[k] = True
    for a, b in kit.overlap(kit):
        if owner[a] != owner[b]:
            join(owner[a], owner[b])
    if world is not None:
        for a, _b in kit.overlap(world):
            grounded[owner[a]] = True
    groups = {}
    for k in range(n):
        groups.setdefault(find(k), []).append(k)
    failures = []
    for members in groups.values():
        if any(grounded[k] for k in members):
            continue
        mine = set(members); best = (float('inf'), None, None)
        for k in members:
            for vi in isl[k][2]:
                v = Vector(verts[vi])
                if world is not None:
                    loc, _nrm, _i, d = world.find_nearest(v, reach)
                    if loc is not None and d < best[0]:
                        best = (d, 'world', loc)
                for loc, _nrm, idx, d in kit.find_nearest_range(v, min(reach, best[0])):
                    if owner[idx] not in mine and d < best[0]:
                        o = isl[owner[idx]]
                        best = (d, f'{o[0].name} {o[0].origins[o[1][0]] if o[0].origins else "?"}', loc)
        lines = sorted({m.origins[p] for k in members for m, ps, _ in [isl[k]] for p in ps if p < len(m.origins)})
        lo = [min(verts[vi][c] for k in members for vi in isl[k][2]) for c in range(3)]
        hi = [max(verts[vi][c] for k in members for vi in isl[k][2]) for c in range(3)]
        failures.append({'islands': len(members), 'meshes': sorted({isl[k][0].name for k in members}), 'lines': lines[:16],
                         'bbox': [[round(c, 3) for c in lo], [round(c, 3) for c in hi]],
                         'nearest_gap_m': round(best[0], 4) if best[1] else None, 'nearest': best[1],
                         'nearest_at': [round(c, 3) for c in best[2]] if best[2] is not None else None})
    failures.sort(key=lambda f: -f['islands'])
    return {'islands': n, 'groups': len(groups), 'uncarried_groups': len(failures),
            'uncarried_islands': sum(f['islands'] for f in failures)}, failures

def audit_fixtures():
    """Known cases the three audits must classify right, run by every kit build before its own audit: the defects
    the audits exist for (a fitting standing off its support, one sunk or over nothing, a gable infill short of a
    sloped roof, two coplanar overlapping tops, a part in the air, a group of parts 2 cm short of the ground, a part
    carried only by the ship) must fail, and their fixed forms must pass. Returns one row per case; a row with ok False
    means an audit no longer catches (or wrongly flags) what it is there for."""
    def seat_case(name, expect, base, embed=0.06, direction=(0, 0, -1), gap=None, spread=None, sloped=False):
        m = Mesh(name, 0)
        if sloped:      # a roof slab rising 0.5 m per m in y, underside z = 1 + 0.5 y
            m.prism(rect(-1, -1, 1, 1), lambda x, y: 1 + 0.5 * y, lambda x, y: 1.1 + 0.5 * y, 0)
        else:           # a 1 m slab whose top is z = 0
            m.box((0, 0, -0.5), (2, 2, 1), 0)
        with m.fitting(name, embed=embed, direction=direction, gap=gap, spread=spread) as b:
            m.box((base[0], base[1], base[2] + (0.05 if direction[2] < 0 else -0.05)), (0.04, 0.04, 0.1), 0)
            b.append(base)
        _rows, bad = seat_failures([m])
        return {'case': name, 'expect': expect, 'got': 'fail' if bad else 'pass', 'ok': bool(bad) == (expect == 'fail')}

    def coplanar_case(name, expect, dz):
        m = Mesh(name, 0)
        m.box((0, 0, 0), (1, 1, 0.2), 0)
        m.box((0.5, 0, dz), (1, 0.9, 0.2), 0)       # narrower, so only the tops and bottoms can be shared
        n, _ = coplanar_overlaps([m])
        return {'case': name, 'expect': expect, 'got': 'fail' if n else 'pass', 'ok': bool(n) == (expect == 'fail')}

    ground = Mesh('ground', 0); ground.box((0, 0, -0.5), (10, 10, 1), 0)     # the world: its top is z = 0
    world = mesh_triangles([ground])

    def carried_case(name, expect, boxes, block=None):
        """Boxes (centre, size) as one kit mesh over the ground. block: a 1 m block at x 3, z 1..2 that the boxes may
        rest on, passed as 'world' (a pier) or 'ship' (built but, like the moored ship, never passed to the audit)."""
        m = Mesh(name, 0)
        for c, sz in boxes:
            m.box(c, sz, 0)
        tris = world
        if block:
            b = Mesh(block, 0); b.box((3, 0, 1.5), (1, 1, 1), 0)
            if block == 'world':
                tris = world + mesh_triangles([b])
        _s, bad = carried_failures([m], tris)
        return {'case': name, 'expect': expect, 'got': 'fail' if bad else 'pass', 'ok': bool(bad) == (expect == 'fail')}

    on_block = [((3, 0, 2.1), (0.4, 0.4, 0.22))]   # its foot 1 cm into the block's top (z 2)
    return [
        carried_case('a part in the air', 'fail', [((0, 0, 1.1), (0.4, 0.4, 0.2))]),
        carried_case('a part 1 cm into the ground', 'pass', [((0, 0, 0.09), (0.4, 0.4, 0.2))]),
        carried_case('two parts, the lower 2 cm short of the ground', 'fail',
                     [((0, 0, 0.12), (0.4, 0.4, 0.2)), ((0, 0, 0.31), (0.2, 0.2, 0.2))]),
        carried_case('two parts, the lower 1 cm into the ground', 'pass',
                     [((0, 0, 0.09), (0.4, 0.4, 0.2)), ((0, 0, 0.28), (0.2, 0.2, 0.2))]),
        carried_case('a part resting only on the ship', 'fail', on_block, block='ship'),
        carried_case('the same part resting on a pier (world)', 'pass', on_block, block='world'),
        seat_case('foot 1 cm into its slab', 'pass', (0, 0, -0.01)),
        seat_case('foot 3 cm above its slab (a floating bench)', 'fail', (0, 0, 0.03)),
        seat_case('foot 20 cm into its slab (sunk)', 'fail', (0, 0, -0.2)),
        seat_case('foot over nothing', 'fail', (3, 0, 0)),
        seat_case('gable infill 3 mm into a sloped roof', 'pass', (0, 0.2, 1.103), embed=0.005,
                  direction=(0, 0, 1), gap=0.002, spread=0, sloped=True),
        seat_case('gable infill 2 cm short of a sloped roof', 'fail', (0, 0.2, 1.08), embed=0.005,
                  direction=(0, 0, 1), gap=0.002, spread=0, sloped=True),
        coplanar_case('two slabs sharing a top face', 'fail', 0.0),
        coplanar_case('two slabs with tops 5 mm apart', 'pass', 0.005),
    ]
