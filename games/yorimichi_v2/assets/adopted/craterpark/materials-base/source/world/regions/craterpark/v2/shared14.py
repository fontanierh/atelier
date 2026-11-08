"""One orange/purple riding room, fed by their actual primary outlets.

The direct exit stays west of the finite vert-return wall; the orange
continuation uses the eastern opening. Both are part of this one wide room.
Dimensions remain subject to the complete native route gate.
"""
import math
from dataclasses import dataclass

import numpy as np

from craterpark.additions import profile

from . import course, dsl, junctions as J, primitives as P, solids
from .curves import EasedTurn

FLOOR_Y = 5.
OUTLET_Y = 5.
WIDTH = 100.
APPROACH = 75.
BRIDGE_LENGTH = 15.
ROOM_HEIGHT = 11.
ROOM_RADIUS = 10.
ORANGE_OFFSET = 30.
DIRECT_OFFSET = -10.
ORANGE_PORT = (ORANGE_OFFSET - 16.,ORANGE_OFFSET + 16.)
DIRECT_PORT = (DIRECT_OFFSET - 16.,DIRECT_OFFSET + 16.)


def level_change(y0, y1, length):
    """Two opposed exact arcs, level at both ends and exactly `length` in plan."""
    dy = y1 - y0
    if abs(dy) < 1e-9:
        return (('line', length),)
    radius = (length * length + dy * dy) / (4 * abs(dy))
    degrees = math.degrees(2 * math.atan2(abs(dy), length)) * (1 if dy > 0 else -1)
    return (('arc', radius, degrees), ('arc', radius, 0.))


def end_height(line):
    from .layout import pieces
    _, y, angle, parts = pieces(line)[-1]
    return float(profile(y, angle, parts)[-1][1])


def inlet_sides(path):
    """Physical edge-length fades start at the exact incoming wall heights."""
    cut = path.length - BRIDGE_LENGTH
    a, b = path.tangent([0., cut])
    angle = math.atan2(a[0] * b[1] - a[1] * b[0], float(a @ b))

    def ordinary(E):
        return np.full(len(E), 3.), np.full(len(E), 3.5)

    # Offset curves have length L - offset*heading_change. Leave one mm for
    # chord sampling, so the first row is exactly full height on both edges.
    return tuple(P.Side('bowl', height=7., radius=6., shape=ordinary,
                        fade=(0., cut - offset * angle - .001), fade_power=3.) for offset in (9., -9.))


@dataclass
class Definition:
    origin: np.ndarray
    arms: dict
    arm_profiles: dict
    body: EasedTurn
    body_parts: tuple
    primary: dict

    def reference(self, key, step=.5, exit_offset=0.):
        """A physical 3D centre path; its sampled segments carry their own lengths.

        The two inlets enter the same body ten metres either side of its axis.
        Each reference converges smoothly to the axis through ordinary riding;
        no lateral teleport or false arc-length parameter is introduced.
        """
        from .layout import knots, LineSpec
        q = self.primary[key]
        k = np.asarray(knots(q, step))
        primary = np.c_[q.path.point(k[:, 0])[:, 0], k[:, 1], q.path.point(k[:, 0])[:, 1]]
        a = np.asarray(profile(end_height(q), 0., self.arm_profiles[key], step=step))
        xy = self.arms[key].point(a[:, 0])
        arm = np.c_[xy[:, 0], a[:, 1], xy[:, 1]]
        room = LineSpec('S14', 'shared', self.body, FLOOR_Y, self.body_parts, (), '', '', rollin=0)
        b = np.asarray(knots(room, step))
        sign = float(np.sign((self.arms[key].point([self.arms[key].length])[0] - self.origin) @ J.direction(220.)))
        u = np.clip(b[:, 0] / 80., 0., 1.)
        offset = sign * 10. * (1 - u ** 3 * (10. - 15. * u + 6. * u ** 2))
        v = np.clip((b[:, 0] - (self.body.length - 90.)) / 90., 0., 1.)
        offset += exit_offset * v ** 3 * (10. - 15. * v + 6. * v ** 2)
        xy = self.body.point(b[:, 0]) + offset[:, None] * self.body.normal(b[:, 0])
        body = np.c_[xy[:, 0], b[:, 1], xy[:, 1]]
        result = np.concatenate([primary, arm[1:], body[1:]])
        return result[np.r_[True, np.linalg.norm(np.diff(result, axis=0), axis=1) > 1e-7]]


