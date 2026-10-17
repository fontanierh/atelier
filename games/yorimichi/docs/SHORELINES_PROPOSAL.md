# Island shoreline proposal

Approved concept proposal, 17 October 2026. The original survey covers the complete island perimeter and separate
temple islet, with ten coastal treatments. Implementation follows this direction on the review branch. Actual game
captures, checks and current limits are published in the [implementation review](shorelines/review.html); the
Sunbursts below remain design references.

The tailnet presentation is mounted at `/shorelines/` on the development machine's existing HTTPS endpoint.
It contains a selectable survey map, southern detail, ten Sunburst concepts, location briefs and a proposed build
order. The site source is in [`shorelines/`](shorelines/); final concept references and full prompt/provenance records
are in [`assets/shorelines/concepts/`](../assets/shorelines/concepts/). PNG masters and generated survey evidence
remain under `build/yorimichi/shorelines/`. A separate machine-local copy serves the presentation persistently.

## Survey findings

The source audit uses revision `f0c7e40d07802ce9feabd00c7bc0eeca63dce7ba`. Coordinates below are Blender metres:
x east, y north, z up. The sea is at z=0.

- **Belmonte's surrounding country has broad coplanar strips.** `belmonte/terrain.py` multiplies its country height
  by two clamped smoothstep masks that become zero at x <= -3000 or x >= 3000. Its grid extends to x = +/-3200.
  There are 276 entirely flat zero-height quads in the exported north-country grid above y=3200, covering
  approximately 916,210.5 square metres. These sit at the main sea plane's height. The north taper also reaches zero
  exactly at its terminal row, y=7100, without a submerged continuation. The imported Belmonte valley is inland,
  at x=-474.5..1573.5 and y=3899.5..5691.5; its authored relief need not change.
- **The far hills end abruptly.** `build_terrain.py` exports a 96 by 96 vertex heightfield over a 6400 m square,
  with roughly 67.37 m cell spacing and no closing cliff faces. The east and west edges are still elevated. They need
  a coastal profile, closed faces and submerged toes, rather than an exposed mesh boundary.
- **The south coast lacks a continuous treatment.** A small sand pad and detour lane are present near the original
  cove. They do not establish a continuous beach below spawn or along the city's frontage.
- **The harbor has a second water sheet.** `hidamari/build.py` creates `HD_Sea` at z=0.025 above the main sea at z=0;
  `sea_look.py` documents their shared look. Audit ownership at their overlap and boundary before adding more shore
  surfaces. The sea already uses derivative-filtered waves and scene-depth surf; new foam alone is not a geometry fix.
- **The temple islet already has a designed coast.** Keep its authored 8–38 m rock cliffs and four sea stacks. Focus
  changes on the landing cove, its connection to the stairs, and the wet/submerged transition.

The zero-height geometry is confirmed from source and grid topology. Its contribution to the owner's reported
flicker is a hypothesis pending a controlled in-game A/B. At the original proposal stage, no new Unreal session or
temporal flicker measurement had been run. Subsequent implementation evidence belongs to the separate review page.
The regional map samples at 12.5 m, omits park stamps on the volcano and shows imported
Belmonte relief as a footprint. Input hashes and limits are recorded in the site's `assets/survey.json`.

## Complete perimeter coverage

Concept dimensions are design targets, not surveyed existing dimensions. Each location's coordinate envelope is
recorded in [`shorelines/sectors.json`](shorelines/sectors.json); these are regional envelopes, not final construction
boundaries. All images establish materials and coastal form; they are not registered before/after renders.

| ID | Stretch | Proposed treatment | Order |
| --- | --- | --- | --- |
| 01 | Spawn and Sunset Pier | 20–35 m pale sand crescent, low rock shoulders and submerged sand shelf; keep road, pier and crossing clear | First |
| 02 | Hidamari south and harbor | Existing working quay and breakwater, 15–25 m sand pockets, short stone revetments; keep canal and navigation open | First |
| 03 | Far east / city headland | Scalloped 15–45 m rock cliffs with 10–20 m sand coves; close the coarse outer terrain inside its present envelope | First |
| 04 | Volcano east / railway coast | Broken 30–80 m charcoal rock cliffs and gravel coves; preserve the inland railway corridor and earthworks | Second |
| 05 | Belmonte east | Two or three 30–60 m ochre sand bays between low rocky points; replace the zero-height apron with a submerged shelf | First |
| 06 | Northern cape | A broad sand crescent between low rocky capes and small dunes; establish a dry coast before the terminal terrain row | First |
| 07 | Belmonte west | 25–50 m sheltered sand coves alternating with 10–30 m wooded bluffs; remove the full coplanar strip | First |
| 08 | Western volcano coast | Broad 40–100 m cliffs with wet rock shelves and sparse pebble landings; close the outer terrain | Second |
| 09 | Southwest outer coast | 10–40 m wooded headlands and small coves, lowering gradually toward spawn; keep the islet passage clear | Second |
| 10 | Temple islet and landing | Retain cliff silhouette and stacks; make the landing a 12–20 m usable beach tied into the existing stair | Second |

## Implementation and acceptance

First remove the north-country zero-height shelves and close its northern cape, then establish the spawn beach,
harbor transitions and eastern city headland. Finish the long volcanic cliff coasts and southwestern return, and
polish the existing temple landing. Keep the inland valley, roads, railway, pier, navigation routes and existing
landmarks intact. A continuous shoreline does not require a continuous pedestrian trail across every cliff.

Build the ground through sea level as one coherent profile with a dry backshore, wet transition and submerged toe.
Stitch adjacent terrain boundaries; avoid nearly coplanar duplicate sand ribbons. Audit the harbor/open-sea water
ownership. Use broad rock masses and material bands that survive distance, then add restrained surf detail.

Acceptance covers a moving view from a standing volcano-rim camera toward Belmonte, a complete perimeter camera
tour, accessible beach ground/collision checks and near/far views. Boat launch and landing checks follow the game's
existing southern-ocean sailing bounds. Use normal forward lighting and saved renderer/tree preferences. Check for
shimmer, open edges, floating foliage, blocked boat approaches and exposed terrain seams. Consult the implementation
review for the actual results and limits; the concept images establish the design direction.

## Concepts and validation

All ten images use `gpt-image-2.5-sunburst`, `quality=high`, 1536 by 1024, through the repository's
`atelier.ai.images.paint` and `atelier.ai.ledger`. Each call completed once without retry. Existing game imagery
provided art direction only. The original PNG hashes, prompts, model, usage and call timing remain in the provenance
records; the committed JPEGs are compact presentation derivatives.

The static presentation passed JavaScript syntax checks and Chrome checks at 1440 by 1000 and 390 by 844: all ten
concept images loaded; sector selection, southern zoom, gallery filters, image expansion and Escape close worked;
no script errors or horizontal overflow were observed. Repository lint passed. No full local Python suite was
needed for this proposal. Hosting verification and browser evidence remain under `build/yorimichi/shorelines/`.
