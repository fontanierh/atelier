"""The Belmonte station's site (world/train/station_site.py) and what it asks of the ground and the planting, on a
straight stand-in for the line's last kilometre ending at the site, and on the committed line, which ends there with
Belmonte's valley tiles carved for it. A line that ends elsewhere (made-up lines, the former riverside terminus) gets
nothing: its earthworks, corridor and route ground stay as they were."""
import json
import math
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world' / 'regions'))

import yori  # noqa: E402,F401
from train import corridor as C, earthworks as E, station_site as S  # noqa: E402

END = np.array([823.4, 4689.3])
RAIL = 207.6
HEADING = math.radians(140.)


def rows(end=END):
    t = np.array([math.cos(HEADING), math.sin(HEADING)])
    return [{'s': float(s), 'x': float(end[0] + (s - 1000.) * t[0]), 'y': float(end[1] + (s - 1000.) * t[1]),
             'rail_z': RAIL, 'ground_z': RAIL + 4., 'class': 'cutting'} for s in range(0, 1010, 10)]


def committed_route():
    return json.loads(C.LINE.read_text())


class Site(unittest.TestCase):
    def test_only_a_line_ending_at_the_site_gets_a_station(self):
        self.assertIsNotNone(E.Line({'samples': rows()}).station())
        self.assertIsNone(E.Line({'samples': rows(END + [2000., 0.])}).station())
        self.assertIsNone(S.for_line([END], [RAIL]))
        self.assertIsNone(S.for_line([END, END], [RAIL, RAIL]))
        self.assertIsNone(S.for_line([END - [10., 0.], END], [RAIL, float('nan')]))

    def test_the_committed_line_ends_at_the_station(self):
        ln = E.Line(committed_route())
        self.assertIsNotNone(ln.station())
        self.assertAlmostEqual(ln.overbridge(), ln.length - 229., delta=10.)
        self.assertIsNotNone(C.Corridor(committed_route()).site)

    def test_frame(self):
        site = E.Line({'samples': rows()}).station()
        self.assertTrue(np.allclose(site.origin, END))
        a, u = site.local(*site.world(np.array([-30.]), np.array([5.]))[0])
        self.assertAlmostEqual(float(a), -30.)
        self.assertAlmostEqual(float(u), 5.)
        self.assertTrue(S.inside(site, *site.world(np.array([-100.]), np.array([0.]))[0]))
        self.assertFalse(S.inside(site, *site.world(np.array([-100.]), np.array([40.]))[0]))

    def test_sheds_take_the_scaled_train(self):
        self.assertGreaterEqual(-S.SHEDS[0], S.TRAIN_LENGTH + 10.)
        self.assertGreaterEqual(S.EDGE, 1.80 * S.TRAIN_SCALE)


class Ground(unittest.TestCase):
    ln = E.Line({'samples': rows()})

    def carve(self, a, u, z):
        x, y = self.ln.station().world(np.array([a]), np.array([u]))[0]
        return float(E.carve(np.array([x]), np.array([y]), np.array([z]), self.ln)[0])

    def test_sheds_and_headhouse_at_the_formation(self):
        for a, u in ((-100., -30.), (-20., 8.), (10., -50.)):
            self.assertAlmostEqual(self.carve(a, u, RAIL + 5.), RAIL + S.FORMATION, delta=.05)

    def test_forecourt_at_street_level(self):
        self.assertAlmostEqual(self.carve(36., S.AXIS_U, RAIL + 9.), RAIL + S.STREET, delta=.05)    # cut
        self.assertAlmostEqual(self.carve(36., S.AXIS_U, RAIL + 5.), RAIL + S.STREET, delta=.05)    # fill

    def test_street_front_flush(self):
        """Along the whole facade the ground meets the street: under the vestibule just under the floor, outside at
        street level, whatever the ground was (no trench where the stair hall's formation meets the street)."""
        street = RAIL + S.STREET
        for u in np.linspace(S.HEADHOUSE[2], S.HEADHOUSE[3], 25):
            for a in (S.VESTIBULE[0] + 1., S.HEADHOUSE[1] - .5, S.HEADHOUSE[1], S.HEADHOUSE[1] + .1, S.HEADHOUSE[1] + 1.,
                      S.HEADHOUSE[1] + 3.):
                for z in (RAIL + 4., RAIL + 11.):
                    self.assertAlmostEqual(self.carve(a, u, z), street, delta=.02 + 1e-9, msg=f'a={a} u={u:.1f}')

    def test_access_road_climbs_to_its_junction(self):
        site = self.ln.station()
        pts, (z0, z1) = site.access()
        self.assertAlmostEqual(z0, RAIL + S.STREET)
        self.assertAlmostEqual(z1, S.ACCESS_END_Z)
        length = float(np.hypot(*(pts[-1] - pts[0])))
        self.assertAlmostEqual(float(site.access_z(S.ACCESS_FLAT / length)), z0)    # level off the forecourt first
        for t in (.25, .5, .9):
            x, y = pts[0] + t * (pts[-1] - pts[0])
            for z in (z0 - 3., z1 + 3.):        # fill and cut
                carved = float(E.carve(np.array([x]), np.array([y]), np.array([z]), self.ln)[0])
                self.assertAlmostEqual(carved, z0 + (t * length - S.ACCESS_FLAT) / (length - S.ACCESS_FLAT) *
                                       (z1 - z0), delta=.05)
        self.assertLess((z1 - z0) / (length - S.ACCESS_FLAT), .03)      # about 2 %

    def test_ground_stands_against_the_walls(self):
        # two metres and a half outside the sheds' wall the ground keeps its natural height
        self.assertAlmostEqual(self.carve(-80., S.SHEDS[3] + 2.5, RAIL + 4.), RAIL + 4., delta=.05)

    def test_the_road_runs_on_the_deck_plane_beyond_the_walls(self):
        k = self.ln.bridge()
        self.assertIsNotNone(k)
        for u in (-13., 13.):   # past the deck's ends, on the road's line: whatever the ground, the deck's plane
            d = float((u - (k.road_xy(0., 0.) - k.origin) @ k.n) / k.rn)
            x, y = k.road_xy(d, 0.)
            for z in (RAIL + 6., RAIL + 12.):
                carved = float(E.carve(np.array([x]), np.array([y]), np.array([z]), self.ln)[0])
                self.assertAlmostEqual(carved, float(k.plane(d)), delta=.01)

    def test_far_ground_untouched(self):
        self.assertEqual(self.carve(-100., 120., RAIL + 4.), RAIL + 4.)


