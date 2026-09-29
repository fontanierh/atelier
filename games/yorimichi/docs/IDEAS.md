# Yorimichi — design notes

> Moved from the prototype repository on 29 September 2026. Paths are translated to this repository where the file moved; paths still starting with `japan/` or `output/imagegen/` refer to the prototype archive (authoring tools, earlier revisions, review images). See [docs/MIGRATION.md](../../../docs/MIGRATION.md).

Working notes, kept short. Decisions at the top, open ideas below. Edit freely.

## Decisions

- **Name: Yorimichi** (寄り道, "a detour on the way home"). Chosen 6 September 2026. *Komorebi* was considered
  and dropped as overused. The Unreal project and module keep their internal `JapanProto` name.
- **Hidamari** (日溜まり, a sunlit spot) is reserved as the name of a future town.
- **Momiji Hamlet** is the forest village north of the road.
- Character cel shading and ink outlines stay off by default and configurable in the Esc menu.

## The world today (see `yorimichi_world_map.png`)

- One coastal road, west to east, climbing from 10 m to 60 m. Spawn at the west end. Five houses, all in the west.
- One detour: the hamlet trail at x ≈ +90, 120 m uphill to Momiji Hamlet. The mega ramp trail continues north.
- Sea to the south, scenery only; the shore is 60 to 80 m below the road and nothing leads down to it.
- Wind is an onshore breeze from the south-south-west at 3.5 m/s, pushing up the slope.
- Everything else is forest: autumn broadleaf low, evergreens toward the ridge.

## Observations to act on

- The game is named after detours and has exactly one. The east half of the road and the whole west hillside
  have nothing to turn off toward.
- Nothing waits at either end of the road: no origin at the west edge beyond the spawn, no destination east.
- Hidamari has no place yet. Candidates: the east end where the road tops out, or across a bay to the south-east
  if the playable square grows.
- Art direction has drifted toward clean low-poly (geometry grass, paint strength 0.35, crisp edges) and away from
  the painted references of 4 September. Characters and world are not yet in the same picture.

## Ideas

### 1. South-west village, the beach, and the island temple (Henry, 6 Sep)

- A **village in the forest around the beginning of the road**, at the south-west, near the spawn.
- Past the village, a **path continues down to a beach**. On the beach, a **small stand selling coconuts**.
- From the beach you can see an **island** out at sea. On the island a **small mountain**, and at its top a
  **beautiful temple**.
- To reach the island the character uses **a board and a kite**. You cannot ride straight upwind, so the crossing
  takes **several tacks**.

Notes and implications:
- The current wind already fits: it blows from the south-south-west onto the shore, so the island (to the south)
  is upwind from the beach. Going out means tacking; coming home is a straight downwind run. That asymmetry is
  good design for free: effort out, reward, easy return.
- Kite riding is a second item like the skateboard (equip, ride, stow) with one real rule: a no-go cone of about
  45° either side of the wind; inside it the board stalls. Speed is best on a beam reach. That is enough for the
  player to discover tacking without a tutorial.
- The world needs to grow to hold it: the playable square ends 300 m south of centre and the sea there is
  scenery. The island wants to sit far enough out that the tacks matter (400 to 600 m offshore) and be tall enough
  that the temple reads from the beach as the destination.
- The beach is 60 to 80 m below the road; the village-to-beach path is the first real vertical descent in the
  game, worth designing as a view corridor (switchbacks facing the island).
- The temple at the top of the island's mountain gives the game its first true summit: a place you can see from
  almost anywhere on the coast, and that sees everything back.
- Names to decide: the south-west village, the island, the temple. Hidamari is reserved for a town and may not be
  this village.

## Status of the south-west detour (6 Sep, evening)

Integrated from branch `design/southwest-detour` (PR #2): coconut stand, kite + board, fishing village kit, summit temple,
island heightfield, world layout (village terrace, shore lane, island with trees, torii, temple), Unreal import,
and the kite mechanic (K on the shore, no-go cone, tacks). Scripted crossing test passes; the rider stance still
reuses the skateboard ride clip. See `games/yorimichi/world/regions/southwest/README.md`.
