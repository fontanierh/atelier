"""The haul rope: one source of truth for its path, tangent and the grip frame on it (plain Python).

Every rope mesh (station loops, review spans, the tileable detail segment) and every cabin placement (berths, the
swept loop, tower passes) comes from a RopePath, so later sag and route fitting cannot separate the rope from the grip.
A RopePath is a densely sampled 3D polyline with arc length; rope_point(s) and rope_tangent(s) interpolate it and
grip_frame(s, outward) gives the grip's frame: x along the tangent, z up (orthogonalised), y = z cross x, with the
cabin's door side (local -y) turned towards `outward`. Only the grip takes that frame: hang_frame(G, pivot) gives the
plumb frame (heading only) of the hanger and cabin, which hang from the grip's pivot pin with the floor level.

Rope construction (review and detail meshes): six helical strands round a core, lay length 6.5 rope diameters; the
strands' outer crowns touch the rope radius exactly, which is also the grip's jaw groove radius.
"""
import math

STRANDS = 6
LAY = 6.5          # lay length in rope diameters


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    L = math.sqrt(_dot(a, a))
    return _mul(a, 1.0 / L) if L > 1e-12 else a


class RopePath:
    def __init__(self, points, radius):
        pts = [tuple(map(float, p)) for p in points]
        self.pts = [pts[0]] + [p for i, p in enumerate(pts[1:], 1) if math.dist(p, pts[i - 1]) > 1e-9]
        self.r = radius
        self.s = [0.0]
        for a, b in zip(self.pts[:-1], self.pts[1:]):
            self.s.append(self.s[-1] + math.dist(a, b))
        self.length = self.s[-1]

    def _seg(self, s):
        s = min(max(s, 0.0), self.length)
        lo, hi = 0, len(self.s) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if self.s[mid] <= s:
                lo = mid
            else:
                hi = mid
        return lo, s

    def rope_point(self, s):
        i, s = self._seg(s); a, b = self.pts[i], self.pts[i + 1]; L = self.s[i + 1] - self.s[i]
        t = (s - self.s[i]) / L if L else 0.0
        return _add(a, _mul(_sub(b, a), t))

    def rope_tangent(self, s, h=0.05):
        return _norm(_sub(self.rope_point(min(self.length, s + h)), self.rope_point(max(0.0, s - h))))

    def grip_frame(self, s, outward):
        """4x4 row-major matrix (list of rows) of the grip at s; local -y points to the `outward` side."""
        x = self.rope_tangent(s); z = _norm(_sub((0, 0, 1), _mul(x, x[2]))); y = _cross(z, x)
        if _dot(y, outward) > 0:          # the door side (local -y) must face outward: turn half round the up axis
            x = _mul(x, -1); y = _mul(y, -1)
        o = self.rope_point(s)
        return [[x[0], y[0], z[0], o[0]], [x[1], y[1], z[1], o[1]], [x[2], y[2], z[2], o[2]], [0, 0, 0, 1]]

    def nearest(self, p, near=None, window=0.6):
        """(distance, arc length) from point p to the rope axis; `near` limits the search to +-window."""
        best = (1e30, 0.0); lo, hi = 0, len(self.pts) - 1
        if near is not None:
            lo = max(0, self._seg(near - window)[0]); hi = min(len(self.pts) - 1, self._seg(near + window)[0] + 1)
        for i, (a, b) in enumerate(zip(self.pts[lo:hi], self.pts[lo + 1:hi + 1]), lo):
            ab = _sub(b, a); L2 = _dot(ab, ab)
            t = 0.0 if L2 == 0 else max(0.0, min(1.0, _dot(_sub(p, a), ab) / L2))
            d = math.dist(p, _add(a, _mul(ab, t)))
            if d < best[0]:
                best = (d, self.s[i] + t * math.sqrt(L2))
        return best

    def nearest_distance(self, p, near=None, window=0.6):
        """Distance from point p to the rope axis (polyline); `near` (an arc length) limits the search to +-window."""
        best = 1e30; lo, hi = 0, len(self.pts) - 1
        if near is not None:
            lo = max(0, self._seg(near - window)[0]); hi = min(len(self.pts) - 1, self._seg(near + window)[0] + 1)
        for a, b in zip(self.pts[lo:hi], self.pts[lo + 1:hi + 1]):
            ab = _sub(b, a); L2 = _dot(ab, ab)
            t = 0.0 if L2 == 0 else max(0.0, min(1.0, _dot(_sub(p, a), ab) / L2))
            best = min(best, math.dist(p, _add(a, _mul(ab, t))))
        return best

    def resampled(self, step):
        n = max(1, int(math.ceil(self.length / step)))
        return [self.rope_point(self.length * k / n) for k in range(n + 1)]


