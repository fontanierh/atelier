# Inventory

Every feature and world row V2 must restore, from [plan §11](../../../docs/YORIMICHI_V2_PLAN.md). This page is the
status index. Source evidence for each row, including old file and package locations, runtime loads, candidate
checks and known gaps, is in [inventory/features.md](inventory/features.md) and [inventory/world.md](inventory/world.md).
Both were read from the source baseline `7eec0f98dd` (DECISIONS D01).

**Status:** `not started`, `in progress`, `blocked`, `ready for review`, `accepted` (with the merge revision and
evidence), or `deferred by owner`. A row is accepted only with revision-bound evidence; a film or a compile alone
never accepts a row. **Baseline:** the source's state: implemented, partial (some of it is unverified or only
proposed), or disabled.

## Facts that shape the whole port

- **The island is built at runtime.** The saved map `/Game/Japan/Maps/Slice` holds only terrain cells, background
  hills, the road set, lighting and the PlayerStart. `AJapanGameMode::BeginPlay` spawns `AJapanWorld`, which reads
  `Content/Data/world.json` and `hidamari/city.json` on every start. It places about 390k instanced trees, props
  and region pieces, plus the sea and sky, and spawns about 15 region and service actors. V2 converts the static
  part once, into saved One File Per Actor actors with stable IDs. It then removes those spawners and keeps the
  dynamic services (plan §6).
- **Runtime clean-ups must be baked in:** pier clearance, the Ronin camp clearing and the floating-tree trace
  (inventory/world.md §0).
- **Excluded code is tangled into the player:** the kart is a default sub-object of `AWandererCharacter`
  (`CreateDefaultSubobject<UDrivingComponent>("CarRide")`). Removing it changes a serialized class: the saved
  character Blueprints must be load-tested (plan §4).
- **V2 needs its own identity:** a different `ProjectName` so its Saved state (settings, markers, racing saves)
  cannot overwrite the original game's, and a network build ID computed from V2's own folders.
- **ElectraPlayer stays:** the music library plays MP3 through it (`JapanMusic.cpp:194`).
- **Rights:** see DECISIONS D05. The owner cleared Mega Park's assets on 2026-11-08, so it is ported in full;
  Sonniss-derived sounds go to restricted storage.

## Gameplay and shared systems

| ID | Coverage | Area | Baseline | Depends on | V2 status |
| --- | --- | --- | --- | --- | --- |
| F01 | Cairo, Modori, Nox, Paul: rigs, textures, clothes, equipment | Player and characters | implemented | — | not started |
| F02 | Walk, run, sprint, jumps, crouch, climb, swim, glide, wave, interact | Player and characters | implemented | F01 | not started |
| F03 | Chase camera, see-through, first-person seats, collisions | Presentation | implemented | F02 | not started |
| F04 | Sword combat | Combat | implemented | F01, F02 | not started |
| F05 | Fox hunter, Kaede's trainer, Ronin camp | Combat | implemented (offline only) | F04, W01, W13 | not started |
| F06 | Flick-It skating | Skating | implemented | F01, Skate plugin | not started |
| F07 | Board carry/stow, markers, ride record/replay | Skating | partial: no player UI for replay | F06 | not started |
| F08 | Bike | Travel | implemented | F01, W00 | not started |
| F09 | Sailboat | Travel | implemented | F01, W00 | not started |
| F10 | Horse: six breeds, tack, appearance | Travel | implemented | F01 | not started |
| F11 | Zeppelin: **four** stations (Woodland, Hidamari, Mega Park, Belmonte) | Travel | implemented | W19 | not started |
| F12 | Belmonte train, stations, interior, seats | Travel | implemented | W16, W20 | not started |
| F13 | Ferry | Travel | implemented | W17 | not started |
| F14 | Gondola | Travel | implemented | W18 | not started |
| F15 | Horse racing, calendar, broadcasts, saves | Racing | implemented | F10, W15, W16 | not started |
| F16 | Villagers and ambient actors | Player and characters | implemented: movement only, no interactions found | W02, W07 | not started |
| F17 | Desktop menus, English text, hints, settings | Presentation | implemented: the phone profile must be removed | — | not started |
| F18 | Painted world map, travel points | Presentation | implemented | W00–W20 | not started |
| F19 | Footsteps, combat and vehicle sounds | Presentation | partial: no train or sailboat sounds found | D05 restricted audio | not started |
| F20 | Zone music director, optional library | Presentation | implemented | external music release | not started |
| F21 | Painterly materials, sky, sea, foliage, effects | World | implemented | W00 | not started |
| F22 | Multiplayer | Network | partial: local two-process tests only | F02–F14 | not started |
| F23 | Live bridge, QA, dev tools | Presentation/Dev | implemented: single port 8830 | P2-C | not started |
| F24 | Runtime data, saves, startup, packaging | World/Presentation | implemented | — | not started |
| F25 | Crater Park tower hoist | Travel | implemented | W12 | not started |
| F26 | Mega Park standalone level and game mode | World | implemented | W11 | blocked (D05) |
| F27 | In-game Dev mode and notes | Presentation/Dev | implemented | F17 | not started |
| F28 | Friends sessions over Tailscale | Network | implemented | F22 | not started |
| F29 | Hair spring, cloth, seat correctives | Player and characters | implemented | F01 | not started |
| F30 | Train departure boards | Travel | implemented | F12 | not started |
| F31 | Kei cars as static car-park dressing (not driving) | World | implemented | W11 | blocked (D05) |
| F32 | Trailer, benchmark and building-review modes | Presentation/Dev | implemented | F23 | not started |

