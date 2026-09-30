# Fox motion lab

A local UniMate experiment on Yorimichi's fox hunter, with a Python inference runner and a browser playground.
The [experiment write-up](../docs/UNIMATE_EXPERIMENT.md) records what worked, the conditioning fix, measurements,
and the current quality limits.

The model installer and inference runner live in [the platform](../../../platform/studio/atelier/ai/unimate/README.md),
alongside shared [retargeting helpers](../../../platform/web/motion/README.md). The fox exporter, clip manifest,
sprint policy, server, and UI stay here. Weights and generated artifacts go in ignored `build/yorimichi/unimate/`.
No gameplay animation is replaced automatically. Quality varies: the prompt-only backflip worked well in user review;
many other takes were poor, and the guided sprint was essentially the Run we already had.

## Setup and run

From the repository root, with Git, `uv`, Node/npm, and Blender on PATH. The tested environment is macOS arm64 with
PyTorch MPS. No API key, paid service, training dataset, or separately downloaded character is required.

```sh
uv sync
uv run python games/yorimichi/animation_lab/setup.py
uv run python -m atelier.safety.guarded --no-lock \
  --report build/yorimichi/unimate/server-health --timeout 0 \
  --purpose 'local UniMate motion lab' -- \
  build/yorimichi/unimate/venv/bin/python games/yorimichi/animation_lab/server.py
```

Open **http://127.0.0.1:8842/** and wait for **UniMate ready**. Press Ctrl-C in the server terminal to stop it.
If Blender is not on PATH, set `BLENDER` to its executable before running setup. Unreal is not needed for the lab.

Setup downloads about 1.2 GB of checkpoint weights, creates a separate Python 3.11 inference environment, exports
the owned fox skin and 15 original clips, samples the Run reference, and bundles the viewer. The pinned Flan-T5
encoder downloads on the first server launch into the normal Hugging Face cache. Subsequent launches reuse it.
A fresh checkout has no generated takes; create a counterpart or a new motion through the prompt form.

The server stays on loopback, keeps the model warm, and runs one inference at a time. The existing 10 GiB memory
guard stays enabled; the server and the small non-rendering Blender export do not take the render slot.
The server accepts `--device cpu` and `--device cuda`, but the packaged dependencies and measurements here were
validated on macOS/MPS. `--port` changes the localhost port.

## Compare an original with its counterpart

1. In **Compare originals**, choose an authored clip from the left library. The default is **Forward sprint**.
2. Select a saved **UniMate counterpart**, or generate the first one with the prompt form. Each original keeps its
   counterparts grouped together. Missing counterparts have an explicit empty state.
3. Review the two opaque, textured foxes together. **Match phase** maps their clip progress to the same normalized
   phase; disable it to keep each clip's native timing. Scrub, change speed, orbit/zoom, or show the rigs.
4. Use **Original only** or **UniMate only** to isolate a character. **Export original** or **Export UniMate** saves
   the selected animation as a skinned GLB. The camera button saves a labeled pose PNG; **Preview GIF** captures
   the current view at the clip's original timing, independent of playback speed.

The source labels distinguish **Original · authored**, **UniMate · prompt only**, and **Hybrid · authored gait +
UniMate arms**. Older takes made before the joint-name fix show **earlier conditioning**.

For prompt-generated counterparts, uncheck **Keep the authored sprint gait** when comparing Run. Other originals
also use prompt-only generation; the original is a visual comparison rather than an inference constraint.

The retained **Keep the authored sprint gait** option is the earlier hybrid experiment. It copies the original
stride, root, torso, head, and wrist/finger detail into a 0.6-second loop with only bounded arm changes (at most 6.3°).
It did not add a useful new sprint and should not be read as successful independent generation. Seed 117, guidance 2,
32 steps, and `A person sprints forward at full speed with bent elbows and alternating arm swings.` reproduce it.

## Create an independent animation

Switch to **Create new motion**, enter a name, describe the action, and set a seed/guidance/step count. For example:

```text
A person does a backflip
```

Seed **99**, guidance **2**, and **32** steps reproduce the useful user-reviewed backflip. It has no authored reference.
Press **Generate new motion**. The result is saved in the separate **UniMate-only motions** library with no original
reference attached. Changing the seed creates another take. The eight attack/movement presets and **Generate missing
experiments** are available here; a preset batch can be continued after a reload with the same button.

Prompt-only generation produces 60 frames at 30 fps, with the last sample at 1.967 seconds. Fingers keep their rest
pose and the loop seam is not synthesized. The viewer centers horizontal root travel for inspection, while the
travel metric and exported GLB retain it. Check balance, feet, intersections, action timing, and recovery before
accepting a take for game use.

## Use the runner without the UI

The playground's HTTP API uses the same warm model and artifact/provenance path. With the guarded server running,
this submits the standalone backflip:

```sh
curl -fsS http://127.0.0.1:8842/api/generate \
  -H 'Content-Type: application/json' --data-binary @- <<'JSON'
{
  "title": "Backflip",
  "category": "Movement",
  "prompt": "A person does a backflip",
  "seed": 99,
  "guidance": 2,
  "steps": 32,
  "reference_clip": null,
  "guided_sprint": false
}
JSON
```

The response is HTTP 202 with an `id`. Put that ID into the following read-only requests:

```sh
motion_job_id='paste-the-returned-id'
curl -fsS "http://127.0.0.1:8842/api/jobs/$motion_job_id"
curl -fsS "http://127.0.0.1:8842/results/$motion_job_id/provenance.json"
```

