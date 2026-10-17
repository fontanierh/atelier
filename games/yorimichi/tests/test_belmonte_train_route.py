"""The Belmonte train's alignment study (world/train/route.py): curves, spiral, stations, volcano clearance, grades and
loop."""
import math
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world'))
import yori  # noqa: E402,F401
from yori import OUT  # noqa: E402
from train import route as R  # noqa: E402

BUILT = all((OUT / name).exists() for name in ('hidamari/city.json', 'belmonte/runtime.json', 'farhills.npy',
                                               'belmonte/natural/SM_BM_NorthCountry.glb', 'belmonte/natural/SM_BM_NorthApron.glb'))


class Alignment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.line = R.alignment(step=1.)

    def test_curves_fit(self):
        self.assertIsNotNone(self.line)
        self.assertLess(self.line.closure, .01)
        spiral = self.line.spiral_mask()
        self.assertGreaterEqual(1 / np.abs(self.line.curvature[~spiral]).max(), R.MIN_RADIUS - 1e-6)
        loops = R.spiral_loops()
        for i, (deflection, radius, spiral_length, _) in enumerate(self.line.curves):
            self.assertGreater(spiral_length, 0)
            if i + 1 in loops:
                self.assertTrue(250. <= radius <= 350.)
            else:
                self.assertGreaterEqual(radius, R.MIN_RADIUS)
                self.assertLessEqual(abs(math.degrees(deflection)), R.MAX_BEND)   # no horseshoe in the open

    def test_one_spiral_of_one_turn(self):
        self.assertEqual(len(self.line.spirals), 1)
        self.assertEqual(abs(self.line.spirals[0]['turns']), 1)

    def test_volcano_clearance(self):
        self.assertGreaterEqual(R.volcano_distance(self.line.x, self.line.y).min(), R.VOLCANO_CLEARANCE)

    def test_posted_limits(self):
        self.assertAlmostEqual(R.MAX_SPEED * 3.6, 100.)
        for radius, kmh in ((250., 50), (300., 50), (450., 70), (620., 80), (760., 90), (2000., 100)):
            self.assertAlmostEqual(R.curve_limit(radius) * 3.6, kmh)
        for start, end, v, radius in R.posted_limits(self.line):
            self.assertLess(start, end)
            self.assertAlmostEqual(v, R.curve_limit(radius))
            self.assertAlmostEqual(round(v * 3.6) % 10, 0)

    def test_traction(self):
        self.assertAlmostEqual(R.MASS, 290e3)
        self.assertTrue(45 / 3.6 < R.balancing_speed(.035) < 55 / 3.6)
        self.assertAlmostEqual(R.balancing_speed(0.), R.MAX_SPEED)

    def test_curves_are_taken_at_their_limit(self):
        line = self.line
        for direction in (1, -1):
            c, t, v = R.run(line, None, direction)
            for start, end, limit, _ in R.posted_limits(line):
                lo, hi = (start, end + R.TRAIN_LENGTH) if direction > 0 else (start - R.TRAIN_LENGTH, end)
                on = (c >= lo) & (c <= hi)
                if on.any():
                    self.assertLessEqual(v[on].max(), limit + 1e-6)
            self.assertLessEqual(np.abs(np.diff(v ** 2) / 2 / np.diff(np.abs(c))).max(), max(R.ACCELERATION, R.BRAKING) + 1e-6)

    def test_endpoints_on_station_axes(self):
        line = self.line
        for station, index in ((R.HIDAMARI, line.s <= R.HIDAMARI.reserve[0]),
                               (R.BELMONTE, line.s >= line.length - R.BELMONTE.reserve[0])):
            pts = np.c_[line.x[index], line.y[index]] - station.centre
            across = pts @ np.array([-station.axis[1], station.axis[0]])
            self.assertLess(np.abs(across).max(), .01, station.name)
            self.assertTrue(np.allclose(line.curvature[index], 0.), station.name)
            heading = np.degrees(line.heading[index]) % 360
            self.assertTrue(np.allclose(heading, station.bearing % 360, atol=1e-3), station.name)
        self.assertAlmostEqual(float(np.hypot(line.x[0] - R.HIDAMARI.centre[0], line.y[0] - R.HIDAMARI.centre[1])),
                               R.HIDAMARI.reserve[0] / 2, 2)

    def test_hidamari_uses_the_town_platform(self):
        from hidamari import station_yard as S
        self.assertEqual(R.HIDAMARI.bearing, 0.)
        self.assertAlmostEqual(self.line.y[0], 299.95 + 1.85)
        self.assertAlmostEqual(self.line.x[0], S.X0)
        self.assertGreater(self.line.x[0] - 2.45, 1120 + 5.5)  # buffer/ballast clear the west lane


