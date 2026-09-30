"""Fox inputs and authored-sprint policy around the shared UniMate runner."""
import json
from pathlib import Path

from atelier.ai.unimate import Engine as MotionEngine, MotionConstraint
from guided import make_sprint_loop, reference_features


class Engine(MotionEngine):
    def __init__(self, root, device='mps'):
        # Export, anatomical labels, orientation, and diagnostics belong to this rig.
        import sys
        sys.path.insert(0, str(Path(root).resolve() / 'upstream'))
        from data_process.joint_annotation.names_clean_rule import clean_joint_name, post_process
        rig = json.loads((Path(root) / 'assets/rig.json').read_text())
        rig['clean_names'] = [post_process(clean_joint_name(name, 'mixamo')) for name in rig['names']]
        super().__init__(root, rig, device, normalization_key='mixamo', skeleton_name='FoxHunter',
            canonical_to_gltf=[0, 2**-0.5, 0, 2**-0.5],
            foot_joint_names=['mixamorig:LeftToeBase', 'mixamorig:RightToeBase'])

    def generate(self, prompt, seed, guidance=3.0, steps=32, progress=None, guided_sprint=False):
        reference, constraint = None, None
        if guided_sprint:
            reference = json.loads((self.root / 'assets/run-reference.json').read_text())
            if reference['source_sha256'] != self.rig['source_sha256'] or reference['names'] != self.rig['names']:
                raise ValueError('Run reference does not match the exported fox rig; rerun setup')
            known, keep, reference_error = reference_features(reference, self.rig, self.scale, self.floor_offset)
            constraint = MotionConstraint(known, keep)
        features, motion, provenance = super().generate(prompt, seed, guidance, steps, progress, constraint)
        if reference:
            motion = make_sprint_loop(motion, reference)
            provenance['diagnostics'].update(root_travel_m=0., reference_fk_error_m=reference_error,
                review='near-copy sprint experiment: authored gait with bounded UniMate arm changes')
        provenance.update(guided=motion.get('guided'), reference_clip=motion.get('reference_clip'))
        return features, motion, provenance
