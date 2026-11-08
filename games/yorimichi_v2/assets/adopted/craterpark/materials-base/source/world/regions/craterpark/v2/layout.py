"""Crater Park v2: the whole park as data (plan/layout.md; owner: the layout agent).

Three lines fall from one tower on the block's high east rim, each with one huge air, into one bowl complex on the low
west side: L1 Crater Line (the Canyon Transfer, ramp to ramp), L2 Serpent Line (snake run, the Rim Gap, a carving berm)
and L3 Valley Line (an inclined half-pipe, the Crater Berm, the Crater Gap). The bowl complex is the Crater Bowl, the
Blue Pool (r4's pool, copied) and the Peanut, linked by spines and a channel into one loop. Respawn returns the rider
to each line's roll-in crest; no pushing path back up.

Frame: native metres, y up; a plan point is (x, z) (dsl.py). Island height = y + 680 (placement.LIFT). Native +x is
roughly island west and native +z island north (placement.HEADING 185 degrees).

Plan paths are turtles: a start (x, z), a heading in degrees (atan2(dz, dx) in the native plan) and segments
('straight', L) or ('turn', R, degrees), a positive turn counter-clockwise in (x, z). A line's distance s runs along
its plan path, and its longitudinal profile is a function of that same s.

Longitudinal profiles use additions.profile semantics: ('line', L) runs L metres of PLAN distance at the current angle,
and ('arc', R, to_degrees) turns on a circle to the absolute angle. ('gap', dx, dy, name) is an open gap of dx plan
metres to a surface dy lower, with no collision. along_parts() converts a piece to dsl.Profile semantics, where a
line's length runs along its slope.

Every jump was ridden on the offline gameplay Session (see MEASURED). Keep the numbers marked "ridden" unless a new
ride proves the change.
"""
import itertools
import math
from dataclasses import dataclass, field, replace

import numpy as np

LIFT = 680.0            # island z = native y + LIFT


# ---------------------------------------------------------------- data types
def _seg_length(seg):
    if seg[0] == 'elbow':
        return float(seg[2].get('drift', 0.)) if len(seg) > 2 else 0.
    return seg[1] if seg[0] == 'straight' else seg[1] * math.radians(abs(seg[2]))


@dataclass(frozen=True)
class Turtle:
    """A plan path: start (x, z), heading degrees (atan2(dz, dx)), segments ('straight', L) | ('turn', R, degrees) |
    ('elbow', degrees, params). An elbow is a corner of no length where the rider turns by riding a vert quarter pipe
    (G's switchbacks): the heading jumps by `degrees` at one point W; `params` size the wall (elbow_spec)."""
    start: tuple
    heading: float
    segs: tuple

    @property
    def length(self):
        return sum(_seg_length(s) for s in self.segs)

    def pieces(self):
        """[(kind, s0, s1, start (x, z), heading0 degrees, radius, turn degrees)], one per segment (an elbow's s0 = s1,
        its radius 0 and its turn the heading jump)."""
        x, z = map(float, self.start); a = math.radians(self.heading); s = 0.; out = []
        for seg in self.segs:
            if seg[0] == 'straight':
                L = float(seg[1]); out.append(('straight', s, s + L, (x, z), math.degrees(a), 0., 0.))
                x += L * math.cos(a); z += L * math.sin(a); s += L
            elif seg[0] == 'elbow':             # the rider rides the wall, drifting `drift` along it (W -> E)
                drift = _seg_length(seg); u = a + math.radians(seg[1]) / 2
                out.append(('elbow', s, s + drift, (x, z), math.degrees(a), drift, float(seg[1])))
                x += drift * math.cos(u); z += drift * math.sin(u); s += drift
                a += math.radians(seg[1])
            else:
                R, d = float(seg[1]), math.radians(seg[2]); sg = 1. if d > 0 else -1.
                out.append(('turn', s, s + R * abs(d), (x, z), math.degrees(a), R, seg[2]))
                cx, cz = x - sg * R * math.sin(a), z + sg * R * math.cos(a)
                a += d; x, z = cx + sg * R * math.sin(a), cz - sg * R * math.cos(a); s += R * abs(d)
        return out

    def at(self, s):
        """Plan point and tangent, including the airborne along-wall drift of an elbow."""
        ps = self.pieces()
        kind, s0, s1, (x, z), h, R, d = next((p for p in ps if s <= p[2] + 1e-9), ps[-1])
        t = min(max(s - s0, 0.), s1 - s0); a = math.radians(h)
        if kind in ('straight', 'elbow'):
            if kind == 'elbow':
                a += math.radians(d) / 2
            return np.array([x + t * math.cos(a), z + t * math.sin(a)]), np.array([math.cos(a), math.sin(a)])
        sg = 1. if d > 0 else -1.; cx, cz = x - sg * R * math.sin(a), z + sg * R * math.cos(a); b = a + sg * t / R
        return np.array([cx + sg * R * math.sin(b), cz - sg * R * math.cos(b)]), np.array([math.cos(b), math.sin(b)])

    def until(self, s_end):
        """The same path cut at plan distance s_end."""
        segs, s = [], 0.
        for seg in self.segs:
            L = _seg_length(seg)
            if s + L >= s_end - 1e-9:
                rest = s_end - s
                if rest > 1e-9:
                    if seg[0] == 'elbow':
                        segs.append(('elbow', seg[1], {**(seg[2] if len(seg) > 2 else {}), 'drift': rest}))
                    else:
                        segs.append(('straight', rest) if seg[0] == 'straight' else ('turn', seg[1], math.copysign(math.degrees(rest / seg[1]), seg[2])))
                break
            segs.append(seg); s += L
        return Turtle(self.start, self.heading, tuple(segs))

    def legs(self):
        """The path split at its elbows: [(s0, s1, Turtle)], each leg a path of its own (no elbows)."""
        out, segs, s_leg = [], [], 0.
        start, heading = self.start, self.heading
        for kind, a, b, p, h, R, d in self.pieces():
            if kind == 'elbow':
                out.append((s_leg, a, Turtle(start, heading, tuple(segs))))
                u = math.radians(h + d / 2)
                start = (p[0] + R * math.cos(u), p[1] + R * math.sin(u))      # E: R holds the drift
                heading, segs, s_leg = h + d, [], b
            else:
                segs.append(('straight', b - a) if kind == 'straight' else ('turn', R, d))
        out.append((s_leg, self.length, Turtle(start, heading, tuple(segs))))
        return out

    def elbows(self):
        """[(s, corner W (x, z), heading in, heading out, params)] in order (params['drift']: W to E along the wall)."""
        return [(a, p, h, h + d, seg[2] if len(seg) > 2 else {})
                for (kind, a, _, p, h, _, d), seg in zip(self.pieces(), self.segs, strict=True) if kind == 'elbow']

    def points(self, step=.5):
        s = np.unique(np.r_[np.arange(0., self.length, step), self.length])
        return np.array([self.at(v)[0] for v in s]), s

    def project(self, points):
        """Exact nearest plan station, including the drift line (ties keep the first piece)."""
        Q = np.atleast_2d(np.asarray(points, 'f8'))
        best = np.full(len(Q), np.inf)
        station = np.zeros(len(Q))
        for kind, s0, s1, start, heading, radius, turn in self.pieces():
            a = math.radians(heading + turn / 2 if kind == 'elbow' else heading)
            A = np.array([math.cos(a), math.sin(a)])
            start = np.asarray(start)
            if kind in ('straight', 'elbow'):
                u = np.clip((Q - start) @ A, 0., s1 - s0)
                P0 = start + u[:, None] * A
            else:
                sign = math.copysign(1., turn)
                centre = start + sign * radius * np.array([-A[1], A[0]])
                angle0 = math.atan2(*(start - centre)[::-1])
                angle = np.arctan2(Q[:, 1] - centre[1], Q[:, 0] - centre[0])
                delta = (sign * (angle - angle0)) % (2 * math.pi)
                inside = delta <= math.radians(abs(turn))
                end, _ = self.at(s1)
                choose_end = np.linalg.norm(Q - end, axis=1) < np.linalg.norm(Q - start, axis=1)
                u = np.where(inside, radius * delta, np.where(choose_end, s1 - s0, 0.))
                th = angle0 + sign * u / radius
                P0 = centre + radius * np.stack([np.cos(th), np.sin(th)], 1)
            d = np.linalg.norm(Q - P0, axis=1)
            take = d < best
            station[take], best[take] = s0 + u[take], d[take]
        return station, best

    def curves(self):
        """The path as dsl curves (curves.Line and curves.Arc), in order (elbows are corners between them)."""
        from .curves import Arc, Line
        out = []
        for kind, s0, s1, (x, z), h, R, d in self.pieces():
            a = math.radians(h)
            if kind == 'straight':
                out.append(Line((x, z), (x + (s1 - s0) * math.cos(a), z + (s1 - s0) * math.sin(a))))
            elif kind == 'turn':
                sg = 1. if d > 0 else -1.; cx, cz = x - sg * R * math.sin(a), z + sg * R * math.cos(a)
                out.append(Arc((cx, cz), R, math.degrees(math.atan2(z - cz, x - cx)), d))
        return out


