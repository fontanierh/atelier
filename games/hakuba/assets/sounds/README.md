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
| `skate-roll/`, `skate-roll-wood/`, `-metal/`, `-asphalt/`, `-stone/`, `-dirt/`, `-grass/`, `-sand/` | 1 each | wheel rumble and each surface's grain, seamless loops | while the wheels roll |
| `skate-grind/`, `-slide/`, `-skid/`, `-scrape/` | 1 each | trucks on a rail, deck on a ledge, sideways wheels and a foot brake, seamless loops | during their board contact |
| `skate-pop/`, `-land/`, `-catch/`, `-push/`, `-flick/`, `-clatter/` | 3 each | tail cracks, wheel/deck slaps, foot catches and pushes, a board whirr and bail knocks | on skate events |
| `skate-pop-wood/`, `-metal/`, `-dirt/`, `-grass/`, `-sand/`; `skate-land-wood/`, `-metal/`, `-dirt/`, `-grass/`, `-sand/` | 3 each | the pop and landing on each surface | on take-off and landing |

Each skating asset records its prepared takes and provenance in `src/`. Its loops use original fixed-seed signal
synthesis. Pops, catches, clatter and hard-surface landings layer original thumps and clicks with two licensed wooden
impact recordings. Their existing recipe was prepared once into local WAV inputs; the exporter packs and encodes
those inputs. The loops need no crossfade; they are periodic by construction.

The takes are 48 kHz, 16-bit, mono but for the countryside's stereo;
each footstep and dash trimmed to one sound, with short fades in and out, levelled within its set; the countryside
looped with a 1.5 s crossfade; the wind levelled and its loop points closed. Each file in `src/` is named after the
recording it was cut from. Only a selection of takes is here, to keep the download small: about 490 kB
of Ogg before the skating cues.

## Licence

Footsteps, dash and countryside, and the wooden impacts layered into skating cues, are cut from the Sonniss GDC
Game Audio Bundles, whose licence lets a game use and modify
them royalty-free, with no attribution, and ship them inside it. It forbids selling them as a sound pack and using
them to train or drive any AI model. Each skating source that uses these recordings carries its licence notice and
recording hashes. The skating synthesis is original project work. The wind is cut from other recordings in this
repository, not from the bundles.
