# AI NPCs in Yorimichi

Status: design proposal. Yorimichi is the first consumer of the platform layer in [docs/NPC_SIMULATION.md](../../../docs/NPC_SIMULATION.md). The cognition loop lives in the Atelier plugin; this page lists only what the game supplies.

## What the game supplies

- Regions and places: Hidamari, Momiji, Belmonte, Brinecove.
- NPC identities, names, prose, and voice guides.
- Jobs, wages, prices, and rent.
- Homes and their canonical occupants.
- Affordance bindings: doors, beds, food, job boards, shop counters, trains, zeppelins, benches.
- Navigation, animation, collision, and crowd LOD.
- Game save fields for identity, memory, goals, and scheduler state.

## Housing audit

| Region | Strict houses | Other residential | Notes |
| --- | ---: | --- | --- |
| Hidamari | 177 HD_House_* | 24 apartments, 22 machiya | 437 building instances total |
| Momiji | 2 cottages | 1 tea house | possibly living quarters |
| Belmonte | 11 (7 villas, 4 farmhouses) | 39 town blocks | plus civic and hippodrome meshes |
| Brinecove | 131 townhouses | 39 shacks, 43 taverns | 170 dwellings with shacks, 213 with taverns |

Strict total across the four regions: 321 houses. That is enough for 200 NPCs once apartments, machiya, and shacks are used, with room for vacancies and eviction.

## Base jobs

The world starts with shop clerk, cafe worker, station attendant, dock worker, and groundskeeper. Each has an employer, location, shift, wage, requirements, and capacity.

The world pays wages. Rent, food, taxes, and purchases at world-owned stores take money back. Stores need a clerk to open; a missing clerk means closed and no revenue. Do not tie critical transport to staffing at first.

Every NPC has a canonical home. Missed rent means eviction; the home becomes available and another NPC can take it. The evicted NPC is homeless until they recover.

Later, NPCs can start businesses: save capital, find a storefront, open, hire.

## Actor and data plan

- AYorimichiNPCCharacter: a pawn with the platform brain and sensor components, nav movement, and the existing wanderer rig.
- AYorimichiHome, AYorimichiJobBoard, AYorimichiShopCounter, AYorimichiBed, AYorimichiDoor: actors with an affordance component.
- Data under games/yorimichi/world/npcs/: identities, jobs, homes, and affordance catalog, as JSON with a schema version.
- No cognition logic in the game module. The game configures the platform.

AVillageLife stays cosmetic and separate for now.

## First milestone

Five NPCs in Belmonte: one shop clerk, one job board, two homes, one bench. Test a shift, a rent payment, a home sleep, a street sleep, one refused action, and one conversation. Measure job fill, money, happiness delta, and cost per in-game day before scaling.