@dataclass(frozen=True)
class Feature:
    """A feature on a line, from s0 to s1 (plan metres along the line). `kind` names the primitive (pipeline.md section 4);
    `tag` is the ride tag of its riding faces ('takeoff' on a lip, 'landing' on a landing); `params` its sizes."""
    id: str
    kind: str
    s0: float
    s1: float
    width: float
    tag: str = ''
    params: dict = field(default_factory=dict)


@dataclass(frozen=True)
class LineSpec:
    id: str
    name: str
    path: Turtle
    y0: float                   # profile start height (the tower deck)
    profile: tuple              # additions.profile parts plus ('gap', dx, dy, name); no kinks, no ('angle', ...)
    features: tuple
    entry: str                  # where the rider starts: the roll-in crest (respawn point)
    exit: str                   # where it leads: no dead ends
    airs: tuple = ()            # (takeoff feature id, landing feature id)
    rollin: int = 3             # the first `rollin` profile parts are the tower's roll-in (built by the tower, not here)


@dataclass(frozen=True)
class Bowl:
    """A bowl or pool: plan `centre` (x, z), long `axis` degrees, `size` (length, width) of its coping outline (an
    ellipse unless `copy_from` names a source outline), `rim_y` and `floor_y`, a wall profile (transition radius `r`
    then `vert` metres of vertical), `deck` width behind the coping, `coping` steel, material, and the measured
    straight-on entry speed limit."""
    id: str
    centre: tuple
    axis: float
    size: tuple
    rim_y: float
    floor_y: float
    r: float
    vert: float
    deck: float
    material: str
    coping: bool = True
    max_entry: float = 0.
    copy_from: dict = None
    openings: tuple = ()        # dicts: line, point (x, z) where its surface ends, y, heading degrees, width, kind (rim | floor)
    notes: str = ''


@dataclass(frozen=True)
class Link:
    """Bowl-complex connection: a spine (two transitions back to back on a cap), a hip or a channel."""
    id: str
    kind: str
    a: str
    b: str
    path: tuple                 # plan points (x, z) along its crest or centreline
    params: dict = field(default_factory=dict)


# ---------------------------------------------------------------- palette (owner, note 26: dark concrete is out)
PALETTE = {
    'concrete': 'material_010',     # pale concrete: every run, ramp and bowl
    'deck': 'material_000',         # decks and the tower
    'pool': 'material_019',         # blue: the Blue Pool only
    'coping': 'coping_steel',       # bowl lips, the pool and the tower lip
    'wood': 'material_016',
}
FORBIDDEN_MATERIALS = ('material_004',)   # dark concrete

# ---------------------------------------------------------------- the tower
TOWER = {
    'centre': (1146.5, 1136.7),    # island (992, 2541); the world-map travel point moves here
    'size': (34.0, 56.0),          # native x, z: two 16 m roll-ins and their bowl walls share the +x side (place_crests)
    'y': 50.0,                     # island 730 (G's v3 tower; v2 lines start at 40)
    'cap': 1.5,                    # flat caps on every wall, metres
    'sides': 'earth-banked at 30 degrees to the ground fill; no free-standing walls',
    'roll_ins': {'T1': 'L1', 'T2': 'L2', 'T3': 'L3'},
    'material': 'material_000',    # PALETTE['deck']
}

# The Crater Gap receiver, validated by park-assist (#13450): knuckle R15 to 24 degrees, 16 m, R30 to 34 degrees, 8 m,
# R45 out; 6/6 passes (baseline and ollie, spawns 1/4/8 m/s) at lip 18.25-19.35 m/s. It drops 23.9 m over 55.9 m of plan.
# The shorter receiver (no 34-degree part) failed at a 17.2 m/s lip: keep the lip at 18.25 m/s or more.
CRATER_LANDING = (('arc', 15, -24), ('line', 16), ('arc', 30, -34), ('line', 8), ('arc', 45, -5))

# ---------------------------------------------------------------- L1, the Crater Line (the hero)
L1 = LineSpec(
    id='L1', name='Crater Line',
    path=Turtle(start=(1159.388, 1126.798), heading=322.3, segs=(('straight', 262.),)),
    y0=40.0,
    profile=(('arc', 14, -35), ('line', 31.5), ('arc', 30, 0),       # T1 roll-in: 40 -> 10 (720 -> 690)
             ('line', 14),                                                           # flat run-in (no spawn hop)
             ('arc', 16, 30), ('line', 6.5),                                         # A ramp: lip 30 deg at y 15.88
             ('gap', 22., -1.5, 'J2 Canyon Transfer'),                               # open canyon
             ('arc', 25, -32), ('line', 12), ('arc', 40, -5),                         # B ramp: knuckle y 14.38 -> foot -2.84
             ('line', 100.)),                                                        # run at -5 deg to the Crater Bowl rim
    features=(
        Feature('L1_rollin', 'roll_in', 0., 56.7, 16., '', {'crest_r': 14, 'face_deg': 35, 'runout_r': 30, 'walls': 'channel walls 1.2 m, flat cap 1.0 m, steel coping'}),
        Feature('L1_runin', 'run', 56.7, 70.7, 16., '', {'grade_deg': 0}),
        Feature('L1_A', 'transfer_takeoff', 70.7, 85.2, 16., 'takeoff', {'r': 16, 'lip_deg': 30, 'lip_y': 15.88, 'height': 5.88, 'flanks_deg': 30}),
        Feature('L1_canyon', 'gap', 85.2, 107.2, 22., '', {'open': True, 'ground_max_y': 6.0, 'note': 'canyon floor at least 8 m under the lip; nothing in it'}),
        Feature('L1_B', 'transfer_landing', 107.2, 150.2, 20., 'landing', {'knuckle_y': 14.38, 'knuckle_r': 25, 'slope_deg': 32, 'slope_len': 12, 'runout_r': 40}),
        Feature('L1_run', 'run', 150.2, 250.2, 16., '', {'grade_deg': -5, 'to_y': -11.59}),
        Feature('L1_bowl_entry', 'bowl_entry', 250.2, 262.0, 16., '', {'bowl': 'crater_bowl', 'kind': 'roll-in bank cut in the rim: R12 to 28 deg, R12 out onto the floor'}),
    ),
    entry='T1 crest (1159.39, 40.0, 1126.80)', exit='crater_bowl',
    airs=(('L1_A', 'L1_B'),),
)

# ---------------------------------------------------------------- L3, the Valley Line
L3 = LineSpec(
    id='L3', name='Valley Line',
    path=Turtle(start=(1147.608, 1123.76), heading=275.0, segs=(('straight', 176.), ('turn', 35., 90.), ('straight', 111.))),
    y0=40.0,
    # A slow Valley, then a late drop: at -2 degrees the rider settles at about 12.3 m/s, where rolling drag is near zero,
    # so standing, 4 and 8 m/s starts all reach the K1 lip at the same speed (ridden: 18.6-18.7 m/s, plan/l3v3).
    profile=(('arc', 14, -30), ('line', 2), ('arc', 30, -2),                          # T3 roll-in: 40 -> 33.0
             ('line', 102.624),                                                      # the Valley at -2 deg (slow)
             ('arc', 40, -30), ('line', 16), ('arc', 40, -6),                         # Valley drop: 29.4 -> 9.7
             ('line', 55),                                                           # the Crater Berm (plan turn R35, 90 deg)
             ('arc', 40, -5), ('line', 20),                                          # 20 m straight run-in
             ('arc', 22, 24), ('line', 3),                                           # K1: lip 24 deg at y 5.23
             ('gap', 20., -1.5, 'J1 Crater Gap'),
             *CRATER_LANDING,                                                        # knuckle y 3.73 -> foot -20.14
             ('line', 0.5)),                                                         # onto the Crater Bowl's east floor
    features=(
        Feature('L3_rollin', 'roll_in', 0., 22.95, 22., '', {'crest_r': 14, 'face_deg': 30, 'runout_r': 30}),
        Feature('L3_valley', 'valley', 22.95, 125.58, 22., '', {
            'grade_deg': -2, 'floor': 22., 'wall_r': 25., 'wall_top_deg': 50., 'wall_height': 10., 'cap': 1.5, 'coping': True,
            'speed': 'settles at 12.3 m/s (ridden): carve wall to wall up to about 8 m',
            'source': 'r4 12 m half-pipe (native 1320, 960): 22 m floor, R25-30 walls, about 45 deg at the top'}),
        Feature('L3_drop', 'valley', 125.58, 176., 22., '', {
            'grade_deg': -30, 'floor': 22., 'wall_r': 25., 'wall_height': 6., 'cap': 1.5, 'note': 'the Valley walls run on, lower'}),
        Feature('L3_berm', 'berm', 176., 231., 22., '', {'turn_r': 35., 'turn_deg': 90., 'outer_bank_height': 8., 'outer_wall_r': 20., 'bank_deg': 55.,
                                                          'speed': 'about 21 m/s: bank for v^2/(gR) = 1.3'}),
        Feature('L3_runin', 'run', 231., 251.69, 16., '', {'grade_deg': -5}),
        Feature('L3_K1', 'kicker', 251.69, 265.56, 14., 'takeoff', {'r': 22, 'lip_deg': 24, 'lip_y': 5.23, 'height': 3.15, 'flanks': 'kicker flanks at 30 degrees'}),
        Feature('L3_gap', 'gap', 265.56, 285.56, 20., '', {'open': True, 'ground_max_y': 0.0}),
        Feature('L3_landing', 'landing', 285.56, 341.48, 18., 'landing', {'knuckle_y': 3.73, 'knuckle_r': 15, 'slope_deg': 24, 'slope_len': 16,
                                                                          'steep_deg': 34, 'steep_len': 8, 'runout_r': 45}),
        Feature('L3_bowl_entry', 'bowl_entry', 341.48, 342.0, 18., '', {'bowl': 'crater_bowl', 'kind': 'floor level, along the bowl axis (no rim)'}),
    ),
    entry='T3 crest (1147.61, 40.0, 1123.76)', exit='crater_bowl',
    airs=(('L3_K1', 'L3_landing'),),
)