Only proposals exist for the canteen lady, the tide-reader and player betting or stables. They are not
migration requirements (plan §11).

## Every world region and connection

| ID | Area | Baseline reaches the game by | V2 status |
| --- | --- | --- | --- |
| W00 | Island foundation: terrain, coast, sea, background, roads | saved Slice map (terrain cells, road set) plus runtime sea and sky | not started |
| W01 | Start, coastal road, houses | runtime `world.json` | not started (P3 slice) |
| W02 | Momiji Hamlet village | runtime | not started |
| W03 | Mini Mega ramp | runtime `AMegaRamp` | not started |
| W04 | Sunset Pier skate plaza | runtime `ASkatePark` from `park.json` | not started (P3 slice) |
| W05 | Forest | runtime | not started |
| W06 | Forest lake | runtime | not started |
| W07 | Hidamari | runtime (`city.json`, city surface tiles) | not started |
| W08 | Southwest | runtime | not started |
| W09 | Brinecove | runtime `ABelmonteRegion` | not started |
| W10 | Tree house | runtime pieces | not started |
| W11 | Super Ultra Mega Park and its own map | runtime plus its own level | blocked: rights (D05) |
| W12 | Volcano and Crater Park | runtime | not started (license to record, D05) |
| W13 | Sword camp | runtime | not started |
| W14 | Hidamari stable | **disabled at baseline** (`AHidamariStable::bEnabled = false`) | not started (keeps the baseline state; DECISIONS D06) |
| W15 | Hippodrome | runtime | not started |
| W16 | Belmonte | runtime | not started |
| W17 | Ferry route | runtime services | not started |
| W18 | Gondola route | runtime services | not started |
| W19 | Zeppelin route (four stations) | runtime | not started |
| W20 | Railway and cross-region routes | runtime track and train | not started |

## Explicit exclusions

| ID | Deferred by owner | V2 action | Status |
| --- | --- | --- | --- |
| X01 | Phone streaming, Pixel Streaming, touch controls | Not ported. Plugins disabled in `YorimichiV2.uproject`; `YorimichiPhone`, the stream hooks in `WandererCharacter`, `JapanHUD`, `JapanGameMode` and the phone profile in `JapanPreferences` are removed from the V2 copy | deferred by owner |
| X02 | Go-kart driving | Not ported. `Driving` disabled; `CarRide`, `JapanKartGrip`, kart HUD, animation and live hooks, and `/Game/Japan/Kart` stay out of V2 | deferred by owner |
| X03 | Browser and mobile ports, Hakuba rendering experiments | Not implemented | deferred by owner |
| X04 | New gameplay, engine upgrade, new art direction | Separate future work | deferred by owner |
