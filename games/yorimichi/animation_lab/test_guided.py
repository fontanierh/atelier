"""Quality contracts for the published hybrid loop, without running inference."""
import unittest
import numpy as np
from guided import bounded_blend, make_sprint_loop


class GuidedSprintTests(unittest.TestCase):
    def test_large_model_deflection_is_bounded(self):
        original = [0., 0., 0., 1.]
        generated = [1., 0., 0., 0.]
        result = bounded_blend(original, generated, .35)
        angle = np.rad2deg(2 * np.arccos(abs(result[3])))
        self.assertAlmostEqual(angle, 6.3, places=6)
        np.testing.assert_allclose(np.linalg.norm(result), 1.)
        np.testing.assert_allclose(bounded_blend(original, [0, 0, 0, 0], .35), original)

    def test_generated_arms_cannot_change_stride_or_hand_detail(self):
        names = ['mixamorig:Hips', 'mixamorig:LeftLeg', 'mixamorig:LeftArm']
        original = np.tile([0., 0., 0., 1.], (7, 3, 1)).tolist()
        raw = np.tile([1., 0., 0., 0.], (6, 3, 1)).tolist()
        reference = {'cycle_frames': 2, 'fps': 30, 'rotations': original,
                     'positions': np.zeros((7, 3, 3)).tolist(), 'reference_clip': 'Fox_Run',
                     'travel_speed': 3., 'detail_tracks': {'mixamorig:LeftHand': original[0]}}
        result = make_sprint_loop({'names': names, 'rotations': raw}, reference)
        np.testing.assert_array_equal(np.array(result['rotations'])[:, :2], np.tile([0, 0, 0, 1], (3, 2, 1)))
        self.assertGreater(abs(result['rotations'][0][2][0]), .01)
        self.assertEqual(result['rotations'][0], result['rotations'][-1])
        self.assertEqual(result['root_positions'][0], result['root_positions'][-1])
        self.assertEqual(result['local_tracks']['mixamorig:LeftHand'][0], reference['detail_tracks']['mixamorig:LeftHand'][0])


if __name__ == '__main__':
    unittest.main()
