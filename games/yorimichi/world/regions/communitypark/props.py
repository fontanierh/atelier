"""Benches, lanterns, planters and wave banners on the lawn around the deck (docs/COMMUNITY_PARK.md, "Restyle").

Props stand 1.2–3.5 m outside the source pieces' footprints, off the access path,
away from the stair route and the support towers, within a few metres of the deck so they frame it. Positions are
spread by farthest-point sampling from a fixed seed. Benches face the park. Planters hold the island's ochre shrubs.
"""
import math
import numpy as np
from communitypark import layout as L
from communitypark.source import scene
from communitypark.structures import Mesh, footprint_gap, footprints, route_distance, stair_route

COUNTS = {'bench': 8, 'lantern': 10, 'planter': 6, 'banner': 4}


def candidates(towers):
    bounds = footprints(scene())
    lo = np.min([a for a, b in bounds], axis=0); hi = np.max([b for a, b in bounds], axis=0)
    x, y = np.meshgrid(np.arange(lo[0]-2., hi[0]+2.01, .5), np.arange(lo[1]-2., hi[1]+2.01, .5))
    xy = np.column_stack((x.ravel(), y.ravel())); gap = footprint_gap(xy, bounds)
    keep = (gap >= 1.2) & (gap <= 3.5)
    distance, unused = L.access_nearest(xy[:, 0], xy[:, 1]); keep &= distance > L.WIDTH/2+1.5
    keep &= route_distance(xy, stair_route()) > 3.
    for legs in towers:
        legs = np.asarray(legs)[:, :2]; keep &= np.all((xy < legs.min(0)-2.) | (xy > legs.max(0)+2.), axis=1)
    xy, gap = xy[keep], gap[keep]
    # The bench faces the nearest piece.
    facing = []
    for p in xy:
        nearest = min(bounds, key=lambda ab: np.maximum(np.maximum(ab[0]-p, p-ab[1]), 0).max())
        facing.append(np.clip(p, nearest[0], nearest[1])-p)
    return xy, np.asarray(facing)


def spread(xy, count, taken, rng):
    """Farthest-point picks, at least 3 m from each other and from earlier props."""
    start = taken if taken else [xy[rng.integers(len(xy))]]
    distance = np.min([np.linalg.norm(xy-q, axis=1) for q in start], axis=0); chosen = []
    for unused in range(count):
        i = int(np.argmax(distance))
        if distance[i] < 3.: break
        chosen.append(i); distance = np.minimum(distance, np.linalg.norm(xy-xy[i], axis=1))
    return chosen


def box(mesh, centre, along, across, size):
    """A box (across, along, height) about its centre, turned with the prop."""
    e = [np.r_[across, 0.]*size[0]/2, np.r_[along, 0.]*size[1]/2, np.array([0., 0., size[2]/2])]
    mesh.cuboid([centre+sx*e[0]+sy*e[1]+sz*e[2] for sz in (-1, 1) for sx, sy in [(-1, -1), (1, -1), (1, 1), (-1, 1)]])


def build(base_sampler, towers):
    timber = Mesh('SM_CP_PropTimber', 'CP_ServiceTimber'); stone = Mesh('SM_CP_PropStone', 'CP_granite')
    paper = Mesh('SM_CP_PropPaper', 'CP_smooth_concrete'); cloth = Mesh('SM_CP_PropBanner', 'CP_Mural_Waves')
    xy, facing = candidates(towers); rng = np.random.default_rng(20261005)
    taken = []; records = []; plants = {}
    for kind, count in COUNTS.items():
        for i in spread(xy, count, taken, rng):
            x, y = xy[i]; z = float(L.ground(x, y, base_sampler)); taken.append(xy[i])
            f = facing[i]/max(np.linalg.norm(facing[i]), 1e-6); side = np.array([-f[1], f[0]])
            yaw = math.degrees(math.atan2(f[1], f[0]))
            def at(a, b, h): return np.array([x+side[0]*a+f[0]*b, y+side[1]*a+f[1]*b, z+h])
            def block(mesh, a, b, h, size): box(mesh, at(a, b, h), f, side, size)
            if kind == 'bench':
                for a in (-.7, .7): block(stone, a, 0, .21, (.12, .42, .42))
                block(timber, 0, 0, .45, (1.9, .46, .07))
            elif kind == 'lantern':
                block(stone, 0, 0, .1, (.4, .4, .2)); block(timber, 0, 0, 1.0, (.14, .14, 1.6))
                block(paper, 0, 0, 1.95, (.36, .36, .42)); block(timber, 0, 0, 2.2, (.56, .56, .07))
            elif kind == 'planter':
                block(stone, 0, 0, .25, (1.2, 1.2, .5))
                plants.setdefault('Bush_Ochre_A', []).append([*L.local([x, y, z+.45]).tolist(), float(rng.uniform(0, 360)), .9])
            else:
                block(timber, 0, 0, 1.7, (.1, .1, 3.4)); block(timber, .45, 0, 3.3, (1.0, .08, .08))
                top = at(.85, .02, 3.25); bottom = at(.85, .02, 1.15); left = at(.05, .02, 0)[:2]
                quad = [[*left, bottom[2]], [*top[:2], bottom[2]], [*top[:2], top[2]], [*left, top[2]]]
                cloth.quad(quad, [[0, .7], [.18, .7], [.18, 0], [0, 0]])
            records.append({'kind': kind, 'xy': [round(float(x), 2), round(float(y), 2)], 'ground_m': round(z, 3),
                            'yaw_deg': round(yaw, 1)})
    return [timber, stone, paper, cloth], records, plants
