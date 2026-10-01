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
`platform/web/package-lock.json`; `build-web` runs `npm ci` there the first time, and `start` runs it when the pages
are missing. The relay needs coturn (`brew install coturn`).

## Network

| Port | What | Listens on |
|---|---|---|
| 8080 | the pages, `/health` and `/diagnostics` (`server.cjs`) | loopback |
| 8888 | the game's signalling connection | loopback |
| 3478 | coturn | loopback |
| 54000–54100 | TURN relay ports | loopback |
| 8443 | Tailscale Serve HTTPS (and WSS) to the pages | the tailnet |
| 3479 | Tailscale Serve TCP forwarder to coturn | the tailnet |

`ATELIER_STREAM_HTTP_PORT`, `ATELIER_STREAM_STREAMER_PORT`, `ATELIER_STREAM_TURN_PORT` and `ATELIER_STREAM_RELAY_MIN`
move the loopback ports, and `ATELIER_STREAM_OUTPUT` the output folder, so a second stream can run beside the first
with `--local`; `stop` and `status` need the same environment.

- Every connection goes through the relay (`iceTransportPolicy: relay`). Remote browsers use TURN over TCP through the
  3479 forwarder; the game uses TURN over UDP on loopback. Direct TURN to the Mac's Tailscale address stalls, which is
  why the forwarder exists. Both peers take relay ports on loopback, so relay-to-relay traffic stays on the Mac.
- coturn accepts loopback peers only and a credential generated at each start, kept in mode-0600 files
  (`peer-options.json`, `turn.conf`) in the output folder.
- The game runs offscreen with backbuffer capture, H.264 keyframes every 120 frames (VideoToolbox needs a positive
  interval), a 3 Mbps starting bitrate adapting between 0.5 and 8 Mbps, and the frame rate of game.toml `video`.
  `caffeinate` keeps the Mac awake for as long as the game runs, and the memory guard stops the game above 10 GiB.
- `server.cjs` accepts one viewer at a time (`maxSubscribers: 1`): a hidden test tab holds the slot too.
- `FAtelierStream::Send` replies to one page with `SendPlayerMessage`: UE 5.8's broadcast holds the participants lock
  during a synchronous RTC send and deadlocks against incoming data.
- Devices need Tailscale connected. TCP and relayed Tailscale paths can add latency on lossy mobile links.
  `tailscale serve --tcp=3479 off` removes the forwarder.

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
