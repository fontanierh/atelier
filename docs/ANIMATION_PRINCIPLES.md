# Animation principles

The craft rules behind the games' authored clips, distilled from Richard Williams' *The Animator's Survival Kit* and
translated for procedurally authored clips on skinned rigs, played by a state machine in Unreal. Section 1 is the
ideas, section 2 the numbers (the walk chart the gait code follows), section 3 how they apply to game clips. Code cites
these sections by number: in Yorimichi, for example, [`cairo_clips.py`](../games/yorimichi/assets/characters/tools/cairo_clips.py)
and [`fox_hunter_animate.py`](../games/yorimichi/assets/characters/tools/fox_hunter_animate.py) take their weight and
arm phasing from §2 and their hard accents from §1.

## 1. The load-bearing ideas

**Timing vs spacing.** Timing is *when* things hit, the beats. Spacing is *how the in-between positions cluster*
between those beats. Two moves with identical timing and different spacing read as completely different actions. "The
clip is 0.8 s long" is timing; "the pelvis spends most of those 0.8 s near the bottom" is spacing, and it has to be
designed, not left to whatever curve the pose function happens to produce.

**The breakdown is the secret.** Given two extremes, the most consequential choice is where the middle position goes.
Do not go straight from A to B; go somewhere else interesting on the way. It is the cheapest source of character in a
move.

**Weight is the up and down of the masses.** Not smooth level travel. Exaggerate the vertical: traced live action
floats. The weight is felt at the **down** position, where the leg is bent and absorbing, not at the contact. A walk
with no vertical on the head reads as weightless.

**Contact before deformation.** Put a frame where the thing *just touches* before it squashes or absorbs: one extra
position at the moment of touch, then the compression. It is what separates a landing that lands from one that melts.

**Flexibility from broken joints, not rubber.** "Breaking" a joint means bending it, even past what anatomy allows, and
doing it *successively*: the elbow leads, the forearm follows, the wrist follows, the fingers arrive last. This gives
curved, limber motion out of rigid bones, without squash and stretch.

**Overlapping action.** Nothing starts or stops at the same time. Most big body actions start in the hips; the head is
usually delayed; cloth, hair and soft mass arrive last and counter the body (body up, hair down). The failure is
everything moving the same amount at the same time (Williams calls it the "King Kong effect").

**Anticipation.** Before going one way, first go the other. A bigger anticipation means more latent force, and the
anticipation is usually slower than the action. *Invisible* anticipations, 1 to 3 frames in the opposite direction,
too fast to see, are where snap comes from.

