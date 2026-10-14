"""Crater Park's added pieces and its tunnel kept open (world/regions/craterpark/additions.py, tunnel.py)."""
from pathlib import Path
import math
import sys
import unittest

import numpy as np

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME / 'world' / 'regions'))
from craterpark import additions, grind, tunnel  # noqa: E402


def quad(a, b, c, d):
    return [[a, c, b], [a, d, c]]


def floor(x0, z0, x1, z1, y=0.):
    return quad((x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1))


def box(x0, y0, z0, x1, y1, z1):
    """A closed box's six faces."""
    c = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    return (quad(c[0], c[4], c[6], c[2]) + quad(c[1], c[3], c[7], c[5]) + quad(c[0], c[1], c[5], c[4])
            + quad(c[2], c[6], c[7], c[3]) + quad(c[0], c[2], c[3], c[1]) + quad(c[4], c[5], c[7], c[6]))


def tube(radius, length, sides=24):
    """A round tunnel along x, from 0 to `length`, its axis at height `radius`."""
    t = []
    for k in range(sides):
        a0, a1 = 2 * math.pi * k / sides, 2 * math.pi * (k + 1) / sides
        p = lambda x, a: (x, radius - radius * math.cos(a), radius * math.sin(a))
        t += quad(p(0, a0), p(length, a0), p(length, a1), p(0, a1))
    return np.asarray(t, 'f8')


class TunnelTests(unittest.TestCase):
    def test_the_solid_in_a_tunnel_is_found_and_the_block_round_it_kept(self):
        bore = tube(3., 20.)
        inside = np.asarray(box(2, .5, -1, 18, 4, 1), 'f8')              # solid filling the bore
        outside = np.asarray(box(2, 7, -1, 18, 9, 1) + box(-10, 0, -10, -5, 5, 10), 'f8')  # over the roof, beside it
        mask = tunnel.inside_tubes(np.concatenate([inside, outside]), [bore])
        self.assertTrue(mask[:len(inside)].all())
        self.assertFalse(mask[len(inside):].any())

    def test_a_long_face_crossing_the_bore_is_found(self):
        bore = tube(3., 20.)
        sliver = np.asarray([[(10, -8, -.2), (10, 5, -.2), (10.3, -8, .2)]], 'f8')    # its centre under the floor
        self.assertTrue(tunnel.inside_tubes(sliver, [bore])[0])

    def test_under_a_deck_is_no_tunnel(self):
        deck = np.asarray(floor(-5, -5, 5, 5, 4.) + floor(-5, -5, 5, 5, 0.), 'f8')    # open on every side
        block = np.asarray(box(-1, 1, -1, 1, 3, 1), 'f8')
        self.assertFalse(tunnel.inside_tubes(block, [deck]).any())


class SnakeTests(unittest.TestCase):
    def setUp(self):
        # Two floor slabs at 0 m with a 5 m slot between them along z; the hillside 20 m down.
        self.riding = np.asarray(floor(0, 0, 30, 10) + floor(0, 15, 30, 25) + floor(0, 10, 3, 15) + floor(27, 10, 30, 15), 'f8')
        self.solid = np.asarray(floor(-10, -10, 40, 35, -20.), 'f8')

    def test_a_slot_holds_a_channel_meeting_the_floor_level(self):
        v, f, uv = additions.snake_channels(self.riding, self.solid, (-2, -2, 32, 27), 0.)
        self.assertEqual(len(uv), len(v))
        mid = (v[:, 2] > 12.4) & (v[:, 2] < 12.6) & (v[:, 0] > 8) & (v[:, 0] < 22)
        self.assertAlmostEqual(float(v[mid, 1].min()), -min(additions.CHANNEL, additions.STEEPEST * 2.5), delta=.05)
        edge = (np.abs(v[:, 2] - 10) < .01) | (np.abs(v[:, 2] - 15) < .01)
        self.assertLess(float(np.abs(v[edge, 1]).max()), .02)       # flush with the floor at both edges
        n = grind.unit_normals(v[f].astype('f8'))
        self.assertTrue((n[:, 1] > 0).all())                         # faces up
        self.assertLess(float(v[:, 1].max()), .001)                  # nothing rises over the floor

    def test_a_bridge_over_the_slot_stays_and_the_channel_rises_to_it(self):
        bridge = np.asarray(box(14.5, -.3, 9.5, 15.5, 0, 15.5), 'f8')
        v, f, uv = additions.snake_channels(self.riding, np.concatenate([self.solid, bridge]), (-2, -2, 32, 27), 0.)
        under = (np.abs(v[:, 0] - 15) < .2) & (v[:, 2] > 11) & (v[:, 2] < 14)
        self.assertLess(float(np.abs(v[under, 1]).max()), .02)      # flush with the bridge's top
        far = (np.abs(v[:, 0] - 6) < .2) & (np.abs(v[:, 2] - 12.5) < .2)
        self.assertLess(float(v[far, 1].min()), -1.)                # deep again away from it


class SolidifyTests(unittest.TestCase):
    def test_a_wall_ending_in_the_air_gets_a_cap_and_a_back_wall(self):
        # A curved sheet (a quarter pipe 2 m high along z) standing on the ground, open behind.
        t = []
        for k in range(8):
            a0, a1 = math.pi / 2 * k / 8, math.pi / 2 * (k + 1) / 8
            p = lambda z, a: (2 * math.sin(a), 2 - 2 * math.cos(a), z)      # rises from x 0 to the vertical at x 2
            t += quad(p(0, a0), p(6, a0), p(6, a1), p(0, a1))
        piece = np.asarray(t, 'f8')
        ground = np.asarray(floor(-5, -5, 10, 10, 0.), 'f8')
        heights = grind.heights(np.concatenate([piece, ground]))
        v, f, uv = additions.solidify(piece, heights, np.concatenate([piece, ground]))
        n = grind.unit_normals(v[f].astype('f8'))
        caps = f[n[:, 1] > .9]
        self.assertTrue(len(caps))
        top = v[caps].reshape(-1, 3)
        self.assertTrue(np.allclose(top[:, 1], 2., atol=1e-6))       # level with the coping
        self.assertGreater(float(top[:, 0].max()), 2 + additions.THICK - 1e-6)   # behind the wall, away from the ramp
        self.assertLess(float(v[:, 1].min()), 0.)                    # the back wall goes down into the ground



class CopingTests(unittest.TestCase):
    def test_a_tube_runs_along_the_line_its_top_just_over_the_deck_facing_out(self):
        line = np.stack([np.linspace(0, 5, 11), np.full(11, 1.), np.zeros(11)], 1)
        v, f, uv = additions.coping([line])
        self.assertAlmostEqual(float(v[:, 1].max()), 1 + additions.COPING_PROUD, delta=.002)
        self.assertAlmostEqual(float(v[:, 0].max()), 5., places=4)
        t = v[f].astype('f8'); n = grind.unit_normals(t)
        axis = np.stack([t.mean(1)[:, 0], np.full(len(t), 1 + additions.COPING_PROUD - additions.COPING_RADIUS), np.zeros(len(t))], 1)
        self.assertTrue(((n * (t.mean(1) - axis)).sum(1) > 0).all())


if __name__ == '__main__':
    unittest.main()
