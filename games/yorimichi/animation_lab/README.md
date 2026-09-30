# Fox motion lab

One local playground for **UniMate and Kimodo** on Yorimichi's owned fox hunter. Compare an authored animation
with counterparts from either model, or create independent animations with a custom prompt. Every generated card,
counterpart option, preview capture and export names its actual model. A model filter lets you inspect both libraries
together or isolate one; the prompt form's **Generate with** selector chooses the next take's generator.

The [UniMate write-up](../docs/UNIMATE_EXPERIMENT.md) records mixed results, a useful independent backflip, and a guided
sprint that was essentially the Run already available. The [Kimodo write-up](../docs/KIMODO_EXPERIMENT.md) records a
headless backflip and the user's forward roll. User review found Kimodo worked quite well on these takes. Generated
motion still needs contact and recovery review before game use; the lab does not replace gameplay clips automatically.

## Setup and run the shared playground

From the repository root, with Git, `uv`, Node/npm and Blender on PATH:

```sh
uv sync
uv run python games/yorimichi/animation_lab/setup.py
uv run python -m atelier.safety.guarded --no-lock \
  --report build/yorimichi/motion_lab/server-health --timeout 0 \
  --purpose 'shared fox motion lab' -- \
  .venv/bin/python games/yorimichi/animation_lab/server.py
```

Open **http://127.0.0.1:8843/**. This is the same UI for both models. Setup installs each pinned model into its own
Python 3.11 environment, exports the owned 53-bone fox skin and 15 original clips, samples the Run reference for
UniMate, and builds one frontend. Existing takes remain in their original directories and appear together without
copying or renaming their files. A fresh checkout has no saved takes; generate them through the prompt form.

The shared server starts two loopback workers on private ephemeral ports, using each model's own interpreter.
Each worker has the unchanged 10 GiB memory guard; only one generation runs at a time across both models.
Ctrl-C stops the shared server and reaps its workers and monitors. No inference request goes to a hosted demo.
No API key or paid service is needed. If Blender is not on PATH, set `BLENDER` to its executable before setup.
Unreal is not needed. Setup and inference do not take the render slot; the small Blender operation exports without
rendering. Failed/uninstalled models report their status while saved takes remain browsable.

UniMate downloads about 1.2 GB of checkpoint weights, plus its pinned Flan-T5 encoder on first load. Kimodo downloads
about 17 GB of weights. The tested macOS ARM configuration uses MPS for UniMate and the streamed Kimodo text encoder,
with CPU diffusion for Kimodo. Its native MotionCorrection build fails on ARM, so foot-skate cleanup is disabled
and recorded as `post_processing: false`. The public NousResearch Llama 3 base distribution and both released McGill
adapters retain their licences. No weights or third-party training assets are redistributed here.

To install just one backend, pass `--generator unimate` or `--generator kimodo` to setup. Then run `npm run --prefix
games/yorimichi/animation_lab build` for the shared frontend. The shared server can browse saved takes even when a
worker is unavailable; the selected model must be ready to generate. Its `--unimate-root` and `--kimodo-root`
options accept existing custom model directories. The exports must use the same fox source revision.

## Compare originals and generated counterparts

1. In **Compare originals**, choose an authored clip. **Forward sprint** is the initial selection.
2. Choose a **Generated counterpart**. Options identify UniMate/Kimodo, prompt-only/hybrid origin and seed.
   The **Show generated from** filter narrows counterparts and independent takes by model.
3. Review the two textured foxes together. **Match phase** maps their normalized progress; disable it to keep native
   timing. Scrub, change speed, orbit/zoom, or show the rigs. **Original only** and **Generated only** isolate a side.
4. For a new counterpart, choose **Generate with**, write its prompt and press **Generate counterpart**. The original
   is a visual comparison, not an inference constraint. The new take stays grouped with that authored clip.

Labels distinguish **Original · authored**, **UniMate/Kimodo · prompt only** and **Hybrid · authored gait + UniMate
arms**. Earlier UniMate takes display **earlier conditioning**. The optional **Keep the authored sprint gait**
checkbox appears only for UniMate when comparing Run. It preserves the authored stride, root, torso, head and hand
tracks with bounded arm changes; it did not produce a useful independent sprint. It is off unless selecting an
existing hybrid take. Kimodo never uses that constraint.