# ---------------------------------------------------------------- L2, the Serpent Line
L2 = LineSpec(
    id='L2', name='Serpent Line',
    path=Turtle(start=(1159.376, 1149.885), heading=5.0, segs=(
        ('straight', 30.), ('turn', 40., -25.), ('straight', 20.), ('turn', 40., 25.),      # Serpent: berms B1, B2
        ('straight', 20.), ('turn', 40., -45.),                                            # B3 onto the jump heading
        ('straight', 201.5),                                                               # straight from s 136.3 to 337.8
        ('turn', 35., -135.), ('straight', 12.))),                                         # carving berm into the bowl
    y0=40.0,
    profile=(('arc', 14, -33), ('line', 20), ('arc', 30, -7),         # T2 roll-in: 40 -> 20.1
             ('line', 97),                                                           # Serpent at -7 deg
             ('arc', 40, -13), ('line', 10), ('arc', 40, -5),                         # chute
             ('arc', 22, 24), ('line', 3),                                           # K3: lip 24 deg at y 8.09
             ('gap', 25., -1.5, 'J3 Rim Gap'),
             *CRATER_LANDING,                                                        # knuckle y 6.59 -> foot about -5.5
             ('arc', 120, 0), ('line', 170.11)),                                    # level run-out and carving berm
    features=(
        Feature('L2_rollin', 'roll_in', 0., 40.3, 14., '', {'crest_r': 14, 'face_deg': 33, 'runout_r': 30}),
        Feature('L2_serpent', 'snake', 40.3, 137.3, 14., '', {
            'grade_deg': -7, 'floor': 14., 'wall': 3.5, 'wall_r': 5., 'outer_wall_in_berms': 5., 'coping': 'one clean coping (owner pick a)',
            'berms': ((30., 47.5), (67.5, 85.), (105., 136.3))}),
        Feature('L2_chute', 'run', 137.3, 156.9, 14., '', {'to_deg': -13}),
        Feature('L2_K3', 'kicker', 156.9, 170.8, 14., 'takeoff', {'r': 22, 'lip_deg': 24, 'lip_y': 7.5, 'height': 3.15}),
        Feature('L2_gap', 'gap', 170.8, 195.8, 25., '', {'open': True, 'ground_max_y': 2.5}),
        Feature('L2_landing', 'landing', 195.8, 251.73, 18., 'landing', {'knuckle_r': 15, 'slope_deg': 24, 'slope_len': 16, 'steep_deg': 34, 'steep_len': 8, 'runout_r': 45}),
        Feature('L2_runout', 'run', 251.73, 337.8, 14., '', {'grade_deg': 0, 'note': 'level: bleeds the landing speed before the berm'}),
        Feature('L2_berm', 'berm', 337.8, 420.3, 16., '', {'turn_r': 35., 'turn_deg': -135., 'outer_bank_height': 6., 'outer_wall_r': 15., 'bank_deg': 40.}),
        Feature('L2_bowl_entry', 'bowl_entry', 420.3, 432.3, 16., '', {'bowl': 'crater_bowl', 'kind': 'roll-in bank at the west end, along the bowl axis'}),
    ),
    entry='T2 crest (1159.38, 40.0, 1149.88)', exit='crater_bowl',
    airs=(('L2_K3', 'L2_landing'),),
)

LINES = (L1, L3, L2)
V2_LINES = LINES


# ---------------------------------------------------------------- v3: G's switchback plan (plan/gaps/plan_v3.py)
# Island frame as G drew it: x east, y north, heading 0 east, counter-clockwise positive. Elements: ('S', length,
# [(s0, s1, kind, label, status)]) a straight leg (s from the leg start); ('QP', turn, drift, label) a vert quarter pipe
# elbow (the rider meets the wall, drifts along it and leaves mirrored); ('HB', turn, radius, label) a half bowl turn.
V3_TOWER_Y = 50.0           # 730 m (G)
V3_PLAN = {
    'L1': {'name': 'Crater Line', 'width': 16., 'heading': 222.7, 'rollin': (('arc', 14, -35), ('line', 31.5), ('arc', 30, 0)), 'elems': (
        ('S', 205., ((70.7, 107.2, 'hero_transfer', 'J2 Canyon Transfer', 'ridden'),
                     (163., 190., 'step_down', 'J4 step-down 15 m', 'planned'))),
        ('QP', -90., 24., 'E1'),
        ('S', 75., ((22., 55., 'step_up', 'J5 step-up 14 m', 'planned'),)),
        ('QP', 140., 9., 'E2'),
        ('S', 110., ((22., 52., 'step_down', 'J6 step-down 16 m', 'planned'),
                     (75., 100., 'step_down', 'J7 gap into the bowl rim 14 m', 'planned'))))},
    'L2': {'name': 'Serpent Line', 'width': 16., 'heading': 182.0, 'rollin': (('arc', 14, -33), ('line', 20), ('arc', 30, -7)), 'elems': (
        ('S', 252., ((60., 112., 'hero_crater', 'J3 Rim Gap', 'planned'),
                     (140., 168., 'step_down', 'J8 step-down 14 m', 'planned'),
                     (190., 215., 'gap', 'J9 gap 18 m', 'planned'))),
        ('HB', 92., 20., 'HB2'),
        ('S', 190., ((25., 60., 'step_down', 'J10 step-down 16 m', 'planned'),
                     (95., 130., 'gap', 'J11 gap 20 m', 'planned'))))},
    'L3': {'name': 'Valley Line', 'width': 22., 'heading': 270.0, 'rollin': (('arc', 14, -34), ('line', 22), ('arc', 30, -6)), 'elems': (
        ('S', 250., ((175., 205., 'step_down', 'J12 step-down 14 m', 'planned'),
                     (215., 240., 'gap', 'J13 gap 16 m', 'planned'))),
        ('HB', -118., 26., 'HB3'),
        ('S', 140., ((22., 70., 'hero_crater', 'J1 Crater Gap', 'planned'),
                     (92., 118., 'step_down', 'J14 step-down 15 m', 'planned'))))},
}
V3_GRADE = -6.5             # run grade (G)


def _gap_template(kind, label):
    """(kicker parts, (gap, dy), landing parts, lip degrees) for a gap kind; every landing ends back on the run grade."""
    import re
    m = re.search(r'(\d+) m', label); g = float(m.group(1)) if m else 16.
    if kind == 'hero_transfer':                    # J2 as ridden: from a flat run
        return [('arc', 16, 30), ('line', 6.5)], (22., -1.5), [('arc', 25, -32), ('line', 12), ('arc', 40, V3_GRADE)], 30.
    if kind == 'hero_crater':                      # J1/J3: 24 degree lip, 20 m gap, the 34x8 receiver
        return [('arc', 22, 24), ('line', 3)], (20., -1.5), [*CRATER_LANDING, ('arc', 60, V3_GRADE)], 24.
    if kind == 'step_up':
        return [('arc', 15, 24), ('line', 2)], (g, 1.0), [('arc', 12, -12), ('line', 4), ('arc', 30, V3_GRADE)], 24.
    if kind == 'step_down':
        return [('arc', 15, 18), ('line', 2)], (g, -2.0), [('arc', 12, -18), ('line', 6), ('arc', 30, V3_GRADE)], 18.
    return [('arc', 18, 22), ('line', 2)], (g, -1.5), [('arc', 15, -22), ('line', 8), ('arc', 35, V3_GRADE)], 22.


def _chain(a0, parts):
    """[(start angle, part)] along parts from angle a0."""
    out, a = [], a0
    for p in parts:
        out.append((a, p))
        if p[0] == 'arc':
            a = p[2]
    return out


def island_to_native_xz(x, y):
    from craterpark import placement as pl
    cx, cy = pl.frame(); a = math.radians(-pl.HEADING)
    dx, dy = x - pl.CENTRE[0], y - pl.CENTRE[1]
    return cx + dx * math.cos(a) - dy * math.sin(a), -(cy + dx * math.sin(a) + dy * math.cos(a))


def native_heading(island_heading):
    a = math.radians(island_heading)
    p0 = np.array(island_to_native_xz(900., 2400.)); p1 = np.array(island_to_native_xz(900. + math.cos(a), 2400. + math.sin(a)))
    return math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0])) % 360.


def v3_crests(tower=None):
    """Native crest points of the v3 roll-ins on the tower deck (B's place_crests: the side each heading faces)."""
    from .primitives import place_crests
    return place_crests(tower or TOWER, {k: (native_heading(v['heading']), v['width']) for k, v in V3_PLAN.items()})


