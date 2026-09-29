# Streaming a game to a browser

`atelier stream <game> start|stop|status|build-web` runs the real game on this Mac, offscreen, and streams it to a
browser on another device: a phone, a handheld PC with a controller, a friend's computer. Pixel Streaming 2 sends
H.264 video and Opus audio over WebRTC through a local TURN relay (coturn); the pages come from a loopback web server.
Nothing listens on a public address: Tailscale Serve is the way in from other devices (HTTPS on 8443, the relay on
3479), and `--local` skips it for tests on this machine.

Streaming and the phone's touch UI are separate things:

| Page | Address | Input |
|---|---|---|
| the plain player (`player.html`, `player.js`) | `/play/` | the far device's own keyboard, mouse and gamepads, forwarded by Pixel Streaming as the game's input |
| a game's touch page (game.toml `[stream] touch_page`) | `/` | the game's own controls, sent as messages over the data channel |

Both pages can use the same stream (one viewer at a time). A game without a touch page serves the plain player at `/`
too. A native mobile build would be a third way to play and needs neither.

## Pieces

| File | What |
|---|---|
| `platform/studio/atelier/stream.py` | the launcher: TURN relay, web server, the game with the Pixel Streaming flags and `-AtelierStream`, memory guard, `caffeinate`, Tailscale Serve; `build-web` bundles the pages with esbuild |
| `server.cjs` | Epic's signalling server plus the pages, diagnostics and extra static routes, on loopback |
| `stream.js` | the browser connection: video, diagnostics, and the message channel keyed by the game's protocol name |
| `touch.js` | touch primitives for a game's page: stick, look pad, hold buttons, hold axes, keyboard, the 50 ms resend |
| `player.*` | the plain player page |
| `smoke.mjs`, `player-smoke.mjs` | the browser driver for the games' smoke tests; the plain player's own end-to-end check |
| `platform/engine/Plugins/Streaming` | the game's end (module AtelierStream): `FAtelierStream` routes action messages to the game's handlers and holds touch controls under a lease |

The packages (Epic's frontend and signalling libraries, express, esbuild, playwright-core) are pinned in
`platform/web/package-lock.json`; `build-web` runs `npm ci` there the first time.

## What a game provides

- **game.toml `[stream]`**: `protocol` (the key every message carries, `{"<protocol>": 1, ...}`), optionally
  `touch_page` (a folder with `index.html`, `client.js` and static files), `routes` (extra static folders from its build
  output, such as a map sheet), `video` (`width`, `height`, `fps`) and `args` (more game arguments).
- **DefaultGame.ini** `[/Script/AtelierStream.AtelierStreamSettings]`: the same `Protocol`, and `LeaseSeconds`.
- **In C++**, when `FAtelierStream::IsRequested()`: an `FAtelierStream` ticked every frame, with `OnAction(name, fn)`
  for the page's requests and `Send(player, json, kind)` for replies and status. `Tick()` returns the touch controls
  (`Move`, `Look`, `Buttons`, `Pressed`, `Released`, `bPaused`, `bActive`, `bLeaseExpired`); a game applies them only
  while `bActive`, so the plain player and the host's own keyboard keep working otherwise.

## Checks

With a stream running (`atelier stream <game> start --local`): `node platform/web/stream/player-smoke.mjs` holds W on
the plain player and checks through the live bridge that the player moved. Games keep their touch page's smoke tests
next to the page (`games/<game>/<touch_page>/*-smoke.mjs`). `STREAM_URL` points them at another address.

Browser diagnostics (connection states, errors; no SDP or credentials) go to `build/<game>/stream/diagnostics.jsonl`;
the game's log, the relay's and the server's are next to it.
