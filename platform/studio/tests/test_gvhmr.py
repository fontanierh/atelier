"""GVHMR install boundaries, SMPL-X body kinematics and fused ViT attention; model weights are never loaded."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np
from atelier.ai.gvhmr.install import BODY_MODEL, download, install_body_model


class InstallTests(unittest.TestCase):
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

    def test_body_model_comes_only_from_the_callers_registered_download(self):
        with tempfile.TemporaryDirectory() as directory:
            root, download_dir = Path(directory) / 'root', Path(directory) / 'models_smplx_v1_1/models'
            with self.assertRaisesRegex(FileNotFoundError, 'smpl-x.is.tue.mpg.de'):
                install_body_model(root, download_dir)
            (download_dir / 'smplx').mkdir(parents=True)
            (download_dir / 'smplx/SMPLX_NEUTRAL.npz').write_bytes(b'model')
            self.assertEqual(install_body_model(root, download_dir), hashlib.sha256(b'model').hexdigest())
            self.assertEqual((root / 'checkpoints' / BODY_MODEL).read_bytes(), b'model')


@unittest.skipUnless(importlib.util.find_spec('scipy'), 'requires scipy from the isolated GVHMR environment')
class BodyMotionTests(unittest.TestCase):
    def setUp(self):
        from atelier.ai.gvhmr.motion import NAMES, PARENTS

        self.names, self.parents = NAMES, PARENTS
        rng = np.random.default_rng(3)
        joints = rng.normal(size=(len(NAMES), 3))
        kintree = np.zeros((2, 55), dtype=np.int64)
        kintree[0, :len(NAMES)] = [2**32 - 1] + PARENTS[1:]  # SMPL-X files store the root's parent as uint32 -1
        self.model = {
            'v_template': joints,
            'shapedirs': np.zeros((len(NAMES), 3, 16)),
            'J_regressor': np.pad(np.eye(len(NAMES)), ((0, 55 - len(NAMES)), (0, 0))),
            'kintree_table': kintree,
        }
        self.joints = joints

    def params(self, frames=2, **pose):
        params = {'global_orient': np.zeros((frames, 3)), 'body_pose': np.zeros((frames, 63)),
                  'transl': np.zeros((frames, 3)), 'betas': np.zeros((frames, 10))}
        params.update(pose)
        return params

    def test_rest_pose_is_the_rest_skeleton_plus_translation(self):
        from atelier.ai.gvhmr.motion import body_motion

        motion = body_motion(self.params(transl=np.array([[0, 0, 0], [1, 2, 3]])), self.model)
        np.testing.assert_allclose(motion['joint_positions'][0], self.joints)
        np.testing.assert_allclose(motion['joint_positions'][1], self.joints + [1, 2, 3])
        np.testing.assert_allclose(motion['rotations'], np.tile([0, 0, 0, 1.0], (2, len(self.names), 1)), atol=1e-12)
        self.assertEqual(motion['root_positions'][1], (self.joints[0] + [1, 2, 3]).tolist())
        self.assertEqual((motion['names'][0], motion['canonical_to_gltf']), ('pelvis', [0, 0, 0, 1]))

    def test_rotations_are_parent_relative_and_move_only_the_subtree(self):
        from scipy.spatial.transform import Rotation
        from atelier.ai.gvhmr.motion import body_motion

        knee = self.names.index('left_knee')
        pose = np.zeros((1, 63))
        pose[0, (knee - 1) * 3:(knee - 1) * 3 + 3] = [np.pi / 2, 0, 0]
        motion = body_motion(self.params(1, global_orient=np.array([[0, np.pi / 2, 0]]), body_pose=pose), self.model)
        yaw, bend = Rotation.from_rotvec([0, np.pi / 2, 0]), Rotation.from_rotvec([np.pi / 2, 0, 0])
        positions, quats = np.array(motion['joint_positions'][0]), np.array(motion['rotations'][0])
        root = self.joints[0]
        for j, name in enumerate(self.names):
            expected = {'pelvis': yaw, 'left_knee': bend}.get(name, Rotation.identity())
            self.assertLess((Rotation.from_quat(quats[j]) * expected.inv()).magnitude(), 1e-9, name)
            if name not in ('left_ankle', 'left_foot'):
                np.testing.assert_allclose(positions[j], root + yaw.apply(self.joints[j] - root), atol=1e-12)
        ankle = self.names.index('left_ankle')
        np.testing.assert_allclose(
            positions[ankle], positions[knee] + (yaw * bend).apply(self.joints[ankle] - self.joints[knee]), atol=1e-12)

    def test_deltas_composed_like_the_retargeter_reproduce_the_joints(self):
        from scipy.spatial.transform import Rotation
        from atelier.ai.gvhmr.motion import body_motion

        rng = np.random.default_rng(5)
        motion = body_motion(self.params(3, global_orient=rng.normal(size=(3, 3)), body_pose=rng.normal(size=(3, 63)),
                                         transl=rng.normal(size=(3, 3))), self.model)
        rest = np.array(motion['rest_positions'])
        for f in range(3):
            # platform/web/motion/retarget.js: a bone's world delta is its parent's animated delta times its own.
            world = [None] * len(self.names)
            positions = np.empty_like(rest)
            for j, p in enumerate(self.parents):
                delta = Rotation.from_quat(motion['rotations'][f][j])
                world[j] = delta if p < 0 else world[p] * delta
                positions[j] = (motion['root_positions'][f] if p < 0
                                else positions[p] + world[p].apply(rest[j] - rest[p]))
            np.testing.assert_allclose(positions, motion['joint_positions'][f], atol=1e-9)

    def test_shape_uses_the_mean_betas(self):
        from atelier.ai.gvhmr.motion import body_motion

        self.model['shapedirs'][:, 1, 0] = 1
        motion = body_motion(self.params(betas=np.array([[0.2] + [0] * 9, [0.4] + [0] * 9])), self.model)
        np.testing.assert_allclose(motion['rest_positions'], self.joints + [0, 0.3, 0])

    def test_a_non_smplx_hierarchy_is_refused(self):
        from atelier.ai.gvhmr.motion import body_motion

        self.model['kintree_table'][0, 4] = 2
        with self.assertRaisesRegex(ValueError, 'not SMPL-X'):
            body_motion(self.params(), self.model)


@unittest.skipUnless(importlib.util.find_spec('torch'), 'requires torch from the isolated GVHMR environment')
class FusedAttentionTests(unittest.TestCase):
    def test_matches_upstream_vit_attention(self):
        import torch
        from types import SimpleNamespace
        from atelier.ai.gvhmr.engine import fused_attention

        torch.manual_seed(0)
        dim, heads = 64, 4
        module = SimpleNamespace(qkv=torch.nn.Linear(dim, dim * 3), proj=torch.nn.Linear(dim, dim), num_heads=heads,
                                 scale=(dim // heads) ** -0.5)
        x = torch.randn(2, 10, dim)
        # Upstream Attention.forward (hmr4d/network/hmr2/vit.py) at inference.
        B, N, C = x.shape
        q, k, v = module.qkv(x).reshape(B, N, 3, heads, -1).permute(2, 0, 3, 1, 4)
        reference = module.proj((((q * module.scale) @ k.transpose(-2, -1)).softmax(-1) @ v).transpose(1, 2)
                                .reshape(B, N, -1))
        torch.testing.assert_close(fused_attention(module, x), reference, atol=1e-6, rtol=1e-5)


if __name__ == '__main__':
    unittest.main()
