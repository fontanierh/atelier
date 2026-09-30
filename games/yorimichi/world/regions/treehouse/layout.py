"""Hidden tree house on the west hillside below the Woodland air-station trail (Blender metres, x east, y north).

From the trail it is one small hut in a maple, reached by stepping stones through a low gap in the bank. Through
the hut, rope bridges reach nine more places stepping down the slope to a lookout whose crow's nest clears the
canopy. The plan (games/yorimichi/docs/TREEHOUSE_PLAN.md) explains each choice; this file is its single source of truth:
the blockout, the final build, the references and the QA all read world['treehouse'] written here. Existing
vegetation that would cut through a floor, a bridge or a roof is removed; the rest of the forest is kept.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import json, math
from pathlib import Path
import numpy as np
from village.layout import sample
from zeppelin.layout import clear as clear_zeppelin
from treehouse.screen import screen, sightlines, summary


# deck: floor height (absolute m). R: octagon circumradius. trunk: anchor trunk radius at the deck.
# crown: an existing painted-card tree (no collision) seated over the roof to give the anchor its leaves.
PLACES = {
    'entry':   dict(xy=(-135.0, 198.5), deck=77.0, trunk=.72, kind='entry', crown=('Tree_Maple_A', 1.45),
                    label='Little hut', role='the only part seen from the trail; its south porch is the reveal'),
    'library': dict(xy=(-144.0, 185.0), deck=75.8, R=4.5, trunk=.52, kind='hut', crown=('Tree_Ginkgo', 1.35),
                    label='Map room', role='maps, books and treasures; first stop, first junction'),
    'heart':   dict(xy=(-131.0, 168.0), deck=74.2, R=5.6, trunk=1.15, kind='heart', crown=('Tree_Ginkgo', 1.9),
                    label='Heart room', role='the big room round the old camphor with the shimenawa rope'),
    'kitchen': dict(xy=(-117.0, 175.0), deck=74.8, R=4.5, trunk=.55, kind='hut', crown=('Tree_Maple_A', 1.5),
                    label='Kitchen', role='clay stove, kettle, drying persimmons'),
    'sleep':   dict(xy=(-160.0, 172.0), deck=74.8, R=4.5, trunk=.55, kind='hut', crown=('Tree_Ginkgo', 1.5),
                    label='Sleeping nest', role='hammocks, futons and quilts'),
    'boat':    dict(xy=(-110.0, 161.0), deck=73.8, R=3.6, trunk=.55, kind='boat', crown=('Tree_Maple_A', 1.6),
                    label='Boat room', role='an old rowboat hauled up the tree as a room'),
    'slide':   dict(xy=(-122.0, 149.0), deck=72.8, R=3.0, trunk=.55, kind='slide', crown=('Tree_Maple_A', 1.55),
                    label='Slide tree', role='a spiral slide down to the forest floor, the back door'),
    'pulley':  dict(xy=(-150.0, 157.0), deck=73.2, R=3.1, trunk=.52, kind='pulley', crown=('Tree_Ginkgo', 1.45),
                    label='Pulley deck', role='a crane arm and a basket on a rope to the ground'),
    'chimes':  dict(xy=(-135.0, 145.0), deck=72.4, R=2.5, trunk=.45, kind='ring', crown=('Tree_Maple_A', 1.35),
                    label='Chime tree', role='a small ring landing hung with wind chimes, where three bridges meet'),
    'lookout': dict(xy=(-148.0, 140.0), deck=71.8, R=3.5, trunk=.62, kind='lookout', crow=89.0,
                    label='Lookout', role='spiral stairs to the crow\'s nest: telescope, bell, flag, the sea'),
}
BRIDGES = [('entry', 'library'), ('library', 'heart'), ('library', 'sleep'), ('heart', 'kitchen'),
           ('kitchen', 'boat'), ('boat', 'slide'), ('slide', 'chimes'), ('chimes', 'lookout'),
           ('heart', 'pulley'), ('sleep', 'pulley'), ('pulley', 'lookout'), ('heart', 'chimes')]
# Stepping stones from the trail edge up the low gap in the bank, then plank steps to the little hut. They lie flush
# with the ground; a last, wider stone (FOOT_STONE: half length across, half depth) lies against the lowest tread.
GATE = [(-133.3, 211.0), (-133.6, 209.6), (-133.9, 208.2), (-134.2, 206.8), (-134.5, 205.4), (-134.8, 204.3)]
FOOT_STONE = (.6, .4)
ENTRY_BOX = (-2.45, 2.45, -4.2, 2.1)    # little hut deck, local metres: x0, x1, y0, y1 (hut 4.0 x 3.0, porch south)
HEART_WALL = 4.3                        # octagonal room circumradius; the deck beyond it is the balcony
HUT = (3.4, 2.8)                        # huts beside the trunk: width (tangential) and depth (radial)
BRIDGE_WIDTH = 1.15
RISE, TREAD = .19, .29                  # every stair in the tree house (the pawn steps 45 cm)
SLIDE = dict(rc=3.55, width=1.0, slope=30.)
CROW = dict(ri=.72, ro=1.85, R=2.7)
ROOF_TOP = {'heart': 5.0, 'hut': 3.75, 'entry': 3.75, 'boat': 3.0}   # highest roof above the deck
# Existing trees in metres at scale 1: trunk top, crown bottom, crown top, crown radius. Cedars and pines have
# complex collision on their leaves, so they keep their full crown; the painted-card trees are not solid.
SPECIES = {
    'Tree_Maple_lo': (3.6, 2.3, 7.1, 3.6), 'Tree_Broad_lo': (4.7, 3.1, 9.1, 3.1), 'Tree_Ginkgo_lo': (5.0, 3.4, 9.6, 2.7),
    'Tree_Cedar_A': (15.2, 2.1, 16.6, 4.0), 'Tree_Cedar_B': (12.4, 1.7, 13.6, 3.6),
    'Tree_Pine_A': (13.0, 6.0, 13.6, 4.4), 'Tree_Pine_B': (11.0, 5.0, 11.6, 4.0),
    # the detailed trees (build_assets.py) have the same shapes as their painted-card versions
    'Tree_Maple_A': (3.6, 2.3, 7.1, 3.6), 'Tree_Maple_B': (2.9, 1.8, 5.7, 2.9), 'Tree_Ginkgo': (5.0, 3.4, 9.6, 2.7),
    'Tree_Broad_A': (4.7, 3.1, 9.1, 3.1),
}
CROWN = {'Tree_Maple_lo': (6.5, 6.0), 'Tree_Broad_lo': (8.5, 5.0), 'Tree_Ginkgo_lo': (9.0, 4.2),   # height, spread
         'Tree_Maple_A': (6.5, 6.0), 'Tree_Broad_A': (8.5, 5.0), 'Tree_Ginkgo': (9.0, 4.2)}
# Near the build the forest is the detailed autumn kind, and denser (autumn()): each painted-card tree becomes a
# detailed one (most green broadleaves turn to maples) and new trees fill the gaps, clear of everything built.
DETAILED = {'Tree_Maple_lo': (('Tree_Maple_A', .45), ('Tree_Maple_B', .35), ('Tree_Ginkgo', .2)), 'Tree_Ginkgo_lo': (('Tree_Ginkgo', 1.),),
            'Tree_Broad_lo': (('Tree_Maple_A', .55), ('Tree_Ginkgo', .15), ('Tree_Broad_A', .3))}
FOREST = dict(radius=50., spacing=3.6, gap=2.8, turn=130.,
              mix=(('Tree_Maple_A', .30), ('Tree_Maple_B', .25), ('Tree_Ginkgo', .27), ('Tree_Cedar_B', .18)))
KEYS = ['TH_Structure', 'TH_Trunks', 'TH_Dressing']
# The tall canopy trees (treehouse/trees.py) hold red and gold crowns at deck height round every place, as in the
# paintings: each is scaled so its crown top stands `above` metres over the nearest deck (more further out), so
# the houses stand just over a carpet of crowns seen from above and the crowns frame the walks at railing height.
TREES = yori.OUT/'treehouse'/'trees'/'trees.json'
CANOPY = dict(reach=26., share=.85, gap=4.2, headroom=2.5, above=(-1.0, 3.5), scale=(.72, 1.5),
              replace=('Tree_Maple_A', 'Tree_Maple_B', 'Tree_Ginkgo', 'Tree_Broad_A', 'Tree_Maple_lo', 'Tree_Ginkgo_lo', 'Tree_Broad_lo'),
              mix=(('Tree_Canopy_Maple', .28), ('Tree_Canopy_Crimson', .27), ('Tree_Canopy_Amber', .2), ('Tree_Canopy_Ginkgo', .25)))
if TREES.exists():
    for _k, _d in json.loads(TREES.read_text()).items():
        SPECIES[_k] = (_d['trunk_top'], _d['crown_lo'], _d['crown_hi'], _d['radius'])


def ground(h, x, y):
    return float(sample(h, x, y))


def octagon(R, phase=22.5):
    return [(R*math.cos(math.radians(phase+45*k)), R*math.sin(math.radians(phase+45*k))) for k in range(8)]


def deck_polygon(p):
    if p['kind'] == 'entry':
        x0, x1, y0, y1 = ENTRY_BOX
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return octagon(p['R'])


def ray_exit(poly, angle):
    """Where a ray from the place's centre leaves its convex deck."""
    d = np.array([math.cos(math.radians(angle)), math.sin(math.radians(angle))])
    best = None
    for a, b in zip(poly, poly[1:]+poly[:1]):
        a, b = np.array(a), np.array(b); e = b-a
        m = np.array([[d[0], -e[0]], [d[1], -e[1]]])
        if abs(np.linalg.det(m)) < 1e-9: continue
        t, s = np.linalg.solve(m, a)
        if t > 0 and -1e-6 <= s <= 1+1e-6 and (best is None or t < best):
            best = t
    return d*best