## Create an independent animation

Switch to **Create new motion**. The **Generated motions** library contains independent takes from both models,
with no original attached. Select a take to replay it or choose **Generate with** for a new model, then enter a name,
prompt, seed, guidance and steps. Kimodo also accepts a duration. Model-specific controls update when switching
models; viewing a take always retains its own source labels even when the next generation uses another model.
Browsing takes does not change the model chosen for the next generation. Controls copy a take's sampling settings
only when its source matches that chosen model, so a UniMate take cannot overwrite Kimodo's step range or duration.

Useful recipes:

| Model / action | Prompt | Seed | Guidance | Steps | Duration |
| --- | --- | --- | --- | --- | --- |
| UniMate backflip | `A person does a backflip` | 99 | 2 | 32 | 2 seconds (fixed) |
| Kimodo backflip | `A person does a backflip.` | 99 | 2 | 100 | 3 seconds |
| User's Kimodo forward roll | `A person crouches down and performs one forward roll on the ground, rolling over their shoulders with tucked knees, then stands back up.` | 56 | 5 | 100 | 3 seconds |

Presets and **Generate missing experiments** use the selected model and sampling controls. A take from another
model does not count as completing that model's preset. Prompt-only UniMate outputs 60 frames at 30 fps; Kimodo
accepts 1–10 seconds at 30 fps. Fingers retain their rest pose and no loop seam is synthesized.

**Export UniMate/Kimodo** saves the selected animation as a skinned GLB, preserving its generated root travel.
**Export original** saves the authored side. The camera button captures a labelled pose PNG; **Preview GIF** captures
all frames at native timing, independent of playback speed. The preview centers horizontal travel for inspection.
Check feet, balance, intersections and recovery before accepting a take. The selected backflip and forward roll GIFs
and their provenance are retained in `docs/media/`; other captures and generated artifacts stay in ignored build output.

## Kimodo headless backflip

Generation itself needs neither the playground nor a browser. After installing/exporting the Kimodo assets:

```sh
uv run python games/yorimichi/animation_lab/setup.py --generator kimodo
uv run python -m atelier.safety.guarded --no-lock \
  --report build/yorimichi/kimodo/headless-health --timeout 1200 \
  --purpose 'local headless Kimodo generation' -- \
  build/yorimichi/kimodo/venv/bin/python games/yorimichi/animation_lab/kimodo_generate.py \
  --prompt 'A person does a backflip.' --seed 99 --steps 100 --guidance 2 --duration 3
```

This writes a new `build/yorimichi/kimodo/results/<id>/` containing `source-motion.npz`, `motion.json`, `job.json` and
`provenance.json`. The shared playground discovers it on reload. Stop the playground before using this standalone
command to avoid loading another model instance. A cached embedding avoids repeating the streamed text pass.
The reusable [`atelier.ai.kimodo.Engine`](../../../platform/studio/atelier/ai/kimodo/README.md) can produce raw SOMA
motion for other characters; the fox's anatomical map belongs in [`kimodo_engine.py`](kimodo_engine.py).

## Generate through the shared HTTP API

With the guarded shared server running:

```sh
curl -fsS http://127.0.0.1:8843/api/generate \
  -H 'Content-Type: application/json' --data-binary @- <<'JSON'
{
  "generator": "kimodo",
  "title": "Backflip",
  "category": "Movement",
  "prompt": "A person does a backflip.",
  "seed": 99,
  "guidance": 2,
  "steps": 100,
  "duration": 3,
  "reference_clip": null,
  "guided_sprint": false
}
JSON
```

The response is HTTP 202 with a model-prefixed `id`, such as `kimodo_<id>`. Use that full ID:

```sh
motion_job_id='paste-the-returned-id'
curl -fsS "http://127.0.0.1:8843/api/jobs/$motion_job_id"
curl -fsS "http://127.0.0.1:8843/results/$motion_job_id/provenance.json"
```

