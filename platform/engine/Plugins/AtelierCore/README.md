# AtelierCore

The base plugin every Atelier game switches on: where a game's runtime data lives, and small pieces of player logic any
game can use. Experimental.

| File | What |
|---|---|
| `AtelierData.h` | `AtelierDataPath("world.json")`: the full path of a runtime file the game's build stages into `Content/Data` (packaged as loose files: the game adds `+DirectoriesToAlwaysStageAsNonUFS=(Path="Data")` to its DefaultGame.ini); `AtelierReadJson(Path)`: the JSON object in a file, or null when it is missing or not an object |
| `AtelierExit.h` | `AtelierRequestExit(Status)`: quit through the normal engine shutdown with that process exit status. A scripted run (QA, a review, a capture) reports its failure this way; on Mac UE's own `RequestExitWithStatus` exits 0 whatever the status |
| `AtelierSettings.h` | A game's saved settings, one `key=value` per line in `Saved/settings.txt` or the file `-preferencesfile=` names: `FilePath`, `ReadFile`, `WriteFile` (through a sibling file renamed over the old one, so a failed write keeps it) and `Overrides`, the `-set=a=1;b=2` that `atelier play GAME --set "a=1;b=2"` passes. What the keys mean is the game's |
| `SprintStamina.h` | `FSprintStamina`, stamina rings for a hold-to-sprint: one to five rings, by default six seconds of sprint and three to refill per ring (a character may set its own), a 0.8 s refill delay, an exhaustion latch (no sprint once empty until full again and the button released) and a pause. `Use` spends rings at once or per frame (climbing, gliding, swimming, a charged attack). Pure C++, so a game can unit-test it without Unreal |