def heading(a, b):
    return math.degrees(math.atan2(b[1]-a[1], b[0]-a[0])) % 360


def widest_gap(angles):
    """Middle of the widest free arc between bridge directions: where a hut, a crane or a slide goes."""
    a = sorted(x % 360 for x in angles)
    if not a: return 0.
    gaps = [((a[(i+1) % len(a)]-a[i]) % 360 or 360, a[i]) for i in range(len(a))]
    size, start = max(gaps)
    return (start+size/2) % 360


def plan(h):
    places = {}
    for name, spec in PLACES.items():
        p = dict(spec, name=name)
        x, y = p['xy']
        p['ground'] = ground(h, x, y)
        p['poly'] = deck_polygon(p)
        p['links'] = []
        places[name] = p
    bridges = []
    for a, b in BRIDGES:
        A, B = places[a], places[b]
        ends = []
        for p, other in ((A, B), (B, A)):
            ang = heading(p['xy'], other['xy'])
            q = ray_exit(p['poly'], ang)
            ends.append([p['xy'][0]+float(q[0]), p['xy'][1]+float(q[1]), p['deck']])
            p['links'].append(dict(angle=round(ang, 2), local=[float(q[0]), float(q[1])], to=other['name']))
        span = float(math.hypot(ends[1][0]-ends[0][0], ends[1][1]-ends[0][1]))
        sag = .032*span
        mid = [(ends[0][0]+ends[1][0])/2, (ends[0][1]+ends[1][1])/2]
        bridges.append(dict(a=a, b=b, start=ends[0], end=ends[1], span=round(span, 3), sag=round(sag, 3),
                            clearance=round((ends[0][2]+ends[1][2])/2-sag-ground(h, *mid), 2)))
    for p in places.values():
        p['open'] = round(widest_gap([l['angle'] for l in p['links']]), 2)
    # Plank steps from the top stepping stone up to the north lip of the little hut's deck.
    E = places['entry']; ex, ey = E['xy']; top_y = ey+ENTRY_BOX[3]; x = GATE[-1][0]
    n_steps = 1
    for _ in range(6):
        n_steps = max(1, math.ceil((E['deck']-ground(h, x, top_y+n_steps*TREAD))/RISE))
    rise = (E['deck']-ground(h, x, top_y+n_steps*TREAD))/n_steps
    # Each stone's z is the ground under its middle plus 3 cm (build.py tilts its top to the slope). The foot stone
    # touches the lowest tread, and its z is the top of its south edge: one rise under that tread.
    stones = [[sx, sy, round(ground(h, sx, sy)+.03, 3)] for sx, sy in GATE]
    stones.append([x, round(top_y+(n_steps-1)*TREAD+.02+FOOT_STONE[1], 3), round(E['deck']-n_steps*rise, 3)])
    entry_stairs = dict(x=x, top_y=top_y, steps=n_steps, rise=round(rise, 4), tread=TREAD, width=1.1,
                        foot=[x, top_y+n_steps*TREAD, round(E['deck']-n_steps*rise, 3)])
    slide = slide_path(h, places['slide'])
    L = places['lookout']
    steps = math.ceil((L['crow']-L['deck'])/RISE); rise_c = (L['crow']-L['deck'])/steps
    rmid = (CROW['ri']+CROW['ro'])/2; da = math.degrees(TREAD/rmid)
    start = (L['open']+90) % 360
    crow = dict(CROW, steps=steps, rise=round(rise_c, 4), da=round(da, 3), floor=L['crow'], start=start,
                hole=[start+da*(steps-math.ceil(2.0/rise_c)), start+da*steps])
    crowns = []
    for p in places.values():
        if 'crown' not in p: continue
        key, s = p['crown']; H, spread = CROWN[key]
        top = p['deck']+ROOF_TOP.get(p['kind'], 2.7)
        base = max(p['ground']-.2, top-.40*H*s)
        yaw = (37*len(p['name'])+11*int(abs(p['xy'][0]))) % 360
        c = dict(place=p['name'], key=key, scale=s, base=round(base, 3), yaw=float(yaw),
                 crown=[round(base+.44*H*s-.6, 2), round(base+H*s+.6, 2)], radius=round((.5*spread+.6)*s, 2))
        crowns.append(c)
        # The anchor trunk rises through the roof into the crown; the crown's own thin trunk hides inside it.
        p['trunk_top'] = round(max(c['crown'][0]+1.1, top+.9), 3)
    L['trunk_top'] = L['crow']-.05          # the trunk ends under the crow's nest floor; posts carry the awning
    return dict(places=places, bridges=bridges, stones=stones, entry_stairs=entry_stairs, slide=slide, crow=crow,
                crowns=crowns, rise=RISE, tread=TREAD, bridge_width=BRIDGE_WIDTH, heart_wall=HEART_WALL, hut=HUT)


