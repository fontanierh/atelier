# Skate controller port

The riding controller now uses C++ adaptations of the recovered Skate 3 routines in
[2010-rust-rewrite-mashup/skate](https://github.com/chasmlol/2010-rust-rewrite-mashup/tree/7842b9e70e9aac22ed176b655dd63302618ee023/skate).
The reference commit is `7842b9e70e9aac22ed176b655dd63302618ee023`; its skate engine originated in
[SK8-ENGINE/skate-3-rust-engine](https://github.com/SK8-ENGINE/skate-3-rust-engine).
This is a controller port into the host game's existing Unreal movement, collision and animation system.
It does **not** reproduce the full board/rider rigid-body solver or claim original-console numerical parity.

## What is in the game

| Mechanism | Rust source under `skate/crates/skate-core/src` | Integration |
|---|---|---|
| Point curves | `point_graph.rs` | Endpoint handling and slope-first FMA interpolation; 4/8/16-point tables |
| Steering | `riding/steering.rs` | Input/speed response, damping, manual/push/truck-tightness scalars, deck tilt and independent truck contact/activation histories |
| Pushing | `riding/push.rs`, `riding/push_animation.rs` | Held-time strength graphs, a target speed per planted stroke, per-tick DV limits, 8.5 m/s push cap |
| Pumping | `riding/pumping/controller.rs`, `riding/pumping.rs` | Ground-normal angular speed and rising COM drive a filtered, curve-shaped, bounded speed increment; flat terrain produces none |
| Pop | `air/ground_jump/mod.rs` | Ordinary jump strength/speed/COM/ground-normal calculation and vertical bonus; no hippy-jump or special launch branches |
| Manuals | `physics/manual/controller.rs` | Pitch target and noise, P/I/D history, contact-dependent torque attenuation; applied to the procedural deck pitch |
| Landings | `animation/landing_quality.rs` | Side speed, forward speed, fakie and spin determine quality; actual board orientation survives touchdown |
| Grind forces | `physics/grind_forces.rs`, host `physics/grind/contact.rs` | Lateral pin and support-normal friction; board/slide strength differences |
| Grind assistance | `air/trajectory/grind/admission.rs`, `physics/grind_air.rs` | Descending trajectory search with native speed/angle limits and bounded displacement; UE polylines/sweeps replace native primitive investigation |
| Flick-It | `input/gesture.rs` | Point/tolerance matching, candidate score, missed-sample cancellation, held first point, refractory sample and difficulty-dependent strength |

`SkateNative.h` contains the engine-independent functions. `SkateNativeTuning.h` contains the selected retail
numeric constants/curves and **all 78 skater.pat variants** (30 unique names). These are committed source data, as
requested; no disc extraction, network access or Rust runtime is needed to build or play. Duplicate pattern names
are intentional: the original recognizer scores multiple paths for the same trick. Regular kickflips now flick
right/up; heelflips left/up. Goofy mirrors horizontally. The live bridge's `FLICKS` dictionary uses these paths.

The presets `easy`, `normal` (default) and `hardcore`, plus `TruckTightness` from 0 to 1, are exposed through
`USkateSettings` / `[/Script/AtelierSkate.SkateSettings]`. The selected preset currently changes the ported push,
pump, jump, gesture-strength and grind-admission parameters, not every EA difficulty flag.

Native controllers, gesture recognition and gameplay transitions share a **60 Hz accumulator**. Wheel and capsule
collision use two 120 Hz substeps per tick to follow steep transitions. Input is sampled before movement; fractional
frame time carries forward. Each rendered frame still updates animation/audio. Mounting or
teleporting resets controller histories. A hitch contributes at most 100 ms, avoiding a large catch-up teleport.

## Unreal adapters and remaining differences

- The actor remains a board frame with four wheel probes and swept capsule collision. EA's seven-body board,
  physical rider skeleton, wheel/truck constraint solver, contact caching and collision broadphase are not ported.
  Native truck tilt feeds a wheelbase curvature approximation, with an authored 8 m/s² lateral acceleration cap;
  finite lateral grip redirects momentum separately from heading. This is the largest remaining physics difference.
- Cairo retains the host game's authored clips and IK. Push timing comes from its foot contacts; the original push
  animation blend trees and clip root-motion attributes are absent. Native held-time strength determines the stroke
  speed target. COM height is estimated from crouch (0.85 m standing, 0.47 m fully crouched), not measured from an
  EA skeleton. The original animation graph, poses, procedural rider and camera are not included.
- The manual controller changes deck pitch. A full rigid-body/manual corrective-force solve remains absent.
  Ground support flags reflect the selected manual axle; they are not a replacement for four physical wheel contacts.
- Landings preserve orientation and tangent momentum, then use authored grip/recovery timing. Catch, grab, severe
  impact and sideways-bail gates remain the host game's. The native landing classifier does not itself define those gates.
- Grind admission searches the game's registered polylines. It does not discover arbitrary mesh edges. Assistance
  uses collision sweeps and retail admission/displacement limits; the native 12-pose contact and yaw selector is absent.
  Grinding retains the existing trick-family choice and rail follower. A single effective 80 kg mass adapts the pin
  and friction forces; material and time multipliers currently use the neutral defaults. The displayed balance is
  physical lateral offset instead of random drift. Left stick can pull the board off the rail.
- Powerslides, reverts, airborne body-spin acceleration, grab selection, flip/catch animation, scoring/combo rules,
  bails and respawn remain the host game's systems. The new retail curves do not imply parity for these systems.
- Host `sin`, `acos`, vector normalization and float conversion are used. The recovered Xenon reciprocal estimate
  and trigonometric kernels are deliberately not claimed as bit-exact.

## Checking and refreshing

From the repository root:

```sh
python3 -m unittest discover -s games/<game>/tests -p test_native.py
python3 games/<game>/tools/check_skate_reference.py --rust /path/to/mashup/skate
PYTHONPATH=platform/studio python3 -m atelier.cli build <game> unreal.compile
PYTHONPATH=platform/studio python3 -m atelier.cli qa <game> skate
```

The reference checker compiles the **actual Rust modules** alongside the C++ port. It compares 360 mixed
steering/contact frames (push, manual, fakie, hard turns, speed changes and truck reactivation) and all 78 gesture
paths. Maximum observed scalar difference: `2.9e-8`. Standalone tests also cover push saturation, flat/ramp pumping,
manual convergence, COM-dependent launch, clean/fakie/sketchy landings and fixed-step counts at 30/60/144 fps.
This is numerical/controller evidence; subjective controller feel still needs hands-on review.

`tools/import_skate_native.py --game /path/to/extracted/game --engine /path/to/skate-3-rust-engine` can audit another
owned copy. It uses the upstream VLT converter (including schema defaults and inheritance), decodes big-endian
point-graph data and reads PAT patterns. Its JSON output and intermediate files stay in ignored Content/build
folders; gameplay uses the committed tables, not the JSON. Original models, sounds, clips and executables are not
part of this change.

## Attribution

The C++ controller adaptations derive from the Rust sources linked above, distributed with the mashup under
Apache-2.0; the accompanying license is in `ThirdParty/skate-core-LICENSE`. IW4L copyright 2026 vladtrc; the mashup
fork and skating integration are by chasmlol, with the skating engine from SK8-ENGINE. The retail constants and
PAT coordinates are from the user's local Skate 3 data. All Unreal adapters, unit conversion, integration and
C++ translation are changes made for Atelier; neither this port nor the reference engine is an EA product.