def plan_line(key, crest=None):
    """A LineSpec from G's v3 plan: native path (legs, elbows with drift, half bowl turns), a profile synthesised from
    the gap templates (runs at V3_GRADE, level over every elbow apron and half bowl), features and airs."""
    from craterpark.additions import profile
    spec = V3_PLAN[key]; w = spec['width']
    h = native_heading(spec['heading'])
    crest = crest or v3_crests()[key]
    segs, feats, airs = [], [], []
    parts = list(spec['rollin'])
    k = profile(V3_TOWER_Y, 0., parts); s, a = k[-1][0], k[-1][2]
    feats.append(Feature(f'{key}_rollin', 'roll_in', 0., s, w, '', {'crest_r': 14}))

    def add(p):
        nonlocal s, a
        kk = profile(0., a, [p]); s += kk[-1][0]; a = kk[-1][2]; parts.append(p)

    def run_to(target):
        if target - s > .25:
            add(('line', target - s))

    def bend(to, R=40.):
        if abs(to - a) > .01:
            add(('arc', R, to))

    def arc_len(frm, to, R=40.):
        return profile(0., frm, [('arc', R, to)])[-1][0] if abs(to - frm) > .01 else 0.

    if abs(a - V3_GRADE) > .01 and spec['elems'][0][2] and spec['elems'][0][2][0][2] != 'hero_transfer':
        bend(V3_GRADE)
    leg0 = 0.
    elems = spec['elems']
    for ei, el in enumerate(elems):
        if el[0] == 'S':
            segs.append(('straight', float(el[1])))
            leg_end = leg0 + float(el[1])
            nxt = elems[ei + 1] if ei + 1 < len(elems) else None
            T = abs(nxt[1]) if nxt is not None else 0.; half = math.radians(T / 2)
            d_in = (6. + w / 2 * math.cos(half)) / max(math.sin(half), 1e-6) if nxt is not None and nxt[0] == 'QP' else 0.
            reserve = d_in + 2. + arc_len(V3_GRADE, 0.) if nxt is not None else 0.
            for f0, f1, kind, label, status in el[2]:
                kick, (gap, dy), land, lip = _gap_template(kind, label)
                if kind != 'hero_transfer':
                    bend(V3_GRADE)
                length = sum(profile(0., q[0], [q[1]])[-1][0] for q in _chain(a, kick)) + gap \
                    + sum(profile(0., q[0], [q[1]])[-1][0] for q in _chain(0., land))
                start = min(leg0 + f0, leg_end - reserve - length)          # the landing stays on its leg
                start = max(start, s, leg0 + 20. if ei else s)              # 20 m of straight run-in after a turn
                if start + length > leg_end - reserve + 1e-6:
                    feats.append(Feature(f'{key}_{label.split()[0]}_dropped', 'note', s, s + .5, w, '',
                                         {'why': f'{label}: {length:.0f} m does not fit its leg'}))
                    continue
                run_to(start)
                ks = s
                for p in kick:
                    add(p)
                lip_s = s
                parts.append(('gap', gap, dy, label)); s += gap; a = 0.
                ls = s
                for p in land:
                    add(p)
                fid = label.split()[0]
                feats += [Feature(f'{key}_{fid}_kicker', 'kicker', ks, lip_s, w, 'takeoff', {'lip_deg': lip, 'status': status}),
                          Feature(f'{key}_{fid}_gap', 'gap', lip_s, lip_s + gap, w, '', {'open': True, 'label': label}),
                          Feature(f'{key}_{fid}_landing', 'landing', ls, s, max(w, 18.), 'landing', {'status': status})]
                airs.append((f'{key}_{fid}_kicker', f'{key}_{fid}_landing'))
            if nxt is not None:                      # level over the next elbow's apron or half bowl
                run_to(leg_end - d_in - 2. - arc_len(a, 0.))
                bend(0.)
            run_to(leg_end)
            leg0 = leg_end
        elif el[0] == 'QP':
            turn, drift, label = el[1], el[2], el[3]
            T = abs(turn); half = math.radians(T / 2)
            d_out = (6. + w / 2 * math.cos(half)) / max(math.sin(half), 1e-6)
            drift = max(float(drift), w + 10.)       # the two legs' floors and walls side by side along the wall
            segs.append(('elbow', -float(turn), {'kind': 'elbow_qp', 'drift': float(drift), 'r': 6., 'vert': 1., 'deck': 2.,
                                                  'apron': 6., 'width': w, 'lip_min': 40., 'label': label}))
            feats.append(Feature(f'{key}_{label}', 'elbow_qp', leg0 - (6. + w / 2 * math.cos(half)) / max(math.sin(half), 1e-6),
                                 leg0 + drift + d_out, w, '', {'r': 6., 'vert': 1., 'deck': 2., 'turn_island_deg': turn}))
            run_to(leg0 + drift + d_out + 2.)
            bend(V3_GRADE)
            leg0 += drift
        else:
            turn, R, label = el[1], el[2], el[3]
            L = R * math.radians(abs(turn))
            segs.append(('turn', float(R), -float(turn)))
            feats.append(Feature(f'{key}_{label}', 'half_bowl', leg0, leg0 + L, w, '', {'r': 7., 'vert': 1., 'deck': 2.}))
            run_to(leg0 + L + 2.)
            bend(V3_GRADE)
            leg0 += L
    path = Turtle(tuple(crest), h, tuple(segs))
    run_to(path.length)
    return LineSpec(id=key, name=spec['name'], path=path, y0=V3_TOWER_Y, profile=tuple(parts), features=tuple(feats),
                    entry=f'{key} crest', exit='crater_bowl', airs=tuple(airs), rollin=len(spec['rollin']))


# ---------------------------------------------------------------- lines from a design file (G's switchbacks)
DESIGN = __import__('pathlib').Path(__file__).with_name('lines.json')


def line_from_design(d):
    """A LineSpec from a design dict (plan/layout.md schema; design5.json): id, name, y0, rollin, path {start,
    heading, segs: ['straight', L] | ['turn', R, deg] | ['elbow', deg, {kind, r, vert, deck, apron, width}]}, profile
    (additions parts and ['gap', dx, dy, name]), features [{id, kind, s0, s1, width, tag, params}], airs, entry, exit."""
    path = d['path']
    segs = tuple((seg[0], float(seg[1]), dict(seg[2])) if seg[0] == 'elbow' else tuple(seg) for seg in path['segs'])
    return LineSpec(id=d['id'], name=d['name'], path=Turtle(tuple(path['start']), float(path['heading']), segs),
                    y0=float(d.get('y0', TOWER['y'])), profile=tuple(tuple(p) for p in d['profile']),
                    features=tuple(Feature(f['id'], f['kind'], float(f['s0']), float(f['s1']), float(f['width']),
                                           f.get('tag', ''), dict(f.get('params', {}))) for f in d['features']),
                    entry=d.get('entry', ''), exit=d['exit'], airs=tuple(tuple(a) for a in d.get('airs', ())),
                    rollin=int(d.get('rollin', 3)))


def load_design(path=DESIGN):
    import json
    return tuple(line_from_design(d) for d in json.loads(__import__('pathlib').Path(path).read_text())['lines'])



# ---------------------------------------------------------------- the bowl complex
BOWLS = (
    Bowl('crater_bowl', centre=(1367.1, 932.2), axis=5.0, size=(120., 55.), rim_y=-10.0, floor_y=-20.2,
         r=9.0, vert=1.0, deck=3.0, material=PALETTE['concrete'], max_entry=25.0,
         openings=(
             {'line': 'L1', 'point': (1366.69, 966.58), 'y': -11.59, 'heading': -37.7, 'width': 16.,
              'kind': 'rim', 'note': 'the line meets the north rim 1.6 m under the coping: a roll-in bank cut through '
                                     'the wall, R12 to 28 degrees, R12 out onto the floor'},
             {'line': 'L3', 'point': (1311.44, 926.29), 'y': -20.19, 'heading': 5.0, 'width': 18.,
              'kind': 'floor', 'note': 'the east end opens at floor level along the axis: the J1 receiver runs out onto the floor'},
             {'line': 'L2', 'point': (1414.47, 941.43), 'y': -18.36, 'heading': -175.0, 'width': 16.,
              'kind': 'floor', 'note': 'the west end opens near floor level along the axis, after the carving berm '
                                       '(1.8 m over the floor: a mellow R25 ramp down)'}),
         notes='Ridden straight-on (simout/bowlwalls.txt): R8 + 1 m vert returns clean to 25 m/s; 26-28 m/s lands on the '
               'deck behind the coping (no bail). The east end is a mellow R25 bank to 30 degrees, where L3 rolls in along '
               'the axis with about 115 m of floor to bleed. r4 SW mega bowl reference: 73 m wide, R10-19, 25 m floor.'),
    Bowl('blue_pool', centre=(1387.6, 870.7), axis=5.0, size=(47., 25.), rim_y=-10.0, floor_y=-12.9,
         r=2.5, vert=0.4, deck=2.0, material=PALETTE['pool'], max_entry=10.0,
         copy_from={'meshes': ('geometry/mesh-0098-000.npz', 'geometry/mesh-0064-000.npz'), 'r4_centre': (1296.3, 910.7),
                        'r4_floor_y': -24.9, 'r4_coping_y': -22.0, 'note': 'translate by (centre - r4_centre), keep orientation; '
                        'r4 pool: about 47 x 25 m, 17 m across at x 1300, 2.9 m deep (4.1 m deep end), R2-3, vertical top'},
         notes='Reached only from inside the complex. Ridden (simout/bowlwalls2.txt): R2.5 + 0.4 m vert returns clean at '
               '8-10 m/s; at 12 m/s the rider lands on the deck. Pool entry 10 m/s or less.'),
    Bowl('peanut', centre=(1312.7, 866.2), axis=5.0, size=(40., 18.), rim_y=-10.0, floor_y=-13.3,
         r=3.0, vert=0.3, deck=2.0, material=PALETTE['concrete'], max_entry=10.0,
         notes='Two lobes 18 m across with a 12 m waist hip. R3 + 0.3 m vert returns clean at 8-10 m/s (ridden).'),
)

