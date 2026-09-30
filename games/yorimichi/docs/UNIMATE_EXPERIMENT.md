# UniMate on the fox hunter

Experiment: September 30, 2026. See the [Motion Lab usage guide](../animation_lab/README.md) for installation,
the comparison/creation playground, prompts, code usage, and exports.

## Result: useful for some new motions, inconsistent overall

UniMate can produce useful **new, prompt-only animations** on our owned fox rig. The clearest positive example
is the backflip the user generated and judged successful: `A person does a backflip`, seed **99**, guidance **2**,
**32** steps. It used no authored reference and took **11.58 seconds** with a warm local model.

Many other attacks/movements looked poor. Correcting joint-name conditioning helped, but fully generated sprints
still did not approach the existing authored Run. Quality depends on the action and take; this experiment does
not establish a success rate or reliable coverage of a whole animation set. Use it to generate candidates, keep
the useful ones, and reject or author the rest.

The **guided sprint was not a useful new animation**. It preserved almost all of the sprint we already had and
introduced only tiny arm changes. Its similarity to the original follows from copying/constraining that original;
it is not evidence that UniMate learned a comparable sprint. The earlier write-up overstated this as the useful
result. We retain the labeled hybrid and its implementation as a record of that unsuccessful variation approach.

<p align="center">
  <img src="../../../docs/media/unimate-backflip.gif" width="640" alt="The owned fox performs a prompt-only UniMate backflip, jumping, rotating backwards, landing and recovering">
</p>

The GIF shows the saved standalone take, sampled at 30 fps with a fixed camera. The viewer centers horizontal
travel, as it does during inspection; the exported animation retains root motion. It repeats the full two-second
sample sequence for presentation, with a visible restart rather than a synthesized seamless loop.

## Inputs and reproduction

The source is [`FoxHunter-Anim-r05.blend`](../assets/characters/fox-hunter/FoxHunter-Anim-r05.blend), with **53 skin
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
| Solver | Fixed midpoint flow ODE; recorded examples use guidance 2 and 32 steps |
| Tested backend | PyTorch MPS on macOS arm64; local inference, no paid API |

