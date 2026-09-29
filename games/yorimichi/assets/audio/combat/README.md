# Combat sounds

One-shot sounds for the bokken fight against the fox hunter, plus one countryside
ambience loop. 39 files in 18 folders. Every file comes from the Sonniss GDC Game
Audio Bundles (archive.org mirrors). They were cut, filtered, layered and level-matched
here. Nothing was generated.

All files are 48 kHz, 16-bit WAV. One-shots are mono. The ambience is a stereo loop.
Files are named `<category>/<category>_<nn>.wav`. When a category has several files,
pick one at random each time it plays.

| Folder | Files | What it is |
|---|---|---|
| `sword_swing` | 4 | A wooden stick cutting the air: short and sharp, with a falling whistle |
| `sword_swing_heavy` | 2 | A deeper, longer whoosh for the charged strike |
| `sword_charge` | 1 | A 1.4 s swell that plays while holding a charge |
| `charge_ready` | 1 | One ring of a Japanese porcelain wind bell (furin) when the charge is full |
| `sword_draw` / `sword_sheathe` | 2 + 2 | Cloth rustle with a light wooden knock |
| `hit_body` | 4 | A wooden stick hitting a body through cloth |
| `hit_heavy` | 2 | A punch, a low boom and a wood crack, layered |
| `parry` | 3 | A hard wood-on-wood clack. The third one has a thin metal ring under it |
| `claw_swipe` | 3 | Thin, fast air swipes for the fox's claws |
| `kick_swing` | 2 | Cloth whooshes |
| `dash` | 2 | Quick bursts of cloth and air |
| `player_hurt` | 3 | Body blows with no voice |
| `body_fall` | 2 | A body landing on dirt, and a body landing on dry grass |
| `fox_hurt` | 3 | Real red fox screams, with the echo faded out |
| `fox_alert` | 1 | A small dog-like growl over a single big drum hit |
| `fox_death` | 1 | A swirl of air through leaves: the spirit blowing away |
| `ambience_countryside` | 1 | A 40 s seamless loop of a rural summer day: birdsong, breeze and a faint distant sea |

`preview/<category>.wav` plays each category's files one after another with 0.4 s
gaps, so you can check a whole category quickly. The ambience preview plays the last
6 s of the loop and then the first 6 s, so you can hear the loop point.

`manifest.json` lists every file with its length, peak and loudness, its source
(archive item, path, and start/end seconds), all of its layers, and why it was picked.

## Levels

- The start of each sound sits 2 ms after sample 0, behind a 2 ms fade-in. Each file
  ends on a fade of 15 to 30 ms. DC offset is removed.
- Within a category, all files are equally loud. Loudness is the loudest 400 ms
  window, measured with the BS.1770 method.
- Hits, parries, player hurt sounds and body falls peak at -1 dBFS. `hit_body` is
  the loudness reference for the other categories:
  - swings are 4 to 6 LU quieter
  - dashes and kicks are 6 LU quieter
  - the charge swell is 6 LU quieter
  - draw and sheathe are 10 LU quieter
  - the fox sounds and the bell are about as loud as the reference
- No file peaks above -1 dBFS.
- The ambience is -30 LUFS integrated.
- In the manifest, `lufs` is integrated loudness. A file shorter than 0.4 s is
  measured as a single block. `lufs_momentary_max` is the value used for matching.

## Rebuild

```bash
python3 tools/fetch_sonniss_combat.py   # restores the 36 masters (154 MB, gitignored) and checks each md5
python3 tools/slice_combat_sfx.py       # rebuilds every WAV, the previews and manifest.json
```

The fetch script saves the masters in `audio/sonniss/combat/`. The slicer gives the
same bytes on every run, because it uses fixed cut points and a seeded dither. It
needs `ffmpeg` and `numpy`. To change a sound, edit its entry in `SPEC` at the top of
`slice_combat_sfx.py` and run the script again. `--only parry,hit_body` rebuilds just
those categories.

## Licence

Sonniss #GameAudioGDC bundle licence: royalty-free, commercial use, no attribution.
See `../sonniss/LICENSE.txt`. We may ship these sounds inside the game. We must not
sell them as a sound pack, and we must not feed them to any AI model (no training,
no audio-to-audio). All the analysis for this set was done locally, with numpy and
ffmpeg.

## Known limits

- The wooden swings last 0.15 to 0.18 s. The brief asked for 0.25 to 0.5 s, but a
  real stick swish is this short. If they feel thin at slower animation speeds, a
  drop-in replacement is David Dumais "Weapon Swings - High Swings 15" (0.3 s, 2020
  bundle).
- `parry_02` lasts 0.18 s, because the source file ends there.
- `fox_alert` and the draw and sheathe sounds are layered mixes, balanced by
  measurement only. They are the first to check by ear.
