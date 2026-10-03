# AtelierCore

The base plugin every Atelier game switches on: where a game's runtime data lives, and small pieces of player logic any
game can use. Header-only apart from the module itself; experimental.

| File | What |
|---|---|
| `AtelierData.h` | `AtelierDataPath("world.json")`: the full path of a runtime file the game's build stages into `Content/Data` (packaged as loose files: the game adds `+DirectoriesToAlwaysStageAsNonUFS=(Path="Data")` to its DefaultGame.ini) |
| `SprintStamina.h` | `FSprintStamina`, stamina rings for a hold-to-sprint: one to five rings, by default six seconds of sprint and three to refill per ring (a character may set its own), a 0.8 s refill delay, an exhaustion latch (no sprint once empty until full again and the button released) and a pause. `Use` spends rings at once or per frame (climbing, gliding, swimming, a charged attack). Pure C++, so a game can unit-test it without Unreal |
