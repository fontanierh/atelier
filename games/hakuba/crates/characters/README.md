# characters

The playable characters.

`Character` lists them. Giving an entity a `Character` loads that character's model from `assets/` onto it and plays
its idle in a loop. Once the model has loaded, the entity has `Clips`, the names of every clip in the model; triggering
`Play` with one of those names switches the character to it.

This crate spawns no character; the screens that show characters do.
