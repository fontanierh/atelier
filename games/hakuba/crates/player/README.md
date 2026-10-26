# player

The character the player controls in the world.

Once the world knows where the player starts (`hakuba_world::Spawn`), the first character spawns there, facing the
way the spawn faces, with the camera behind it. It waits there until the tile under it has loaded, then stands on it.

| | keyboard and mouse | controller |
|---|---|---|
| move | W A S D | left stick (tilt it a little to walk) |
| walk | hold Alt | |
| sprint | hold Shift | hold East (B on Xbox, Circle on PlayStation) |
| jump, double jump, paraglider | Space | South (A, Cross) |
| dodge | C | West (X, Square) or the right bumper |
| look around | drag, or the arrow keys | right stick |
| camera nearer or further | scroll | |
| pause | Escape | Start |

- `input.rs` reads the keyboard, mouse and controllers into `Controls`.
- `moves.rs` moves the player, with Yorimichi's numbers: walking, running and sprinting at the speeds the export
  measured for each clip; the jump; in the air a double jump with Yorimichi's somersault, then the paraglider; the
  dodges, a side hop when the stick points to the side, a backflip otherwise; and the landings, hard from higher than
  4.5 m. The player stands on what `hakuba_world::Ground` calls solid, steps up and down 45 cm, and is stopped by
  walls, slopes steeper than 50° and water deeper than 60 cm. Falling into deep water puts the player back where they
  last stood.
- `camera.rs` orbits the camera around the player, in front of anything solid between them.
- `glider.rs` holds the paraglider above the character, between its palms, while the player glides, banking it into
  turns. Each player has one from the start, too small to see while it is put away, so it opens without a stall.

The player holds the world's loading curtain until they stand on the ground with the paraglider ready. The moves use
only the clips every character has and their measured speeds, and the paraglider is scaled to each character's hips,
so a new character moves the same way. Nothing here names a character.

Nothing moves while the game is paused: the systems run only in `Pause::Playing`.
