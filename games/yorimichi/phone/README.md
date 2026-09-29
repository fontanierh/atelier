# Yorimichi on a phone

The phone page: touch controls, the world map, settings and the stamina gauge for Yorimichi streamed from the Mac. The
streaming itself (the launcher, the web server, the TURN relay, the browser connection) is the platform's:
[platform/web/stream](../../../platform/web/stream/README.md). The same stream also serves the platform's plain player at
`/play/`, for a device with its own keyboard, mouse or controller (a handheld PC, a friend's computer).

The Mac runs the actual Unreal game. Safari receives H.264 video and Opus audio over WebRTC; this page sends touch
controls back over the data channel. No iOS build or Apple signing is needed. The Mac must stay awake, online and
running the stream.

## Start and stop

```sh
brew install coturn
atelier build yorimichi
atelier stream yorimichi build-web      # installs platform/web's packages the first time (npm ci)
atelier stream yorimichi start          # --local: this machine only, no Tailscale Serve
atelier stream yorimichi status
atelier stream yorimichi stop
```

A second stream can run next to the live one with other ports (and, in the same checkout, another output folder):
`ATELIER_STREAM_HTTP_PORT=8180 ATELIER_STREAM_STREAMER_PORT=8988 ATELIER_STREAM_TURN_PORT=3578 ATELIER_STREAM_RELAY_MIN=54200 atelier stream yorimichi start --local`
(then `STREAM_URL=http://127.0.0.1:8180` for the smoke tests). `stop` and `status` need the same environment.

Connect the iPhone to the same Tailscale network, open the HTTPS address printed by `start` in Safari, turn the phone
sideways and tap Play: `https://<your-mac>.<your-tailnet>.ts.net:8443/`. The plain player is the same address with `/play/`.

The launcher runs a 1280×720 game with a 60 FPS cap (game.toml `[stream] video`), H.264, an adaptive 0.5–8 Mbps
bitrate (3 Mbps starting point), and `caffeinate` tied to the game process. This is a cap, not a measured performance
guarantee. It does not change saved game settings. Only one player can subscribe at a time. Close agent-created live
play tabs after verification and before handing the link to the phone; even a hidden test tab holds the slot.

## iPhone screen space

Safari → Share → Add to Home Screen → enable Open as Web App → Add. Close the Safari play tab and launch the Yorimichi icon, with Tailscale connected. The manifest requests standalone landscape display; safe-area padding protects the notch and home indicator. iOS controls its system bars and orientation, so the page cannot force Safari browser chrome away. The Full screen button opens these instructions on unsupported browsers, or uses the browser fullscreen API where available.

## Controls

- Settings: all Esc menu preferences, including camera, graphics, art, world lighting, FPS display. Values and limits come from Unreal; changes apply on slider release and persist in the same settings file as the desktop menu. Look sensitivity also controls phone dragging.
- Map: the painted world map with numbered places and a pulsing arrow where you are (heading included). Tap a pin or a list entry to travel there; the game stows the board or sailboat and lands you on the ground at that place. The sheet is `/map/map.jpg` from `japan/out/map` (see `docs/WORLD_MAP.md`), the places and your position come from the game.
- Back to spawn: return to the starting road on foot, clear momentum and queued jump input, and leave sailing.
- On foot: left stick to move; Walk slows down and Sprint uses stamina. Sailboat mode uses left/right steering and raise/lower sail buttons.
- Drag right side: camera, with independent pointer tracking so you can steer and look at the same time.
- Dash: move forward on ground or once in the air. One-second cooldown; landing restores air dash. The separate double jump stays available if unused.
- Use: interact, climb the mini-mega ladder, begin the drop-in.
- Sailboat: launch near shore; left/right steer, Raise sail cruises, Lower sail stops. Step ashore only near a safe landing; menus and connection loss stop the boat. Wave and Walk are also available; Walk slows movement on foot while running remains the default.
- Desktop testing: WASD, mouse drag, Space, B, E, K, Q, Shift.

Pointer cancellation, page hiding, lost focus and disconnect release controls. A native 600 ms lease also releases inputs and brakes equipped travel items when messages stop. The touch controls exist only in a streamed game (`-AtelierStream`) and apply only while the page sends them, so the plain player and the host keyboard keep working otherwise; the game accepts only bounded numeric input fields and known action bits, and exposes no console-command interface.

## Network and implementation

The platform's `server.cjs` wraps Epic's UE5.8 signalling library with HTTP and streamer listeners bound to loopback (`8080` and `8888`). Tailscale Serve proxies private HTTPS/WSS on port `8443`. The video/data transport is WebRTC, separate from the HTTPS proxy. Coturn listens on loopback port 3478. A second Tailscale Serve TCP forwarder exposes port 3479 to the tailnet and forwards to coturn. Remote browsers use TURN over this TCP forwarder; Unreal uses local TURN/UDP. Direct TURN traffic addressed to the Mac's Tailscale interface stalled, while the Serve forwarder passed allocation and data exchange tests. Both peers allocate loopback relay ports (54000–54100), so relay-to-relay traffic stays on the Mac. TURN permits only loopback peers and requires a fresh password generated at each start, stored in ignored, mode-0600 runtime files. Devices need their Tailscale VPN enabled. TCP and relayed Tailscale connections can add latency on lossy 5G links. Remove the TURN forwarder with `tailscale serve --tcp=3479 off`.

Browser diagnostics record connection states and error messages in `build/yorimichi/stream/diagnostics.jsonl`; they omit SDP and TURN credentials. Play does not restart a connection that is still negotiating. Reconnect reloads the page after a failure.

The launcher uses backbuffer capture and H.264 keyframes at a positive 120-frame interval accepted by VideoToolbox. Native telemetry uses `SendPlayerMessage`: UE5.8's broadcast API holds the participants lock during a synchronous RTC send, which deadlocked against simultaneous incoming touch messages in testing.

The frontend and signalling packages are pinned in `package-lock.json`. A custom frontend is bundled with esbuild. Unreal's public Pixel Streaming 2 input-handler API receives the UI-interaction protocol; engine files are not modified. Logs, generated pages and process state live under `build/yorimichi/stream/`.

## Verification

With a local stream (`atelier stream yorimichi start --local`), each test drives a real Chrome at phone size over
WebRTC and checks the game's own telemetry; reports and screenshots go to `build/yorimichi/`:

- `jump-smoke.mjs`: multi-touch stick and jump: a held single jump, the double jump, a third tap refused.
- `map-smoke.mjs`: the map sheet, pins and player marker, travel from a pin and from the list, back to spawn.
- `settings-smoke.mjs`: every setting against the game's answers and the saved file, then restored (the session-only
  `desktop` switch is left alone).