Poll until `status` is `complete`. Published motion/provenance URLs are ready then. For UniMate, use
`"generator": "unimate"`, 32 steps, and omit duration. A counterpart sets `reference_clip` to an owned ID such as
`Fox_Jump`; an independent take uses `null`. Guided requests require UniMate and `Fox_Run`.

`GET /api/status` reports both model states and the one active job. `GET /api/library` returns originals, presets
by model and all saved takes. IDs are namespaced in the shared API so collisions cannot mix models; files retain
their original IDs in each backend directory. Exports route back to the selected take's backend. The API returns
409 while loading or busy and 400 for invalid input. Seeds are integer 0–2147483647, guidance 1.01–8 and prompt
length 3–1000 characters. Steps are integer 8–64 for UniMate and 8–250 for Kimodo; its duration is 1–10 seconds.

## Source and outputs

| Location | Responsibility |
| --- | --- |
| [`platform/studio/atelier/ai/unimate/`](../../../platform/studio/atelier/ai/unimate/README.md), [`platform/studio/atelier/ai/kimodo/`](../../../platform/studio/atelier/ai/kimodo/README.md) | Reusable installers, inference, decoding/retargeting and provenance |
| [`platform/web/motion/`](../../../platform/web/motion/README.md) | Skin rest-frame transfer, axes, quaternion continuity and loop endpoints |
| [`engine.py`](engine.py), [`kimodo_engine.py`](kimodo_engine.py), [`guided.py`](guided.py) | Fox-specific vocabulary, anatomy, diagnostics and optional gait policy |
| [`export_rig.py`](export_rig.py), [`export_reference.mjs`](export_reference.mjs), [`setup.py`](setup.py) | Owned character/clip export, Run sampling, backend setup and shared frontend build |
| [`server.py`](server.py), [`unified.py`](unified.py) | Loopback API, job persistence, guarded worker lifecycle, shared library and artifact routing |
| [`kimodo_generate.py`](kimodo_generate.py) | Standalone headless fox generation |
| [`index.html`](index.html), [`app.js`](app.js), [`style.css`](style.css) | Shared comparison/creation UI, playback, labelled captures and GLB/GIF export |

`build/yorimichi/unimate/` and `build/yorimichi/kimodo/` each retain their own code, weights, inference environment,
owned exported assets, prompt caches, `results/<id>/` and `exports/<id>/`. Raw output is `features.npy` for UniMate
and `source-motion.npz` for Kimodo. Every take has motion, job and provenance JSON. Hybrid features/published output
have different frame counts; the provenance records the reference, preserved channels and angular bound.

`build/yorimichi/motion_lab/` contains the shared `web/app.js`, `workers/<model>/` logs, address files and memory
reports, the shared server guard report, and exports of authored clips. Nothing moves out of its backend directory
just to appear in the shared library. The source fox is owned; upstream code and weights keep their respective
licences and stay in ignored build output.

## Development and verification

```sh
npm run --prefix games/yorimichi/animation_lab build
.venv/bin/python -m unittest discover -s games/yorimichi/animation_lab -p 'test_*.py'
.venv/bin/python -m unittest discover -s platform/studio/tests -p 'test_unimate.py'
build/yorimichi/kimodo/venv/bin/python -m unittest discover -s platform/studio/tests -p 'test_kimodo.py'
node platform/web/motion/test_motion.mjs games/yorimichi/animation_lab/node_modules/three/build/three.module.js
build/yorimichi/unimate/venv/bin/python games/yorimichi/animation_lab/verify.py
build/yorimichi/kimodo/venv/bin/python games/yorimichi/animation_lab/verify_kimodo.py
.venv/bin/atelier lint
```

The game tests cover request bounds, origin/file restrictions, hybrid gait, shared identities/artifact routing and
serialization across models. Platform tests cover the independent runners and streamed/full PEFT parity. The two
JavaScript tests use a synthetic skin with explicit axes/rest transforms. Each verifier needs saved generated takes;
it compares rendered body joints with FK at every frame. After Python changes, restart the shared server; after
frontend changes, rebuild and reload. If the fox source changes, rerun setup for both backends.
