# UniMate on the fox hunter

[UniMate](../../../platform/studio/atelier/ai/unimate/README.md) is a released text-to-motion model that works on any
skeleton: given the rig's joint tree, an anatomical label per joint and a prompt, it generates two seconds of motion
for that rig, locally and in about 10 to 20 seconds. The fox motion lab runs it on the fox hunter's own rig and shows
the result next to the authored clips. It can produce useful **new, prompt-only** animations (a backflip on the fox
is good enough to keep as a candidate), but quality depends on the action and the seed: many attacks and movements
look poor, and prompt-only sprints stay well below the authored Run. Use it to generate candidates, keep the useful
ones, and reject or author the rest. Generated motion never replaces a game clip automatically.

<p align="center">
  <img src="../../../docs/media/unimate-backflip.gif" width="640" alt="The fox hunter performs a prompt-only UniMate backflip, jumping, rotating backwards, landing and recovering">
</p>

The backflip: `A person does a backflip`, seed **99**, guidance **2**, **32** steps, no authored reference, 11.6
seconds of inference with a warm model. The GIF shows the saved take at 30 fps with a fixed camera; the viewer centres
horizontal travel, while the exported animation keeps the root motion. It repeats the two-second take with a visible
restart, not a generated loop. Its [provenance](../../../docs/media/unimate-backflip.json) records the take ID,
settings, hashes and capture details.

## Run it

Install and start the shared playground from the [lab guide](../animation_lab/README.md). To reproduce the backflip,
select **Create new motion**, enter `A person does a backflip`, set seed **99**, guidance **2** and steps **32**, and
generate; the [HTTP example](../animation_lab/README.md#generate-through-the-shared-http-api) sends the same request
with `"generator": "unimate"`. **Preview GIF** captures a selected take the way the GIF above was made. Generated takes
stay in the ignored `build/yorimichi/unimate/`; a fresh checkout has none until it runs setup and generates.

Every take records its settings, vocabulary, solver, flow start time, reference use, backend, source hash and model
and text-encoder revisions. A seed fixes the initial noise, but results can differ across hardware.

## Inputs

The source is [`FoxHunter-Anim-r05.blend`](../assets/characters/fox-hunter/FoxHunter-Anim-r05.blend): **53 skin
bones**, **22 anatomical body joints** for generation, and **15 authored clips** for comparison. Run cadence and
travel speed come from its [manifest](../assets/characters/fox-hunter/manifest.json).

| Input | Pinned value |
| --- | --- |
| UniMate code | `5d6aabedd947297b5ba6706d8e9113e68c0c3e4f` |
| Checkpoint | `unimate_uniml3d_f60_v2`, EMA step 100000 |
| Checkpoint repository revision | `387a344c3031299bc25fcbef35d36bd186d5afe7` |
| Checkpoint SHA-256 | `cbcfb7a057e45f967d5964fecf6b3f83358096f1306f25831e1644a18a50eb34` |
| Flan-T5 revision | `7bcac572ce56db69c1ea7c8af255c5d7c9672fc2` |
| Fox source SHA-256 | `8103d0bf2c970d4adcd6d9af32f109e376b29433b3cc3597387efd75a3a6219c` |
| Solver | fixed midpoint flow ODE; the recipes use guidance 2 and 32 steps |
| Tested backend | PyTorch MPS on macOS arm64; local inference, no paid API |

## How it runs

`export_rig.py` keeps the full skin and exports canonical +Z-forward, Y-up body points from the fox's +X-forward, Z-up
source. The shared engine normalises tree length, builds graph and spectral conditioning, embeds the joint labels and
the prompt with Flan-T5, and samples the released humanoid checkpoint; two padding sizes follow the actual joint count
without changing learned weights. The shared retargeter conjugates canonical deltas into the original bones' rest
frames and moves root positions onto the original skin, keeping quaternion signs continuous.

**Joint labels must use the training vocabulary.** The fox adapter labels its joints with upstream name cleaning
(`Left Thigh`, `Left Shin`, `Left Upper Arm`, `Spine`, ...); hand-written lowercase labels miss the vocabulary and
degrade every take. The playground marks takes generated without these labels as **earlier conditioning**.

Raw output is **60 frames at 30 fps**, the last sample at 1.967 seconds. Fingers outside the body representation keep
their rest pose, and no loop seam is generated.

## The guided sprint

The guided path (`guided.py`) does not give a new sprint: its output is a near-copy of the authored Run with arm
changes of at most about 4°. It converts the owned Run into reference features, adds the manifest's travel, leaves six
arm-related slots free and starts the flow at 0.55 with the other slots locked; the final step restores the authored
gait and blends phase-averaged arm changes at strength 0.35 under an 18° cap (6.3° in the result). Its similarity to
the Run comes from constraining it to the Run, not from UniMate generating a comparable sprint. It stays in the lab as
the **Keep the authored sprint gait** option, labelled **Hybrid**; it is not a contact solver.

## Findings for choosing it

| Question | Finding |
| --- | --- |
| Quality | good on some prompt-only actions (the backflip); many attacks and movements poor; prompt-only sprints recognisable but below the authored Run, with contact, hand and loop problems |
| Time per take | 10 to 20 s with a warm model; up to about 40 s under system load |
| Length | a fixed two seconds (60 frames) |
| Transfer fidelity | rendered fox joints match forward kinematics at every frame, to 0.0009 mm at most |
| Reproducibility | the extracted runner reproduces saved takes exactly on MPS |
| Against [Kimodo](KIMODO_EXPERIMENT.md) | faster and lighter, but shorter takes; both give a usable backflip |

Good numerical checks do not remove floating feet, weak hands, incomplete actions or abrupt clip restarts; contact,
balance, intersections, timing and recovery stay acceptance decisions.

## Code

| Code | Responsibility |
| --- | --- |
| [`platform/studio/atelier/ai/unimate/`](../../../platform/studio/atelier/ai/unimate/README.md) | pinned installer and inference environment; topology and text conditioning, EMA sampling, decoding, provenance |
| [`platform/web/motion/`](../../../platform/web/motion/README.md) | rest-frame retargeting, root conversion, quaternion continuity, loop endpoints |
| [`games/yorimichi/animation_lab/`](../animation_lab/README.md) | the fox's exporter, vocabulary, axes, foot diagnostics, clip manifest, reference exporter, guided sprint, loopback server, playground and verification |

The platform code does not import a game or know its asset paths, and has been tested with explicit inputs and a
synthetic rig, not with a second character's motion. Heavy model dependencies stay in a separate environment, run
under the platform memory guard.

The [upstream code](https://github.com/Friedrich-M/UniMate) and [checkpoint](https://huggingface.co/Linzhan/UniMate)
are MIT licensed. No UniML3D characters, raw Mixamo downloads, or Truebones motions are redistributed. The fox is owned.
Weights, upstream checkouts, generated clips, full captures and exports stay in ignored build output.
