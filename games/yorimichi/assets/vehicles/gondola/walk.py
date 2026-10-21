"""Walkability audit of the gondola cabin and the three stations, from the same collision proxies that build.py
exports as UCX hulls for Unreal.

uv run python games/yorimichi/assets/vehicles/gondola/walk.py
Reads build/yorimichi/gondola/layout_<piece>.json (written by build.py) and writes, under build/yorimichi/gondola/review/:
walk_report.json and one top-down layout image per piece (walk_cabin.png, walk_valley.png, walk_rim.png,
walk_crater.png).

The walking surface is the platform (z = 0), plus ramps (the rim boardwalk) and stairs (the crater stair) from the
layout. A cell is blocked when any proxy covers it in plan, with any part of its height between 0.30 m (the step
limit) and 2.0 m (required headroom) above the surface there. The player capsule's centre (radius 0.22 m) may stand
where the clearance to the nearest blocked cell is at least the radius. Clear width at a point is twice that
clearance; routes report their bottleneck (max-min) width. Trapping pockets are free cells, reachable from the open
floor, that the capsule cannot sweep; unswept slots no wider than 0.3 m are listed separately as slivers. Station
layouts have a cabin standing in each berth with its doors open, so the boarding routes run into the cabins.

The raster analysis (distance transform, labels, bottlenecks, pinch points, pockets, drawing) is the ferry's walk.py
core; the ferry is not on main yet, so it is carried here until both can share one module.
"""
import json
import hashlib
import math
from collections import deque
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[5]
OUT = REPO / 'build' / 'yorimichi' / 'gondola'
REVIEW = OUT / 'review'
CELL = 0.05
RADIUS = 0.22
STEP, HEAD = 0.30, 2.0       # step limit and required headroom (m)
MIN_WIDTH, HARD_MIN = 0.9, 0.6
RISER_MAX, TREAD_MIN = 0.30, 0.25
DOOR_MIN = (0.9, 2.0)        # cabin door clear width and height (m)
BOARDING_GAP_MIN, BOARDING_GAP_MAX = 0.05, 0.12   # berth: cabin door sill to the platform edge, across (m)
SILL_MIN, SILL_MAX = 0.0, 0.03                    # berth: the cabin sill above the platform (m)
CAPSULE_HALF_HEIGHT = 0.755
SLIVER = 2 * RADIUS          # an unswept slot narrower than the capsule cannot be entered, so it cannot trap
INF = 1e20


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
    def __init__(self, name, x0, x1, y0, y1, region, surface, own):
        self.name = name; self.x0, self.y0 = x0, y0
        self.xs = np.arange(x0, x1 + CELL / 2, CELL); self.ys = np.arange(y0, y1 + CELL / 2, CELL)
        self.X, self.Y = np.meshgrid(self.xs, self.ys)
        self.region = region(self.X, self.Y); self.S = surface(self.X, self.Y); self.own = own

    def cell(self, x, y):
        return int(round((y - self.y0) / CELL)), int(round((x - self.x0) / CELL))

    def rasterise(self, proxies):
        blocked = np.zeros(self.X.shape, dtype=bool)
        for pr in proxies:
            if pr['name'] in self.own:
                continue
            px = [p[0] for p in pr['poly']]; py = [p[1] for p in pr['poly']]
            j0, j1 = max(0, int((min(px) - self.x0) / CELL) - 1), min(len(self.xs), int((max(px) - self.x0) / CELL) + 2)
            i0, i1 = max(0, int((min(py) - self.y0) / CELL) - 1), min(len(self.ys), int((max(py) - self.y0) / CELL) + 2)
            if j0 >= j1 or i0 >= i1:
                continue
            X, Y = self.X[i0:i1, j0:j1], self.Y[i0:i1, j0:j1]
            m = inside_poly(X, Y, pr['poly'])
            if not m.any():
                continue
            (a0, b0, c0), (a1, b1, c1) = plane(pr)
            zb = a0 + b0 * X + c0 * Y; zt = a1 + b1 * X + c1 * Y; s = self.S[i0:i1, j0:j1]
            blocked[i0:i1, j0:j1] |= m & (zt > s + STEP) & (zb < s + HEAD)
        self.blocked = blocked | ~self.region
        self.free = self.region & ~blocked
        self.dist = edt(self.blocked) * CELL
        self.walk = self.free & (self.dist >= RADIUS)
        return self

    def snap(self, x, y, reach=0.6):
        """The most open walkable cell within reach of (x, y), so a route endpoint does not set its bottleneck."""
        i, j = self.cell(x, y); k = int(reach / CELL); best = None
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
        deck.route_cells = getattr(deck, 'route_cells', set()) | set(path)
        cmin = min(path, key=lambda c: deck.dist.ravel()[c]); i, j = divmod(cmin, w)
        width = round(float(2 * deck.dist[i, j]), 2)        # in [t, next threshold): every route crosses its bottleneck
        out.append({'route': name, 'from': a, 'to': b, 'connected': True, 'bottleneck_width_m': width,
                    'bottleneck_at': [round(float(deck.xs[j]), 2), round(float(deck.ys[i]), 2)],
                    'meets_0.9': width >= MIN_WIDTH, 'meets_hard_0.6': width >= HARD_MIN})
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
        extent = math.hypot((jj.max() - jj.min()) * CELL, (ii.max() - ii.min()) * CELL)
        width = round(float(2 * d[i, j]), 2)
        out.append({'at': [round(float(deck.xs[j]), 2), round(float(deck.ys[i]), 2)], 'clear_width_m': width,
                    'length_m': round(extent, 2),
                    'status': 'ok (>= 0.9 m)' if width >= MIN_WIDTH else ('isolated pinch (>= 0.6 m, documented)' if width >= HARD_MIN and extent <= 1.5 else 'too narrow')})
    return out


