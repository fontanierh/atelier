# glider

The paraglider, and how a character holds it. The world's player and the character viewer both use it.

Spawn `Glider::of(character)` as a child of a character's model. It loads the paraglider and plays its cloth's ripple
in a loop. Whoever spawned it sets `held` and `bank`:

- While `held`, it sits on the body over the wrists as the clip holds them, scaled to the character's size against
  its holder's: the line between the holder's wrists turned onto the line between the character's, their middles
  together. It leans `bank` radians into the turn about that middle, and both hands hold its handles.
- Put away, it is drawn too small to see, so its shaders are ready the first time it opens.

`ready_for(character)` says whether it is that character's and its model has spawned. A model that fails to load, or
whose `holder` node does not say how it was held, is reported as an error, and the paraglider stays put away rather
than holding up the game.

- `src/lib.rs` loads and places the paraglider, and logs an error whenever a closed fist misses its handle: its
  cavity more than 1.5 cm off the handle's axis, its wrist more than 5 mm off the holder's, or its palm turned more than
  3° from the holder's (lengths for a character the holder's size).
- `src/grip.rs` puts each hand on its handle as the skeleton that held the paraglider in the motion library did. Its
  export gives, in the paraglider's own frame, that skeleton's palm frame for each hand: the origin at the wrist, the
  y axis toward the knuckles and the z axis from the index finger toward the little finger. The hand turns so its own
  palm frame, from its own bones, is that one; the arm bends with two bones so the wrist lands at its origin, the
  elbow bending toward where the clip has it; then each finger but the thumb curls until it lies on the handle's
  tube. A fist's cavity is the centre of the circle its fingers' joints lie on, seen along its knuckles.

It works on the pose the animation has just written, in the body's frame, before that pose is carried to the screen,
so the hands never trail the paraglider by a frame. It reads only the bones every character has (`Hands`) and names
no character.
