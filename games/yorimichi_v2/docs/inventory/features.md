# Yorimichi V2 inventory — features (F01–F24, X01–X04)

Source: `the baseline checkout` at baseline `7eec0f98dd` (read-only). All paths are
relative to `games/yorimichi/` unless they start with `platform/`. "Src/" = `unreal/Source/Yorimichi/`.
Check labels: **[A]** automated assertion, **[V]** visual review, **[P]** performance measurement.
Status words: implemented / proposed / unverified / excluded (evidence given). This is source evidence only; it was
not reconciled against release `yorimichi-macos-2026-10-23-r13`.

## Cross-cutting facts

- **Modules:** `Yorimichi` (Runtime, 182 .cpp, 55,957 lines), `YorimichiAssets` (Runtime, 188 lines, saved data
  types), `YorimichiImport` (UncookedOnly editor import code, 629 lines). Targets: `Yorimichi`, `YorimichiEditor`,
  `YorimichiServer` (dedicated server target exists, `unreal/Source/YorimichiServer.Target.cs`).
- **Plugins (`unreal/Yorimichi.uproject`):** HorseRacing (game plugin, 10,634 lines), EnhancedInput,
  PythonScriptPlugin, EditorScriptingUtilities, Interchange, AtelierCore, AtelierAnimation, LiveBridge, AtelierFX,
  Skate (`platform/engine/Plugins/Activities/Skate`, about 91.5k lines), and the excluded **PixelStreaming2 (l.48),
  Driving (l.80), AtelierStream (l.84)**. **ElectraPlayer (l.88) is not phone-only: `JapanMusic.cpp:194-195` uses
  it to play the MP3 music library (F20). Keep it.**
- **One integration point registers world services.** `AJapanGameMode::BeginPlay` (`Src/JapanGameMode.cpp:55-66`)
  spawns `AJapanWorld`, the fox hunter, Kaede and the Ronin camp. `AJapanWorld` (`Src/JapanWorld.cpp:813-932`)
  spawns VillageLife, Zeppelin, MegaRamp, SkatePark, Mega Park and Crater Park (`ASuperUltraMegaPark::Spawn`),
  CraterCloud, Hippodrome, HidamariStable, Belmonte and Brinecove (`ABelmonteRegion`), BelmonteTrack and Train,
  Ferry, Gondola, RacingService, RacingBroadcast, LeafStorm and GullFlock. Nearly all are placed at runtime from
  `Content/Data/*.json`. The Slice map holds only engine actors (`Scripts/setup_project.py`). This is the V2 "single
  integration owner" seam.
- **Runtime data (loose files, `DirectoriesToAlwaysStageAsNonUFS=Data`):** `AtelierDataPath(...)` reads
  `world.json`, `terrain/island.json`, `map/map.json`, `map/atlas-serif.ttf`, `village/atomic-manifest.json`,
  `hidamari/city.json`, `city_surface_tiles/v1_128m/manifest.json`, `southwest/runtime.json`,
  `forest_lake/manifest.json`, `treehouse/{pieces,surfaces}.json`, `skatepark/park.json`, `megapark/park.json`,
  `craterpark/{park,cloud}.json`, `hippodrome/hippodrome.json`, `hidamari_stable/stable.json`,
  `belmonte/runtime.json`, `brinecove/runtime.json`, `belmonte_track/track.json`, `belmonte_train/service.json`,
  `ferry/service/service.json`, `gondola/runtime.json`, `horses/roster.json`, `racing/belmonte_courses.json`,
  `bike/manifest.json`, `<character>/{character.json,adventure.json,portrait.png}`, and for the kart
  `kart/{cockpit.json,prepared-models.json,grips/<id>.json}`.
- **Input** is built in code (`Src/WandererCharacter.cpp:506-653`: `NewObject<UInputMappingContext>`/`UInputAction`).
  No saved input assets exist.
- **Cook:** the build cooks all content (`docs/PACKAGING.md` "cooks all content (the game loads about 83 assets by path)");
  `DefaultGame.ini` also lists `DirectoriesToAlwaysCook` for Wanderer, Cairo, Modori, SkateMotion, SkateRuntime,
  Belmonte*, Brinecove, CraterPark, IslandTerrain, Southwest/Lake pieces, VillageAtomic, Racing, Horses and CairoHorse.
  Nox and Paul are not listed, so they depend on the cook-everything behavior.
- **State locations:** `FPaths::ProjectSavedDir()` holds `settings.txt` (`platform/.../AtelierCore/Private/AtelierSettings.cpp:11-16`,
  `-preferencesfile=`), `markers.json` (`Src/JapanMarkers.cpp:31`, `-markersave=`), `stable-names.json`
  (`Src/JapanAtlasNames.cpp:34`), `racing/world.json` + `racing/player-id.txt` (`Src/RacingService.cpp:402`),
  `DevNotes/`, `Screenshots/`. `ProjectName=Yorimichi` in both `DefaultGame.ini` and `DefaultEngine.ini`. **V2 must
  change the project name, or it will share the original game's Saved state.**

## Gameplay rows

### F01 Characters (Cairo, Modori, Nox, Paul)
- **Status:** implemented. Four `role = "player"` characters exist (`assets/characters/{cairo,modori,nox,paul}/character.toml`).
  Cairo is `default = true` with alias `CairoAdventure`. NPC rigs: `sword-trainer` (Kaede), `fox-hunter`, `wanderer`
  (villagers). `tide-reader` (Kiyo, `/Game/TideReader`) has a character.toml but no game code loads it: proposed/unused.
- **Old source:** the roster is data-defined. `Src/PlayableCharacter.{h,cpp}` and `Src/CharacterRoster.cpp` scan
  `Content/Data/<id>/character.json` and `LoadClass` `/Game/<Name>/BP_<Name>.BP_<Name>_C`. `AMoverCharacter :
  AWandererCharacter` (`Src/MoverCharacter.*`) is the BP parent (`Scripts/character_pawn.py:67`). Rig/presentation:
  `Src/WandererAnimInstance.cpp` (587), `HairSpringComponent`, `SeatCorrectiveComponent`/`SeatCorrectiveGrid.h` (Nox seat morphs),
  `FingerWrapNode.h`, `GripPoseNode.h`, `HorseRiderNode.h`, `YorimichiFit`. Cloth: `Source/YorimichiImport/YorimichiCloth.*`
  (`/Game/Modori/PA_Modori_Cloth`). Data asset: `UWandererDefinition` (YorimichiAssets). Selection and switching:
  `Src/JapanCharacterSelect.cpp` (878), `Src/JapanCharacterSwitch.cpp`.
- **Content:** `/Game/{Cairo,Modori,Nox,Paul}` (body, `BP_<Name>`, definition), `/Game/<Name>Adventure`,
  `/Game/<Name>Bike`, `/Game/<Name>Horse`, `/Game/Adventure` (motion reference, sword, paraglider), `/Game/Wanderer`.
- **Build steps:** `characters.<k>`, `unreal.<k>`, `characters.<k>_adventure`/`unreal.<k>_adventure`, `characters.<k>_bike`/`unreal.<k>_bike`,
  `characters.<k>_horse`/`unreal.<k>_horse`, `characters.<k>_grips`, `characters.<k>_fit`, `characters.adventure`, `unreal.adventure`,
  and the pawn step (`build.py:640-765`). Scripts: `import_character.py`, `import_adventure_moveset.py`, `import_ride_clips.py`, `character_pawn.py`.
- **V2:** Player and characters: `Source/Yorimichi/Player/Characters/` (roster, MoverCharacter, anim instance, rig
  nodes, cloth/hair/seat components). Keep `YorimichiAssets` and `YorimichiImport` unchanged.
