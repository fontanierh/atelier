# Kimodo on the fox hunter

**The first proper headless backflip works.** The fox anticipates, takes off, completes a backward rotation, lands
and returns to standing. Its legs remain fairly straight in flight and its contacts need polish. This is a promising
motion sketch, not evidence that Kimodo will handle every action well or outperform UniMate across the library.
User review found Kimodo worked quite well, and a subsequent user-generated forward roll is another useful result.
The [earlier UniMate experiment](UNIMATE_EXPERIMENT.md) had mixed results and a useful independent backflip;
its near-copy guided sprint remains of little value.

![Headless Kimodo backflip on the owned fox](../../../docs/media/kimodo-backflip.gif)

The selected take uses `A person does a backflip.`, seed **99**, **100** denoising steps, guidance **[2, 2]** and
**90 frames at 30 fps**. There is no authored animation constraint. The GIF shows all three seconds at normal
speed and repeats the take; its restart is not a synthesized loop. Fingers and the tail keep their rest pose.

## User-generated forward roll

![User-generated Kimodo forward roll](../../../docs/media/kimodo-forward-roll.gif)

The user generated this take directly in the playground with:

> A person crouches down and performs one forward roll on the ground, rolling over their shoulders with tucked knees, then stands back up.

Seed **56**, guidance **[5, 5]**, **100** steps and **three seconds** (90 frames at 30 fps). It crouches, rolls over
the shoulders with tucked knees, and returns to standing. The GIF captures that exact saved take at normal speed;
its prompt/settings, model revisions and source hash are in `docs/media/kimodo-forward-roll.json`.

## What actually ran

The model is `nvidia/Kimodo-SOMA-RP-v1.1` at `6c9233af1180b8151e3c4703477104af5dce9dd5`, with upstream Kimodo
at `58e781898b3d7e328a676a75d3e338c45dce3ad9`. It predicts the fixed SOMA body skeleton and expands its output
to 77 joints. An explicit map transfers its body motion to the owned fox's 22 body joints and 53-bone skin.
The fox source is `FoxHunter-Anim-r05.blend`, SHA-256
`8103d0bf2c970d4adcd6d9af32f109e376b29433b3cc3597387efd75a3a6219c`.

Generation is entirely **headless and local**. A browser is used to inspect/export the result in the playground.
We initially tried NVIDIA's hosted demo, but its download did not yield a usable artifact here. The accepted take
comes from the local command, not that demo or a downloaded example motion.

The default 8B LLM2Vec encoder would exceed the rig's memory ceiling. The shared runner streams its layers in
fp32 with both released LoRA adapters and caches each prompt's embedding. It reuses upstream tokenization/pooling
and explicitly requests bidirectional attention. It is not the default bf16 CUDA runtime, so benchmark parity is
not claimed. The base-weight distribution and all adapter revisions are recorded alongside each take.
Text encoding uses MPS; diffusion uses CPU on this M3 Pro because the upstream diffusion has float64 buffers.

The fox transfer uses canonical rotation deltas, folds source-only joints such as the second neck, scales root
travel by the fox's leg height and applies a **single constant floor offset**. It preserves the generated root
rotation and timing. It does not copy the authored Run, add a pose constraint, run IK, or alter the airborne arc.
The upstream native foot-skate cleanup is disabled because its x86 SIMD build does not compile on this ARM rig.
The landing therefore still deserves contact review.

## Recorded checks

- The small whole-model test compares the streamed layers and real PEFT adapter files to full bidirectional
  inference. A separate regression test rejects a missing expected adapter tensor.
- The packaged CLI reproduced the selected raw sample exactly. The first packaged run took **106.8 seconds**
  including text encoding; the observed process footprint peaked at **4.05 GiB**, below the unchanged 10 GiB guard.
  The separate encoder experiment stayed near 2.1 GiB. Cached prompts avoid the encoding pass.
- The playground prompt form generated another independent backflip with seed **117**, using the cached
  embedding in **42.0 seconds**. The selected seed-99 take also exported as a skinned fox GLB and a 90-frame GIF.
- Source SOMA FK and rendered fox FK are checked at every frame. The selected take has **1,980** target joint
  samples; maximum viewer-transfer error was **0.00050 mm**. Across both takes, all **3,960** samples passed
  with a maximum error of **0.00059 mm**.
- The root completes approximately **359°** of backward rotation and finishes upright. Those numerical checks
  establish transfer fidelity; visual inspection establishes that this particular take resembles a backflip.
- The shared playground generated a Kimodo jump counterpart and a UniMate backflip through the same API;
  the latter reproduced the existing UniMate features exactly. Cross-model overlap returned HTTP 409, both
  skinned GLB exports retained 53 bones, and a shared-server shutdown reaped both guarded workers.
  All 14 game tests passed. Subsequent FK checks covered **18,480 Kimodo** and **27,654 UniMate** joint samples,
  including the user's forward roll, with maximum errors of **0.00059 mm** and **0.00088 mm** respectively.

## Reproduce and inspect

Follow the [Kimodo setup and headless commands](../animation_lab/README.md#kimodo-headless-backflip).
Open the shared playground at `http://127.0.0.1:8843/` after starting it. **Create new motion** shows independent
UniMate and Kimodo takes and accepts a custom prompt, model, seed, duration, guidance and step count.
**Compare originals** groups counterparts from both models with the owned authored clips. Model filters, source
badges, counterpart options and export labels identify the actual generator of each take. The preview centers
horizontal travel, while the GLB preserves root motion. Inference stays in each model's isolated environment;
the shared server starts and guards both workers and accepts one generation at a time.

The reusable installer, streamed encoder, diffusion runner and explicit retargeting helper live in
[`platform/studio/atelier/ai/kimodo/`](../../../platform/studio/atelier/ai/kimodo/README.md).
The fox map, headless command and playground integration live in `games/yorimichi/animation_lab/`.
Weights, raw SOMA NPZ files, per-take JSON, embeddings, exported GLBs and captures stay under ignored
`build/yorimichi/kimodo/`. Only the selected README GIF and its provenance are retained in `docs/media/`.
