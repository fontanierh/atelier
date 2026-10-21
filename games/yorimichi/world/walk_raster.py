"""Shared capsule raster, routes and clearance analysis for vehicle walking audits.

Vehicle adapters own their layouts, grid sizes and verdict policy. A Deck captures
its settings so alternating cabin/station audits never mutate shared state.
"""
import math
from collections import deque
import numpy as np

INF=1e20


def edt_1d(f):
    """Squared Euclidean distance transform of a sampled function (Felzenszwalb & Huttenlocher)."""
    n = len(f); d = [0.0] * n; v = [0] * n; z = [0.0] * (n + 1); k = 0; z[0] = -INF; z[1] = INF
    for q in range(1, n):
        while True:
            s = ((f[q] + q * q) - (f[v[k]] + v[k] * v[k])) / (2 * q - 2 * v[k])
            if s <= z[k]:
                k -= 1
                continue
            break
        k += 1; v[k] = q; z[k] = s; z[k + 1] = INF
    k = 0
    for q in range(n):
        while z[k + 1] < q:
            k += 1
        d[q] = (q - v[k]) ** 2 + f[v[k]]
    return d



def edt(blocked):
    """Distance (cells) from every cell to the nearest blocked cell."""
    f = np.where(blocked, 0.0, INF)
    for i in range(f.shape[0]):
        f[i, :] = edt_1d(list(f[i, :]))
    for j in range(f.shape[1]):
        f[:, j] = edt_1d(list(f[:, j]))
    return np.sqrt(f)



def label(mask):
    """4-connected component labels (0 = background)."""
    h, w = mask.shape; lab = np.zeros((h, w), dtype=np.int32); flat = mask.ravel(); lf = lab.ravel(); n = 0
    for start in np.flatnonzero(flat):
        if lf[start]:
            continue
        n += 1; lf[start] = n; q = deque([start])
        while q:
            c = q.popleft(); i, j = divmod(c, w)
            for nb, ok in ((c - w, i > 0), (c + w, i < h - 1), (c - 1, j > 0), (c + 1, j < w - 1)):
                if ok and flat[nb] and not lf[nb]:
                    lf[nb] = n; q.append(nb)
    return lab, n



def bfs_path(mask, a, b):
    h, w = mask.shape; flat = mask.ravel(); par = {a: -1}; q = deque([a])
    while q:
        c = q.popleft()
        if c == b:
            break
        i, j = divmod(c, w)
        for nb, ok in ((c - w, i > 0), (c + w, i < h - 1), (c - 1, j > 0), (c + 1, j < w - 1)):
            if ok and flat[nb] and nb not in par:
                par[nb] = c; q.append(nb)
    if b not in par:
        return []
    path = [b]
    while par[path[-1]] != -1:
        path.append(par[path[-1]])
    return path[::-1]



def inside_poly(X, Y, poly):
    """Even-odd point-in-polygon on grids X, Y."""
    res = np.zeros(X.shape, dtype=bool); n = len(poly)
    for k in range(n):
        (x0, y0), (x1, y1) = poly[k], poly[(k + 1) % n]
        cond = (y0 > Y) != (y1 > Y)
        with np.errstate(divide='ignore', invalid='ignore'):
            xi = x0 + (Y - y0) * (x1 - x0) / (y1 - y0)
        res ^= cond & (X < xi)
    return res



def plane(pr):
    """Least-squares planes z = a + b x + c y through a proxy's bottom and top corner heights."""
    A = np.array([[1, x, y] for x, y in pr['poly']])
    return [np.linalg.lstsq(A, np.array(pr[k]), rcond=None)[0] for k in ('z0', 'z1')]