- **Checks:** [A] `tests/test_character_{definitions,fit,select,moveset_config,ledger,import_reuse}.py`, `test_nox_*`,
  `test_paul_source.py`, `test_grips.py`, `Yorimichi.Grip.*` (FingerWrapTests). [A] fit gate `characters.<k>_fit`
  (reach_error_cm ≤ 4 cm, `docs/PLAYABLE_CHARACTER.md`). [V] `scenarios/cairo_shoes.py`, `tools/character_review.py`,
  `skate_grab_shots.py`. [A] `test_network_mixed_characters.py`.
- **Depends on:** none (foundation). F02–F14 and F22 depend on it.
- **Gaps:** the kart grip/fit files are per character (`assets/characters/*/kart-grip*.json`) and are excluded (X02).

### F02 On-foot movement set
- **Status:** implemented. `EAdventureMoveMode { Ground, Air, Glide, Climb, Swim }` (`Src/AdventureMoveSet.h:43`).
  Side hop and backflip: `Src/AdventureMoveSet.cpp:813`, `AdventureMoveSetDefence.cpp:181` (HopL/HopR). Double jump:
  `UAdventureMoveSet::StartDoubleJump`. Stamina, sprint, crouch, climb/ledge, swim, dash, glide (paraglider): AdventureMoveSet*.
  Wave (Q) and Interact (E): `Src/WandererCharacter.cpp:538-539`.
- **Old source:** `Src/AdventureMoveSet.{h,cpp}` (505 + 1063), `AdventureMoveSetTraversal.cpp` (786), `AdventureMoveSetDetail.h`,
  `JapanCharacterMovement.*`, `Src/WandererCharacter.cpp` (input), `Src/WandererAnimInstance.cpp`. Move data:
  `assets/characters/adventure/moves.toml`/`moves.py`, written to `Content/Data/<id>/adventure.json`.
- **V2:** Player and characters: `Player/Movement/` (move set, traversal), `Player/Input/`.
- **Checks:** [A] `scenarios/adventure_moves.py` (live bridge). [A] `Yorimichi.Network.{MoveClock,OrderedInput,TraversalCheckpoint}`.
  [A] `tests/test_character_moveset_config.py`, `test_glider_grip_fit.py`. [A] `-controllertrace` (WandererCharacter).
- **Depends on:** F01.
- **Gaps:** `bDriving`/`AdvanceDrive` in AdventureMoveSet is the root-motion "drive path" for ledge pull-up, not the
  kart. Keep it.

### F03 Camera
- **Status:** implemented. Chase arm, solid push-in, spatial fade of thin occluders, noren, hole-mode fallback
  (`docs/CAMERA.md`). Scoped first-person: train passenger view (`TrainPassengerView`, `-trainview`) and gondola
  seat (yaw ±100°, pitch ±60°, `scenarios/gondola_seat.py`).
- **Old source:** `Src/JapanCameraArm.*`, `Src/SeeThrough.*` (`/Game/SeeThrough/MPC_SeeThrough`, `/Game/Japan/Treehouse/Materials/M_TreeHouse`),
  `Src/TrainPassengerView.*`, the camera blend and FOV in `Src/WandererCharacter.cpp:1750-1810` (skate, horse and kart
  blends). Skate camera: Skate plugin `Simulation/Camera*` + `DefaultGame.ini` `CameraFollow`/`CameraPullback`.
  `Scripts/see_through.py`, `import_see_through.py`, step `unreal.see_through`.
- **V2:** Presentation: `Presentation/Camera/`. The skate camera stays in the Skate plugin.
- **Checks:** [A] `Yorimichi.CityPieces.LogicalFadeBounds`, `Yorimichi.Belmonte.TrainView{Body,State}`. [V]
  `scenarios/gondola_seat.py`, `treehouse.py`/`treehouse_walk.py`. [A][P] `scenarios/skate_camera_speed.py`.
- **Depends on:** F01, F12, F14, F06.
- **Gaps (CAMERA.md "Limits"):** `M_Village` kit pieces do not fade; thin fences push the camera; a piece stopped at
  the band edge stays half-faded; long bent pieces must be split.

### F04 Sword combat
- **Status:** implemented. Draw/sheath, combo, charge, guard, parry, dodge/hops, flurry, knockdown/get-up and
  immunity (0.7 s) are all in AdventureMoveSet*. Health and the training post: `WandererSword`.
- **Old source:** `Src/AdventureMoveSetCombat.cpp` (1218), `AdventureMoveSetDefence.cpp`, `AdventureMoveSetReaction.cpp`,
  `AdventureMovementReaction.*`, `SwordCombatRules.h`, `JapanCombat.*`, `JapanCombatResolver.*`,
  `JapanDefenceTimeline.*`/`JapanDefenceClock.h`, `JapanReaction*`, `JapanScheduledReactions.cpp`, `WandererSword.*` (574),
  `Dev/WandererSwordDummy.cpp` (`-sworddummy`). FX: `YorimichiCombatFX` (AtelierFX `FXClass`, `/Game/FX/*`).
  Audio: `/Game/Audio/Combat`. Clip timing: `FWandererSwordClip` in `UWandererDefinition`.
- **Build:** `fx.textures`, `unreal.fx`, `audio.combat`, `unreal.sounds`, the `unreal.<k>_adventure` steps.
- **V2:** Combat: `Combat/Sword/`, `Combat/Resolution/`. The network reaction scheduling goes to Network (`Network/Reactions/`).
- **Checks:** [A] `Yorimichi.Combat.{Rules,Contacts}`, `Yorimichi.Network.{DefenceTimeline,ReactionPayload,ReactionDelivery,ReactionJournal,ReactionTiming,ReactionTransport}`.
  [A] `scenarios/adventure_moves.py`, `-networkcombat` QA (`JapanCombatQA.cpp`). [V] `ronin_camp_film.py`, `trainer_film.py`.
- **Depends on:** F01, F02, F19 (combat sounds). F05 and F22 depend on it.
- **Gaps (`docs/MULTIPLAYER.md`):** end-to-end immunity pair cases 10–12 were proposed but not implemented. Combat at
  30/60 host fps is still open.

### F05 Fox hunter, Kaede trainer, Ronin camp
- **Status:** implemented (offline). Fox hunter: `AFoxHunter` + `UFoxHunterDefinition` + `UFoxHunterAnimInstance`,
  spawned near the start (`Src/JapanGameMode.cpp:27-36`, `-nofox`). Kaede: `ASwordTrainer::SpawnInVillage` with three
  levels Gentle/Steady/Master and a Slate menu (`Src/SwordTrainer.cpp:563-644`). Ronin camp:
  `ASwordTrainer::SpawnRoninCamp` (`SwordTrainer.cpp:427-507`), scout/guard/captain roles, scout thrown blade
  `ARoninProjectile`. **Online status is unverified.** The map hides the camp zone online (`Src/JapanMap.cpp:217`).
  `SwordTrainer.cpp` has no network code. The fox has `FFoxNetworkState`, encounter leases (`JapanEncounters`) and
  `-networkenemy` QA.
- **Old source:** `Src/FoxHunter.*` (462), `FoxHunterAnimInstance.*`, `SwordTrainer.*` (1300: trainer + camp + menu UI),
  `RoninProjectile.*`, `JapanEncounters.*`, `JapanEnemyQA.*`.
- **Paths:** `/Game/FoxHunter/DA_FoxHunter`, `/Game/SwordTrainer/DA_SwordTrainer`, `/Game/SwordTrainer/Textures/T_tripo_mat_ee5a1a4b`,
  `/Game/CairoAdventure/DA_CairoAdventure`, `/Game/SwordCamp/Assets/*` (SM_RoninKasa, SM_GuardJingasa, SM_CaptainKabuto,
  SM_RoninWakizashi…), `/Game/SwordCamp/Materials/M_RoninBody`.
- **Build:** `characters.fox_hunter`, `unreal.fox_hunter` (`import_fox_hunter.py`), sword-trainer character steps,
  `world.swordcamp`, `world.swordcamp_atlas`, `unreal.swordcamp`.