def slide_path(h, p):
    """Spiral chute round the slide tree: a flat landing, then 30 degrees down until it meets the slope."""
    cx, cy = p['xy']; rc = SLIDE['rc']; slope = math.tan(math.radians(SLIDE['slope']))
    start = p['open']+12.; landing = [start-24., start]
    pts = []; a = start; z = p['deck']; step = 3.
    while True:
        x, y = cx+rc*math.cos(math.radians(a)), cy+rc*math.sin(math.radians(a))
        g = ground(h, x, y)
        pts.append([round(x, 3), round(y, 3), round(max(z, g+.04), 3), round(a, 2), round(g, 3)])
        if z <= g+.06: break
        a += step; z -= slope*rc*math.radians(step)
        if a-start > 900: raise ValueError('slide never meets the ground')
    ta = math.radians(pts[-1][3]); tangent = (-math.sin(ta), math.cos(ta))
    runout = [[pts[-1][0]+tangent[0]*d, pts[-1][1]+tangent[1]*d] for d in (.8, 1.6)]
    runout = [[x, y, round(ground(h, x, y)+.04, 3)] for x, y in runout]
    return dict(SLIDE, start=start, center=[cx, cy], landing=landing, path=pts, runout=runout,
                turns=round((pts[-1][3]-start)/360, 2))


