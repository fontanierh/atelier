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


def thin_plate(x0, y0, x1, y1, split=False):
    boundary = [(x0, y0, 0), (x1, y0, 0), (x1, y1, 0), (x0, y1, 0)]
    if split: boundary.append((x0, (y0+y1)/2, 0))
    n = len(boundary)
    vertices = np.array(boundary+[((x0+x1)/2, (y0+y1)/2, 0),
                                 (x0+(x1-x0)*.6, (y0+y1)/2, 0)])
    faces = [(a, (a+1)%n, n) for a in range(n)]+[((a+1)%n, a, n+1) for a in range(n)]
    return vertices, np.array(faces)


def transition(x0, x1, bend=15., rows=4, radius=1., base=-.2):
    """A closed bowl transition piece, faceted like the source: rows of `bend` degrees up a circular profile, swept
    along x in two spans. Returns (vertices, faces) and the profile's (y, z) points."""
    profile = [(radius*np.sin(np.radians(bend*i)), radius*(1-np.cos(np.radians(bend*i)))) for i in range(rows+1)]
    xs = (x0, (x0+x1)/2, x1); top = len(profile)*len(xs)
    vertices = [(x, y, z) for y, z in profile for x in xs] + [(x, y, base) for y in (0., profile[-1][0]) for x in (x0, x1)]
    def at(i, j): return i*len(xs)+j
    groups = []
    for i in range(rows):
        for j in range(2):
            groups.append(((at(i, j), at(i, j+1), at(i+1, j+1)), (0, 0, 1)))
            groups.append(((at(i, j), at(i+1, j+1), at(i+1, j)), (0, 0, 1)))
    a, b, c, d = top, top+1, top+2, top+3     # bottom: front x0, front x1, back x0, back x1
    groups += [((a, b, d), (0, 0, -1)), ((a, d, c), (0, 0, -1)),
               ((a, at(0, 0), at(0, 2)), (0, -1, 0)), ((a, at(0, 2), b), (0, -1, 0)),
               ((c, at(rows, 0), at(rows, 2)), (0, 1, 0)), ((c, at(rows, 2), d), (0, 1, 0))]
    for end, j, (front, back) in ((-1, 0, (a, c)), (1, 2, (b, d))):
        ring = [front] + [at(i, j) for i in range(rows+1)] + [back]
        groups += [((back, ring[k], ring[k+1]), (end, 0, 0)) for k in range(len(ring)-2)]
    vertices = np.array(vertices, float); faces = []
    for face, outward in groups:
        n = np.cross(vertices[face[1]]-vertices[face[0]], vertices[face[2]]-vertices[face[0]])
        faces.append(face if n@outward > 0 else face[::-1])
    return (vertices, np.array(faces)), profile


def riding_bends(vertices, faces, up=.3):
    """Bend in degrees across every edge shared by two upward faces of a welded mesh."""
    normals = C._normals(vertices[faces])[0]; edges = {}
    for k in np.flatnonzero(normals[:, 2] > up):
        for a, b in zip(faces[k], np.roll(faces[k], -1)):
            edges.setdefault((min(a, b), max(a, b)), []).append(k)
    return np.array([np.degrees(np.arccos(np.clip(normals[k[0]]@normals[k[1]], -1, 1)))
                     for k in edges.values() if len(k) == 2])


