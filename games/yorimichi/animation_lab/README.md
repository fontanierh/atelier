# Fox motion lab

A local UniMate experiment on Yorimichi’s fox hunter, with a live 3D gallery and a prompt box.
Open **http://127.0.0.1:8842** while the server is running.

The gallery contains the fox’s 15 authored clips, eight generated attack/movement experiments, and saved custom
prompts. Select a take, orbit the textured character, scrub or slow playback, show the rig, compare against an
authored reference, or export the animated fox as GLB. The small camera button saves a pose PNG. Exports also
remain in the ignored build directory.

## Setup and run

From the repository root, with `uv`, Node and Blender on PATH:

```sh
uv sync
uv run python games/yorimichi/animation_lab/setup.py
uv run python -m atelier.safety.guarded --no-lock \
  --report build/yorimichi/unimate/server-health --timeout 0 \
  --purpose 'local UniMate motion lab' -- \
  build/yorimichi/unimate/venv/bin/python games/yorimichi/animation_lab/server.py
```

Setup downloads about 1.2 GB of checkpoint weights into `build/yorimichi/unimate/model`, installs a separate
Python 3.11 inference environment, exports the owned fox skin and original clips, and bundles the viewer. The frozen
Flan-T5 encoder downloads on the first server launch. Model startup is visible in the UI. Press **Generate missing
experiments** to fill the eight preset slots; custom prompts generate a single take. Change the seed for another
variation of the same prompt. All requests stay on loopback, and only one inference runs at a time.

The Mac uses PyTorch MPS. `server.py --device cpu` provides an explicit CPU option; CUDA is also accepted if using a
compatible installation. No paid API is used. The server and the small non-rendering Blender export use the memory
guard without taking the render slot; they do not launch Unreal or render Blender frames. Keep the server’s 10 GiB
memory guard enabled.

After changing the frontend, run `npm run --prefix games/yorimichi/animation_lab build` and reload the page.

## Experiment, September 30, 2026

Ran the recommended [UniMate f60 v2 checkpoint](https://huggingface.co/Linzhan/UniMate), EMA step 100000, directly on
our own unseen fox topology. All eight presets used guidance 3 and 32 fixed midpoint ODE steps:

| Prompt experiment | Seed | Inference |
| --- | ---: | ---: |
| Diagonal claw | 42 | 13.40 s |
| Double strike | 117 | 12.15 s |
| Roundhouse kick | 73 | 12.08 s |
| Low sweep | 204 | 12.11 s |
| Forward sprint | 19 | 12.23 s |
| Lateral dodge | 89 | 12.26 s |
| Retreating steps | 312 | 12.10 s |
| Jump & land | 56 | 12.21 s |

Also submitted a custom “raise a guard, duck, then step forward with a left jab” prompt through the UI with seed 0:
12.10 s. It persisted across reload and exported as an animated, skinned GLB.

These are motion sketches for review. The prompts name the requested action; the checkpoint does not guarantee the
whole requested sequence. Contact, floating feet, body intersections, and recovery can need correction. The sampler
produces 60 frames at 30 fps (the final sample is at 1.967 seconds), and the clips have no synthesized loop seam.
Fingers keep their rest pose. The viewport centers horizontal root travel for inspection; the displayed travel
distance and exported GLB retain the motion. The results have not been accepted into the gameplay library.

Retarget validation compared every joint at every frame against upstream UniMate forward kinematics: **11,880 joint
samples** across nine takes, maximum error **0.00075 mm** in the source mesh’s world units. This establishes the
conversion’s accuracy, not the model’s motion quality. The first batch’s inference process peaked at about 3.3 GiB
under the existing 10 GiB guard.

## How it works

`export_rig.py` keeps the complete 53-bone skin and exports the 22 anatomical body joints used for generation.
It converts the fox’s +X-forward/Z-up rest pose to UniMate’s +Z-forward/Y-up coordinates. `engine.py` canonicalizes
bone lengths to the training convention, builds upstream graph/spectral conditioning, uses the released humanoid
normalization statistics and Flan-T5 joint/prompt embeddings, and samples the EMA model. Two upstream fixed padding
sizes are set to the actual joint count for compact spectral attention; no learned weights are changed.

`retarget.js` conjugates those canonical rotation deltas into each original bone’s rest frame, converts root
translation, and builds an animation clip on the original skin. Quaternion signs are made continuous before glTF
interpolation. The original finger bones and source blend are preserved.

`server.py` keeps the model warm, validates prompts/seeds/steps, serializes jobs, reports progress, and saves each
take to `build/yorimichi/unimate/results/<id>/`. Every take includes raw `features.npy`, the browser motion, job state,
and provenance with prompt, seed, guidance, solver, step count, device, elapsed time, checkpoint hash, upstream
revision, text encoder revision, and rig source hash. The viewer only serves explicitly allowed files; checkpoints,
credentials and the rest of the repository are outside its file routes. A running batch can be continued after a
reload by pressing “Generate missing experiments” again.

The [upstream code](https://github.com/Friedrich-M/UniMate) and checkpoint are MIT licensed. No UniML3D character,
Mixamo download, or Truebones motion is downloaded or redistributed. The fox is an owned asset. Upstream code,
weights, generated takes, captures and exports stay in ignored build output.

## Verification

```sh
.venv/bin/python -m unittest discover -s games/yorimichi/animation_lab -p 'test_*.py'
build/yorimichi/unimate/venv/bin/python games/yorimichi/animation_lab/verify.py
.venv/bin/atelier lint
```

The server tests cover numeric validation, seed zero, failed-job cleanup, origin/host restrictions, and file
boundaries. `verify.py` recovers upstream FK from the actual saved features and checks all frames against the same
Three.js retargeter used by the viewer. Browser verification covered generation through the prompt form, reload
persistence, playback/scrubbing, comparisons, rig overlays, filtering and GLB export.
