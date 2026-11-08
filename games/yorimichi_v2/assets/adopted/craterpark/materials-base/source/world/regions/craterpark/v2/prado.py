"""Prado-inspired finishing bowl: a clover and two long spine-separated pockets.

The owner's overhead reference sets the plan: three connected rounded pockets
on one side and two longer half-pipe pockets on the other. This is scaled for
Crater Park, not a survey of Marseille. Dimensions and heights are native metres.
Two opposed quarter pipes meet at each solid 30 cm crest; their exact floor
footprints are cut from the surrounding bowl, so no ramp covers an intact floor. Reference: Marseille's official Bowl du Prado page.
"""
import math

import numpy as np

from . import bowls, coping, dsl, primitives as P, solids
from .profile import Profile


CENTRE = (1367.1, 932.2)
AXIS = 5.
RIM = -10.
DEEP = -20.2
SHALLOW = -18.4
PLAN_SCALE = (1.35, 1.45)       # generous pockets for the park's high-speed transfers


def _capsule(Q, a, b, radius):
    a, b = np.asarray(a), np.asarray(b)
    v = b - a
    t = np.clip((Q - a) @ v / (v @ v), 0., 1.)
    return np.linalg.norm(Q - (a + t[:, None] * v), axis=1) - radius


class PradoPlan(bowls.Plan):
    """One bowl, with smooth depth changes and the spine cut into its plan."""

    def __init__(self, centre=CENTRE, axis=AXIS, ports=()):
        self.centre = np.asarray(centre, 'f8')
        a = math.radians(axis)
        self.rotation = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
        box = np.array([[-67., -39.], [65., -39.], [65., 39.], [-67., 39.]])
        box = (box * PLAN_SCALE) @ self.rotation.T + self.centre
        super().__init__(RIM, {'crater_bowl': DEEP}, [(8.4, 7.8, .6), (10.2, 9., 1.2)],
                         {'crater_bowl': self.shape}, [], list(ports), box, box)
        self.notes.append('Prado-inspired clover and paired half-pipe pockets; widened for high-speed transfers; two narrow shared-crest spines; native riding pending')

    def local(self, Q):
        return (np.atleast_2d(np.asarray(Q, 'f8')) - self.centre) @ self.rotation

    def native(self, Q):
        return np.atleast_2d(np.asarray(Q, 'f8')) @ self.rotation.T + self.centre

    def shape(self, Q):
        q = self.local(Q) / PLAN_SCALE
        # Left-hand clover: each bulb has enough space for the R9 transition.
        bulbs = [((-43., 18.), 21.), ((-45., -18.), 22.), ((-14., -5.), 24.)]
        d = None
        for c, r in bulbs:
            v = np.linalg.norm(q - c, axis=1) - r
            d = v if d is None else bowls.smin(d, v, 13.)
        # Two long pockets share a broad open throat with the clover.
        for z in (-15., 15.):
            v = _capsule(q, (0., z), (41., z), 22.)
            d = bowls.smin(d, v, 12.)
        return d

    def floor(self, Q):
        x = self.local(Q)[:, 0] / PLAN_SCALE[0]
        return DEEP + (SHALLOW - DEEP) * bowls.smootherstep(x / 18.)


def spine(plan, a, b, *, floor, height, radius, feature):
    """@cc [owner:fontanierh,label:correctness] shared-spine-crest
    The opposed transitions MUST meet one solid crest, at most 0.30 m wide;
    the floor MUST be cut out along the returned exact foot loop.
    The quarter pipes continue around both rounded noses.
    """
    a, b = plan.native(np.array([a, b]))
    u = (b - a) / np.linalg.norm(b - a)
    n = np.array([-u[1], u[0]])
    cap_width = .30
    top = np.array([a - cap_width / 2 * n, b - cap_width / 2 * n,
                    b + cap_width / 2 * n, a + cap_width / 2 * n])
    outline = P.Rounded(top, cap_width / 2, closed=True)
    vertical = height - radius
    # Nose stations are millimetres apart near the crest. Short vertical
    # columns keep those quads well-shaped instead of long thin triangles.
    count = max(1, math.ceil(vertical / .2))
    parts = ([('line', vertical / count)] * count if vertical > 0 else []) + [('arc', radius, 0.)]
    section = Profile(parts, start=(0., floor + height), degrees=-90.)
    built, G, _ = P.transverse(outline, section, side=-1, ground=floor, front='ground', back='flush',
                              feature=feature, on_ground=True, tess=dsl.Tess(.002, 1.2, 2.8))
    lip = G[:, 0]
    if np.linalg.norm(lip[0] - lip[-1]) < 1e-9:
        lip = lip[:-1]
    cap = solids.polygon(lip, outward=np.array([0., 1., 0.]), feature=feature, role=dsl.RIDING)
    built.mesh = dsl.Mesh.concat([built.mesh, cap])
    built.foot = solids.check_open(built.mesh, name=feature)
    if len(built.foot) != 1:
        raise ValueError(f'{feature}: spine must have exactly one floor footprint')
    into = G[:, -1] - G[:, 0]
    into[:, 1] = 0
    into /= np.linalg.norm(into, axis=1, keepdims=True)
    tube, rail = coping.coping(G[:, 0], into, closed=True, feature=feature)
    built.mesh = dsl.Mesh.concat([built.mesh, tube])
    built.rails.append(rail)
    built.checks.append({'kind': 'spine', 'feature': feature, 'crest_width_m': cap_width,
                         'height_m': height, 'radius_m': radius, 'gap_m': 0.})
    return built


def build(*, centre=CENTRE, axis=AXIS, ports=(), on_ground=False):
    """Build the whole finish once, with true shared crests and cut floor seams."""
    plan = PradoPlan(centre, axis, ports)
    spines = [spine(plan, (32.4, 0.), (56., 0.), floor=SHALLOW, height=8.4, radius=7.8,
                    feature='crater_bowl.transfer_spine'),
              spine(plan, (-32., 0.), (-14., 0.), floor=DEEP, height=10.2, radius=9.,
                    feature='crater_bowl.clover_spine')]
    out = bowls.compile_plan(plan, on_ground=on_ground, inserts=spines)
    out.checks.extend(c for b in spines for c in b.checks)
    return out