- `sailboat-smoke.mjs`: launch, steer, raise and lower the sail, step ashore.
- `sprint-smoke.mjs`, `forest-lake-smoke.mjs`: sprint stamina and rings; the woodland lake and its pier.
- `map-scroll-smoke.mjs`: touch gestures on the map alone, without the game.
- `performance-smoke.mjs`: decoded video and native frame rate at idle and running (a manual diagnostic).

`node platform/web/stream/player-smoke.mjs` checks the plain player (`/play/`) on the same stream. Last run on the
fresh Atelier build (29 September 2026): jump, map, settings, sailboat and the plain player pass. The phone page has no
skateboard controls: the board reads the far device's controller or keyboard directly, so skate through `/play/`.

Sources: [Epic setup](https://dev.epicgames.com/documentation/en-us/unreal-engine/getting-started-with-pixel-streaming-in-unreal-engine), [Epic infrastructure](https://github.com/EpicGamesExt/PixelStreamingInfrastructure/tree/UE5.8), [Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve).

## Character lighting performance follow-up (September 14)

The phone profile shares instance occlusion culling with desktop. At the user's request the screen-probe lighting change was subsequently reverted: performance mode again uses the original medium irradiance-volume gather. When reading `PROFILE`, `gi_gather=0` means the logged screen-probe budgets are inactive. See [measurements and limitations](../docs/WARM_ORIGINAL_STREAM_PERFORMANCE.md).

`STREAM_URL=https://<your-mac>.<your-tailnet>.ts.net:8443/ node games/yorimichi/phone/performance-smoke.mjs LABEL` measures sampled native FPS and decoded video throughput separately at idle and under forward+sprint input. It uses the single player slot, refuses an occupied session, requests return to spawn and always closes its browser. Run before handing the stream to the user; it is a manual diagnostic, not a guarantee of physical-iPhone FPS.
