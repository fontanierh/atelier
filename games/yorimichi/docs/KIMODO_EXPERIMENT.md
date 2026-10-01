# Kimodo on the fox hunter

[Kimodo](../../../platform/studio/atelier/ai/kimodo/README.md) is NVIDIA's text-to-motion diffusion model. Given a
prompt such as `A person does a backflip.`, it generates body motion on its SOMA skeleton, locally and without a
browser; the fox motion lab retargets that motion onto the fox hunter's own rig and shows it next to the authored
clips. On the fox it gives usable motion sketches for acrobatics: a complete backflip and a clean forward roll, both
with anticipation and recovery. The motion still needs contact polish, and two good takes do not show that it covers a
whole animation set. Generated motion never replaces a game clip automatically.

![Kimodo backflip on the fox hunter](../../../docs/media/kimodo-backflip.gif)

The backflip: `A person does a backflip.`, seed **99**, **100** denoising steps, guidance **[2, 2]**, **90 frames at
30 fps**, no animation constraint. The fox anticipates, takes off, completes about 359° of backward rotation, lands and
returns to standing. Its legs stay fairly straight in flight and the landing contacts need polish. The GIF plays all
three seconds at normal speed and repeats; the restart is not a generated loop. Fingers and the tail keep their rest
pose. Provenance: [kimodo-backflip.json](../../../docs/media/kimodo-backflip.json).

![Kimodo forward roll on the fox hunter](../../../docs/media/kimodo-forward-roll.gif)

The forward roll, generated in the playground: seed **56**, guidance **[5, 5]**, **100** steps, **three seconds** (90
frames at 30 fps), with the prompt

> A person crouches down and performs one forward roll on the ground, rolling over their shoulders with tucked knees, then stands back up.

It crouches, rolls over the shoulders with tucked knees and stands back up. Provenance:
[kimodo-forward-roll.json](../../../docs/media/kimodo-forward-roll.json).

## Run it

Install and generate with the [headless Kimodo commands](../animation_lab/README.md#kimodo-headless-backflip), or start
the shared playground and open `http://127.0.0.1:8843/` ([lab guide](../animation_lab/README.md)). **Create new
motion** takes a prompt, model, seed, duration (1 to 10 seconds), guidance and step count; **Compare originals** sets
generated counterparts beside the authored clips. The preview centres horizontal travel; the exported GLB keeps the
root motion. The shared server runs one generation at a time, each model in its own environment.

Generation is local: no hosted demo, no API key, no paid call. Weights (about 17 GB), raw SOMA files, per-take JSON,
prompt embeddings, GLB exports and captures stay in the ignored `build/yorimichi/kimodo/`.

## How it runs

| Input | Pinned value |
| --- | --- |
| Model | `nvidia/Kimodo-SOMA-RP-v1.1` at `6c9233af1180b8151e3c4703477104af5dce9dd5` |
| Upstream code | `58e781898b3d7e328a676a75d3e338c45dce3ad9` |
| Text encoder | LLM2Vec on Llama 3 8B Instruct with the two released McGill adapters; revisions in each take's provenance |
| Fox source | [`FoxHunter-Anim-r05.blend`](../assets/characters/fox-hunter/FoxHunter-Anim-r05.blend), SHA-256 `8103d0bf2c970d4adcd6d9af32f109e376b29433b3cc3597387efd75a3a6219c` |
| Devices (macOS arm64) | text encoding on MPS; diffusion on CPU, because the upstream diffusion has float64 buffers |

- **Text encoder.** Loaded whole, the 8B encoder would exceed the 10 GiB memory guard. The shared runner streams its
  layers in fp32 with both adapters, uses upstream tokenisation and pooling with bidirectional attention, and caches
  each prompt's embedding. It is not the default bf16 CUDA runtime, so benchmark parity is not claimed.
- **Transfer.** Kimodo predicts the fixed SOMA skeleton and expands it to 77 joints. An explicit map transfers canonical
  rotation deltas onto the fox's 22 body joints and 53-bone skin, folds source-only joints such as the second neck,
  scales root travel by the fox's leg height and applies one constant floor offset. It keeps the generated root
  rotation and timing; it adds no pose constraint, IK or change to the airborne arc.
- **No foot-skate cleanup.** The upstream native cleanup is an x86 SIMD build that does not compile on ARM, so it is off
  and every take records `post_processing: false`. Landings deserve a contact review.

## Findings for choosing it

| Question | Finding |
| --- | --- |
| Quality | a complete backflip and forward roll, readable at normal speed; contacts and in-flight leg shape need polish |
| Time per take | about 107 s including text encoding; about 42 s with a cached prompt embedding |
| Memory | the process peaks at about 4 GiB, inside the lab's 10 GiB guard; the streamed encoder alone stays near 2.1 GiB |
| Transfer fidelity | rendered fox joints match the SOMA forward kinematics at every frame, to 0.0006 mm at most |
| Reproducibility | the packaged command reproduces a saved raw take exactly on the same hardware |
| Against [UniMate](UNIMATE_EXPERIMENT.md) | longer takes (1 to 10 s against a fixed 2 s) and slower generation; both give a usable backflip |

The numerical checks show that the transfer is faithful; only watching a take shows whether it is the move asked for.

## Code

The installer, streamed encoder, diffusion runner and retargeting helper are in
[`platform/studio/atelier/ai/kimodo/`](../../../platform/studio/atelier/ai/kimodo/README.md). The fox's joint map,
the headless command and the playground integration are in [`games/yorimichi/animation_lab/`](../animation_lab/README.md).