def volumes(pl):
    """Everything built, as flat capsules (segment, half width, floor and ceiling at each end) and discs."""
    segs, discs, ground_zones = [], [], []
    for p in pl['places'].values():
        x, y = p['xy']
        top = p['deck']+ROOF_TOP.get(p['kind'], 2.7)+.2
        R = p.get('R', 3.2) if p['kind'] != 'entry' else 4.0
        discs.append((x, y, R+.35, p['deck']-1.2, top))
        ground_zones.append((x, y, p['trunk']*1.4+1.8))
    L = pl['places']['lookout']
    discs.append((L['xy'][0], L['xy'][1], pl['crow']['R']+.4, L['deck'], pl['crow']['floor']+2.6))
    for b in pl['bridges']:
        (x0, y0, z0), (x1, y1, z1) = b['start'], b['end']
        segs.append(((x0, y0), (x1, y1), BRIDGE_WIDTH/2+.45, (z0-b['sag']-.5, z1-b['sag']-.5), (z0+1.8, z1+1.8)))
    path = pl['slide']['path']
    for a, b in zip(path[:-1:2], path[2::2]):
        segs.append(((a[0], a[1]), (b[0], b[1]), .9, (a[2]-.6, b[2]-.6), (a[2]+1.9, b[2]+1.9)))
    last = path[-1]; ro = pl['slide']['runout'][-1]
    segs.append(((last[0], last[1]), (ro[0], ro[1]), 1.0, (last[2]-.6, ro[2]-.6), (last[2]+2.0, ro[2]+2.0)))
    ground_zones.append((ro[0], ro[1], 1.8))
    st = pl['stones']+[pl['entry_stairs']['foot']]
    for a, b in zip(st[:-1], st[1:]):
        segs.append(((a[0], a[1]), (b[0], b[1]), 1.1, (a[2]-1., b[2]-1.), (a[2]+2.6, b[2]+2.6)))
        ground_zones.append((a[0], a[1], 1.4))
    ex = pl['entry_stairs']; top = pl['places']['entry']['deck']+3.
    segs.append(((ex['x'], ex['foot'][1]), (ex['x'], ex['top_y']), 1.0, (ex['foot'][2]-1.,)*2, (top, top)))
    return segs, discs, ground_zones


