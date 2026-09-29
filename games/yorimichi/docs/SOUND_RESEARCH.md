# Sound for Yorimichi — what we can generate, and with what

> Moved from the prototype repository on 29 September 2026. Paths are translated to this repository where the file moved; paths still starting with `japan/` or `output/imagegen/` refer to the prototype archive (authoring tools, earlier revisions, review images). See [docs/MIGRATION.md](../../../docs/MIGRATION.md).

Research pass, 2026-09-14. Scope: **sound effects only** — footsteps, wind, foliage,
water, cloth, bells, combat hits, UI. No music (that is a separate pass later).

The game has no audio at all today: nothing under `unreal/JapanProto/Content/**` is a
sound asset, and no doc in `games/yorimichi/docs/` covers audio. So this is a clean start.

---

## 1. What we actually need

Three different jobs, and they do not want the same tool:

| Job | Examples | What matters |
| --- | --- | --- |
| **One-shots** | footstep on gravel / wood / grass, sword hit, jump land, roll, UI click, bell strike | short (0.2–1.5 s), needs **many variations** so it does not machine-gun |
| **Loops / beds** | wind in trees, cicadas, river, village murmur, rain on a roof | must loop **seamlessly**, 10–30 s, stereo |
| **One-offs / signature** | the big temple bell, the spirit "opening" sound, the zeppelin | few of them, worth hand-picking or hand-editing |

A rough first count for the current world: ~8 surface types × ~6 footstep variations
(~50 files), ~15 ambience loops, ~40 combat/traversal one-shots, ~20 UI/objects.
Call it **~150–250 files** for a first full pass.

Important: we do **not** need to generate 6 footstep variations per surface if Unreal's
MetaSounds does the variation for us (random pitch/volume/start offset, round-robin over
2–3 source files). That cuts the generated file count by roughly half and sounds better
than 6 slightly-different AI takes.

---

## 2. The landscape, provider by provider

### ElevenLabs — the only mature text-to-SFX API. Front-runner.

- Product: **Sound Effects v2** (`eleven_text_to_sound_v2`), the current model as of
  Aug 2026 (no v3). Launched Sept 2025; it added 30 s length, looping and 48 kHz.
- API: `POST /v1/sound-generation`. Parameters that matter to us:
  - `text` — the prompt
  - `duration_seconds` — 0.5 to 30 s; omit it and the model picks
  - `loop` — **seamless looping**, v2 only. This is the feature that makes ambience beds
    practical.
  - `prompt_influence` — 0..1, default 0.3. Higher = literal, lower = more variety.
    This is also our "give me another take" knob for variations.
  - `output_format` — MP3 (22–44.1 kHz) or **PCM/WAV up to 48 kHz** (48 kHz WAV is
    non-looping output only), plus Opus/µ-law. PCM 48 kHz needs Creator/Pro tier.
- Cost: the API pricing page headlines **$0.12/min**. In credits it is 200 credits for an
  auto-length effect, or 40 credits/second if you set the length. On Creator ($22 for
  220k credits) that is roughly **$0.02 per auto-length effect**, ~$0.004/second.
  A full 200-file pass is therefore **$5–15**, not a budget line item.
- Licence: on **paid** plans you own the output and can use it commercially, perpetually,
  no attribution. Free plan cannot be used commercially. One real restriction to know:
  you may not sell or distribute SFX output **on a standalone basis** — as isolated files,
  samples, or a sound library. Shipping them inside the game is exactly the allowed case;
  publishing "Yorimichi SFX pack" would not be.
- Weakness: no layer editing. If a generated sound is 90% right you regenerate, you do not
  fix it. Budget for a 3–5× regeneration ratio on the sounds that matter.

### Google — no text-to-SFX product. Not usable for this.

- **Lyria** (2, 3, 3 Pro, 3.5 on Vertex AI / Gemini API) is a **music** family — songs,
  stems, up to ~3 min, with SynthID watermarking. Not sound effects, and we are not doing
  music yet.
- **Gemini TTS** (2.5 TTS preview) is speech only. Inline tags like `[laughs]` are speech
  performance, not foley.
- **Veo 3 / 3.1** does generate real sound effects and ambience at 48 kHz stereo — but
  only **welded to a video clip**. To get a footstep you would render 4–8 s of video and
  strip the audio: expensive, slow, no length control, no loop flag, and the audio is
  mixed with whatever else is in the shot. Interesting later for a **trailer**, useless
  for a game SFX library.
- There is no Vertex or Gemini endpoint equivalent to ElevenLabs' `sound-generation`.
  Google is the weakest option here today.

### Suno — no official API; the in-app "Sounds" tool is decent.

