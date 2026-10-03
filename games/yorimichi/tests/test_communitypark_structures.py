"""Exercise ascent clearance and grounded contacts with an independent source fixture."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'world'))
import yori  # noqa: E402,F401
from communitypark import layout as L, structures as S  # noqa: E402


def source_fixture():
    parts = []
    # Adjacent upper slabs share a frame, and a separate slab sits over a
    # lower original platform. This distinguishes terrain and mesh footings.
    for node, centre, size in [(1, (1262, 550, 61), (4, 8, 1)),
                               (2, (1266, 550, 61), (4, 8, 1)),
                               (3, (1280, 550, 58), (6, 6, 1)),
                               (4, (1280, 550, 48.25), (10, 10, .5))]:
        item = S.Mesh('fixture', 'none'); item.box(centre, size)
        triangles = L.local(item.triangles())
        parts.append({'node': node, 'mesh': 0, 'vertices': triangles.reshape(-1, 3),
                      'faces': np.arange(triangles.size//3).reshape(-1, 3)})
    return SimpleNamespace(parts=parts, triangles=lambda: np.concatenate(
        [part['vertices'][part['faces']] for part in parts]))


class StructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = source_fixture()
        def ground(x, y, sampler=None): return np.full(np.broadcast(x, y).shape, 48.)
        with patch('communitypark.structures.scene', return_value=cls.source), patch('communitypark.layout.ground', side_effect=ground):
            cls.meshes, cls.metadata = S.build(ground)
        cls.triangles = np.concatenate([mesh.triangles() for mesh in cls.meshes])

    def test_every_tread_and_landing_has_footing_and_body_clearance(self):
        route = S.stair_route()
        self.assertLess(self.metadata['step_rise_m'], .18)
        self.assertGreaterEqual(self.metadata['tread_run_m'], .28)
        self.assertGreaterEqual(self.metadata['stair_width_m'], 2.)
        self.assertGreater(route[-1, 2]-route[0, 2], 36.)
        for x, y, z in route:
            hits = S.heights(self.triangles, x, y)
            self.assertTrue(np.any(abs(hits-z) < .025), (x, y, z, 'missing tread'))
            # Sample a 70 cm wide body, including the two bridge turns.
            for dx, dy in [(0, 0), (.35, 0), (-.35, 0), (0, .35), (0, -.35)]:
                hits = S.heights(self.triangles, x+dx, y+dy)
                self.assertFalse(np.any((hits > z+.2) & (hits < z+1.95)), (x, y, z, dx, dy, hits.tolist()))

    def test_raised_groups_have_contacts_on_original_surface_or_ground(self):
        groups = S.raised_groups(self.source)
        self.assertEqual(len(groups), 2)
        contacts = self.metadata['support_contacts']
        self.assertEqual(set(n for c in contacts for n in c['nodes']), {1, 2, 3})
        source = L.place(self.source.triangles())
        for contact in contacts:
            x, y, z = contact['top']
            self.assertLess(float(abs(S.heights(source, x, y)-z).min()), 1e-8)
            x, y, z = contact['bottom']
            below = S.heights(source, x, y)
            self.assertTrue(abs(z-48.) < .03 or np.any(abs(below-z) < .03))
            self.assertGreater(contact['top'][2]-z, .85)


if __name__ == '__main__':
    unittest.main()
