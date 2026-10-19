"""The Belmonte terminus's approach (route v4): the alignment keeps the former terminus's coastal curve, so the
shoreline's railway headlands stay where they were, then turns onto the station's axis under the road's overbridge
(world/train/overbridge.py). The overbridge is regular and the ground fits it (earthworks.bridge_ground): checked on a
straight stand-in for the line's last kilometre over a made-up road, and on the committed line and carved tiles."""
import json
import math
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world' / 'regions'))

import yori  # noqa: E402,F401
import shorelines  # noqa: E402
from train import earthworks as E, overbridge as OB, route as R, station_site as S, track as T  # noqa: E402

END = np.array([823.4, 4689.3])
RAIL = 207.6
HEADING = math.radians(140.)
# shorelines._rail_headlands() on the line before the terminus moved (upstream 1e55d54b): the station must not
# move them.
HEADLANDS = ((2629.92, 1648.22, 3056.99, 2308.21), (2442.93, 2861.79, 2507.52, 3121.74),
             (1782.36, 3915.38, 2056.66, 4238.33))


class Straight:
    """The last kilometre of the line, straight and level into the station (track.Line's frame())."""
    length = 7661.

    def frame(self, s):
        t = np.array([math.cos(HEADING), math.sin(HEADING)])
        scalar = np.ndim(s) == 0
        s = np.atleast_1d(np.asarray(s, float))
        xy = END + (s - self.length)[:, None] * t
        p = np.c_[xy, np.full(len(s), RAIL)]
        tt = np.tile([t[0], t[1], 0.], (len(s), 1))
        n = np.tile([-t[1], t[0], 0.], (len(s), 1))
        return (p[0], tt[0], n[0]) if scalar else (p, tt, n)

    @staticmethod
    def earthworks():
        """The same line for the earthworks (earthworks.Line): its last kilometre, in a cutting."""
        t = np.array([math.cos(HEADING), math.sin(HEADING)])
        rows = [{'s': float(s), 'x': float(END[0] + (s - 1000.) * t[0]), 'y': float(END[1] + (s - 1000.) * t[1]),
                 'rail_z': RAIL, 'ground_z': RAIL + 8., 'class': 'cutting'} for s in range(0, 1010, 10)]
        return E.Line({'samples': rows})


def road_ground(x, y):
    """A made-up valley: the road's ground climbs 11 % along its bearing through the deck's level and leans 3 %
    across it."""
    b = math.radians(S.OVERBRIDGE['road_bearing'])
    dx, dy = np.asarray(x) - S.OVERBRIDGE['xy'][0], np.asarray(y) - S.OVERBRIDGE['xy'][1]
    d, w = dx * math.cos(b) + dy * math.sin(b), -dx * math.sin(b) + dy * math.cos(b)
    return S.OVERBRIDGE['deck_z'] + .11 * d + .03 * w


def standin_ground(x, y):
    """The made-up valley carved by the earthworks for the stand-in line."""
    return E.carve(np.asarray(x, float), np.asarray(y, float), road_ground(x, y), STANDIN)


STANDIN = Straight.earthworks()


def by_material(mesh, mat):
    """The distinct vertices of a material's polygons."""
    v = np.asarray(mesh.verts)
    v = v[sorted({i for f, m in zip(mesh.faces, mesh.mats) if m == mat for i in f})]
    return np.unique(np.round(v, 6), axis=0)


def ground_at(ground, q):
    q = np.atleast_2d(q)
    return np.asarray(ground(q[:, 0], q[:, 1]), float)


def under_deck(k, q, margin=0.):
    d, w = k.road_dw(*np.asarray(q, float).T)
    lo, hi = k.ends()
    return (np.abs(w) <= S.DECK_HALF + margin) & (d >= lo - margin) & (d <= hi + margin)


