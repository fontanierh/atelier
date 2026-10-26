# Sounds

Every sound the game plays. Each is one asset of the `sound` kind: its takes, WAV
files in `src/`, exported into one Ogg Vorbis file and the list of where each take starts and how long it lasts
(`<name>.ogg` and `<name>.takes.json`). The game plays one take at a time (`crates/audio`).

| sound | takes | what it is | where it plays |
|---|---|---|---|
| `footstep-grass/` | 12 | a step on dry grass and on a meadow | on the ground |
| `footstep-gravel/` | 13 | a step on dirt and gravel, walking and in loafers | on roads |
| `footstep-stone/` | 9 | a step on rocks | on anything built |
| `dash/` | 2 | a quick burst of cloth and air | the double jump, the dodges and the paraglider opening |
| `countryside/` | 1 | a 40 s stereo loop of a rural summer day: birdsong, a breeze and a faint distant sea | around the world |
| `glide-wind/` | 3 | rushing air at three speeds, each a seamless loop | while gliding, rising with the speed |

The takes are 48 kHz, 16-bit, mono but for the countryside's stereo;
each footstep and dash trimmed to one sound, with short fades in and out, levelled within its set; the countryside
looped with a 1.5 s crossfade; the wind levelled and its loop points closed. Each file in `src/` is named after the
recording it was cut from. Only a selection of takes is here, to keep the download small: about 490 kB
of Ogg in all.

## Licence

Every take but the wind's is cut from the Sonniss GDC Game Audio Bundles, whose licence lets a game use and modify
them royalty-free, with no attribution, and ship them inside it. It forbids selling them as a sound pack and using
them to train or drive any AI model. The wind is cut from other recordings in this repository, not from the bundles.