**Hard accent vs soft accent.** A hard accent (hammer on anvil, a karate kick) **bounces back** after the hit. A soft
accent (a conductor's baton, a friendly gesture) **keeps going** through it.

**Never use normal timing.** Go slightly too fast, then slightly too slow, and keep switching. Contrast is the engine:
slow against fast, straight against curve, concave back against convex back.

**The mind is the pilot.** There is a beat of thinking before the body acts. A change of expression shows thought, and
it must sit *where the audience can see it*, never buried inside a fast move.

**Believability, not realism.** The goal is never to copy life but to make an invented move convincing.

**Working method.** Keys, then extremes, then breakdowns, then several separate straight-ahead passes, one body part at
a time: the primary mass first, secondary parts next, flapping bits (hair, cloth, tails) last. Test at every stage.

## 2. The numbers

The book counts at 24 fps. The durable unit is **steps per second**: convert, do not copy frame counts.

| Frames per step | Steps per second | Reads as |
| --- | --- | --- |
| 4 | 6.0 | very fast run |
| 6 | 4.0 | run, or a very fast walk |
| 8 | 3.0 | slow run, "cartoon" walk |
| **12** | **2.0** | brisk, business-like: the *natural* walk |
| 16 | 1.5 | stroll |
| 20 | 1.2 | elderly or tired |
| 24 | 1.0 | slow deliberate step |

For a locomotion blend space this becomes a speed to cadence mapping, not fixed clip lengths: walk about 2 steps per
second, jog 3, run 4, sprint 5 to 6.

**Walk phases** (one step is contact to opposite contact):

| Phase | Position | Fraction of the step |
| --- | --- | --- |
| contact | foot touches, no weight on it yet, legs spread widest | 0 % |
| **down** | leg bent, taking the weight: *this is where weight is felt* | about 25 % |
| passing position | support leg straight, swing leg passing | about 50 % |
| **up** | body at its highest, push-off | about 75 % |
| contact | next step | 100 % |

**Weight phasing.** The pelvis is lowest at the down, a quarter step *after* the contact, and highest at the up, a
quarter step after the passing position. Lowest at the contact and highest at the passing position is a quarter step
early: the walk bounces instead of carrying weight.

**Spacing within the step** (Williams' 12-frame walk): speed *through* the contact, cushion *into* the down, ease out of
the down, speed *through* the passing position, cushion into **and** out of the up. The curve is not a sine wave: the
top is held, the bottom is approached quickly and left slowly, and the contact is the fastest moment of the step.

**Arm phasing.** Arms swing widest when the legs are widest, and slightly after: the swing peaks at the down, with the
hand at the bottom of its arc at the passing position. Arms that hang neutral at the contact and peak at the passing
position are a quarter cycle out.

**Other numbers:**

- Walk: one foot is always on the ground. Run: both feet off for 1 to 3 frames.
- Runs are densely sampled (on ones): there is too much action per unit of time. Arm swing is about half the amplitude
  you would guess.
- Run positions per step: 6 looks best; at 4 (6 steps per second) there is no time to swing the arms, so they stretch
  out in front; 3 is 8 steps per second; 2 (12 steps per second) only works with the two positions close together,
  mostly from the front or back.
- On a fast run, never make the second step an exact mirror of the first. Vary the silhouette (back concave then
  convex, feet twisted differently), or the eye reads one leg going round in a circle.
- Runners lean into a turn like a motorbike.
- An accent or a hold needs **at least 6 frames** to read. Nothing under 4 frames reads at all.
- The impact frame of a hit is not the contact: skip the contact and show the *result*, displaced, with the sound on
  the rebound frame after.
- Sound sync: the visual accent 2 frames ahead of the sound; sharp body and head accents 3 to 4 frames ahead. Never
  late.
- Sneaks: 24 to 32 frames per step slow, 16 fast. A skip is two bounces on one foot.

**Putting life into a walk** (Williams' checklist, paraphrased): lean the body; straight legs on contacts and
push-offs; tilt the shoulders against the hips; swivel the hips; tilt the belt line toward the lower leg; flop the feet
and twist them off parallel; delay the toe leaving the ground to the last instant; tip the head; delay parts so nothing
moves together; counteract the soft mass; break the joints; more vertical for more weight; run the arms on a different
timing from the legs.

## 3. Applying them to game clips

A film shot is non-interactive with a fixed camera; a game plays a graph of blendable loops from a player-controlled
camera, and any clip can be interrupted on any frame. Some of the best devices cost interruptibility (a 3-frame
anticipation is a liability if the player cancels on frame 1; a delayed head is a liability when blending into the
next state), so the library splits in two:

- **Locomotion and idles** (interruptible every frame): no anticipation, short blend-in, overlap only on parts that do
  not affect the pose graph (hair, cloth, fingers).
- **Committed actions** (attacks, dodge, jump takeoff, hurt, defeat): the full kit. Anticipation, invisible
  anticipation, hard accents with rebound, delayed settles. These clips own their frames, so the craft is free.

Rules that carry straight over to the pose functions:

- **Layer the keys.** Posing every bone on the same key grid is the King Kong failure. Offset head, chest and arm keys
  by 1 to 3 frames from the hips.
- **Contact before absorption on every landing.** One pose where the sole touches and the knee has *not* yet bent.
- **Successive arm breaks.** On any arm action the elbow arrives first; the hand and fingers are late.
- **Anticipate every committed action**, including 1 to 3 frame invisible anticipations: attacks, kicks, jump takeoff,
  dashes.
- **Classify every impact.** Strikes and kicks are hard accents: snap out, overshoot past the contact, rebound at once.
  Put the visual accent 3 to 4 frames ahead of the sound.
- **Vary mirrored moves.** Left and right attacks, like left and right steps, should not be exact mirrors.

Rules that need translating:

- **Cycles.** Williams dislikes them; a game cannot avoid them. Make them long instead: two or more strides with varied
  extremes and passing positions before the loop closes, which delays the eye reading the repetition.
- **Author travelling, not in place.** Build a walk travelling across the ground, then make the cycle; derive in-place
  or root-motion variants at export.
- **Dense sampling is not good spacing.** Continuous sampling removes the question of ones and twos, but smooth
  interpolation between sparse poses (a sine-based pose function) is exactly the "mechanical inbetween" the book warns
  against.
- **Separate the characters** by contrast of size, shape, silhouette, colour and movement, a real constraint as the
  enemy roster grows.

What does not transfer: the 2D production craft (exposure sheets, cel levels, pegs, inbetweener drawings, dry-brush
blurs), squash and stretch of volumes and faces (the characters are skinned low-poly meshes without blendshapes or a
facial rig), and lip sync (no dialogue). If dialogue ever comes: move the body somewhere while the character speaks,
and put the head accent 3 to 4 frames ahead of the sound.

Related: Yorimichi's [FOX_HUNTER_ANIMATION.md](../games/yorimichi/docs/FOX_HUNTER_ANIMATION.md).