@unittest.skipUnless(BUILT, 'needs world.hidamari and world.belmonte')
class Profile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = R.study()

    def test_committed_line_matches_study(self):
        import json
        from train import corridor as C
        line, rail, zg, kind = self.r['line'], self.r['rail'], self.r['zg'], self.r['kind']
        side = 1. if self.r['loop'] and float(np.interp(sum(self.r['loop']) / 2, line.s, line.curvature)) <= 0 else -1.
        lt = R.loop_track(line, self.r['loop'], side)
        if R.volcano_distance(lt[:, 1], lt[:, 2]).min() < R.volcano_distance(*line.at(lt[:, 0])[:2]).min():
            lt = R.loop_track(line, self.r['loop'], -side)
        route_doc = {
            'frame': 'Blender metres, x east, y north, z up; bearings counter-clockwise from east',
            'samples': [{'s': round(float(s), 2), 'x': round(float(x), 2), 'y': round(float(y), 2),
                         'rail_z': round(float(z), 3), 'ground_z': round(float(g), 3), 'class': str(k)}
                        for s, x, y, z, g, k in zip(line.s, line.x, line.y, rail, zg, kind)],
            'passing_loop': {'start': self.r['loop'][0], 'end': self.r['loop'][1],
                             'second_track': [[round(float(a), 1), round(float(b), 2), round(float(c), 2)] for a, b, c in lt]},
        }
        committed = json.loads(C.LINE.read_text())
        self.assertEqual(C.line_data(route_doc), committed, 'update games/yorimichi/assets/vehicles/belmonte-train/line.json')

    def test_grades_and_vertical_curves(self):
        line, rail = self.r['line'], self.r['rail']
        grade = np.diff(rail) / np.diff(line.s)
        self.assertLessEqual(np.abs(grade).max(), R.DESIGN_GRADE + 1e-6)
        self.assertGreaterEqual(R.STEP / max(np.abs(np.diff(grade)).max(), 1e-9), R.VERTICAL_RADIUS - 1.)
        self.assertEqual(self.r['loop'], R.LOOP)                            # the approved loop stays put

    def test_earthworks_follow_the_ground(self):
        h = self.r['rail'] - self.r['zg']
        open_ = ~np.isin(self.r['kind'], ('tunnel', 'viaduct'))
        self.assertGreater(h[open_].min(), -(R.TUNNEL_COVER + R.TUNNEL_BORE) - .5)    # no cutting deeper than a portal
        self.assertLess(h[open_].max(), R.EMBANKMENT_HEIGHT + .5)

    def test_level_platforms(self):
        line, rail, zg = self.r['line'], self.r['rail'], self.r['zg']
        for on in (line.s <= R.HIDAMARI.reserve[0], line.s >= line.length - R.BELMONTE.reserve[0]):
            self.assertLess(np.ptp(rail[on]), 1e-6)
            self.assertLessEqual(np.abs(rail[on] - zg[on]).max(), R.PLATFORM_OFFSET + .5)
        from hidamari import station_yard as S
        self.assertAlmostEqual(rail[0], S.floor_z() + S.RAIL, places=6)

    def test_spiral_is_a_climbing_tunnel(self):
        line, rail, kind = self.r['line'], self.r['rail'], self.r['kind']
        spiral = line.spiral_mask()
        self.assertTrue((kind[spiral] == 'tunnel').all())
        self.assertGreater(rail[spiral][-1] - rail[spiral][0], 60.)

    def test_other_tunnels_within_budget(self):
        line, kind = self.r['line'], self.r['kind']
        other = ((kind == 'tunnel') & ~line.spiral_mask()).sum() * R.STEP
        self.assertLessEqual(other, R.TUNNEL_BUDGET * 1.1)

    def test_passing_loop(self):
        line, rail, kind, loop = self.r['line'], self.r['rail'], self.r['kind'], self.r['loop']
        self.assertIsNotNone(loop)
        self.assertGreaterEqual(loop[1] - loop[0], R.LOOP_TOTAL - 1e-6)
        on = (line.s >= loop[0]) & (line.s <= loop[1])
        self.assertLessEqual(np.abs(np.diff(rail[on]) / np.diff(line.s[on])).max(), R.LOOP_GRADE + 1e-6)
        self.assertTrue(set(kind[on]) <= {'cutting', 'deep cutting', 'embankment'}, set(kind[on]))
        self.assertLessEqual(np.abs(line.curvature[on]).max(), 1 / R.LOOP_RADIUS + 1e-9)
        for side in (1., -1.):
            track = R.loop_track(line, loop, side)
            self.assertGreaterEqual(R.volcano_distance(track[:, 1], track[:, 2]).min(), R.VOLCANO_CLEARANCE)

    def test_timetable(self):
        for name in ('run', 'run_down'):
            c, t, v = self.r[name]
            self.assertLessEqual(v.max(), R.MAX_SPEED + 1e-6)
            self.assertEqual(v[0], 0.)
            self.assertEqual(v[-1], 0.)
            self.assertLess(t[-1], 600.)
        self.assertGreater(self.r['one_way'], self.r['one_way_down'])       # uphill to Belmonte is the slow way
        self.assertFalse(math.isnan(self.r['loop_time']))
        service = self.r['service']
        self.assertEqual(service['dwell_s'], R.DWELL)
        self.assertAlmostEqual(service['cycle_s'], service['run_up_s'] + service['run_down_s'] + 2 * R.DWELL, delta=.2)
        a, b = service['schedule']
        for train in (a, b):        # exactly DWELL at each terminus, the loop inside each leg
            first, second = train['legs']
            self.assertAlmostEqual(second['depart_s'] - first['arrive_s'], R.DWELL, delta=.2)
            for leg in train['legs']:
                self.assertLessEqual(leg['depart_s'], leg['loop_arrive_s'])
                self.assertLessEqual(leg['loop_arrive_s'], leg['loop_leave_s'])
                self.assertLessEqual(leg['loop_leave_s'], leg['arrive_s'])
        # the two trains are on the loop together and the waiting one leaves after the other has passed
        up, down = a['legs'][0], b['legs'][0]
        self.assertLess(max(up['loop_arrive_s'], down['loop_arrive_s']), min(up['loop_leave_s'], down['loop_leave_s']))
        self.assertAlmostEqual(b['legs'][1]['depart_s'] - a['legs'][0]['depart_s'], service['headway_s'], delta=.2)


if __name__ == '__main__':
    unittest.main()
