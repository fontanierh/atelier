# Footsteps — first sound pass

Game-ready footstep one-shots, sliced from the Sonniss GDC Game Audio Bundles.
Everything here is **48 kHz, 16-bit, mono**, peak-normalised to −3 dBFS, with a 3 ms
fade in and a 30 ms fade out. Mono on purpose: these get spatialised in engine.

## What's here

| Surface | Files | Where it goes in the world |
| --- | --- | --- |
| `dirt_gravel` | 71 | village paths, the track up to the shrine, courtyard gravel |
| `grass` | 79 | meadows, the hillsides, anything off-path |
| `leaves` | 191 | forest floor around the lake and under the tree cover |
| `wood` | 110 | engawa, temple steps, boardwalks, the zeppelin deck |
| `barefoot` | 50 | interiors — the tatami stand-in until we record something closer |
| `mud_water` | 21 | rice paddy edges, the shallows, puddles after rain |
| `stone` | 9 | stone steps and rock — **thin, needs more** |

`manifest.json` maps every one-shot back to the file and timestamp it came from.
`preview/<surface>_walk.wav` is ten of them laid out at a walking pace so you can hear
what the round-robin will sound like; `preview/<surface>_sheet.png` is the waveforms.

## Regenerating

The raw library masters (96/192 kHz, 24-bit, long performances — 86 MB) live in
`audio/sonniss/` and are **gitignored**. To rebuild from scratch:

```bash
python3 tools/fetch_sonniss_footsteps.py   # pull masters from the archive.org mirrors
python3 tools/slice_footsteps.py           # detect footfalls, slice, normalise
python3 tools/preview_footsteps.py         # montages + waveform sheets
```

`slice_footsteps.py` finds footfalls with a short-time RMS envelope, refuses slices
under 70 ms or with the loudest moment in the back half (those are clipped steps), and
never lets a slice run into the next footfall.

## In engine

Wired up and playing — see [docs/FOOTSTEPS.md](../../docs/FOOTSTEPS.md). Short version:
`UJapanFootstepComponent` watches the foot bones for a plant, traces once to read the
material under the foot, and draws from a shuffled bag per surface with pitch and volume
scaled by speed. `japan/run.sh footsteps` rebuilds the whole chain.

It ended up as C++ rather than MetaSounds: the animation graph is native with no Blueprint
to hang anim notifies on, and bone-height detection works for every clip and play rate
without authoring markers per animation.

## Licence

Sonniss #GameAudioGDC bundle licence — see `../sonniss/LICENSE.txt`. Short version:
royalty-free, commercial use, no attribution, modification explicitly allowed, and we
may ship them inside the game. Two things we must not do: sell them as a sound pack in
their own right, and **feed them to any AI model** as training or audio-to-audio input
(the licence forbids AI use outright). That matters given the ElevenLabs plan in
`docs/SOUND_RESEARCH.md` — prompts are fine, these files as model input are not.

## Gaps

- `stone` is 9 one-shots from a single source. Needs a real stone/rock pass.
- No tatami, no gravel-under-sandal (geta/zori), no snow, no metal.
- Everything is a *walk*; runs are in there but not separated by pace. If the run needs
  its own weight, slice `sv_leaves_run` and the Tovusound jog into a `_run` pool.