def coherent(test, line, ground, mesh):
    """The structure and the ground read as one: no lip where the road runs onto the deck, the parapets on it, the
    walls' copings flush with the ground behind them all along (ends and return walls included), the cutting clear
    between the walls."""
    k, p, _ = OB.bridge(line)
    lo, hi = k.ends()
    # the road surface (gravel tops) on the deck's plane, and the road's ground just beyond each end at that level
    v = by_material(mesh, 'MI_B_gravel') + p
    tops = v[v[:, 2] > k.plane(k.road_dw(v[:, 0], v[:, 1])[0]) - .01]
    test.assertLess(float(np.abs(tops[:, 2] - k.plane(k.road_dw(tops[:, 0], tops[:, 1])[0])).max()), 1e-3)
    ws = np.linspace(-S.DECK_HALF + OB.PARAPET, S.DECK_HALF - OB.PARAPET, 17)
    for end, out in ((lo, -1.), (hi, 1.)):
        d = end + out * .05
        lips = ground_at(ground, k.road_xy(np.full_like(ws, d), ws)) - k.plane(d)
        test.assertLess(float(np.abs(lips).max()), .02, f'lip at the deck end d={end:.1f}')
    # the parapets' tops stand on the deck, inside its footprint
    stone = by_material(mesh, 'MI_B_stone') + p
    d, w = k.road_dw(stone[:, 0], stone[:, 1])
    parapet = stone[:, 2] - k.plane(d) > 1.
    test.assertEqual(int(parapet.sum()), 8)
    test.assertTrue(np.all(np.abs(w[parapet]) <= S.DECK_HALF + 1e-6))
    test.assertTrue(np.all((d[parapet] >= lo - 1e-6) & (d[parapet] <= hi + 1e-6)))
    for sign in (-1., 1.):
        a0, a1 = k.wall(sign)
        # the mesh's copings are the frame's
        for a in (a0, a1):
            q = k.world(np.array(a), np.array(sign * (k.outer + OB.COPING_LIP)))
            near = np.hypot(stone[:, 0] - q[0], stone[:, 1] - q[1]) < 1e-3
            test.assertTrue(near.any())
            test.assertAlmostEqual(float(stone[near, 2].max()), float(k.coping(sign, a)) + OB.COPING[1], places=3)
        # the retaining wall: the ground just behind its coping, all along, beside the deck excepted
        for a in np.arange(a0 + S.WALL_THICK, a1 - S.WALL_THICK + 1e-9, .25):
            us = np.arange(k.outer + OB.COPING_LIP, k.outer + 1.01, .1)
            q = k.world(np.full_like(us, a), sign * us)
            if under_deck(k, q, 1.).any():
                continue
            gap = float(k.coping(sign, a)) + OB.COPING[1] - ground_at(ground, q).max()
            test.assertGreaterEqual(gap, -.02, f'ground over the coping at a={a:.2f} (side {sign:+.0f})')
            test.assertLess(gap, .15, f'coping over the ground at a={a:.2f} (side {sign:+.0f})')
        # the return walls: the ground behind their copings, and in front of them over their feet, under the copings
        for end, inward in ((a0, 1.), (a1, -1.)):
            reach = E.return_reach(k, sign, end)
            back = end + inward * S.WALL_THICK
            top = float(k.coping(sign, back)) + OB.COPING[1]
            us = np.arange(k.outer + OB.COPING_LIP, reach + 1e-9, .25)
            q = k.world(np.full_like(us, back + inward * OB.COPING_LIP), sign * us)
            gap = top - ground_at(ground, q)[~under_deck(k, q, 1.)]
            test.assertGreaterEqual(float(gap.min()), -.02, f'ground over the return wall at a={end}')
            test.assertLess(float(gap.max()), .15, f'return wall over the ground at a={end}')
            us = np.arange(k.wall_half, reach + 1e-9, .25)
            q = k.world(np.full_like(us, end - inward * .3), sign * us)
            front = ground_at(ground, q)
            foot = k.rail(end) - E.FORMATION_DROP + E._rise(us - k.wall_half, *E.BRIDGE_SLOPES) - .3
            test.assertTrue(np.all(front >= foot), f'the return wall at a={end} stands on air')
            test.assertTrue(np.all(front < float(k.coping(sign, end)) + OB.COPING[1]))
    # the cutting is clear between the walls under the deck: the formation
    a = np.arange(-8., 8.01, 1.)
    for u in (-k.wall_half + .3, 0., k.wall_half - .3):
        q = k.world(a, np.full_like(a, u))
        floor = k.rail(a) - E.FORMATION_DROP
        test.assertLess(float(np.abs(ground_at(ground, q) - floor).max()), .05, f'the cutting at u={u}')


