# Yorimichi module

The original game's `Yorimichi` C++ module, ported to saved V2 scenery and split into feature folders
(plan §7). The module name and every reflected type keep their names, so saved packages still resolve
`/Script/Yorimichi.X`. Every folder is on the module's private include path (`Yorimichi.Build.cs`), so
`#include "X.h"` works from any folder. Go-kart (X02) and phone streaming (X01) were removed.

| Folder | Area (plan §7) | Holds |
| --- | --- | --- |
| `Player/` | Player and characters | Wanderer and mover characters, movement, move set, anim instance and nodes, roster, character select/switch, fit |
| `Combat/` | Combat | Sword, combat resolver, defence timeline, encounters, fox hunter, sword trainer and Ronin camp, combat FX |
| `Skating/` | Skating | Skate park, mega ramp, Super Ultra Mega Park |
| `Travel/` | Travel | Bike, sailboat, horse, zeppelin, Belmonte train and track, ferry, gondola, Crater Park tower, transport riders/audio |
| `Racing/` | Racing | Racing service, course, motion, broadcast, hippodrome |
| `World/` | World | Game mode, JapanWorld, regions and pieces, city surfaces, gameplay collision, atlas data, village life, gulls, leaves, looks |
| `Presentation/` | Presentation | Camera arm, see-through, HUD, preferences, map and atlas widget, markers, music, footsteps, desktop viewport |
| `Network/` | Network | Session, net driver, Tailscale, movement prediction, network state, reactions, skate pose transport, activity handoff |
| `Dev/` | Presentation (dev tools) | Reviews, benchmark, trailer, dev notes, QA drivers and probes, live-bridge verbs (`YorimichiLive`) |
| `Tests/` | Owner of the tested feature | Automation tests only |

## Serialized changes

These were removed from saved classes. The four playable-character Blueprints have been cleaned of the
excluded component in the merged city/train work. Fresh-load and package evidence is revision-bound;
[the inventory](../../../docs/INVENTORY.md) tracks current implementation and final acceptance separately:

- `AWandererCharacter`: the default subobject `CarRide` (`UDrivingComponent`) and its `UPROPERTY() Car`.
  Stale `BP_<Name>` overrides must not be reintroduced; they no longer have a native subobject.
- `UYorimichiLive`: the Blueprint-callable functions `CarState`, `CarFlip`, `CarRide` and `CarLoops`.
- `UJapanPreferences`: the `desktop` preference (V2 always uses the desktop profile). It is still ignored in
  `settings.txt` and `-set=` like the retired `haze` and `supersample` keys.

The other removed members (`PhoneInput`, car camera blend and effect timers) were not reflected.
