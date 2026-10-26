# Sounds

Every sound the game plays, from Yorimichi's sound library. Each is one asset of the `sound` kind: its takes, WAV
files in `src/`, exported into one Ogg Vorbis file and the list of where each take starts and how long it lasts
(`<name>.ogg` and `<name>.takes.json`). The game plays one take at a time (`crates/audio`).

| sound | takes | what it is | where it is from |
|---|---|---|---|
| `footstep-grass/` | 12 | a step on dry grass and on a meadow | Yorimichi's `grass` footsteps |
| `footstep-gravel/` | 13 | a step on dirt and gravel, walking and in loafers | Yorimichi's `dirt_gravel` footsteps, which it plays on roads |
| `footstep-stone/` | 9 | a step on rocks | Yorimichi's `stone` footsteps, which it plays on stone, concrete and metal |
| `dash/` | 2 | a quick burst of cloth and air | Yorimichi's `dash`, which it plays for the double jump, the dodges and the paraglider opening |
| `countryside/` | 1 | a 40 s stereo loop of a rural summer day: birdsong, a breeze and a faint distant sea | Yorimichi's countryside ambience |
| `glide-wind/` | 3 | rushing air at three speeds, each a seamless loop | the wind Yorimichi's kart hears at three speeds |

The takes are copied as Yorimichi's sound builds left them: 48 kHz, 16-bit, mono but for the countryside's stereo;
each footstep and dash trimmed to one sound, with short fades in and out, levelled within its set; the countryside
looped with a 1.5 s crossfade; the wind levelled and its loop points closed. Each file in `src/` is named after the
recording it was cut from. Only a selection of Yorimichi's takes is here, to keep the download small: about 490 kB
of Ogg in all.

## Licence

Every take but the wind's is cut from the Sonniss GDC Game Audio Bundles, whose licence lets a game use and modify
them royalty-free, with no attribution, and ship them inside it. It forbids selling them as a sound pack and using
them to train or drive any AI model. The wind is cut from the recordings Yorimichi's kart
sounds are built from.
