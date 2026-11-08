"""The finite orange continuation at the shared-room choice point.

A single quarter pipe and integral apron turn the rider ninety degrees. The
separate forward transfer leaves through the other portal.
"""
import math
from dataclasses import dataclass

import numpy as np

from . import dsl, junctions as J, primitives as P, shared14
from .curves import Line
from .layout import LineSpec, Turtle, elbow_spec

WIDTH = 32.
RADIUS = 18.
VERT = 1.
DRIFT = 55.
APPROACH = 80.
ACROSS = np.unique(np.r_[-16., -15., np.arange(-14., 15., 2.), 15., 16.])


@dataclass
class Choice:
    line: LineSpec
    spec: dict
    inlet: np.ndarray
    outlet: np.ndarray

    def row(self, point, heading):
        n = J.direction(heading + 90.)
        q = point + ACROSS[:, None] * n
        return np.c_[q[:, 0], np.full(len(q), self.line.y0), q[:, 1]]


def definition():
    """@cc [owner:fontanierh,label:correctness] choice-vert-alignment
    Actual room port, eighty-metre alignment, finite R18 quarter pipe and return.

    The 32 m clear mouth MUST remain wide enough for the measured along-wall
    speed-dependent drift; it MUST NOT be funnelled to an 18 m lane at the wall.
    The level approach MUST precede the actual apron inlet by eighty metres;
    its floor and underside MUST share the apron and room's exact port rows.
    The finite apron MUST preserve three metres of headroom over the direct
    receiver corridor; parallel portal clearance alone is insufficient.
    """
    room = shared14.definition()
    inlet = room.body.point([room.body.length])[0] + shared14.ORANGE_OFFSET * room.body.normal([room.body.length])[0]
    tangent = room.body.tangent([room.body.length])[0]
    heading = math.degrees(math.atan2(tangent[1],tangent[0])) % 360.
    run = 6. * math.sqrt(2.) + WIDTH / 2.
    params = dict(r=RADIUS, vert=VERT, deck=3., apron=6., width=WIDTH,
                  drift=DRIFT, lip_min=40.)
    path = Turtle(tuple(inlet), heading, (('straight', APPROACH + run), ('elbow', 90., params), ('straight', run)))
    line = LineSpec('V14', 'Orange vert continuation', path, shared14.OUTLET_Y,
                    (('line', path.length),), (), 'shared choice', 'orange straight', rollin=0)
    spec = elbow_spec(line, 0)
    if abs(spec['s_in'] - APPROACH) > 1e-7 or abs(spec['s_out'] - path.length) > 1e-7:
        raise ValueError('choice vert: actual apron port differs from the room portal')
    outlet = np.asarray(path.at(path.length)[0])
    return Choice(line, spec, inlet, outlet)


def build(choice=None):
    choice = definition() if choice is None else choice
    apron_inlet = np.asarray(choice.line.path.at(choice.spec['s_in'])[0])
    side = P.Side('bowl', height=3., radius=3.5, fade=(10., 10.))
    approach = P.ramp(Line(choice.inlet, apron_inlet),
                      P.from_additions(choice.line.y0, 0., [('line', APPROACH)]), 30.,
                      left=side, right=side, feature='V14.approach', thickness=1.5,
                      across=ACROSS[(ACROSS >= -15.) & (ACROSS <= 15.)],
                      bottom_u=(ACROSS + 16.) / 32.)
    row = J.boundary_row(approach.mesh, apron_inlet, J.direction(choice.spec['heading_in']))
    turn = J.elbow(choice.spec, ground=choice.line.y0 - 1.5, on_ground=False,
                   rows=[row, choice.row(choice.outlet, choice.spec['heading_out'])])
    return P.Built.concat([approach, turn])