class Planting(unittest.TestCase):
    route = {'samples': rows()}

    def test_no_plants_on_the_station(self):
        c = C.Corridor(self.route)
        site = c.site
        on = site.world(np.array([-60., 36., -60.]), np.array([-30., S.AXIS_U, 60.]))
        margin = c.station_margin(on[:, 0], on[:, 1])
        self.assertLess(margin[0], 0.)
        self.assertLess(margin[1], 0.)
        self.assertGreater(margin[2], 0.)
        pts, _ = site.access()
        mid = (pts[0] + pts[-1]) / 2
        self.assertLess(float(c.station_margin(mid[:1], mid[1:])[0]), 0.)                 # the access road too
        for name in ('Tree_Tuscan_Test', C.SHRUBS[0] if isinstance(C.SHRUBS, tuple) else C.SHRUBS):
            with patch.object(E, 'line', return_value=E.Line(self.route)):
                keep, _ = C.settle(name, on[:, 0], on[:, 1], np.full(3, RAIL + 4.), c)
            self.assertEqual(keep.tolist(), [False, False, True], name)

    def test_committed_corridor_keeps_plants_off_the_station(self):
        c = C.Corridor(committed_route())
        self.assertLess(float(c.station_margin(np.array([900.]), np.array([4625.]))[0]), 0.)
        self.assertGreater(float(c.station_margin(np.array([900.]), np.array([4900.]))[0]), 0.)


