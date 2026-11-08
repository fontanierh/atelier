"""The forward choice from the orange/purple room, into the final bowl.

The ordinary gap remains independent of the optional vert continuation. Both
start at the actual shared-room outlet plane; its direct receiver is long and
level-ended so the bowl can be joined by a real floor port.
"""
from dataclasses import dataclass

import numpy as np

from . import course, dsl, junctions as J, primitives as P, shared14
from .curves import Line

WIDTH = 30.
RECEIVER_WIDTH = 32.
MIN_AIR = 11.
FLOOR_ACROSS = np.unique(np.r_[-15., np.arange(-14., 15., 2.), 15.])
PORT_ROW = np.r_[-16., FLOOR_ACROSS, 16.]
BOTTOM_U = (PORT_ROW + 16.) / 32.


@dataclass
class Entry:
    path: course.RoutePath
    parts: tuple
    y: float
    gap: float
    drop: float

    def line(self):
        from .layout import LineSpec
        return LineSpec('B14', 'Forward bowl transfer', self.path, self.y,
                        self.parts, (), 'shared choice', 'bowl floor', rollin=0)


def definition(*, gap=8., rise=-.8, lip=16., receiver_angle=-30., crest_radius=90.):
    """@cc [owner:fontanierh,label:correctness] direct-bowl-transfer-port
    This transfer MUST start at the actual direct opening in the shared room,
    level and tangent to its outlet. Its normal kicker MUST have at least 20 m
    of straight approach. Native trials MUST certify the complete connection
    before this module can be accepted for play.
    """
    room = shared14.definition()
    end = room.body.length
    origin = room.body.point([end])[0] + shared14.DIRECT_OFFSET * room.body.normal([end])[0]
    tangent = room.body.tangent([end])[0]
    parts = (*shared14.level_change(shared14.OUTLET_Y, shared14.OUTLET_Y - 3.2, 28.),
             ('arc', 22., lip), ('line', 3.), ('gap', gap, rise, 'B14.direct'),
             ('arc', 10., -8.5), ('arc', crest_radius, receiver_angle),
             ('line', 25.), ('arc', 60., 0.), ('line', 25.))
    # The plan curve covers the complete profile, including the actual open gap.
    from .layout import knots, LineSpec
    probe = LineSpec('B14', '', Line((0., 0.), (1000., 0.)), shared14.OUTLET_Y,
                     parts, (), '', '', rollin=0)
    length = float(knots(probe)[-1][0])
    path = course.RoutePath((Line(origin, origin + length * tangent),))
    return Entry(path, parts, shared14.OUTLET_Y, gap, -rise)


def build(entry=None, *, include_runout=True):
    """Build one kicker and one receiving channel, without a floor across the gap."""
    from .layout import pieces
    entry = definition() if entry is None else entry
    modules = []
    spans = pieces(entry.line())
    for i, (station, y, angle, parts) in enumerate(spans):
        if i == len(spans) - 1 and not include_runout:
            if parts[-1] != ('line', 25.):
                raise ValueError('bowl transfer: the final 25 m must be supplied by the bowl floor')
            parts = parts[:-1]
        width = WIDTH if i == 0 else RECEIVER_WIDTH
        half = width / 2.
        across = FLOOR_ACROSS if i == 0 else np.arange(-half, half + 1., 2.)
        underside = (np.r_[-half - 1., across, half + 1.] + half + 1.) / (width + 2.)
        side = P.Side('bowl', height=3., radius=3.5,
                      fade=(20. if i == 0 else 0., 10.))
        prof = P.from_additions(y, angle, parts)
        prof = dsl.Profile(P.tagged(prof.parts, 'takeoff' if i == 0 else 'landing'),
                           start=tuple(prof.start), degrees=prof.degrees)
        modules.append(P.ramp(entry.path, prof, width, start=station,
                              left=side, right=side, feature='B14.' + str(i),
                              across=across, bottom_u=underside,
                              thickness=course.THICKNESS,
                              ends=('flush' if i == 0 else 'wall',
                                    'wall' if i == 0 else 'flush')))
    return P.Built.concat(modules)
