# AtelierStream

The game's end of a browser stream (module `AtelierStream`). Pixel Streaming 2 carries the video and the page's
UI-interaction messages; this plugin reads those messages as JSON under the game's protocol key, runs the game's
handlers for named actions, and turns the rest into touch controls held under a lease, so a phone that goes quiet
cannot leave a button pressed. Experimental (version 0.1); it depends on PixelStreaming2. The launcher, the relay and
the pages are in [platform/web/stream](../../../web/stream/README.md), which also covers the network and the checks.

## What a game provides

- **DefaultGame.ini** `[/Script/AtelierStream.AtelierStreamSettings]`:

  | Setting | What |
  | --- | --- |
  | `Protocol` | the key every message carries, `{"<Protocol>": 1, ...}`; the same name as game.toml `[stream] protocol` (default `atelier`) |
  | `LeaseSeconds` | touch controls are let go when their messages stop for this long (default 0.6) |

- **In C++**, when `FAtelierStream::IsRequested()` (the game was started with `-AtelierStream`, as
  `atelier stream <game> start` does): an `FAtelierStream` made with `MakeShared` and ticked every frame, usually
  owned by the game's phone controller.

## API

| Piece | What it does |
| --- | --- |
| `OnAction(Name, Fn)` | runs `Fn(Player, Message)` on the game thread for a message whose `action` is `Name` |
| `Tick()` | connects to the default streamer once it exists, runs the lease, and returns the `FAtelierTouchControls` since the last call |
| `FAtelierTouchControls` | `Move` (stick, -1..1, y forward), `Look` (drag since the last read), `Buttons`, `Pressed`, `Released` (a mask whose bits the game defines), `bPaused`, `bActive`, `bLeaseExpired` |
| `Send(Player, Message, Kind)` | a reply to one page, with the protocol key and `kind` added |
| `ResetControls(KeepButtons)` | forgets movement and held buttons without reporting them released (after a teleport) |
| `GetPlayer`, `SecondsSinceInput`, `IsTouchActive` | the page that sent controls last, and how recently |

## Behaviour

- A message without an `action` must carry finite `x`, `y`, `dx`, `dy` and an integer `buttons` mask of 0 to 65535,
  or it is ignored, as are messages over 2048 characters or without the protocol key set to 1. `paused` zeroes the
  controls. `x, y` are clamped to the unit disc and each `dx`, `dy` to ±30.
- When the lease runs out, every held button is reported `Released` once, with `bLeaseExpired` set, and the state is
  cleared. A game applies the controls only while `bActive`, so the plain player, whose keyboard, mouse and gamepads
  reach the game as its own input, and the host's keyboard keep working otherwise.
- `Send` uses `SendPlayerMessage` to one page rather than a broadcast: UE 5.8's broadcast holds the participants lock
  during a synchronous RTC send and deadlocks against incoming data.
- The previous `UIInteraction` handler is put back when the `FAtelierStream` is destroyed.

## Testing

Start a stream with `atelier stream <game> start --local`, then run `node platform/web/stream/player-smoke.mjs` for
the plain player, or the smoke tests beside a game's touch page (`games/<game>/<touch_page>/*-smoke.mjs`). The log lines
`ATELIER STREAM input ready` and `ATELIER STREAM input timeout: released controls` show the connection and the lease.
