# AtelierFX

Cosmetic combat feedback without Niagara, all on the CPU: camera-facing sprites drawn as instanced quads, pooled
point-light flashes, hit-stop, slow motion, camera shake, sound cues with variant banks, and a ribbon trail for a
blade. A game subclasses `AAtelierFX` to compose its own reactions (a sword hit, a parry, a charge) from these
primitives. Gameplay never reads it. Experimental (version 0.1); it depends on AtelierCore and ProceduralMeshComponent.

## What a game provides

Settings in `DefaultGame.ini`, section `[/Script/AtelierFX.AtelierFXSettings]`:

| Setting | What |
| --- | --- |
| `FXClass` | the game's `AAtelierFX` subclass, spawned on first use |
| `GlowMaterial`, `SparkMaterial`, `RingMaterial`, `DustMaterial` | one material per sprite layer |
| `TrailMaterial` | the ribbon's material, with an `Intensity` scalar |
| `SoundFolder` | the content folder holding the sound waves, named `<Cue>_01`, `<Cue>_02` and so on (up to 16, numbered without gaps) |

The sprite materials read four per-instance custom floats: alpha, then red, green and blue. Glow, spark and ring are
meant to be additive and dust translucent. The trail material gets vertex colour and alpha.

The player pawn implements `IAtelierFXTarget::AddCameraShake(float Trauma)`; `Shake` forwards to it.

## API

| Piece | What it does |
| --- | --- |
| `AAtelierFX::Get(WorldContext)` | the world's effects actor (one per world), spawned as `FXClass` on first use |
| `Spawn(Kind, At)` | a raw sprite particle (glow, spark, ring or dust) with velocity, drag, gravity, size, colour, fade-in and wobble |
| `Flash`, `Burst`, `Streaks`, `Dust` | a glow flash; sparks thrown along a direction; fast short streaks in every direction; a dust puff on the ground |
| `LightFlash(At, Color, Intensity, Radius, Life)` | a short point-light flash from a pool of three, fading quadratically; the intensity is scaled by 0.045, so authored values in the thousands give hundreds of lumens |
| `HitStop(Seconds, A, B)` | freezes one or two actors (`CustomTimeDilation` 0.02) for real seconds, then restores them |
| `SlowMotion(Seconds, Dilation)` | global time dilation for real seconds, easing back over the last 40% |
| `Shake(Trauma)` | adds trauma to the player's camera shake |
| `Play(Cue, At, Volume, PitchSpread, b2D)` | plays a variant of `<SoundFolder>/<Cue>_NN` (see below); returns false if the bank is empty |
| `PlayLater`, `DustLater` | the same, after a delay (a body reaching the ground) |
| `UAtelierTrail` | a procedural ribbon between two moving points |
| `FAtelierAudioLog` | records every sound with its frame index while `bRecording` is set, for mixing a filmed take offline |

## Behaviour

- **Sprites.** Four instanced layers, ticked in `TG_PostUpdateWork` so they face the current frame's view. Sparks
  stretch along their velocity. A sprite never grows past 0.28 × its distance from the camera (about 16° of view), so
  an impact next to the lens cannot white out the frame. Colours are authored hot and every layer but dust is damped
  by 0.45, for daylight exposure.
- **Sound.** Each cue loads its variants on first use and plays them from a shuffled bag: every variant plays once per
  round, in random order. Pitch varies by ±`PitchSpread` (default 0.05). Spatialised sounds are at full volume inside 450 cm
  and fall off over 5000 cm (natural-sound curve) to −48 dB. Every played sound is passed to `FAtelierAudioLog`.
- **Trail.** `Sample(Base, Tip, bEmit, Strength, Dt)` is called every frame; with `bEmit` false the remaining ribbon
  fades out. Points are smoothed with Catmull-Rom (5 subdivisions), and alpha falls off as (1 − u)^2.4 along the
  ribbon. Strength 1, 2 or 3 sets the life (0.13, 0.19 or 0.24 s), the tint and the material `Intensity` (1.8, 2.6 or
  3.4).