- **V2:** Combat: `Combat/Enemies/{FoxHunter,Ronin}/`, `Combat/Trainer/`. Split SwordTrainer.cpp into trainer AI,
  camp spawn and menu UI (the UI goes to Presentation).
- **Checks:** [A] `Yorimichi.Network.EncounterReplacement`, `Combat.*`. `-trainerqa`. [V] `trainer_film.py`, `ronin_camp_film.py`.
  [A] `tests/test_swordcamp.py`, `test_enemy_receipts.py`, `tools/network_enemy_review.py`.
- **Depends on:** F04, F16/W02 (village record), W13.
- **Gaps (`docs/FOX_HUNTER_COMBAT.md` "Limits"):** no navigation; one hunter; Jump clip unused; timings not tuned.

### F06 Skating
- **Status:** implemented. The simulation (Flick-It, grinds, manuals, powerslides, pumping, vert, bails) is in the
  generic Skate plugin. The game integration is in Yorimichi.
- **Old source:** `platform/engine/Plugins/Activities/Skate` (module `AtelierSkate`: `SkateComponent`, `Ride/*`,
  `Simulation/*`). In the game: `Src/SkatePark.*` (pier), `MegaRamp.*`, `SuperUltraMegaPark.*`, `CraterParkTower.*`,
  `JapanSkateNetwork.*`, `JapanSkateWire.*`, `JapanSkateDelivery.cpp`, `JapanSkateBudget.h`/`JapanSkateClock.h`,
  `JapanAudioPreferences.*`, and the skate feel menu in `JapanPreferences.cpp` (around 45 `skate_*` keys).
- **Config/paths:** `DefaultGame.ini [/Script/AtelierSkate.SkateSettings]`: `/Game/SkateMotion/MotionData`,
  `/Game/SkateRuntime/RuntimeData`, `/Game/SkatePark/Board/{SM_SkateDeck,SM_SkateTruck,SM_SkateWheel,M_BoardDissolve}`,
  `/Game/Audio/Skate`, the `SurfaceMeshes`/`SurfaceMaterials` tables. Plugin: `/Game/SkateRide/{SK_SkateRider,MDT_SkateRider,Clips/B0,B1}` (`RideAnimator.cpp:12-14`).
- **Build:** `skate.runtime`, `unreal.skate_clips`, `unreal.skate_data`, `unreal.skate_board`, `unreal.skatepark`, `audio.skate`.
- **V2:** Skating: `Skating/` (park actors, rider integration, skate network goes to `Network/Skate/`). Reuse the
  plugin unchanged.
- **Checks:** [A] scenarios `skate`/`skate_runtime` (19 checks), `skate_transitions`, `ride_e2e`, `skate_ride`, `skatepark`.
  [P] `skate_performance` (≥58.5 fps, p95 < 20 ms). [A] `japan.SkateGroundCheck` for the packaged build.
  [A] `tools/check_skate_runtime.py`, `check_skatepark_runtime.py`. [A] `Yorimichi.Network.{SkateWire,SkateBudget}`,
  `Yorimichi.Audio.Skate*`, plugin tests (`SkatePadTests`, `SkateBowlBoostTests`…). [V] `skate_showreel`, `pier_part*`, `megapark_ride_film`.
- **Depends on:** F01, W00 surfaces, F19.
- **Gaps:** the `switch-skate-bail` QA case does not exercise a bail (`docs/MULTIPLAYER.md`). macOS exits 0 even
  when SkateGroundCheck fails; read the log line instead.

### F07 Board carry/stow, transitions, markers, ride record/replay
- **Status:** implemented. Mount, stow, carry and dissolve live in Skate `Ride/RideTransition*`,
  `Simulation/BoardPossession*`, and the `SkateboardHand`/`SkateboardPad` inputs. Session markers:
  `Simulation/SessionMarkerRuntime.*` (plugin) and the player's saved places in `Src/JapanMarkers.*`
  (`SetMarker`/`ReturnMarker`/`MarkersPad`). Record/replay: `scenarios/ride_record.py` and `ride_session.py` (live
  bridge, 60 Hz lockstep replay).
- **V2:** Skating: `Skating/Board/`. Markers go to Presentation: `Presentation/Map/Markers`.
- **Checks:** [A] `skate_transitions`, `session_marker.py` (`-markersave`, `--reload`), `ride_session.py`.
  [A] `Yorimichi.Network.TrainVehicleAdmission` (board visibility aboard).
- **Depends on:** F06, F18.
- **Gaps:** whether ride record/replay is a player feature or only a dev/QA script is unverified. No in-game UI for
  it was found (live-bridge scripts only).

### F08 Bike
- **Status:** implemented (`docs/BIKE.md`, "Cairo's bike"; every playable character has bike clips).
- **Old source:** `Src/BikeComponent.*` (887), `BikeMeshComponent.*` (+ `UBikeSteeringBoundsData` saved asset user
  data), `BikeNetwork.cpp`, `JapanBike{State,Support,Ground,Presentation,Substeps}.*`, `JapanParkedBikeState.h`,
  `WandererNetworkBike.cpp`, `JapanVehicleMovement.cpp`.
- **Paths:** `/Game/Japan/Assets/BK_{Frame,WheelFront,WheelRear,Crank,Pedal,Kickstand,RackBoard}`, `/Game/Audio/Bike/`,
  `/Game/<Rig>Bike/A_<clip>` (built by format string at `BikeComponent.cpp:188`).
- **Build:** `world.bike.*` (`vehicle_atomic_build.py`), `unreal.bike` (`import_bike.py`), `audio.bike`, `characters.<k>_bike`.
- **V2:** Travel: `Travel/Bike/`. Bike network state goes to `Network/Vehicles/`.
- **Checks:** [A] `Yorimichi.Network.{BikeCheckpoint,BikeSupport}`, `Yorimichi.Bike.AtomicLogicalBounds`. [V][A] `scenarios/bike_live.py`
  + `tools/review_bike.py`. `-networkvehicles` QA. [A] `tests/test_vehicle_*`.
- **Depends on:** F01, W00 ground, F19.
- **Gaps:** pending-mount bike/sail has not been rerun since the scheduled-reaction fix (MULTIPLAYER.md).

### F09 Sailboat
- **Status:** implemented, with a gap. Sailing is confined to the coastal ocean (`Src/SailboatComponent.cpp:66`). The
  shoreline review says "sailing limited to the southern ocean". There is no sailboat sound code.
- **Old source:** `Src/SailboatComponent.*`, `SailboatNetwork.cpp`, `JapanSail{State,Presentation}.*`, `WandererNetworkSail.cpp`,
  and the `-sailboatqa` self-test in `WandererCharacter.cpp:1329-1420`.
- **Paths:** `/Game/Japan/Assets/SB_{Hull,Sail,Boom,Rudder,Wake}`. Built in `unreal.world` (`import_sailboat.py`,
  `sailboat_material.py`), needs `world.sailboat`.