LINKS = (
    Link('spine_bowl_pool', 'spine', 'crater_bowl', 'blue_pool', ((1395.5, 895.5), (1375.5, 893.7)),
         {'cap': 0.35, 'crest_y': -10.0, 'note': 'crest R10 or more: above about 10 m/s it is a spine transfer air'}),
    Link('channel_pool_peanut', 'channel', 'blue_pool', 'peanut', ((1364.6, 869.7), (1332.6, 867.9)),
         {'floor': 6., 'wall': 2.0, 'wall_r': 3.0, 'grade_deg': 0., 'note': 'level pump channel at rim height'}),
    Link('spine_peanut_bowl', 'spine', 'peanut', 'crater_bowl', ((1318.6, 890.8), (1298.6, 889.0)),
         {'cap': 0.35, 'crest_y': -10.0}),
)

# ---------------------------------------------------------------- the ground between the lines
GROUND = {
    'site': 'M1: keep the old block hillside as the base; every feature builds up from it (pipeline.md section 6)',
    'fill': 'a smooth membrane (additions.relax) over the block inside its footprint, meeting every feature outline flush '
         '(within 0.3 m)',
    'flanks': 'where a feature stands above the membrane, its flanks fall at 30 degrees or less into it: no thin walls, '
           'no knife edges. Where a wall is needed it is at least 1.2 m thick with a flat cap',
    'gaps': {'L1_canyon': 6.0, 'L3_gap': -9.0, 'L2_gap': 3.0},      # the membrane stays at or under these native y in gaps
    'clearance': 'no membrane above a line\'s riding surface within its width + 2 m',
    'dressing': 'granite domes and autumn bushes on the membrane only, at least 4 m clear of every feature and line',
    'respawn': 'the game resets to each line\'s roll-in crest (decision 1); no pushing path back up',
}

# What the offline Session measured (plan/layout.md; plan/line1/validation*/report.json; plan/simout/).
# Rolling drag on the offline Session, m/s^2 against speed m/s (plan/model.py, calibrated by straight-lane rides): about
# zero below 11 m/s, then 0.8-1.2 m/s^2 (a 5-6 degree slope's worth) from 14 to 30 m/s.
MEASURED_DRAG = ((0, 8, 11, 12, 12.6, 13.4, 16, 18, 20, 22, 25, 28, 30, 40),
                 (0, 0, .06, .15, .4, .75, .82, .95, 1.0, 1.08, 1.1, 1.2, 1.25, 1.4))

MEASURED = {
    'roll_in_30m': 'from the tower deck at 3-5 m/s: 22.1-22.4 m/s on the flat run-in (plan/rollin_speed.py)',
    'L1_canyon_transfer': 'validator PASS at entry 21-24.5 m/s: airs 27-45 m, 1.8-2.8 s, mismatch 5-16 deg, normal 2-6 m/s '
                       '(short B, plan/line1/validation6); park-assist, steered, full route: 37/38/51 m airs, no bail',
    'crater_gap': 'lip 17.6-20.5 m/s: 26-43 m, ollie up to 44 m, no bail (simout/j1_shortest.txt)',
    'crater_bowl_wall': 'R8 + 1 m vert: clean to 25 m/s straight-on',
    'pool_wall': 'R2.5 + 0.4 m vert: clean to 10 m/s; 12 m/s lands on the deck',
    'peanut_wall': 'R3 + 0.3 m vert: clean to 10 m/s',
}


# ---------------------------------------------------------------- helpers
def pieces(line, start=None):
    """The line's continuous surfaces between gaps: [(s0, y0, degrees0, parts)] in additions.profile semantics. A piece
    boundary happens only at a gap, so a landing and its run-out are one surface. `start='exit'` begins at the tower
    roll-in's exit section (exit_station) and leaves the roll-in out."""
    from craterpark.additions import profile
    parts = list(line.profile)
    s0, y0, a0 = 0., line.y0, 0.
    if start == 'exit':
        s0, y0, a0 = exit_station(line)[:3]; parts = parts[line.rollin:]
    out, cur, here = [], [], (s0, y0, a0)
    for part in parts:
        if part[0] == 'angle':
            raise ValueError(f'{line.id}: an angle part is a kink; use an arc')
        if part[0] == 'gap':
            if cur:
                k = profile(here[1], here[2], cur); out.append((*here, tuple(cur)))
                here = (here[0] + k[-1][0], k[-1][1], k[-1][2])
            here, cur = (here[0] + part[1], here[1] + part[2], 0.), []
        else:
            cur.append(part)
    if cur:
        out.append((*here, tuple(cur)))
    return out


def exit_station(line):
    """(s, y, degrees, (x, z), heading degrees): where the tower's roll-in hands over to the line (B's tower builds the
    roll-in up to this section; build_line starts here, so the two never overlap in plan)."""
    from craterpark.additions import profile
    k = profile(line.y0, 0., list(line.profile[:line.rollin]))
    s, y, a = (float(v) for v in k[-1])
    p, d = line.path.at(s)
    return s, y, a, (float(p[0]), float(p[1])), math.degrees(math.atan2(d[1], d[0]))


def cut(s0, y0, a0, parts, stop):
    """A piece's parts cut at plan distance `stop` (None when the piece starts at or past it)."""
    from craterpark.additions import profile
    if s0 >= stop - 1e-6:
        return None
    keep = list(parts)
    while keep and s0 + profile(y0, a0, keep)[-1][0] > stop + 1e-6:
        last = keep[-1]; over = s0 + profile(y0, a0, keep)[-1][0] - stop
        if last[0] == 'line' and last[1] > over:
            keep[-1] = ('line', last[1] - over); break
        keep.pop()
    return tuple(keep) or None


def knots(line, step=1.):
    """[(s, y, degrees)] along the whole line, gaps left out (each piece's knots offset by its start)."""
    from craterpark.additions import profile
    out = []
    for s0, y0, a0, parts in pieces(line):
        out += [(s0 + s, y, a) for s, y, a in profile(y0, a0, list(parts), step)]
    return out


def along_parts(parts, degrees=0.):
    """additions.profile parts (line = plan metres) as dsl.Profile parts (line = metres along the slope)."""
    out, a = [], math.radians(degrees)
    for p in parts:
        if p[0] == 'line':
            out.append(('line', p[1] / max(math.cos(a), 1e-9)))
        else:
            out.append(p); a = math.radians(p[2])
    return out


def feature(fid):
    for line in (*LINES, *V2_LINES):
        for f in line.features:
            if f.id == fid:
                return line, f
    raise KeyError(fid)


def corners(path):
    """A turtle as corner points and fillet radii (primitives.Rounded): each turn becomes the intersection of its two
    tangent legs, with its radius."""
    ps = path.pieces(); pts = [np.array(path.start, 'f8')]; radii = [0.]
    for kind, s0, s1, (x, z), h, R, d in ps:
        if kind != 'turn':
            continue
        a = math.radians(h)
        half = R * math.tan(abs(math.radians(d)) / 2)
        pts.append(np.array([x, z]) + half * np.array([math.cos(a), math.sin(a)])); radii.append(R)
    end, _ = path.at(path.length); pts.append(end); radii.append(0.)
    return np.array(pts), np.array(radii)


def curve(path):
    """Keep the turtle's analytic arcs; do not intersect parallel turn tangents."""
    from .curves import Chain
    pieces_ = path.curves()
    return pieces_[0] if len(pieces_) == 1 else Chain(pieces_)


def slab_ground(lines=None, depth=2.0, step=1.0):
    """An interim ground until A's landform (v2/ground.py) lands: a plan height function (x, z) -> y that sits `depth`
    under the nearest riding station of any line, and at each open gap's `ground_max_y` (or 6 m under its lip) across
    the gap, so the flanks of every line bank down only a short way and never run into each other."""
    pts = []
    for line in lines or LINES:
        for s, y, _ in knots(line, step):
            p, _ = line.path.at(s); pts.append((p[0], p[1], y - depth))
        for f in line.features:
            if f.kind == 'gap':
                floor = f.params.get('ground_max_y')
                if floor is None:
                    floor = min(y for s, y, _ in knots(line, step) if abs(s - f.s0) < step) - 6.
                for s in np.arange(f.s0, f.s1 + 1e-9, step):
                    p, _ = line.path.at(s); pts.append((p[0], p[1], floor))
    P = np.asarray(pts, 'f8')

    def ground(x, z):
        x, z = np.asarray(x, 'f8'), np.asarray(z, 'f8'); shape = np.shape(x)
        q = np.c_[x.ravel(), z.ravel()]; out = np.empty(len(q))
        for a in range(0, len(q), 2048):
            d = ((q[a:a + 2048, None, :] - P[None, :, :2]) ** 2).sum(-1)
            out[a:a + 2048] = P[np.argmin(d, axis=1), 2]
        return out.reshape(shape)
    return ground