def pockets(deck):
    reach = edt(deck.walk) * CELL <= RADIUS + CELL * 0.75   # within the capsule's sweep of some walkable centre
    pocket = deck.free & ~reach
    swept = deck.free & reach
    plab, n = label(pocket); out = []; slivers = []
    for k in range(1, n + 1):
        ii, jj = np.nonzero(plab == k)
        width = float(2 * deck.dist[ii, jj].max())
        if len(ii) * CELL * CELL < 0.02:
            continue
        touch = any(swept[a, b] for i, j in zip(ii, jj) for a, b in ((i - 1, j), (i + 1, j), (i, j - 1), (i, j + 1))
                    if 0 <= a < swept.shape[0] and 0 <= b < swept.shape[1])
        if not touch:                                         # sealed off (e.g. outboard of a rail): unreachable
            continue
        if round(width, 2) <= SLIVER:      # far narrower than the capsule (0.44 m): the body cannot enter, so it cannot be trapped
            slivers.append(width); continue
        out.append({'at': [round(float(deck.xs[jj].mean()), 2), round(float(deck.ys[ii].mean()), 2)],
                    'area_m2': round(len(ii) * CELL * CELL, 3), 'max_width_m': round(width, 2)})
    return out, {'count': len(slivers), 'max_width_m': round(max(slivers), 2) if slivers else 0.0,
                 'note': f'unswept slots no wider than {SLIVER} m (behind rails, bench backs, davit feet): the capsule cannot enter'}



def draw(deck, pinches, routes, marks, path, pockets_=(), scale=40):
    h, w = deck.walk.shape
    img = np.zeros((h, w, 3), dtype=np.uint8); img[:] = (250, 250, 250)
    img[deck.region] = (215, 225, 236)
    img[deck.region & deck.blocked] = (110, 112, 118)
    img[deck.free & ~deck.walk] = (238, 170, 160)
    img[deck.walk] = (150, 205, 140)
    try:
        from PIL import Image, ImageDraw            # only for the review image; the audit itself needs numpy alone
    except ImportError:
        return
    im = Image.fromarray(img[::-1]).resize((int(w * CELL * scale), int(h * CELL * scale)), Image.NEAREST)
    d = ImageDraw.Draw(im)
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




# ------------------------------------------------------------------ gondola pieces
def path_s(X, Y, line):
    """Distance along a centreline polyline of the nearest point to (X, Y): a ramp that follows a curved path."""
    best = np.full(X.shape, np.inf); out = np.zeros(X.shape); s0 = 0.0
    for p, q in zip(line[:-1], line[1:]):
        dx, dy = q[0] - p[0], q[1] - p[1]; L2 = dx * dx + dy * dy
        t = np.clip(((X - p[0]) * dx + (Y - p[1]) * dy) / L2, 0.0, 1.0)
        dd = (X - p[0] - t * dx) ** 2 + (Y - p[1] - t * dy) ** 2
        better = dd < best; best = np.where(better, dd, best); out = np.where(better, s0 + t * np.sqrt(L2), out)
        s0 += np.sqrt(L2)
    return out