class RidingCollisionTest(unittest.TestCase):
    def test_zero_thickness_plate_keeps_its_top_and_a_closed_ceiling(self):
        vertices = np.array([(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0), (1, 1, 0.)])
        faces = np.array([(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4), (0, 2, 1), (0, 3, 2)])
        owner = np.zeros(len(faces), int)
        v, f, _, report = C.solid_sheet_undersides(vertices, faces, owner)
        self.assertEqual(report, {'solid_sheet_patches': 1, 'partial_sheet_patches_kept': 0,
                                  'covered_sheet_patches_kept': 0,
                                  'lowered_sheet_triangles': 2,
                                  'sheet_skirt_triangles': 8})
        triangles = v[f]; normals = C._normals(triangles)[0]
        np.testing.assert_array_equal(triangles[normals[:, 2] > .99], vertices[faces[:4]])
        self.assertTrue(np.all(triangles[normals[:, 2] < -.99, :, 2] == -2*C.WELD))
        # Every exposed rim stays a real corner: the new skirts face outwards, and the volume is closed.
        centre = np.array([1, 1, -C.WELD]); side = abs(normals[:, 2]) < .01
        self.assertTrue(np.all(np.sum(normals[side]*(triangles[side].mean(1)-centre), axis=1) > 0))
        edges = {}
        for face in f:
            for a, b in zip(face, np.roll(face, -1)):
                key = tuple(sorted((int(a), int(b)))); edges[key] = edges.get(key, 0)+1
        self.assertEqual(set(edges.values()), {2})

    def test_solid_sloped_and_obstacle_plates_keep_their_collision(self):
        v = np.array([(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0), (1, 1, 0.)])
        f = np.array([(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4), (0, 2, 1), (0, 3, 2)])
        sloped = v.copy(); sloped[:, 2] = .1*sloped[:, 0]
        for vertices, faces, obstacles in ((*slab(0, 0, 2, 2, -.1, 0), ()),
                                          (sloped, f, ()), (v, f, (0,))):
            with self.subTest(obstacle=bool(obstacles), vertices=vertices.tolist()):
                actual_v, actual_f, _, report = C.solid_sheet_undersides(vertices, faces,
                                                                         np.zeros(len(faces), int), obstacles)
                np.testing.assert_array_equal(actual_v, vertices)
                np.testing.assert_array_equal(actual_f, faces)
                self.assertEqual(report['solid_sheet_patches'], 0)

    def test_plate_rim_with_a_real_wall_does_not_get_an_extra_skirt(self):
        vertices = np.array([(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0), (1, 1, 0.),
                             (0, 0, 1), (2, 0, 1)])
        faces = np.array([(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4), (0, 2, 1), (0, 3, 2),
                          (0, 1, 6), (0, 6, 5)])
        v, f, _, report = C.solid_sheet_undersides(vertices, faces, np.zeros(len(faces), int))
        self.assertEqual(report['sheet_skirt_triangles'], 6)
        # Retain both authored wall triangles, and add no new wall between the ceiling and this join.
        triangles = v[f]
        for triangle in vertices[faces[-2:]]:
            self.assertTrue(any(np.array_equal(t, triangle) for t in triangles))
        self.assertFalse(any(np.all(t[:, 1] == 0) and np.min(t[:, 2]) < 0 for t in triangles))

    def test_flush_plate_t_junctions_do_not_gain_internal_skirts(self):
        vertices, faces, owner = C.weld([thin_plate(0, 0, 2, 2), thin_plate(2, 0, 4, 2, split=True)])
        v, f, _, report = C.solid_sheet_undersides(vertices, faces, owner)
        self.assertEqual(report['solid_sheet_patches'], 2)
        self.assertEqual(report['partial_sheet_patches_kept'], 0)
        triangles = v[f]; normals = C._normals(triangles)[0]
        self.assertFalse(any(np.all(t[:, 0] == 2) for t in triangles[abs(normals[:, 2]) < .01]))
        np.testing.assert_array_equal(triangles[normals[:, 2] > .99],
                                      vertices[faces][C._normals(vertices[faces])[0][:, 2] > .99])

    def test_partially_abutting_plate_keeps_its_original_unsplit_rim(self):
        vertices, faces, owner = C.weld([thin_plate(0, 0, 2, 2), thin_plate(2, 0, 4, 1, split=True)])
        v, f, o, report = C.solid_sheet_undersides(vertices, faces, owner)
        self.assertEqual(report['partial_sheet_patches_kept'], 1)
        np.testing.assert_array_equal(v[f][o == 0], vertices[faces][owner == 0])

    def test_unpaired_plate_t_edge_does_not_gain_a_new_contact_partner(self):
        vertices = np.array([(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0),
                             (2, 1, 0), (1, 1, 0.)])
        faces = np.array([(0, 1, 5), (1, 4, 5), (4, 2, 5), (2, 3, 5), (3, 0, 5),
                          (0, 2, 1), (0, 3, 2)])
        v, f, _, report = C.solid_sheet_undersides(vertices, faces, np.zeros(len(faces), int))
        self.assertEqual(report['solid_sheet_patches'], 1)
        self.assertEqual(report['sheet_skirt_triangles'], 6)
        triangles = v[f]; normals = C._normals(triangles)[0]
        self.assertFalse(any(np.all(t[:, 0] == 2) for t in triangles[abs(normals[:, 2]) < .01]))

    def test_plate_buried_under_another_riding_floor_stays_unchanged(self):
        top = np.array([(-1, -1, .025), (3, -1, .025), (3, 3, .025), (-1, 3, .025)])
        vertices, faces, owner = C.weld([thin_plate(0, 0, 2, 2),
                                         (top, np.array([(0, 1, 2), (0, 2, 3)]))])
        v, f, o, report = C.solid_sheet_undersides(vertices, faces, owner)
        self.assertEqual(report['solid_sheet_patches'], 0)
        self.assertEqual(report['covered_sheet_patches_kept'], 1)
        np.testing.assert_array_equal(v[f], vertices[faces])
        np.testing.assert_array_equal(o, owner)

    def test_back_beneath_a_curved_top_is_not_flooded_into_the_sheet_patch(self):
        vertices = np.array([(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0),
                             (4, 1, 0), (4, 1, 1.)])
        faces = np.array([(0, 1, 2), (0, 2, 3), (2, 1, 0), (3, 2, 0),
                          (1, 2, 4), (2, 1, 5)])
        v, f, _, report = C.solid_sheet_undersides(vertices, faces, np.zeros(len(faces), int))
        self.assertEqual(report['lowered_sheet_triangles'], 2)
        triangles = v[f]
        self.assertTrue(any(np.array_equal(t, vertices[faces[4]]) for t in triangles))
        self.assertTrue(any(np.array_equal(t, vertices[faces[5]]) for t in triangles))
        self.assertFalse(any(np.all(t[:, 0] == 2) and np.min(t[:, 2]) < 0 for t in triangles))

    def test_sheet_joined_only_to_sloped_aprons_stays_authored(self):
        self.check_apron_joins(flat_west=False)

    def test_sheet_at_a_flat_floor_join_gets_no_wall_across_sloped_aprons(self):
        self.check_apron_joins(flat_west=True)

    def check_apron_joins(self, flat_west):
        pieces = [thin_plate(0, 0, 2, 2)]
        # A half-millimetre source seam, inside the weld tolerance: the probes lie on the apron, whose
        # extrapolated plane is flush at the rim. Its actual probe height differs from that rim height.
        for points in ([[(-.1, -.3005, -.012), (2.1, -.3005, -.012), (2.1, -.0005, 0), (-.1, -.0005, 0)],
                        [(-.1, 2.0005, 0), (2.1, 2.0005, 0), (2.1, 2.3005, -.012), (-.1, 2.3005, -.012)],
                        [(2.0005, -.1, 0), (2.3005, -.1, -.012), (2.3005, 2.1, -.012), (2.0005, 2.1, 0)],
                        [(-.3005, -.1, 0 if flat_west else -.012), (-.0005, -.1, 0), (-.0005, 2.1, 0),
                         (-.3005, 2.1, 0 if flat_west else -.012)]]):
            pieces.append((np.array(points), np.array([(0, 1, 2), (0, 2, 3)])))
        vertices, faces, owner = C.weld(pieces)
        v, f, o, report = C.solid_sheet_undersides(vertices, faces, owner)
        triangles = v[f]; normals = C._normals(triangles)[0]
        self.assertEqual(report['sheet_skirt_triangles'], 0)
        if flat_west:
            self.assertEqual(report['lowered_sheet_triangles'], 4)
            before = vertices[faces]; up = C._normals(before)[0][:, 2] > 0
            np.testing.assert_array_equal(triangles[normals[:, 2] > 0], before[up])
        else:
            np.testing.assert_array_equal(triangles, vertices[faces])
            np.testing.assert_array_equal(o, owner)

    def test_faceted_transitions_ride_smoothly_and_stay_joined(self):
        # The community bowl's transitions bend up to 17 degrees between rows; at 10 m/s one such crease
        # in a frame jolts the board past the native shock limit. Two pieces share a profile at x=1.
        (first, profile), (second, _) = transition(0., 1.), transition(1., 2.)
        floor = slab(0., -2., 2., 0., -.2, 0.)
        before = C.weld([floor, first, second])
        self.assertAlmostEqual(riding_bends(before[0], before[1]).max(), 15., places=6)
        vertices, faces, owner, report = C.riding_collision([floor, first, second])
        self.assertEqual(report['smoothed_pieces'], 2)
        self.assertEqual(report['wedges'], 0)
        self.assertEqual(C.steps(vertices, faces, owner), [])
        bends = riding_bends(vertices, faces)
        self.assertLess(bends[bends < C.CREASE].max(), 4.)
        # Loop draws a concave transition slightly inward: up to about 13 mm above these 26 cm facets, never
        # below them, and still flush with the floor.
        triangles = vertices[faces]; up = C._normals(triangles)[0][:, 2] > .3
        points = np.unique(triangles[up].reshape(-1, 3), axis=0)
        y, z = np.array(profile).T
        on = points[(points[:, 1] >= 0) & (points[:, 1] <= y[-1])]
        rise = on[:, 2]-np.interp(on[:, 1], y, z)
        self.assertGreaterEqual(rise.min(), -1e-9); self.assertLess(rise.max(), .015)
        self.assertEqual(abs(points[points[:, 1] <= 0, 2]).max(), 0.)

    def test_flat_and_sharp_pieces_are_not_smoothed(self):
        for piece in (slab(-1, -1, 1, 1, -.2, 0.), slab(-1, -.2, 1, .2, -.1, .04)):
            welded = C.weld([piece])
            self.assertIs(C.smooth_riding(*welded)[0], welded[0])
        _, _, _, report = C.riding_collision(floor_tiles())
        self.assertEqual(report['smoothed_pieces'], 0)

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

    def test_shared_feet_do_not_cut_across_a_neighbour_end(self):
        # The extra floor ends at y=0. One foot can extend, while the next must stay short;
        # the diagonal between them must not cross the open quadrant x<-.15, y>0.
        pieces = [slab(-.15, -1, 0, 1, -.2, 0.), slab(0, -1, 1, 1, -.18796, .01204),
                  slab(-.4, -1, -.15, 0, -.2, 0.)]
        vertices, faces, owner, _ = C.riding_collision(pieces)
        ramps = vertices[faces[owner == -2]]
        self.assertGreater(len(ramps), 0)
        self.assertLessEqual(ramps[..., 0].min(), -.3+1e-9)
        for triangle in ramps:
            feet = triangle[abs(triangle[:, 2]) < 1e-9]
            if len(feet) == 2:
                centre = feet.mean(0)
                self.assertFalse(centre[0] < -.15-1e-9 and centre[1] > 1e-9)
        feet = ramps[(abs(ramps[..., 2]) < 1e-9) & (abs(ramps[..., 1]) < 1e-9)]
        np.testing.assert_allclose(np.unique(feet[:, 0]), [-.1])

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

    def test_a_closed_transition_shell_does_not_leave_a_cap_at_its_crest(self):
        # The measured bowl transition meets the slab in a knife edge. Its underside
        # closes the small void within 30 cm; the crest must not snag the board.
        floor = slab(-2, -1, 0, 1, -.3, 0.)
        def shell(x0, x1, fall=.96):
            vertices, faces = slab(x0, -1, x1, 1, -.3, 0.)
            vertices[:4, 2] = -fall*vertices[:4, 0]
            vertices[4:, 2] = -vertices[4:, 0]/6
            return vertices, faces
        for kind in ('closed', 'wider_closed', 'short', 'gap', 'adjacent_gap', 'long_void', 'underpass'):
            with self.subTest(neighbour=kind):
                pieces = [floor, shell(0., .2 if kind == 'short' else 1.)]
                groups = None
                if kind == 'gap':
                    pieces = [floor, shell(0., .1), shell(.12, 1.)]
                    groups = [0, 1, 1]
                elif kind == 'adjacent_gap':
                    pieces[1] = shell(.01, 1.)
                elif kind in ('wider_closed', 'long_void'):
                    pieces[1] = shell(0., 1., .6 if kind == 'wider_closed' else .4)
                elif kind == 'underpass':
                    pieces[0] = slab(-2, -1, 0, 1, -1.5, 0.)
                vertices, faces, owner, _ = C.riding_collision(pieces, groups=groups)
                cap = (owner == 0) & np.all(abs(vertices[faces, 0]) < 1e-9, axis=1)
                self.assertEqual(sum(cap), 0 if kind in ('closed', 'wider_closed') else 2)

    def test_measured_bowl_shell_closes_before_its_short_edge_ends(self):
        joint, end = -10.19744873046875, -9.89764404296875
        floor = slab(17.01348876953125, -13.19744873046875, 20.0140380859375, joint,
                     7.227691650390625, 7.527740478515625)
        vertices, faces = slab(17.01397705078125, joint, 21.5140380859375, end, 0., 1.)
        along = (vertices[:, 1]-joint)/(end-joint)
        vertices[:4, 2] = 7.5276947021484375+along[:4]*(7.2386322021484375-7.5276947021484375)
        vertices[4:, 2] = 7.5276947021484375+along[4:]*(7.4749603271484375-7.5276947021484375)
        vertices, faces, owner, _ = C.riding_collision([floor, (vertices, faces)])
        cap = (owner == 0) & np.all(abs(vertices[faces, 1]-joint) < 1e-9, axis=1)
        self.assertEqual(sum(cap), 0)
        outer = (owner == 0) & np.all(abs(vertices[faces, 1]+13.19744873046875) < 1e-9, axis=1)
        self.assertEqual(sum(outer), 2)

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

    def test_knife_edge_fill_keeps_a_ceiling_below_the_riding_crest(self):
        # The measured bowl crest with synthetic full-width slab coverage. A speculative
        # truck contact on its downward face cut 3.39 m/s from a faithful replay.
        # The real park has two adjacent slabs across this width;
        # partial coverage is tested separately. The pocket closes to their base in 30 cm.
        joint, end = -10.19744873046875, -9.89764404296875
        floor = slab(17.01348876953125, -13.19744873046875, 21.5140380859375, joint,
                     7.227691650390625, 7.527740478515625)
        vertices, faces = slab(17.01397705078125, joint, 21.5140380859375, end, 0., 1.)
        along = (vertices[:, 1]-joint)/(end-joint)
        vertices[:4, 2] = 7.5276947021484375+along[:4]*(7.2386322021484375-7.5276947021484375)
        vertices[4:, 2] = 7.5276947021484375+along[4:]*(7.4749603271484375-7.5276947021484375)
        source = C.weld([floor, (vertices, faces)])
        down = C._normals(source[0][source[1]])[0][:, 2] < 0
        removed = C.crest_pockets(*source)
        self.assertEqual(set(removed), set(np.flatnonzero(down & (source[2] == 1))))
        self.assertEqual(len(removed), 2)
        actual_vertices, actual_faces, owner, report = C.riding_collision([floor, (vertices, faces)])
        actual = actual_vertices[actual_faces]
        self.assertEqual(report['filled_underside_triangles'], 2)
        self.assertEqual(report['filled_crest_pockets'], 1)
        ceilings = actual[(owner == 1) & (C._normals(actual)[0][:, 2] < 0)]
        self.assertEqual(len(ceilings), 2)
        np.testing.assert_allclose(ceilings[:, :, 2], 7.227691650390625)
        # Their extended planes remain below both riding tops, even across the old crest.
        self.assertTrue(np.all(C._normals(ceilings)[0][:, 2] < -.999))
        self.assertTrue(np.any((owner == 1) & (C._normals(actual)[0][:, 2] > C.UP)))

    def test_underpasses_overhangs_and_open_pockets_keep_their_undersides(self):
        for kind in ('underpass', 'overhang', 'short', 'gap', 'not_knife_edge', 'obstacle', 'long_pocket'):
            with self.subTest(pocket=kind):
                floor = slab(-2, -1, 0, 1, -1.6 if kind == 'underpass' else -.3, 0.)
                end = .2 if kind == 'short' else 1.
                v, f = slab(0, -1, end, 1, -.3, 0.)
                v[:4, 2] = -(.4 if kind == 'long_pocket' else .96)*v[:4, 0]
                v[4:, 2] = -v[4:, 0]/6
                if kind == 'not_knife_edge': v[:4, 2] -= .02
                pieces = [floor, (v, f)]
                if kind == 'overhang': pieces = [(v, f)]
                if kind == 'gap':
                    pieces = [slab(-2, -1, 0, -.031, -.3, 0.),
                              slab(-2, -.026, 0, 1, -.3, 0.), (v, f)]
                self.assertEqual(len(C.crest_pockets(*C.weld(pieces),
                                                       obstacles={1} if kind == 'obstacle' else ())), 0)

    def test_lower_riding_space_preserves_the_entire_underside_patch(self):
        floor = slab(-2, -1, 0, 1, -.3, 0.)
        vertices, faces = slab(0, -1, .3, 1, -.3, 0.)
        vertices[:4, 2] = -.96*vertices[:4, 0]
        vertices[4:, 2] = -vertices[4:, 0]/6
        for depth in (.01, .4, 1., 2.):
            with self.subTest(lower_floor_depth=depth):
                # Even a narrow lower platform must be found between any fixed-spacing probes.
                lower = slab(.12, .031, .19, .036, -depth-.2, -depth)
                lower[0][:, 2] -= .96*lower[0][:, 0]
                removed = C.crest_pockets(*C.weld([floor, (vertices, faces), lower]))
                self.assertEqual(len(removed), 2 if depth <= C.ROLLABLE+C.WELD else 0)

    def test_a_steep_lower_riding_wall_preserves_the_ceiling(self):
        floor = slab(-2, -1, 0, 1, -.3, 0.)
        vertices, faces = slab(0, -1, .3, 1, -.3, 0.)
        vertices[:4, 2] = -.96*vertices[:4, 0]
        vertices[4:, 2] = -vertices[4:, 0]/6
        lower = slab(.12, .031, .14, .036, -.6, -.4)
        lower[0][:, 2] += np.tan(np.deg2rad(70))*(lower[0][:, 0]-.12)
        self.assertEqual(len(C.crest_pockets(*C.weld([floor, (vertices, faces), lower]))), 0)

    def test_partial_crest_coverage_keeps_both_halves_of_the_patch(self):
        floor = slab(-2, -1, 0, .5, -.3, 0.)
        vertices, faces = slab(0, -1, .3, 1, -.3, 0.)
        vertices[:4, 2] = -.96*vertices[:4, 0]
        vertices[4:, 2] = -vertices[4:, 0]/6
        self.assertEqual(len(C.crest_pockets(*C.weld([floor, (vertices, faces)]))), 0)

    def test_material_parts_share_one_piece_for_cap_coverage(self):
        parts = []
        for v, f in floor_tiles():
            parts.extend([(v, f[:4]), (v, f[4:])])
        _, _, _, report = C.riding_collision(parts, groups=[0, 0, 1, 1])
        self.assertEqual(report['buried_wall_triangles'], 4)


if __name__ == '__main__':
    unittest.main()
