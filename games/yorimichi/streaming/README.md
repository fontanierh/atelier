The default player is now Warm Original. On foot: WASD / left stick run, Alt or J / Walk slows down, Shift / Sprint speeds up, Space / Jump jumps again in the air, and F / Dash moves forward on the ground or once in the air. Skateboarding is disabled. Rebuild the character with `japan/run.sh warm-original` before starting the stream. See [game integration](../docs/WARM_ORIGINAL_GAME_INTEGRATION.md).

# Yorimichi on a phone

The Mac runs the actual Unreal game. Safari receives H.264 video and Opus audio over WebRTC; a private Tailscale HTTPS page sends touch controls back over its data channel. No iOS build or Apple signing is needed. The Mac must stay awake, online and running the stream.

## Start and stop

```sh
brew install coturn
atelier build yorimichi
python games/yorimichi/streaming/run.py build-web
python games/yorimichi/streaming/run.py start
python games/yorimichi/streaming/run.py status
python games/yorimichi/streaming/run.py stop
```

A second checkout can run its own private test stream next to the live one by overriding the ports for both `run.py` and `server.cjs`: `YORIMICHI_HTTP_PORT=8180 YORIMICHI_STREAMER_PORT=8988 YORIMICHI_TURN_PORT=3578 YORIMICHI_RELAY_MIN=54200 python games/yorimichi/streaming/run.py start --local` (then `STREAM_URL=http://127.0.0.1:8180` for the smoke tests). `stop` and `status` need the same environment.

Connect the iPhone to the same Tailscale network, open the HTTPS address printed by `start` in Safari, turn the phone sideways and tap Play. This Mac's address is `https://<your-mac>.<your-tailnet>.ts.net:8443/`.

The launcher runs a 1280×720 game with a 60 FPS cap, H.264, an adaptive 0.5–8 Mbps bitrate (3 Mbps starting point), and `caffeinate` tied to the game process. This is a cap, not a measured performance guarantee. It does not change saved game settings. Only one player can subscribe at a time. Close agent-created live play tabs after verification and before handing the link to the phone; even a hidden test tab holds the slot. Leave the recorded review open instead. The launcher stores and verifies its own PIDs; stopping this stream does not stop another checkout's playtest. `stop` leaves the private HTTPS proxy configured for the next start. Remove just this proxy with `tailscale serve --https=8443 off` if desired.

## iPhone screen space

Safari → Share → Add to Home Screen → enable Open as Web App → Add. Close the Safari play tab and launch the Yorimichi icon, with Tailscale connected. The manifest requests standalone landscape display; safe-area padding protects the notch and home indicator. iOS controls its system bars and orientation, so the page cannot force Safari browser chrome away. The Full screen button opens these instructions on unsupported browsers, or uses the browser fullscreen API where available.

## Controls

- Settings: all Esc menu preferences, including camera, graphics, art, world lighting, FPS display. Values and limits come from Unreal; changes apply on slider release and persist in the same settings file as the desktop menu. Look sensitivity also controls phone dragging.
- Map: the painted world map with numbered places and a pulsing arrow where you are (heading included). Tap a pin or a list entry to travel there; the game stows the board or sailboat and lands you on the ground at that place. The sheet is `/map/map.jpg` from `japan/out/map` (see `docs/WORLD_MAP.md`), the places and your position come from the game.
- Back to spawn: return to the starting road on foot, clear momentum and queued jump input, and leave skating/sailing/custom ramp movement.
- On foot: left stick to move; Walk slows down and Sprint uses stamina. Sailboat mode uses left/right steering and raise/lower sail buttons.
- Drag right side: camera, with independent pointer tracking so you can steer and look at the same time.
- Dash: move forward on ground or once in the air. One-second cooldown; landing restores air dash. The separate double jump stays available if unused.
- Use: interact, climb the mini-mega ladder, begin the drop-in.
- Sailboat: launch near shore; left/right steer, Raise sail cruises, Lower sail stops. Step ashore only near a safe landing; menus and connection loss stop the boat. Wave and Walk are also available; Walk slows movement on foot while running remains the default.
- Desktop testing: WASD, mouse drag, Space, B, E, K, Q, Shift.

Pointer cancellation, page hiding, lost focus and disconnect release controls. A native 600 ms lease also releases inputs and brakes equipped travel items when messages stop. Native phone input runs only with `-phonestreaming`, preserves ordinary desktop controls otherwise, accepts only bounded numeric input fields and known action bits, and exposes no console-command interface.

## Network and implementation

`server.cjs` wraps Epic's UE5.8 signalling library with HTTP and streamer listeners bound to loopback (`8080` and `8888`). Tailscale Serve proxies private HTTPS/WSS on port `8443`. The video/data transport is WebRTC, separate from the HTTPS proxy. Coturn listens on loopback port 3478. A second Tailscale Serve TCP forwarder exposes port 3479 to the tailnet and forwards to coturn. Remote browsers use TURN over this TCP forwarder; Unreal uses local TURN/UDP. Direct TURN traffic addressed to the Mac's Tailscale interface stalled, while the Serve forwarder passed allocation and data exchange tests. Both peers allocate loopback relay ports (54000–54100), so relay-to-relay traffic stays on the Mac. TURN permits only loopback peers and requires a fresh password generated at each start, stored in ignored, mode-0600 runtime files. Devices need their Tailscale VPN enabled. TCP and relayed Tailscale connections can add latency on lossy 5G links. Remove the TURN forwarder with `tailscale serve --tcp=3479 off`.

