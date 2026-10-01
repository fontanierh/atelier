"""The conventions files parse and say what the code expects."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from atelier import conventions, paths


class ConventionTests(unittest.TestCase):
    def test_units(self):
        self.assertEqual(conventions.to_unreal((1.0, 2.0, 3.0)), (100.0, -200.0, 300.0))
        self.assertEqual(conventions.yaw_to_unreal(30.0), -30.0)

    def test_humanoid_core(self):
        bones = conventions.required_bones()
        self.assertEqual(len(bones), 23)
        self.assertEqual(len(set(bones)), 23)
        for role, bone in conventions.humanoid()['roles'].items():
            self.assertIn(bone, bones, role)
        fingers = conventions.humanoid()['optional']['fingers']
        self.assertEqual(len(fingers['per_hand']) * len(fingers['suffixes']), 30)

    def test_clip_roles(self):
        roles = conventions.clip_roles()
        self.assertTrue(roles['SwordAttack1']['root_motion'])
        self.assertFalse(roles['Walk']['root_motion'])

    def test_repo_layout(self):
        self.assertTrue((paths.REPO / 'ARCHITECTURE.md').is_file())
        self.assertEqual(paths.CONVENTIONS, paths.REPO / 'platform/conventions')


if __name__ == '__main__':
    unittest.main()