def _bowl_rect(bowl, grow=0.):
    """The bowl's coping as a rounded rectangle (k, 2) grown by `grow`: centre, axis, size; corner radius 25 m (or half
    the width), so primitives.bowl never folds at its ends."""
    (cx, cz), (L, W) = bowl.centre, bowl.size
    L, W = L + 2 * grow, W + 2 * grow
    a = math.radians(bowl.axis); u = np.array([math.cos(a), math.sin(a)]); v = np.array([-u[1], u[0]])
    c = np.array([cx, cz])
    return np.array([c + u * x * L / 2 + v * z * W / 2 for x, z in ((1, 1), (-1, 1), (-1, -1), (1, -1))])


def _inside(poly, p):
    """Point in convex polygon (counter-clockwise or clockwise)."""
    sgn = None
    for a, b in zip(poly, np.roll(poly, -1, 0), strict=True):
        c = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
        if sgn is None:
            sgn = c >= 0
        elif (c >= 0) != sgn:
            return False
    return True


def build_stop(line):
    """Where build_line stops: before the first berm turning more than 100 degrees (a bank primitive, not a ramp), and
    3 m before the line's path enters its exit bowl's coping plus deck (the bowl owns its rim)."""
    stops = [f.s0 for f in line.features if f.kind == 'berm' and abs(f.params.get('turn_deg', 0)) > 100]
    bowl = next((b for b in BOWLS if b.id == line.exit), None)
    if bowl is not None:
        poly = _bowl_rect(bowl, bowl.deck + 1.)
        for s in np.arange(exit_station(line)[0], line.path.length, 1.):
            if _inside(poly, line.path.at(s)[0]):
                stops.append(max(s - 3., 0.)); break
    return min(stops + [line.path.length])


def clip(s0, y0, a0, parts, lo, hi):
    """A surface's parts between plan distances lo and hi: (lo', y, degrees, parts) or None if nothing is left."""
    from craterpark.additions import profile
    lo = max(lo, s0)
    if hi <= lo + 1e-6:
        return None
    s, y, a, keep = s0, y0, a0, []
    for part in parts:
        k = profile(y, a, [part], .05)
        e = s + k[-1][0]
        if keep or e > lo + 1e-9:
            if not keep and lo > s + 1e-9:                     # split the part that straddles lo
                ks = np.asarray(k, 'f8')
                y = float(np.interp(lo - s, ks[:, 0], ks[:, 1])); a = float(np.interp(lo - s, ks[:, 0], ks[:, 2]))
                part = ('line', e - lo) if part[0] == 'line' else part
                s = lo
            if not keep:
                start = (s, y, a)
            keep.append(part)
        s, y, a = e, k[-1][1], k[-1][2]
    if not keep:
        return None
    kept = cut(*start, keep, hi)
    return (*start, kept) if kept else None


def _profile_at(line, s):
    """Height and slope at a built station, preserving each gap's length and drop."""
    from craterpark.additions import profile
    for s0, y0, a0, parts in pieces(line):
        k = np.asarray(profile(y0, a0, list(parts), .02), 'f8')
        if s0 - 1e-7 <= s <= s0 + k[-1, 0] + 1e-7:
            return float(np.interp(s - s0, k[:, 0], k[:, 1])), float(np.interp(s - s0, k[:, 0], k[:, 2]))
    raise ValueError(f'{line.id}: station {s:.6f} is not on a built profile')


def elbow_spec(line, index):
    """B's interface for the `index`-th elbow of a line (an `elbow_qp`): the corner W where the rider meets the wall,
    the drift along it to E, the unit normal `n` into the riding side (the bisector, away from the wall), the wall
    direction `t`, the apron plane y(p) = y + grade_t * ((p - W) . t) (level: grade_t 0 on v3 lines), the transition
    `r`, `vert`, `deck`, the apron depth, the wall's centre and half length, and where each leg's whole end section
    clears the apron (s_in, s_out)."""
    s_w, W, h_in, h_out, prm = line.path.elbows()[index]
    W = np.asarray(W, 'f8')
    A = np.array([math.cos(math.radians(h_in)), math.sin(math.radians(h_in))])
    B = np.array([math.cos(math.radians(h_out)), math.sin(math.radians(h_out))])
    n = (B - A) / np.linalg.norm(B - A); t = np.array([-n[1], n[0]])
    drift = float(prm.get('drift', 0.))
    # The angle bisector also defines a full reversal's drift; A+B is zero
    # for 180 degrees and used to collapse its two approach ports together.
    bisector = math.radians((h_in + h_out) / 2)
    u = np.array([math.cos(bisector), math.sin(bisector)])
    E = W + u * drift; mid = (W + E) / 2
    y, deg = _profile_at(line, s_w)
    at = float(A @ t)
    grade_t = math.tan(math.radians(deg)) / at if abs(at) > 1e-6 else 0.
    apron = float(prm.get('apron', 6.)); w = float(prm.get('width', 16.))
    an, bn = max(-float(A @ n), 1e-6), max(float(B @ n), 1e-6)
    d_in = (apron + w / 2 * abs(at)) / an
    d_out = (apron + w / 2 * abs(float(B @ t))) / bn
    reach = drift / 2 + max(abs(d_in * at) + w / 2 / an, abs(d_out * float(B @ t)) + w / 2 / bn)
    return {'line': line.id, 'index': index, 'kind': prm.get('kind', 'elbow_qp'), 'corner': (float(W[0]), float(W[1])),
            'exit_corner': (float(E[0]), float(E[1])), 'centre': (float(mid[0]), float(mid[1])), 'drift': drift,
            'y': y, 'n': tuple(n), 't': tuple(t), 'grade_t': grade_t, 'r': float(prm.get('r', 6.)),
            'vert': float(prm.get('vert', 1.)), 'deck': float(prm.get('deck', 2.)), 'apron': apron,
            'half_length': max(float(prm.get('half_length', 0.)), reach + 2., float(prm.get('lip_min', 40.)) / 2),
            'width': w, 's': s_w, 's_in': s_w - d_in, 's_out': s_w + drift + d_out, 'heading_in': h_in,
            'heading_out': h_out, 'material': PALETTE['concrete'], 'label': prm.get('label', '')}


def half_bowl_spec(line, f):
    """B's interface for a half bowl (a `half_bowl` feature over a path turn): a quarter pipe on a concave arc whose
    floor strip is the riding surface across the turn, so the run's floor flows round and up the wall. Centre, the
    riding radius, the lip radius (riding radius + half the floor + 0.5 + r), the angles, floor y (level), r, vert,
    deck."""
    turn = next(p for p in line.path.pieces() if p[0] == 'turn' and abs(p[1] - f.s0) < .05)
    _, s0, s1, (x, z), h, R, d = turn
    a = math.radians(h); sg = 1. if d > 0 else -1.
    cx, cz = x - sg * R * math.sin(a), z + sg * R * math.cos(a)
    r = float(f.params.get('r', 7.)); vert = float(f.params.get('vert', 1.))
    y, _ = _profile_at(line, s0)
    return {'line': line.id, 'feature': f.id, 'centre': (cx, cz), 'riding_radius': R, 'turn': d,
            'start_deg': math.degrees(math.atan2(z - cz, x - cx)), 'floor': f.width + .5,
            'lip_radius': R + f.width / 2 + .5 + r, 'floor_y': y, 'r': r, 'vert': vert,
            'deck': float(f.params.get('deck', 2.)), 's_in': s0, 's_out': s1}


def breaks(line):
    """Ranges owned by integral elbow aprons; half bowls remain continuous swept runs."""
    out = [(e['s_in'], e['s_out']) for e in (elbow_spec(line, i) for i in range(len(line.path.elbows())))]
    return sorted(out)


def surfaces(line):
    """The surfaces build_line makes, in riding order: dicts with s0, y0, degrees, parts (additions semantics), the leg
    (index, s0, Turtle), and the open gaps before and after (metres, or 0). A surface runs between gaps, elbow aprons
    and half bowls only: never a seam mid-surface."""
    from craterpark.additions import profile
    stop = build_stop(line)
    legs = line.path.legs()
    ps = [p for p in pieces(line, start='exit') if p[0] < stop - 1e-6]
    ends = [p[0] + profile(p[1], p[2], list(p[3]))[-1][0] for p in ps]
    free, lo = [], 0.
    for a, b in breaks(line):
        free.append((lo, a)); lo = b
    free.append((lo, stop))
    out = []
    for k, (s0, y0, a0, parts) in enumerate(ps):
        before = s0 - ends[k - 1] if k else 0.
        after = ps[k + 1][0] - ends[k] if k + 1 < len(ps) else 0.
        for f0, f1 in free:
            lo_, hi_ = max(s0, f0), min(ends[k], f1, stop)
            if hi_ - lo_ < .05:
                continue
            li, (L0, _, turtle) = next((i, g) for i, g in enumerate(legs) if g[0] - 1e-6 <= (lo_ + hi_) / 2 <= g[1] + 1e-6)
            c = clip(s0, y0, a0, parts, lo_, hi_)
            if c is None:
                continue
            out.append({'s0': c[0], 'y0': c[1], 'degrees': c[2], 'parts': c[3], 'leg': (li, L0, turtle), 'piece': k,
                        'gap_before': before if abs(c[0] - s0) < 1e-6 else 0.,
                        'gap_after': after if abs(hi_ - ends[k]) < 1e-6 else 0.})
    return out