To reproduce the positive example, select **Create new motion**, enter `A person does a backflip`, set seed **99**,
guidance **2**, and steps **32**, then generate. The [HTTP example](../animation_lab/README.md#use-the-runner-without-the-ui)
uses the same request. Its saved take ID is `220f6f9e6f75407685e67b0c1583489a`; generated takes stay in ignored build
output. The README [GIF provenance](../../../docs/media/unimate-backflip.json) records that ID, settings, hashes,
and capture details. **Preview GIF** reproduces the capture from a selected take.

Every take records settings, vocabulary, solver, flow start time, reference usage, backend, source hash, and model/text
revisions. Seeds fix initial noise, although numerical results can differ across hardware. A fresh checkout must
run setup and generation; the README GIF is the small documentation illustration, not an installed animation asset.

## What we tried

The initial attack/movement results were weak. Investigation found an integration bug: hand-written lowercase joint
labels differed from the training vocabulary. The fox adapter now uses upstream name cleaning (`Left Thigh`,
`Left Shin`, `Left Upper Arm`, `Spine`, etc.). New provenance records `canonical-names-v2`; old takes remain labeled
**earlier conditioning**. The fix removed an avoidable input error but did not make all generated motion good.

| Experiment | Seed | Inference | Finding |
| --- | ---: | ---: | --- |
| Prompt-only sprint, corrected names | 10 | 10.34 s | Recognizable running, below authored quality; contacts/hands/seam need work |
| Prompt-only sprint, corrected names | 19 | 10.02 s | Similar limitations |
| Guided sprint | 10 | 11.97 s | Near-copy of authored Run; up to 4.2° arm change, little new value |
| Guided sprint, generated through UI | 117 | 19.45 s | Near-copy; up to 3.7° arm change, little new value |
| Independent prompt-only sprint, generated through UI | 99 | 13.15 s | Standalone generation works, but sprint quality target remains unmet |
| Independent prompt-only backflip, user-generated/reviewed | 99 | 11.58 s | Useful new motion; no authored reference |

The backflip is a qualitative, user-reviewed success. It does not imply that all acrobatics work or that this take
needs no further polish. Contact, balance, intersections, timing, and recovery remain acceptance decisions.

Raw generation produces **60 frames at 30 fps**, with the last sample at 1.967 seconds. Fingers outside the body
representation keep their rest pose; no loop seam is synthesized. Guided sprint output has 18 unique gait frames
plus a closing endpoint and copies authored wrist/finger tracks. Neither workflow replaces gameplay clips automatically.

## Implementation and repository placement

Reusable code now lives in the platform:

| Shared code | Responsibility / explicit caller inputs |
| --- | --- |
| [`platform/studio/atelier/ai/unimate/`](../../../platform/studio/atelier/ai/unimate/README.md) | Pinned installer and optional inference environment; topology/text conditioning, EMA sampling, decoding, provenance. Caller supplies the rig, anatomical labels, normalization key, axes, and optional constraint features/mask. |
| [`platform/web/motion/`](../../../platform/web/motion/README.md) | Rest-frame retargeting, root conversion, quaternion continuity, and loop endpoint restoration. Caller supplies Three.js, the source-to-target transform, and target rest transforms. |

These are experimental utilities, tested with explicit inputs and a synthetic rig; extraction is not a claim of
validated motion quality on a second character. Heavy model dependencies stay in a separate environment.
The existing platform memory guard is reused.

The [fox lab](../animation_lab/README.md) retains the owned-source exporter, upstream Mixamo vocabulary selection,
axis transform, named-foot diagnostics, clip manifest, reference exporter, sprint policy, loopback server,
playground, and fox-specific verification. Platform code does not import a game or know its asset paths.

`export_rig.py` keeps the full skin and exports canonical +Z-forward/Y-up body points from the fox's +X-forward/Z-up
source. The shared engine normalizes tree length, builds graph/spectral conditioning, embeds names/prompt with
Flan-T5, and samples the released humanoid checkpoint. Two padding sizes use the actual joint count without changing
learned weights. The shared retargeter conjugates canonical deltas into original bone rest frames and translates
root positions to the original skin, preserving quaternion sign continuity.

The game-specific guided path converts the owned Run into reference features, validates FK, adds manifest travel
for conditioning, leaves six arm-related slots free, and starts flow at 0.55 with the other slots locked. Final
postprocessing restores the authored gait and blends phase-averaged arm changes at strength 0.35 with an 18° input
cap (6.3° final cap). This explains why the result was essentially the existing sprint. It is not a general contact solver.

`server.py` keeps the model warm, validates inputs, serializes jobs, and saves raw features, published motion, job
state, and provenance under `build/yorimichi/unimate/results/<id>/`. The viewer groups original/counterpart comparisons
separately from independent creations, labels authored/prompt-only/hybrid origins, and exports GLB, PNG, and GIF.
It serves only allowed artifacts on loopback; weights and the rest of the repository are outside its file routes.
The playground now includes Kimodo in the same library and comparison workflow. Its generator selector chooses
the next model, while cards, counterpart options and capture/export labels retain each take's actual source.
The shared server runs guarded workers in separate inference environments and preserves both models' existing
output directories. See the [lab guide](../animation_lab/README.md) for the common launch command and API.

The [upstream code](https://github.com/Friedrich-M/UniMate) and [checkpoint](https://huggingface.co/Linzhan/UniMate)
are MIT licensed. No UniML3D characters, raw Mixamo downloads, or Truebones motions are redistributed. The fox is owned.
Weights, upstream checkouts, generated clips, full captures, and exports stay in ignored build output; the selected
README GIF and its provenance are kept alongside the repository's existing documentation media.

## What validation establishes

Retarget/FK checks cover **26,334 body-joint samples** across saved takes including the backflip, with maximum error
**0.00088 mm** in source mesh world units. Guided preservation checks found at most **0.00053 mm** deviation in
locked body joints and a closed
**0.6-second** cycle. Its GLB kept all 53 skin bones and 53 animation channels. These show conversion and copying
accuracy; they do not score perceived quality or show useful novelty in the guided sprint.

Tests cover request validation, local host/origin/file boundaries, persistence, failed-job cleanup, constrained
motion bounds, and loop closure. Shared input tests cover explicit rig axes/vocabulary, invalid trees and constraint
shapes, and checksum-safe installation. A differently named synthetic skin exercises retargeting under rotated/scaled
parents, quaternion continuity, root translation, and local detail overrides. Browser checks cover generation,
source labels, playback/scrubbing, comparison views, and exports. The backflip GIF captures all 60 samples at native
timing. Regenerating the backflip and seed-117 guided sprint through the extracted runner produced exactly the same
raw features and published motion as their saved predecessors on MPS.

Good numerical checks do not remove floating feet, weak hands, incomplete actions, or abrupt clip restarts. The
original trials took 10–20 seconds with a warm model; later regression runs took 29–39 seconds. Latency varies with
system load, and these observations are not a performance guarantee. Gameplay import, polish, and acceptance
remain separate.
