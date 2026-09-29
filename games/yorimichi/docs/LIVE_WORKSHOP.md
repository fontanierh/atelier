# Live workshop: changing the running game without a rebuild

> Moved from the prototype repository on 29 September 2026. Paths are translated to this repository where the file moved; paths still starting with `japan/` or `output/imagegen/` refer to the prototype archive (authoring tools, earlier revisions, review images). See [docs/MIGRATION.md](../../../docs/MIGRATION.md).

Started 24 September 2026. The game always runs uncooked, from the editor binary (`atelier play yorimichi` / `desktop`,
the phone stream too). That means three things are available inside the running game: Unreal's Python, the
engine's runtime glTF parser, and an HTTP server. The live workshop uses them so the agent can place new assets and
behaviours in the game you're playing, with nothing rebuilt or restarted.

## How it fits together

```
agent (Claude Code) ── atelier live (platform/studio/atelier/live.py) ──HTTP 127.0.0.1:8830──▶ the LiveBridge plugin in the game
                                                                     ├─ POST /python: runs code in the game's shared Python namespace
                                                                     └─ GET /state: player, camera, aim point, live props
      games/yorimichi/assets/props/make_prop.py: sentence ─▶ Sunburst concept ─▶ Tripo model ─▶ games/yorimichi/assets/props/<slug>/<slug>.glb
```

- **The LiveBridge plugin** (`platform/engine/Plugins/Dev/LiveBridge`, with Yorimichi's own verbs in `YorimichiLive.h/.cpp`) starts once the world is ready, only for the player. It listens on loopback only
  (`[HTTPServer.Listeners]` in `DefaultEngine.ini`); `-nolive` turns it off and `-liveport=` moves it.
  - It boots the in-game helper module and reloads every overlay.
  - `ULiveLibrary` holds the verbs Python calls, as `unreal.LiveLibrary.*`: spawn a GLB, find, remove, aim point,
    ground height, teleport, say a line on the HUD, screenshot, save and load overlays.
  - `ALiveProp` is a placed GLB.
- **Runtime GLB loading.** The engine's glTF reader (Interchange `GLTFCore`) parses the file. Every mesh node is
  merged into one static mesh, built in memory. Each glTF material becomes an instance of the world's
  `M_Painted`, with its base-colour texture and factor, so live props get the same matte painterly shading and
  distance haze as the baked world.
  - Loaded models are cached by file and modification time: overwrite a GLB and the next spawn picks it up.
  - A prop's origin is the middle of its footprint at its lowest point, so `Location` is where it stands.
  - Collision: `box` (default), `complex` or `none`.
- **`games/yorimichi/live/python/yorimichi_live.py`** is imported in the game as `live`. It gives short verbs in game
  units (cm and degrees): `live.spawn(id, glb, at=None|'aim'|(x, y), height=m, yaw=…)`, `live.move`,
  `live.remove`, `live.props()`, `live.here()`, `live.in_front(d, side)`, `live.save('workshop')`, `live.say()`,
  `live.shot()`, `live.teleport()`, `live.drive(forward, right, gait)` (hold the stick: 'walk', 'run' or
  'sprint'; `drive(0)` stops, and player input takes over) `live.sword()` (draw or sheathe) and `live.press('jump' | 'jump_release' | 'roll' | 'crouch')`.
  - `live.behave(name, fn)` runs `fn(dt)` every frame and replaces the function when it's registered again: hot
    behaviours. A behaviour that raises is dropped with a warning.
- **Overlays** live in `games/yorimichi/live/overlays/<name>.json`: id, GLB path, location, yaw, scale and collision for
  each prop. All overlays load on every start, so accepted work survives restarts without a bake. `workshop` is
  the default overlay.
- **`games/yorimichi/assets/props/make_prop.py`** makes a prop in two stages, so the concept can be checked before paying for a
  model.
  - `concept`: Sunburst (`gpt-image-2.5-sunburst`, high) with a fixed style preamble.
  - `model`: Tripo P2 image-to-model, 6,000-face default, colour texture. The task is resumed by id and never
    re-posted.
  - Run it with `~/.cache/yorimichi/imagegen-venv/bin/python` (it needs httpx). Keys come from `.env`.

## Using it

```sh
atelier play yorimichi                                            # the game, with the bridge
atelier live state
atelier live py "live.say('hello'); print(live.here())"
atelier live shot                             # build/yorimichi/live/shots/<time>.png
~/.cache/yorimichi/imagegen-venv/bin/python games/yorimichi/assets/props/make_prop.py concept stone_lantern "a weathered stone lantern ..."
~/.cache/yorimichi/imagegen-venv/bin/python games/yorimichi/assets/props/make_prop.py model stone_lantern
atelier live py "live.spawn('stone_lantern_1', 'games/yorimichi/assets/props/stone-lantern/stone_lantern.glb', at=live.in_front(500, -250), height=1.25); live.save()"
```

The first prop, on 24 September: a mossy stone lantern by the spawn road. The concept took about 40 s, the Tripo
model about 70 s (120 credits), and it was placed in the running game with no restart.

## Limits and next steps

- Live props are static meshes without Nanite, LODs or baked lighting. Keep to the face budget until they are
  baked. The bake step, which would import accepted overlay props through the normal pipeline, isn't built yet.
- Rigged and animated models (creatures, NPCs) aren't loaded yet. The skeleton path of the glTF reader is next.
- The desktop launcher refuses to start while `DefaultEngine.ini` differs from what's committed, so commit config
  changes before `atelier play yorimichi --profile desktop`.
- The bridge runs any Python the agent sends. It exists only in uncooked sessions and listens only on this Mac.
- Planned next: an in-game prompt box, new areas as "openings", and the bake to the normal pipeline
  (see the proposal in the chat of 24 September).
