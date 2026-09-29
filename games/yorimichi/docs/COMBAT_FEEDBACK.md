# Combat feedback: effects, sound and the filmed fight

> Moved from the prototype repository on 29 September 2026. Paths are translated to this repository where the file moved; paths still starting with `japan/` or `output/imagegen/` refer to the prototype archive (authoring tools, earlier revisions, review images). See [docs/MIGRATION.md](../../../docs/MIGRATION.md).

Written 24 September 2026, alongside the combat-r02 sword clips (`game-r15`, see
[SWORD_COMBAT.md](SWORD_COMBAT.md)). Everything here is cosmetic: gameplay never reads it.

## Effects (`JapanCombatFX.h/.cpp`)

`AJapanCombatFX` is one actor per world, spawned on first use.

**Sprites.** Camera-facing quads, drawn as four instanced layers:
- glow, spark, ring: additive
- dust: translucent

Each sprite's colour and intensity come from per-instance custom data. A sprite never grows past about 16
degrees of the view, so an impact next to the lens can't white out the frame. All colours share one damping
factor (0.45), because the scene runs at daylight exposure.

**Point-light flashes.** 300–700 lm, the same range as the city's shop lights.

**Hit-stop.** `CustomTimeDilation` freezes both fighters for 55–130 ms of real time.

**Slow motion.** Global dilation (0.3) for about a third of a second on parries and full charges, easing back.

**Camera shake.** Trauma-squared Perlin noise on the follow camera (`AWandererCharacter::AddCameraShake`),
plus a brief red wash on the HUD when the player is hit.

**What each event does:**

| Event | Picture | Sound |
| --- | --- | --- |
| Strike (light / charged / full) | flash, 14–24 sparks thrown along the swing, radiating impact streaks, a ring when charged, dust at the target's feet | `hit_body` / `hit_heavy` |
| Parry | white-gold flash, sparks, streaks, two rings, 0.34 s slow motion | `parry` |
| Player hit / knocked down | red-orange sparks, shake, red wash; a body-fall thud and dust 0.55 s later | `player_hurt`, `body_fall` |
| Swing (just before contact) | slash trail | `sword_swing` / `sword_swing_heavy` |
| Charge | embers rising off the blade and a glow gathering at the tip; a flash and ring when full | `sword_charge`, `charge_ready` (a wind bell) |
| Roll, dash, fox dashes | dust puff | `dash` |
| Draw / sheathe / parry raise | | `sword_draw`, `sword_sheathe`, a soft `sword_swing` |
| Fox notices, claws, kicks, is hurt | hit flash on its material | `fox_alert`, `claw_swipe`, `kick_swing`, `fox_hurt` (first hit, heavy hits, every other hit) |
| Fox dies | falls (thud and dust at 1.95 s), then burns away into rising embers from 2.45 s over 1.7 s | `body_fall`, `fox_death` |

**Slash trail.** `UJapanSwordTrail` is a procedural ribbon between 55% of the blade and just past the tip.
- It is sampled each frame from 0.05 s before the active window to 0.04 s after.
- Catmull-Rom smoothing keeps a 20 cm-per-frame cut as a clean arc.
- A painted streak texture gives it a brush look. It fades over 0.13 s (light), 0.19 s (charged) or 0.24 s
  (full).

**Fox dissolve.** The fox's material is masked. World-space noise against a `Dissolve` parameter burns the body
away, and an ember-orange band follows the edge (`Scripts/import_fox_hunter.py`).

**Assets.** `games/yorimichi/assets/fx/gen_textures.py` makes the sprite and trail masks (deterministic).
`Scripts/import_combat_fx.py` builds `/Game/FX` (M_FX_Additive, M_FX_Dust, M_FX_Trail and the MI_FX_*
instances).

## Sound

The library is in `games/yorimichi/assets/audio/combat/`: 39 one-shots in 17 cues, plus a countryside ambience loop.
- **Source:** all from the Sonniss GDC bundles, royalty-free. Nothing is generated.
- **Rebuild:** `games/yorimichi/assets/audio/combat/fetch.py` restores the masters (gitignored) and
  `games/yorimichi/assets/audio/combat/slice.py` rebuilds the files exactly.
- **Details:** the README and `manifest.json` in that folder list sources, cuts and levels. Each cue has an
  audition file in `preview/`.
- **Import:** `Scripts/import_combat_audio.py` puts them at `/Game/Audio/Combat/<cue>_<nn>`.
- **Playback:** `AJapanCombatFX::Play` picks a variant without back-to-back repeats, with a small pitch
  spread, spatialized (full inside 4.5 m, −48 dB at 50 m).
- **Ambience:** the loop plays in 2D under everything from the start of play.

Nobody has listened to the picks yet. The sound agent flagged these as worth hearing first:
- the fox's cry (a real fox scream)
- the `fox_alert` growl-and-drum mix
- the draw/sheathe balance
- the ambience's high hiss

## Filming the fight (`JapanFightFilm.cpp`, `-fightfilm`)

```sh
games/yorimichi/tools/film_fight.sh take01                      # 1080p60 frames + camera.csv + audio.json + film.json
python3 games/yorimichi/tools/mix_fight_film.py build/yorimichi/fightfilm/take01   # soundtrack + fight.mp4 and fight-720p.mp4
```

**Staging.** The film runs the real input handlers on a fixed 60 Hz clock. The fight is staged on the middle of
the spawn road:
- Downward traces find the `Road` material's edges, 20 cm apart. The road is under 5 m wide.
- The player starts on the centreline and the fox waits 11 m ahead of the spawn, not on its grass verge.

**Script:** walk up, draw when the fox notices, parry its claw into a counter, roll back out of the kick, take
one claw, a three-strike chain, then a cut held into a full charge that kills it. Any attack the script didn't
ask to land is parried.

**Camera.** A follow camera looks along the road from behind the player at a three-quarter angle, and pushes in
on parries and charges. It switches sides if a pole blocks the view, and ends on a side view of the body
burning away.

**Sound.** Every sound the game starts is logged by captured frame. The mixer rebuilds the soundtrack from the
source WAVs with the same falloff, pans each sound by its bearing in the camera frame, adds the ambience,
limits to −1 dBFS and encodes H.264/AAC with half-second fades.

The final take on 24 September is `build/yorimichi/fightfilm/final/` (ignored; 23 s).

## Limits

- The effects are procedural sprites, not Niagara. They are cheap (a few hundred quads at most) but CPU-driven.
- The film mixer approximates Unreal's attenuation and panning. It is not a recording of the audio engine.
- Sound in play is untested on the phone stream.
