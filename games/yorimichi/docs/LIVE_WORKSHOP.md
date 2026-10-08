# Live workshop

The live workshop changes the running game without a rebuild or restart: the agent places new props, moves them,
drives the player and adds small per-frame behaviours while you play. The game runs uncooked from the editor binary
(`atelier play yorimichi`, every profile, and the phone stream), so Unreal's Python, the engine's glTF reader and an
HTTP server are all available inside it. The platform's [LiveBridge plugin](../../../platform/engine/Plugins/Dev/LiveBridge/README.md)
puts them behind a loopback HTTP server on port 8830; the game's side lives in `games/yorimichi/live/`.

```
agent ── atelier live ── HTTP 127.0.0.1:8830 ──▶ LiveBridge in the game
                                                 ├─ POST /python: code in the game's shared Python namespace
                                                 └─ GET /state: player, camera, aim point, live props, fps
make_prop.py: sentence ─▶ Sunburst concept ─▶ Tripo model ─▶ games/yorimichi/assets/props/<slug>/<slug>.glb
```

## Using it

```sh
atelier play yorimichi                     # the game, with the bridge
atelier live state                         # player, camera, aim point, live props
atelier live py "live.say('hello'); print(live.here())"
atelier live py - < script.py              # Python from stdin
atelier live shot [out.png]                # screenshot; default build/live/shots/<time>.png
```

Making and placing a prop:

```sh
uv run python games/yorimichi/assets/props/make_prop.py concept paper-lantern "a red paper lantern on a short post"
uv run python games/yorimichi/assets/props/make_prop.py model paper-lantern
atelier live py "live.spawn('paper-lantern-1', 'games/yorimichi/assets/props/paper-lantern/paper-lantern.glb', at=live.in_front(500, -250), height=1.25); live.save()"
```

`atelier live` exits with 1 when the game is unreachable or the Python raised.

## In the game

The character starts the bridge once the world is ready, for the player only, and routes its teleports through the
game's own travel. The bridge listens on loopback only (`[HTTPServer.Listeners]` in `DefaultEngine.ini`) and refuses
to start, with an error in the log, when its port is not bound to loopback. On start it imports the helper module and
loads every overlay.

`-nolive` on the Unreal command line turns the bridge off. `-liveport=N` moves it, for a second game running beside the
first; add `-ini:Engine:[HTTPServer.Listeners]:DefaultBindAddress=localhost` so the new port is loopback too (as
`tools/review_megapark.py` does). `atelier live` always talks to port 8830.

The bridge's settings are in `DefaultGame.ini` under `[/Script/AtelierLive.AtelierLiveSettings]`:

| Setting | Value |
| --- | --- |
| `PropMaterial` | `/Game/Japan/Materials/M_Painted` (the world's painterly material) |
| `OverlayFolder` | `games/yorimichi/live/overlays` |
| `PythonFolder` | `games/yorimichi/live/python` |
| `PythonModule` | `yorimichi_live`, imported as `live` |
| `Port` | 8830 |

Verbs come from three function libraries: the game's `unreal.YorimichiLive` (`YorimichiLive.h/.cpp`: player input,
the sword, skating, film HUD, camera hold), the platform's `unreal.LiveLibrary` (props, traces, screenshots, overlays,
HUD text, test boxes, GPU frame time) and `unreal.AtelierFXLibrary` (audio logging). The helper module looks a verb up
in that order.

### Runtime props

A prop is a GLB loaded while the game runs. The engine's glTF reader (Interchange `GLTFCore`) parses it and every mesh
node is merged into one static mesh built in memory. Each glTF material becomes an instance of `M_Painted` with its
base-colour texture and factor, so a live prop gets the same matte painterly shading and distance haze as the baked
world.

- Models are cached by file and modification time: overwrite a GLB and the next spawn picks it up.
- A prop's origin is the middle of its footprint at its lowest point, so its location is where it stands.
- Collision is `box` (default), `complex` or `none`.

### The `live` module

`games/yorimichi/live/python/yorimichi_live.py`, imported in the game as `live`. It builds on the bridge's
game-independent `atelier_live` module (`platform/engine/Plugins/Dev/LiveBridge/Python/`), which supplies the
placement helpers and `behave`/`stop`. Units are Unreal's (centimetres, degrees); paths are relative to the repository
root.

| Function | Does |
| --- | --- |
| `here()`, `player()`, `ground(x, y)`, `in_front(distance=300, side=0)`, `aim()`, `size(glb)` | where things are |
| `spawn(id, glb, at=None, yaw=None, scale=None, height=None, collision='box', overlay='workshop')` | place a GLB: `at` is 3 m in front of the player by default, `'aim'` for where the camera looks, or a ground point `(x, y)`; `height` in metres scales it; `yaw` faces the player by default |
| `move(id, at, yaw)`, `remove(id)`, `props()` | edit placed props |
| `save(overlay='workshop')` | write the overlay to disk |
| `say(text, seconds=4)` | a line of text on the HUD |
| `teleport(at, yaw)` | move the player |
| `drive(forward, right, gait)` | hold the stick (−1 to 1, camera-relative) with gait `'walk'`, `'run'` or `'sprint'`; `drive(0)` stops and player input takes over |
| `press(button)` | `'jump'`, `'jump_release'`, `'roll'`, `'crouch'` (toggles), `'interact'`, `'stop_previous'`, `'stop_next'` |
| `sword()` | draw or sheathe the sword |
| `skate()`, `skate_input(...)`, `skate_release()`, `skate_state()`, `skate_place(at, yaw)`, `skate_park()`, `skate_script(steps)`, `flick(trick)` | get on the board and ride it from scripts ([SKATE.md](SKATE.md)) |
| `shot(path=None)` | screenshot, by default into `build/yorimichi/live/shots/` |
| `behave(name, fn)`, `stop(name=None)` | run `fn(dt)` every frame under a name; registering the name again replaces it. A behaviour that raises is dropped with a warning |

### Overlays

`games/yorimichi/live/overlays/<name>.json` lists each prop's id, GLB path, location, yaw, scale and collision. Every
overlay loads at each start, so accepted props survive restarts without a bake. `workshop` is the default overlay; it
holds a stone lantern by the spawn road
([assets/props/stone-lantern](../assets/props/stone-lantern/asset.toml)).

## Making a prop

`games/yorimichi/assets/props/make_prop.py` makes a prop in two stages, so the concept can be checked before paying for
a model:

- `concept <slug> "<description>"`: a GPT Image 2.5 Sunburst image (`gpt-image-2.5-sunburst`, quality high) with a
  fixed style preamble (an isolated object on a plain background).
- `model <slug> [--faces 6000]`: Tripo P2 image-to-model with a colour texture. The task is submitted once and resumed
  by id; an uncertain request is never repeated.
- `make <slug> "<description>"`: both, without stopping.

Everything lands in `games/yorimichi/assets/props/<slug>/`: `concept.png`, `prompt.txt`, `provenance.json`, `job.json`,
`raw/` (the Tripo outputs, ignored) and `<slug>.glb`, the file to place. Keys come from the environment or the ignored
`.env`: `OPENAI_API_KEY` and `TRIPO_API_KEY`.

## Limits

- Live props are static meshes without Nanite, LODs or baked lighting; keep to the face budget. There is no step that
  bakes accepted overlay props into the normal pipeline.
- Rigged and animated models (creatures, characters) do not load.
- The bridge runs any Python the agent sends and has no authentication. It exists only in uncooked sessions and
  listens only on loopback.
