"""M0 smoke layout: one quarter pipe with its deck, closed into a watertight block, at the marked drop-in.

Two regions on one shared path (network key 'qp'): the transition (riding, tagged lip at its top) and the body (deck,
back wall, buried base) whose profile starts where the transition ends and returns to its foot. Both sweep with the
same merged stations, so both seams conform; the two ends are capped from the section vertices (no new vertices).
"""
import numpy as np

from . import dsl, ground, network
from .curves import Line
from .profile import Profile
from .sweep import sweep

DROP = (1149.5, 37.6, 1094.8)      # assets/craterpark/drop-in.json groundPosition
SPAWN_DECK_Y = None                # the smoke's deck is the r4 drop-in, not the v2 tower deck


def quarter_pipe(path, *, height=3.5, radius=3.5, extension=.3, deck=8., deck_y=DROP[1], feature='m0_quarter',
                 side=1):
    """A quarter pipe on `path` (left side), its deck at `deck_y`: (Mesh, lip rail points (k, 3))."""
    reach = radius - np.sqrt(max(radius ** 2 - height ** 2, 0.)) if height < radius else radius
    up = np.degrees(np.arcsin(min(height, radius) / radius))
    rise = radius * (1 - np.cos(np.radians(up))) + (extension if height >= radius else 0.)
    parts = [('arc', radius, up)] + ([('line', extension)] if height >= radius else [])
    floor = deck_y - rise
    tran = Profile(parts, start=(0., floor), tags={'lip': 'end'}, material=dsl.CONCRETE)
    x1, y1 = tran.end
    # the body: deck, back wall, buried base 0.3 m under the floor, and a 0.3 m front face up to the transition's foot
    # (so no section corner is a zero-angle wedge)
    sink = .3
    body = Profile([('line', deck, {'material': dsl.DECK}),
                    ('corner', -90), ('line', y1 - floor + sink, {'role': dsl.SIDE, 'material': dsl.SIDE_WALL}),
                    ('corner', -180), ('line', x1 + deck, {'role': dsl.BASE, 'material': dsl.SIDE_WALL}),
                    ('corner', -270), ('line', sink, {'role': dsl.SIDE, 'material': dsl.SIDE_WALL})],
                   start=(x1, y1), degrees=0.)
    net = network.Network()
    net.add('qp', path)
    offsets = (0., x1 + deck)
    net.propose('qp', path.samples(dsl.RIDING_TESS, offsets=offsets), priority=1)
    net.merge()
    t = net.samples('qp')
    a = sweep(path, tran, t=t, side=side, feature=feature)
    b = sweep(path, body, t=t, side=side, feature=feature)
    parts_ = [a, b]
    # end caps from the two sections' first and last rows (crease duplicates and seam twins removed)
    for row, sign in ((0, -1.), (len(t) - 1, 1.)):
        loop = []
        for m, st in ((a, tran), (b, body)):
            n_cols = len(m.seams[f'{feature}.start'])
            idx = m.seams[f'{feature}.start'] + row * n_cols if row else m.seams[f'{feature}.start']
            pts = m.V[idx]
            keep = np.r_[True, np.linalg.norm(np.diff(pts, axis=0), axis=1) > 1e-9]
            loop.append(pts[keep][:-1])        # the last point is the next region's first
        loop = np.concatenate(loop)
        T = path.tangent([t[row]])[0]
        normal = sign * np.array([T[0], 0., T[1]])
        loop, F = ground.fill_mesh(loop, normal)
        parts_.append(dsl.Mesh.part(loop, F, material=dsl.SIDE_WALL, role=dsl.SIDE, feature=feature,
                                    N=np.broadcast_to(normal, loop.shape)))
    mesh = dsl.Mesh.concat(parts_)
    # the grind line: the lip, every 0.5 m
    tt = np.linspace(0., path.length, max(2, int(np.ceil(path.length / .5)) + 1))
    lip = path.point(tt) + side * x1 * path.normal(tt)
    rail = np.stack([lip[:, 0], np.full(len(tt), y1), lip[:, 1]], 1)
    return mesh, rail


def park():
    # the path runs north (+z) 6 m east of the drop-in; its left (-x) holds the transition, then the deck under the
    # drop-in, so a rider spawned on the deck rolls east into the quarter pipe
    x = DROP[0] + 3.5 + 4.
    path = Line((x, DROP[2] - 6.), (x, DROP[2] + 6.))
    mesh, rail = quarter_pipe(path)
    line = dsl.RideLine('m0', ['m0_quarter'], path=[DROP, (x, DROP[1] - 3.8, DROP[2])], spawn=(DROP, 0.),
                    finish=(x, DROP[1] - 3.8, DROP[2]), entry_speed=(0., 4.))
    return dsl.Park(mesh, [dsl.Rail(rail, False, 'm0_quarter')], [line])
