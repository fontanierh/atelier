# Inventory

**Current checkpoint: 2026-11-10. Package `0adbb5ab212e` at main `7719234597` includes everything merged through [PR #801](https://github.com/fontanierh/atelier/pull/801), among it the small-families batch (#797) and the Brine Cove signal mast and shipyard slip (#798, #800).**
This is the status index for the full original-game port.
The source baseline `7eec0f98dd` is documented separately in [features](inventory/features.md) and
[world](inventory/world.md); those pages describe the donor, not today's V2 completion state.

## How to read status

- **Ported** means the implementation and its committed inputs are present in V2. It does not certify every
  gameplay interaction, appearance or source-recovery requirement.
- **Prepared** means sources/recipes or plans exist; it does not establish an accepted import.
- **Merged** means the change is on main. Saved working-branch content is not merged or packaged by implication.
- **Saved** means committed placements/packages have owner records and receipts. A record for a fused tile
  is not proof that every useful object inside it is independently editable.
- **Packaged** names the revision that was cooked. Unmerged follow-ups are not included in that package.
- **Verified** applies only to the specific check and revision cited. Final human gameplay, visual and
  multiplayer acceptance is still open; the owner will playtest with his brother after construction.
  Human-editor and second-machine proofs remain separate from same-host automation and do not block migration.

## What is already delivered

| Scope | Package `0adbb5ab212e` at `7719234597` | Evidence and limits |
| --- | --- | --- |
| Whole island | W00–W20 have committed coverage (29 world region scopes); W14 keeps its disabled baseline. The region receipts contain 2,750 saved object definitions. | [Regions](../world/regions/), `actors.verified.json`, `objects.saved.json`; these counts are not the number of independently split source models. |
| Recovered models | Merged:<br>- 1,048 city records;<br>- 67 train mesh records, plus 159 train texture and material records (459 packages);<br>- ten families with 141 meshes and 29 textures;<br>- 100 Japan props;<br>- 72 Brine Cove plants and city tree residuals;<br>- the two Japan leaf instances.<br>The first small-families batch (21 records, 48 packages) is merged (#797). | [PR #784](https://github.com/fontanierh/atelier/pull/784), [PR #786](https://github.com/fontanierh/atelier/pull/786), [PR #792](https://github.com/fontanierh/atelier/pull/792), [PR #794](https://github.com/fontanierh/atelier/pull/794), [PR #796](https://github.com/fontanierh/atelier/pull/796); the read-back results are below. Source completeness and remaining fused objects are tracked below. |
| Restricted and Adventure originals | 6,768 restricted package entries and 124 Adventure/animation entries have source routes; the manifest records 6,086 original pins. | [restricted.originals.json](../restricted.originals.json), [PR #785](https://github.com/fontanierh/atelier/pull/785). Private bytes stay on the pinned restricted route. This is not closure of every open source family. |
| Brine Cove individual objects | All 21 market stalls, all 265 town objects, the two harbour Soft fragments, eleven small props and three ship objects have saved placements in main ([PR #787](https://github.com/fontanierh/atelier/pull/787)). The signal mast and the shipyard slip are saved, merged and packaged ([PR #798](https://github.com/fontanierh/atelier/pull/798), [PR #800](https://github.com/fontanierh/atelier/pull/800)). Other scenery still includes fused models/patches. | [Brine Cove scope](inventory/brinecove-objects.md), [split work](inventory/brinecove-split.md), [remaining exceptions](inventory/exceptions.md). |
| Transport objects | The 10 gondola pylons and 12 railway fittings are saved as their own objects; their fused groups and the train LOD records are retired. | [PR #790](https://github.com/fontanierh/atelier/pull/790), [exceptions](inventory/exceptions.md). |
| Desktop package | Built 2026-11-10 08:38 Paris from main `7719234597` (fingerprint `0adbb5ab212e`). All automated checks pass; first launch (Slice in 15.7 s, peak 7.8 GiB, no error lines) and shutdown were observed passing. The previous `bb451f636160` (#797) app is kept. | [Package guide](PACKAGE.md). Human input, travel, gameplay, sound and persistence checks are not claimed complete. |
| Appearance | Whole-island captures exist, as well as the earlier slice route/package measurements. | [PARITY](PARITY.md) retains their exact revisions and limits; those earlier captures do not accept every later split. |

## Active work after this checkpoint

Saved, prepared and packaged totals are kept separate:
- **Saved and packaged:** everything in the table above is in the `0adbb5ab212e` package, which is main
  `7719234597`. That includes the small-families batch (#797) and the Brine Cove signal mast and shipyard slip
  (#798, #800). The package includes these imports:
  - The two used Japan leaf instances (MI_LeafAmber, MI_LeafCrimson) are material-instance records imported
    from their recipe ([PR #792](https://github.com/fontanierh/atelier/pull/792)). They read identical to the
    packaged ones.
  - 72 Brine Cove plants and city tree residuals are source records, imported and verified
    ([PR #794](https://github.com/fontanierh/atelier/pull/794)).
  - The residual Belmonte train batch has 138 texture and 21 material-instance records covering 459 packages
    ([PR #796](https://github.com/fontanierh/atelier/pull/796)). A read-only read-back matches the donor in
    parent, switches and effective values for all 321 instances, and in every setting for the 138 textures.
  - The first small-families batch (#797) has 21 records covering 48 packages:
    - 4 Hippodrome loose meshes;
    - 4 plaza textures and 3 tree house textures;
    - 10 material-instance records (37 instances).

    All 21 are imported under claim SMALLFAM. The read-back matches the editor reads of the original packages:
    - the 37 instances in parent, switches, overrides and effective values;
    - the 7 textures in every setting;
    - the 4 meshes in LODs, triangles, slots and trace.

    The donor meshes carried one convex hull, which the complex-as-simple recipe drops. That trace flag never
    uses a hull, so collision is unchanged.
- **Saved follow-ups, not in main or the package at this documentation checkpoint (`028bc6243b`):**
  [PR #803](https://github.com/fontanierh/atelier/pull/803) contains 36 material-master records, including the Hidamari
  parent. [PR #804](https://github.com/fontanierh/atelier/pull/804), based on that work, adds
  13 Japan masters (49 total); its base-materials adopted record retains only `MPC_Wind`. These supersede
  the old “19 masters still to start” list, but remain subject to review/integration. Their imported receipts
  do not upgrade the existing package or constitute final visual acceptance.
- **Remaining source/detail work:** the Hippodrome mesh residuals (14 packages on main: four Color textures
  and ten instances), the two Mega Park seam instances with two-sided base-property overrides, the standalone
  Mega Park map's reference check, `MI_TH_pane`, the Hidamari `MI_HD_flat` instance and the 41 Japan
  material instances. Parent-master recovery alone does not close their instance records. Hippodrome recovery is an active saved working-checkout
  follow-up to #804, not main content at this checkpoint. The other current material/settings classification
  rows and their branch dispositions are in [exceptions](inventory/exceptions.md#current-source-classification).

Remaining construction work:
- Close the other useful-object/source gaps in [exceptions](inventory/exceptions.md) and
  [sources](inventory/sources.md); an imported package with an unknown original stays unfinished.
- Review and integrate the saved master follow-ups above. The earlier #799/#801 preparation and
  [master recovery design](inventory/master-sources.md) explain their provenance; they are not a second backlog.
- Produce the next package checkpoint from accepted merged work and retain the existing package. The packaging
  guard fix merged in [PR #805](https://github.com/fontanierh/atelier/pull/805) is separate from a successful native rerun;
  no replacement package is claimed here. The six remaining manual acceptance checks and final owner-led
  gameplay/multiplayer playtesting remain unrecorded. Earlier same-day forecasts are superseded by these
  evidence-based states; they are not completion promises.

## Runtime and ownership facts

- The donor built most scenery at runtime. V2's `/Game/V2/Maps/Slice` now covers the island through saved
  World Partition scenery and stable ownership records. The map name and `slice` profile are historical names,
  not a coastal-only content limit. Dynamic services remain; `JapanWorld` consults the saved manifest instead
  of duplicating covered scenery. Some fused scenery still needs finer object/source ownership.
- The kart component, phone profile and phone streaming are removed from the V2 runtime. Four character
  Blueprints were cleaned after the serialized component change. Exclusions are listed below.
- V2 has its own project/build identity and `com.atelier.yorimichiv2` package identity. ElectraPlayer remains
  because the optional music library uses it. See [PACKAGE](PACKAGE.md) for current fetch/play commands.
- Mega Park rights were cleared by the owner on 2026-11-08; it is included. Restricted originals, including
  restricted sound sources, keep their pinned private route rather than being copied into public Git.

## Gameplay and shared systems

| ID | Coverage | Area | Donor baseline | Depends on | Current V2 implementation / remaining proof |
| --- | --- | --- | --- | --- | --- |
| F01 | Cairo, Modori, Nox, Paul: rigs, textures, clothes, equipment | Player and characters | implemented | — | Ported: [Player](../unreal/Source/Yorimichi/Player/) and character packages; four character Blueprints cleaned of the excluded kart component. Human appearance/animation checks remain. |
| F02 | Walk, run, sprint, jumps, crouch, climb, swim, glide, wave, interact | Player and characters | implemented | F01 | Ported: [Player](../unreal/Source/Yorimichi/Player/). Earlier walk/skate route evidence is in [PARITY](PARITY.md); full movement playtest remains. |
| F03 | Chase camera, see-through, first-person seats, collisions | Presentation | implemented | F02 | Ported: Player, Presentation and seat camera code. Human camera/occlusion checks remain. |
| F04 | Sword combat | Combat | implemented | F01, F02 | Ported: [Combat](../unreal/Source/Yorimichi/Combat/). Gameplay playtest remains. |
| F05 | Fox hunter, Kaede's trainer, Ronin camp | Combat | implemented (offline only) | F04, W01, W13 | Ported: FoxHunter and SwordTrainer spawn from JapanGameMode; camp scenery saved in W13. Keep the baseline offline-only limitations. |
| F06 | Flick-It skating | Skating | implemented | F01, Skate plugin | Ported: [Skating](../unreal/Source/Yorimichi/Skating/), shared Skate plugin and clips. Earlier route evidence is limited to its recorded revision. |
| F07 | Board carry/stow, markers, ride record/replay | Skating | partial: no player UI for replay | F06 | Ported baseline behavior: board/markers/replay code. A new player replay UI is outside this port. |
| F08 | Bike | Travel | implemented | F01, W00 | Ported: [BikeComponent](../unreal/Source/Yorimichi/Travel/BikeComponent.cpp) and recovered bike inputs. Ride playtest remains. |
| F09 | Sailboat | Travel | implemented | F01, W00 | Ported: [SailboatComponent](../unreal/Source/Yorimichi/Travel/SailboatComponent.cpp) and recovered boat inputs. Sailing playtest remains. |
| F10 | Horse: six breeds, tack, appearance | Travel | implemented | F01 | Ported: [HorseComponent](../unreal/Source/Yorimichi/Travel/HorseComponent.cpp), roster and restricted originals route. Breed/tack playtest remains. |
| F11 | Zeppelin: **four** stations (Woodland, Hidamari, Mega Park, Belmonte) | Travel | implemented | W19 | Ported: [ZeppelinService](../unreal/Source/Yorimichi/Travel/ZeppelinService.cpp), four stations and saved station scenery. Ride playtest remains. |
| F12 | Belmonte train, stations, interior, seats | Travel | implemented | W16, W20 | Ported: [BelmonteTrainService](../unreal/Source/Yorimichi/Travel/BelmonteTrainService.cpp), 67 recovered train records, saved W20 stations/track. Boarding/seats playtest remains. |
| F13 | Ferry | Travel | implemented | W17 | Ported: [FerryService](../unreal/Source/Yorimichi/Travel/FerryService.cpp); terminals saved in W17. Ride playtest remains. |
| F14 | Gondola | Travel | implemented | W18 | Ported: [GondolaService](../unreal/Source/Yorimichi/Travel/GondolaService.cpp); fixed stations and the ten per-tower pylon objects saved in W18 ([PR #790](https://github.com/fontanierh/atelier/pull/790), [transport-objects](inventory/transport-objects.md)). Ride playtest remains. |
| F15 | Horse racing, calendar, broadcasts, saves | Racing | implemented | F10, W15, W16 | Ported: [Racing](../unreal/Source/Yorimichi/Racing/) and [HorseRacing](../unreal/Plugins/HorseRacing/). Race/save playtest remains; proposed betting/stables are not added. |
| F16 | Villagers and ambient actors | Player and characters | implemented: movement only, no interactions found | W02, W07 | Ported: [VillageLife](../unreal/Source/Yorimichi/World/VillageLife.cpp). Baseline movement retained; new villager interactions are not claimed. |
| F17 | Desktop menus, English text, hints, settings | Presentation | implemented: the phone profile must be removed | — | Ported: [Presentation](../unreal/Source/Yorimichi/Presentation/); phone profile removed. Human menu/settings checks remain. |
| F18 | Painted world map, travel points | Presentation | implemented | W00–W20 | Ported: [JapanMap](../unreal/Source/Yorimichi/Presentation/JapanMap.cpp), atlas and runtime map data. Human travel/map checks remain. |
| F19 | Footsteps, combat and vehicle sounds | Presentation | partial: no train or sailboat sounds found | D05 restricted audio | Ported sound code and restricted audio packages/original links. Listening checks remain; baseline train/sailboat sound gaps are not claimed fixed. |
| F20 | Zone music director, optional library | Presentation | implemented | external music release | Ported: [JapanMusic](../unreal/Source/Yorimichi/Presentation/JapanMusic.cpp) and optional pinned music fetch/launcher route. See [PACKAGE](PACKAGE.md). |
| F21 | Painterly materials, sky, sea, foliage, effects | World | implemented | W00 | Ported: saved environment/scenery and dynamic effects. Whole-island comparison evidence is in [PARITY](PARITY.md); it is not final visual acceptance. |
| F22 | Multiplayer | Network | partial: local two-process tests only | F02–F14 | Ported: [Network](../unreal/Source/Yorimichi/Network/). Cross-machine gameplay acceptance remains; owner will test live with his brother after construction. |
| F23 | Live bridge, QA, dev tools | Presentation/Dev | implemented: single port 8830 | P2-C | Ported: [Dev](../unreal/Source/Yorimichi/Dev/) and session-targeted LiveBridge. Native packaged build has no Python input route; see [PACKAGE](PACKAGE.md). |
| F24 | Runtime data, saves, startup, packaging | World/Presentation | implemented | — | Packaged checkpoint `0adbb5ab212e` (main `7719234597`); V2 identity and staged runtime files checked. Human save/persistence checks remain. |
| F25 | Crater Park tower hoist | Travel | implemented | W12 | Ported: [CraterParkTower](../unreal/Source/Yorimichi/Travel/CraterParkTower.cpp). Hoist playtest remains. |
| F26 | Mega Park standalone level and game mode | World | implemented | W11 | Ported: [standalone profile](../game.toml) and Mega Park map/game mode. Rights cleared; standalone playtest remains. |
| F27 | In-game Dev mode and notes | Presentation/Dev | implemented | F17 | Ported: [DevNotes](../unreal/Source/Yorimichi/Dev/DevNotes.cpp). Human notes/export checks remain. |
| F28 | Friends sessions over Tailscale | Network | implemented | F22 | Ported: [JapanSession](../unreal/Source/Yorimichi/Network/JapanSession.cpp) and Tailscale adapter. Live two-person acceptance remains with F22. |
| F29 | Hair spring, cloth, seat correctives | Player and characters | implemented | F01 | Ported character presentation code and linked rig/animation inputs. Human hair/cloth/seat checks remain. |
| F30 | Train departure boards | Travel | implemented | F12 | Ported: [BelmonteTrainBoards](../unreal/Source/Yorimichi/Travel/BelmonteTrainBoards.cpp). In-game board readability/schedule checks remain. |
| F31 | Kei cars as static car-park dressing (not driving) | World | implemented | W11 | Ported static Mega Park dressing; rights cleared. These cars are scenery, distinct from excluded go-kart driving. |
| F32 | Trailer, benchmark and building-review modes | Presentation/Dev | implemented | F23 | Ported [Dev](../unreal/Source/Yorimichi/Dev/) modes. Available tools do not imply every diagnostic mode has been exercised on this package. |

Only proposals exist for the canteen lady, the tide-reader and player betting or stables. They are not
migration requirements. Baseline partial behavior is not silently counted as a new V2 feature.

## Every world region and connection

All rows below have current V2 coverage; gameplay and appearance still need the final human playtest. Saved
terrain/scatter patches are valid area owners. A patch that bundles several useful objects still needs splitting.
W10 shares W06's region scope; W19's stations belong to their host regions, so there are no separate W10/W19 folders.

| ID | Area | Current saved coverage / remaining work |
| --- | --- | --- |
| W00 | Island foundation: terrain, coast, sea, background, roads | Saved [island environment](../world/regions/w00-island/) and region scenery; source recovery merged. |
| W01 | Start, coastal road, houses | Saved [start](../world/regions/w01-start/) scenery and object placements; earlier route proof in PARITY. |
| W02 | Momiji Hamlet village | Saved [village](../world/regions/w02-village/) scenery/objects; ambient life remains dynamic. |
| W03 | Mini Mega ramp | Saved [mini ramp](../world/regions/w03-mega/); family source recovery merged. |
| W04 | Sunset Pier skate plaza | Saved [pier approach](../world/regions/w04-pier-approach/) and skate-park content; family source recovery merged. |
| W05 | Forest | Saved across five `w05-forest-*` scopes in [regions](../world/regions/); scatter stays grouped for rendering/editing. |
| W06 | Forest lake | Saved [lake/treehouse](../world/regions/w06-lake-treehouse/) scenery/objects. |
| W07 | Hidamari | Saved [harbour](../world/regions/w07-hidamari-harbour/) and [station](../world/regions/w07-hidamari-station/) scenery/objects; 1,048 city source records recovered. |
| W08 | Southwest | Saved across coast, terrace and isle-east scopes in [regions](../world/regions/); recovered models in main. |
| W09 | Brine Cove | Saved [region](../world/regions/w09-brinecove/): small props, ships, the 21 market stalls and the 265 town objects (#787), with the fused originals preserved and the emptied tiles retired. The signal mast and the shipyard slip are saved, merged and packaged ([PR #798](https://github.com/fontanierh/atelier/pull/798)). |
| W10 | Tree house | Saved under [W06](../world/regions/w06-lake-treehouse/); recovered models in main. |
| W11 | Super Ultra Mega Park and its own map | Saved [island region](../world/regions/w11-megapark/) and standalone map/profile; rights cleared. |
| W12 | Volcano and Crater Park | Saved [Crater Park](../world/regions/w12-craterpark/) plus three volcano scopes; restricted original routes linked. |
| W13 | Sword camp | Saved [camp](../world/regions/w13-swordcamp/) props; trainers/squad stay dynamic. Clearing verification remains recorded in [D10](DECISIONS.md). |
| W14 | Hidamari stable | [Site](../world/regions/w14-hidamari-stable/) retained; stable remains disabled as in the donor (`bEnabled = false`, D06). |
| W15 | Hippodrome | Saved [hippodrome](../world/regions/w15-hippodrome/) scenery/objects; racing service stays dynamic. |
| W16 | Belmonte | Saved [town/estates/courses](../world/regions/w16-belmonte/) and object placements; broader useful-object/source exceptions still tracked. |
| W17 | Ferry route | Saved [terminals](../world/regions/w17-ferry/); ships remain dynamic. |
| W18 | Gondola route | Saved [stations](../world/regions/w18-gondola/) and the ten per-tower pylon objects ([PR #790](https://github.com/fontanierh/atelier/pull/790)); cabins/ropes remain dynamic. |
| W19 | Zeppelin route (four stations) | Saved station scenery in Woodland/W06, Hidamari/W07, Mega Park/W11 and Belmonte/W16; moving service remains dynamic. |
| W20 | Railway and cross-region routes | Saved [railway](../world/regions/w20-railway/); 67 train source records recovered, moving train retained. |

## Explicit exclusions

| ID | Deferred by owner | V2 action | Status |
| --- | --- | --- | --- |
| X01 | Phone streaming, Pixel Streaming, touch controls | Not ported. Plugins disabled in `YorimichiV2.uproject`; `YorimichiPhone`, the stream hooks in `WandererCharacter`, `JapanHUD`, `JapanGameMode` and the phone profile in `JapanPreferences` are removed from the V2 copy | deferred by owner |
| X02 | Go-kart driving | Not ported. `Driving` disabled; `CarRide`, `JapanKartGrip`, kart HUD, animation and live hooks, and `/Game/Japan/Kart` stay out of V2 | deferred by owner |
| X03 | Browser and mobile ports, Hakuba rendering experiments | Not implemented | deferred by owner |
| X04 | New gameplay, engine upgrade, new art direction | Separate future work | deferred by owner |

## Keeping the status current

A content or behavior PR updates this index and its affected README, workflow notes, TODOs and comments in the
same change. Record the revision and distinguish prepared, imported, saved, merged, packaged and human-verified
work. Never promote a provisional receipt or an ownership map to accepted content. When a follow-up lands,
replace its pending row with the merged evidence rather than leaving contradictory status in another page.

The baseline inventories, dated measurements and decision history remain evidence of their named revisions;
their historical findings are not current blockers unless repeated here or in the current exceptions list.
Files under `assets/adopted/**/source/**` are pinned donor inputs, including embedded README/TODO/comments.
Preserve their bytes and provenance; current V2 instructions live in this documentation, not in rewritten originals.
