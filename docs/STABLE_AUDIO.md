# Stable Audio sound effect experiments

**Experiment context:** the catalog and `build/yorimichi/` examples below belong to the retained V1 sound-review
experiment. They are not adopted V2 audio or required work for the port. The shared review tooling can prepare
new candidates when separately requested; keep those in the intended game's ignored build directory and use
normal guards for inference. V2 currently uses its recovered/pinned audio through the
[V2 content workflow](../games/yorimichi_v2/README.md#restricted-content-and-recoverable-originals), with remaining
work in [INVENTORY.md](../games/yorimichi_v2/docs/INVENTORY.md). Do not rerun retired game tests or regenerate
accepted sounds merely to refresh this experiment.

Stable Audio 3 is the family tested for this experiment on 2026-10-18. Start
with its sound effect specialist, **Small-SFX**, using the official **MLX**
runtime on Apple silicon. This is an offline authoring tool: the game does not
load the model, and experimental takes are not accepted game assets.

The official repository supports MLX directly, without PyTorch, CUDA or a
community conversion. Its older top-level benchmark also mentions CoreML;
the selected runtime is the current `optimized/mlx` implementation. Medium is
an optional later quality comparison; Small-Music is not the sound effect model.

Sources:

- [Stable Audio 3 official repository](https://github.com/Stability-AI/stable-audio-3)
- [Official Apple silicon runtime](https://github.com/Stability-AI/stable-audio-3/tree/main/optimized/mlx)
- [Small-SFX model card](https://huggingface.co/stabilityai/stable-audio-3-small-sfx)
- [Official optimized weights](https://huggingface.co/stabilityai/stable-audio-3-optimized)
- [Prompting guide](https://github.com/Stability-AI/stable-audio-3/blob/main/docs/guides/prompting.md)

## Isolated setup

Keep the vendor checkout and its Python environment separate from Atelier's
environment. The experiment uses these fixed identities:

| Component | Revision |
| --- | --- |
| Stability-AI/stable-audio-3 | `77e0398c26f7d22d801ec1bb036307e8b231f741` |
| stabilityai/stable-audio-3-optimized | `08b17423649b5714b22eab20f96bf00751f2358a` |
| Python | 3.11 |
| Model / decoder | `sm-sfx` / `same-s` |
| Sampling | 8 steps, CFG 1, DiT FP16, default model freeing |

Clone the official repository to a caller-selected location, check out the
source revision, then create `optimized/mlx/.venv` with `uv venv --python 3.11`.
Install its requirements with `uv pip install --python .venv/bin/python
--only-binary :all: -r requirements.txt` from `optimized/mlx`. Binary-only
installation prevents an unexpected native dependency compile. Save `uv pip
freeze --python .venv/bin/python` alongside the local setup receipt.

The initial installation used MLX/MLX-Metal 0.32.4, NumPy 2.4.6, SentencePiece
0.2.2, Hugging Face Hub 2.2.0, SoundFile 0.14.0 and Pillow 13.0.0. CLI help
was checked successfully before inference. No UI or public sharing is needed.

Download only these four files from the pinned optimized-weight revision via
`huggingface_hub.hf_hub_download(..., revision=...)`:

- `MLX/dit_sm-sfx_f16.npz`
- `MLX/same_s_decoder_f32.npz`
- `MLX/same_s_encoder_f32.npz`
- `MLX/t5gemma_f16.npz`

They total 1,919,674,322 bytes. Link each returned snapshot path into the
vendor checkout's `optimized/mlx/models/mlx/` directory under its basename.
These are immutable shared model downloads, not mutable Unreal artifacts.
The batch runner verifies the source revision and each file's official SHA-256
before generation. The optimized repository was accessible without credentials
at the checked revision; do not work around an access restriction if this changes.

The runtime code and model weights have different licenses. Preserve the model
card and its Community/Gemma terms in the experiment records; production use
is a separate decision. No paid API is used for this local experiment.

## Review library

The historical V1 experiment catalog is
`games/yorimichi/assets/audio/stable_audio_review.json`: 48 descriptions, each
with four explicit seeds, for **192 candidate takes**.

| Category | Takes |
| --- | ---: |
| Footsteps on 12 surfaces | 48 |
| Skateboard rolling on 8 surfaces | 32 |
| Powerslides on 6 surfaces | 24 |
| Landings on 8 surfaces | 32 |
| Four bird calls | 16 |
| Three effort-grunt voices | 12 |
| Three hurt-reaction voices | 12 |
| Jogging / breathless recovery voices | 16 |

Prepare a dedicated served folder, with logs outside it:

```sh
uv run python -m atelier.ai.stable_audio.review prepare \
  --catalog games/yorimichi/assets/audio/stable_audio_review.json \
  --web platform/web/audio-review \
  --output build/yorimichi/stable-audio-review
```

Generate through ordinary admission and both memory guards. Substitute the
installed vendor checkout for `VENDOR_ROOT`. Use a fresh report name for every
batch; inspect failed receipts before any retry.

```sh
ATELIER_AGENT=OWNER nice -n 10 uv run python -m atelier.harness.safety.guarded \
  --kind job --report build/yorimichi/logs/stable-audio-batch-01.guard \
  --timeout 240 --purpose "Stable Audio SFX review: 24 takes" -- \
  .venv/bin/python -u -m atelier.ai.stable_audio.review generate \
  --output build/yorimichi/stable-audio-review \
  --runtime VENDOR_ROOT \
  --logs build/yorimichi/logs/stable-audio-takes --limit 24
```

Libraries accept at most 512 takes and a 4 MiB manifest. Each batch resumes
verified ready takes and generates at most 24 pending takes.
Failed or interrupted takes require diagnosis and an explicit manifest status
reset, never automatic replay. Each take has a 120-second child deadline; the
outer guard also bounds the batch and reaps its owned children on interruption.
Keep the source fixed until the enclosing caller and native children have exited.

The manifest records prompts, seeds, model and weight identities, settings,
durations and WAV checksums. A take is ready only after its process succeeds and
its stereo PCM WAV passes format, duration, truncation and non-silence checks.
The runtime rejects non-finite samples before writing and clips its output to
16-bit PCM; clipping, audible artifacts and semantic accuracy still need listening
review. A valid WAV does not prove the desired sound was generated.

To check a completed small library without loading models or waiting for native
admission, run this read-only command:

```sh
uv run python -m atelier.ai.stable_audio.review validate-ready \
  --output build/yorimichi/stable-audio-review
```

It requires every take to be ready and checks the recorded WAV hashes, format,
duration and signal. It accepts at most 512 takes, 64 MiB of WAV files and a 4 MiB
manifest. For more than 64 MiB of WAV data, use guarded `generate`; the take-count
and manifest limits still apply. A completed `generate` run also verifies existing
audio and returns before accessing model weights.
These checks verify retained files, not sound quality or a new inference run.

## Tailnet review

Run `python -m atelier.ai.stable_audio.serve --root REVIEW_ROOT --port 8794`
using Atelier's Python, and proxy that loopback listener with an unused
Tailscale Serve HTTPS port. The initial session uses a dedicated launchd
service, `com.atelier.stable-audio-review`, with HTTPS port 9444. Read the
existing Tailscale configuration before adding a route; do not reset other
services or enable Funnel. Machine addresses belong in local receipts, not Git.

Only the named HTML/JS/CSS, manifest and numbered WAV files are exposed. Logs,
dotfiles, directory listings and symlink escapes are denied. The page supports
category/material search, native audio controls, WAV downloads, browser-local
favourites and JSON shortlist export. It updates generation progress every
15 seconds and pauses other clips when one starts playing. Favourites are not
shared across devices until exported.

Before adopting a take, listen for material identity, transient timing, unwanted
voices, background music, distortion and repetitive patterns. Trim one-shots,
author seamless loops where appropriate, set playback gain and mono/spatial
behavior, then add selected sources and provenance through the target game's owned audio route. For V2, that
means its asset records and explicitly claimed targeted import, not a normal-build generation step. The experiment deliberately performs none of those
production acceptance steps automatically.

## Contact samples and skating loops

After raw generation, run `python -m atelier.ai.stable_audio.prepare_samples
--root build/yorimichi/stable-audio-review` through the same guarded launcher,
using a new report and a bounded timeout. This creates `prepared.json` and
`samples/` WAVs without replacing original takes.

Footstep sequences become individual contact candidates: independent attacks,
short pre-roll, tails bounded before the next contact and short fades. Each
landing take supplies its strongest impact candidate. Prepared samples are mono
48 kHz / 16-bit PCM, DC-centered and peak-normalized to -3 dBFS. Source intervals
use the resampled 48 kHz frame domain; raw stereo takes remain unchanged.

Rolling and powerslide takes instead supply sustained loop candidates. Selection
prefers a steady interval away from recording edges and isolated impacts, then
uses a documented equal-power circular crossfade. This makes the splice
continuous; it does not prove the interval contains the correct wheel sound.
Listen to several repetitions before accepting it. Footfalls are never exported
as a pre-recorded locomotion rhythm.

The review page's **Library** selector switches between raw takes and game
samples; `?bank=samples` opens the latter directly. Loops repeat in the player.
Provenance includes each sample's cue, intended trigger, source interval and
crossfade length. Listening acceptance is still required.

Prepared namespaces include the ordered verified source WAV identities and
hashes, the raw plan and processor hash. Regenerating different audio with the
same prompt and seed therefore creates a different bank. Source hashes are
checked again before manifest publication. Existing sample files are reused
only when their bytes match the expected result; mismatches fail without
overwriting published audio.

The current game already has the relevant timing hooks:

- `UJapanFootstepComponent` detects actual `foot_L` / `foot_R` plants, traces
  the material under each contact and chooses one variation. It does not use a
  fixed walking timer or animation-notify assets.
- `USkateComponent` triggers `land` on air-to-ground transitions and plays
  board-attached rolling loops based on ground state, wheel speed and surface.
  Surface transitions crossfade; powerslide state drives the `skid` loop.
- Skating network presentation consumes replicated mode/surface/audio state.
  Asset integration must preserve this and replay guards rather than adding
  owner-only playback.

Prepared cue names preserve detailed surface labels. They are not an automatic
runtime bank migration. The current footsteps group several materials into
`stone` and `dirt_gravel`, while powerslides use one generic `skid` loop. Finer
distinctions require explicit material/bank mappings; surface-specific skid
playback also needs runtime support. Snow and carpet need explicit mappings.
Candidates are not silently assigned to different physical surfaces.

## Initial verification

An M1 Max smoke test generated a four-second skateboard landing in 2.78 seconds
of model wall time. The aggregate guard observed a 1,900,547,776-byte peak and
certified `child_exited`, empty cleanup and zero remaining footprint. These
are measured smoke-test results, not guarantees for all clip lengths or models.

Focused tests cover immutable plans, WAV truncation/duration, verified resume,
failure replay refusal and the served-file boundary. Browser checks cover
material/category filters, shortlist export, favourites, native WAV metadata
decoding, mobile overflow and JavaScript errors. Human sound selection remains
the purpose of the review page.

## Browser gameplay audition

The review page has a loop checkbox on every raw take and prepared sample. The
**Try it in motion** panel independently loads the prepared bank: choose a surface
and either shuffle its takes without replacement or repeat one variation. Walking
and running schedule individual contacts at 60–240 steps per minute. Skating uses
speed-driven loop volume/pitch, a powerslide toggle where a slide sample exists,
and a landing-hit button where a contact sample exists. Master volume is adjustable.
Surface/activity/variation changes, Stop, individual clip playback, library changes
and hiding the page stop the audition, including a session still loading its WAVs.

This is a browser simulation for listening decisions, not animation, physics,
spatialisation or multiplayer validation in the game. Footstep cadence is a stand-in
for animation foot-plant events; skate speed follows the existing response ranges
and slide playback represents the full slide angle. None of these candidates are
installed into runtime sound pools by this page.