def definition():
    """@cc [owner:fontanierh,label:correctness] shared14-actual-inlets
    Each approach MUST start at its actual primary outlet, with matching height
    and tangent. Both routes MUST reference one body, whose construction is
    performed once. No copied overlapping room may stand in for a merge.
    """
    primary = {q.id: q for q in course.primary_specs() if q.id in ('L1', 'L4')}
    outlets = {k: v.path.point([v.path.length])[0] for k, v in primary.items()}
    forward = J.direction(130.)
    normal = J.direction(220.)
    mean = (outlets['L1'] + outlets['L4']) / 2
    wide = float(np.linalg.norm(outlets['L1'] - outlets['L4']) / 2)
    origin = mean + APPROACH * forward
    arms, profiles = {}, {}
    body = EasedTurn(origin, 130., 80., 135.)
    # Keep the choice deck level to reserve height for later orange jumps.
    # The inlet arms finish their descent before the shared body begins.
    body_parts = level_change(FLOOR_Y, OUTLET_Y, body.length)
    for key in ('L1', 'L4'):
        q = primary[key]
        sign = -1 if float((outlets[key] - mean) @ normal) < 0 else 1
        arm = J.MergeCurve(origin, 130., sign, length=APPROACH, wide=wide, narrow=10.)
        if np.linalg.norm(arm.point([0.])[0] - outlets[key]) > 1e-7:
            raise ValueError('shared14: approach misses the actual outlet')
        if np.abs(arm.curvature(np.linspace(0., arm.length, 2001))).max() > 1 / 80.:
            raise ValueError('shared14: approach is tighter than the preferred R80')
        change = (*level_change(end_height(q), FLOOR_Y, arm.length - BRIDGE_LENGTH), ('line', BRIDGE_LENGTH))
        arms[key], profiles[key] = arm, change
    return Definition(origin, arms, profiles, body, body_parts, primary)


def build(spec=None):
    """Build the two inlet arms and the single shared room, including real portals."""
    spec = definition() if spec is None else spec
    built, rows = [], {}
    port_row = np.r_[-16.,-15.,np.arange(-14.,15.,2.),15.,16.]
    across = np.unique(np.r_[np.arange(-50., 51., 2.),
                             port_row+ORANGE_OFFSET,port_row+DIRECT_OFFSET])
    # Top and underside use one row of port samples at both room ends.
    bottom_u = (np.r_[-51., across, 51.] + 51.) / 102.

    for key, path in spec.arms.items():
        cut = path.length - BRIDGE_LENGTH
        left, right = inlet_sides(path)
        q = next(q for q in course.primary_specs() if q.id == key)
        arm = P.ramp(path, P.from_additions(end_height(q), 0., spec.arm_profiles[key][:-1]), 18.,
                     left=left, right=right, thickness=course.THICKNESS, feature='S14.' + key + '.arm',
                     across=course.FLOOR_ACROSS, bottom_u=course.BOTTOM_U)
        built.append(arm)
        rows[key] = J.boundary_row(arm.mesh, path.point([cut])[0], path.tangent([cut])[0])
    from .layout import pieces, LineSpec
    room = LineSpec('S14', 'Shared room', spec.body, FLOOR_Y, spec.body_parts, (), 'merge', 'choice', rollin=0)
    continuous = pieces(room)
    for i, (start, y, a, parts) in enumerate(continuous):
        # Only the actual room ends carry connecting portals.
        left = right = P.Side('bowl', height=ROOM_HEIGHT, radius=ROOM_RADIUS, fade=(20., 20.))
        prof = P.from_additions(y, a, parts)
        prof = dsl.Profile(P.tagged(prof.parts, 'takeoff' if not i else 'landing'),
                           start=tuple(prof.start), degrees=prof.degrees)
        openings = ([(-20., 20.)] if not i else None,
                    [ORANGE_PORT,DIRECT_PORT] if i == len(continuous) - 1 else None)
        b = P.ramp(spec.body, prof, WIDTH, start=start, left=left, right=right, across=across,
                   feature='S14.shared.' + str(i), thickness=course.THICKNESS,
                   bottom_u=bottom_u, end_openings=openings,
                   ends=('flush' if not i else 'wall', 'flush' if i == len(continuous) - 1 else 'wall'))
        built.append(b)
        if not i:
            row = J.boundary_row(b.mesh, spec.origin, J.direction(130.),span=WIDTH+2.)
            w = (row[:, [0, 2]] - spec.origin) @ J.direction(220.)
            body_row = row[np.abs(w) <= 20. + 1e-7]
    built.append(_bridge(spec, rows, body_row))
    out = P.Built.concat(built)
    # Exported surfaces have no internal cap where the two inlet arms meet
    # the room. Any unmatched port is a hard structural failure.
    exposed = out.mesh.subset(out.mesh.role != dsl.ROLE[dsl.BASE])
    out.foot = solids.check_open(exposed, name='S14')
    room_y = end_height(room)
    out.checks.append({'kind': 'shared_room', 'feature': 'S14', 'owners': ['L1', 'L4'],
                        'floor_width_m': WIDTH, 'body_length_m': spec.body.length,
                        'floor_y_m': FLOOR_Y, 'outlet_y_m': room_y,
                        'direct_port_m': DIRECT_PORT, 'orange_port_m': ORANGE_PORT})
    return out


