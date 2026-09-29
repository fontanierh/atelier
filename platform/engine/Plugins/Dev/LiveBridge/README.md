# LiveBridge (dev)

Lets an agent or a tool change the running game without a rebuild. Loopback HTTP on port 8830 (`-liveport=N`,
`-nolive`):

- `POST /python` runs Python in the game's shared namespace (uncooked editor-binary sessions only), where the game's
  helper module is imported as `live`.
- `GET /state` returns the player and camera transforms, the aim point, the live props and the frame rate.

`ULiveLibrary` (Python: `unreal.LiveLibrary`) has the game-independent verbs: world and player queries, ground and aim
traces, GLB props built at runtime (`SpawnModel`, cached per file), simulated input (`InputKey`), a fixed simulation
step for filming, screenshots, a line of text for the HUD (`Say`), and overlays (props saved to JSON and reloaded at
every start).

## What a game provides

- `[HTTPServer.Listeners] +ListenerOverrides=(Port=8830,BindAddress=localhost)` in its DefaultEngine.ini. The engine's
  default binds every interface; the bridge refuses to start (an error in the log) unless its port is on loopback.
- `[/Script/AtelierLive.AtelierLiveSettings]` in its DefaultGame.ini: `PropMaterial` (parameters `Tint` and `Tex`),
  `OverlayFolder`, `PythonFolder`, `PythonModule` (paths relative to the repository root), `Port`.
- A call to `AtelierLive::Start(World)` once the player is ready, and optionally `AtelierLive::SetTeleport(...)` to
  route teleports through its own travel.
- Its own verbs in its own function library (a `UBlueprintFunctionLibrary`), and a HUD that draws
  `ULiveLibrary::CurrentMessage`.

The CLI side is `atelier live state|py|shot` (`platform/studio/atelier/live.py`). The bridge has no authentication:
it only listens on loopback (checked at start), and must stay that way.
