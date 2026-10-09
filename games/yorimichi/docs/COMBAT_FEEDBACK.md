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

## Reviewing combat

Normal play, scripted QA and benchmarks all use the merged combat set. The live scenario checks sword drawing,
the four-cut combo, charged spin, sword guard and parry through the player's actual input handlers:

```sh
uv run atelier play yorimichi
# In another terminal, against the running game:
uv run atelier live py "TAKE='combat_review'; ONLY=['sword']; SHOTS=True"
uv run atelier live py - < games/yorimichi/scenarios/adventure_moves.py
```

Results and stills go to `build/yorimichi/adventure/moves/combat_review/`. Kaede's live training helpers exercise
the same move set against an opponent ([SWORD_TRAINER.md](SWORD_TRAINER.md)); the shield option has been removed.

`tools/mix_capture.py` remains the soundtrack mixer for live captures such as `scenarios/treehouse_walk.py`.
It rebuilds captured `audio.json` and `camera.csv` records from the source WAVs, with the game's attenuation and
panning, then encodes the frames and mix as H.264/AAC with a 720p copy.

## Limits

- The effects are CPU-driven instanced sprites, not Niagara: cheap (a few hundred quads at most) but on the game
  thread.
- The film mixer approximates Unreal's attenuation and panning; it is not a recording of the audio engine.
- Sound in play is untested on the phone stream.
