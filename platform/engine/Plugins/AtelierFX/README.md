# AtelierFX

Cosmetic feedback without Niagara, all on the CPU and cheap: camera-facing sprites drawn as instanced quads (glow,
spark, ring, dust layers; colour and alpha as per-instance data), pooled point-light flashes, hit-stop
(per-actor time dilation), slow motion (global dilation with an ease back), camera shake, sound cues and a ribbon trail.
Experimental.

| Piece | What |
|---|---|
| `AAtelierFX::Get(World)` | the world's effects actor, spawned on first use as the configured class |
| `Spawn`, `Flash`, `LightFlash`, `Burst`, `Streaks`, `Dust`, `DustLater` | visual primitives |
| `HitStop`, `SlowMotion`, `Shake` | timing and camera (the player pawn implements `IAtelierFXTarget`) |
| `Play(Cue)`, `PlayLater` | a random variant of `<SoundFolder>/<Cue>_01.._16`, never the same one twice in a row |
| `FAtelierAudioLog` | records every sound with the frame index while a film is captured, for mixing offline |
| `UAtelierTrail` | a Catmull-Rom ribbon between two moving points (a blade) |

## What a game provides

`[/Script/AtelierFX.AtelierFXSettings]` in DefaultGame.ini: `FXClass` (its subclass, where it composes its own
reactions from the primitives, such as a sword hit, a parry or a charge), the four
sprite materials, the trail material and the sound folder. Its player implements `IAtelierFXTarget`.