def seg_distance(px, py, a, b):
    a, b = np.array(a), np.array(b); ab = b-a; L2 = float(ab@ab) or 1e-9
    t = np.clip(((px-a[0])*ab[0]+(py-a[1])*ab[1])/L2, 0, 1)
    return np.hypot(px-(a[0]+t*ab[0]), py-(a[1]+t*ab[1])), t


GLIMPSE = (-128.5, 214.5)      # where the trail first shows the little hut


def reveal_lines(pl, h=None):
    """The designed views, kept clear of crowns (and, from the trail, of trunks): the porch reveal, where the whole
    city opens up from the entry hut's back door; the crow's nest looking back over every place; the trail glimpse."""
    P = pl['places']; ex, ey = P['entry']['xy']; eye = np.array([ex+.4, ey-2.6, P['entry']['deck']+1.55])
    ends = [(n, P[n]['deck']+2.) for n in P if n != 'entry'] + [('lookout', pl['crow']['floor']+1.5)]
    lines = [(eye, np.array([*P[n]['xy'], z])) for n, z in ends]
    lx, ly = P['lookout']['xy']; crow = np.array([lx, ly, pl['crow']['floor']+1.75])
    lines += [(crow, np.array([*P[n]['xy'], P[n]['deck']+2.])) for n in P if n != 'lookout']
    # and over the bridges between them, so the view back reads as one network of walks, as painted
    lines += [(crow, (np.array(b['start'])+np.array(b['end']))/2+[0, 0, 1.]) for b in pl['bridges']]
    if h is not None:
        g = np.array([*GLIMPSE, ground(h, *GLIMPSE)+1.6])
        lines += [(g, np.array([ex+dx, ey, P['entry']['deck']+dz])) for dx in (-1.5, 0, 1.5) for dz in (.5, 2.5)]
    return lines


