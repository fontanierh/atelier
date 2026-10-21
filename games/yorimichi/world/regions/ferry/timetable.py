"""The ferry's timetable: when the ship is where, as a pure function of the service time (pure Python).

A voyage is a list of legs, each one of site.py's moves from where the last one ended. Consecutive ahead and arc legs
are one run: the ship gathers way from rest, holds each leg's speed limit (slow inside a harbour, cruising at sea and
slow enough on an arc for a gentle turn) and comes to rest at the run's end. Every other move (a crab onto or off the
berth, a glide, a pivot) starts and ends at rest. A cycle is: standing at the first berth, the voyage to the second,
standing there, the voyage back. Every ship on the line sails the same cycle, offset in time.

sample() tabulates the cycle every DT seconds: position, heading, velocity, turn rate, throttle and thruster effort,
which the game interpolates (AFerryService, FFerryLine) from the replicated server clock, so every machine places the
ships alike without replicating their movement. phases() and brows() give what the ship's sounds and the terminals'
brows follow. Metres, seconds, degrees (0 east, 90 north); service.py converts to Unreal's units.
"""
import bisect
import math

SPEED = {
    'sea': 15.0,          # m/s cruising (about 29 knots): the sea crossing takes about four minutes
    'harbour': 6.0,       # m/s on the harbours' ahead legs
    'accel': 0.25,        # m/s^2 gathering way and stopping
    'lateral': 0.65,      # m/s^2 on an arc: the speed limit there is sqrt(lateral * radius)
    'crab': 0.9, 'crab_accel': 0.15,     # thrusters, sideways onto and off the berth
    'glide': 1.5, 'glide_accel': 0.15,   # engines and thrusters, heading held
    'pivot': 4.5, 'pivot_accel': 0.9,    # deg/s and deg/s^2, turning on the spot
}
DWELL = 120.0             # seconds standing at each berth, brow down for most of it
BROW = {'settle': 4.0,    # after the ship comes alongside, before the brow starts down
        'travel': 8.0,    # seconds to lower or raise it
        'before': 22.0}   # it starts up this long before the ship moves off
DT = 0.5                  # seconds between samples
STEP = 0.25               # metres (or degrees) of the speed profile's grid
PHASES = ('berthed', 'departing', 'cruise', 'approach')


def _profile(length, caps, accel):
    """Rest-to-rest speed along a run of `length` (metres or degrees). caps: [(start, limit)] by start, the limit holding
    until the next start. Returns (s grid, speed grid, time grid)."""
    n = max(1, int(math.ceil(length / STEP)))
    s = [length * i / n for i in range(n + 1)]
    starts = [c[0] for c in caps]
    cap = [caps[max(0, bisect.bisect_right(starts, x) - 1)][1] for x in s]
    v = list(cap)
    v[0] = v[-1] = 0.0
    ds = length / n
    for i in range(1, n + 1):
        v[i] = min(v[i], math.sqrt(v[i - 1] ** 2 + 2 * accel * ds))
    for i in range(n - 1, -1, -1):
        v[i] = min(v[i], math.sqrt(v[i + 1] ** 2 + 2 * accel * ds))
    t = [0.0]
    for i in range(n):
        t.append(t[-1] + 2 * ds / max(v[i] + v[i + 1], 1e-9))
    return s, v, t


