# GVHMR on macOS (experimental)

Pinned macOS port of [GVHMR](https://github.com/zju3dv/GVHMR) (SIGGRAPH Asia 2024): one video of one person in,
SMPL-X body motion out, in the camera frame and in a gravity-aligned world frame. Upstream targets NVIDIA GPUs; this
adapter runs every neural stage on Apple MPS. The motion output follows the same convention as the
[Kimodo](../kimodo/README.md) and [UniMate](../unimate/README.md) runners, so the shared
[retargeting helpers](../../../../web/motion/README.md) can apply it to a game rig.

**Licences.** GVHMR's code and weights are for non-commercial research only, and SMPL-X has its own non-commercial
licence. Neither is redistributed here. Using generated motion in a shipped product needs licences from both owners.

## Install

```sh
uv run python -m atelier.ai.gvhmr.install --root build/gvhmr --smplx /path/to/SMPLX_NEUTRAL.npz
```

The installer pins the upstream revision and applies `macos.patch` to it. It installs Python 3.11 dependencies tested
on macOS arm64, puts pytorch3d's pure-Python rotation transforms on the path (pytorch3d has no macOS wheel, and its
compiled operators are not needed for inference), and downloads about 5.6 GB of checkpoints. Upstream publishes them
on Google Drive, which cannot be fetched unattended, so they come from a revision-pinned Hugging Face mirror and every
file is checked against a SHA-256. The SMPL-X body model is never downloaded: register at
https://smpl-x.is.tue.mpg.de, download SMPL-X v1.1, and pass `SMPLX_NEUTRAL.npz` (or the folder holding it) as
`--smplx`. You can rerun the installer with `--smplx` alone later.

`macos.patch` replaces upstream's fixed `.cuda()` placement with a device chosen at run time (`HMR4D_DEVICE`, else
CUDA, else MPS, else CPU). It loads pytorch3d's compiled k-NN lazily, and passes HMR2 a contiguous crop because MPS
`conv2d` rejects the strided view. It also adapts SimpleVO to pycolmap 4, which reports an unsolvable frame pair
without a pose. DPVO (CUDA-only) and the pytorch3d mesh renderer are not ported: a moving camera
uses upstream's default SimpleVO, and the output is motion data, not a rendered video.

## Run

Run this with the installed environment's Python inside a memory-guarded process (`atelier.safety.guarded`):

```python
from atelier.ai.gvhmr import Engine, save
from atelier.ai.gvhmr.motion import body_motion, load_body_model

engine = Engine('build/gvhmr')
pred, provenance = engine.run('take.mp4', static_cam=True)
save(pred, provenance, 'build/gvhmr/takes/take')
motion = body_motion({k: v.numpy() for k, v in pred['smpl_params_global'].items()},
                     load_body_model('build/gvhmr/checkpoints/body_models/smplx/SMPLX_NEUTRAL.npz'))
```

| Option | Contract |
| --- | --- |
| `static_cam` | Required. `True` only for a locked-off camera; otherwise SimpleVO estimates camera rotation |
| `f_mm` | Full-frame equivalent focal length; upstream estimates one when omitted |
| `precision` | `fp32` (default) or `fp16` for the two ViT-H stages |
| `fused_attention` | Fused scaled-dot-product attention in both ViTs (default off) |
| `batch_size` | ViT batch, default 16 |
| `vo_workers` | SimpleVO matching threads, default 6 |

Upstream treats consecutive frames as 30 fps samples whatever the file's rate. Supply 30 fps footage for true timing;
`provenance.source_fps` records the file's own rate. The tracked person is the one with the largest summed box area.

`pred` holds upstream's `smpl_params_global` and `smpl_params_incam` (SMPL-X `global_orient`, `body_pose`, `transl`,
`betas`), the intrinsics, the person boxes, the ViTPose keypoints and the camera rotations. `body_motion` turns either
parameter set into the 22-joint motion dict: `names` and `parents` root first, `fps`, `frames`, per-frame xyzw
parent-relative rotation deltas, `root_positions`, `rest_root`, `rest_positions`, all `joint_positions`, the mean `betas`, and
`canonical_to_gltf`. It uses one body shape per take, the mean of GVHMR's per-frame betas. Hands, jaw and eyes are not
estimated.

## Performance

Measured on an M1 Max (32-core GPU, 32 GB) with PyTorch 2.5.1 on a 10-second, 300-frame 1600×1000 clip. The
neural stages run one after another; peak memory was 8.4 GB.

| Stage | Time |
| --- | --- |
| YOLOv8x person tracking | 17–24 s |
| Half-size decode and crops, once for both ViTs | under 1 s |
| ViTPose-H keypoints with flip test | 29–32 s |
| HMR2 ViT-H features | 15–17 s |
| SimpleVO, moving camera only (6 threads, alongside the GPU stages) | 1.5 s; 6.9 s on one thread |
| GVHMR transformer | not yet measured |

The defaults are the fastest settings that match upstream exactly. Their keypoints and features are identical to
upstream's own preprocessing. The alternatives were slower or barely faster:

- **fp16:** ViTPose is 20–25% slower. HMR2 is about 7% faster, with keypoints up to 1.3 px from upstream.
- **Fused attention:** slower in both ViTs.
- **Batch size:** batches of 32 or 64 are slower than 16.
- **Float16 YOLO:** no faster, and it moves boxes by up to 0.8 px.
- **PyTorch 2.14.1:** ViTPose drops from 8.5 to 5.9 frames per second, HMR2 from 14.0 to 12.7. Its bundled OpenMP
  runtime also conflicts with pycolmap's in the same process.

SimpleVO seeds its RANSAC, so camera rotations are reproducible for any worker count. When a frame pair has too few
matches to solve, it keeps the previous rotation, as older pycolmap releases did.

## Tests

The kinematics and attention tests need scipy and torch from the isolated environment, and the repository's
`uv run pytest` skips them without it:

```sh
build/gvhmr/venv/bin/python -m unittest discover -s platform/studio/tests -p 'test_gvhmr.py'
```
