"""Ramp the joint lips of separately placed park pieces without touching ledges or real steps."""
import sys
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'world'))
import yori  # noqa: E402,F401
from communitypark import collision as C  # noqa: E402


def slab(x0, y0, x1, y1, z0, z1):
    """A closed box, faces wound outward, as a placed source piece."""
    vertices = np.array([(x, y, z) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)], float)
    faces = [(0, 2, 3), (0, 3, 1), (4, 5, 7), (4, 7, 6), (0, 1, 5), (0, 5, 4),
             (2, 6, 7), (2, 7, 3), (0, 4, 6), (0, 6, 2), (1, 3, 7), (1, 7, 5)]
    return vertices, np.array(faces)


def floor_tiles():
    """Two flush tiles of a deck: their shared edge rises 0 and must stay unramped."""
    return [slab(-4, -4, 0, 4, -.2, 0.), slab(0, -4, 4, 4, -.2, 0.)]


class RidingCollisionTest(unittest.TestCase):
    def test_flush_tiles_weld_without_ramps(self):
        vertices, faces, owner, report = C.riding_collision(floor_tiles())
        self.assertEqual(report['wedges'], 0)
        self.assertLess(report['welded_vertices'], 16)
        self.assertEqual(C.steps(vertices, faces, owner), [])
        self.assertEqual(report['buried_wall_triangles'], 4)
        triangles = vertices[faces]
        self.assertFalse(np.any(np.all(abs(triangles[:, :, 0]) < 1e-9, axis=1)))
        # The outside caps still stop a rider leaving the deck sideways.
        self.assertEqual(sum(np.all(abs(triangles[:, :, 0]-4) < 1e-9, axis=1)), 2)
        self.assertEqual(sum(np.all(abs(triangles[:, :, 0]+4) < 1e-9, axis=1)), 2)

    def test_a_proud_pad_gets_a_shallow_ramp_on_every_side(self):
        pad = slab(-1, -1, 1, 1, -.1, .02)
        before = C.steps(*C.weld(floor_tiles()+[pad]))
        self.assertTrue(before and all(abs(r-.02) < 1e-9 for _, r, _ in before))
        vertices, faces, owner, report = C.riding_collision(floor_tiles()+[pad])
        self.assertEqual([x for x in C.steps(vertices, faces, owner) if x[2] >= 0], [])
        self.assertAlmostEqual(report['max_rise_m'], .02)
        ramps = vertices[faces[owner < 0]]
        # 1:8 at most, and never above the pad or below the floor.
        self.assertGreaterEqual(ramps[..., 2].min(), -1e-9); self.assertLessEqual(ramps[..., 2].max(), .02+1e-9)
        normals = C._normals(ramps)[0]
        self.assertTrue(np.all(normals[:, 2] > np.cos(np.arctan(.2/.1))-1e-9))
        self.assertTrue(np.all(normals[:, 2] > 0))
        self.assertAlmostEqual(report['wedged_length_m'], 8., places=6)

    def test_small_floor_lip_has_a_gentle_transition(self):
        # The real bowl-floor joint rises 12.04 mm. Its old 10 cm wedge abruptly slowed the board;
        # exact recorded-input replays cleared that loss with a 30 cm run, keeping the lip smoothed.
        pieces = [slab(-4, -4, 0, 4, -.2, 0.), slab(0, -4, 4, 4, -.18796, .01204)]
        vertices, faces, owner, report = C.riding_collision(pieces)
        ramps = vertices[faces[owner < 0]]
        self.assertGreater(report['wedges'], 0)
        self.assertGreater(len(ramps), 0)
        normals = C._normals(ramps)[0]
        grade = np.linalg.norm(normals[:, :2], axis=1)/normals[:, 2]
        self.assertLessEqual(grade.max(), .05)
        self.assertGreaterEqual(ramps[..., 2].min(), -1e-9)
        self.assertLessEqual(ramps[..., 2].max(), .01204+1e-9)
        self.assertEqual(C.steps(vertices, faces, owner), [])

    def test_longer_run_does_not_leave_short_or_convex_neighbours(self):
        for kind in ('short', 'convex', 'gap'):
            with self.subTest(neighbour=kind):
                width = .18 if kind == 'gap' else .15
                pieces = [slab(-width, -1, 0, 1, -.2, 0.),
                          slab(0, -1, 1, 1, -.18796, .01204)]
                if kind == 'convex':
                    v, f = slab(-1, -1, -.15, 1, -.2, 0.)
                    v[:, 2] += .2*(v[:, 0]+.15)
                    pieces.append((v, f))
                elif kind == 'gap':
                    # The supported far endpoint must not hide a 5 mm gap along the extra run.
                    pieces.append(slab(-.4, -1, -.185, 1, -.2, 0.))
                vertices, faces, owner, report = C.riding_collision(pieces)
                ramps = vertices[faces[owner == -2]]
                self.assertGreater(report['wedges'], 0)
                self.assertGreater(len(ramps), 0)
                self.assertGreaterEqual(ramps[..., 0].min(), -width-1e-9)

    def test_ledges_and_real_steps_stay_sharp(self):
        ledge = slab(-1, -.2, 1, .2, -.1, .04)
        step = slab(2, -3, 3.5, 3, -.1, .3)
        vertices, faces, owner, report = C.riding_collision(floor_tiles()+[ledge, step], obstacles={2})
        self.assertEqual(report['wedges'], 0)
        self.assertEqual(C.steps(vertices, faces, owner, obstacles={2}), [])
        for part in (2, 3):
            self.assertEqual(sum(owner == part), 12)

    def test_sloped_join_caps_are_buried_but_the_riding_faces_stay(self):
        parts = floor_tiles()
        parts = [(v+np.column_stack((np.zeros(len(v)), np.zeros(len(v)), v[:, 1]*.4)), f) for v, f in parts]
        original = np.concatenate([v[f] for v, f in parts])
        riding = original[C._normals(original)[0][:, 2] > C.UP]
        vertices, faces, owner, report = C.riding_collision(parts)
        self.assertEqual(report['buried_wall_triangles'], 4)
        actual = vertices[faces][C._normals(vertices[faces])[0][:, 2] > C.UP]
        np.testing.assert_allclose(actual, riding)

    def test_cap_with_a_gap_beside_it_stays(self):
        pieces = [slab(-4, -4, 0, 4, -.2, 0.), slab(.1, -4, 4, 4, -.2, 0.)]
        _, _, _, report = C.riding_collision(pieces)
        self.assertEqual(report['buried_wall_triangles'], 0)

    def test_narrow_slots_between_neighbours_keep_the_exposed_cap(self):
        for lo, hi in ((.03, .07), (.12, .19), (.53, .58), (.031, .036)):
            with self.subTest(slot=(lo, hi)):
                pieces = [slab(-4, -4, 0, 4, -.2, 0.),
                          slab(0, -4, 4, lo, -.2, 0.), slab(0, hi, 4, 4, -.2, 0.)]
                vertices, faces, owner, _ = C.riding_collision(pieces)
                cap = (owner == 0) & np.all(abs(vertices[faces, 0]) < 1e-9, axis=1)
                self.assertEqual(sum(cap), 2)

    def test_an_overhead_deck_does_not_bury_a_lower_wall(self):
        floor = slab(-4, -4, 0, 4, -.2, 0.)
        roof = slab(-4, -4, 4, 4, 2.8, 3.)
        _, _, owner, report = C.riding_collision([floor, roof])
        self.assertEqual(report['buried_wall_triangles'], 0)
        self.assertEqual(sum(owner == 0), 12)

    def test_one_piece_with_floor_and_roof_keeps_its_lower_wall(self):
        floor = slab(-4, -4, 0, 4, -.2, 0.)
        roof = slab(-4, -4, 0, 4, 2.8, 3.)
        neighbour_roof = slab(0, -4, 4, 4, 2.8, 3.)
        _, _, owner, _ = C.riding_collision([floor, roof, neighbour_roof], groups=[0, 0, 1])
        self.assertEqual(sum(owner == 0), 12)

    def test_a_roof_beside_a_tall_piece_leaves_the_underpass_wall(self):
        wall = slab(-4, -4, 0, 4, 0., 3.)
        roof = slab(0, -4, 4, 4, 2.8, 3.)
        _, _, owner, _ = C.riding_collision([wall, roof])
        self.assertEqual(sum(owner == 0), 12)

    def test_small_foundation_offsets_do_not_leave_a_cap_above_the_join(self):
        first = slab(-4, -4, 0, 4, -.2, 0.)
        second = slab(0, -4, 4, 4, -.188, 0.)
        _, _, _, report = C.riding_collision([first, second])
        self.assertEqual(report['buried_wall_triangles'], 4)

    def test_larger_foundation_gaps_keep_the_lower_wall(self):
        first = slab(-4, -4, 0, 4, -.2, 0.)
        second = slab(0, -4, 4, 4, -.17, 0.)
        _, _, owner, _ = C.riding_collision([first, second])
        self.assertEqual(sum(owner == 0), 12)

    def test_a_floor_coincident_with_the_ramp_underside_keeps_its_coverage(self):
        parts = floor_tiles()
        ramps = [slab(-4, -4, 0, 4, 0., .2), slab(0, -4, 4, 4, 0., .2)]
        for vertices, _ in ramps:
            vertices[4:, 2] += (vertices[4:, 1]+4)*.005
        # A separate proud pad exercises the same wedge-and-merge path as the real park.
        pad = [slab(6, -4, 10, 4, -.2, 0.), slab(7, -1, 9, 1, 0., .02)]
        vertices, faces, owner, report = C.riding_collision(parts+ramps+pad)
        self.assertGreater(report['wedges'], 0)
        joint = np.isin(owner, (2, 3)) & np.all(abs(vertices[faces, 0]) < 1e-9, axis=1)
        self.assertEqual(sum(joint), 0)
        # Upward ramp faces and the foundation remain in the collision.
        self.assertTrue(np.any((owner == 2) & (C._normals(vertices[faces])[0][:, 2] > C.UP)))

    def test_material_parts_share_one_piece_for_cap_coverage(self):
        parts = []
        for v, f in floor_tiles():
            parts.extend([(v, f[:4]), (v, f[4:])])
        _, _, _, report = C.riding_collision(parts, groups=[0, 0, 1, 1])
        self.assertEqual(report['buried_wall_triangles'], 4)


if __name__ == '__main__':
    unittest.main()
