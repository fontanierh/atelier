# AtelierCore

The base every Atelier game switches on. Experimental: it grows into the player shell and the activity interface
(ARCHITECTURE.md) as the engine code moves out of the first game.

| File | What |
|---|---|
| `AtelierData.h` | `AtelierDataPath("world.json")`: runtime files a game's build stages into `Content/Data` |
| `SprintStamina.h` | Stamina rings for a hold-to-sprint: duration per ring, refill delay, exhaustion latch, pause (pure C++, unit-tested by the first game) |