def surface_fn(surfaces):
    """Walking-surface height: 0 by default, planes and stairs where the layout has them."""
    def S(X, Y):
        z = np.zeros(X.shape)
        for s in surfaces:
            m = inside_poly(X, Y, s['poly'])
            if 'plane' in s:
                a, b, c = s['plane']; z = np.where(m, a + b * X + c * Y, z)
            elif 'path' in s:
                z = np.where(m, -path_s(X, Y, s['path']) * s['grade'], z)
            elif 'stair' in s:
                st = s['stair']; k = np.ceil((Y - st['y0']) / st['tread'] - 1e-9)
                z = np.where(m, np.maximum(st['bottom_z'], st['top_z'] - st['rise'] * np.maximum(k, 0)), z)
            else:
                z = np.where(m, s['z'], z)
        return z
    return S


def union_fn(polys):
    def R(X, Y):
        r = np.zeros(X.shape, dtype=bool)
        for p in polys:
            r |= inside_poly(X, Y, p)
        return r
    return R


def analyse(deck, pts, routes, image):
    lab, n = label(deck.walk)
    comps = {int(lab[deck.snap(*p)]) for p in pts.values() if deck.snap(*p)} or set(range(1, n + 1))
    rts = bottlenecks(deck, routes); pin = pinch_points(deck, comps, lab); poc, sliv = pockets(deck)
    # A narrowing that no route passes through (a notch beside a gate post, a gap behind a bench) is not a pinch
    # on a walkable route: it is kept in the list and labelled as such.
    w = deck.walk.shape[1]; near = max(1, int(0.15 / CELL)); cells = getattr(deck, 'route_cells', set())
    on_route = np.zeros(deck.walk.shape, dtype=bool)
    for c in cells:
        i, j = divmod(c, w); on_route[max(0, i - near):i + near + 1, max(0, j - near):j + near + 1] = True
    for p in pin:
        i, j = deck.cell(*p['at'])
        p['on_route'] = bool(on_route[i, j])
        if not p['on_route'] and p['clear_width_m'] < MIN_WIDTH:
            p['status'] = 'off-route notch (no route passes)'
    marks = [(k, x, y, (220, 110, 0)) for k, (x, y) in pts.items()]
    draw(deck, pin, rts, marks, REVIEW / image, poc, scale=260 if CELL < 0.04 else 24)
    main_area = max((int((lab == c).sum()) for c in comps), default=0)
    return {'walkable_area_m2': round(float(deck.walk.sum() * CELL * CELL), 1), 'components': n,
            'main_component_area_m2': round(main_area * CELL * CELL, 1),
            'routes': rts, 'pinch_points': pin, 'trapping_pockets': poc, 'slivers': sliv, 'image': f'review/{image}'}


def cabin_report():
    global CELL
    CELL = 0.02
    L = json.loads((OUT / 'layout_cabin.json').read_text())
    z = L['floor_z']; d = L['door']; inner = [tuple(p) for p in L['interior']]
    x0, x1 = d['x']; apron = [(x0 - 1.0, d['y_outer'] - 1.6), (x1 + 1.0, d['y_outer'] - 1.6), (x1 + 1.0, d['y_outer']), (x0 - 1.0, d['y_outer'])]
    strip = [(x0, d['y_outer']), (x1, d['y_outer']), (x1, d['y_inner'] + 0.01), (x0, d['y_inner'] + 0.01)]
    region = [inner, strip, apron]
    proxies = [dict(p, z0=[v - z for v in p['z0']], z1=[v - z for v in p['z1']]) for p in L['proxies'] if p['name'] != 'cabin floor']
    xs = [p[0] for p in inner]; ys = [p[1] for p in inner]
    deck = Deck('cabin (doors open, platform apron outside the door)', min(xs) - 0.6, max(xs) + 0.6, d['y_outer'] - 1.7, max(ys) + 0.1,
                union_fn(region), lambda X, Y: np.zeros(X.shape), set()).rasterise(proxies)
    b = L['benches']
    pts = {'platform apron': (0.0, d['y_outer'] - 0.7), 'door': (0.0, (d['y_outer'] + d['y_inner']) / 2), 'centre': (0.0, 0.0),
           'east bench front': (b['east'][0] - 0.3, 0.2), 'west bench front': (b['west'][1] + 0.3, 0.2), 'back bench front': (0.0, b['back_y'][0] - 0.3)}
    routes = [(f'platform apron -> {k}', pts['platform apron'], v) for k, v in pts.items() if k != 'platform apron']
    rep = analyse(deck, pts, routes, 'walk_cabin.png')
    xi = max(xs)
    rep['door'] = {'clear_width_m': round(x1 - x0, 3), 'clear_height_m': d['clear_height'], 'required_m': list(DOOR_MIN),
                   'ok': (x1 - x0) >= DOOR_MIN[0] and d['clear_height'] >= DOOR_MIN[1]}
    rep['headroom_m'] = L['headroom']; rep['aisle_between_side_benches_m'] = round(b['east'][0] - b['west'][1], 3)
    rep['bench_seat_height_m'] = b['seat_height']; rep['interior_floor_m'] = [round(2 * xi, 3), round(max(ys) - min(ys), 3)]
    return rep