def _bridge(spec, rows, body_row):
    """A single flat slab replaces the narrowing tips of the two separate arms.

    Its exact two inlet rows and one outlet row are the only hidden end walls.
    There is no narrowing pair of vertical walls beneath a converging slit.
    """
    curves = {}
    for key, sign in (('L1', -1), ('L4', 1)):
        p = spec.arms[key]
        s = np.linspace(p.length - BRIDGE_LENGTH, p.length, 21)
        q = p.point(s) + sign * 10. * p.normal(s)
        curves[key] = np.c_[q[:, 0], np.full(len(q), FLOOR_Y), q[:, 1]]
    for key, first, last in (('L1', rows['L1'][0], body_row[0]),
                              ('L4', rows['L4'][-1], body_row[-1])):
        if max(np.linalg.norm(curves[key][0] - first), np.linalg.norm(curves[key][-1] - last)) > 1e-7:
            raise ValueError('shared14: bridge boundary misses its actual port endpoint')
        curves[key][0], curves[key][-1] = first, last
    loop = P._strip_dupes(np.concatenate([rows['L1'], rows['L4'], curves['L4'][1:],
                                         body_row[::-1][1:], curves['L1'][::-1][1:-1]]))
    if np.linalg.norm(rows['L1'][-1] - rows['L4'][0]) < .3:
        raise ValueError('shared14: the separate arms must end before their gap narrows below30cm')
    def key(p):
        return tuple(np.round(p / 1e-7).astype('i8'))
    hidden = {tuple(sorted((key(a), key(b)))) for r in (*rows.values(), body_row)
              for a, b in zip(r[:-1], r[1:])}
    area = np.sum(loop[:, 0] * np.roll(loop[:, 2], -1) - np.roll(loop[:, 0], -1) * loop[:, 2])
    if area < 0:
        loop = loop[::-1]
    base = loop - [0., course.THICKNESS, 0.]
    parts = [solids.polygon(loop, outward=[0., 1., 0.], feature='S14.bridge', role=dsl.RIDING),
             solids.polygon(base, outward=[0., -1., 0.], feature='S14.bridge', role=dsl.SIDE)]
    for i in range(len(loop)):
        j = (i + 1) % len(loop)
        d = loop[j] - loop[i]
        role = dsl.BASE if tuple(sorted((key(loop[i]), key(loop[j])))) in hidden else dsl.SIDE
        parts.append(solids.grid(np.array([[loop[i], base[i]], [loop[j], base[j]]]),
                                 outward=[d[2], 0., -d[0]], feature='S14.bridge', role=role))
    mesh = dsl.Mesh.concat(parts)
    solids.check_closed(mesh, name='S14.bridge')
    return P.Built(mesh)