def hang_frame(G, pivot):
    """The frame of everything that hangs from the grip's pivot pin (hanger, cabin body, doors), for a grip frame G
    (rows, as grip_frame returns). The cabin hangs plumb under gravity: its x axis is the grip's heading turned level,
    its z axis is world up (no pitch, no roll), and the pivot point, fixed in the grip, is the same point in both
    frames. On a level rope the two frames coincide."""
    gx = (G[0][0], G[1][0], G[2][0]); h = _norm((gx[0], gx[1], 0.0)); z = (0.0, 0.0, 1.0); y = _cross(z, h)
    px, py, pz = pivot
    w = tuple(G[i][0] * px + G[i][1] * py + G[i][2] * pz + G[i][3] for i in range(3))
    o = _sub(w, _add(_add(_mul(h, px), _mul(y, py)), _mul(z, pz)))
    return [[h[0], y[0], z[0], o[0]], [h[1], y[1], z[1], o[1]], [h[2], y[2], z[2], o[2]], [0, 0, 0, 1]]


def strand_rings(path, start=0.0, end=None, sides=6, step=None):
    """Six helical strands along a RopePath: returns [(strand radius, [centre points])] plus the core radius."""
    r = path.r; rs = r / 3.0; rc = r - rs; lay = LAY * 2 * r
    end = path.length if end is None else end; step = step or lay / 14
    n = max(2, int(math.ceil((end - start) / step))); out = []
    frames = []
    for k in range(n + 1):
        s = start + (end - start) * k / n; t = path.rope_tangent(s)
        ref = (0, 0, 1) if abs(t[2]) < 0.9 else (1, 0, 0)
        u = _norm(_cross(ref, t)); v = _cross(t, u); frames.append((s, path.rope_point(s), u, v))
    for j in range(STRANDS):
        pts = []
        for s, o, u, v in frames:
            a = 2 * math.pi * (s / lay) + 2 * math.pi * j / STRANDS
            pts.append(_add(o, _add(_mul(u, rc * math.cos(a)), _mul(v, rc * math.sin(a)))))
        out.append((rs, pts))
    return out, rc * 0.95


# ------------------------------------------------------------------ path factories
def straight(a, b, radius, step=0.05):
    n = max(1, int(math.dist(a, b) / step))
    return RopePath([_add(a, _mul(_sub(b, a), k / n)) for k in range(n + 1)], radius)


def sagging_span(half, sag, radius, step=0.5):
    """A sagging span between two supports at x = +-half: a parabola (the catenary's small-sag form) whose lowest point,
    at mid-span, lies `sag` below the supports."""
    n = max(2, int(round(2 * half / step)))
    return RopePath([(-half + 2 * half * k / n, 0.0, sag * ((-half + 2 * half * k / n) / half) ** 2) for k in range(n + 1)], radius)


def over_tower(H, y, radius, half_train=1.6, deflection_deg=3.0, span=30.0, step=0.05):
    """A rope crossing a tower: level over the sheave train, falling away at the deflection angle on both sides,
    with a fillet over the end sheaves (radius 60 m)."""
    k = math.tan(math.radians(deflection_deg)); Rf = 60.0; xf = Rf * k / 2
    pts = []; x = -span
    while x <= span + 1e-9:
        ax = abs(x)
        if ax <= half_train:
            dz = 0.0
        elif ax <= half_train + 2 * xf:
            dz = -((ax - half_train) ** 2) * k / (4 * xf)          # parabolic blend from level to the deflection slope
        else:
            dz = -k * (ax - half_train - xf)
        pts.append((x, y, H + dz)); x += step
    return RopePath(pts, radius)


def station_loop(R, z_line, z_station, x_mouth, radius, x_ramp=1.6, step=0.05):
    """The station's stretch: in from the line at z_line, down a short ramp to z_station (the rope drops away from
    the opened grips), round the bullwheel (radius R at the origin) and back out. Starts and ends 0.6 m past the mouth."""
    pts = []; x0 = x_mouth + 0.6; xr = x_mouth - x_ramp

    def zf(x):
        if x >= x_mouth:
            return z_line
        if x <= xr:
            return z_station
        t = (x - xr) / (x_mouth - xr)
        return z_station + (z_line - z_station) * (3 * t * t - 2 * t ** 3)
    n = int((x0 - 0.0) / step)
    for k in range(n + 1):
        x = x0 - (x0 - 0.0) * k / n; pts.append((x, -R, zf(x)))
    m = int(math.pi * R / step)
    for k in range(1, m):
        a = -math.pi / 2 - math.pi * k / m; pts.append((R * math.cos(a), R * math.sin(a), z_station))
    for k in range(n + 1):
        x = x0 * k / n; pts.append((x, R, zf(x)))
    return RopePath(pts, radius)
