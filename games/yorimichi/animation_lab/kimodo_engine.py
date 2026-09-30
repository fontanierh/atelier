"""Owned fox anatomy and placement policy for the shared headless Kimodo runner."""

import json
from pathlib import Path
from atelier.ai.kimodo import Engine as MotionEngine, retarget_motion

JOINT_MAP = {
    "Hips": "Hips",
    "Spine": "Spine1",
    "Spine1": "Spine2",
    "Spine2": "Chest",
    "Neck": "Neck1",
    "Head": "Head",
    "LeftUpLeg": "LeftLeg",
    "LeftLeg": "LeftShin",
    "RightUpLeg": "RightLeg",
    "RightLeg": "RightShin",
}
for side in ("Left", "Right"):
    for part in ("Shoulder", "Arm", "ForeArm", "Hand", "Foot", "ToeBase"):
        JOINT_MAP[side + part] = side + part


class Engine(MotionEngine):
    def __init__(self, root, device="cpu"):
        super().__init__(root, device)
        self.rig = json.loads((Path(root) / "assets/rig.json").read_text())

    def generate(
        self,
        prompt,
        seed,
        guidance=2.0,
        steps=100,
        progress=None,
        guided_sprint=False,
        frames=90,
    ):
        if guided_sprint:
            raise ValueError("Kimodo fox generation uses no authored constraints")
        output, provenance = super().generate(
            prompt, seed, guidance, steps, frames, progress
        )
        motion, diagnostics = retarget_motion(
            output,
            self.rig,
            self.model.output_skeleton,
            {name: JOINT_MAP[name.split(":")[-1]] for name in self.rig["names"]},
            foot_names=["mixamorig:LeftToeBase", "mixamorig:RightToeBase"],
            canonical_to_gltf=[0, 2**-0.5, 0, 2**-0.5],
        )
        provenance.update(
            diagnostics=diagnostics,
            conditioning_version="soma-canonical-to-fox-v1",
            source_sha256=self.rig["source_sha256"],
            joint_map=JOINT_MAP,
            retarget="canonical deltas, mapped parent folding, leg-height scale, constant floor offset",
        )
        return output, motion, provenance