class Deck:
    """@cc [owner:fontanierh,label:correctness] walking-raster-instance-settings
    Rasterisation, snapping and clearance analysis MUST use this instance's
    captured grid/capsule settings. Vehicle audits MUST NOT mutate shared
    settings or silently change their region, proxy or verdict policy.
    """
    def __init__(self, name, x0, x1, y0, y1, region, surface, own, *, cell=.05, radius=.22, step=.30, head=2.,
                 min_width=.9, hard_min=.6, sliver=.3, record_routes=False):
        self.name = name; self.x0, self.y0 = x0, y0
        self.cell_size,self.radius,self.step,self.head=cell,radius,step,head
        self.min_width,self.hard_min,self.sliver,self.record_routes=min_width,hard_min,sliver,record_routes
        self.xs = np.arange(x0, x1 + self.cell_size / 2, self.cell_size); self.ys = np.arange(y0, y1 + self.cell_size / 2, self.cell_size)
        self.X, self.Y = np.meshgrid(self.xs, self.ys)
        self.region = region(self.X, self.Y); self.S = surface(self.X, self.Y); self.own = own

    def cell(self, x, y):
        return int(round((y - self.y0) / self.cell_size)), int(round((x - self.x0) / self.cell_size))

    def rasterise(self, proxies):
        blocked = np.zeros(self.X.shape, dtype=bool)
        for pr in proxies:
            if pr['name'] in self.own:
                continue
            px = [p[0] for p in pr['poly']]; py = [p[1] for p in pr['poly']]
            j0, j1 = max(0, int((min(px) - self.x0) / self.cell_size) - 1), min(len(self.xs), int((max(px) - self.x0) / self.cell_size) + 2)
            i0, i1 = max(0, int((min(py) - self.y0) / self.cell_size) - 1), min(len(self.ys), int((max(py) - self.y0) / self.cell_size) + 2)
            if j0 >= j1 or i0 >= i1:
                continue
            X, Y = self.X[i0:i1, j0:j1], self.Y[i0:i1, j0:j1]
            m = inside_poly(X, Y, pr['poly'])
            if not m.any():
                continue
            (a0, b0, c0), (a1, b1, c1) = plane(pr)
            zb = a0 + b0 * X + c0 * Y; zt = a1 + b1 * X + c1 * Y; s = self.S[i0:i1, j0:j1]
            blocked[i0:i1, j0:j1] |= m & (zt > s + self.step) & (zb < s + self.head)
        self.blocked = blocked | ~self.region
        self.free = self.region & ~blocked
        self.dist = edt(self.blocked) * self.cell_size
        self.walk = self.free & (self.dist >= self.radius)
        return self

    def snap(self, x, y, reach=0.6):
        """The most open walkable cell within reach of (x, y), so a route endpoint does not set its bottleneck."""
        i, j = self.cell(x, y); k = int(reach / self.cell_size); best = None
        for di in range(-k, k + 1):
            for dj in range(-k, k + 1):
                a, b = i + di, j + dj
                if di * di + dj * dj <= k * k and 0 <= a < self.walk.shape[0] and 0 <= b < self.walk.shape[1] and self.walk[a, b]:
                    if best is None or self.dist[a, b] > best[0]:
                        best = (self.dist[a, b], a, b)
        return None if best is None else (best[1], best[2])



def bottlenecks(deck, routes):
    w = deck.walk.shape[1]
    # Fine thresholds: the largest one that still connects a route is the route's true (max-min) clear width.
    widths = [round(0.45 + 0.05 * k, 2) for k in range(22)] + [1.6, 1.8, 2.0, 2.5]
    labels = [label(deck.walk & (2 * deck.dist >= t))[0] for t in widths]
    out = []
    for name, a, b in routes:
        ca, cb = deck.snap(*a), deck.snap(*b)
        if ca is None or cb is None:
            out.append({'route': name, 'from': a, 'to': b, 'connected': False, 'note': 'endpoint not walkable'}); continue
        ok = [t for t, lab in zip(widths, labels) if lab[ca] and lab[ca] == lab[cb]]
        if not ok:
            out.append({'route': name, 'from': a, 'to': b, 'connected': False}); continue
        t = max(ok); mask = deck.walk & (2 * deck.dist >= t)
        path = bfs_path(mask, ca[0] * w + ca[1], cb[0] * w + cb[1])
        if deck.record_routes:
            deck.route_cells = getattr(deck, 'route_cells', set()) | set(path)
        cmin = min(path, key=lambda c: deck.dist.ravel()[c]); i, j = divmod(cmin, w)
        width = round(float(2 * deck.dist[i, j]), 2)        # in [t, next threshold): every route crosses its bottleneck
        out.append({'route': name, 'from': a, 'to': b, 'connected': True, 'bottleneck_width_m': width,
                    'bottleneck_at': [round(float(deck.xs[j]), 2), round(float(deck.ys[i]), 2)],
                    'meets_0.9': width >= deck.min_width, 'meets_hard_0.6': width >= deck.hard_min})
    return out



def pinch_points(deck, comp_ids, lab, report_below=1.2):
    """Saddles of the clearance field: cells on a corridor's centre ridge whose clearance is a local minimum along
    the ridge (a narrowing between two obstacles), reported where the clear width is under report_below."""
    d = deck.dist; h, w = d.shape; ridge = np.zeros_like(deck.walk)
    pad = np.pad(d, 1, constant_values=0)
    c = pad[1:-1, 1:-1]
    for (a, b) in (((0, 1), (2, 1)), ((1, 0), (1, 2)), ((0, 0), (2, 2)), ((0, 2), (2, 0))):
        n1 = pad[a[0]:a[0] + h, a[1]:a[1] + w]; n2 = pad[b[0]:b[0] + h, b[1]:b[1] + w]
        ridge |= (c >= n1) & (c >= n2) & ((c > n1) | (c > n2))   # a crest across the corridor, not along it
    cand = ridge & deck.walk & (2 * d < report_below) & np.isin(lab, list(comp_ids))
    saddle = np.zeros_like(cand)
    for i, j in zip(*np.nonzero(cand)):
        nb = [(i + a, j + b) for a in (-1, 0, 1) for b in (-1, 0, 1) if (a or b) and 0 <= i + a < h and 0 <= j + b < w and ridge[i + a, j + b]]
        if len(nb) < 2 or any(d[p] < d[i, j] - 1e-9 for p in nb):
            continue
        if max(abs(p[0] - q[0]) + abs(p[1] - q[1]) for p in nb for q in nb) >= 3:   # ridge continues on both sides
            saddle[i, j] = True
    plab, n = label(saddle | (cand & np.pad(saddle, 1)[0:-2, 1:-1]) | (cand & np.pad(saddle, 1)[2:, 1:-1]))
    out = []
    for k in range(1, n + 1):
        ii, jj = np.nonzero(plab == k)
        m = int(np.argmin(d[ii, jj])); i, j = ii[m], jj[m]
        extent = math.hypot((jj.max() - jj.min()) * deck.cell_size, (ii.max() - ii.min()) * deck.cell_size)
        width = round(float(2 * d[i, j]), 2)
        out.append({'at': [round(float(deck.xs[j]), 2), round(float(deck.ys[i]), 2)], 'clear_width_m': width,
                    'length_m': round(extent, 2),
                    'status': 'ok (>= 0.9 m)' if width >= deck.min_width else ('isolated pinch (>= 0.6 m, documented)' if width >= deck.hard_min and extent <= 1.5 else 'too narrow')})
    return out



