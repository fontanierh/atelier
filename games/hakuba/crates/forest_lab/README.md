# Forest lab

A small, repeatable forest for building and proving how the game draws its trees, before any of it goes into the
game. It plants one dense forest of the game's own exported trees on a hill and moves the camera along a fixed path, one fixed
step per frame with the wind on the same fixed clock, so two runs see exactly the same frames. It draws them with the
game's own look: its camera, sky, sun and shadow cascades, and its foliage and impostor materials.

- With no settings, every tree is drawn in full, its middle version casting its shadow as in the game: the
  reference, what the screen should look like.
- The other settings draw the trees for less. A run logs each frame's GPU time to `frames.csv` in `LAB_OUT`, and
  with `LAB_CAPTURE=N` saves every Nth frame.
- `lab-compare REFERENCE CANDIDATE` compares two runs' frames: how much of the screen differs from the reference,
  and how many squares *shift*, their difference from the reference jumping from one frame to the next, in patches:
  what a player sees as a tree changing shape, appearing late or disappearing. `lab-compare RUN` alone counts a still
  camera's flicker. Two reference runs compare as identical, so any shift is the candidate's.

A way of drawing trees is ready for the game when, on every path, it shifts in no patch, differs from the reference
only by what anti-aliasing would, and costs far less GPU time.

```sh
cargo run --release -p hakuba_forest_lab
cargo run --release -p hakuba_forest_lab --bin lab-compare -- REFERENCE CANDIDATE
```

| Setting | What it does |
| --- | --- |
| `LAB_PATH` | `fly` (default), `walk` or `glide` |
| `LAB_OUT`, `LAB_CAPTURE=N`, `LAB_SECONDS` | where to write, every Nth frame to save, how long the path runs |
| `LAB_STILL=1` | holds the camera at the path's start, to measure flicker |
| `LAB_SPECIES` | the plants to plant, comma separated (default the four forest trees); `lab:NAME` loads `target/lab/NAME/NAME.glb` |
| `LAB_SPACING`, `LAB_SCALE` | metres between trees, and their size |
| `LAB_VERSION` | `full` (default) or `middle`, the version drawn near |
| `LAB_CASTER` | `middle` (default, as the game), `same` or `none` |
| `LAB_FAR_M`, `LAB_FADE_M`, `LAB_SWAP` | from how far, over how many metres, and to what (`impostor` or `middle`) trees swap |
| `LAB_MIDDLE_M` | under `LAB_FAR_M`: the middle version between the full one and the impostor, from that far |
| `LAB_END_M`, `LAB_CASTER_M` | how far impostors are drawn, and how far trees cast shadows |
| `LAB_SHADOWS=off`, `LAB_AA=off`, `LAB_OCCLUSION=1` | no sun shadows, no temporal anti-aliasing, occlusion culling |
| `LAB_PREPASS=1` | a depth prepass: alpha-masked leaves are cut out there, and the main pass shades only each pixel's nearest leaf |
| `LAB_SHADOW_FILTER=gaussian` | anti-aliasing without its temporal shadow filter |
| `LAB_PIXELS=M` | M million pixels instead of the game's 3 |
| `LAB_SCREEN=other` | opens on the screen that is not the main one |
| `LAB_OFFSCREEN=1` | draws into an image of the window's size, as the game does: frames are drawn and timed even while the screen is locked |
