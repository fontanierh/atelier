# Fox motion lab

A local UniMate experiment on Yorimichi’s fox hunter, with a live 3D gallery and a prompt box.
Open **http://127.0.0.1:8842** while the server is running.

**Compare originals** is the default workflow. Pick one of the fox’s 15 authored clips, then choose its generated
counterpart. Two opaque, textured characters share playback and scrubbing, with **Original**, **Prompt only**, or
**Hybrid** source labels. Match phase, slow playback, isolate either character, show the rig, or export the selected
animation as GLB. The camera button saves a labeled pose PNG. Exports remain in the ignored build directory.

**Create new motion** has a separate library and a name/prompt/seed form for independent, prompt-only animations.
Comparison takes stay attached to their chosen original; standalone takes remain independent across reloads.
The eight preset prompts are available in this creation workflow.

The forward sprint has a **Keep the authored sprint gait** option. It produces a hybrid: the original stride,
contacts, root, torso, head, and local hand/finger detail, with bounded UniMate shoulder/arm variation. Turn the
option off to compare a fully prompt-generated body motion. A hybrid is deliberately a modest variation of an
existing good gait; it does not demonstrate that unconstrained UniMate matches the original’s quality.

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
Python 3.11 inference environment, exports the owned fox skin and original clips, samples the authored Run reference,
and bundles the viewer. Rerun setup to create that reference when upgrading an older installation. The frozen Flan-T5
encoder downloads on the first server launch. Model startup is visible in the UI. **Generate missing experiments**
fills the standalone preset slots; either prompt form generates a single take. Change the seed for another variation.
All requests stay on loopback, and only one inference runs at a time.

The Mac uses PyTorch MPS. `server.py --device cpu` provides an explicit CPU option; CUDA is also accepted if using a
compatible installation. No paid API is used. The server and the small non-rendering Blender export use the memory
guard without taking the render slot; they do not launch Unreal or render Blender frames. Keep the server’s 10 GiB
memory guard enabled.

After changing the frontend, run `npm run --prefix games/yorimichi/animation_lab build` and reload the page.

## Experiment, September 30, 2026

Uses the recommended [UniMate f60 v2 checkpoint](https://huggingface.co/Linzhan/UniMate), EMA step 100000, on our own
unseen fox topology. The first attack/movement experiments were weak. Investigation found a conditioning bug:
hand-written lowercase joint labels did not match the training vocabulary. The engine now uses upstream’s actual
name cleaning (`Left Thigh`, `Left Shin`, `Left Upper Arm`, `Spine`, etc.). New provenance records
`canonical-names-v2`; older takes remain available with an **earlier conditioning** label.

Corrected names and a short sprint prompt improved the raw gait, but it still fell below the authored Run in visual
quality. The constrained sprint was then checked against that source:

| Sprint experiment | Seed | Inference | Result |
| --- | ---: | ---: | --- |
| Prompt only, corrected names | 10 | 10.34 s | Recognizable running; contacts, hands, and seam still need work |
| Prompt only, corrected names | 19 | 10.02 s | Similar limitations |
| Guided hybrid | 10 | 11.97 s | Original gait with up to 4.2° arm variation |
| Guided hybrid, generated through UI | 117 | 19.45 s | Original gait with up to 3.7° arm variation |
| Independent prompt only, generated through UI | 99 | 13.15 s | Saved in the standalone library |

These runs used guidance 2 and 32 fixed midpoint steps. Both hybrids preserve the original **0.6-second** cycle and
its in-place speed (5.91 m/s at the viewer’s display scale). Independent FK verification measured a maximum
**0.00053 mm** deviation in preserved body joints. Exported hybrid GLBs retain all **53 skin bones**, **53 animation
channels**, and identical first/last transforms. This establishes preservation of the owned gait, not raw-model quality.

Raw generation still produces 60 frames at 30 fps (last sample at 1.967 seconds), with no synthesized loop seam and
rest-pose fingers. Guided output contains 18 unique frames plus the closing endpoint, and copies authored wrist/finger
tracks. The viewport centers horizontal root travel for inspection; prompt-only travel distances and exported GLBs
retain the motion. None of these experiments has replaced a gameplay animation.

Retarget verification covered **23,276 body-joint samples**, maximum error **0.00088 mm** in source mesh world units.
That measures conversion accuracy. Prompt adherence, balance, contacts, and recovery still require visual review.

## How it works

`export_rig.py` keeps the complete 53-bone skin and exports the 22 anatomical body joints used for generation.
It converts the fox’s +X-forward/Z-up rest pose to UniMate’s +Z-forward/Y-up coordinates. `engine.py` canonicalizes
bone lengths to the training convention, builds upstream graph/spectral conditioning, uses the released humanoid
normalization statistics and Flan-T5 joint/prompt embeddings, and samples the EMA model. Two upstream fixed padding
sizes are set to the actual joint count for compact spectral attention; no learned weights are changed.

`export_reference.mjs` samples the owned Run clip, restoring the duplicate endpoint at its manifest period.
`guided.py` validates its source-to-model FK conversion, adds the manifest’s virtual forward travel for conditioning,
and leaves six arm-related feature slots free. Guided inference starts at flow time 0.55 and clamps the remaining
slots to the reference’s noise-to-motion path. The published loop keeps the source gait, averages generated arm
rotations by gait phase, and blends them at strength 0.35 with an 18° input cap (at most 6.3° final change per joint).
This constraint and blend are specific to the current owned sprint, rather than a general contact solver.

`retarget.js` conjugates those canonical rotation deltas into each original bone’s rest frame, converts root
translation, and builds an animation clip on the original skin. Quaternion signs are made continuous before glTF
interpolation. The original finger bones and source blend are preserved.

`server.py` keeps the model warm, validates prompts/seeds/steps, serializes jobs, reports progress, and saves each
take to `build/yorimichi/unimate/results/<id>/`. Every take includes raw `features.npy`, the browser motion, job state,
and provenance with prompt, seed, guidance, solver, step count, flow start time, device, elapsed time, checkpoint hash,
upstream revision, text encoder revision, joint vocabulary, and rig source hash. Guided provenance also records the
reference and blend. Its raw 60-frame features precede the published 19-frame loop and are retained for inspection.
The viewer only serves explicitly allowed files; checkpoints, credentials and the rest of the repository are outside
its file routes. A preset batch can be continued after a reload with **Generate missing experiments**.

The [upstream code](https://github.com/Friedrich-M/UniMate) and checkpoint are MIT licensed. No UniML3D character,
Mixamo download, or Truebones motion is downloaded or redistributed. The fox is an owned asset. Upstream code,
weights, generated takes, captures and exports stay in ignored build output.

## Verification

```sh
.venv/bin/python -m unittest discover -s games/yorimichi/animation_lab -p 'test_*.py'
build/yorimichi/unimate/venv/bin/python games/yorimichi/animation_lab/verify.py
.venv/bin/atelier lint
```

Eight tests cover numeric validation, seed zero, failed-job cleanup, origin/host restrictions, file boundaries,
comparison persistence, guided request restrictions, bounded arm changes, and loop closure. `verify.py` recovers FK
from actual saved features for raw takes and from the published loop for hybrids; it also checks the preserved gait
against independently sampled source positions. All frames are checked against the viewer’s Three.js retargeter.
Browser verification covered both generation forms, library grouping, reload persistence, comparisons, playback,
scrubbing, filtering, and GLB export.