def station_deck(L,key):
    global CELL
    CELL = 0.05
    polys = [[tuple(q) for q in r] for r in L['regions']] + [[tuple(q) for q in s['poly']] for s in L.get('surfaces', [])]
    allx = [q[0] for p in polys for q in p]; ally = [q[1] for p in polys for q in p]
    return Deck(f'{key} station (cabins in both berths, doors open)', min(allx) - 0.3, max(allx) + 0.3, min(ally) - 0.3, max(ally) + 0.3,
                union_fn(polys), surface_fn(L.get('surfaces', [])), set()).rasterise(L['obstacles'])


def station_routes(L,key):
    """Native driving waypoints use the same capsule raster as the kit audit."""
    deck=station_deck(L,key);w=deck.walk.shape[1];routes={}
    start=deck.snap(*L['access'][0]['point'])
    if start is None:raise ValueError('Station access has no walking cell')
    for berth in L['berths']:
        end=deck.snap(*berth['cabin_grip'][:2],reach=.2)
        if end is None:raise ValueError('Station berth has no walking cell')
        path=bfs_path(deck.walk,start[0]*w+start[1],end[0]*w+end[1])
        if not path:raise ValueError('No capsule route from station access to cabin')
        cells=[divmod(c,w) for c in path]
        # Drop only collinear intermediate cells. Corners and staircase points
        # remain, so the live drive follows the audited route rather than a chord.
        keep=[cells[0]]
        for i in range(1,len(cells)-1):
            a,b,c=cells[i-1:i+2]
            if (b[0]-a[0],b[1]-a[1])!=(c[0]-b[0],c[1]-b[1]):keep.append(b)
        keep.append(cells[-1])
        routes[str(berth['side'])]=[[float(deck.xs[j]),float(deck.ys[i]),float(deck.S[i,j])] for i,j in keep]
    return routes


def station_report(key):
    L = json.loads((OUT / f'layout_{key}.json').read_text())
    deck=station_deck(L,key)
    pts = {}
    for a in L['access']:
        pts[a['name']] = tuple(a['point'])
    for b in L['berths']:
        s = b['side']; x = b['cabin_grip'][0]; ye = b['platform_edge']['y']
        pts[f'berth {s:+d} platform'] = (x, ye + s * 0.8)
        pts[f'berth {s:+d} cabin'] = (x, b['cabin_grip'][1])
    for name, p in L.get('points', {}).items():
        pts[name] = tuple(p)
    first = L['access'][0]['name']
    routes = [(f'{first} -> {k}', pts[first], v) for k, v in pts.items() if k != first]
    rep = analyse(deck, pts, routes, f'walk_{key}.png')
    rep['boarding'] = [{'side': b['side'], 'door_centre': b['door_centre'], 'gate_x': b['platform_edge']['x'],
                        'door_within_gate': (b['platform_edge']['x'][0] <= b['door_centre'][0] - b['door_clear_width'] / 2
                                             and b['door_centre'][0] + b['door_clear_width'] / 2 <= b['platform_edge']['x'][1]),
                        'gap_door_to_edge_m': b['gap_door_to_edge_m'], 'sill_above_platform_m': b['door_centre'][2],
                        'gap_ok': BOARDING_GAP_MIN - 1e-9 <= b['gap_door_to_edge_m'] <= BOARDING_GAP_MAX + 1e-9,
                        'sill_ok': SILL_MIN - 1e-9 <= b['door_centre'][2] <= SILL_MAX + 1e-9} for b in L['berths']]
    rep['stairs'] = [dict(s, riser_ok=s['riser_m'] <= RISER_MAX + 1e-9, tread_ok=s['tread_m'] >= TREAD_MIN - 1e-9,
                          width_ok=s['width_m'] >= MIN_WIDTH) for s in L['stairs']]
    return rep