- Suno **still has no public self-serve API** in 2026. There is an intake form and a
  "partner powered model"; access is selective, no public keys, no docs, no GA date.
- The third-party "Suno APIs" (sunoapi.org, unifically, aimlapi, etc.) are unofficial
  wrappers. They quote ~$0.01/SFX generation, but they are reverse-engineered access:
  ToS risk, no uptime guarantee, and no clean licence chain for a commercial game. **Do
  not build our pipeline on those.**
- What *is* usable: Suno's **Sounds** feature in the web app, with **One Shot** mode
  (hits, clicks, impacts, transitions) and **Loop** mode (ambience, drones, beds). Good
  for hand-picking a few signature sounds manually. Not automatable.
- Suno is fundamentally a music model. Keep it on the list for **later**, when we do music
  and the adaptive/BPM-locked stuff.

### Vercel AI Gateway — checked live. No sound-effect models at all.

I pulled `https://ai-gateway.vercel.sh/v1/models` (no auth needed). 376 models, typed as:

```
language 253 · video 35 · image 33 · embedding 26 · speech 9 · transcription 9 · realtime 6 · reranking 5
```

There is **no `audio` or sound-generation model type**. The audio side of the gateway is:

- `speech` = text-to-**speech** only: Fish Audio s1 / s2-pro / s2.1-pro, OpenAI tts-1/1-hd, Grok TTS
- `transcription` = Whisper, GPT-4o transcribe, Gemini 3.5 Transcribe
- `realtime` = voice agents (GPT-Realtime, Grok Voice)
- `video` = Veo 3/3.1, Kling, Seedance, Wan, Grok Imagine — these carry audio, same caveat as above

The AI SDK's own model filters only know `language / embedding / reranking / image / video`.
**Conclusion: the gateway cannot generate sound effects.** No ElevenLabs SFX, no Stable
Audio. If we want one key and one bill we need a different aggregator (see fal below).

### Stability AI — good second source, and the only self-hostable one worth using

- **Stable Audio 2.5 / 3.0** (hosted API): music, soundscapes and SFX from text, ~20 credits
  per result, up to 3 min. Trained on **fully licensed** data (WMG/UMG partnerships), which
  is the cleanest provenance story of anything here.
- **Stable Audio Open**: open weights on Hugging Face, explicitly aimed at **short samples,
  sound effects and production elements**, trained on Freesound + Free Music Archive.
  Stability AI Community License — **free commercial use under $1M revenue**. We can run it
  locally on the Mac and generate unlimited takes for free.
- Quality on discrete foley is below ElevenLabs, but it is strong on **texture and
  ambience**, and free local iteration is genuinely useful for the "generate 40, keep 3"
  workflow.

### fal.ai — the aggregator that actually has SFX

- Hosts **ElevenLabs Sound Effects v2** (`fal-ai/elevenlabs/sound-effects/v2`) as a plain
  HTTP API with a queue, alongside the rest of the ElevenLabs suite.
- Also hosts **MMAudio v2** in both `text-to-audio` and video-to-audio form. The
  video-to-audio mode is the interesting one long term: feed it a gameplay capture and it
  produces audio synced to the motion. Worth an experiment for the trailer, not for the
  asset library.
- Useful if we want one key + queue + batch instead of talking to ElevenLabs directly.
  Slight markup, one more party in the licence chain. Direct ElevenLabs is simpler.

### Open-weight also-rans

- **Meta AudioCraft / AudioGen** — free, self-host, but clearly behind the 2026 models.
  Only worth it if we want zero external dependency.
- Research models (Foley-Omni, FolAI, AC-Foley, 2026 papers) do **video-synced foley** and
  are the direction this is all heading, but none ship a usable API yet.

### The non-AI baseline we should not skip

Generating everything is not obviously the right call for footsteps and impacts, where
recorded foley still wins:

- **Sonniss GDC Game Audio Bundle** — free, ~7.5 GB for 2026, and a community archive of
  **200 GB+** across nine years. Worldwide, royalty-free, commercial use, unlimited
  projects, **no attribution**. Explicitly licensed for games. (One clause to respect: no
  using it for AI/ML training.)
- **Freesound** — huge, but mixed CC licences per file; needs per-file bookkeeping. Use
  only for something we cannot get elsewhere.

---

## 3. Recommendation

**Primary: ElevenLabs Sound Effects v2 via the direct API.** It is the only provider with a
real text-to-SFX endpoint, a loop flag, 48 kHz output, per-generation cost in cents, and a
licence that plainly covers shipping sounds inside a game.

Around it:

1. **Sonniss bundle as the reality anchor** for footsteps, cloth, impacts — recorded foley,
   free, and it stops the whole game sounding synthetic.