class Overbridge(unittest.TestCase):
    meshes, piece = OB.layout(Straight())

    def test_budgets(self):
        lods = self.meshes['SM_ST_Overbridge']
        for k, (mesh, limit) in enumerate(zip(lods, T.BUDGETS['SM_ST_Overbridge'])):
            self.assertLessEqual(mesh.triangles, limit, f'LOD{k}')
        self.assertGreater(lods[0].triangles, lods[-1].triangles)

    def test_piece_at_the_crossing(self):
        self.assertEqual(self.piece['name'], 'SM_ST_Overbridge')
        self.assertEqual(self.piece['collision'], 'LOD2')
        at = np.asarray(self.piece['origin'][:2])
        self.assertLess(np.hypot(*(at - S.OVERBRIDGE['xy'])), 5.)
        self.assertAlmostEqual(self.piece['chainage'], Straight.length - 229., delta=3.)

    def test_frames_agree(self):
        """The mesh's frame (track.Line) and the earthworks' (earthworks.Line) are one."""
        k, _, _ = OB.bridge(Straight())
        e = STANDIN.bridge()
        self.assertLess(float(np.hypot(*(k.origin - e.origin))), .01)
        self.assertAlmostEqual(float(k.coping(1., 0.)), float(e.coping(1., 0.)), places=2)

    def test_structure_and_ground_agree(self):
        for lod, mesh in enumerate(self.meshes['SM_ST_Overbridge']):     # LOD2 is the collision
            with self.subTest(lod=lod):
                coherent(self, Straight(), standin_ground, mesh)

    def test_copings_are_straight_and_parallel_to_the_deck(self):
        k, _, _ = OB.bridge(Straight())
        for sign in (-1., 1.):
            a0, a1 = k.wall(sign)
            z = k.coping(sign, np.linspace(a0, a1, 9))
            self.assertLess(float(np.abs(np.diff(z, 2)).max()), 1e-9)
            slope = (z[-1] - z[0]) / (a1 - a0)
            self.assertAlmostEqual(slope, S.OVERBRIDGE['grade'] * float(k.t @ k.road), places=6)

    def test_other_lines_get_none(self):
        class Elsewhere(Straight):
            def frame(self, s):
                p, t, n = Straight.frame(self, s)
                return p - np.array([2000., 0., 0.]), t, n
        self.assertEqual(OB.layout(Elsewhere()), ({}, None))


class CommittedOverbridge(unittest.TestCase):
    """On the committed line and the committed (carved) valley tiles."""

    @classmethod
    def setUpClass(cls):
        from train import corridor as C
        cls.line = T.Line(dict(json.loads(C.LINE.read_text()), summary={'structures': []}))
        cls.meshes, _ = OB.layout(cls.line)

    def test_structure_and_ground_agree(self):
        self.assertTrue(self.meshes)
        for lod, mesh in enumerate(self.meshes['SM_ST_Overbridge']):
            with self.subTest(lod=lod):
                coherent(self, self.line, OB.valley_ground, mesh)

    def test_road_ramps_to_the_deck_at_most_12_5_percent(self):
        k, _, _ = OB.bridge(self.line)
        lo, hi = k.ends()
        reach = hi - k.dc + S.ROAD_FLAT + S.ROAD_RAMP - 2.     # the graded road (its own ground beyond)
        d = np.arange(k.dc - reach, k.dc + reach + 1e-9, 1.)
        for w in (-2., 0., 2.):
            z = ground_at(OB.valley_ground, k.road_xy(d, np.full_like(d, w)))
            on = (d >= lo) & (d <= hi)
            z[on] = k.plane(d[on])
            grade = np.abs(z[2:] - z[:-2]) / 2.            # over 2 m: a wheelbase, not a triangle's crease
            self.assertLessEqual(float(grade.max()), .125, f'w={w}')


class Alignment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.line = R.alignment()

    def test_fixed_radius_is_a_plain_curve(self):
        radii = R.fixed_radii()
        self.assertEqual(len(radii), 1)
        self.assertNotIn(next(iter(radii)), R.spiral_loops())
        (i, radius), = radii.items()
        self.assertAlmostEqual(self.line.curves[i - 1][1], radius)
        self.assertEqual(len(self.line.spirals), 1)         # still the one spiral tunnel

    def test_ends_at_the_station(self):
        self.assertLess(self.line.closure, .01)
        end = np.array([self.line.x[-1], self.line.y[-1]])
        self.assertIsNotNone(S.for_line(np.array([[self.line.x[-2], self.line.y[-2]], end]), [RAIL, RAIL]))

    def test_shoreline_headlands_unchanged(self):
        import tempfile
        rows = [dict(x=float(x), y=float(y)) for x, y in zip(self.line.x, self.line.y)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'line.json'
            path.write_text(json.dumps({'samples': rows}))
            saved = shorelines.RAIL_LINE
            try:
                shorelines.RAIL_LINE = path
                shorelines._rail_headlands.cache_clear()
                boxes = shorelines._rail_headlands()
            finally:
                shorelines.RAIL_LINE = saved
                shorelines._rail_headlands.cache_clear()
        np.testing.assert_allclose(boxes, HEADLANDS, atol=.02)


if __name__ == '__main__':
    unittest.main()
