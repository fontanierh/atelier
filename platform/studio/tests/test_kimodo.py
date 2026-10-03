"""Retargeting boundaries; real LoRA loader parity in the isolated Kimodo env."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
import numpy as np
from atelier.ai.kimodo import retarget_motion


class ArrayTensor:
    def __init__(self, value):
        self.value = np.asarray(value)

    def cpu(self):
        return self

    def numpy(self):
        return self.value


@unittest.skipUnless(
    importlib.util.find_spec("scipy"), "requires scipy from the isolated Kimodo environment"
)
class RetargetTests(unittest.TestCase):
    def setUp(self):
        from types import SimpleNamespace

        self.skeleton = SimpleNamespace(
            bone_index={"hips": 0, "extra": 1, "head": 2, "toe": 3},
            root_idx=0,
            neutral_joints=ArrayTensor(
                [[0, 0, 0], [0, 0.1, 0], [0, 0.2, 0], [0, -1, 0]]
            ),
        )
        self.rig = {
            "names": ["root", "head", "toe"],
            "parents": [-1, 0, 0],
            "positions": [[0, 0.5, 0], [0, 0.7, 0], [0, 0.05, 0]],
        }
        self.mapping = {"root": "hips", "head": "head", "toe": "toe"}

    def transfer(self, output, rig=None):
        return retarget_motion(
            output,
            rig or self.rig,
            self.skeleton,
            self.mapping,
            foot_names=["toe"],
            canonical_to_gltf=[0, 0, 0, 1],
        )

    def test_source_only_joint_is_folded_and_root_is_scaled(self):
        from scipy.spatial.transform import Rotation

        rotations = np.tile(np.eye(3), (2, 4, 1, 1))
        rotations[:, 2] = Rotation.from_euler("z", 90, degrees=True).as_matrix()
        output = {
            "global_rot_mats": rotations,
            "root_positions": np.array([[1, 1, 2], [2, 1, 2.0]]),
        }
        motion, diagnostics = self.transfer(output)
        np.testing.assert_allclose(
            motion["root_positions"], [[0, 0.5, 0], [0.45, 0.5, 0]], atol=1e-7
        )
        np.testing.assert_allclose(
            Rotation.from_quat(motion["rotations"][0][1]).as_matrix(),
            rotations[0, 2],
            atol=1e-7,
        )
        np.testing.assert_array_equal(output["root_positions"], [[1, 1, 2], [2, 1, 2]])
        self.assertAlmostEqual(diagnostics["scale"], 0.45)

    def test_full_rotation_keeps_the_airborne_phase(self):
        from scipy.spatial.transform import Rotation

        rotations = np.tile(np.eye(3), (5, 4, 1, 1))
        rotations[:, 0] = Rotation.from_euler(
            "x", np.asarray([0, 90, 180, 270, 360])[:, None], degrees=True
        ).as_matrix()
        motion, diagnostics = self.transfer(
            {"global_rot_mats": rotations, "root_positions": np.tile([0, 1, 0], (5, 1))}
        )
        self.assertAlmostEqual(diagnostics["hip_rotation_degrees"], 360)
        self.assertAlmostEqual(diagnostics["foot_clearance_max_m"], 0.9)

    def test_invalid_hierarchy_fails(self):
        output = {
            "global_rot_mats": np.tile(np.eye(3), (1, 4, 1, 1)),
            "root_positions": np.array([[0, 1, 0]]),
        }
        with self.assertRaisesRegex(ValueError, "parents"):
            self.transfer(output, {**self.rig, "parents": [-1, 2, 0]})


@unittest.skipUnless(
    importlib.util.find_spec("kimodo"), "requires isolated Kimodo environment"
)
class StreamingTests(unittest.TestCase):
    def test_published_adapter_names_and_stream_match_full_peft_model(self):
        import torch
        from peft import get_peft_model, LoraConfig
        from transformers import LlamaConfig
        from kimodo.model.llm2vec.models.bidirectional_llama import LlamaBiModel
        from atelier.ai.kimodo.streamed_text import Adapter, run_layers

        torch.manual_seed(11)
        config = LlamaConfig(
            hidden_size=32,
            intermediate_size=64,
            num_hidden_layers=3,
            num_attention_heads=4,
            num_key_value_heads=2,
            vocab_size=100,
            pad_token_id=0,
        )
        config._attn_implementation = "sdpa"
        model = LlamaBiModel(config).eval()
        original = {key: value.clone() for key, value in model.state_dict().items()}
        adapters = []
        with tempfile.TemporaryDirectory() as directory:
            for index in range(2):
                model = get_peft_model(
                    model,
                    LoraConfig(
                        r=2,
                        lora_alpha=4,
                        target_modules=[
                            "q_proj",
                            "k_proj",
                            "v_proj",
                            "o_proj",
                            "gate_proj",
                            "up_proj",
                            "down_proj",
                        ],
                    ),
                )
                for name, param in model.named_parameters():
                    if "lora_" in name:
                        torch.nn.init.normal_(param, std=0.025)
                path = Path(directory) / str(index)
                model.save_pretrained(path)
                adapters.append(Adapter(path))
                if index == 0:
                    model = model.merge_and_unload()
            self.assertGreater(
                adapters[0]
                .delta("model.layers.0.self_attn.q_proj.weight")
                .abs()
                .max()
                .item(),
                0,
            )
            ids = torch.tensor([[1, 2, 5, 6, 10]])
            with torch.inference_mode():
                expected = model(
                    ids, attention_mask=torch.zeros((1, 1, 5, 5)), use_cache=False
                ).last_hidden_state
                actual = run_layers(
                    config,
                    lambda key: original[key.removeprefix("model.")].clone(),
                    adapters,
                    original["embed_tokens.weight"][ids],
                    "cpu",
                    lambda message: None,
                )
            torch.testing.assert_close(actual, expected, atol=2e-6, rtol=2e-6)

    def test_missing_expected_adapter_cannot_be_silently_skipped(self):
        import json
        import torch
        from safetensors.torch import save_file
        from atelier.ai.kimodo.streamed_text import Adapter

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "adapter_config.json").write_text(
                json.dumps({"target_modules": ["q_proj"], "r": 2, "lora_alpha": 4})
            )
            save_file({"unrelated": torch.zeros(1)}, path / "adapter_model.safetensors")
            with self.assertRaisesRegex(ValueError, "Missing adapter tensor"):
                Adapter(path).delta("model.layers.0.self_attn.q_proj.weight")


if __name__ == "__main__":
    unittest.main()
