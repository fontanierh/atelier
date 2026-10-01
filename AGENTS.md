# Working rules

Atelier builds 3D games with Unreal Engine 5.8 and Blender from scripts and AI tools. [README.md](README.md) says what
is here and how to build it; [ARCHITECTURE.md](ARCHITECTURE.md) says how the parts fit.

## Layout

- `platform/`: `studio/` (the `atelier` command, Python), `engine/Plugins/` (Unreal plugins), `web/` (stream pages,
  motion helpers), `conventions/` (units, bone contract, clip roles, sound cues). Platform files never name a game.
- `games/<game>/`: `game.toml` (play profiles, fetches, stream), `build.py` (build steps), `unreal/`, `world/`,
  `assets/`, `scenarios/`, `docs/`. `yorimichi` is the full game; `sandbox` is the template for `atelier new`.

```sh
uv run atelier build <game> [step ...]   # incremental; --list shows the steps
uv run atelier play <game> [--profile P]
uv run atelier qa <game> <scenario>      # scripted checks against the running game
uv run atelier live state|py "..."|shot  # talk to the running game
uv run atelier lint                      # public-repository checks
uv run pytest                            # studio and game Python tests
```

## Repository

- The repository is **public**. Never commit credentials, tokens, personal hostnames or home-directory paths, and
  never commit third-party files whose licence forbids redistribution (Sonniss sounds, raw Mixamo downloads, licensed
  music). `atelier lint` checks the common cases; run it before pushing.
- Before every commit, run `atelier lint` and read `git diff`. The Unreal editor rewrites `Config/*.ini` when it starts
  (it can add the Android file server's generated token): keep only the changes you meant.
- Commit and push completed work at task boundaries, before starting the next task.
- Never prefix pull request titles with `[codex]` unless explicitly asked.
- Generated files go in `build/<game>/` or the game's ignored `unreal/Content/`, never next to sources. The tracked
  `unreal/Content/Data/SkateNative` bundle is source data: keep it when clearing `Content/`.
- Keep only the current revision of a source in git. Older revisions, captures and evidence go to the archive.

## Credentials and paid calls

- API keys live in the ignored repository-root `.env` (`OPENAI_API_KEY`, `AI_GATEWAY_API_KEY`, `TRIPO_API_KEY`;
  template in `.env.example`). `atelier.env.load()` reads them into the environment. Never print their values.
- Every paid call goes through `atelier.ai.ledger`: it is recorded before and after, and never retried blindly.

## Images

- Use **GPT Image 2.5 Sunburst** (`gpt-image-2.5-sunburst`) with `quality=high` for new concepts, reference sheets,
  textures and map paintings, unless the task calls for another quality. Never silently substitute another model.
- Record the model and prompt of every generated image in its provenance file.

## Animation reference videos

- Prefer **H3 Max at 480p** (`minimax/minimax-h3-max` through the Vercel AI Gateway) for cost; use Seedance only when
  its quality justifies it. Both clients are in `platform/studio/node/`.
- An H3 prompt states the appearance and camera, ordered and timed phases, support contacts, airborne impulses,
  rotation direction and count, and the recovery. Always require **constant framing** (no zoom, the character stays
  the same size) and **real-time speed** (no slow motion). Inspect the motion before accepting a take.
- Generated video is a reference for animation authored locally in Blender, never the animation itself.

## Heavy jobs

- Heavy jobs (Unreal, Blender renders) run under the render lock and memory guard (`atelier.safety`). `atelier play`
  and `atelier build` do this for you.
- The render lock has one big slot. A small slot sits beside it when `~/.cache/atelier/render-slots.json` says
  `{"slots": 2}` (`ATELIER_RENDER_SLOTS` overrides the file; no file means one slot). The small slot takes a job
  expected to peak at 3 GiB or less, never a game or a compile, when at least 10 GiB is free and the big slot's job is
  in another checkout; its memory ceiling is 4 GiB. `atelier build` sends a heavy step there when the step's last
  guard report allows it, and says which slot each step used. A compile waits for a small job to finish.
- A checkout whose code predates the slots stays safe but refuses to start while a small job runs: merge main into
  every checkout before switching to two slots.
- The live bridge (Unreal plugin, port 8830) stays loopback-only.
