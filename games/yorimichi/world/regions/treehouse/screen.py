"""Sight lines from the walks to the tree house lookout, and the tall trees that screen it (Blender metres, x east).

The lookout's crow's nest (89 m) stands over the canopy to look out to the sea. From the lake trail and the start of
the air-station trail it showed over the autumn trees and gave the hidden base away. `sightlines()` measures how much
of the tower an eye over each walk sees past the terrain, the tree crowns and the tree house rooms; `screen()` plants
tall cedars and canopy trees on the lines that still show it, clear of every walk, the lake, the air station and the
build, and away from the tree house so the crow's nest keeps its views over the bridges and out to the sea.

    python games/yorimichi/world/regions/treehouse/screen.py [--eye 1.6]   # what each walk sees of the tower now
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import json, math
import numpy as np
from village.layout import sample

EYE = 1.6
CORE = .8               # the part of a crown that hides what is behind it; its outer leaves are sparse
REACH = 420.            # walks further than this from the tower are not checked
STEP = 2.               # metres between eyes along a walk
# Crown shapes at scale 1 missing from layout.SPECIES (build_foliage_lods.py: tree_broad's height and spread)
EXTRA = {'Tree_Broad_B': (3.9, 2.6, 7.5, 2.6), 'Tree_Broad_C': (5.5, 3.6, 10.7, 3.6)}
SCREEN = dict(
    walks=('lake trail', 'air-station trail'),  # the walks the tower must stay hidden from
    eyes=(1.6, 2.6),                            # the player's eye, and the follow camera a little above it
    core=.7,                                    # plan with smaller crowns than CORE, for a margin
    across=(-1.5, 0., 1.5),                     # the middle and both edges of the walk
    clear=7.5,                                  # off every walk: a cedar's crown is solid down to head height
    gap=2.6, spacing=3.4,                       # from the trunks already there, and between the new trees
    replace=('Tree_Maple_A', 'Tree_Maple_B', 'Tree_Ginkgo', 'Tree_Broad_A',       # or in the place of one of these
             'Tree_Maple_lo', 'Tree_Ginkgo_lo', 'Tree_Broad_lo'),
    grid=1.5, reach=80., away=22.,              # candidate spots: within `reach` of an eye, `away` from every place
    most=36, least=.01, passes=3,               # at most this many trees; stop when the next hides less than this
                                                # (in whole towers: 1 is everything one spot saw)
    kinds=(('Tree_Cedar_A', (1.2, 1.55), .45), ('Tree_Cedar_B', (1.35, 1.6), .2),
           ('Tree_Canopy_Ginkgo', (1.1, 1.45), .2), ('Tree_Canopy_Amber', (1.1, 1.45), .15)))


def walks(world):
    """Every path a player follows, resampled every STEP metres: name -> (n, 2) array."""
    lines = {'air-station trail': world['zeppelin']['trail'], 'lake trail': world['forest_lake']['trail'],
             'mega trail': world['mega']['trail'], 'road': world['road'], 'southwest lane': world['southwest']['lane']}
    for i, p in enumerate(world['village']['paths']):
        lines[f'village lane {i+1}'] = p
    out = {}
    for name, p in lines.items():
        p = np.asarray(p, float)[:, :2]
        s = np.r_[0, np.cumsum(np.hypot(*np.diff(p, axis=0).T))]
        t = np.arange(0, s[-1]+1e-6, STEP)
        out[name] = np.column_stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])])
    return out


def crown_rows(instances, species, near=None, reach=None, core=None):
    """Tree crowns (within `reach` of `near`) as rows x, y, lo, hi, r (the hiding core), cone (cedars and pines)."""
    cols = []
    for name, v in instances.items():
        if not name.startswith('Tree') or not v: continue
        dims = species.get(name) or EXTRA.get(name)
        if dims is None: continue
        a = np.asarray(v, float)
        if near is not None: a = a[np.hypot(a[:, 0]-near[0], a[:, 1]-near[1]) < reach]
        if not len(a): continue
        s = a[:, 4]; lo = a[:, 2]+dims[1]*s; hi = a[:, 2]+dims[2]*s
        r = (core or CORE)*dims[3]*s*(.85 if name.endswith('_lo') else 1.)
        cone = np.full(len(a), name.startswith(('Tree_Cedar', 'Tree_Pine')))
        cols.append(np.column_stack([a[:, 0], a[:, 1], lo, hi, r, cone]))
    return np.vstack(cols) if cols else np.zeros((0, 6))


def inside(c, x, y, z):
    """Whether points (k, m) are in the hiding core of the crowns c (k rows): an ellipsoid, or a cone for conifers."""
    rho = np.hypot(x-c[:, 0, None], y-c[:, 1, None])
    lo, hi, r, cone = c[:, 2, None], c[:, 3, None], c[:, 4, None], c[:, 5, None] > .5
    ell = (rho/r)**2+((z-(lo+hi)/2)/((hi-lo)/2))**2 <= 1
    con = (z >= lo) & (z <= hi) & (rho <= r*(hi-z)/(hi-lo)+.3)
    return np.where(cone, con, ell)


def tower(pl):
    """Points on the lookout: legs and stair from the deck up, the crow's nest, its roof, mast and flag, as rows
    (height, offset across the view), and the rooms in front of it (x, y, radius, floor, top) that hide it too."""
    from treehouse.layout import ROOF_TOP
    P = pl['places']; L = P['lookout']; top = pl['crow']['floor']
    rows = []
    for z in np.arange(L['deck']+.4, top+2.8, .75):
        w = 2.4 if z <= top+2.1 else 2.4*(top+2.75-z)/.65
        rows += [(z, -w), (z, 0.), (z, w)]
    rows += [(top+3.5, 0.), (top+4.4, 0.)]
    # the little hut (4 x 3 m) and the heart room's walls, kept smaller than they are
    rooms = [(*P['entry']['xy'], 1.5, P['entry']['deck'], P['entry']['deck']+ROOF_TOP['entry']),
             (*P['heart']['xy'], 3.6, P['heart']['deck'], P['heart']['deck']+ROOF_TOP['heart']-.8)]
    return np.array(L['xy'], float), np.array(rows), rooms


def targets(eye, centre, rows):
    d2 = centre-eye[:2]; u = d2/float(np.hypot(*d2)); side = np.array([-u[1], u[0]])
    return np.column_stack([centre+rows[:, 1, None]*side, rows[:, 0]])


def seen(eye, centre, rows, rooms, trees, h):
    """Which tower points an eye sees: a boolean per row of `rows`."""
    T = targets(eye, centre, rows); D = T-eye
    dist = float(np.hypot(*(centre-eye[:2]))); u = (centre-eye[:2])/dist; side = np.array([-u[1], u[0]])
    n = max(8, int(dist))
    s = (np.arange(n)+.5)/n*.97                    # the lookout's own deck and trunk are not in the way
    P = eye+s[:, None, None]*D
    hidden = (P[..., 2] < sample(h, P[..., 0], P[..., 1])).any(0)
    for x, y, r, z0, z1 in rooms:
        hidden |= ((np.hypot(P[..., 0]-x, P[..., 1]-y) < r) & (P[..., 2] > z0) & (P[..., 2] < z1)).any(0)
    if len(trees):
        rel = trees[:, :2]-eye[:2]; along = rel@u; across = np.abs(rel@side)
        c = trees[(along > 0) & (along < .97*dist) & (across < trees[:, 4]+2.6)]
        if len(c): hidden |= blocked(c, np.broadcast_to(eye, D.shape), D).any(0)
    return ~hidden


def far(q, pts, d):
    """Which points q (n, 2) are further than d from every point of pts (m, 2)."""
    out = np.ones(len(q), bool)
    for i in range(0, len(pts), 400):
        p = pts[i:i+400]
        out &= np.min(np.hypot(q[:, None, 0]-p[None, :, 0], q[:, None, 1]-p[None, :, 1]), axis=1) > d
    return out


def blocked(c, E, D, tmax=.97):
    """(k, m): whether the rays E + t D (t in 0..tmax) pass through the hiding core of each crown in c."""
    L2 = (D[:, :2]**2).sum(1)
    ts = ((c[:, None, :2]-E[None, :, :2])*D[None, :, :2]).sum(2)/L2      # closest approach, (k, m)
    dt = c[:, 4, None]/np.sqrt(L2)[None]
    hit = np.zeros(ts.shape, bool)
    for f in np.linspace(-1, 1, 9):
        t = np.clip(ts+f*dt, 0, tmax)
        hit |= inside(c, E[None, :, 0]+t*D[None, :, 0], E[None, :, 1]+t*D[None, :, 1], E[None, :, 2]+t*D[None, :, 2])
    return hit


def sightlines(world, pl, h, species, eye=EYE, only=None, extra=None):
    """For every walk: per eye (x, y, share of the tower it sees, highest point it sees or None)."""
    centre, rows, rooms = tower(pl)
    trees = crown_rows(world['instances'], species, centre, REACH+20)
    if extra: trees = np.vstack([trees, crown_rows(extra, species)])
    result = {}
    for name, pts in walks(world).items():
        if only and name not in only: continue
        pts = pts[np.hypot(*(pts-centre).T) < REACH]
        per = []
        for x, y in pts:
            e = np.array([x, y, float(sample(h, x, y))+eye])
            v = seen(e, centre, rows, rooms, trees, h)
            per.append((round(float(x), 2), round(float(y), 2), round(float(v.mean()), 4),
                        round(float(rows[v, 0].max()), 2) if v.any() else None))
        result[name] = per
    return result


def summary(result, pl):
    """Per walk: metres from which any of the tower shows, from which the crow's nest shows, and the most seen."""
    top = pl['crow']['floor']; out = {}
    for name, per in result.items():
        if not per: continue
        worst = max(per, key=lambda p: p[2])
        out[name] = dict(checked_m=len(per)*STEP, seen_m=sum(p[3] is not None for p in per)*STEP,
                         crow_seen_m=sum(p[3] is not None and p[3] >= top for p in per)*STEP,
                         most=round(100*worst[2], 1), at=[round(worst[0], 1), round(worst[1], 1)])
    return out


