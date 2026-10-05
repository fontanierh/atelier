# Combat feedback

The sword fight's effects, sounds and filmed fight. `AYorimichiCombatFX` (`YorimichiCombatFX.h/.cpp`) composes each
combat event (a swing, a hit, a parry, a charge, the player getting hurt, a fox burning away) from the primitives of
the platform's AtelierFX plugin ([README](../../../platform/engine/Plugins/AtelierFX/README.md)): instanced sprites,
point-light flashes, hit-stop, slow motion, camera shake, sound cues and a ribbon trail. It is all cosmetic; gameplay
never reads it. The rules of the fight are in [SWORD_COMBAT.md](SWORD_COMBAT.md) and
[FOX_HUNTER_COMBAT.md](FOX_HUNTER_COMBAT.md).

## Build

```sh
atelier fetch yorimichi                                    # sound masters into ~/.cache/atelier/sonniss
atelier build yorimichi audio.combat unreal.sounds         # cut the combat sounds, import /Game/Audio/Combat
atelier build yorimichi fx.textures unreal.fx              # sprite and trail masks, /Game/FX materials
```

`fx.textures` runs `assets/fx/gen_textures.py`, which writes deterministic greyscale masks to
`build/yorimichi/combat_fx/`: `T_FX_Glow`, `T_FX_Spark`, `T_FX_Ring`, `T_FX_Dust` and `T_FX_Trail` (broken brush
streaks for a painted look). `unreal.fx` runs `unreal/Scripts/import_combat_fx.py`, which builds `/Game/FX`:

- `M_FX_Additive`: unlit, additive, two-sided, for the sprites, with colour and intensity from per-instance data and
  the texture's red channel as the mask. Instances `MI_FX_Glow`, `MI_FX_Spark` and `MI_FX_Ring`.
- `M_FX_Dust` and `MI_FX_Dust`: the same inputs, translucent, so dust covers rather than adds light.
- `M_FX_Trail`: unlit, additive, two-sided, for the slash ribbon: vertex colour times vertex alpha times the streak
  texture times an `Intensity` parameter.

`DefaultGame.ini` points AtelierFX at these, at `/Game/Audio/Combat` for sounds, and at
`/Script/Yorimichi.YorimichiCombatFX` as the effects class (`[/Script/AtelierFX.AtelierFXSettings]`).

## Events

| Event | Picture and timing | Sound |
| --- | --- | --- |
| Swing, 0.06 s before the active window | the slash trail | `sword_swing`, or `sword_swing_heavy` for a charged strike |
| Sword hit (quick, charged, full) | hit-stop 55, 80 or 130 ms on both fighters; two flashes; 14, 17 or 20 sparks thrown along the swing; 4 streaks (7 when charged); a ring when charged; a 495–718 lm light flash; shake 0.28, 0.45 or 0.75; dust at the target's feet; 0.32 s of slow motion (0.3×) on a full charge | `hit_body`, or `hit_heavy` when charged |
| Parry | hit-stop 90 ms; white-gold flashes, 30 sparks, 7 streaks, two rings; a 720 lm flash; shake 0.5; 0.34 s of slow motion (0.28×) | `parry` |
| Parry raise | | a soft `sword_swing` |
| Player hit | hit-stop 70 ms; 12 red-orange sparks and streaks; a 405 lm flash; shake 0.6; a red wash on the HUD | `player_hurt` |
| Player knocked down | as a hit with 120 ms hit-stop, shake 0.9 and a full wash; a thud and dust 0.55 s later | `player_hurt`, `body_fall` |
| Guard broken (a heavy blow on the guard) | 26 gold sparks thrown back off the guard, a flash; shake 0.6 | `hit_heavy` |
| Charge winding up and held | embers rising off the blade (26 to 96 a second as the charge fills) and a glow gathering at the tip | `sword_charge` |
| Charge full | a flash, a ring, 14 sparks, a 360 lm flash | `charge_ready` (a wind bell) |
| Roll, dash, fox dashes | a dust puff | `dash` |
| Draw, sheathe | | `sword_draw`, `sword_sheathe` |
| Fox notices, claws, kicks | | `fox_alert`, `claw_swipe`, `kick_swing` |
| Fox hit | its material flashes for 0.22 s | `fox_hurt` (first hit, charged hits, every other hit) |
| Fox dies | the body lands at 1.95 s with dust, then burns away from 2.45 s over 1.7 s into rising embers, ending in a burst and a flash | `body_fall`, `fox_death` |