class Leg:
    """One move from a pose: where it is after `along` (metres, or degrees for a pivot) and how it moves there."""

    def __init__(self, move, pose, phase, berth=None):
        self.move, self.kind, self.phase, self.berth = move, move[0], phase, berth
        self.x, self.y, self.h = pose
        k = self.kind
        self.length = (abs(move[1]) if k in ('ahead', 'crab', 'berth', 'pivot') else
                       abs(move[1] * math.radians(move[2])) if k == 'arc' else math.hypot(move[1], move[2]) if k == 'move' else 0.0)
        self.end = self.at(self.length)[:3]

    def at(self, a):
        """(x, y, heading deg, unit velocity x, y per unit `along`, heading rate deg per unit `along`)."""
        x, y, h, m, k = self.x, self.y, math.radians(self.h), self.move, self.kind
        if k in ('ahead', 'crab', 'berth'):
            sgn = 1.0 if m[1] >= 0 else -1.0
            ux, uy = (math.cos(h), math.sin(h)) if k == 'ahead' else (-math.sin(h), math.cos(h))
            return x + ux * sgn * a, y + uy * sgn * a, self.h, ux * sgn, uy * sgn, 0.0
        if k == 'move':
            L = max(self.length, 1e-9)
            return x + m[1] * a / L, y + m[2] * a / L, self.h, m[1] / L, m[2] / L, 0.0
        if k == 'pivot':
            sgn = 1.0 if m[1] >= 0 else -1.0
            return x, y, self.h + sgn * a, 0.0, 0.0, sgn
        if k == 'arc':
            R, sgn = m[1], (1.0 if m[2] > 0 else -1.0)
            cx, cy = x - sgn * R * math.sin(h), y + sgn * R * math.cos(h)
            hk = h + sgn * a / R
            return (cx + sgn * R * math.sin(hk), cy - sgn * R * math.cos(hk), math.degrees(hk), math.cos(hk), math.sin(hk),
                    sgn * math.degrees(1.0 / R))
        raise ValueError(k)

    def cap(self, sea):
        """The leg's speed limit (m/s, or deg/s for a pivot) and its acceleration."""
        k = self.kind
        if k == 'pivot':
            return SPEED['pivot'], SPEED['pivot_accel']
        if k in ('crab', 'berth'):
            return SPEED['crab'], SPEED['crab_accel']
        if k == 'move':
            return SPEED['glide'], SPEED['glide_accel']
        limit = SPEED['sea'] if sea else SPEED['harbour']
        if k == 'arc':
            limit = min(limit, math.sqrt(SPEED['lateral'] * abs(self.move[1])))
        return limit, SPEED['accel']


class Motion:
    """A run of ahead and arc legs, or one other leg, from rest to rest."""

    def __init__(self, legs):
        self.legs = legs
        self.offsets = [0.0]
        for leg in legs:
            self.offsets.append(self.offsets[-1] + leg.length)
        caps = [(o, leg.cap(leg.phase == 'cruise')[0]) for o, leg in zip(self.offsets, legs)]
        accel = legs[0].cap(legs[0].phase == 'cruise')[1]
        self.s, self.v, self.t = _profile(self.offsets[-1], caps, accel)
        self.duration = self.t[-1]

    def along(self, t):
        """(distance along the run, speed) at time t into it."""
        if t <= 0.0:
            return 0.0, 0.0
        if t >= self.duration:
            return self.s[-1], 0.0
        i = max(0, min(len(self.t) - 2, bisect.bisect_right(self.t, t) - 1))
        dt = self.t[i + 1] - self.t[i]
        a = (self.v[i + 1] - self.v[i]) / dt if dt > 0 else 0.0
        tau = t - self.t[i]
        return self.s[i] + self.v[i] * tau + 0.5 * a * tau * tau, self.v[i] + a * tau

    def leg_at(self, s):
        i = max(0, min(len(self.legs) - 1, bisect.bisect_right(self.offsets, s) - 1))
        return i, s - self.offsets[i]

    def state(self, t):
        s, v = self.along(t)
        i, a = self.leg_at(s)
        leg = self.legs[i]
        x, y, h, ux, uy, w = leg.at(a)
        limit = leg.cap(leg.phase == 'cruise')[0]
        if leg.kind == 'pivot':
            throttle, thruster = (0.35 if v > 1e-3 else 0.0), min(1.0, v / SPEED['pivot'])
        elif leg.kind in ('crab', 'berth'):
            throttle, thruster = (0.2 if v > 1e-3 else 0.0), min(1.0, v / SPEED['crab'])
        elif leg.kind == 'move':
            throttle, thruster = (0.35 if v > 1e-3 else 0.0), min(1.0, 0.6 * v / SPEED['glide'])
        else:
            throttle, thruster = (max(0.35, v / SPEED['sea']) if v > 1e-3 else 0.0), 0.0
        return {'x': x, 'y': y, 'h': h, 'vx': ux * v, 'vy': uy * v, 'w': w * v, 'speed': v if leg.kind != 'pivot' else 0.0,
                'throttle': throttle, 'thruster': thruster, 'phase': leg.phase, 'berth': None, 'limit': limit, 'kind': leg.kind}

    def phase_starts(self):
        """[(time, phase)] where the run enters each leg's phase."""
        out = []
        for o, leg in zip(self.offsets, self.legs):
            i = max(0, min(len(self.s) - 1, int(round(o / (self.s[-1] / (len(self.s) - 1)))))) if self.s[-1] > 0 else 0
            t = self.t[i]
            if not out or out[-1][1] != leg.phase:
                out.append((t, leg.phase))
        return out