def sea_view(pl, h, trees, spacing=8.):
    """How many sea points (at the waterline, within the island square) the crow's nest sees past terrain and crowns."""
    L = pl['places']['lookout']; eye = np.array([*L['xy'], pl['crow']['floor']+1.6])
    n = len(h); ax = np.linspace(-300, 300, n); k = max(1, int(spacing/(ax[1]-ax[0])))
    X, Y = np.meshgrid(ax[::k], ax[::k]); sea = h[::k, ::k] < -.5
    T = np.column_stack([X[sea], Y[sea], np.full(sea.sum(), .5)]); D = T-eye
    s = np.linspace(.01, .99, 160)
    P = eye+s[:, None, None]*D
    hidden = (P[..., 2] < sample(h, P[..., 0], P[..., 1])+.2).any(0)
    # only a crown that rises over the lowest of these lines can hide the sea
    d = np.hypot(trees[:, 0]-eye[0], trees[:, 1]-eye[1]); nearest = float(np.hypot(*(T[:, :2]-eye[:2]).T).min())
    c = trees[(d > 3.) & (trees[:, 3] > eye[2]-(eye[2]-.5)*(d+trees[:, 4])/nearest)]
    for i in range(0, len(c), 256):
        hidden |= blocked(c[i:i+256], np.broadcast_to(eye, D.shape), D, tmax=.99).any(0)
    return int((~hidden).sum()), int(len(T))