def clear(instances, pl, h=None):
    """Remove only what would pass through the build: trunks through floors, crowns through bridges and roofs,
    bushes and grass on the paths that touch the ground. Returns counts and the removed placements."""
    segs, discs, ground_zones = volumes(pl)
    anchors = [p['xy'] for p in pl['places'].values()]
    removed, gone = {}, {}
    for name, placements in list(instances.items()):
        tree = name.startswith('Tree')
        if not (tree or name.startswith(('Bush', 'Grass', 'Rock')) or name == 'Litter') or not placements:
            continue
        a = np.array(placements, float)
        x, y, z, s = a[:, 0], a[:, 1], a[:, 2], a[:, 4]
        near = np.flatnonzero((x > -190) & (x < -85) & (y > 115) & (y < 225))
        if not len(near): continue
        x, y, z, s = x[near], y[near], z[near], s[near]
        drop = np.zeros(len(near), bool)
        if tree:
            dims = SPECIES.get(name, (5., 2., 9., 3.))
            t_top = z+dims[0]*s; c_lo = z+dims[1]*s; c_hi = z+dims[2]*s
            reach = dims[3]*s*(.85 if name.endswith('_lo') else 1.)
            trunk_r = .35*s
            # a tall canopy crown hangs at head height along the walks: keep it clear of the player and the camera
            # that follows (a little behind and above), not only of the floors
            lift = CANOPY['headroom'] if name.startswith('Tree_Canopy') else 0.
            for ax, ay in anchors:
                drop |= np.hypot(x-ax, y-ay) < 3.2
            for a0, a1, hw, lo, hi in segs:
                d, t = seg_distance(x, y, a0, a1)
                zlo = lo[0]+(lo[1]-lo[0])*t; zhi = hi[0]+(hi[1]-hi[0])*t
                drop |= (d < hw+trunk_r+.3) & (t_top > zlo) & (z < zhi)
                drop |= (d < hw+reach) & (c_hi > zlo) & (c_lo < zhi+lift)
            for cx, cy, r, zlo, zhi in discs:
                d = np.hypot(x-cx, y-cy)
                drop |= (d < r+trunk_r+.3) & (t_top > zlo) & (z < zhi)
                drop |= (d < r+reach) & (c_hi > zlo) & (c_lo < zhi+lift)
            for eye, target in reveal_lines(pl, h):
                d, t = seg_distance(x, y, eye[:2], target[:2])
                zl = eye[2]+(target[2]-eye[2])*t
                drop |= (d < .8*reach) & (c_lo < zl) & (c_hi > zl) & (t > .08)
                drop |= (d < trunk_r+.6) & (z < zl) & (t_top > zl) & (t > .02) & (t < .97)
        else:
            r = (1.4 if name.startswith('Bush') else .5)*s
            for cx, cy, rr in ground_zones:
                drop |= np.hypot(x-cx, y-cy) < rr+r
            for a0, a1, hw, lo, hi in segs:
                d, t = seg_distance(x, y, a0, a1)
                zlo = lo[0]+(lo[1]-lo[0])*t
                drop |= (d < hw+r) & (z+2.0*s > zlo+.8)
        keep = np.ones(len(a), bool); keep[near[drop]] = False
        gone[name] = a[near[drop]].round(3).tolist()
        instances[name] = a[keep].tolist(); removed[name] = int(drop.sum())
    return removed, gone


def autumn(instances, pl, h):
    """The detailed autumn forest round the build (DETAILED, FOREST). Returns the added trees, before clearing."""
    rng = np.random.default_rng(29); R = FOREST['radius']
    c = np.mean([p['xy'] for p in pl['places'].values()], axis=0)
    for lo, kinds in DETAILED.items():
        a = np.array(instances.get(lo, []), float)
        if not len(a): continue
        near = np.hypot(a[:, 0]-c[0], a[:, 1]-c[1]) < R
        instances[lo] = a[~near].tolist(); moved = a[near]
        pick = rng.choice(len(kinds), size=len(moved), p=[w for _, w in kinds])
        for i, (k, _) in enumerate(kinds): instances.setdefault(k, []).extend(moved[pick == i].tolist())
    a = np.array(instances.get('Tree_Broad_lo', []), float)      # further out the green broadleaf cards turn too
    if len(a):
        far = np.hypot(a[:, 0]-c[0], a[:, 1]-c[1]) < FOREST['turn']
        instances['Tree_Broad_lo'] = a[~far].tolist(); moved = a[far]; pick = rng.random(len(moved)) < .6
        instances.setdefault('Tree_Maple_lo', []).extend(moved[pick].tolist())
        instances.setdefault('Tree_Ginkgo_lo', []).extend(moved[~pick].tolist())
    have = np.array([q[:2] for k, v in instances.items() if k.startswith('Tree') for q in v
                     if abs(q[0]-c[0]) < R+6 and abs(q[1]-c[1]) < R+6], float).reshape(-1, 2)
    kinds, weights = zip(*FOREST['mix']); added = {}; s = FOREST['spacing']
    for gx in np.arange(-R, R, s):
        for gy in np.arange(-R, R, s):
            q = c+[gx, gy]+rng.uniform(-.45, .45, 2)*s
            if math.hypot(*(q-c)) > R or (len(have) and np.hypot(*(have-q).T).min() < FOREST['gap']): continue
            k = kinds[rng.choice(len(kinds), p=weights)]
            added.setdefault(k, []).append([round(float(q[0]), 3), round(float(q[1]), 3), round(ground(h, *q)-.15, 3),
                                            round(float(rng.uniform(0, 360)), 1), round(float(rng.uniform(1.0, 1.45)), 3)])
            have = np.vstack([have, q])
    if TREES.exists(): canopy(instances, pl, h, rng, added)
    return added


