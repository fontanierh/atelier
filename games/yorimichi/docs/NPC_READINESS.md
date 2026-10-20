# Yorimichi NPC readiness audit

Status: audit. Nothing here is implemented.

Audited: 2026-10-20, after merging origin/main (c956b82b) into the design branch.

## Verdict

Yorimichi is visually ready and mechanically not ready. The streets, terrain, transport, and building silhouettes exist. The buildings are solid exteriors: doors are painted meshes, walls are one collision block, there are no interiors, no beds, no kitchens, no shop counters, no navigation, no clock, no currency, and no save.

The simulation cannot be dropped into this world. A livability layer has to be built first.

The smallest honest pilot is Momiji: five authored buildings, a tea house, a workshop, two cottages, and a storehouse. It is small enough to finish, and it contains a home, a job, and a shop in one place. Belmonte is the hardest region to retrofit and should not be first.

## What the simulation needs

| Requirement | Why | Current state |
| --- | --- | --- |
| Enterable homes | Sleep, storage, rent, eviction | None |
| Beds and kitchens | Sleep and food needs | None outside the train |
| Doors that open, close, lock | Access and privacy | Decorative only |
| Per-wall collision with openings | Walk through a door, not a wall | One solid block per building |
| Workplaces with counters | Shifts and wages | Signs only |
| Shop transactions | Buy, sell, stock, prices | No currency or inventory |
| Navigation | Walk streets, through doors, up stairs | No navmesh; pathfinding explicitly disabled |
| In-game clock and calendar | Shifts, rent, sleep, day/night | Static lighting, no clock |
| Save and load | A town that persists | No world save |
| Generic interaction | Use doors, beds, counters, people | Train, trainer, and zeppelin only |
| Observation hooks | Tell the simulation what is in range | Player-only prompts |
| 200 crowd bodies | The target population | Three cosmetic residents in Momiji |

## What already exists

- Roads, terrain, and districts are walkable. Hidamari, Momiji, Belmonte, and Brinecove have authored ground and street networks.
- Buildings have authored footprints and collision. The modular kits make procedural changes practical.
- The player already has an Interact input (WandererCharacter::Interact), used by the train, the sword trainer, and the zeppelin.
- The Belmonte train has working doors, seats, rooms, and furniture. That is a proven pattern for a door component, an interior, and an interaction prompt.
- The treehouse has authored rooms, a kitchen, and a sleeping nest. It is a set piece, but it proves the pipeline can build interiors.
- The live bridge is useful for QA and screenshots. It is not the runtime channel for the simulation.

## The blocking finding: buildings are solid

Hidamari's house and shop builders make one filled box and one collider for the whole body:

- world/regions/hidamari/build.py, shop(): a full-width box plus a single collider.
- world/regions/hidamari/kit/house.py: two solid storeys plus one body collider.
- world/regions/village/build.py, shell(): a solid box with one collider, used by the kit buildings.
- world/regions/houses/build.py, house_a/b/c: a solid plaster body plus one house-wide collider.
- world/regions/brinecove/kit.py, building(): a solid box; the door is a leaf mesh on the face.

The door meshes are decorative. No wall has a door opening. Walking through a doorway is impossible because the whole footprint is solid.

Momiji's own README says it plainly: "The buildings are modelled exteriors with closed doors."

## Doors and interaction

The only working doors in the game are on the Belmonte train (BelmonteTrainService). They open and close, have a prompt, and are replicated. There is no reusable building door actor, no lock state, no door animation, and no nav link.

The player's Interact input is wired, but each system implements its own prompt and trace. A generic interaction component is needed so the player and the simulation ask the same question: what is in range, and what can I do with it?

## Furniture and needs

There are no beds, kitchens, tables, chairs, or storage in any house. Furniture exists on the train (galley counters, benches, seats) and in the treehouse (kitchen, sleeping shelves). Both are bespoke, not a reusable furniture kit.

Hunger and sleep therefore have nowhere to happen. A bed and a kitchen are required in every home; a counter is required in every shop.

## Shops and economy

Shop buildings carry signs, awnings, and display props. There is no clerk station, no stock, no price, no purchase interaction, no player wallet, and no inventory. The racing service shows odds but has no wallet or payout.

The simulation needs at least: a counter affordance, stock, a price, a transaction, a clerk assignment, and a money ledger with source and sink accounts. The player-facing wallet and shop UI are a separate, smaller piece.

## Navigation

Yorimichi.cpp states the current position: "Yorimichi has no navigation: no navmesh, and nothing finds paths (the village and the sword trainer steer themselves)." The cook also strips static-mesh navigation data to save roughly half a GiB in the packaged game.

The cosmetic residents in VillageLife have no collision and no navigation. One walker moves between two fixed points with a ground trace.

Two options:

1. Add a navmesh. Standard, handles interiors and doors, but costs cook time and memory, and the current build deliberately removed that data.
2. Build a road and interior waypoint graph with door links. Cheaper, deterministic, and fits the simulation's path service, but more authoring and weaker for arbitrary movement.

Either way, doors, stairs, interiors, and the crowd need a path graph. This is a design decision before content work starts.

## Time

The sun is static. There is no clock, calendar, day/night cycle, shift schedule, or rent period. The simulation's tick can run on its own clock, but the game needs a shared in-game time so the player sees the same morning, workday, and night the NPCs do.

## Save and load

There is no world save. Settings persist; the town does not. The simulation needs a versioned save envelope for time, NPC records, doors, shop stock, homes, jobs, money, and scheduler deadlines. Without it, a persistent town cannot survive a restart.

