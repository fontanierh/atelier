"""Recover upstream FK and verify the browser retarget numerically for every saved take."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument('--root', type=Path, default=HERE.parents[2] / 'build/yorimichi/unimate')
args = ap.parse_args()
root = args.root.resolve()
sys.path.insert(0, str(root / 'upstream'))
import numpy as np
from scipy.sparse.csgraph import shortest_path
from unimate.utils.motion_utils import recover_unimate_anim_from_rot
from Animation import positions_global
rig = json.loads((root / 'assets/rig.json').read_text())
points = np.array(rig['positions'])
parents = rig['parents']
n = len(parents)
dist = np.full((n, n), np.inf)
np.fill_diagonal(dist, 0)
for j, p in enumerate(parents):
    if p >= 0:
        dist[j, p] = dist[p, j] = np.linalg.norm(points[j] - points[p])
scale = 2 / shortest_path(dist, directed=False).max()
floor = points[:, 1].min()
points *= scale
points[:, 1] -= points[:, 1].min()
offsets = points.copy()
for j, p in enumerate(parents):
    if p >= 0:
        offsets[j] -= points[p]
count = 0
for folder in (root / 'results').glob('*'):
    if not (folder / 'features.npy').exists():
        continue
    motion = json.loads((folder / 'motion.json').read_text())
    if motion.get('guided'):
        from Animation import Animation
        from Quaternions import Quaternions
        q = np.array(motion['rotations'])[:, :, [3, 0, 1, 2]]
        translations = np.tile(offsets, (motion['frames'], 1, 1))
        translations[:, 0] = np.array(motion['root_positions']) * scale
        anim = Animation(Quaternions(q), translations, Quaternions.id(n), offsets, parents)
        positions = positions_global(anim) / scale
        reference = json.loads((root / 'assets/run-reference.json').read_text())
        cycle = reference['cycle_frames']
        expected = np.array(reference['positions'])[:cycle]
        expected = np.concatenate([expected, expected[:1]])
        preserved = [j for j, name in enumerate(rig['names']) if not any(part in name for part in ('Shoulder', 'Arm', 'Hand'))]
        gait_error = np.abs(positions[:, preserved] - expected[:, preserved]).max()
        if gait_error > .0001:
            raise AssertionError(f'{folder.name}: guided sprint changed the authored gait by {gait_error} m')
        if motion['rotations'][0] != motion['rotations'][-1] or motion['root_positions'][0] != motion['root_positions'][-1]:
            raise AssertionError(f'{folder.name}: sprint loop does not close')
        if (motion['frames'] - 1) / motion['fps'] != reference['period']:
            raise AssertionError(f'{folder.name}: sprint cadence differs from the original')
        print(f'{folder.name}: preserved sprint gait, max error {gait_error * 1000:.5f} mm; closed {reference["period"]}s loop')
    else:
        anim = recover_unimate_anim_from_rot(np.load(folder / 'features.npy'), parents, offsets)
        positions = positions_global(anim) / scale
        positions[:, :, 1] += floor
    positions += np.array(rig['canonical_center'])
    positions = positions[:, :, [2, 1, 0]]
    positions[:, :, 2] *= -1
    (folder / 'expected-joints.json').write_text(json.dumps(positions.tolist()))
    count += 1
if not count:
    raise SystemExit('Generate at least one take before running verification')
subprocess.run(['node', str(HERE / 'check_retarget.mjs'), str(root)], check=True)