Hit-stop sets `CustomTimeDilation` on both fighters for real time; slow motion is global and eases back. Camera shake is trauma-squared Perlin noise on the follow camera
(`AWandererCharacter`, which implements `IAtelierFXTarget::AddCameraShake`).

**Slash trail.** The sword component's `UAtelierTrail` runs from 55% along the blade to just past the tip. It is
sampled from 0.05 s before the active window to 0.04 s after, smoothed with Catmull-Rom so a 20 cm-per-frame cut stays
a clean arc, and fades over 0.13 s (quick), 0.19 s (charged) or 0.24 s (full).

**Fox dissolve.** The fox's material (`unreal/Scripts/import_fox_hunter.py`) is masked: world-space noise against a
`Dissolve` parameter burns the body away, with an ember-orange band along the edge.

## Sound

The combat sounds are in `assets/audio/combat/` ([README](../assets/audio/combat/README.md)): 38 one-shots in 17
cues plus the countryside ambience loop, all cut from Sonniss GDC bundle masters. `unreal.sounds` imports them as
`/Game/Audio/Combat/<cue>_<nn>`; the ambience is imported looping.

Each cue plays a random variant from a shuffled bag (every variant once per round), with a small pitch spread,
spatialised: full volume inside 4.5 m, then a natural falloff over 50 m down to −48 dB. The ambience
(`/Game/Audio/Combat/ambience_countryside_01`) plays in 2D at half volume from the start of play.

## Filming the fight

`-fightfilm` (`JapanFightFilm.cpp`) films a scripted fight against the fox through the real input handlers on a fixed
60 Hz step:

```sh
games/yorimichi/tools/film_fight.sh take01                                        # frames, camera.csv, audio.json, film.json
python3 games/yorimichi/tools/mix_fight_film.py build/yorimichi/fightfilm/take01  # soundtrack, fight.mp4 and fight-720p.mp4
```

`film_fight.sh <take> [extra -set= preferences]` runs the game offscreen at 1920 × 1080 under the memory guard
(`atelier.safety.guarded`) and writes `build/yorimichi/fightfilm/<take>/`: `frame_NNNNN.jpg`, `camera.csv`,
`audio.json` (every sound the game started, by captured frame), `film.json` (the counts and the step log) and
`game.log`.

- **Staging.** Traces every 20 cm across the road, 2 m behind and 10 m ahead of the spawn, find the edges of the
  `Road` material. The player starts on the centreline; the fox waits about 11 m ahead, on the road (seed 11).
- **Script.** Settle, walk up, draw, parry a claw into a counter, roll back out of a kick, draw again, take a claw,
  recover, a three-strike chain, breathe, a cut held into a full charge that kills the fox, sheathe, hold. Any attack
  the script did not ask to land is parried 0.19 s before its window. The film stops after 70 s at most.
- **Camera.** A three-quarter view from behind the player along the road, held within 35° of it, pushing in on
  parries and charges. It changes side when the view is blocked for 0.2 s and ends on a side view of the body burning
  away.
- **Mix.** `mix_fight_film.py <take folder> [--out fight]` rebuilds the soundtrack from the WAVs in
  `build/yorimichi/audio/combat/` and the footsteps: each sound is pitched, attenuated by its distance from the camera
  with the game's falloff, and panned by its bearing in the camera frame; the ambience loops underneath. A soft limiter
  peaks at −1 dBFS. The output is H.264/AAC at 1080p60 plus a 720p copy, with a 0.5 s fade in and a 1.2 s fade out.

## Limits

- The effects are CPU-driven instanced sprites, not Niagara: cheap (a few hundred quads at most) but on the game
  thread.
- The film mixer approximates Unreal's attenuation and panning; it is not a recording of the audio engine.
- Sound in play is untested on the phone stream.
- Reading the film script: the roll keeps the sword drawn, so the "draw again" step sheathes it, and the steps that
  wait for guard (recover, the chain, the full charge) would time out with the fox alive. Check a take before relying
  on it.