class RouteGround(unittest.TestCase):
    def test_carved_tiles_match_the_committed_line_and_site(self):
        import hashlib
        from belmonte import source
        carved = [e for e in source.manifest()['meshes'] if e.get('railway_carved')]
        self.assertTrue(carved)
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
        import belmonte_station_terrain as tool
        digest = hashlib.sha256(C.LINE.read_bytes() + Path(S.__file__).read_bytes() +
                                json.dumps(tool.SALON_PATH).encode()).hexdigest()[:16]
        for entry in carved:
            self.assertEqual(entry['railway_carved'], digest, f"{entry['name']}: run tools/belmonte_station_terrain.py")
            self.assertTrue((yori.ASSETS / 'belmonte' / 'natural' / f"{entry['name']}.glb").is_file(), entry['name'])

    def test_natural_terrain_differs_only_where_carved(self):
        from belmonte import source, layout as BM
        natural, carved = source.terrain(natural=True), source.terrain()
        # local frame: the station's ground (carved) and the town's centre (not)
        site = np.array([900., 4625.]) - BM.ORIGIN[:2]
        town = np.array([550., 4482.]) - BM.ORIGIN[:2]
        self.assertGreater(abs(float(natural.height(*site[:, None])[0] - carved.height(*site[:, None])[0])), .5)
        self.assertEqual(float(natural.height(*town[:, None])[0]), float(carved.height(*town[:, None])[0]))

    def test_committed_street_front_flush(self):
        """The carved tiles along the facade: the ground from the front face to 3 m out stays within 2 cm of the
        street, sampled every 0.1 m (no slot wider than that between the building and the ground)."""
        from belmonte import source, layout as BM
        carved = source.terrain()
        site = E.line().station()
        a, u = np.meshgrid(np.arange(S.HEADHOUSE[1], S.HEADHOUSE[1] + 3. + 1e-9, .1),
                           np.linspace(S.HEADHOUSE[2], S.HEADHOUSE[3], 160))
        xy = site.world(a.ravel(), u.ravel())
        z = carved.height(xy[:, 0] - BM.ORIGIN[0], xy[:, 1] - BM.ORIGIN[1]) + BM.ORIGIN[2]
        off = np.abs(z - (site.rail + S.STREET))
        worst = int(np.argmax(off))
        self.assertLess(float(off[worst]), .02, f'a={a.ravel()[worst]:.1f} u={u.ravel()[worst]:.1f}')

    def test_committed_access_road_and_salon_path(self):
        """The carved tiles carry the access road at its grade, and the Salon's path on its own ground."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
        import belmonte_station_terrain as tool
        from belmonte import source, layout as BM
        natural, carved = source.terrain(natural=True), source.terrain()
        site = E.line().station()
        pts, _ = site.access()
        t = np.linspace(.1, .95, 9)
        q = pts[0] + t[:, None] * (pts[-1] - pts[0]) - BM.ORIGIN[:2]
        z = carved.height(q[:, 0], q[:, 1]) + BM.ORIGIN[2]
        self.assertLess(float(np.abs(z - site.access_z(t)).max()), .15)
        a, b = (np.asarray(p, float) for p in tool.SALON_PATH['points'])
        q = a + np.linspace(0., 1., 9)[:, None] * (b - a) - BM.ORIGIN[:2]
        self.assertLess(float(np.abs(carved.height(q[:, 0], q[:, 1]) - natural.height(q[:, 0], q[:, 1])).max()), .05)


    def test_committed_ground_stays_under_the_paving(self):
        """The carved tiles never rise through the forecourt's cobbles (its side kerbs included) or the access road's:
        at least a centimetre under their top on a 0.25 m grid (the in-game probe's defect, 2026-10-19)."""
        from belmonte import source, layout as BM
        from train import station as ST
        carved, site = source.terrain(), E.line().station()

        def ground(x, y):
            return carved.height(np.ravel(x) - BM.ORIGIN[0], np.ravel(y) - BM.ORIGIN[1]) + BM.ORIGIN[2]
        a0, a1, u0, u1 = S.FORECOURT
        a, u = np.meshgrid(np.arange(a0, a1 + 1e-6, .25), np.arange(u0 - .3, u1 + .3 + 1e-6, .25), indexing='ij')
        xy = site.world(a, u)
        over = ground(xy[..., 0], xy[..., 1]) - (site.rail + S.STREET + ST.PAVING)
        worst = int(np.argmax(over))
        self.assertLess(float(over[worst]), -.01, f'forecourt a={a.ravel()[worst]:.2f} u={u.ravel()[worst]:.2f}')
        pts, _ = site.access()
        length = float(np.hypot(*(pts[-1] - pts[0])))
        d = (pts[-1] - pts[0]) / length
        s, w = np.meshgrid(np.arange(0., length + 1e-6, .25), np.arange(-3.5, 3.5 + 1e-6, .25), indexing='ij')
        xy = pts[0] + s[..., None] * d + w[..., None] * np.array([-d[1], d[0]])
        over = ground(xy[..., 0], xy[..., 1]) - (site.access_z(s.ravel() / length) + ST.PAVING)
        worst = int(np.argmax(over))
        self.assertLess(float(over[worst]), -.01, f'access road s={s.ravel()[worst]:.2f} w={w.ravel()[worst]:.2f}')


class Bank(unittest.TestCase):
    def test_last_bank_meets_the_carved_cutting(self):
        """The valley's last embankment runs into the final cutting, whose tiles are carved (valley_carve_start): its
        bank mesh follows the carved ground there, not the natural one (no step at the formation)."""
        from belmonte import layout as BM, source
        from belmonte.source import Surface
        from train import route as R, track as T
        valley = source.terrain(natural=True)

        def ground(x, y):       # the valley's natural ground (the route study's, without the built far hills)
            return valley.height(np.asarray(x) - BM.ORIGIN[0], np.asarray(y) - BM.ORIGIN[1]) + BM.ORIGIN[2]
        route = dict(committed_route(), summary={'structures': []})
        line = T.Line(route)
        a, b = T.bank_ranges(line)[-1]
        self.assertLess(E.valley_carve_start(E.line(), route['samples']), b)
        with patch.object(R, 'ground', ground):
            mesh = T.bank_mesh(line, a, b, 0, (0., 0., 0.))
        v = np.asarray(mesh.verts)
        bank = Surface(np.asarray([(v[f[0]], v[f[k]], v[f[k + 1]]) for f in mesh.faces for k in range(1, len(f) - 1)]))
        rows_ = [r for r in route['samples'] if a <= r['s'] <= b]
        z = bank.height(np.array([r['x'] for r in rows_]), np.array([r['y'] for r in rows_]))
        rail = np.array([r['rail_z'] for r in rows_])
        on = np.isfinite(z)
        self.assertLess(float(np.abs(z[on] - (rail[on] - E.FORMATION_DROP)).max()), .12)


class Tool(unittest.TestCase):
    def test_refuses_a_line_without_station(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
        import belmonte_station_terrain as tool
        with patch.object(E, 'line', return_value=E.Line({'samples': rows(END + [2000., 0.])})):
            with self.assertRaises(SystemExit):
                tool.main(['--dry-run'])


if __name__ == '__main__':
    unittest.main()
