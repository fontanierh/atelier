# characters

Character models and their animation playback.

`Character` lists them. Give an entity a `Character` and it loads that character's model from `assets/` and plays
its idle in a loop. Once the model has loaded, the entity gets:

- `Clips`: the name of every clip in the model, and how fast each carries the character over the ground at its own
  speed, which the export measures (`Clips::speed`).
- `Playing`: the clip playing, how far into it, and whether it has finished.

Triggering `Play` with one of those names makes the character play it, in a loop or once, at a speed, fading from the
clip before. The node in the model's right palm gets `Grip`: what the character holds in that hand is spawned as its
child. `Hands` names each arm's bones, for what it holds in both hands, such as the paraglider (`hakuba_glider`): the
upper arm, forearm and hand, and the three bones of each finger but the thumb.

Playable characters use the shared clips and grip. A model with authored clips keeps its own skeleton and clips;
its export can also request emission proportional to its vertex-tinted base colour. Models without that profile keep
their original material.