def pockets(deck):
    reach = edt(deck.walk) * deck.cell_size <= deck.radius + deck.cell_size * 0.75   # within the capsule's sweep of some walkable centre
    pocket = deck.free & ~reach
    swept = deck.free & reach
    plab, n = label(pocket); out = []; slivers = []
    for k in range(1, n + 1):
        ii, jj = np.nonzero(plab == k)
        width = float(2 * deck.dist[ii, jj].max())
        if len(ii) * deck.cell_size * deck.cell_size < 0.02:
            continue
        touch = any(swept[a, b] for i, j in zip(ii, jj) for a, b in ((i - 1, j), (i + 1, j), (i, j - 1), (i, j + 1))
                    if 0 <= a < swept.shape[0] and 0 <= b < swept.shape[1])
        if not touch:                                         # sealed off (e.g. outboard of a rail): unreachable
            continue
        if round(width, 2) <= deck.sliver:      # far narrower than the capsule (0.44 m): the body cannot enter, so it cannot be trapped
            slivers.append(width); continue
        out.append({'at': [round(float(deck.xs[jj].mean()), 2), round(float(deck.ys[ii].mean()), 2)],
                    'area_m2': round(len(ii) * deck.cell_size * deck.cell_size, 3), 'max_width_m': round(width, 2)})
    return out, {'count': len(slivers), 'max_width_m': round(max(slivers), 2) if slivers else 0.0,
                 'note': f'unswept slots no wider than {deck.sliver} m (behind rails, bench backs, davit feet): the capsule cannot enter'}



def draw(deck, pinches, routes, marks, path, pockets_=(), scale=40, *, image, image_draw):
    h, w = deck.walk.shape
    img = np.zeros((h, w, 3), dtype=np.uint8); img[:] = (250, 250, 250)
    img[deck.region] = (215, 225, 236)
    img[deck.region & deck.blocked] = (110, 112, 118)
    img[deck.free & ~deck.walk] = (238, 170, 160)
    img[deck.walk] = (150, 205, 140)
    im = image.fromarray(img[::-1]).resize((int(w * deck.cell_size * scale), int(h * deck.cell_size * scale)), image.NEAREST)
    d = image_draw.Draw(im)
    to = lambda x, y: ((x - deck.x0) * scale, im.height - (y - deck.y0) * scale)
    for p in pinches:
        x, y = to(*p['at']); col = (30, 30, 200) if p['status'].startswith('ok') else ((200, 120, 0) if p['status'].startswith('isolated') else (200, 30, 30))
        d.ellipse((x - 6, y - 6, x + 6, y + 6), outline=col, width=2); d.text((x + 7, y - 14), f"{p['clear_width_m']:.2f} m", fill=col)
    for r in routes:
        if r.get('connected'):
            x, y = to(*r['bottleneck_at']); d.rectangle((x - 4, y - 4, x + 4, y + 4), outline=(20, 20, 120), width=2)
            d.text((x + 6, y + 2), f"{r['bottleneck_width_m']:.2f}", fill=(20, 20, 120))
    for p in pockets_:
        x, y = to(*p['at']); d.rectangle((x - 7, y - 7, x + 7, y + 7), outline=(160, 0, 160), width=3); d.text((x + 9, y), 'pocket', fill=(160, 0, 160))
    for label_, x, y, col in marks:
        px, py = to(x, y); d.polygon([(px, py - 9), (px - 7, py + 5), (px + 7, py + 5)], fill=col); d.text((px + 9, py - 6), label_, fill=col)
    d.text((8, 6), f'{deck.name}: green = capsule-centre walkable (r 0.22 m), pink = within capsule radius of an obstacle, grey = blocked 0.3-2.0 m above deck. '
                   'Circles: pinch points (clear width). Squares: route bottlenecks.', fill=(30, 30, 30))
    im.save(path)
