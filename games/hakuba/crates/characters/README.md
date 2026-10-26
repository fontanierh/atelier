# characters

The playable characters.

`Character` lists them. Give an entity a `Character` and it loads that character's model from `assets/` and plays
its idle in a loop. Once the model has loaded, the entity gets:

- `Clips`: the name of every clip in the model, and how fast each carries the character over the ground at its own
  speed, which the export measures (`Clips::speed`).
- `Playing`: the clip playing, how far into it, and whether it has finished.

Triggering `Play` with one of those names makes the character play it, in a loop or once, at a speed, fading from the
clip before. The node in the model's right palm gets `Grip`: what the character holds, such as the paraglider, is
spawned as its child.

Every character has every clip and its grip, so what works for one works for all. The screens that show a character
spawn it.