## Readiness by region

| Region | Buildings | Construction | Interiors | Doors | Navigation | Effort | Use |
| --- | ---: | --- | --- | --- | --- | --- | --- |
| Momiji | 5 | Hand-authored kit | None | Decorative | Trail only | Low | First pilot |
| Rural houses | 5 | Hand-authored kit | None | Decorative | Road only | Low | Home prototype |
| Hidamari | 437 | Procedural kit | None | Decorative | Streets, no navmesh | Medium | Main town |
| Brinecove | 266 | Procedural kit | None | Decorative | Streets, no navmesh | Medium | Second town |
| Belmonte | 50 principal | Scanned meshes | None | Decorative | Streets, no navmesh | High | Later retrofit |

Hidamari's 437 instances break down as 177 back-lane houses, 27 apartment buildings, 22 machiya, 142 other shop-type buildings, 58 arcade shops, and 11 civic buildings. The 226 residential buildings are enough homes for 200 NPCs before apartments are counted as multiple units.

Brinecove's 266 are 131 houses, 39 shacks, 43 taverns, 45 shops, and 8 warehouses. Belmonte's 50 principal meshes are 39 town blocks, 7 villas, and 4 farmhouses, plus 8 village buildings and the civic set.

The counts are capacity, not livability. None of these buildings can currently be entered.

## Work breakdown

### 1. Livability kit

- Hollow the shells: interior floor, ceiling, inner wall faces, and per-wall collision with a door opening.
- Add a threshold, a door frame, and a swing or slide door that blocks when closed.
- Add stairs and upper floors where the building has them.
- Keep the exterior silhouette unchanged. Interiors are inserted behind the existing facades.
- Make it procedural so 437 Hidamari buildings and 266 Brinecove buildings do not need hand modelling.

### 2. Doors and interaction

- A reusable door component: open, close, lock, knock, animation, collision, nav link, save state.
- A generic interaction component and prompt that the player and the simulation share.
- One trace path for doors, beds, counters, job boards, benches, and people.
- A lock and permission model for homes and closed shops.

### 3. Furniture and needs

- A furniture kit: bed, kitchen counter, stove, table, chair, storage, lamp, rug, shelf.
- Placement rules per room size and building type.
- A usable bed and kitchen affordance, with sleep and food effects.
- A sleeping-rough option on benches and the ground.

### 4. Shops and economy

- A counter affordance with a clerk slot, stock, price, and transaction.
- A money ledger with source and sink accounts, so conservation is testable.
- A minimal player wallet, inventory, and purchase prompt.
- Stock and restock rules that a shop clerk can own.

### 5. Navigation

- Choose navmesh or waypoint graph.
- Cover streets, door thresholds, stairs, interiors, and vehicle boarding.
- Add door links that close when the door is locked.
- Add crowd avoidance and a path-failure signal for the simulation.

### 6. Time and schedules

- A world clock with a defined day length and calendar.
- Sun and sky driven by time, or a small set of lighting states for the pilot.
- Shift, rent, and sleep periods derived from the clock.

### 7. NPC bodies and crowd LOD

- A navigable pawn with collision, locomotion, and the existing character rig.
- Idle, walk, sit, sleep, work, and talk animations.
- Distance and occlusion LOD, plus a cheap off-screen representation.

### 8. Persistence

- A versioned save envelope for the simulation state and the game state it touches.
- Save and reload tests at door, interior, and region boundaries.

### 9. Observation bridge

- Room and building identity, door state, occupancy, and the nearby affordance list.
- The same data in the editor, the game, and the headless adapter.

## Pilot and acceptance

Momiji pilot, five buildings:

1. Enter and leave both cottages and the tea house through working doors.
2. Walls collide; the doorway is the only way in.
3. Each cottage has a bed, a kitchen, and storage. The tea house has a counter and stock.
4. One NPC wakes, eats, walks to the workshop, works a shift, walks home, and sleeps.
5. The player can talk to that NPC, buy tea, and see the shop close when the clerk leaves.
6. Save, reload, and continue the same day.
7. Five NPCs run at the target frame rate with no stuck paths or teleports.

This pilot is the gate. Do not scale to 200 or start Belmonte before it passes.

## Sequence

1. Prototype the livability kit on one rural house and one Hidamari shop. No simulation.
2. Build the Momiji pilot: five buildings, one NPC, one shop, one clock.
3. Add the generic interaction and door components, then navigation through doors.
4. Add five NPCs and the platform adapter. Test a full day, save and reload.
5. Convert one Hidamari street: six homes and two shops, then ten NPCs.
6. Add the economy, rent, eviction, and a job board.
7. Scale to 200 with crowd LOD. Then consider Belmonte.

## Risks

- Navmesh memory. The current cook strips navigation data to save about half a GiB. Re-enabling it changes the package and load budget.
- Belmonte's scanned meshes cannot be hollowed cheaply. It needs authored interior shells or a separate interior layer.
- Interiors multiply draw calls, lights, and occlusion work. Bake lighting where possible and keep interior props instanced.
- Procedural interiors need rules; hand-modelling 700 buildings is not viable.
- Door and stair links are where pathfinding usually breaks. Test them before adding NPCs.
- Save format and determinism must be settled before content scales.

## Open questions

- Navmesh or waypoint graph?
- How long is an in-game day, and does the sun move?
- Do apartments count as one home or several?
- Is the player wallet global, or per region?
- How much of Belmonte can be reused, and how much needs authored interiors?
- Which region is the second town after Hidamari?
