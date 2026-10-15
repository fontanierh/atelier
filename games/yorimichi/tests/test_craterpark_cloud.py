"""Crater Park's lenticular cap cloud (world/regions/craterpark/cloud.py): closed shells, dense from Belmonte, thin
inside, the volcano's slopes left clear."""
import math
from pathlib import Path
import sys
import unittest

import numpy as np

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME / 'world' / 'regions'))
sys.path.insert(0, str(GAME))
from craterpark import cloud  # noqa: E402
from hidamari import mountains  # noqa: E402
import runtime_data  # noqa: E402

# Belmonte's town square at eye height, the coordinator's framing camera over it (UE 55000, -450000, 30000) and the
# racecourse: all look south at the volcano.
BELMONTE = [(550., 4482., 214.), (550., 4500., 300.), (385., 4855., 243.)]
# Riders inside: the caldera floor, the north ramps, the drop-in tower's deck and the west deck.
INSIDE = [(850., 2400., 645.), (870., 2700., 700.), (1293.5, 2481.3, 862.), (600., 2300., 670.)]


def ramp_space():
    """Points the ramps take (cloud.HIDE_RADIUS of the volcano, from the ground up to the north ramps' 770 m), and
    the drop-in tower's top."""
    points = [(1285., 2497., 855.)]
    cx, cy = mountains.VOLCANO
    for angle in range(0, 360, 30):
        for radius in (250., 400., cloud.HIDE_RADIUS - 10.):
            x, y = cx + radius * math.cos(math.radians(angle)), cy + radius * math.sin(math.radians(angle))
            ground = float(mountains.natural_height(np.array([x]), np.array([y]))[0])
            points += [(x, y, ground + 5.), (x, y, max(ground + 5., 770.))]
    return np.array(points)


def seen(camera, point):
    """Whether the volcano's ground leaves the sight line from camera to point open."""
    t = np.linspace(.02, .98, 240)[:, None]
    line = np.asarray(camera) + t * (np.asarray(point) - np.asarray(camera))
    return bool((line[:, 2] >= mountains.natural_height(line[:, 0], line[:, 1]) - 1.).all())


class ShellTests(unittest.TestCase):
    def test_shells_are_closed_outward_lenses(self):
        for layer in cloud.LAYERS:
            vertices, triangles = cloud.surface(layer)
            self.assertTrue(np.isfinite(vertices).all())
            self.assertEqual(triangles.min(), 0); self.assertEqual(triangles.max(), len(vertices) - 1)
            edges = np.sort(np.concatenate([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]]), 1)
            _, counts = np.unique(edges, axis=0, return_counts=True)
            self.assertTrue((counts == 2).all(), f"{layer['name']} is not closed")
            t = vertices[triangles]
            normals = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
            middle = vertices.mean(0)
            self.assertTrue((np.einsum('ij,ij->i', normals, t.mean(1) - middle) > 0).all(), layer['name'])

    def test_the_envelope_holds_every_shell(self):
        """The camera term's ellipsoid bounds every shell, and the veil lies inside the saucers' silhouette."""
        self.assertEqual([layer.get('veil', False) for layer in cloud.LAYERS], [True] + [False] * (len(cloud.LAYERS) - 1))
        centre, radii = cloud.envelope()
        for layer in cloud.LAYERS:
            vertices, _ = cloud.surface(layer)
            q = np.linalg.norm((vertices - centre) / radii, axis=1)
            self.assertLessEqual(q.max(), math.sqrt(2) + 1e-6, layer['name'])
        self.assertLess(cloud.LAYERS[0]['radius'], cloud.LAYERS[1]['radius'])

    def test_the_shells_stack_as_saucers(self):
        """Each rim higher and narrower than the one before (the concepts' pile of saucers)."""
        rims = [(layer['z'], layer['radius']) for layer in cloud.LAYERS[1:]]
        for (z0, r0), (z1, r1) in zip(rims, rims[1:]):
            self.assertGreater(z1, z0); self.assertLess(r1, r0)

    def test_record_is_unreal_ready(self):
        record = cloud.record()
        self.assertEqual(len(record['layers']), len(cloud.LAYERS))
        self.assertEqual(sum(layer['veil'] for layer in record['layers']), 1)
        for layer, source in zip(record['layers'], cloud.LAYERS):
            vertices = np.array(layer['vertices']).reshape(-1, 3) + record['origin_cm']
            expected, _ = cloud.surface(source)
            np.testing.assert_allclose(vertices, cloud.to_unreal(expected), atol=.1)
            self.assertEqual(len(layer['triangles']) % 3, 0)
        self.assertIn('craterpark/cloud.json', runtime_data.STAGED)


class LookTests(unittest.TestCase):
    def test_belmonte_does_not_see_the_ramps(self):
        points = ramp_space()
        for camera in BELMONTE:
            self.assertGreater(cloud.camera_q(camera), cloud.FAR_Q)
            covered = [cloud.coverage(camera, p, step=3.) for p in points if seen(camera, p)]
            self.assertGreater(len(covered), 10)
            self.assertGreaterEqual(min(covered), .85, camera)

    def test_riders_inside_see_the_world_through_a_thin_veil(self):
        for camera in INSIDE:
            self.assertLess(cloud.camera_q(camera), cloud.NEAR_Q)
            camera = np.array(camera)
            for angle in range(0, 360, 45):
                way = np.array([math.cos(math.radians(angle)), math.sin(math.radians(angle)), -.1])
                self.assertLessEqual(cloud.coverage(camera, camera + 900. * way, step=3.), .4)
            # nothing hangs in the rider's face: no shell surface within the near fade's clear distance
            for direction in ((0, 0, 1.), (0, 0, -1.), (1., 0, 0), (0, 1., 0)):
                self.assertEqual(cloud.coverage(camera, camera + cloud.NEAR_FADE[0] * np.array(direction)), 0.)

    def test_the_slopes_stay_clear(self):
        cx, cy = mountains.VOLCANO
        for camera in BELMONTE:
            for angle in range(30, 160, 20):    # the slopes facing Belmonte
                x, y = cx + 760. * math.cos(math.radians(angle)), cy + 760. * math.sin(math.radians(angle))
                ground = float(mountains.natural_height(np.array([x]), np.array([y]))[0])
                self.assertLess(cloud.coverage(camera, (x, y, ground + 2.), step=3.), .05, (angle, ground))


if __name__ == '__main__':
    unittest.main()
