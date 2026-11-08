# Gondola: unfinished work and known differences

This is the list of what is not finished, kept current with each review pass. [`README.md`](README.md) describes what
is built.

## Mechanism

- **Grip: jaw versus running wheels.** The grip is a detachable (MDG) grip. The **jaw** is the pair of grooved
  blocks under the housing's top body, between the two side plates. It closes on the rope, and its groove sits on the
  rope radius within 2 mm in every checked placement. The two large tyred wheels at the ends of the housing are the
  **station running wheels**. On the line they turn freely on their own stub axles, 0.30 m outboard of the rope with
  their treads at rope-axis height, and touch nothing. In the station they roll on the steel running rail (the band
  round the bullwheel bay) once the jaw has opened. The wheels sit on the cabin's outer side, so the rail and the hanger brackets clear the rope and the jaw. The build checks the
  wheels against everything except the rail, and the rest of the cabin against everything including the rail.
- **Rope size.** The rope is 90 mm across (radius 0.045 m). Real MDG haul ropes are 40 to 60 mm; it is stylised so it
  reads at riding distance. The sheave grooves, jaw groove and clearances are all built from `rope_radius`.
- **Hanging.** The cabin hangs plumb from the grip's pivot pin, which only allows pitch. Real cabins also swing a
  little across the line in wind and on deceleration; that swing is not modelled.
- **Jaws modelled closed.** The jaws are closed everywhere. In the station they would open as the wheels run onto the
  rail; instead the station rope drops 0.15 m inside the mouth, so the open state reads as the gap between the rope and
  the jaws (`station_mouth_side.png`, `station_mouth_section.png`). The build checks the jaws on the rope everywhere
  except the 1.8 m attach zone. Nothing models the detach and attach cams or the tyre conveyor that drives the
  friction plate.
- Tower sheave trains are fixed groups of four sheaves per rope on a straight carrier. There are no rocker beams, no
  compression and depression variants, and no catch hooks or rope catchers.
- The rope geometry is a parametric review path: level over the sheave train, falling 3° each side. Real spans and
  sag come with the routes. Placement must then call `rope.py` with the route's rope path, so that the grip frame and
  the groove check use the same path.

## Look

- **Cabin door side.** The door is on the face parallel to the rope, as boarding at the berth needs. In the cabin
  concept the rope runs across the door face.
- **Interior painting.** The painting's view down the cabin is matched by looking along the rope.
- **Textures.** The timber textures are procedural (`textures.py`, no paid generation): plank grain, seams, butt
  joints and roughness variation. They have no normal maps, so the seams are colour only. Painted-detail passes (wear,
  dirt, metal edge highlights) are not done.
- **Towers and stations.** These follow the concepts' style (timber framing, stone piers, tiles and shingles), but
  their structure is designed for riding and walking. The valley and crater-floor cameras are fitted to structural
  anchors, so their overlays compare roof massing, truss layout and the bullwheel under its roof directly. The fit
  residual is what remains (valley 66 px rms, crater floor 50 px on a 1536 px frame):
  - **Valley.** The painting's big gable is drawn asymmetric (the apex sits about 3 m west of the centre between its
    eaves); the model's cross-gable is symmetric over the bullwheel. The painted posts are also taller: the model's tie
    sits at 4.95 m, set by the rail frame and the passing grips.
  - **Crater floor.** The painted canopy eaves are lower than the model's, for the same reason.
  - **Rim.** The rim painting's layout does not trace: its bullwheel overhangs the deck edge under a small flat roof
    pressed against the pavilion, with no room for a 6 m loop, a pit and a walkable deck. That camera is framed by
    eye, so its overlay shows deliberate layout differences; the gabled pavilion on stone piers and the flat-roofed
    shelter over the wheel keep the painting's two roof shapes.
- **Bullwheels: horizontal at the crater floor too, for a mechanical reason.** The crater-floor concept paints a
  vertical wheel in the mechanism house. The model keeps a horizontal return bullwheel because the line arrives as
  two ropes side by side, 6 m apart (the gauge) and level, at the rope height of 3.77 m. A horizontal wheel of 6 m
  diameter turns the rope straight back into the other track with no extra rope bends.
  - A vertical wheel stands in one vertical plane, so it can only return the rope into the same track, one leg above
    the other. Restoring the 6 m horizontal gauge needs two deflection sheave assemblies, each bending the
    fully loaded haul rope a further 90 degrees.
  - A vertical 6 m wheel with its top at rope height puts the lower leg about 2.4 m below the deck: through the stone base
    and into the crater floor, under the walkable platform.
  - The detached cabins go round the station on the horizontal running rail either way. A vertical wheel would not
    change the loop; it would only add rope bends and sheave wear.
  - The house therefore covers the back of the horizontal loop: the cabins pass in through its open end, under the
    header. The drive and gearbox stand on the wheel's column.
  - Any vertical wheel shown would have to be a different machine (for example a tensioning sheave) rather than
    the return wheel. None is modelled, because it would be decoration with no function.
- **Pit railing.** A railing runs round the bullwheel bay, 0.26 m back from the pit edge. The concepts show open decks; the
  railing keeps players out of the cabins' path.
- **Berth gates.** Gates 1.6 m wide (±0.8 m about the berth) open the railing at each berth. They line up with the
  cabin door.
- **Rim boardwalk.** The boardwalk is 2.4 m wide at a 1:15 grade and curves on a 7 m radius, so a player can walk it
  without stairs. The concept's boardwalk is narrower and steeper.
- **Roof heights.** Shelter and canopy tie beams sit above the rail frame and the passing grips (canopy ties at
  4.95 m, rim shelter beams from 4.68 m), higher than the concepts' proportions.
- **Crater stair.** The stair from the deck to the crater floor has six 0.20 m risers and 0.30 m treads, with a
  1.5 m landing. The concept has no stair.
- **Ground at the mouth.** The ground beyond each mouth must stay below the pit floor (see below).
- **No set dressing.** There is no foliage, trees, pools or terrain. Those belong to world placement.

## Gameplay and placement

- Nothing is placed in the world and nothing is imported into Unreal. Routes and tower spacing are not chosen.
- The walkability audit is a raster check on the collision proxies. A game drive of the routes (the
  walkable-routes-traversable contract) needs the Unreal import.
- The ground beyond each station mouth must stay below the pit floor (−0.28 m): the cabin bottoms run 0.18 m below
  the platform there.
- **Riding logic.** Cabin spacing, the doors opening and closing in the berth, and the slow-down through the station
  are not modelled.

## Code

- `solid.py` and the raster core of `walk.py` duplicate the ferry's builder, which is not on `main` yet. Merge them
  into one shared module when the ferry lands (one-implementation-per-mechanism).
