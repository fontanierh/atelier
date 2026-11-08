"""Four-line course assembly, with explicit levels at every crossing.

The first switchbacks are two pairs of concentric half-bowl returns. The lower
orange/purple pair uses the original falling mega receivers. Blue/green reclaim
height in the tested rising receivers before crossing above them. This module
contains construction data, not a claim that an assembled route has passed.
"""
import math
from dataclasses import replace

import numpy as np

from craterpark.additions import profile

from . import dsl, mega, primitives as P
from .curves import Chain, EasedTurn, Line

DECK_Y = 100.
FIRST_CREST = (1147., 1098.)
HEADING = 310.
LANE_SPACING = 30.
TURN_START = 214.
THICKNESS = 1.5
FLOOR_ACROSS = np.unique(np.r_[np.linspace(-9., 9., 13), np.arange(-9., 10., 1.)])
PORT_CROSS = np.r_[-10., FLOOR_ACROSS, 10.]
BOTTOM_U = (PORT_CROSS + 10.) / 20.


class RoutePath(Chain):
    """A projectable chain of exact, tangent-continuous course pieces."""
    def __init__(self, pieces):
        super().__init__(pieces)
        self.start = tuple(self.point([0.])[0])
        d = self.tangent([0.])[0]
        self.heading = math.degrees(math.atan2(d[1], d[0])) % 360.
        self._sample_s = np.linspace(0., self.length, math.ceil(self.length / 2.) + 1)
        self._sample_p = self.point(self._sample_s)

    def curves(self):
        return self.pieces

    def at(self, s):
        return self.point([s])[0], self.tangent([s])[0]

    def project(self, points):
        q = np.atleast_2d(np.asarray(points, 'f8'))
        ids = np.concatenate([np.argmin(((p[:, None] - self._sample_p[None]) ** 2).sum(2), axis=1)
                              for p in np.array_split(q, max(1, math.ceil(len(q) / 128)))])
        s = self._sample_s[ids]
        for _ in range(8):
            delta, tangent = self.point(s) - q, self.tangent(s)
            denom = 1 + self.curvature(s) * (delta * self.normal(s)).sum(1)
            s = np.clip(s - (delta * tangent).sum(1) / np.maximum(denom, .1), 0., self.length)
        lateral = ((q - self.point(s)) * self.normal(s)).sum(1)
        return s, lateral


class PrimaryPath(RoutePath):
    """Projectable smooth switchback, in actual plan metres."""
    def __init__(self, crest, radius, turn):
        d = np.array([math.cos(math.radians(HEADING)), math.sin(math.radians(HEADING))])
        a = Line(crest, np.asarray(crest) + TURN_START * d)
        b = EasedTurn(a.b, HEADING, radius, turn)
        super().__init__((a, b))


def primary_specs():
    """@cc [owner:fontanierh,label:correctness] four-line-crossing-levels
    The four mega modules and their integral, nested half-bowl returns.
    Orange/purple MUST use falling receivers and blue/green rising receivers.
    Their swept surfaces MUST be audited together in 3D before park adoption;
    parallel plan curves alone do not establish clearance at crossings.
    """
    from .layout import Feature, LineSpec
    normal = np.array([-math.sin(math.radians(HEADING)), math.cos(math.radians(HEADING))])
    out = []
    for i, (key, name, module, turn, radius, recover) in enumerate((
            ('L1', 'Orange Mega', mega.ORANGE, 180., 90., False),
            ('L4', 'Purple Technical', mega.STANDARD, 180., 60., False),
            ('L2', 'Blue Flow', mega.STANDARD, -180., 60., True),
            ('L3', 'Green Canyon', mega.STANDARD, -180., 90., True))):
        crest = tuple(np.asarray(FIRST_CREST) + i * LANE_SPACING * normal)
        receiver = module.rising_receiver if recover else module.receiver
        parts = [*module.approach, ('gap', module.gap, -module.knuckle_drop, key + '.mega'), *receiver]
        approach = profile(DECK_Y, 0., module.approach)
        lip_s, lip_y, _ = approach[-1]
        landing_s = lip_s + module.gap
        knots = profile(lip_y - module.knuckle_drop, 0., receiver)
        end = landing_s + knots[-1][0]
        path = PrimaryPath(crest, radius, turn)
        length = path.length
        if end > length:
            raise ValueError(f'{key}: receiver leaves its first return')
        parts.append(('line', length - end))
        features = (
            Feature(key + '.approach', 'kicker', 0., lip_s, 18., 'takeoff'),
            Feature(key + '.mega', 'gap', lip_s, landing_s, 18., params={'open': True}),
            Feature(key + '.receiver', 'landing', landing_s, end, 18., 'landing'),
            Feature(key + '.half_bowl', 'half_bowl', TURN_START, length, 18.,
                    params={'turn_r': radius, 'turn_deg': turn, 'wall_height': 7., 'wall_radius': 6.}),
        )
        out.append(LineSpec(key, name, path, DECK_Y, tuple(parts), features, 'tower', 'return',
                            airs=((key + '.approach', key + '.receiver'),), rollin=0))
    return tuple(out)


def primary_sides(line):
    """The outer half-bowl belongs to the same swept channel as its floor."""
    turn = next(f for f in line.features if f.kind == 'half_bowl')
    outer = 1 if turn.params['turn_deg'] > 0 else 0

    def shape(E):
        station = line.path.project(E[:, [0, 2]])[0]
        fade_in = np.clip((station - (turn.s0 - 40.)) / 40., 0., 1.)
        fade_out = np.clip((turn.s1 - station) / 40., 0., 1.)
        weight = (1 - np.cos(np.pi * fade_in)) / 2 * (1 - np.cos(np.pi * fade_out)) / 2
        return 3. + 4. * weight, 3.5 + 2.5 * weight

    def ordinary(E):
        return np.full(len(E), 3.), np.full(len(E), 3.5)

    # The common envelope gives both sides the same transverse port samples,
    # including when one side grows into the integral half bowl.
    sides = [P.Side('bowl', height=7., radius=6., shape=ordinary) for _ in range(2)]
    sides[outer] = replace(sides[outer], height=7., radius=6., shape=shape)
    return sides


def build_primary(line):
    """One elevated solid per continuous riding sheet; gaps stay open."""
    from .layout import curve, pieces
    built = []
    continuous = pieces(line)
    left, right = primary_sides(line)
    for i, (station, y, angle, parts) in enumerate(continuous):
        prof = P.from_additions(y, angle, parts)
        name = f'{line.id}.primary.{i}'
        prof = dsl.Profile(P.tagged(prof.parts, 'landing' if i else 'takeoff'),
                           start=tuple(prof.start), degrees=prof.degrees)
        b = P.ramp(curve(line.path), prof, 18., start=station, left=left, right=right,
                   feature=name, thickness=THICKNESS,
                   across=FLOOR_ACROSS, bottom_u=BOTTOM_U,
                   ends=('wall' if i else 'flush', 'wall' if i < len(continuous) - 1 else 'flush'))
        built.append(b)
    return P.Built.concat(built)
