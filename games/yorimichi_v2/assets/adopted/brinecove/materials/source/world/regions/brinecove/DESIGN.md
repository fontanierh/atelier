# Brinecove design

## One-line pitch

A neutral pirate port wedged into a jungle cove: a broad stone quay at the water, a noisy market square, timber
taverns stacked three deep, stairs and rope bridges climbing the cliffs, and a lighthouse and watchtower that make
the town legible from the sea.

## Geography

Layout metres, x east, y north, z up; world = local + (-1500, -120, 0) (region.py, README.md). Sea level is 0.

| Feature | Position / extent |
| --- | --- |
| Basin | x -800..800, y -700..500 |
| Horseshoe bay | opens south; water from y -700 to about y 60 |
| Main quay | x -380..380, y 60..100, deck z 4.5 (piers 4.9) |
| Market square | x -90..90, y 100..220, z 4.7 |
| Lower town | y 100..260, z 4..8 |
| Grand stair | x -20..30, y 230..288, rises 4.6 to 30 m |
| Upper terrace | y 300..380, z 30..34 |
| Watchtower crest | x -120, y 470, z 42 |
| West headland | x -780..-430, y -180..250, z up to 70 |
| Lighthouse | x -618, y -38, base z 63 |
| East cliff and waterfall | x 430..720, y 20..330; fall at x 448, y 30, top z 55, facing the harbor |
| Shipwreck rocks | x -540, y -290 |
| Harbor statue | x -120, y -220, on a rock islet |

The bay is sheltered by two arms of land. The western arm is a rocky, jungle-covered headland with the lighthouse
on a cleared lookout. The eastern arm is a wet jungle cliff with a waterfall dropping into a rock pool behind the
shipyard. Both arms carry dense palm and hardwood canopy above exposed cliff bands; the town sits between them, with
the tallest roofs and the watchtower stepping back from the water.

## Districts

1. **The Quay.** Stone retaining wall, iron bollards, three timber piers, fish sheds, cargo cranes, crates and
   gulls. The central pier is the arrival view; the east pier serves the shipyard.
2. **Rum Row.** The first street behind the quay. Three-storey taverns, balconies, awnings, hanging signs,
   lanterns and shopfronts facing the water.
3. **Market Square.** A cobbled opening with canvas stalls, a well, a raised auction block and a big mast with
   rigging and banners. Permanent two-storey halls close the long sides so the square reads as a bazaar street,
   not a parade ground. This is the social heart and the clearest place to read the town's colour.
4. **The Terraces.** Narrow lanes and stairs climb to a second row of houses. A continuous narrow row sits on the
   terrace lip, hiding the retaining-wall top behind inhabited facades. Retaining walls, planted string courses,
   cisterns, potted palms and rope bridges make the vertical change feel inhabited.
5. **The Crest.** The watchtower, a small signal station, a cannon platform and the best view over the cove.
6. **Shipyard.** Slipway, half-built hull, timber stacks and a crane on the east shore.
7. **The Headlands.** Lighthouse and keeper's cottage to the west; waterfall, rope bridge and jungle shrine to the
   east. Dense canopy, vines and stilt shacks cover the shelves and cliff tops. These frame the town from the sea.

## Architecture

Brinecove is built from a small kit, repeated with variation:

- Stone bases in grey-green ashlar, sometimes exposed on the water side.
- Cream, ochre, faded coral and pale teal limewash walls with dark timber posts, braces and lintels.
- Deep eaves, gable or hipped roofs in terracotta, oxidized teal and dark slate.
- External stairs, timber galleries, shutters, awning frames, rope, barrels, crates, anchors and lanterns.
- Wide generated lots are split into two or three narrow facades with their own wall colour, height and roof
  material, so the waterfront reads as a row of houses rather than one long block.
- Buildings lean into the slope and step with the terraces. No two waterfront blocks share a roof height.
- Striped canvas awnings, bunting, laundry, painted shutters, flower boxes, potted plants and street goods carry the
  colour at eye level; the same kit builds all of it from flat primitives.
- Foliage is built from alpha leaf cards on branch tubes, not solid spheres: several hundred cards per crown in
  overlapping lobes with crown-centred normals, bent frond strips for palms, and card clouds for shrubs. Species
  are instanced so the headland canopy closes the way it does in the paintings.
- Cliff faces are dressed with stepped, pale prism outcrops over a darker heightfield, with ledges, fissures,
  boulder aprons and shelf vegetation; the cliff shacks are huddles of small stilt cabins with planked walls,
  porches, ladders and stove pipes, joined by plank walks.
- Big shapes first: a roofscape of overlapping planes, a forest of masts, a green canopy, and a cliff silhouette
  that stays readable from 500 m away.

## Palette

| Role | Colour |
| --- | --- |
| Limewash | warm cream `#d8c19a` |
| Ochre | `#c08a4d` |
| Coral | `#b56248` |
| Faded teal | `#4f7d77` |
| Weathered blue | `#5f8fa0` |
| Pale lime | `#a9b487` |
| Shutters | teal `#3f7570`, blue `#3d6b83`, green `#4a6b3f`, red `#9c4a3c` |
| Bougainvillea | `#d4626a` / `#e39a92` |
| Weathered timber | `#6b4d35` |
| Dark timber | `#3f3128` |
| Galleon sail canvas | `#5f6b66` |
| Terracotta roof | `#a8563e` |
| Oxidized copper | `#4f7f79` |
| Slate roof | `#4a5158` |
| Stone | `#8a7d67` |
| Jungle | `#3f5a2c` / `#58733a` |
| Water | `#1f7f8c` shallow, `#0f4257` deep |
| Lantern | `#f2c36b` |

The style is painterly and flat-shaded, with broad facets over a seamless Sunburst surface set: lime plaster, clay
roof tile, ashlar, cobbles, weathered planks, canvas, iron, foliage, natural sea-cliff rock, beach sand and
turquoise water. The eleven source surfaces expand to 41 palette-tinted material maps. Every material is tinted to
the palette above. Lighting should be a warm late afternoon with a high sun, a pale blue sky with painted clouds
and a soft haze on the far headlands.

## Composition targets

- From the harbor mouth, the eye should read: statue on the left, central pier and masts in the middle, the
  waterfall and shipyard on the right, watchtower above the roofs.
- From the water, the quay wall is a strong horizontal band; the roofs step up behind it; the cliffs close the
  composition at both sides.
- From the market, the grand stair is visible as a diagonal, with the watchtower above it.
- From the crest, the whole bay, three piers and both ships should be legible at once.
- At night, lantern strings, tavern windows and the lighthouse beam carry the silhouette. The beam is a real swept
  cone in the viewer, not a painted glow.

## Locally generated assets

The hero pieces that are hard to carve from primitives come from the documented local TRELLIS.2/MLX workflow:
the pirate-queen statue, the galleon figurehead, a harbor cannon, a large anchor, a working capstan and a ship's
wheel. Each starts from an isolated Sunburst reference on black, is matted by the pinned worker, generated on the
verified shared 15 GiB weight cache, then reduced, UV-checked, textured, scaled, seated and rendered before it is
committed. The procedural town remains the bulk of the district; the generated pieces are landmarks and props, not
a replacement for the modular building kit.
