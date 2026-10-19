"""The railway's corridor (train/corridor.py) over every planted source along the line (Hidamari's city.json,
Belmonte's runtime.json, the world's world.json): no tree in it, shrubs and grass only down to its soft edge, and
nothing near the line left floating over or sunk under the earthworks' carved ground."""
import json
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world' / 'regions'))

import yori  # noqa: E402
from train import corridor as C  # noqa: E402


def planted():
    """{source: {name: array of (x, y, z)}} for the built sources that exist."""
    out = {}
    city = yori.OUT / 'hidamari' / 'city.json'
    if city.exists():
        out['hidamari'] = {n: np.asarray(v, float).reshape(len(v), -1)[:, :3]
                           for n, v in json.loads(city.read_text())['instances'].items() if v}
    world = yori.OUT / 'world.json'
    if world.exists():
        out['world'] = {n: np.asarray(v, float).reshape(len(v), -1)[:, :3]
                        for n, v in json.loads(world.read_text()).get('instances', {}).items() if v}
    runtime = yori.OUT / 'belmonte' / 'runtime.json'
    if runtime.exists():
        from belmonte import layout as BM
        rows = {}
        for g in json.loads(runtime.read_text())['groups']:
            if not g.get('plant'):
                continue
            name = g['asset'].split('.')[-1]
            xy = [(t['translation_cm'][0] / 100 + BM.ORIGIN[0], -t['translation_cm'][1] / 100 + BM.ORIGIN[1],
                   t['translation_cm'][2] / 100 + BM.ORIGIN[2]) for t in g['transforms']]
            if xy:
                rows[name] = np.concatenate([rows[name], xy]) if name in rows else np.asarray(xy, float)
        out['belmonte'] = rows
    return out


class Corridor(unittest.TestCase):
    def test_tunnels_stay_wooded_and_earthworks_widen_it(self):
        self.assertIsNone(C.half_width({'class': 'tunnel', 'rail_z': 0, 'ground_z': 40}))
        self.assertEqual(C.half_width({'class': 'cutting', 'rail_z': 10, 'ground_z': 10.5}), C.HALF_WIDTH)
        self.assertGreater(C.half_width({'class': 'embankment', 'rail_z': 20, 'ground_z': 12}), C.HALF_WIDTH)
        self.assertEqual(C.half_width({'class': 'deep cutting', 'rail_z': 0, 'ground_z': 80}), C.MAX_HALF_WIDTH)

    def test_a_point_on_the_line_is_blocked_and_one_far_away_is_not(self):
        route = {'samples': [{'s': s, 'x': s, 'y': 0., 'rail_z': 0., 'ground_z': 0., 'class': 'embankment' if s < 100 else 'tunnel'}
                             for s in range(0, 210, 10)]}
        c = C.Corridor(route)
        self.assertEqual(c.blocked([50., 50., 50., 150.], [0., 9., 30., 0.]).tolist(), [True, True, False, False])

    def test_no_route_means_no_change(self):
        self.assertIsNone(C.load(Path('/nonexistent/route.json')))
        self.assertTrue(C.keep([0.], [0.]).all() or C.load() is not None)


class Clearance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.line = C.load()
        if cls.line is None:
            raise unittest.SkipTest('route not built (atelier build yorimichi world.belmonte_train_route)')
        cls.sources = planted()
        if not cls.sources:
            raise unittest.SkipTest('no planted source built')

    def test_no_tree_in_the_corridor_and_shrubs_and_grass_only_to_its_soft_edge(self):
        from train import earthworks as E
        ln = E.line()
        for source, names in self.sources.items():
            for name, xyz in names.items():
                k = C.kind(name)
                if k is None or not len(xyz):
                    continue
                with self.subTest(source=source, plant=name):
                    x, y = xyz[:, 0], xyz[:, 1]
                    if k == 'tree' or ln is None:
                        bad = self.line.blocked(x, y) if k != 'grass' else np.zeros(len(x), bool)
                    else:
                        s, u, _ = ln.project(x, y)
                        near = np.isfinite(s)
                        tunnel, _ = ln.inside(np.nan_to_num(s), ln.tunnels)
                        viaduct, _ = ln.inside(np.nan_to_num(s), ln.viaducts)
                        half = C.SHRUB_HALF if k == 'shrub' else C.GRASS_HALF
                        bad = near & (tunnel <= 0) & (viaduct <= 0) & (np.abs(np.nan_to_num(u, nan=1e9)) < half)
                    if bad.any():
                        self.fail(f'{int(bad.sum())} in the corridor, e.g. {xyz[bad][0].round(1).tolist()}')

    def test_nothing_near_the_line_floats_over_or_sinks_under_the_carved_ground(self):
        from train import earthworks as E
        ln = E.line()
        if ln is None:
            self.skipTest('earthworks off')
        for source, names in self.sources.items():
            for name, xyz in names.items():
                if C.kind(name) is None or not len(xyz):
                    continue
                with self.subTest(source=source, plant=name):
                    keep, z = C.settle(name, xyz[:, 0], xyz[:, 1], xyz[:, 2], self.line)
                    # Carving twice moves a crest by about ROUND / 4 (a plant right on a deep cutting's crest).
                    off = np.abs(z - xyz[:, 2]) > C.MOVED + .05
                    bad = off | ~keep
                    if bad.any():
                        self.fail(f'{int(bad.sum())} not settled on the carved ground, e.g. {xyz[bad][0].round(1).tolist()}')


if __name__ == '__main__':
    unittest.main()