def _ride_tags(parts, gap_before, gap_after):
    """Face tags: a surface after a gap is 'landing' down to its run-out (its first arc back to -6 degrees or flatter);
    a surface before a gap is 'takeoff' on its last arc (the kicker's)."""
    from .primitives import tagged
    arcs = [i for i, p in enumerate(parts) if p[0] == 'arc']
    if gap_after and arcs:
        parts = tagged(parts, 'takeoff', [arcs[-1]])
    if gap_before:
        run = next((i for i in arcs if parts[i][2] >= -7. and (not gap_after or i != arcs[-1])), len(parts) - 1)
        parts = tagged(parts, 'landing', list(range(run + 1)))
    return parts


def run_side(width):
    """The owner's rule: bowl walls on both sides of every run (B's Side('bowl'), R about 3.5 m, about 3 m tall, capped);
    bank flanks until B's primitive has it."""
    from . import primitives as P
    try:
        return P.Side('bowl')
    except (ValueError, TypeError):
        return 'bank'


def run_sides(line, width):
    """Continuous shoulders: the outside grows to R7 + 1 m vert through a half bowl."""
    from . import primitives as P
    from .bowls import smootherstep
    out = []
    for sign in (1., -1.):                    # left, right
        turns = []
        for f in line.features:
            if f.kind != 'half_bowl':
                continue
            piece = next(p for p in line.path.pieces() if p[0] == 'turn' and abs(p[1] - f.s0) < .05)
            if math.copysign(1., piece[-1]) == -sign:
                turns.append(f)
        if not turns:
            out.append(run_side(width))
            continue

        def shape(E, turns=tuple(turns)):
            s, _ = line.path.project(E[:, [0, 2]])
            w = np.zeros(len(s))
            for f in turns:
                w = np.maximum(w, np.minimum(smootherstep((s - f.s0 + 40.) / 40.),
                                              smootherstep((f.s1 + 40. - s) / 40.)))
            return 3. + 5. * w, 3.5 + 3.5 * w

        out.append(P.Side('bowl', height=8., radius=7., shape=shape))
    return out


def build_line(line, ground=None, side=None, on_ground=False, extras=None):
    """Compile a line with B's primitives, from the tower roll-in's exit section (exit_station) to build_stop: every
    surface (between gaps, elbow aprons and half bowls) is one primitives.ramp on its leg, with a wall end at a gap (the
    kicker's back, the landing's front) and flush ends elsewhere; each elbow and half bowl is a quarter pipe (B's
    elbow_qp / half_bowl when they exist). Widths are each surface's widest feature. Returns a primitives.Built."""
    from craterpark.additions import profile

    from . import dsl
    from . import primitives as P

    def width(s0, s1):
        return max([f.width for f in line.features
                    if f.kind not in ('gap', 'bowl_entry', 'elbow_qp', 'half_bowl') and f.s0 < s1 - .05 and f.s1 > s0 + .05]
                   or [16.])

    from . import junctions
    elbows = [elbow_spec(line, i) for i in range(len(line.path.elbows()))]
    port_rows = [{} for _ in elbows]
    built, checks, last = [], [], {}
    for n, sf in enumerate(surfaces(line)):
        _, L0, turtle = sf['leg']
        parts = list(sf['parts'])
        s1 = sf['s0'] + profile(sf['y0'], sf['degrees'], parts)[-1][0]
        prof = P.from_additions(sf['y0'], sf['degrees'], parts)
        prof = dsl.Profile(_ride_tags(prof.parts, sf['gap_before'], sf['gap_after']), start=tuple(prof.start),
                           degrees=prof.degrees, tags=prof.tags)
        name = f'{line.id}.{n}'
        w = width(sf['s0'], s1)
        sides = [side, side] if side is not None else run_sides(line, w)
        at_start = [i for i, e in enumerate(elbows) if abs(sf['s0'] - e['s_out']) < 1e-5]
        at_end = [i for i, e in enumerate(elbows) if abs(s1 - e['s_in']) < 1e-5]
        if at_start or at_end:
            for j, sd in enumerate(sides):
                if isinstance(sd, P.Side) and sd.kind == 'bowl':
                    fade = sd.fade or (P.BOWL_FADE if sf['gap_before'] else 0., P.BOWL_FADE if sf['gap_after'] else 0.)
                    sides[j] = replace(sd, fade=(max(fade[0], 20.) if at_start else fade[0],
                                                  max(fade[1], 20.) if at_end else fade[1]))
        b = P.ramp(curve(turtle), prof, w, start=sf['s0'] - L0, left=sides[0], right=sides[1], ground=ground,
                   ends=('wall' if sf['gap_before'] else 'flush', 'wall' if sf['gap_after'] else 'flush'),
                   feature=name, on_ground=on_ground)
        built.append(b)
        if on_ground:
            for ids, station, key in ((at_start, sf['s0'], 'out'), (at_end, s1, 'in')):
                for i in ids:
                    point, tangent = line.path.at(station)
                    port_rows[i][key] = junctions.boundary_row(b.mesh, point, tangent)
        if sf['gap_before'] and last.get('gap_after'):
            lip_p, _ = line.path.at(last['s1'])
            land_p, _ = line.path.at(sf['s0'])
            checks.append({'feature': last['name'], 'kind': 'air', 'lip': [float(lip_p[0]), last['y1'], float(lip_p[1])],
                           'lip_degrees': last['deg1'], 'gap': float(sf['s0'] - last['s1']), 'landing': name,
                           'landing_start': [float(land_p[0]), float(sf['y0']), float(land_p[1])],
                           'landing_t': (float(sf['s0']), float(s1))})
        k = profile(sf['y0'], sf['degrees'], parts)
        last = {'name': name, 's1': s1, 'y1': float(k[-1][1]), 'deg1': float(k[-1][2]), 'gap_after': sf['gap_after']}
    walls = built if extras is None else extras
    for i, e in enumerate(elbows):
        rows = [port_rows[i][k] for k in ('in', 'out')] if on_ground else None
        walls.append(build_elbow(e, ground=ground, on_ground=on_ground, checks=checks, rows=rows))
    for f in line.features:
        if f.kind == 'half_bowl' and f.s0 < build_stop(line):
            checks.append({'kind': 'half_bowl', 'feature': f.id, 's0': f.s0, 's1': f.s1,
                           'wall_radius_m': 7., 'wall_height_m': 8., 'continuous_with_run': True})
    out = P.Built.concat(built)
    out.checks += checks
    return out


def _on_site(built, margin=1.):
    """Every foot point of a Built on the r4 block (placement.contains)."""
    from . import ground as G
    pts = np.concatenate([np.asarray(f, 'f8') for f in built.foot]) if built.foot else built.mesh.V
    return bool(G.even_odd(pts[:, [0, 2]], [_site2()]).all())


_SITE = []


def _site2():
    """A's site outline in plan (ground.r4_site), cached."""
    if not _SITE:
        from . import ground as G
        _SITE.append(G.r4_site()[:, [0, 2]])
    return _SITE[0]


def build_elbow(spec, ground=None, on_ground=False, checks=None, rows=None):
    """One integral apron and vert turn, cut to the exact approach sections."""
    from .junctions import elbow
    return elbow(spec, ground=ground, on_ground=on_ground, rows=rows)


def build_half_bowl(spec, ground=None, on_ground=False):
    """A half bowl: B's primitives.half_bowl(spec) when it exists, else a primitives.quarter_pipe along the concave lip
    arc (deck outside), its floor strip the riding surface round the turn."""
    from . import primitives as P
    from .curves import Arc
    fn = getattr(P, 'half_bowl', None)
    if fn is not None:
        return fn(spec, ground=ground, on_ground=on_ground)
    arc = Arc(spec['centre'], spec['lip_radius'], spec['start_deg'], spec['turn'])
    return P.quarter_pipe(arc, floor_y=spec['floor_y'], height=spec['r'] + spec['vert'], radius=spec['r'],
                          deck=spec['deck'], floor=spec['floor'], side=-1 if spec['turn'] > 0 else 1, ground=ground,
                          feature=spec['feature'], on_ground=on_ground)


# ---------------------------------------------------------------- the bowl complex interface (F's bowls.py)
def bowl_outline(bowl, step=1.):
    """The bowl's coping line as a closed plan polyline (k, 2), counter-clockwise: an ellipse `size` (length along
    `axis`, width) round `centre`, or the r4 source outline moved to `centre` when `copy_from` names one (F reads the
    r4 meshes; this returns the ellipse that bounds it)."""
    (cx, cz), (L, W) = bowl.centre, bowl.size
    n = max(16, math.ceil(math.pi * (L + W) / 2 / step))
    t = np.linspace(0., 2 * math.pi, n, endpoint=False)
    a = math.radians(bowl.axis)
    x, z = L / 2 * np.cos(t), W / 2 * np.sin(t)
    return np.c_[cx + x * math.cos(a) - z * math.sin(a), cz + x * math.sin(a) + z * math.cos(a)]


