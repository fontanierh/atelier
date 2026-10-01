# Footsteps

The game's footstep one-shots, sliced from the Sonniss GDC Game Audio Bundles: 531 steps across seven surfaces, all
**48 kHz, 16-bit, mono**, peak-normalised to −3 dBFS, with a 3 ms fade in and a 30 ms fade out. Mono on purpose: the
engine spatialises them. How the game plays them is in [docs/FOOTSTEPS.md](../../../docs/FOOTSTEPS.md).

## Building

```bash
atelier fetch yorimichi                       # the masters, into ~/.cache/atelier/sonniss/footsteps
atelier build yorimichi audio.footsteps       # slice them into build/yorimichi/audio/footsteps
atelier build yorimichi unreal.sounds         # import them into Unreal
```

| File | Does |
| --- | --- |
| `bank.toml` | the bank: cue names `footstep.<surface>`, fetch and build scripts |
| `fetch.py` | downloads the selected masters (96/192 kHz, 24-bit, long performances, 86 MB) from the archive.org mirrors |
| `slice.py` | converts to 48 kHz mono with ffmpeg, finds each footfall, slices, trims, fades and normalises (`--surface <name>`, `--dry-run`) |

The masters stay out of the repository. `slice.py` writes `<surface>/<surface>_<stem>_<nn>.wav` and a `manifest.json`
that maps every one-shot back to its source file, offset and duration. It finds footfalls with a short-time RMS
envelope, never lets a slice run into the next footfall, and rejects slices under 70 ms or with the loudest moment past
55% of the slice (those are clipped steps). It needs ffmpeg and numpy.

## Surfaces

| Surface | Files | Heard on |
| --- | --- | --- |
| `dirt_gravel` | 71 | roads, lanes, sand and dirt |
| `grass` | 79 | the terrain, hills, grass and moss; the default for anything unmapped |
| `leaves` | 191 | leaf litter and the forest floor around the lake |
| `wood` | 110 | wood, bark, lattice and the tree house's timber |
| `barefoot` | 50 | the tree house's rugs, cushions and quilts (hardwood recordings) |
| `mud_water` | 21 | water and mud |
| `stone` | 9 | stone, rock, concrete, tile, plaster and metal |

## Licence

Sonniss #GameAudioGDC bundle licence — see [SONNISS-LICENSE.txt](../SONNISS-LICENSE.txt). Short version:
royalty-free, commercial use, no attribution, modification explicitly allowed, and we
may ship them inside the game. Two things we must not do: sell them as a sound pack in
their own right, and **feed them to any AI model** as training or audio-to-audio input
(the licence forbids AI use outright).

## Known gaps

- `stone` is 9 one-shots from a single source.
- No tatami recordings, no gravel under sandals (geta, zori), no snow, no metal-specific steps.
- Every pool is a walk: runs are in the sources but not separated by pace.