def screen(world, pl, h, species, rng):
    """Tall trees on the sight lines from SCREEN['walks'] to the lookout, picked greedily by how much of the tower
    they hide, in a few passes (a short tree a new one takes the place of may have hidden a little on its own). The
    short trees leave world['instances']; returns the new trees by species (not yet in it) and a report."""
    added, report = {}, dict(passes=[], replaced={})
    for _ in range(SCREEN['passes']):
        room = SCREEN['most']-sum(len(v) for v in added.values())
        new, gone, found = one_pass(world, pl, h, species, rng, added, room)
        report['passes'].append(found)
        for k, v in new.items(): added.setdefault(k, []).extend(v)
        for k, n in gone.items(): report['replaced'][k] = report['replaced'].get(k, 0)+n
        if not new: break
    return added, report


def one_pass(world, pl, h, species, rng, added, room):
    from treehouse.layout import clear as clear_build
    from zeppelin.layout import clear as clear_station
    S = SCREEN; centre, rows, rooms = tower(pl)
    trees = np.vstack([crown_rows(world['instances'], species, centre, REACH+20, S['core']),
                       crown_rows(added, species, core=S['core'])])
    paths = walks(world); lake = world['forest_lake']
    # every (eye, tower point) ray that still shows, from the middle and both edges of the walk, weighted so the
    # whole tower seen from one spot of a walk counts 1
    E, D, W = [], [], []
    share = 1./len(rows)/len(S['eyes'])/len(S['across'])
    for name in S['walks']:
        p = paths[name]; t = np.gradient(p, axis=0); t /= np.linalg.norm(t, axis=1)[:, None]+1e-9
        for (x, y), (tx, ty) in zip(p, t):
            if math.hypot(x-centre[0], y-centre[1]) > REACH: continue
            for off in S['across']:
                ex, ey = x-ty*off, y+tx*off
                for dz in S['eyes']:
                    e = np.array([ex, ey, float(sample(h, ex, ey))+dz])
                    v = seen(e, centre, rows, rooms, trees, h)
                    if not v.any(): continue
                    T = targets(e, centre, rows)[v]
                    E += [e]*len(T); D += list(T-e); W += [share]*len(T)
    report = dict(rays=len(E))
    if not E or room <= 0: return {}, {}, report
    E, D, W = np.array(E), np.array(D), np.array(W)
    # candidate spots near the lines, off every walk, the lake, the cabin, the station and the tree house: a grid
    # through the gaps in the forest, and the spots of the short broadleaves (the tall tree then takes their place)
    lo = np.minimum(E[:, :2].min(0), centre)-10; hi = np.maximum(E[:, :2].max(0), centre)+10
    gx, gy = np.meshgrid(np.arange(lo[0], hi[0], S['grid']), np.arange(lo[1], hi[1], S['grid']))
    q = np.column_stack([gx.ravel(), gy.ravel()])+rng.uniform(-.4, .4, (gx.size, 2))*S['grid']
    q = q[far(q, trees[:, :2], S['gap'])]
    swap = [(k, i) for k in S['replace'] for i, p in enumerate(world['instances'].get(k, []))
            if lo[0] < p[0] < hi[0] and lo[1] < p[1] < hi[1]]
    sq = np.array([world['instances'][k][i][:2] for k, i in swap]).reshape(-1, 2)
    q = np.vstack([q, sq]); owner = [None]*(len(q)-len(sq))+swap
    ok = ~far(q, np.unique(E[:, :2].round(2), axis=0), S['reach'])
    for p in paths.values():
        ok &= far(q, p, S['clear'])
    ok &= far(q, np.array([p['xy'] for p in pl['places'].values()]), S['away'])
    ok &= far(q, np.array([p[:2] for v in added.values() for p in v]).reshape(-1, 2), S['spacing'])
    (cx, cy), (rx, ry) = lake['center'], lake['radii']
    ok &= ((q[:, 0]-cx)/(rx+4))**2+((q[:, 1]-cy)/(ry+4))**2 > 1
    ok &= np.hypot(q[:, 0]-lake['cabin'][0], q[:, 1]-lake['cabin'][1]) > 13
    names, ranges, weights = zip(*S['kinds'])
    pick = rng.choice(len(names), size=len(q), p=np.array(weights)/sum(weights))
    cand, where = {}, {}
    for i in np.flatnonzero(ok):
        x, y = q[i]; k = names[pick[i]]; s = float(rng.uniform(*ranges[pick[i]]))
        z = world['instances'][owner[i][0]][owner[i][1]][2] if owner[i] else float(sample(h, x, y))-.15
        row = [round(float(x), 3), round(float(y), 3), round(z, 3), round(float(rng.uniform(0, 360)), 1), round(s, 3)]
        cand.setdefault(k, []).append(row); where[(row[0], row[1])] = owner[i]
    n0 = sum(len(v) for v in cand.values())
    clear_build(cand, pl, h); clear_station(cand, path=np.array(world['zeppelin']['trail']))
    spec = [(k, p) for k, v in cand.items() for p in v]
    report.update(spots=n0, candidates=len(spec))
    if not spec: return {}, {}, report
    C = np.vstack([crown_rows({k: [p]}, species, core=S['core']) for k, p in spec])
    hits = np.zeros((len(C), len(E)), bool)
    for i in range(0, len(C), 64):
        hits[i:i+64] = blocked(C[i:i+64], E, D)
    # greedy cover: the tree that hides the most of what still shows, then the next, spaced apart
    left = np.ones(len(E), bool); chosen = []
    free = np.ones(len(C), bool)
    for _ in range(room):
        gain = (hits & left[None]) @ W
        gain[~free] = 0
        b = int(gain.argmax())
        if gain[b] < S['least']: break
        chosen.append(b); left &= ~hits[b]
        free &= np.hypot(C[:, 0]-C[b, 0], C[:, 1]-C[b, 1]) > S['spacing']
    new, gone = {}, {}
    for b in chosen:
        k, p = spec[b]; new.setdefault(k, []).append(p)
        o = where[(p[0], p[1])]
        if o: gone.setdefault(o[0], set()).add(o[1])
    for k, idx in gone.items():
        world['instances'][k] = [p for i, p in enumerate(world['instances'][k]) if i not in idx]
    report.update(chosen=len(chosen), left=round(float(W[left].sum()), 3), total=round(float(W.sum()), 3))
    return new, {k: len(v) for k, v in gone.items()}, report


def main(argv):
    from treehouse.layout import SPECIES
    eye = float(argv[argv.index('--eye')+1]) if '--eye' in argv else EYE
    world = json.loads((yori.OUT/'world.json').read_text()); h = np.load(yori.OUT/'heightmap.npy')
    pl = world['treehouse']
    res = sightlines(world, pl, h, SPECIES, eye)
    for name, s in summary(res, pl).items():
        print(f"{name:20s} checked {s['checked_m']:5.0f} m  tower seen {s['seen_m']:5.0f} m  crow's nest seen {s['crow_seen_m']:5.0f} m"
              f"  most {s['most']:5.1f}% at {s['at']}")
    print('sea points seen from the crow\'s nest: %d of %d' % sea_view(pl, h, crown_rows(world['instances'], SPECIES)))
    if '--json' in argv:
        _Path(argv[argv.index('--json')+1]).write_text(json.dumps(res)+'\n')


if __name__ == '__main__':
    main(_sys.argv[1:])