def verdict(r):
    """The reasons one piece fails the walk audit (empty when it passes)."""
    why = [f'route {x["route"]}: ' + ('not connected' if not x.get('connected') else f'bottleneck {x.get("bottleneck_width_m")} m < {MIN_WIDTH} m')
           for x in r['routes'] if not x.get('connected') or not x.get('meets_0.9')]
    why += [f'pinch {p["clear_width_m"]} m at {p["at"]}' for p in r['pinch_points'] if p['status'] == 'too narrow']
    why += [f'trapping pocket at {p.get("at")}' for p in r['trapping_pockets']]
    why += [f'stair at {s["x"]}, {s["y"]}: riser {s["riser_m"]} / tread {s["tread_m"]} / width {s["width_m"]}'
            for s in r.get('stairs', []) if not (s['riser_ok'] and s['tread_ok'] and s['width_ok'])]
    if 'door' in r and not r['door']['ok']:
        why.append(f'cabin door {r["door"]["clear_width_m"]} x {r["door"]["clear_height_m"]} m under {DOOR_MIN}')
    for b in r.get('boarding', []):
        if not b['door_within_gate']:
            why.append(f'berth {b["side"]:+d}: door outside the gate')
        if not b.get('gap_ok', True):
            why.append(f'berth {b["side"]:+d}: boarding gap {b["gap_door_to_edge_m"]} m outside {BOARDING_GAP_MIN}..{BOARDING_GAP_MAX} m')
        if not b.get('sill_ok', True):
            why.append(f'berth {b["side"]:+d}: sill {b["sill_above_platform_m"]} m above the platform, outside {SILL_MIN}..{SILL_MAX} m')
    return why


def audit(quiet=False):
    """Run the walk audit on the layouts build.py wrote; returns (report, list of failures). Writes walk_report.json
    and (when PIL is available) the review images."""
    REVIEW.mkdir(parents=True, exist_ok=True)
    report = {'capsule': {'radius_m': RADIUS, 'half_height_m': CAPSULE_HALF_HEIGHT},
              'rules': {'min_clear_width_m': MIN_WIDTH, 'headroom_m': HEAD, 'step_m': STEP, 'riser_max_m': RISER_MAX, 'tread_min_m': TREAD_MIN,
                        'door_min_m': list(DOOR_MIN), 'boarding_gap_m': [BOARDING_GAP_MIN, BOARDING_GAP_MAX], 'sill_m': [SILL_MIN, SILL_MAX]},
              'source': 'collision proxies = the UCX hulls in assets/GD_*_Collision.fbx', 'pieces': {}}
    report['pieces']['cabin'] = cabin_report()
    for key in ('valley', 'rim', 'crater'):
        if (OUT / f'layout_{key}.json').exists():
            report['pieces'][key] = station_report(key)
    failures = []
    for name, r in report['pieces'].items():
        why = verdict(r)
        r['verdict'] = 'pass' if not why else 'fail'; r['failures'] = why
        failures += [f'{name}: {w}' for w in why]
        if quiet:
            continue
        print(name, r['verdict'], 'area', r['walkable_area_m2'], 'components', r['components'])
        for x in r['routes']:
            print('  ', x['route'], x.get('bottleneck_width_m'), x.get('bottleneck_at'), 'OK' if x.get('meets_0.9') else 'FAIL')
        for p in r['pinch_points']:
            print('   pinch', p)
        for p in r['trapping_pockets']:
            print('   pocket', p)
    report['all_pass'] = not failures; report['failures'] = failures
    report['inputs'] = {'checker_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                        'layouts':{name:hashlib.sha256((OUT/f'layout_{name}.json').read_bytes()).hexdigest()
                                   for name in report['pieces']}}
    (REVIEW / 'walk_report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report, failures


def main():
    _, failures = audit()
    for f in failures:
        print('FAIL', f)
    print('walk report:', 'PASS' if not failures else 'FAIL')
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