Browser diagnostics record connection states and error messages in ignored `phone-diagnostics.jsonl`; they omit SDP and TURN credentials. Play does not restart a connection that is still negotiating. Reconnect reloads the page after a failure.

The launcher uses backbuffer capture and H.264 keyframes at a positive 120-frame interval accepted by VideoToolbox. Native telemetry uses `SendPlayerMessage`: UE5.8's broadcast API holds the participants lock during a synchronous RTC send, which deadlocked against simultaneous incoming touch messages in testing.

The frontend and signalling packages are pinned in `package-lock.json`. A custom frontend is bundled with esbuild. Unreal's public Pixel Streaming 2 input-handler API receives the UI-interaction protocol; engine files are not modified. Logs, generated frontend and PID state live under `japan/out/pixel-streaming/` and are ignored by git.

Ordinary skating now caps at 50.4 km/h (previously 30.6), with substantially lower rolling resistance and stronger contact-driven pushes. Uphill slopes and collisions still remove speed; downhill slopes add it. The existing mini-mega surface and air motion are unchanged.

## Verification

The historical skateboard harness `node games/yorimichi/streaming/smoke.mjs` predates Warm Original and is not a current-character acceptance test. It connects a real Chrome WebRTC receiver at phone dimensions, checks decoded video, drives the character and skateboard, checks an ollie, checks spawn return on foot and mid-ollie (including a held-button single-trigger check), and saves screenshots plus actual RTC statistics. Set `STREAM_URL` to test the private HTTPS endpoint. It controls the running game, so use it before handing the session to the player.

September 6 local relay test passed: touch running moved 8.5 m, skateboard motion and airborne ollie telemetry passed, and Chrome decoded 706 frames at 1280×720 (55 FPS at the final sample), with zero packet loss and zero recorded freezes. Disconnect triggered the native input timeout. Private HTTPS responds successfully. Safari-compatible WebKit also received continuous video through the HTTPS/Tailscale TCP route. The user subsequently confirmed live iPhone Safari playback with an in-game screenshot; the FPS measurements above remain local receiver measurements, not an iPhone/5G benchmark.

`node games/yorimichi/streaming/map-smoke.mjs` opens the map, checks the sheet, pins and player marker, travels to the clock square from a pin and to the island landing from the list, verifies the game's position each time and the marker sitting on the travelled pin, then returns to spawn.

`node games/yorimichi/streaming/settings-smoke.mjs` checks all 19 settings against native responses and saved values, exercises the phone slider, and compares actual running distances at 1× and 1.8×. It restores the original settings and returns to spawn afterwards.

`node games/yorimichi/streaming/skate-smoke.mjs` follows the road while testing multi-touch steering/pushing, speed buildup beyond the old cap, coasting retention and simultaneous Push/Brake priority. It returns the character to spawn afterwards. Verified on the road: a sustained Push reached 1,400 cm/s (50.4 km/h); three seconds coasting retained 95.3% of speed (1,360.9 → 1,296.5 cm/s); holding Brake and Push together stopped at 0 cm/s.

Before streaming, all feature branches were merged to main, including the southwest island/kite work and the complete harbor. The combined native build and southwest import passed. A fresh city audit checked 6,039 ground samples, 6,039 capsule sweeps, 567 bridge samples and three water tests with no errors.

Sources: [Epic setup](https://dev.epicgames.com/documentation/en-us/unreal-engine/getting-started-with-pixel-streaming-in-unreal-engine), [Epic infrastructure](https://github.com/EpicGamesExt/PixelStreamingInfrastructure/tree/UE5.8), [Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve).

For a second stream in the **same checkout**, also set `YORIMICHI_STREAM_OUTPUT`
to a separate absolute output directory. This isolates process state, TURN
credentials, logs and built web files. Use the same output-directory and port
overrides for `start --local`, `status` and `stop`; local testing does not alter
the live Tailscale route.

## Character lighting performance follow-up (September 14)

The phone profile shares instance occlusion culling with desktop. At the user's request the screen-probe lighting change was subsequently reverted: performance mode again uses the original medium irradiance-volume gather. When reading `PROFILE`, `gi_gather=0` means the logged screen-probe budgets are inactive. See [measurements and limitations](../docs/WARM_ORIGINAL_STREAM_PERFORMANCE.md).

`STREAM_URL=https://<your-mac>.<your-tailnet>.ts.net:8443/ node games/yorimichi/streaming/performance-smoke.mjs LABEL` measures sampled native FPS and decoded video throughput separately at idle and under forward+sprint input. It uses the single player slot, refuses an occupied session, requests return to spawn and always closes its browser. Run before handing the stream to the user; it is a manual diagnostic, not a guarantee of physical-iPhone FPS.