def canopy(instances, pl, h, rng, added):
    """Tall trees round every place and bridge, their crown tops a few metres over the nearest deck. The forest here
    is already dense, so they take the spots of the short broadleaves (cedars and pines stay as the dark accents)."""
    P = list(pl['places'].values()); xy = np.array([p['xy'] for p in P]); C = CANOPY
    kinds, weights = zip(*C['mix'])
    mids = np.array([((b['start'][0]+b['end'][0])/2, (b['start'][1]+b['end'][1])/2) for b in pl['bridges']])
    mine = np.zeros((0, 2)); new = {}; swapped = {}
    for name in C['replace']:
        a = np.array(instances.get(name, []), float)
        if not len(a): continue
        keep = np.ones(len(a), bool)
        for i in rng.permutation(len(a)):
            q = a[i, :2]; d = np.hypot(*(xy-q).T); near = int(d.argmin())
            dist = min(d.min(), np.hypot(*(mids-q).T).min()+4.)
            if dist > C['reach'] or rng.random() > C['share']: continue
            if len(mine) and np.hypot(*(mine-q).T).min() < C['gap']: continue
            k = kinds[rng.choice(len(kinds), p=weights)]
            g = ground(h, *q)-.2; top = P[near]['deck']+rng.uniform(*C['above'])+.06*dist
            sc = float(np.clip((top-g)/SPECIES[k][2], *C['scale']))
            new.setdefault(k, []).append([round(float(q[0]), 3), round(float(q[1]), 3), round(g, 3),
                                          round(float(rng.uniform(0, 360)), 1), round(sc, 3)])
            mine = np.vstack([mine, q]); keep[i] = False; swapped[(round(float(q[0]), 3), round(float(q[1]), 3))] = (name, a[i].tolist())
        instances[name] = a[keep].tolist()
    first = {k: list(v) for k, v in new.items()}
    clear(new, pl, h)
    # a crown that would reach into a walk tries again lower, its top under the floors round it (the paintings fill
    # the space under the bridges with crowns); failing that the spot goes back to the short tree
    kept = {(q[0], q[1]) for v in new.values() for q in v}; lower = {}
    for k, v in first.items():
        for q in v:
            if (q[0], q[1]) in kept: continue
            d = np.hypot(*(xy-np.array(q[:2])).T); floor = min(P[int(i)]['deck'] for i in np.argsort(d)[:2])
            sc = (floor-rng.uniform(1.2, 3.5)-q[2])/SPECIES[k][2]
            if sc >= C['scale'][0]: lower.setdefault(k, []).append([*q[:4], round(float(min(sc, C['scale'][1])), 3)])
    clear(lower, pl, h)
    for k, v in lower.items(): new.setdefault(k, []).extend(v)
    for k, v in new.items():
        added.setdefault(k, []).extend(v)
        for q in v: swapped.pop((q[0], q[1]), None)
    for name, row in swapped.values(): instances[name].append(row)