Poll the job route until `status` is `complete`; the final job contains motion/provenance URLs and diagnostics.
`GET /api/status` reports readiness and the active job, while `GET /api/library` returns originals, presets, and saved
takes. The API returns 409 while loading or busy and 400 for invalid input.

For a prompt-only counterpart, set `guided_sprint` to `false` and retain the selected `reference_clip`. For standalone
generation, set `reference_clip` to `null` and `guided_sprint` to `false`. Guidance is 1.01–8, steps are integer 8–64,
and seeds are integer 0–2147483647. Prompt text must contain 3–1000 characters. A guided request requires `Fox_Run`.

The numerical runner is the shared [`atelier.ai.unimate.Engine`](../../../platform/studio/atelier/ai/unimate/README.md).
The local [`Engine`](engine.py) supplies fox inputs and the optional sprint policy, returning `(features, motion,
provenance)`. Use the HTTP API to retain the job lifecycle and avoid loading a second model. The shared browser
[`retargetMotion`](../../../platform/web/motion/retarget.js) turns published motion into tracks on the original skin;
GLB/GIF export happens in the viewer, not in the HTTP generation request.

## Code and outputs

| Source | Responsibility |
| --- | --- |
| [`platform/studio/atelier/ai/unimate/`](../../../platform/studio/atelier/ai/unimate/README.md) | Pinned installer/dependencies, topology/text conditioning, local inference, decoding, provenance |
| [`platform/web/motion/`](../../../platform/web/motion/README.md) | Rest-frame retargeting, root conversion, quaternion continuity, loop endpoint restoration |
| [`setup.py`](setup.py), [`package-lock.json`](package-lock.json) | Invoke shared installation, export owned assets, build frontend |
| [`export_rig.py`](export_rig.py) | Full skin and authored GLB clips; 22-joint canonical conditioning rig |
| [`engine.py`](engine.py) | Fox vocabulary/axes/diagnostics adapter and retained authored-sprint policy |
| [`export_reference.mjs`](export_reference.mjs), [`guided.py`](guided.py) | Sample/validate the owned Run and make bounded hybrid variations |
| [`server.py`](server.py) | Loopback HTTP server, serialized jobs, persistence, allowed artifact routes |
| [`index.html`](index.html), [`app.js`](app.js), [`style.css`](style.css) | Comparison/creation playground, playback, snapshots, GLB/GIF export |
| [`verify.py`](verify.py), [`check_retarget.mjs`](check_retarget.mjs), [`test_server.py`](test_server.py), [`test_guided.py`](test_guided.py) | FK/retarget verification and request/gait contracts |

Setup and generation write the following under `build/yorimichi/unimate/`:

| Output | Contents |
| --- | --- |
| `upstream/`, `venv/`, `model/` | Pinned UniMate code, inference environment, checkpoint/config/statistics |
| `assets/fox.glb`, `assets/rig.json`, `assets/run-reference.json` | Owned skin/original clips, body skeleton, sampled Run reference |
| `web/app.js` | Bundled playground JavaScript |
| `results/<id>/features.npy` | Actual 60-frame model features, before the hybrid loop postprocessing |
| `results/<id>/motion.json` | Published body rotations/root positions; hybrid reference/detail tracks and blend metadata |
| `results/<id>/job.json`, `results/<id>/provenance.json` | Persisted request, source grouping, progress, settings, hashes, timings, diagnostics |
| `exports/<id>/fox.glb`, `exports/<id>/pose.png`, `exports/<id>/preview.gif` | Viewer exports, also offered as browser downloads |
| `export-health/`, `server-health/` | Memory-guard reports |

The raw feature file and published hybrid have different frame counts: 60 model frames versus 18 gait frames plus
the closing endpoint. Guided provenance names the reference, preserved channels, blend strength, and angular bound.
Raw provenance records whether the original is only a comparison reference or absent.

## Development and verification

After changing the frontend, run `npm run --prefix games/yorimichi/animation_lab build` and reload the page. After
changing the fox source or inference code, stop the server, rerun setup if assets changed, and restart it. A missing
or mismatched Run reference requires setup again. Model-load or generation failures are described in the server log.

```sh
.venv/bin/python -m unittest discover -s games/yorimichi/animation_lab -p 'test_*.py'
.venv/bin/python -m unittest discover -s platform/studio/tests -p 'test_unimate.py'
node platform/web/motion/test_motion.mjs games/yorimichi/animation_lab/node_modules/three/build/three.module.js
build/yorimichi/unimate/venv/bin/python games/yorimichi/animation_lab/verify.py
.venv/bin/atelier lint
```

The eight game tests and five shared Python tests run without inference. The two shared JavaScript tests use a
synthetic skin with arbitrary bone names and explicit axes/rest transforms. `verify.py` needs at least one saved
generated take; it compares the viewer retargeter to FK at every frame and checks hybrid gait preservation and
loop closure. See the
[experiment write-up](../docs/UNIMATE_EXPERIMENT.md) for the recorded results and what those checks establish.

The [upstream code](https://github.com/Friedrich-M/UniMate) and
[checkpoint](https://huggingface.co/Linzhan/UniMate) are MIT licensed. Setup does not download or redistribute
UniML3D characters, raw Mixamo motions, or Truebones assets. The source fox is owned; upstream code, weights,
generated takes, captures, and exports stay in ignored build output. The selected backflip GIF and its provenance
are retained in `docs/media/` as the README illustration.
