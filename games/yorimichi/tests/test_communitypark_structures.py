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
from communitypark.validate import riding_clearance  # noqa: E402


def source_fixture():
    parts = []
    # Adjacent upper slabs share a frame, and a separate slab sits over a
    # lower original platform. This distinguishes terrain and mesh footings.
    for node, centre, size in [(1, (1262, 550, 61), (4, 8, 1)),
                               (2, (1266, 550, 61), (4, 8, 1)),
                               (3, (1280, 550, 58), (6, 6, 1)),
                               (4, (1280, 550, 48.25), (10, 10, .5)),
                               (5, (1308, 544, 54.5), (.545, 3, .09)),
                               (6, (1308, 544, 56.5), (.545, 3, .09)),
                               (7, (1307, 602, 48.25), (20, 20, .5)),
                               (8, (1264.25, 583.7, 49.25), (.5, 3, .5)),
                               (9, (1264.25, 583.7, 48.25), (4, 6, .5))]:
        item = S.Mesh('fixture', 'none'); item.box(centre, size)
        triangles = L.local(item.triangles())
        parts.append({'node': node, 'mesh': 21 if node in (5, 6) else 18 if node == 8 else 0, 'vertices': triangles.reshape(-1, 3),
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
        cls.walking_triangles = np.concatenate((cls.triangles, L.place(cls.source.triangles())))

    def test_every_tread_and_landing_has_footing_and_body_clearance(self):
        route = S.stair_route()
        self.assertLess(self.metadata['step_rise_m'], .18)
        self.assertGreaterEqual(self.metadata['tread_run_m'], .28)
        self.assertGreaterEqual(self.metadata['stair_width_m'], 2.)
        self.assertGreater(route[-1, 2]-route[0, 2], 36.)
        # The service doorway crosses the west tower wall between waypoints.
        for x in np.linspace(route[0, 0], route[1, 0], 25):
            hits = S.heights(self.walking_triangles, x, route[0, 1])
            self.assertFalse(np.any((hits > S.DECK+.4) & (hits < S.DECK+1.95)), ('blocked doorway', x, hits.tolist()))
        # The top bridge must pass through an opening in the landing railing.
        for x in np.linspace(1300.9, 1302.1, 25):
            hits = S.heights(self.walking_triangles, x, 600.3)
            self.assertFalse(np.any((hits > S.TOP+.4) & (hits < S.TOP+1.95)), ('blocked bridge exit', x, hits.tolist()))
        for x, y, z in route:
            hits = S.heights(self.walking_triangles, x, y)
            bounded = hits[(hits >= z-.4) & (hits <= z+.4)]
            self.assertTrue(len(bounded), (x, y, z, 'missing tread'))
            self.assertLess(abs(float(bounded.max())-z), .025, (x, y, z, 'first floor hit'))
            # Sample a 70 cm wide body, including the two bridge turns.
            for dx, dy in [(0, 0), (.35, 0), (-.35, 0), (0, .35), (0, -.35)]:
                hits = S.heights(self.walking_triangles, x+dx, y+dy)
                self.assertFalse(np.any((hits > z+.2) & (hits < z+1.95)), (x, y, z, dx, dy, hits.tolist()))

    def test_raised_groups_have_contacts_on_original_surface_or_ground(self):
        groups = S.raised_groups(self.source)
        self.assertEqual(len(groups), 5)
        contacts = self.metadata['support_contacts']
        self.assertEqual(set(n for c in contacts for n in c['nodes']), {1, 2, 3, 5, 6, 8})
        for node in (5, 6, 8):
            self.assertEqual(sum(c['nodes'] == [node] for c in contacts), 2)
        source = L.place(self.source.triangles())
        for contact in contacts:
            x, y, z = contact['top']
            self.assertLess(float(abs(S.heights(source, x, y)-z).min()), 1e-8)
            self.assertTrue(np.any(abs(S.heights(self.triangles, x, y)-z) < .02), contact)
            x, y, z = contact['bottom']
            below = S.heights(source, x, y)
            self.assertTrue(abs(z-48.) < .03 or np.any(abs(below-z) < .03))
            self.assertGreater(contact['top'][2]-z, .45 if contact['nodes'] == [8] else .85)

    def test_main_frame_footings_stay_outside_original_skating_footprints(self):
        for footing in self.metadata['frame_footings']:
            x, y = footing['bottom'][:2]
            for part in self.source.parts:
                t = L.place(part['vertices'][part['faces']]); lo, hi = t.min((0, 1)), t.max((0, 1))
                self.assertFalse(lo[0]-.65 <= x <= hi[0]+.65 and lo[1]-.65 <= y <= hi[1]+.65,
                                 (footing, part['node']))

    def test_solid_clearance_catches_a_pole_with_both_ends_outside_body_band(self):
        pole = S.Mesh('bad-pole', 'steel')
        pole.beam([1305, 603.9, 48], [1305, 603.9, 60], .4)
        metadata = {'ride_support_members': [0], 'frame_footings': []}
        with self.assertRaisesRegex(AssertionError, 'intrudes into usable skating space'):
            riding_clearance(pole, metadata, L.place(self.source.triangles()), self.source.parts)

    def test_solid_clearance_checks_the_outer_edge_of_a_member(self):
        pole = S.Mesh('wide-pole', 'steel')
        # Its spine and spine-centred body probes miss the platform, but the
        # actual steel edge occupies the platform's previously usable space.
        pole.beam([1305, 591.6, 48], [1305, 591.6, 60], 1.)
        metadata = {'ride_support_members': [0], 'frame_footings': []}
        with self.assertRaisesRegex(AssertionError, 'intrudes into usable skating space'):
            riding_clearance(pole, metadata, L.place(self.source.triangles()), self.source.parts)


if __name__ == '__main__':
    unittest.main()
