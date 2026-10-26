# audio

The sounds, as Yorimichi plays them, from `assets/sounds`, at the settings' **Volume**. Two are Hakuba's own: the
step a jump pushes off with (Yorimichi's jump is silent), and the wind while gliding, which Yorimichi's kart hears and
its paraglider does not.

| sound | when | how loud |
|---|---|---|
| a footstep, on grass, gravel or stone | each time a foot plants while the player walks, runs or sprints | 0.32 at a walk to 1 at a sprint, a little higher in pitch as it speeds up, with some of each at random |
| a footstep | a jump pushing off | 0.45 |
| a footstep, lower | landing: both feet at once | 0.55 to 1.4 as the fall goes from 2 to 11 m/s; 0.6 when the paraglider lands |
| `dash`, a burst of cloth and air | the double jump; a side hop or backflip; the paraglider opening | 0.5; 0.55; 0.5 |
| `glide-wind`, rushing air | while gliding, through its three takes as the airspeed goes from 2 to 4.7 m/s | 0.2 to 0.6, fading in and out over 0.3 s |
| `countryside`, birdsong, a breeze and a faint sea | always, in the world | 0.5 |

A foot plants when, having swung 5.8 cm above where it rests, it comes back down to 2.3 cm, at least 0.1 s after
its last step: the rig's `foot_l` and `foot_r` bones are followed, so every clip, speed and character steps right
with no marks in the clips. What the foot lands on is what `hakuba_world::Ground` says: grass on the ground, gravel on
a road, stone on anything built.

Each sound has several takes, and a take never plays twice in a row. The player's sounds play as heard from the
player, without placing them around the listener; nothing plays while the game is paused, and the wind fades out.

Nothing plays before the world opens, which takes a click or a key on the menu. Browsers keep a page silent until
then, so `index.html` starts the page's audio on the first one.

```text
src/
  lib.rs     the plugin: loads every sound, starts the world's loops and keeps the countryside at its volume
  sound.rs   a sound: its Ogg file and list of takes, and playing one take
  moves.rs   the player's sounds: footsteps, landings, the moves' bursts of air, and the paraglider's wind
```