- **V2:** Travel: `Travel/Sailboat/`.
- **Checks:** [A][V] `scenarios/sailboat.py`, `-sailboatqa`. [A] `Yorimichi.Network.SailCheckpoint`.
- **Depends on:** F01, W00 sea/coast.
- **Gaps:** shoreline work is "implementation in review" (`docs/shorelines/review-status.json`, PR #395). Whether
  it is in the baseline is unverified.

### F10 Horse
- **Status:** implemented offline. Online is unverified: "The horse … has source and Python receipt review only; it
  has not been compiled or run natively" (MULTIPLAYER.md). There are six breeds, seven tack sets, 17 coats, 5 masks,
  19 hair colours, 4 patterns and 5 tints (`docs/HORSE.md`). The horse is summoned anywhere with H/RB.
- **Old source:** `Src/HorseComponent.*` (1112), `HorseNetwork.cpp`, `JapanHorse{State,Appearance,Presentation}.*`,
  `WandererNetworkHorse.cpp`, `HorseRiderNode.h`.
- **Paths:** `/Game/Horses` (roster `horses/roster.json`), `/Game/<Rig>Horse/A_<clip>` (format string,
  `HorseComponent.cpp:328,348`).
- **Build:** `world.horses`, `unreal.horses` (`import_horses.py`, `horse_data.py`), `characters.<k>_horse`/`unreal.<k>_horse`, `data.racing_assets`.
- **V2:** Travel: `Travel/Horse/`. The breed library is shared with Racing (see F15).
- **Checks:** [A] `Yorimichi.Network.{HorseCheckpoint,HorseWater}`, `Yorimichi.Horse.TurnInPlace`, `tests/test_horses.py`.
  `switch-horse` feature case (never run natively).
- **Depends on:** F01, F19 (hoofsteps in `JapanFootsteps`).

### F11 Zeppelin
- **Status:** implemented. **The baseline has four stations, not three.** `world/regions/zeppelin/layout.py:11-14`
  lists Woodland, Hidamari, Mega Park and Belmonte (meshes `ZP_Woodland/City/MegaPark/Belmonte`). Destination and
  speed controls: `ChooseDestination`, `AdjustFlightSpeed`, `FlightFaster`/`FlightSlower` inputs. Passengers are
  replicated (`FZeppelinNetworkState`).
- **Old source:** `Src/ZeppelinService.*` (325), `ZeppelinNetwork.cpp`, `TransportAudio.*` (`UZeppelinAudioComponent`).
  Meshes `/Game/Japan/Assets/ZP_*`, built in `unreal.world` (`import_zeppelin.py`), needs `world.zeppelin.meshes`.
  Audio `/Game/Audio/Transport`.
- **V2:** Travel: `Travel/Zeppelin/`. Its replication goes to Network.
- **Checks:** [A][V] `scenarios/zeppelin.py` (captures + pawn collision probes), [V] `megapark_access_film.py`,
  `zeppelin` feature case, `-zeppelindock=`. [A] `tests/test_zeppelin_*`.
- **Depends on:** F01, W19, F19.
- **Gap:** plan F11/W19 say "three stations". Settle this in `DECISIONS.md` against r13.

### F12 Belmonte train
- **Status:** implemented (on foot only, host admission, safe-ground recovery). Interiors are unfinished: reservation
  boxes remain in every coach (`docs/BELMONTE_TRAIN_TODO.md` §1). There are no train sounds (no audio code in
  `BelmonteTrainService.cpp`). The canteen lady is a brief only (`docs/BELMONTE_TRAIN_CANTEEN_LADY.md`): proposed.
- **Old source:** `Src/BelmonteTrainService.*` (1714 + 375), `BelmonteTrainRecovery.*`, `BelmonteTrainRules.h`,
  `BelmonteTrainBoards.cpp` (departure boards: `/Game/BelmonteTrain/Materials/M_BT_BoardText`, `/Game/Belmonte/Materials/M_Belmonte`),
  `BelmonteTrack.*`, `TrainPassengerView.*`. Flags `-traingo`, `-trainview`, `-traintimescale`.
- **Content:** `/Game/BelmonteTrain`, `/Game/BelmonteTrack`.
- **Build:** `world.belmonte_train*` (plan, furniture LODs, assembly, route, service), `world.belmonte_track*`,
  `unreal.belmonte_train`, `unreal.belmonte_track`, `train_*_build.py`, `tools/belmonte_train_service.py`.
- **V2:** Travel: `Travel/Train/`. Split `BelmonteTrainService.cpp` into service/clock, boarding/admission, recovery and seats/view.
- **Checks:** [A] `Yorimichi.Belmonte.{TrainAdmission,TrainBoards,TrainEjectRules,TrainLine,TrainRecoveryProbe,TrainRules,TrainViewBody,TrainViewState}`,
  `Yorimichi.Network.TrainVehicleAdmission`. [A] about 20 `tests/test_belmonte_train_*`. [V] `tools/review_belmonte_train_ride.py`.
- **Depends on:** F01, W16, W20, F03.
- **Note:** `bTrainDriving`/`IsDrivingRider` is the train and gondola seating state (also set by `GondolaService.cpp:300,326`), not the kart.

### F13 Ferry
- **Status:** implemented. One ship shuttles between two harbours, Hidamari and Brinecove (`world/regions/ferry/service.py:28-29`).
  Wake mesh `/Game/Ferry/Ship/FY_Wake`. Audio `UFerryAudioComponent`.
- **Old source:** `Src/FerryService.*` (793). Content `/Game/Ferry`.
- **Build:** `world.ferry_ship*`, `world.ferry_terminals*`, `world.ferry_probes`, `world.ferry_site`, `world.hidamari_ferry_cut`,
  `world.ferry_service`, `unreal.ferry`, `audio.transport`.
- **V2:** Travel: `Travel/Ferry/`.
- **Checks:** [A] `Yorimichi.Ferry.{ClockAndBoarding,InvalidLine,ProductionInitialization,RemotePassengerPresentation,SharedRiderTransitions}`.
  [A] `scenarios/ferry_roundtrip_live.py`, `-ferrygo`, `-ferrytimescale`. [A] `tests/test_ferry_*` (about 14).
- **Depends on:** W07, W09, W17, F19.

### F14 Gondola
- **Status:** implemented. Three lines (`world/regions/gondola/layout.py`): L1 Hidamari–southeast, L2
  Belmonte–northwest, L3 crater floor–rim. Level cabins. Seated first-person view.
- **Old source:** `Src/GondolaService.*` (597), `TransportAudio` (`UGondolaAudioComponent`, `UGondolaStationAudioComponent`).
  Content `/Game/Gondola` (meshes named in `gondola/runtime.json`).
- **Build:** `world.gondola_kit*`, `world.gondola_ground*`, `world.gondola_structures`, `world.gondola_site`, `world.gondola_service`, `unreal.gondola`.
- **V2:** Travel: `Travel/Gondola/`.
- **Checks:** [A] `Yorimichi.Gondola.{FittedClockAndLevelCabin,NorthTreeClearance}`. [A] `scenarios/gondola_roundtrip_live.py`,
  `gondola_seat.py`. [A] `tests/test_gondola_*` (about 20).
- **Depends on:** W12, W16, W18, F03, F19.

### F15 Horse racing
- **Status:** implemented. HorseRacing rules: continuous calendar, CPU stables, two venues (Hidamari Hippodrome and
  Belmonte turf/sand), saves, four Belmonte TVs. The host player only: "Remote guests get no player record, wallet or
  stable" (`docs/RACING.md`). The plugin has betting and owner/stable rules plus tests (`HRBetting.cpp`, `HROwner.cpp`)
  with no game UI: out of scope per the plan. **`AHidamariStable::bEnabled = false`** (`Src/HidamariStable.h:57`,
  paired with `world/regions/hidamari_stable/layout.py:20`), so the stable is not spawned at baseline.
- **Old source:** `unreal/Plugins/HorseRacing` (`AtelierHorseRacing`, `HRWorld.cpp` 1384, `HRSave`, `HRRace`, `HRRiders`,
  `HRVisualGenome`…). Game: `Src/RacingService.*` (1229), `RacingCourse.*`, `RacingMotion.*`, `RacingBroadcast.*` (886),
  `Hippodrome.*`, `HidamariStable.*`, `JapanAtlasNames.*` (stable names).
- **Paths:** `/Game/Racing` (+ `M_RacingTv`), `/Game/Horses`, `/Game/<Rig>Horse/A_*` jockey clips (`RacingService.cpp:858`),
  `/Game/Hippodrome`, `/Game/HidamariStable{,/Atomic}`. Data `racing/belmonte_courses.json`, `hippodrome/hippodrome.json`.
- **Build:** `data.racing_assets`, `unreal.hippodrome`, `unreal.hidamari_stable`, `world.hidamari_stable_review`,
  `unreal.belmonte` (TV material `racing_tv_material.py`). Flags `-racingsave=`, `-racingseed=`, `-racingnext`.
- **V2:** Racing: `Racing/` (service, courses, motion, broadcast) + `Plugins/HorseRacing`. Split `RacingService.cpp`.
- **Checks:** [A] `Yorimichi.Racing.{BelmonteCourse,EnglishName,Ground,HippodromeCourse,HudGrounds,Motion,Save,SaveSafety,SharedHorseGait,Snapshot,TvDirector,TvPlacement}`,
  `Atelier.HorseRacing.*` (25), `Yorimichi.Map.StableNames`, `Yorimichi.Stable.SelectedLodBounds`. [A] `tests/test_racing_{assets,courses}.py`,
  `test_hippodrome_*`, `test_hidamari_stable_layout.py`.
- **Depends on:** F10 (breeds, clips), F01, W14–W16, F24 (Saved/racing).

### F16 Villagers and ambient actors
- **Status:** implemented. `AVillageLife` places procedural villagers from the village record and world groups
  (`Src/JapanWorld.cpp:813,928`). It is skipped on a dedicated server, so it is presentation only.
- **Old source:** `Src/VillageLife.*`. Paths `/Game/Wanderer/DA_Wanderer`, `/Game/Japan/Materials/M_VillageResident`.
  Build `characters.wanderer` + `import_wanderer.py` (inside `unreal.world`). Rig source `assets/characters/wanderer`.
- **V2:** World: `World/Ambient/VillageLife`.
- **Checks:** none found. [V] baseline views only.
- **Depends on:** W02, W07.
- **Gaps:** interactions with villagers are unverified (no Interact handler found in `VillageLife.cpp`).

### F17 Desktop menus, text, hints, character choice, settings
- **Status:** implemented. Slate settings menu with pages: graphics, audio (soundbank), skate feel, friends
  (host/join), dev mode/export, character select (`Src/JapanPreferences.cpp`, 1377). HUD hints: `Src/JapanHUD.cpp`
  (444). Character select: `JapanCharacterSelect.cpp` (portraits from `Data/<id>/portrait.png`). The renderer choice
  (Forward/Lumen) restarts the game (`-renderrestart`). **Lumen is editor-only:** `bLumenAvailable = WITH_EDITOR`
  (`JapanPreferences.cpp:62`). "Pause" freezes input (`bMenuOpen`); no `SetGamePaused` was found.
- **Old source:** the above plus `JapanAudioPreferences.*`, `DesktopPreviewViewportClient.*`, `ForwardLookExperiment.cpp`,
  `JapanMapControls.h` (pad glyphs), `tools/desktop_preview.py` (play profile), settings file via `AtelierSettings`.
- **V2:** Presentation: `Presentation/Menus/`, `Presentation/HUD/`. Split `JapanPreferences.cpp` into a settings store
  and the menu pages.
- **Checks:** [A] `Yorimichi.Preferences.{ReleaseDefaults,RetiredSoundbankMenu,RetiredSoundbankSave}`, `Yorimichi.Audio.*Preferences`.
  [A] `tests/test_english_text.py`, `test_release_defaults.py`, `test_character_select.py`, `test_desktop_preview.py`.
- **Depends on:** F01, F06 (skate menu), F22 (friends page).
- **Gaps:** kart hints in the HUD (`JapanHUD.cpp:292-310,359`) and the phone-profile handling in settings must be
  removed (X01/X02).

### F18 World map and travel
- **Status:** implemented. Painted atlas overlay, zones/travel points, saved places bar, ground-checked travel ("Missing,
  changed or obstructed ground refuses travel", `docs/WORLD_MAP.md:164`). Dynamic zones: Hippodrome, Ronin camp
  (offline only), Crater Park tower start, train termini (`Src/JapanMap.cpp:200-245`).
- **Old source:** `Src/JapanMap.*` (579), `JapanMapPlayers.cpp`, `JapanAtlas.cpp`, `JapanAtlasWidget.cpp` (570),
  `JapanAtlasNames.*`, `JapanAtlasLabels.h`, `JapanMarkers.*`. Data `map/map.json`, `map/atlas-serif.ttf`. Build `world.map`.
- **V2:** Presentation: `Presentation/Map/`. The travel validation goes to World (`World/Travel`).
- **Checks:** [A] `Yorimichi.Map.{LabelLayout,SalonLanding,StableNames}`, `Yorimichi.Network.PlayerTravelClearance`.
  [A] `-mapqa`/`-mapqazone=`. [A] `tests/test_world_map_*`, `test_regional_atlas.py`, `test_map_*`, `tools/review_map_network.py`.
  [V] `scenarios/regional_atlas.py`.
- **Depends on:** W00–W20 (zones), F07 (markers), F12.

### F19 Sound
- **Status:** implemented. Partial gaps are listed below.
- **Old source:** footsteps `Src/JapanFootsteps.*` + `UJapanFootstepSet`/`FJapanFootstepBank` (YorimichiAssets,
  `/Game/Japan/Audio/DA_Footsteps`). Hoofsteps are in `JapanFootsteps.cpp`/`HorseComponent.cpp`. Transport:
  `Src/TransportAudio.*` (zeppelin, ferry, gondola, gondola station; `/Game/Audio/Transport/`). Bike: `/Game/Audio/Bike/`.
  Combat: `/Game/Audio/Combat` (AtelierFX `SoundFolder`). Skate: `/Game/Audio/Skate`. Ambience:
  `/Game/Audio/Combat/ambience_countryside_01` (`WandererCharacter.cpp:277`).
- **Build:** `audio.{footsteps,combat,skate,bike,transport}`, `unreal.sounds` (`import_footsteps.py`, `import_combat_audio.py`,
  `import_skate_audio.py`, `import_bike_audio.py`, `import_transport_audio.py`, plus the excluded `import_driving_audio.py`).
  Fetch `sonniss/footsteps` and `sonniss/combat` (`game.toml [fetch]`).
- **V2:** Presentation: `Presentation/Audio/`. Activity-owned emitters stay with their feature.
- **Checks:** [A] `Yorimichi.Audio.{FootstepShuffle,FootstepPreferences}`, `tests/test_transport_audio.py`, `test_sound_sequences.py`,
  `test_native_audio_saves.py`, `test_world_audio_boundary.py`. [V] `docs/SOUND_REVIEW.md` listening page.
- **Depends on:** F04, F06, F08, F11, F13, F14.
- **Gaps:** footsteps (`docs/FOOTSTEPS.md` "Known gaps"): repetitive stone pool, no tatami, no water splash, no
  crouch pool. No train or sailboat sound code was found.

### F20 Music
- **Status:** implemented and optional. `UJapanMusic` (`Src/JapanMusic.*`, 485) is a zone/activity director
  (`EJapanMusicScene { Explore, Skate, Ride, Sail, Air, Combat }`) with an equal-power crossfade. The external library
  is passed with `-music=DIR`; `-nomusic` turns it off; without a library the game is silent. Playback uses
  MediaPlayer + **ElectraPlayer** (`JapanMusic.cpp:194-195`).
- **Build:** `audio.music`, the optional `unreal.music` (`import_music.py`, `/Game/Audio/Music`). Release: `game.toml [release.music]`.
- **V2:** Presentation: `Presentation/Audio/Music`.
- **Checks:** [A] `tests/test_music_{ledger,prepare}.py`. The r9 music smoke is noted in the operator memory, not in the repo.
- **Depends on:** F18 (`map/map.json` zones), F24 (container path).

### F21 Visuals
- **Status:** implemented. The forward renderer is the default (`DefaultEngine.ini`). `JapanWorld` builds the sky dome,
  sea, fog and lighting (`MPC_Wind`). `ALeafStorm` (`/Game/Japan/Assets/Leaf`). `AGullFlock` (`BirdBody`/`BirdWingL`/`BirdWingR`).
  `ACraterCloud` (`/Game/CraterPark/Cloud/M_CraterCloud{,Veil}`). `HarborLook`. Volumetric fog is a setting
  (`docs/VOLUMETRIC_FOG.md`). City tree LODs and foliage.
- **Old source:** `Src/JapanWorld.cpp` (1305: also world loading, so split it), `LeafStorm.*`, `GullFlock.*`, `CraterCloud.*`,
  `HarborLook.*`, `SeeThrough.*`, `CityTreeLODExperiment.cpp`, `ForwardLookExperiment.cpp`. Materials from Scripts:
  `painterly_kernel.py`, `sea_look.py`, `atmosphere.py`, `foliage_material.py`, `shared_materials.py`, `city_material.py`…
- **Build:** `unreal.world`, `unreal.crater_cloud`, `unreal.city_tree_lods`, `unreal.forest`, `world.foliage*`, `world.*_textures`.
- **V2:** Presentation: `Presentation/Visuals/` (sky, sea, effects). Material assets become committed content.
- **Checks:** [V] `fog_film.py`, baseline views. [P] `tools/benchmark.py`, `Dev/JapanBenchmark.cpp` (`-benchmark*` flags), `docs/DESKTOP_PERFORMANCE.md`.
  [A] `tests/test_benchmark_profile.py`, `test_foliage_*`, `test_sea_depth_seams.py`, `test_shorelines.py`.
- **Depends on:** W00–W20.
- **Gaps:** shoreline visual approval is pending (PR #395). Lumen is not available in packaged builds.

### F22 Multiplayer
- **Status:** implemented and tested with two processes on one machine. **Two-machine and packaged play are
  unverified:** "This is development evidence, not a completed two-machine or packaged release certification"
  (`docs/MULTIPLAYER.md`). The horse online path has never run natively. The `switch-skate-bail` case is broken.
  Pending-mount bike/sail has not been rerun. Immunity pair cases 10–12 were never implemented.
- **Old source:** `Src/JapanNetwork.*`, `JapanSession.*` (482), `JapanIpNetDriver.*` (config `NetDriverDefinitions`),
  `JapanTailscale.cpp`, `JapanMovementNet.*`, `JapanMovementPrediction.cpp` (814), `JapanMoveClock.h`,
  `AdventureNetwork{State,Presentation}.*`/`AdventureNetworkFields.inl`, `WandererNetwork{Activity,Bike,Horse,Sail}.cpp`,
  `JapanReaction*`, `JapanScheduledReactions.cpp`, `JapanGameplayCollision*`, `JapanActivityState.h`/`JapanAvatarState.h`,
  plus each service's `F*NetworkState`. Build identity: `Yorimichi.Build.cs` generates `YorimichiBuildIdentity.h` +
  `network_identity.py` + step `data.network`. QA: `JapanNetworkQA`, `JapanMultiplayerQA`, `JapanGameplayQA`, `JapanVehicleQA*`,
  `JapanJumpReplayQA`, `JapanReactionDelivery{Probe,QA}`, `JapanCombatQA`, `JapanEnemyQA` (`-network*` flags).
- **V2:** Network: `Network/{Session,Movement,Reactions,Vehicles,Skate}`. Keep `YorimichiServer` if dedicated play is retained.
- **Checks:** [A] all `Yorimichi.Network.*` fixtures (around 25). [A] `tools/review_network_{wire,session,bind}.py`
  (`--feature-case equipment|switch-*|zeppelin`, `--reaction-delivery-case 0-9`, lag 60/15/2). [A] `tests/test_network_*` (about 20).
  [V] the two-device Tailscale playtest procedure in `MULTIPLAYER.md`.
- **Depends on:** F01–F15.
- **Note:** `Yorimichi.Build.cs` hashes every source and ini under `games/yorimichi/unreal` and `platform/engine/Plugins`
  into the network ID. V2 must point this at its own roots.

### F23 Live bridge, QA and dev tools
- **Status:** implemented. LiveBridge (`platform/engine/Plugins/Dev/LiveBridge`, module `AtelierLive`) listens on
  loopback port **8830, fixed** (`DefaultGame.ini [/Script/AtelierLive.AtelierLiveSettings]`, `DefaultEngine.ini
  [HTTPServer.Listeners]`). It is disabled in packaged builds unless `-live`, refuses networked sessions, and runs
  Python only in uncooked builds (`docs/LIVE_WORKSHOP.md`). In-game Dev mode/DevNotes (free camera, notes,
  screenshots, zip export) is in the release settings menu (`Src/DevNotes.*`).
- **Old source:** `Src/YorimichiLive.*` (314), `live/python/yorimichi_live.py`, `live/overlays/workshop.json`, `Src/Dev/*`
  (BuildingReview, HidamariReview, JapanBenchmark, JapanSkateReview, JapanTrailer, WandererSwordDummy), the `*QA.cpp`
  files, `NativeAtomicEquivalence.*`, `AtomicMeshBounds.*`, `CitySurfaceValidation.*`, `UBelmonteTrainLive`/`UFerryLive`/`UGondolaLive`/`URacingLive`,
  `tools/capture.py`, `tools/benchmark.py`, and the scenarios (54 files).
- **V2:** `Source/Yorimichi/Dev/` (opt-in, excluded from Shipping). LiveBridge stays a platform plugin.
- **Checks:** [A] `tests/test_scenarios_parse.py`, `test_capture_telemetry.py`. Release absence is checked through `test_release_defaults.py`.
- **Depends on:** all rows.
- **Gaps:** the fixed port 8830 cannot target the right session among several games (plan §8). The kart helpers in
  YorimichiLive and the live module must go (X02).

### F24 Runtime data, saves, startup, packaging
- **Status:** implemented. Packaging targets macOS only (`docs/PACKAGING.md`). There is a known pre-start SIGSEGV
  that clears on relaunch; the launcher retries once (PACKAGING.md §"A launch can crash"). The music library is
  outside the package.
- **Old source:** `runtime_data.py` (`data.stage`), `content_policy.py`, `tools/package_cook.py`, `package_archive.py`,
  `game_binary.py`, `network_package_target.py`. Game startup: `Src/Yorimichi.cpp`, `JapanGameMode.cpp`, `JapanWorld.cpp`
  (load order + splash), `Src/JapanGameMode.cpp:19` scripted-session keys. The State locations above apply.
- **Build:** `data.stage`, `data.content`, `data.network`, `unreal.compile`, `unreal.game_binary`, `unreal.cook`, `unreal.package`.
- **V2:** World (`World/Loading`) + `games/yorimichi_v2/build.py`.
- **Checks:** [A] `tests/test_{package,package_cook,verify_package,runtime_data,build_outputs,game_binary,release_defaults}.py`, `japan.SkateGroundCheck` on an extracted package.
- **Depends on:** all rows.

## Features the F table misses

| Proposed ID | Feature | Evidence | Suggested area |
| --- | --- | --- | --- |
| F25 | Crater Park tower hoist (Kiyomizu portal ride up/down) and tower line starts | `Src/CraterParkTower.*`, `scenarios/crater_tower_hoist.py`, `TowerReturn` input | Travel or Skating |
| F26 | Mega Park standalone level and game mode (`AMegaParkGameMode`, `AMegaParkWorld`, `GameModeMapPrefixes`, play profile `megapark`) | `DefaultEngine.ini`, `game.toml [play.megapark]`, `Src/SuperUltraMegaPark.*` | World (W11) |
| F27 | In-game Dev mode/DevNotes (free camera, notes, screenshots, zip export) shipped in the menu | `Src/DevNotes.*`, `JapanPreferences` `dev_mode`/`dev_export`, `scenarios/notes_revisit.py` | Presentation/Dev |
| F28 | Friends sessions over Tailscale: host/join menu, join endpoint, mixed characters | `Src/JapanTailscale.cpp`, `JapanSession.*`, menu "friends", `Yorimichi.Network.JoinEndpoint` | Network (a sub-row of F22) |
| F29 | Character presentation physics: Cairo hair spring, Modori cloth, Nox seat correctives | `HairSpringComponent`, `YorimichiCloth`, `SeatCorrectiveComponent`; Mac `r.SkinCache.CompileShaders=1` for Cairo's hair | Player (a sub-row of F01) |
| F30 | Belmonte train departure boards | `Src/BelmonteTrainBoards.cpp`, `Yorimichi.Belmonte.TrainBoards` | Travel (a sub-row of F12) |
| F31 | Kei cars as static Mega Park car-park dressing (not driving) | step `unreal.kei` (`import_kei.py`, `/Game/Japan/Assets`), `SuperUltraMegaPark.cpp:156` | World (W11). Keep it; it is not X02 |
| F32 | Trailer/film, benchmark and building-review modes | `Src/Dev/JapanTrailer.cpp`, `JapanBenchmark.cpp`, `BuildingReview.cpp`, `HidamariReview.*` | Dev (an F23 sub-row) |

Only proposed (no runtime code): canteen lady (Zia Pappa), tide-reader (Kiyo), player betting/stables (plugin rules only).

## Exclusions

### X01 Phone streaming, Pixel Streaming, touch controls
Remove from V2:
- `unreal/Yorimichi.uproject:48` PixelStreaming2 and `:84` AtelierStream. **Keep `:88` ElectraPlayer** (it is used by F20).
- `Src/Yorimichi.Build.cs:59` `"AtelierStream"` in PublicDependencyModuleNames.
- `unreal/Config/DefaultGame.ini:93-96` `[/Script/AtelierStream.AtelierStreamSettings]`.
- `Src/YorimichiPhone.{h,cpp}` (26 + 209 lines): delete.
- `Src/WandererCharacter.h:32,106-107,261,279` (`FYorimichiPhone`, `IsPhoneTouchActive`, friend, `PhoneInput`).
- `Src/WandererCharacter.cpp:20-21` (includes), `:267` (`FAtelierStream::IsRequested()`), `:318`, `:716`, `:1710`,
  and the log text at `:453`. `ReturnToSpawn()` is shared (also called at `:1420,1634`), so keep it.
- `Src/JapanHUD.cpp:98` (`IsPhoneTouchActive()`).
- `Src/JapanGameMode.cpp:19` (`AtelierStream` scripted-session key).
- `Src/JapanPreferences.cpp:345-353,734-741` (`desktop` session-only key and the phone/desktop profile split).
  Comments at `:398,520-528,1293`; `Src/JapanMap.h:74-75`; `Src/YorimichiLive.h:33`; `Src/WandererCharacter.h:120`.
  **Make sure the desktop profile becomes the default before you remove the phone baseline.**
- `game.toml:60-66` `[stream]`. `phone/` (touch page, smoke tests). Platform plugins
  `platform/engine/Plugins/Streaming` (AtelierStream depends on PixelStreaming2) are untouched; V2 just does not
  enable them. No other platform plugin depends on them.
- False positives: "Touchpad" is a PS controller glyph (`JapanHUD.cpp:63`, `JapanMapControls.h:14`). The skate
  "stream" code (JapanSkateNetwork/Delivery) is network pose streaming. Keep both.

### X02 Go-kart and Driving plugin
Remove from V2:
- `unreal/Yorimichi.uproject:80` Driving. `Src/Yorimichi.Build.cs:59` `"AtelierDriving"`.
- `Src/JapanKartGrip.{h,cpp}`: delete (reads `kart/grips/<id>.json`, `kart/prepared-models.json`).
- `Src/WandererCharacter.h:29,132,271-274,283,333-336,403-405` (`UDrivingComponent* Car`, `GetCar`, car blend/smoke
  fields, `ConfigureCar`, `AdvanceCarEffects`, `ToggleCar`, `CarHandbrake*`).
- `Src/WandererCharacter.cpp:29-30,34` (includes), `:93` **`CreateDefaultSubobject<UDrivingComponent>(TEXT("CarRide"))`**
  (a native subobject on the pawn; BP_<Name> may carry overrides, so check the BP load warnings),
  `:334-336,349-430` (ConfigureCar: `/Game/Japan/Kart/SM_Kart_{Body,Seat,Wheel,SteeringWheel}`, `kart/cockpit.json`),
  `:441,479` (StowImmediately), `:539` (key L "Car"), `:578-587` (CarPad, CarHandbrakePad), `:624,650-653` (bindings),
  `:767,799` (handbrake on jump), `:815` (`OnVehicle` includes Car), `:834-850`, `:950` (`"car"` button), `:1600-1603`,
  `:1714-1725` (`driving_intent`), `:1754,1768,1803` (camera/FOV), `:1817-1860` (AdvanceCarEffects).
- `Src/WandererAnimInstance.cpp:20,304-534` (`bDriving` = kart pose, grips, recline, "Kart wrist reach gap").
- `Src/JapanHUD.cpp:12,292-310,359` (kart controls and "L kart" hint).
- `Src/YorimichiLive.cpp:9,196-222` and `.h:54-58` (car_state, flip QA). `live/python/yorimichi_live.py:58-69`.
- **Not kart (keep):** `AdventureMoveSet` `bDriving`/`AdvanceDrive` (root-motion drive path); `bTrainDriving`/`IsDrivingRider`
  (train/gondola seating); `JapanReactionDeliveryProbe.cpp:276-278` (a local named `Driving`); `JapanGameplayQA.cpp:235` comment.
- Build/content loaders: `build.py:113-115` (kart_source_identity), `:1190` (`vehicle_atomic_build` kart steps → `world.kart`),
  `:1456-1458` `audio.kart`, `:1488` (driving_audio), `:1650-1665` `unreal.kart`, `:1744-1752` (`import_driving_audio.py` in `unreal.sounds`),
  `:2100` OWNED_CONTENT `Japan/Kart`. `runtime_data.py:38-40`, `content_policy.py:37,77` (`kart`, audio root `Driving`),
  `vehicle_atomic_build.py:25-82`. Scripts `import_kart.py`, `kart_material.py`, `import_driving_audio.py`.
- Content `/Game/Japan/Kart`, `/Game/Audio/Driving` (`platform/.../DrivingComponent.h:196`). Assets `assets/vehicles/kart`,
  `assets/audio/kart`, `assets/characters/*/kart-grip{,-model}.json`, `tools/kart_grip_editor`.
- QA: `scenarios/kart_{cleanup,equipment,film,fit,flip,spawn,uneven}.py`, `tests/test_kart_*` (8), `test_driving_pose_side.py`, `docs/DRIVING.md`.

### X03 Native browser/mobile ports and Hakuba rendering experiments
- `hakuba_port/` directory, `tests/test_hakuba_port_*` (6). `phone/` (shared with X01). `uproject` `AndroidFileServer`
  is already disabled. Do not port. Keep only asset/layout knowledge.

### X04 New gameplay, engine upgrade, new art direction
- Out of scope. This includes the proposed-only items: player betting/stables (HorseRacing `HRBetting`/`HROwner` stay
  dormant), canteen lady, tide-reader, unfinished train interiors (finishing them is new content; preserve the
  current state). The engine stays on `EngineAssociation "5.8"` plus local patches.

## Saved-content type surface (keep names and module identity)

- **YorimichiAssets** (`/Script/YorimichiAssets.*`): `UWandererDefinition`, `FWandererSwordClip`, `UJapanFootstepSet`,
  `FJapanFootstepBank`, `AMegaParkLayout`, `FMegaParkLayoutData`, `FMegaParkRail`. `CoreRedirects` from `/Script/Yorimichi.*`
  for five of them are in `DefaultEngine.ini`. `MegaParkLayoutData` has no redirect.
- **Yorimichi types that saved content or config references:** `AMoverCharacter` (parent of every `BP_<Name>`),
  `UFoxHunterDefinition` + `FFoxHunterClip` (`/Game/FoxHunter/DA_FoxHunter`, `import_fox_hunter.py:172`), `UBikeSteeringBoundsData`
  (UAssetUserData on bike meshes, `import_bike.py:61`), `AWandererCharacter`/`UWandererAnimInstance` (BP parent chain/anim class),
  `AJapanGameMode`, `AJapanNetworkGameMode`, `UJapanGameInstance`, `AMegaParkGameMode`, `UJapanIpNetDriver`, `AYorimichiCombatFX`,
  `UDesktopPreviewViewportClient`. Editor-only script surface: `UCitySurfaceValidation`, `UBikeMeshComponent`, `UHidamariStableMeshComponent`,
  `UBelmonteTrainImportLibrary`, `UMeshImportAudit`, `UMegaParkValidation`, `UNativeAtomicEquivalence`, `UYorimichiFitLibrary`.
  Skate plugin: `SkateDataLibrary`, MotionData/RuntimeData assets.
- **All reflected types in `Yorimichi`** (for the dependency audit): UAdventureMoveSet, ABelmonteRegion, FBelmonteTrainPassenger,
  FBelmonteTrainNetworkState, ABelmonteTrainService, UBelmonteTrainLive, UBelmonteTrainImportLibrary, ABelmonteTrack,
  UBikeSteeringBoundsData, UBikeMeshComponent, ACraterCloud, UBikeComponent, UDesktopPreviewViewportClient, UCitySurfaceValidation,
  FFerryPassenger, FFerryNetworkState, AFerryService, UFerryLive, FFoxHunterClip, UFoxHunterDefinition, EFoxState, FFoxNetworkState,
  AFoxHunter, FGondolaPassenger, FGondolaNetworkState, AGondolaService, UGondolaLive, UFoxHunterAnimInstance, UHairSpringComponent,
  UHidamariStableMeshComponent, AHidamariStable, AGullFlock, UHorseComponent, EJapanActivity, FJapanActivityState, AHippodrome,
  UJapanAudioPreferences, FJapanBikePresentation, FJapanAvatarState, FJapanBikeState, UJapanCameraArm, UJapanCharacterMovement,
  EJapanCombatCue, FJapanCombatEvent, UJapanEncounters, UJapanCombatResolver, UJapanFootstepComponent, AJapanGameMode, AJapanHUD,
  UJapanGameplayCollisionWorld, UJapanIpNetDriver, FJapanHorsePresentation, FJapanHorseAppearance, FJapanHorseState, UJapanMap,
  UJapanPreferences, UJapanMusic, FJapanParkedBikeState, FJapanSailPresentation, FJapanSailState, UJapanGameInstance, AJapanPlayerState,
  AJapanGameState, AJapanPlayerController, AJapanNetworkGameMode, UJapanSkateNetwork, FWorldShot, AJapanWorld, FJapanSkateChunk,
  FJapanBoardState, FJapanSkateBodies, AMoverCharacter, ALeafStorm, UNativeAtomicEquivalence, USailboatComponent, AMegaRamp, ASkatePark,
  FRacingNet{Runner,Race,Result,Standing,State}, ARacingService, URacingLive, ARacingBroadcast, ASwordTrainer, USeatCorrectiveComponent,
  ARoninProjectile, ASuperUltraMegaPark, AMegaParkGameMode, AMegaParkWorld, UMegaParkValidation, USeeThroughComponent, FWandererStateNode,
  UWandererAnimInstance, UTransportAudioComponent, UZeppelinAudioComponent, EFerryAudioPhase, UFerryAudioComponent, UGondolaAudioComponent,
  UGondolaStationAudioComponent, AYorimichiCombatFX, AWandererCharacter, AVillageLife, FZeppelin{Station,Passenger,NetworkState},
  AZeppelinService, UYorimichiFitLibrary, ESwordState, UWandererSwordComponent, ASwordDummy, UYorimichiLive.

## `/Game` roots referenced from code and config

`/Game/Adventure` (build), `/Game/Audio/{Bike,Combat,Skate,Transport,Music,Driving(X02)}`, `/Game/Belmonte{,/Materials,/Meshes}`,
`/Game/BelmonteTrack`, `/Game/BelmonteTrain{,/Materials}`, `/Game/Brinecove`, `/Game/Cairo`, `/Game/CairoAdventure`, `/Game/CairoHorse`,
`/Game/<Rig>Bike`, `/Game/<Rig>Horse`, `/Game/{Modori,Nox,Paul}` (+Adventure/Bike/Horse), `/Game/CraterPark{,/Cloud}`,
`/Game/Experiments/{CitySurfaces/v1_128m,CityTrees,IslandTerrain/v1_atomic,VillageAtomic/v1_atomic}`, `/Game/FX`, `/Game/Ferry{,/Ship}`,
`/Game/FoxHunter`, `/Game/Gondola`, `/Game/HidamariStable{,/Atomic}`, `/Game/Hippodrome`, `/Game/Horses`,
`/Game/Japan/{Assets,Audio,Kart(X02),Lake/Pieces,Maps,Materials,Southwest/Pieces,Terrain,Treehouse/{Pieces,StructurePieces,Materials}}`,
`/Game/MegaPark/{Meshes,Maps}`, `/Game/Modori/PA_Modori_Cloth`, `/Game/Racing`, `/Game/SeeThrough`, `/Game/SkateMotion`, `/Game/SkatePark{,/Board}`,
`/Game/SkateRide{,/Clips}`, `/Game/SkateRuntime`, `/Game/SwordCamp/{Assets,Materials}`, `/Game/SwordTrainer{,/Textures}`, `/Game/Wanderer`.
The default map is `/Game/Japan/Maps/Slice`. The `/Game/Experiments/...` roots are production paths despite the name;
plan §4 says do not rename them.

## Biggest C++ files (split by feature)

| Lines | File | Split along |
| --- | --- | --- |
| 2017 | Src/WandererCharacter.cpp | input map, activity toggles (bike/sail/horse/kart), camera blends, kart FX, QA modes (benchmark/review/mapqa/sailboatqa/trailer), phone |
| 1714 | Src/BelmonteTrainService.cpp | clock/service, boarding/admission, recovery, seats/view |
| 1384 | Plugins/HorseRacing/.../HRWorld.cpp | plugin-internal; leave |
| 1377 | Src/JapanPreferences.cpp | settings store, render settings, menu pages, skate feel page, friends page |
| 1305 | Src/JapanWorld.cpp | world load/terrain, visuals (sky/sea/fog), service registration |
| 1300 | Src/SwordTrainer.cpp | trainer AI, Ronin camp spawn, menu UI |
| 1229 | Src/RacingService.cpp | rules host, runners/presentation, save |
| 1218 | Src/AdventureMoveSetCombat.cpp | already a feature split; consider attack vs blade-sweep |
| 1112 | Src/HorseComponent.cpp | ride sim, looks, rider clips |
| 1063 | Src/AdventureMoveSet.cpp | core move set |
| 887 | Src/BikeComponent.cpp | |
| 886 | Src/RacingBroadcast.cpp | |
| 878 | Src/JapanCharacterSelect.cpp | |
| 814 | Src/JapanMovementPrediction.cpp | |
| 793 | Src/FerryService.cpp | |
| 786 | Src/AdventureMoveSetTraversal.cpp | |
| 756 | Src/JapanVehicleQA.cpp | |