class Dwell:
    def __init__(self, pose, seconds, berth):
        self.pose, self.duration, self.berth = pose, seconds, berth

    def state(self, t):
        x, y, h = self.pose
        return {'x': x, 'y': y, 'h': h, 'vx': 0.0, 'vy': 0.0, 'w': 0.0, 'speed': 0.0, 'throttle': 0.0, 'thruster': 0.0,
                'phase': 'berthed', 'berth': self.berth, 'limit': 0.0, 'kind': 'dwell'}

    def phase_starts(self):
        return [(0.0, 'berthed')]


def voyage(start, moves):
    """Legs of a voyage: [(phase, moves)] sailed in turn from pose start. Returns (motions, end pose)."""
    legs, pose = [], start
    for phase, ms in moves:
        for m in ms:
            leg = Leg(m, pose, phase)
            if leg.length > 1e-9:
                legs.append(leg)
            pose = leg.end
    motions, run = [], []
    for leg in legs:
        if leg.kind in ('ahead', 'arc'):
            run.append(leg); continue
        if run:
            motions.append(Motion(run)); run = []
        motions.append(Motion([leg]))
    if run:
        motions.append(Motion(run))
    return motions, pose


class Cycle:
    """One ship's cycle: [Dwell, Motion..., Dwell, Motion...], back to where it started."""

    def __init__(self, parts):
        self.parts = parts
        self.starts = [0.0]
        for p in parts:
            self.starts.append(self.starts[-1] + p.duration)
        self.duration = self.starts[-1]

    def state(self, t):
        t = t % self.duration
        i = max(0, min(len(self.parts) - 1, bisect.bisect_right(self.starts, t) - 1))
        return self.parts[i].state(t - self.starts[i])

    def phases(self):
        """[(start, end, phase, berth)] over the cycle, merged where a phase runs on across parts."""
        out = []
        for start, part in zip(self.starts, self.parts):
            for t, phase in part.phase_starts():
                berth = part.berth if isinstance(part, Dwell) else None
                if out and out[-1][2] == phase and out[-1][3] == berth:
                    continue
                if out:
                    out[-1][1] = start + t
                out.append([start + t, None, phase, berth])
        out[-1][1] = self.duration
        return [tuple(p) for p in out]

    def dwells(self):
        """[(berth, comes alongside, moves off)] in cycle time."""
        return [(p.berth, s, s + p.duration) for s, p in zip(self.starts, self.parts) if isinstance(p, Dwell)]


def brows(cycle, berths):
    """Per berth, the brow's windows in cycle time: (lowering starts, down, raising starts, up)."""
    out = {b: [] for b in range(berths)}
    for berth, alongside, off in cycle.dwells():
        lower = alongside + BROW['settle']
        raise_ = off - BROW['before']
        if raise_ < lower + BROW['travel'] or raise_ + BROW['travel'] > off:
            raise ValueError('the dwell is too short for the brow')
        out[berth].append((lower, lower + BROW['travel'], raise_, raise_ + BROW['travel']))
    return out


def sample(cycle, dt=DT):
    """The cycle tabulated every dt seconds (dt shrinks a little so the cycle holds a whole number of samples)."""
    n = max(2, int(round(cycle.duration / dt)))
    step = cycle.duration / n
    return step, [cycle.state(i * step) for i in range(n)]


def hermite(samples, step, t):
    """The pose at time t from the samples, as the game interpolates them (cubic Hermite on position and heading)."""
    n = len(samples)
    f = (t / step) % n
    i = int(f) % n
    j = (i + 1) % n
    u = f - int(f)
    a, b = samples[i], samples[j]
    h00, h10, h01, h11 = 2 * u ** 3 - 3 * u ** 2 + 1, u ** 3 - 2 * u ** 2 + u, -2 * u ** 3 + 3 * u ** 2, u ** 3 - u ** 2
    x = h00 * a['x'] + h10 * step * a['vx'] + h01 * b['x'] + h11 * step * b['vx']
    y = h00 * a['y'] + h10 * step * a['vy'] + h01 * b['y'] + h11 * step * b['vy']
    dh = (b['h'] - a['h'] + 180.0) % 360.0 - 180.0
    h = a['h'] + h00 * 0 + h10 * step * a['w'] + h01 * dh + h11 * step * b['w']
    return x, y, h

