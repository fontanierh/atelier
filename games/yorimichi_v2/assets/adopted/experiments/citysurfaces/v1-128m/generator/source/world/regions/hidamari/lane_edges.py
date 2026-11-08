"""What lines Hidamari's lanes (the narrow north-south streets, layout.road_width): HD_LaneEdges.

Along both paving edges of every lane, runs of a grey concrete-block wall with a tile cap, a weathered board fence
between posts, or a clipped hedge, as round Japanese back lanes, so the lane reads as a lane between yards rather
than a road across a lawn. Each run is RUN metres long with a gate gap between runs; a run stops short of the
crossing streets' paving and of any building whose footprint comes within REACH metres of the edge (shops on corner
lots front their own side walls). Everything follows the ground in 2 m steps, from 0.3 m under it; the
collision is a box per CHUNK steps of a run, as tall as the run's highest point there.
"""
import math, random

SET_BACK = .35        # metres outside the paving edge
RUN = (7., 22.)       # a run's length
GATE = (1.4, 3.2)     # the gap between runs
REACH = 4.            # metres from the edge line to a building footprint that stops a run
KINDS = (('wall', .45), ('fence', .3), ('hedge', .25))
PALETTE = {'hd_block_concrete': (.30, .29, .265), 'hd_block_concrete_dark': (.24, .232, .21),
           'hd_wall_roof_cap': (.085, .09, .10), 'hd_fence_board': (.17, .115, .07), 'hd_fence_post': (.11, .075, .045),
           'hd_shrub_moss': (.05, .085, .03), 'hd_shrub_moss_light': (.07, .11, .035)}
STEP = 2.
CHUNK = 4          # steps per collision box


def _near_building(x, y, buildings):
    for b in buildings:
        a = math.radians(b['yaw']); dx = x-b['position'][0]; dy = y-b['position'][1]
        lx = dx*math.cos(a)+dy*math.sin(a); ly = -dx*math.sin(a)+dy*math.cos(a)
        if abs(lx) < b['width']/2+REACH and abs(ly) < b['depth']/2+REACH: return True
    return False


def build(m, height, buildings, road_x, road_y, road_width, keep_out=()):
    """Add the lane edges to Mesh m; returns {kind: metres}."""
    r = random.Random(733)
    done = {}
    for cx in road_x:
        paving, _ = road_width(x=cx)
        if paving >= 8: continue
        for side in (-1, 1):
            ex = cx+side*(paving+SET_BACK)
            # spans between the crossing streets' paving
            cuts = sorted(road_y)
            spans = [(a+road_width(y=a)[0]+1.5, b-road_width(y=b)[0]-1.5) for a, b in zip(cuts, cuts[1:])]
            spans.append((cuts[-1]+road_width(y=cuts[-1])[0]+1.5, 349.))
            for y0, y1 in spans:
                y = y0+r.uniform(0, 3)
                while y < y1-3:
                    length = min(r.uniform(*RUN), y1-y)
                    kind = r.choices([k for k, _ in KINDS], [w for _, w in KINDS])[0]
                    steps = max(1, round(length/STEP)); chunk = []
                    for k in range(steps):
                        ya = y+k*length/steps; yb = y+(k+1)*length/steps; ym = (ya+yb)/2
                        if _near_building(ex, ym, buildings) or any(x0 < ex < x1 and z0 < ym < z1 for x0, x1, z0, z1 in keep_out):
                            _collide(m, chunk); chunk = []; continue
                        chunk.append(_piece(m, kind, ex, ya, yb, side, height, r))
                        if len(chunk) == CHUNK: _collide(m, chunk); chunk = []
                        done[kind] = done.get(kind, 0)+(yb-ya)
                    _collide(m, chunk)
                    y += length+r.uniform(*GATE)
    return {k: round(v) for k, v in done.items()}


def _collide(m, pieces):
    """One box round consecutive pieces, each (x, ya, yb, z_low, z_high, thickness)."""
    if not pieces: return
    x = pieces[0][0]; ya = pieces[0][1]; yb = pieces[-1][2]
    lo = min(p[3] for p in pieces); hi = max(p[4] for p in pieces); t = max(p[5] for p in pieces)
    m.collider((x, (ya+yb)/2, (lo+hi)/2), (t, yb-ya, hi-lo))


def _box(m, x0, x1, ya, yb, za, zb, z0a, z0b, key):
    """A box from x0 to x1 and ya to yb whose bottom and top follow the ground (z0a at ya, z0b at yb)."""
    p = lambda x, y, z: (x, y, z)
    lo_a, lo_b, hi_a, hi_b = z0a+za, z0b+za, z0a+zb, z0b+zb
    m.poly([p(x0, ya, lo_a), p(x0, yb, lo_b), p(x0, yb, hi_b), p(x0, ya, hi_a)], key)
    m.poly([p(x1, yb, lo_b), p(x1, ya, lo_a), p(x1, ya, hi_a), p(x1, yb, hi_b)], key)
    m.poly([p(x0, ya, hi_a), p(x0, yb, hi_b), p(x1, yb, hi_b), p(x1, ya, hi_a)], key)
    m.poly([p(x1, ya, lo_a), p(x1, ya, hi_a), p(x0, ya, hi_a), p(x0, ya, lo_a)], key)
    m.poly([p(x0, yb, lo_b), p(x0, yb, hi_b), p(x1, yb, hi_b), p(x1, yb, lo_b)], key)


def _piece(m, kind, x, ya, yb, side, height, r):
    za, zb = float(height(x, ya)), float(height(x, yb))
    if kind == 'wall':
        t = .15; h = r.choice((1.2, 1.4, 1.6))
        _box(m, x-t/2, x+t/2, ya, yb, -.3, h, za, zb, 'hd_block_concrete' if r.random() < .7 else 'hd_block_concrete_dark')
        _box(m, x-.13, x+.13, ya, yb, h, h+.09, za, zb, 'hd_wall_roof_cap')
        return (x, ya, yb, min(za, zb)-.3, max(za, zb)+h, t+.05)
    elif kind == 'fence':
        h = 1.5
        _box(m, x-.035, x+.035, ya+.06, yb-.06, .12, h, za, zb, 'hd_fence_board')
        for yy, zz in ((ya, za), (yb, zb)):
            _box(m, x-.06, x+.06, yy-.06, yy+.06, -.3, h+.08, zz, zz, 'hd_fence_post')
        _box(m, x-.08, x+.08, ya, yb, h, h+.05, za, zb, 'hd_fence_post')
        return (x, ya, yb, min(za, zb)-.3, max(za, zb)+h, .15)
    else:
        h = r.uniform(1.05, 1.35); w = r.uniform(.55, .75)
        x0, x1 = x-w/2+side*.1, x+w/2+side*.1
        _box(m, x0, x1, ya, yb, -.2, h, za, zb, 'hd_shrub_moss' if r.random() < .6 else 'hd_shrub_moss_light')
        return (x+side*.1, ya, yb, min(za, zb)-.2, max(za, zb)+h, w)
