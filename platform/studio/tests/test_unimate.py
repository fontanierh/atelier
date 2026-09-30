"""Character-independent input boundaries and checksum-safe local installation."""
import hashlib
from pathlib import Path
import tempfile
import unittest

import numpy as np
from atelier.ai.unimate.inputs import MotionConstraint, validate_rig
from atelier.ai.unimate.install import download


class UniMateInputTests(unittest.TestCase):
    def setUp(self):
        self.rig = {'names': ['pelvis', 'limb', 'tip'], 'parents': [-1, 0, 1],
                    'positions': [[1, 2, 3], [1, 3, 3], [2, 3, 3]],
                    'clean_names': ['Hips', 'Spine', 'Head']}

    def test_custom_names_and_axis_are_explicit(self):
        rig = validate_rig(self.rig, [0, 0, 0, 1])
        self.assertEqual(rig, self.rig)
        self.assertIsNot(rig, self.rig)
        self.assertEqual(rig['clean_names'], ['Hips', 'Spine', 'Head'])

    def test_invalid_skeletons_fail_before_model_loading(self):
        for change in ({'parents': [-1, 2, 0]}, {'parents': [-1, -1, 1]},
                       {'names': ['pelvis', 'limb', 'limb']}, {'clean_names': ['Hips']},
                       {'positions': [[0, 0, 0]] * 3},
                       {'positions': [[0, 0, 0], [0, float('nan'), 0], [0, 1, 0]]}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_rig({**self.rig, **change}, [0, 0, 0, 1])
        with self.assertRaises(ValueError):
            validate_rig(self.rig, [0, 0, 0, 2])

    def test_reference_normalization_does_not_mutate_the_caller(self):
        features = np.full((60, 3, 12), 5, dtype=np.float32)
        known, keep = MotionConstraint(features, [True, False, True]).normalized(
            np.full((3, 12), 1), np.full((3, 12), 2))
        np.testing.assert_array_equal(known, np.full_like(features, 2))
        np.testing.assert_array_equal(features, np.full_like(features, 5))
        np.testing.assert_array_equal(keep, [True, False, True])

    def test_invalid_constraint_cannot_silently_broadcast(self):
        for constraint in (MotionConstraint(np.zeros((59, 3, 12)), [True] * 3),
                           MotionConstraint(np.zeros((60, 3, 12)), [True]),
                           MotionConstraint(np.zeros((60, 3, 12)), [1, 0, 1]),
                           MotionConstraint(np.zeros((60, 3, 12)), [True] * 3, 1)):
            with self.subTest(constraint=constraint), self.assertRaises(ValueError):
                constraint.normalized(np.zeros((3, 12)), np.ones((3, 12)))

    def test_bad_download_does_not_replace_an_installed_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / 'source', Path(directory) / 'checkpoint'
            source.write_bytes(b'wrong weights')
            target.write_bytes(b'previous checkpoint')
            with self.assertRaisesRegex(RuntimeError, 'Checksum mismatch'):
                download(source.as_uri(), target, hashlib.sha256(b'expected weights').hexdigest())
            self.assertEqual(target.read_bytes(), b'previous checkpoint')
            download(source.as_uri(), target, hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(target.read_bytes(), source.read_bytes())
