# Local UniMate runner (experimental)

Pinned installation and inference for the released [UniMate](https://github.com/Friedrich-M/UniMate)
`unimate_uniml3d_f60_v2` model. This module accepts an explicit skeleton and returns features, canonical motion,
and provenance. Character export, anatomical naming, reference conversion, quality decisions, and the UI belong
with the caller. Motion quality varies by action and seed; inspect generated takes before accepting them.

## Install

Run from an Atelier checkout. Choose an ignored build directory for the model and its isolated environment:

```sh
uv run python -m atelier.ai.unimate.install --root build/motion-experiment
```

The installer pins the upstream revision, checkpoint repository revision, checkpoint SHA-256, inference dependencies,
and Motion decoder dependency. It installs Atelier into that environment without pulling heavy dependencies into
ordinary Atelier installs. The Flan-T5 encoder is revision-pinned and downloads on first model load. No API key or
training characters/motion dataset are required. The tested dependency set is macOS arm64/MPS; other backends need
compatible PyTorch wheels and their own validation. Use the platform memory guard when loading/running the model.

The installer exports no character assets. Upstream, model binaries, environment, and generated output stay in build
output. Upstream code and the released checkpoint are MIT licensed; training assets are not included.

## Supply a rig and generate

Run this code with the installed environment's Python, inside a memory-guarded process:

```python
import json
from pathlib import Path
from atelier.ai.unimate import Engine

root = Path('build/motion-experiment')
rig = json.loads((root / 'assets/rig.json').read_text())
# The exporter supplies clean_names using the selected upstream training vocabulary.
engine = Engine(root, rig, device='mps', normalization_key='mixamo',
                canonical_to_gltf=[0, 0, 0, 1], skeleton_name='owned-body')
features, motion, provenance = engine.generate(
    'A person does a backflip', seed=99, guidance=2, steps=32)
root.joinpath('results').mkdir(exist_ok=True)
engine.np.save(root / 'results/features.npy', features)
(root / 'results/motion.json').write_text(json.dumps(motion))
(root / 'results/provenance.json').write_text(json.dumps(provenance, indent=2))
```

`canonical_to_gltf` must describe the supplied export's axes; identity above applies only when they already match.
The runner does not infer anatomical labels or select normalization statistics from a character name.

| Rig field / option | Contract |
| --- | --- |
| `names` | Unique source bone names; these identify tracks on the target skin |
| `parents` | Connected tree, root index 0 with parent -1; every parent precedes its children |
| `positions` | Canonical world rest points, Y-up/+Z-forward, in metres; not local bone offsets |
| `clean_names` | One anatomical training label per joint, preserving the upstream vocabulary's capitalization |
| `source_sha256` | Optional owned-source hash, retained in provenance |
| `normalization_key` | Explicit key in the checkpoint's dataset statistics; `mixamo` is the tested humanoid key |
| `canonical_to_gltf` | Unit xyzw quaternion from canonical to target model world axes |
| `skeleton_name` | Caller-supplied topology identifier |
| `foot_joint_names` | Optional source names for foot-height diagnostics; no named feet are assumed |

The checkpoint limits joint count. The runner normalizes tree length, builds graph/spectral conditioning, embeds
joint labels and the prompt, samples the released EMA weights with a fixed midpoint flow ODE, and decodes rotations.
It changes padding sizes to the actual rig size without changing learned weights. Default device is MPS, falling
back to CPU when unavailable. `guidance` is 1.01–8, integer `steps` 8–64, and integer seeds 0–2147483647.
`progress(completed, total)` is an optional callback.

`features` has shape `(60, joints, 12)` before caller postprocessing. `motion` contains `names`, `parents`, `fps=30`,
`frames=60`, xyzw rotation deltas, canonical root positions, the rest root, and the explicit axis transform. The last
sample is at 1.967 seconds. Fingers outside the supplied body representation stay in their rest pose. No loop seam,
contact optimization, or quality guarantee is provided. Provenance records prompt/settings, vocabulary, source hash,
model/text/code revisions, checkpoint hash, backend, solver start time, elapsed time, and numerical diagnostics.

## Optional reference constraint

```python
from atelier.ai.unimate import MotionConstraint

# Caller-converted, unnormalized canonical features and one boolean lock per joint.
constraint = MotionConstraint(reference_features, locked_joints, start_time=.55)
features, motion, provenance = engine.generate(
    prompt, seed=99, guidance=2, steps=32, constraint=constraint)
```

The reference must have shape `(60, joints, 12)`. The mask locks complete joint feature slots to their reference
noise-to-motion path; other slots remain sampled. The caller owns source validation, gait/contact policy, any final
blend or loop, and provenance describing that postprocessing. This primitive is not a general motion-quality fix.

## Validation

```sh
.venv/bin/python -m unittest discover -s platform/studio/tests -p 'test_unimate.py'
```

Tests cover a differently named skeleton, explicit axes/vocabulary, invalid/disconnected/degenerate rig rejection,
constraint normalization/shape boundaries, and checksum failure without replacing an installed checkpoint. They
run without PyTorch or model weights. The character-independent [browser retargeter](../../../../web/motion/README.md)
accepts the caller's rest transforms and Three.js instance. Actual model/skin regression belongs with each caller.
