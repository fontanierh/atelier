# Working rules

## Repository

- This repository is **public**. Never commit credentials, tokens, personal hostnames or home-directory paths, and
  never commit third-party files whose licence forbids redistribution (Sonniss sounds, raw Mixamo downloads, licensed
  music). `atelier lint` checks for the common cases; run it before pushing.
- Run `atelier lint` and look at `git diff` before every commit. The Unreal editor rewrites `Config/*.ini` when it
  starts (it once added the Android file server's generated token); keep only the changes you meant.
- Commit and push completed work at task boundaries before starting the next task.
- Never prefix pull request titles with `[codex]` unless explicitly asked.
- Generated files belong in `build/<game>/` or the game's ignored `unreal/Content/`, never next to sources.
- Keep only the current revision of a source in git. Older revisions, captures and evidence go to the archive.

## Credentials

- API keys live in the ignored repository-root `.env` (`OPENAI_API_KEY`, `AI_GATEWAY_API_KEY`, `TRIPO_API_KEY`;
  template in `.env.example`). `atelier.env.load()` reads them into the environment. Never print their values.
- Every paid call goes through `atelier.ai.ledger`: it is recorded before and after, and never retried blindly.

## Image generation

- Use **GPT Image 2.5 Sunburst** (`gpt-image-2.5-sunburst`) for new concepts, reference sheets, textures and map
  paintings, with `quality=high` unless the task calls for another quality. Do not silently substitute another model.
- Keep the model and prompt of every generated image in its provenance file.

## Animation reference videos

- Prefer **H3 Max at 480p** (`minimax/minimax-h3-max` via the Vercel AI Gateway) because of cost; keep Seedance for
  when its quality justifies it (`platform/studio/node/`).
- H3 prompts need appearance and camera, ordered and timed phases, support contacts, airborne impulses, rotation
  direction and count, and recovery. Always require **constant framing** (no zoom, the character stays the same size)
  and **real-time speed** (no slow motion). Inspect the motion before accepting a take.
- Generated video is a reference for locally authored Blender animation, never the animation itself.

## Running things

- Heavy jobs (Unreal, Blender renders) go through the render lock and memory guard (`atelier.safety`). `atelier play`
  and `atelier build` do this for you.
- The render lock has one big slot, and a small one beside it when `~/.cache/atelier/render-slots.json` says
  `{"slots": 2}` (`ATELIER_RENDER_SLOTS` overrides it; no file means one slot). The small slot takes a job expected to
  peak at 3 GiB or less, never a game or a compile, when at least 10 GiB is free and the big slot's job is in another
  checkout; its memory ceiling is 4 GiB. `atelier build` sends a heavy step there when its last guard report allows
  it and says which slot each step used. A compile waits for a small job to finish. Code older than the slots stays
  safe but refuses to start while a small job runs, so merge main in every checkout before switching to two.
- The live bridge (Unreal plugin, port 8830) stays loopback-only.
