"""Check source SOMA FK and every rendered fox body joint for saved Kimodo takes."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import numpy as np

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root', type=Path, default=HERE.parents[2] / 'build/yorimichi/kimodo')
args = parser.parse_args()
root = args.root.resolve()
sys.path.insert(0, str(root / 'upstream'))
import torch
from kimodo.skeleton import SOMASkeleton77

skeleton = SOMASkeleton77()
rig = json.loads((root / 'assets/rig.json').read_text())
count = 0
for folder in (root / 'results').iterdir():
    source = folder / 'source-motion.npz'
    if not source.is_file():
        continue
    output = dict(np.load(source))
    rotations, positions, _ = skeleton.fk(torch.from_numpy(output['local_rot_mats']), torch.from_numpy(output['root_positions']))
    source_error = max(float(np.max(np.abs(rotations.numpy() - output['global_rot_mats']))),
        float(np.max(np.abs(positions.numpy() - output['posed_joints']))))
    if source_error > .00001:
        raise AssertionError(f'{folder.name}: inconsistent source SOMA FK ({source_error})')
    motion = json.loads((folder / 'motion.json').read_text())
    points = np.asarray(motion['positions']) + np.asarray(rig['canonical_center'])
    points = points[:, :, [2, 1, 0]]
    points[:, :, 2] *= -1
    (folder / 'expected-joints.json').write_text(json.dumps(points.tolist()))
    count += 1
if not count:
    raise SystemExit('Generate a Kimodo take first')
subprocess.run(['node', str(HERE / 'check_retarget.mjs'), str(root)], check=True)
