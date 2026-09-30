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
