# Yorimichi on a phone

The phone page: touch controls, the world map, settings and the stamina gauge for Yorimichi streamed from the Mac. The
Mac runs the real Unreal game; Safari receives H.264 video and Opus audio over WebRTC, and the page sends touch controls
back over the data channel. No iOS build or Apple signing is needed, but the Mac must stay awake, online and running the
stream. The streaming itself (the launcher, the web server, the TURN relay, the network, the browser connection) is the
platform's: [platform/web/stream](../../../platform/web/stream/README.md). The same stream also serves the platform's
plain player at `/play/`, for a device with its own keyboard, mouse or controller (a handheld PC, a friend's computer).

## Start and stop

```sh
brew install coturn
atelier build yorimichi
atelier stream yorimichi build-web      # installs platform/web's packages the first time (npm ci)
atelier stream yorimichi start          # --local: this machine only, no Tailscale Serve
atelier stream yorimichi status
atelier stream yorimichi stop
```

Connect the iPhone to the same Tailscale network, open the HTTPS address printed by `start` in Safari
(`https://<your-mac>.<your-tailnet>.ts.net:8443/`), turn the phone sideways and tap Play. The plain player is the same
address with `/play/`.

The game streams at 1280×720 with a 60 fps cap (game.toml `[stream] video`); the stream does not change saved
settings. Only one player can connect at a time, and even a hidden test tab holds the slot: close test tabs before
handing the link to the phone.

A second stream can run next to the live one with other ports, for example
`ATELIER_STREAM_HTTP_PORT=8180 ATELIER_STREAM_STREAMER_PORT=8988 ATELIER_STREAM_TURN_PORT=3578 ATELIER_STREAM_RELAY_MIN=54200 atelier stream yorimichi start --local`
(then `STREAM_URL=http://127.0.0.1:8180` for the smoke tests). `stop` and `status` need the same environment.

## Home screen

Safari → Share → Add to Home Screen → enable Open as Web App → Add, then launch the Yorimichi icon with Tailscale
connected. The manifest asks for a standalone landscape display, and safe-area padding keeps controls clear of the
notch and home indicator. iOS controls its own system bars and orientation, so the page cannot hide Safari's browser
chrome; the Full screen button uses the browser's fullscreen API where it exists and shows these instructions
elsewhere.

## Controls

| Control | Does |
| --- | --- |
| Left stick | move; Walk (hold) slows down, Sprint (hold) uses stamina |
| Drag on the right | camera, tracked separately so you can steer and look at once (the settings' look sensitivity applies) |
| Jump | jump; tap again in the air for the double jump |
| Dash | dash forward on the ground or once in the air; one-second cooldown, landing restores the air dash |
| Roll | roll |
| Use | interact. It reads Fly at a zeppelin stop with the zeppelin docked, Call ship when it is elsewhere, and Skip flight aboard |
| Slower / Faster | flight speed aboard the zeppelin; before boarding they read ‹ Stop / Stop › and choose the destination |
| Sailboat | launch the sailboat near the shore; it reads Step ashore while sailing (only near a safe landing) |
| ◀ ▶, Raise sail, Lower sail | while sailing, in place of the stick: steer, cruise, stop. Menus and a lost connection stop the boat |
| Wave | wave |
| Back to spawn | return to the starting road on foot, clearing momentum and queued jumps, and leave the sailboat |
| Map | the painted world map with numbered places and an arrow where you are. Tap a pin or a list entry to travel there: the game stows the board or sailboat and lands you on the ground |
| Settings | every preference of the game's Esc menu (camera, graphics, art, world lighting, FPS display), with values and limits from the game; a change applies when the slider is released and is saved in the same file as the desktop menu |

The page has no skateboard controls: the board reads the far device's controller or keyboard directly, so skate through
`/play/`. For testing on a computer the page also takes WASD, mouse drag, Space (jump), F (dash), E (use), K
(sailboat), Q (wave), J (walk), Shift (sprint) and Ctrl (roll).

The map sheet is `/map/map.jpg`, served from `build/yorimichi/map` (game.toml `[stream] routes`) and built by the
`world.map` step ([docs/WORLD_MAP.md](../docs/WORLD_MAP.md)); the places and your position come from the game.

A cancelled touch, hiding the page, losing focus or disconnecting releases the controls. The page resends its state
every 50 ms, and the game holds touch controls under a 0.6 s lease (`LeaseSeconds` in `DefaultGame.ini`): when
messages stop it releases them and brakes the sailboat. Touch controls exist only in a streamed game (`-AtelierStream`)
and apply only while the page sends them, so the plain player and the host keyboard keep working otherwise. The game
accepts only bounded numeric fields and known action bits, and exposes no console commands.

## Files

| File | What |
| --- | --- |
| `index.html`, `style.css`, `manifest.webmanifest`, `icon-*.png` | the page and its home-screen manifest |
| `client.js` | the connection, the touch controls and the status the game sends back |
| `map.js`, `settings.js`, `stamina.js` | the map, settings and stamina panels |
| `*-smoke.mjs` | the smoke tests below |

## Smoke tests

With a stream running (`atelier stream yorimichi start --local`), each test drives a real Chrome at phone size over
WebRTC and checks the game's own telemetry; reports and screenshots go to `build/yorimichi/`. Run them with
`node games/yorimichi/phone/<name>-smoke.mjs`; `STREAM_URL` points them at another address.

| Test | Checks |
| --- | --- |
| `jump-smoke.mjs` | multi-touch stick and jump: a held single jump, the double jump, a third tap refused |
| `map-smoke.mjs` | the map sheet, pins and player marker, travel from a pin and from the list, back to spawn |
| `map-scroll-smoke.mjs` | touch gestures on the map alone, without the game |
| `settings-smoke.mjs` | every setting against the game's answers and the saved file, then restored (the session-only `desktop` switch is left alone) |
| `sailboat-smoke.mjs` | launch, steer, raise and lower the sail, step ashore |
| `sprint-smoke.mjs` | sprint stamina and its rings |
| `forest-lake-smoke.mjs` | the woodland lake and its pier |
| `performance-smoke.mjs LABEL` | sampled native frame rate and decoded video throughput, at idle and running forward with sprint |

`performance-smoke.mjs` is a manual diagnostic, not a guarantee of the frame rate on a physical iPhone: it takes the
single player slot, refuses an occupied session, returns the player to spawn and always closes its browser.
`node platform/web/stream/player-smoke.mjs` checks the plain player on the same stream.

Sources: [Epic setup](https://dev.epicgames.com/documentation/en-us/unreal-engine/getting-started-with-pixel-streaming-in-unreal-engine),
[Epic infrastructure](https://github.com/EpicGamesExt/PixelStreamingInfrastructure/tree/UE5.8),
[Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve).