def bowl_wall(bowl):
    """The wall section from floor to coping, for primitives.bowl: radius, depth, vertical top and deck."""
    return {'floor_y': bowl.floor_y, 'depth': bowl.rim_y - bowl.floor_y, 'radius': bowl.r, 'vert': bowl.vert,
            'top_degrees': 90. if bowl.vert > 0 else None, 'deck': bowl.deck, 'material': bowl.material,
            'coping': bowl.coping, 'max_entry_mps': bowl.max_entry}


# ---------------------------------------------------------------- the compiled park (generate.py calls park())
SPAWN_DECK_Y = None         # park() sets the tower deck's y once B's tower builds; until then spawns stand at the exits


def exit_speed(line, v0=1.):
    """The modelled speed at the roll-in's exit section from `v0` at the crest (MEASURED_DRAG)."""
    s_exit = exit_station(line)[0]
    k = np.asarray([p for p in knots(line, .25) if p[0] <= s_exit + 1e-6])
    v = float(v0)
    for (s0, y0, _), (s1, y1, _) in itertools.pairwise(k):
        drag = float(np.interp(v, *MEASURED_DRAG))
        v = math.sqrt(max(v * v - 2 * 9.81 * (y1 - y0) - 2 * drag * math.hypot(s1 - s0, y1 - y0), 0.))
    return v


def ride_line(line, built):
    """The dsl.RideLine of a built line: its centre path from the exit section to build_stop (2 m steps, on the
    surface; gaps follow the ballistic chord), the spawn 1 m past the exit section facing down the line, and its airs."""
    from . import dsl
    s_exit, _, _, _, heading = exit_station(line)
    stop = build_stop(line)
    deck = SPAWN_DECK_Y is not None
    first = 0. if deck else s_exit
    k = np.asarray([p for p in knots(line, 1.) if first - 1e-6 <= p[0] <= stop + 1e-6])
    pts = np.array([(*line.path.at(s)[0], y) for s, y, _ in k[::2]])
    path = pts[:, [0, 2, 1]]
    if deck:                    # on the tower deck, 2 m behind the roll-in's crest, facing down it
        heading = line.path.heading
        d = np.array([math.cos(math.radians(heading)), math.sin(math.radians(heading))])
        p0, y0 = np.asarray(line.path.start, 'f8') - 2. * d, float(TOWER['y'])
    else:
        s0 = s_exit + 1.
        y0 = float(np.interp(s0, k[:, 0], k[:, 1])); p0, _ = line.path.at(s0)
    names = list(built.mesh.features)
    airs = [(c['feature'], c['landing']) for c in built.checks if c.get('kind') == 'air']
    return dsl.RideLine(line.id, names, path, ((float(p0[0]), y0, float(p0[1])), heading), tuple(path[-1]),
                        entry_speed=(1., 8.) if deck else (round(exit_speed(line, 1.), 1), round(exit_speed(line, 8.), 1)),
                        airs=airs)


def park():
    """The whole park as a dsl.Park: every line from its roll-in exit to build_stop, on A's ground landform (the lines'
    foot loops are its holes), plus B's tower and F's bowl complex when their modules land. Interim slab: the lines'
    flanks bank down to slab_ground() (2 m under the nearest riding station), where the landform takes over."""
    from . import dsl
    from . import primitives as P
    slab = slab_ground()
    walls = []
    built = {line.id: build_line(line, ground=slab, on_ground=True, extras=walls) for line in LINES}
    parts = list(built.values()); checks = [c for b in parts for c in b.checks]
    global SPAWN_DECK_Y
    SPAWN_DECK_Y = None
    if hasattr(P, 'tower'):                 # B: the tower solid with its roll-ins to the exit sections
        try:
            parts.append(P.tower(TOWER, tower_exits(), ground=slab))
            SPAWN_DECK_Y = TOWER['y']
        except ValueError as error:         # e.g. crests too close for the deck: spawn at the exits meanwhile
            checks.append({'kind': 'todo', 'what': 'tower', 'owner': 'B/G', 'error': str(error)})
    else:
        checks.append({'kind': 'todo', 'what': 'tower', 'owner': 'B', 'note': 'lines start at the roll-in exit sections'})
    try:
        from . import bowls  # F: the bowl complex from BOWLS and LINKS
    except ImportError:
        bowls = None
    complex_ = None
    if bowls is not None and hasattr(bowls, 'complex'):
        try:
            complex_ = bowls.complex(only=('crater_bowl',), on_ground=True)
        except Exception as error:  # noqa: BLE001 (F's module in progress: keep the park visible, placeholder)
            checks.append({'kind': 'todo', 'what': 'bowl complex failed, placeholder used', 'owner': 'F',
                           'error': f'{type(error).__name__}: {error}'[:300]})
    if complex_ is None:                    # placeholder until F lands: the Crater Bowl as B's bowl at its outline
        complex_ = crater_placeholder(slab)
        checks.append({'kind': 'todo', 'what': 'bowl complex (Crater Bowl is a placeholder)', 'owner': 'F'})
    parts.append(complex_)
    from . import ground as G
    # Turns are required route geometry. Never hide a placement defect by
    # dropping its wall; validation must reject the assembled park instead.
    parts.extend(walls)
    feet = _merged_feet(parts)
    import re
    for _ in range(40):                     # a hole the ground refuses (overlap, off the site): the ground runs on
        try:                                # without it, and the check names the place (preview over perfection)
            land = G.ground(G.r4_site(), holes=feet, guide=G.r4_block_controls())
            break
        except ValueError as error:
            m = re.search(r'foot loop (\d+) (?:overlaps foot loop (\d+)|leaves the site)', str(error))
            if not m:                       # the landform can't take these feet yet: show the park without it
                checks.append({'kind': 'todo', 'what': 'ground landform left out', 'owner': 'A/D',
                               'error': str(error)[:200]})
                land = None
                break
            drop = int(m.group(2) or m.group(1))
            checks.append({'kind': 'todo', 'what': 'ground hole left out', 'owner': 'D/G', 'error': str(error)[:200],
                           'where': np.asarray(feet[drop]).mean(0).round(1).tolist()})
            feet = feet[:drop] + feet[drop + 1:]
    mesh = dsl.Mesh.concat([b.mesh for b in parts] + ([land] if land is not None else []))
    lines = [ride_line(line, built[line.id]) for line in LINES]
    for line in LINES:
        checks.append({'kind': 'speed', 'line': line.id, 'exit_speed_mps': [round(exit_speed(line, v), 2) for v in (1., 4., 8.)],
                       'bowl_entry_max_mps': next(b.max_entry for b in BOWLS if b.id == line.exit)})
    return dsl.Park(mesh, [r for b in parts for r in b.rails], lines, checks)


def site_outline(G, inset=.985):
    """r4's site outline (ground.r4_site) pulled in about its centroid by `inset`: r4_site's spline runs up to 1 m past
    the block's own edge at its corners (dressing.check rejects any face off placement.contains)."""
    o = G.r4_site()
    c = o[:, [0, 2]].mean(0)
    o = o.copy(); o[:, [0, 2]] = c + (o[:, [0, 2]] - c) * inset
    return o


def _loops_overlap(a, b):
    from . import ground as G
    a, b = np.asarray(a, 'f8')[:, [0, 2]], np.asarray(b, 'f8')[:, [0, 2]]
    if (a.min(0) > b.max(0)).any() or (b.min(0) > a.max(0)).any():
        return False
    return bool(G.even_odd(a, [b]).any() or G.even_odd(b, [a]).any())


def _merged_feet(parts):
    """The ground's holes: the open loops of all on-ground parts together (solids.check_open), so the tower's exit
    rows and the lines' start rows merge into one loop (B); each part's own feet if the union is not manifold."""
    from . import dsl
    from .solids import check_open
    try:
        return [np.asarray(f, 'f8') for f in check_open(dsl.Mesh.concat([b.mesh for b in parts]), name='park')]
    except ValueError:
        return [np.asarray(f, 'f8') for b in parts for f in b.foot]


def crater_placeholder(ground=None):
    """The Crater Bowl as B's primitives.bowl on its rounded-rectangle outline, rim and floor (F's bowls.py replaces it)."""
    from . import primitives as P
    b = next(b for b in BOWLS if b.id == 'crater_bowl')
    return P.bowl(P.Rounded(_bowl_rect(b), 25., closed=True), floor_y=b.floor_y, depth=b.rim_y - b.floor_y, radius=b.r,
                  deck=b.deck, top_degrees=90. if b.vert > 0 else None, ground=ground, feature='crater_bowl', on_ground=True)


def tower_exits():
    """B's tower interface: per line, the roll-in (its profile parts from the deck at TOWER['y']) and the exit section
    it must end on exactly: s, y, degrees, plan point (x, z), heading degrees and width."""
    out = {}
    for line in LINES:
        s, y, a, p, h = exit_station(line)
        f = next(f for f in line.features if f.kind == 'roll_in')
        out[line.id] = {'crest': line.path.start, 'heading': line.path.heading, 'rollin': line.profile[:line.rollin],
                        'path': curve(line.path.until(s + 1.)),
                        's': s, 'y': y, 'degrees': a, 'point': p, 'exit_heading': h, 'width': f.width,
                        'params': dict(f.params)}
    return out


# ---------------------------------------------------------------- the park's lines: G's v3 plan (a design file wins)
LINES = load_design() if DESIGN.exists() else tuple(plan_line(k) for k in V3_PLAN)
LINE_LABELS = {line.id: line.name for line in LINES}
