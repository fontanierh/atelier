"""The actual receiving bowl at the end of the shared-room transfer.

The receiver stops at a sampled floor port. The remaining twenty-five metres
belong to the bowl, so there is one floor across the join and no buried ramp.
"""
import numpy as np

from . import bowl_entry, bowls, junctions as J, prado
from .layout import knots

CENTRE = (1240., 882.)
PLAN_SCALE = (1.35, 1.55)
DEEP_WALL = (16.8, 15.6, 1.2)
SHALLOW_WALL = (15., 14.4, .6)
CROP_BLEND = 36.
PORT_RADIUS_MARGIN = 22.


def floor_port(entry_mesh):
    entry = bowl_entry.definition()
    s = entry.path.length - 25.
    point = entry.path.point([s])[0]
    heading = entry.path.tangent([s])[0]
    y = float(knots(entry.line())[-1][1])
    row = J.boundary_row(entry_mesh, point, heading)
    if not np.allclose(row[:, 1], y, atol=1e-7, rtol=0.):
        raise ValueError('finish: actual receiver row differs from its authored floor height')
    return bowls.Port('B14', 'floor', point, heading, y, 0.,
                      float(np.linalg.norm(row[-1] - row[0])), 16., row)


class FinishPlan(prado.PradoPlan):
    """Prado plan with larger walls and an exactly cut, level floor entrance."""

    def __init__(self, port):
        self.centre = np.asarray(CENTRE, 'f8')
        self.rotation = np.eye(2)
        self.outline_smooth = 100
        self.outline_normal_span = 2.
        self.deep = port.y
        self.shallow = self.deep + 1.8
        box = np.array([[-69., -41.], [67., -41.], [67., 41.], [-69., 41.]])
        box = box * PLAN_SCALE + self.centre
        # Include the entrance capsule in the tracing domain.
        radius = port.width / 2. + DEEP_WALL[1] + PORT_RADIUS_MARGIN
        ends = np.array([port.point, port.point + 35. * port.heading])
        lo = np.minimum(box.min(0), ends.min(0) - radius - 8.)
        hi = np.maximum(box.max(0), ends.max(0) + radius + 8.)
        box = np.array([lo, [hi[0], lo[1]], hi, [lo[0], hi[1]]])
        bowls.Plan.__init__(self, self.deep + DEEP_WALL[0], {'crater_bowl': self.deep},
                            [SHALLOW_WALL, DEEP_WALL], {'crater_bowl': self.shape}, [],
                            [port], box, box)
        self.notes.append('Connected floor port; R14.4/R15.6 walls and two solid 30 cm spines; native bowl riding pending')

    def shape(self, Q):
        Q = np.atleast_2d(np.asarray(Q, 'f8'))
        q = self.local(Q) / PLAN_SCALE
        d = None
        for c, r in [((-43., 18.), 21.), ((-45., -18.), 22.), ((-14., -5.), 24.)]:
            v = np.linalg.norm(q - c, axis=1) - r
            d = v if d is None else bowls.smin(d, v, 13.)
        for z in (-15., 15.):
            d = bowls.smin(d, prado._capsule(q, (0., z), (41., z), 22.), 12.)
        d *= min(PLAN_SCALE)
        for p in self.ports:
            along = (Q - p.point) @ p.heading
            capsule = prado._capsule(Q, p.point, p.point + 35. * p.heading,
                                     p.width / 2. + DEEP_WALL[1] + PORT_RADIUS_MARGIN)
            d = bowls.smin(d, capsule, 5.)
            # A straight northern receiving edge avoids a re-entrant notch:
            # its neighbouring large-radius walls have room to meet the port.
            d = -bowls.smin(-d, along, CROP_BLEND)
        return d

    def floor(self, Q):
        """@cc [owner:fontanierh,label:correctness] finish-floor-port
        The entire incoming row MUST remain at the receiver's exact level.
        Its floor blend MUST preserve both solid spines' constant-height feet.
        """
        Q = np.atleast_2d(np.asarray(Q, 'f8'))
        x = self.local(Q)[:, 0] / PLAN_SCALE[0]
        y = self.deep + (self.shallow - self.deep) * bowls.smootherstep(x / 18.)
        for p in self.ports:
            n = np.array([-p.heading[1], p.heading[0]])
            along = (Q - p.point) @ p.heading
            lateral = np.abs((Q - p.point) @ n)
            weight = (1. - bowls.smootherstep((lateral - p.width / 2. - bowls.PORT_PAD) / bowls.MORPH))
            weight *= 1. - bowls.smootherstep((along - 15.) / 80.)
            y = y * (1. - weight) + p.y * weight
        return y


def build(entry_mesh, *, on_ground=False):
    port = floor_port(entry_mesh)
    plan = FinishPlan(port)
    inserts = [prado.spine(plan, (39., -12.), (52., -12.), floor=plan.shallow,
                           height=15., radius=14.4, feature='crater_bowl.transfer_spine'),
               prado.spine(plan, (-28., -3.), (-17., -3.), floor=plan.deep,
                           height=16.8, radius=15.6, feature='crater_bowl.clover_spine')]
    for spine in inserts:
        for foot in spine.foot:
            if not np.allclose(plan.floor(foot[:, [0, 2]]), foot[:, 1], atol=1e-7, rtol=0.):
                raise ValueError('finish: spine foot does not meet the actual bowl floor')
    built = bowls.compile_plan(plan, on_ground=on_ground, inserts=inserts)
    built.checks.extend(c for insert in inserts for c in insert.checks)
    return built