def integrate(world, h):
    if 'treehouse' in world:
        raise ValueError('Tree house already integrated: world.json must come fresh from gen_world.py')
    pl = plan(h)
    added = autumn(world['instances'], pl, h)
    removed, gone = clear(world['instances'], pl, h)
    clear(added, pl, h)
    # the added forest keeps off the air-station trail and the station as the zeppelin region cleared them (7.5 m):
    # a cedar's crown is solid down to head height, so one on the trail is an invisible wall across it
    off = clear_zeppelin(added, path=np.array(world['zeppelin']['trail']))
    pl['forest_off_trail'] = {k: n for k, n in off.items() if n}
    for k, v in added.items(): world['instances'].setdefault(k, []).extend(v)
    pl['forest_added'] = {k: len(v) for k, v in added.items()}
    for c in pl['crowns']:
        x, y = pl['places'][c['place']]['xy']
        world['instances'].setdefault(c['key'], []).append([x, y, c['base'], c['yaw'], c['scale']])
    # a few tall cedars and canopy trees keep the lookout out of sight from the lake trail and the first part of the
    # air-station trail (screen.py); the crow's nest still looks over them to the bridges and the sea
    before = summary(sightlines(world, pl, h, SPECIES), pl)
    grove, found = screen(world, pl, h, SPECIES, np.random.default_rng(37))
    for k, v in grove.items(): world['instances'].setdefault(k, []).extend(v)
    after = summary(sightlines(world, pl, h, SPECIES), pl)
    pl['forest_screen'] = {k: len(v) for k, v in grove.items()}
    pl['forest_screen_replaced'] = found.get('replaced', {})
    pl['screen'] = dict(trees=[[k, *q] for k, v in grove.items() for q in v],
                        seen=[dict(walk=w, before=before[w], after=after[w]) for w in before if before[w]['seen_m']])
    for name in KEYS:
        world['instances'][name] = [[0, 0, 0, 0, 1]]
    world['treehouse'] = dict(pl, removed=removed)
    # What depends on the build's meshes (prop instances, lantern and room lights, the rooms' look) is written by
    # treehouse/build.py to build/yorimichi/treehouse/runtime.json (staged into Content/Data), which AJapanWorld merges
    # into this at load.
    xy = np.array([q['xy'] for q in pl['places'].values()]); lo, hi = xy.min(0)-18, xy.max(0)+18
    decks = [q['deck'] for q in pl['places'].values()]
    # a warm late-afternoon grade while the camera is in or over the canopy (AJapanWorld)
    world['treehouse']['grade'] = dict(center=[*((lo+hi)/2).round(2).tolist(), round(float(np.mean(decks)), 2)],
                                       extent=[*((hi-lo)/2).round(2).tolist(), 45.], blend=14., tint=[1.04, .97, .88],
                                       saturation=1.2, contrast=1.08, bloom=.9)
    world['shots'] += [[-128.5, 214.5, 75.8, -118., -6.], [-135.5, 195.0, 78.6, -103., -10.]]
    out = yori.OUT/'treehouse'; out.mkdir(parents=True, exist_ok=True)
    (out/'layout.json').write_text(json.dumps(world['treehouse'], indent=1)+'\n')
    (out/'removed.json').write_text(json.dumps(gone)+'\n')
    return pl


def report(pl):
    for p in pl['places'].values():
        print(f"{p['name']:8s} ground {p['ground']:5.1f} deck {p['deck']:5.1f} up {p['deck']-p['ground']:4.1f} open {p['open']:5.1f}")
    for b in pl['bridges']:
        print(f"{b['a']:>8s} -> {b['b']:8s} span {b['span']:4.1f} drop {b['start'][2]-b['end'][2]:+.1f} clearance {b['clearance']:.1f}")
    s = pl['slide']
    print('slide', s['turns'], 'turns, start', s['start'], 'ends', s['path'][-1][:3], '| entry steps', pl['entry_stairs']['steps'],
          '| crow steps', pl['crow']['steps'])


if __name__ == '__main__':
    # gen_world.py integrates the tree house (world.layout); this prints the plan of the current build
    import json as _json
    report(_json.loads((yori.OUT/'treehouse'/'layout.json').read_text()))
