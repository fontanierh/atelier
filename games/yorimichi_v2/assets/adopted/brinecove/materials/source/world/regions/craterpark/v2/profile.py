"""2D profiles: a chain of parts in the (x, y) plane, x horizontal (across or along a path), y up, evaluated by the
profile's own arc length s (plan/pipeline.md 3.1, as additions.profile).

Parts (each may end with a dict of attributes, e.g. {'role': 'side', 'material': 'material_023', 'tag': 'landing'}):
- ('line', L): straight on at the current angle for L metres;
- ('arc', R, to_deg): a circle of radius R turning from the current angle to the absolute angle to_deg (degrees from
  +x, counter-clockwise toward +y): ('arc', 3.5, 90) turns a flat floor up into a vertical wall;
- ('corner', to_deg): a crease, zero length, the angle jumps to to_deg (a lip, a wall top). Creases split vertices.

Profile(parts, start=(0, 0), degrees=0, tags=None, role='riding', material=CONCRETE): `tags` names parameters, e.g.
{'lip': 'end'} or {'foot': 0.0}; a value is an s, 'start', 'end' or a part index k (the start of part k).
"""
import math

import numpy as np

from .curves import adaptive, merge_params


class Profile:
    def __init__(self, parts, start=(0., 0.), degrees=0., tags=None, role='riding', material='material_010', tag=''):
        self.start = np.asarray(start, 'f8'); self.degrees = float(degrees)
        self.parts, self.attrs = [], []
        default = {'role': role, 'material': material, 'tag': tag}
        # per part: kind, s0, s1, x0, y0, a0 (rad), a1 (rad), radius, signed turn
        x, y, a, s = self.start[0], self.start[1], math.radians(degrees), 0.
        self.knots, self.creases = [0.], []
        self.rows = []
        for part in parts:
            attrs = dict(default)
            if isinstance(part[-1], dict):
                attrs.update(part[-1]); part = part[:-1]
            kind = part[0]
            if kind == 'line':
                L = float(part[1])
                self.rows.append(('line', s, s + L, x, y, a, a, 0., 0.))
                x += L * math.cos(a); y += L * math.sin(a); s += L
            elif kind == 'arc':
                R, to = float(part[1]), math.radians(part[2])
                turn = to - a; L = R * abs(turn)
                self.rows.append(('arc', s, s + L, x, y, a, to, R, math.copysign(1., turn)))
                # centre on the turning side: left normal (-sin a, cos a) for a positive turn
                sg = math.copysign(1., turn)
                cx, cy = x - sg * R * math.sin(a), y + sg * R * math.cos(a)
                x, y = cx + sg * R * math.sin(to), cy - sg * R * math.cos(to)
                a = to; s += L
            elif kind == 'corner':
                to = math.radians(part[1])
                self.rows.append(('corner', s, s, x, y, a, to, 0., 0.))
                if abs(to - a) > 1e-12:
                    self.creases.append(s)
                a = to
            else:
                raise ValueError(f'unknown profile part {part!r}')
            self.parts.append(part); self.attrs.append(attrs)
            self.knots.append(s)
        self.length = s
        self.end = np.asarray([x, y]); self.end_degrees = math.degrees(a)
        self.tags = {}
        for name, where in (tags or {}).items():
            self.tags[name] = self._resolve(where)

    def _resolve(self, where):
        if where == 'start':
            return 0.
        if where == 'end':
            return self.length
        if isinstance(where, int):
            return self.knots[where]
        return float(where)

    def _row(self, s, right=True):
        """Index of the non-corner part holding each s (right: the part starting at s on a knot)."""
        s = np.atleast_1d(np.asarray(s, 'f8'))
        spans = [(i, r) for i, r in enumerate(self.rows) if r[0] != 'corner']
        s0 = np.asarray([r[1] for _, r in spans]); s1 = np.asarray([r[2] for _, r in spans])
        idx = np.searchsorted(s0, s, 'right') - 1 if right else np.searchsorted(s1, s, 'left')
        idx = np.clip(idx, 0, len(spans) - 1)
        return np.asarray([spans[i][0] for i in idx], 'i8') if len(spans) else np.zeros(len(s), 'i8'), s

    def _eval(self, s, right=True):
        rows, s = self._row(s, right)
        x = np.zeros(len(s)); y = np.zeros(len(s)); ang = np.zeros(len(s)); k = np.zeros(len(s))
        for i in np.unique(rows):
            m = rows == i; kind, s0, s1, x0, y0, a0, a1, R, sg = self.rows[i]
            d = np.clip(s[m] - s0, 0., s1 - s0)
            if kind == 'line':
                x[m] = x0 + d * math.cos(a0); y[m] = y0 + d * math.sin(a0); ang[m] = a0
            else:
                cx, cy = x0 - sg * R * math.sin(a0), y0 + sg * R * math.cos(a0)
                a = a0 + sg * d / R
                x[m] = cx + sg * R * np.sin(a); y[m] = cy - sg * R * np.cos(a); ang[m] = a; k[m] = sg / R
        return x, y, ang, k, rows

    def point(self, s):
        """(n, 2) points (x, y) at s."""
        x, y, *_ = self._eval(s)
        return np.stack([x, y], 1)

    def angle(self, s, right=True):
        """Tangent angle in radians at s (right: just after a crease, else just before)."""
        return self._eval(s, right)[2]

    def tangent(self, s, right=True):
        a = self.angle(s, right)
        return np.stack([np.cos(a), np.sin(a)], 1)

    def curvature(self, s):
        return self._eval(s)[3]

    def part_of(self, s, right=True):
        """Index into `parts`/`attrs` of the part holding s."""
        return self._eval(s, right)[4]

    def samples(self, tess, extra=()):
        """Adaptive s: each arc at the smallest step of chord, angle and max edge (dsl.Tess), lines at max_edge; every
        knot (part joins, creases) and tag kept, plus `extra`."""
        spans = [(r[1], r[2]) for r in self.rows if r[0] != 'corner' and r[2] > r[1]]

        def density(s):
            return tess.density(self.curvature(s))
        s = adaptive(spans, density)
        keep = list(self.knots) + list(self.tags.values()) + [x for x in np.ravel(extra) if 0 <= x <= self.length]
        return merge_params(s, keep)
