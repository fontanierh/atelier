# characters

The playable characters.

`Character` lists them. Give an entity a `Character` and it loads that character's model from `assets/` and plays
its idle in a loop. Once the model has loaded, the entity gets `Clips`, the names of every clip in the model.
Triggering `Play` with one of those names makes the character play it.

The screens that show a character spawn it.