2. **Stable Audio Open locally** for free bulk iteration on ambience and texture, and as
   the fallback if ElevenLabs' take on something is wrong five times running.
3. **MetaSounds in Unreal for variation** — random pitch/gain/round-robin. Generate 2–3
   source files per footstep surface, not 6.
4. **Google and Suno: not now.** Revisit Suno when we do music, and Veo/MMAudio when we cut
   a trailer.

## 4. Proposed pipeline (next step, not done yet)

Mirrors how the rest of this repo works — a manifest plus a tool:

- `games/yorimichi/docs/SFX_MANIFEST.md` (or a JSON/YAML next to it): one row per sound —
  id, category, prompt, duration, loop yes/no, target surface/event.
- `japan/tools/sfx_gen.py` — reads the manifest, calls the ElevenLabs API, writes
  48 kHz WAV into `japan/audio/raw/<category>/<id>_take<N>.wav`. Idempotent, skips existing,
  `--takes N` to generate alternates for picking.
- `japan/tools/sfx_post.py` — trim silence, normalise to a target LUFS, verify loop points
  on `loop` assets, convert to the format Unreal wants.
- Import into `Content/Japan/Audio/`, wrap each family in a MetaSound that randomises.
- A contact-sheet-style review page (same idea as the animation/asset reviews) so sounds can
  be auditioned against the clip they belong to before anything is committed.

First slice worth doing to prove it out: **footsteps on 3 surfaces + wind loop + one bell**,
maybe 10 files, under $1, and hear it in the build.

**Status: footsteps are in the game.** 531 one-shots across 7 surfaces, sliced from the
Sonniss masters and played from the character's foot bones —
[FOOTSTEPS.md](FOOTSTEPS.md) covers the integration, and
[`audio/footsteps/README.md`](../audio/footsteps/README.md) the library itself. One licence constraint that
lands directly on the plan above: the Sonniss licence **forbids AI use of those files**,
so they can never be fed to ElevenLabs or Stable Audio as audio-to-audio input. Text
prompts describing the sound we want are fine; the recordings themselves are not.

## 5. Open questions

- Middleware: plain Unreal audio + MetaSounds, or Wwise/FMOD? MetaSounds is enough for what
  this game does, and it avoids a licence and a build step. Recommend staying native.
- Do we want a "painterly" sound identity to match the art — slightly stylised, few layers,
  strong silence — or naturalistic? That changes every prompt we write.
- Bells: the lore has all the bells ringing at once. That is probably a hand-built layered
  sound, not a single generation.

## Sources

- ElevenLabs: [sound effects docs](https://elevenlabs.io/docs/overview/capabilities/sound-effects), [create sound effect API](https://elevenlabs.io/docs/api-reference/text-to-sound-effects/convert), [API pricing](https://elevenlabs.io/pricing/api), [commercial rights summary](https://terms.law/ai-output-rights/elevenlabs/)
- Google: [Lyria 3 on Vertex AI](https://cloud.google.com/blog/products/ai-machine-learning/lyria-3-and-lyria-3-pro-on-vertex-ai), [Lyria model page](https://deepmind.google/models/lyria/), [Gemini speech generation](https://ai.google.dev/gemini-api/docs/speech-generation), [Veo 3.1 API](https://ai.google.dev/gemini-api/docs/veo)
- Suno: [no official API (2026)](https://tunova.ai/guides/is-there-an-official-suno-api), [developer API exploration](https://www.musicbusinessworldwide.com/suno-explores-developer-api-seeking-apps-that-unlock-experiences-generative-music-makes-possible-for-the-first-time/), [Suno Sounds guide](https://jackrighteous.com/en-us/blogs/guides-using-suno-ai-music-creation/suno-sounds-ai-sound-effects-guide)
- Vercel: [AI Gateway models and providers](https://vercel.com/docs/ai-gateway/models-and-providers), live model list at `https://ai-gateway.vercel.sh/v1/models`, [realtime voice/speech changelog](https://vercel.com/changelog/realtime-voice-speech-and-transcription-now-supported-on-ai-gateway)
- Stability: [Stable Audio Open](https://stability.ai/news-updates/introducing-stable-audio-open), [Stable Audio 2.5 API](https://www.pixazo.ai/models/audio-generation/stable-audio-2-5-api)
- fal: [ElevenLabs sound effects v2](https://fal.ai/models/fal-ai/elevenlabs/sound-effects/v2/api), [MMAudio v2 text-to-audio](https://fal.ai/models/fal-ai/mmaudio-v2/text-to-audio/api)
- Libraries: [Sonniss GDC bundle](https://gdc.sonniss.com/), [Sonniss archive](https://sonniss.com/gameaudiogdc/)
