"""Getting to the Mega Park: the trail from the woodland air station, and the zeppelin's third stop by the top road."""
from pathlib import Path
import json
import math
import sys
import unittest

import numpy as np

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'world' / 'regions'), str(Path(__file__).resolve().parents[1] / 'world')]
import yori  # noqa: E402
from megapark import forest, placement, trail  # noqa: E402
from zeppelin import layout as zeppelin  # noqa: E402

OUT = yori.OUT
BUILT = all((OUT / name).exists() for name in ('megapark/trail.json', 'farhills.npy', 'heightmap.npy'))
CITY = OUT / 'hidamari' / 'city.json'


def surface(triangles, p, near=None):
    """Heights of the triangles over the point p (x, y), within 0.5 m of `near` if given."""
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    den = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
    den[den == 0] = np.inf
    u = ((b[:, 1] - c[:, 1]) * (p[0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (p[1] - c[:, 1])) / den
    v = ((c[:, 1] - a[:, 1]) * (p[0] - c[:, 0]) + (a[:, 0] - c[:, 0]) * (p[1] - c[:, 1])) / den
    hit = np.isfinite(den) & (u >= 0) & (v >= 0) & (u + v <= 1)
    z = (u * a[:, 2] + v * b[:, 2] + (1 - u - v) * c[:, 2])[hit]
    return z if near is None else z[abs(z - near) < .5]


def city_instances():
    try:
        return json.loads(CITY.read_text())['instances']
    except (OSError, ValueError, KeyError):
        return {}


def ground(x, y):
    """The island's ground: the square heightmap, else the north terrain and far hills (hidamari.layout)."""
    from hidamari.layout import north_height
    from village.layout import sample
    x, y = np.asarray(x, 'f8'), np.asarray(y, 'f8')
    z = north_height(x, y)
    h = np.load(OUT / 'heightmap.npy')
    for i in np.flatnonzero((abs(x) <= 300) & (abs(y) <= 300)):      # the square's heightmap reaches its edges
        z[i] = float(sample(h, x[i], y[i]))
    return z


class TrailTests(unittest.TestCase):
    def test_runs_from_the_woodland_station_to_the_foot_of_the_steps_onto_the_deck(self):
        xy, s = trail.path()
        ox, oy, _ = zeppelin.STATIONS[0]['origin']
        self.assertLess(math.dist(xy[0], (ox, oy)), 30)
        self.assertGreater(s[-1], 1100)
        run = trail.STEPS * trail.TREAD
        np.testing.assert_allclose(xy[-1], np.array(trail.DECK[:2]) - run * np.array(trail.INTO), atol=.01)
        self.assertLess(float(forest.distance(*xy[-1])), run + .5)

    def test_steps_land_flush_on_the_deck_edge(self):
        # Just across the edge is deck at DECK's height; just short of it, none (the treads fill it).
        t = placement.place(placement.collision_triangles())
        across = np.array([-trail.INTO[1], trail.INTO[0]])
        for o in (-trail.HALF, 0., trail.HALF):
            edge = np.array(trail.DECK[:2]) + o * across
            on = surface(t, edge + .1 * np.array(trail.INTO))
            self.assertTrue(len(on) and abs(on - trail.DECK[2]).min() < .02, o)
            self.assertFalse(len(surface(t, edge - .15 * np.array(trail.INTO), trail.DECK[2])), o)

    @unittest.skipUnless(BUILT, 'needs world.layout')
    def test_bed_keeps_walking_grades_and_meets_the_ground_at_both_ends(self):
        bed = trail.bed()
        s = np.r_[0, np.cumsum(np.hypot(*np.diff(bed[:, :2], axis=0).T))]
        z = np.interp(np.arange(0, s[-1], 1.), s, bed[:, 2])
        self.assertLess(float(abs(z[10:] - z[:-10]).max()) / 10, .26)
        start, end = bed[[0, -1]]
        self.assertAlmostEqual(float(ground([start[0]], [start[1]])[0]), start[2], delta=.1)
        self.assertAlmostEqual(float(ground([end[0]], [end[1]])[0]), end[2], delta=.5)

    @unittest.skipUnless(BUILT, 'needs world.layout')
    def test_ground_follows_the_bed(self):
        bed = trail.bed()
        g = ground(bed[:, 0], bed[:, 1])
        self.assertLess(float(abs(g - bed[:, 2]).max()), .5)

    @unittest.skipUnless(BUILT, 'needs world.layout')
    def test_approach_meets_the_north_terrain(self):
        from hidamari import layout, mountains
        x0, _, x1, y1 = trail.APPROACH
        x = np.arange(x0 + 2, x1 - 2, 2.)
        north = mountains.height(x, np.full_like(x, y1), layout.north_base_height)
        np.testing.assert_allclose(trail.approach_height(x, np.full_like(x, y1 - 1e-6)), north, atol=.02)


class MegaParkStopTests(unittest.TestCase):
    station = zeppelin.STATIONS[2]

    def local(self, x, y):
        ox, oy, _ = self.station['origin']
        X, Y = np.meshgrid(np.arange(*x, .5), np.arange(*y, .5))
        return ox + X, oy + Y

    def test_station_and_the_ships_turn_are_clear_of_the_park(self):
        # The ship turns about its centre (SHIP) as it lifts off: a 13.5 m circle round it, and the station's apron.
        self.assertFalse(placement.contains(*self.local((-11, 20), (-10, 18)), margin=1.).any())

    def test_pad_never_touches_the_park(self):
        x, y = self.local((-40, 45), (-30, 30))
        on = placement.contains(x, y)
        z = np.full(x.shape, 50.)
        np.testing.assert_array_equal(zeppelin.megapark_pad(x, y, z)[on], 50.)

    @unittest.skipUnless(BUILT, 'needs world.layout')
    def test_ground_is_level_under_the_station_and_ship(self):
        from hidamari.layout import north_height
        oz = self.station['origin'][2]
        z = north_height(*self.local((-10.5, 11.5), (-9, 12.5)))
        self.assertLessEqual(float(z.max()), oz + .001)     # never above the apron slabs (their top is at +0.03)
        self.assertGreater(float(z.min()), oz - .35)

    @unittest.skipUnless(BUILT, 'needs world.layout')
    def test_footpath_is_level_and_the_footbridge_lands_on_the_road_deck(self):
        from hidamari.layout import north_height
        oz = self.station['origin'][2]
        (x0, y), (x1, _) = zeppelin.PARK_WALK
        x = np.arange(x0, x1 + .01, .5)
        np.testing.assert_allclose(north_height(x, np.full_like(x, y)), oz, atol=.01)
        # The bridge's end rests on the deck across its whole width, its planks (at +0.03) within a step of it: the
        # deck rises 14 cm across the bridge.
        (_, _), (end, _) = zeppelin.PARK_BRIDGE
        t = placement.place(placement.collision_triangles())
        for dy in (-1.1, 0., 1.1):
            deck = surface(t, np.array([end - .15, y + dy]), oz)
            self.assertTrue(len(deck), dy)
            np.testing.assert_allclose(deck, oz + .03, atol=.13)

    @unittest.skipUnless('ZP_MegaPark' in city_instances(), 'needs world.hidamari')
    def test_trees_are_cleared_over_the_station_and_its_footpath(self):
        ox, oy, _ = self.station['origin']
        path = np.array([[*p, 0.] for p in (*zeppelin.PARK_WALK, zeppelin.PARK_BRIDGE[1])])
        from village.layout import nearest
        for name, rows in city_instances().items():
            if 'Tree' not in name or not rows:
                continue
            a = np.asarray(rows, 'f8')
            self.assertFalse(((abs(a[:, 0] - ox - 3) < 25) & (abs(a[:, 1] - oy) < 23)).any(), name)
            self.assertGreaterEqual(float(nearest(a[:, 0], a[:, 1], path)[0].min()), 7.5, name)


class LegTests(unittest.TestCase):
    def test_every_pair_of_stops_is_a_leg_at_the_first_legs_speed(self):
        meta = zeppelin.metadata()
        n = len(meta['stations'])
        self.assertEqual(sorted(tuple(sorted(leg['stops'])) for leg in meta['legs']),
                         [(a, b) for a in range(n) for b in range(a + 1, n)])
        first = next(leg for leg in meta['legs'] if sorted(leg['stops']) == [0, 1])
        self.assertEqual(first['seconds'], 28.)
        self.assertEqual(first['height'], 155.)

    @unittest.skipUnless(BUILT, 'needs world.layout')
    def test_cruise_clears_the_ground_and_trees(self):
        # Beyond 100 m of either stop, 50 m over the highest ground in a 40 m corridor: about 15 m of trees, the ship
        # and the trailing camera above it.
        meta = zeppelin.metadata()
        for leg in meta['legs']:
            a, b = (np.array(meta['stations'][i]['ship'][:2]) for i in leg['stops'])
            length = float(np.linalg.norm(b - a))
            t = np.arange(100, length - 100, 4.) / length
            side = np.array([a[1] - b[1], b[0] - a[0]]) / length
            for offset in (-20, 0, 20):
                p = a + np.outer(t, b - a) + offset * side
                self.assertLess(float(ground(p[:, 0], p[:, 1]).max()) + 50, leg['height'], leg['stops'])


if __name__ == '__main__':
    unittest.main()
