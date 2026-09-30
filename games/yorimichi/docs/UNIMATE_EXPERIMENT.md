# UniMate on the fox hunter

Experiment: September 30, 2026. The runnable implementation and browser playground are in
[`../animation_lab/`](../animation_lab/README.md).

## What we wanted to establish

Can a released text-to-motion model produce attack and movement variations on Yorimichi's owned fox hunter rig,
while keeping its skinned character intact? The first quality target was a forward sprint close to the existing
Run clip. The playground makes that comparison explicit: original and counterpart together, and independent
prompt-only generation in a separate workflow.

The useful result is a guided sprint variation. It retains the authored gait and lets UniMate change the arms
within a small bound. Fully prompt-generated body motion improved after correcting conditioning, but has not
matched the authored sprint's quality. Neither path replaces a gameplay clip automatically.

## Inputs and reproducibility

The source is [`FoxHunter-Anim-r05.blend`](../assets/characters/fox-hunter/FoxHunter-Anim-r05.blend), with 53 skin bones,
22 anatomical body joints for generation, and 15 authored comparison clips. The Run period and travel speed come
from its [manifest](../assets/characters/fox-hunter/manifest.json).

| Input | Pinned value |
| --- | --- |
| UniMate code | `5d6aabedd947297b5ba6706d8e9113e68c0c3e4f` |
| Checkpoint | `unimate_uniml3d_f60_v2`, EMA step 100000 |
| Checkpoint repository revision | `387a344c3031299bc25fcbef35d36bd186d5afe7` |
| Checkpoint SHA-256 | `cbcfb7a057e45f967d5964fecf6b3f83358096f1306f25831e1644a18a50eb34` |
| Flan-T5 revision | `7bcac572ce56db69c1ea7c8af255c5d7c9672fc2` |
| Fox source SHA-256 | `8103d0bf2c970d4adcd6d9af32f109e376b29433b3cc3597387efd75a3a6219c` |
| Sampler | Fixed midpoint flow ODE, 32 steps, prompt guidance 2 for the sprint comparisons |
| Tested backend | PyTorch MPS on macOS arm64; local inference, no paid API |

The raw sprint prompt was `A person sprints forward at full speed.` The guided prompt was
`A person sprints forward at full speed with bent elbows and alternating arm swings.`
The [setup script](../animation_lab/setup.py) installs pinned Python/Node dependencies and checks the checkpoint hash.
Each generated take records the prompt, seed, vocabulary, solver settings, flow start time, reference usage, device,
rig hash, and model/text revisions in provenance. Seeds fix initial noise; different hardware can still produce
numerical differences.

## Findings

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

## Implementation

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

## What the checks establish

Eight tests cover request validation, failed-job cleanup, local host/origin and file boundaries, comparison
persistence, guided request restrictions, bounded arm changes, and loop closure. `verify.py` independently samples
source positions and checks the published hybrid's preserved body joints and cadence. It then compares every
saved take against the same Three.js retargeter used by the playground. Browser checks covered both generation
forms, persistence, source labels, comparison views, playback, scrubbing, filtering, rig overlays, and exports.

The tiny FK errors establish correct conversion and preservation of the reference gait. They do not measure
perceived motion quality or prove that arbitrary prompts, attacks, or new rigs work well. The 10–20 second timings
are measured warm-model runs, rather than a performance guarantee.

The guided result is specific to this source Run. It preserves in-place locomotion; the manifest supplies travel
speed. The arm variation is intentionally modest, and the loop blends pose endpoints without a general velocity
or contact optimization. Prompt-only clips can still have floating feet, intersections, weak hands, incomplete
sequences, and an abrupt loop seam. Export creates a skinned GLB for review; gameplay import and acceptance remain
separate.

## Repository placement

All inference, export, verification, and playground source lives in `games/yorimichi/animation_lab/`. This experiment
knows the fox's source file, joint naming, authored clips, and sprint constraint, so it remains game-local under
[Atelier's architecture rules](../../../ARCHITECTURE.md#rules). It has not yet demonstrated a shared interface in a
second game. Weights, upstream checkouts, generated clips, captures, and exports live under the ignored
`build/yorimichi/unimate/`; they are reproduced with setup and generation rather than redistributed in this PR.

The candidates for a later platform extraction are concrete:

| Shared candidate | Platform destination | Game input that must become explicit |
| --- | --- | --- |
| Checkpoint installer and environment setup | `platform/studio/atelier/ai/` | Model revision, dependency environment, output directory; owned-character export stays in the game |
| Topology/text conditioning and inference runner | `platform/studio/atelier/ai/` | Skeleton, canonical axes, joint-name vocabulary, normalization statistics, optional reference constraint |
| Rest-frame rotation conversion and skin retargeting | `platform/web/` | Bone mapping, rest transforms, root translation, canonical-to-model transform |

The current runner still assumes Mixamo anatomical labels/statistics, the fox's canonical orientation, and named
feet for diagnostics. The sprint constraint is authored motion data plus fox-specific policy, not a shared contact
solver. The existing memory guard is already reused from the platform. Validation on another owned rig or a sandbox
fixture should precede promoting the remaining candidates; the generic model dependencies can stay optional so
ordinary Atelier installs do not acquire the inference environment.

For setup commands, the two UI workflows, HTTP usage, outputs, and validation commands, use the
[Motion Lab usage guide](../animation_lab/README.md).
