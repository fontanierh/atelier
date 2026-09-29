# Richard Williams, *The Animator's Survival Kit* — distilled, and what of it applies to Yorimichi

> Moved from the prototype repository on 29 September 2026. Paths are translated to this repository where the file moved; paths still starting with `japan/` or `output/imagegen/` refer to the prototype archive (authoring tools, earlier revisions, review images). See [docs/MIGRATION.md](../../../docs/MIGRATION.md).

Read 2026-09-14, cover to cover. The book is a 1940s-Hollywood craft manual written by
someone who spent thirteen years extracting it from Ken Harris, Milt Kahl, Art Babbitt
and Grim Natwick. It is about drawn 2D film animation, but roughly half of it is really
about *how bodies move*, which is medium-independent.

This doc is the distillation plus an honest audit of how much transfers to what we are
doing (procedurally authored clips on skinned rigs, played back by a state machine in UE).

---

## 1. The load-bearing ideas

Everything else in the book hangs off these.

**Timing vs spacing.** Timing is *when* things hit — the beats. Spacing is *how the
in-between positions cluster* between those beats. Timing is the easy half and most
people have a natural feel for it; spacing is the rare skill and has to be learnt.
Two moves with identical timing and different spacing read as completely different
actions. For us this is the difference between "the clip is 0.8 s long" (timing,
which we always get right) and "the pelvis spends most of that 0.8 s near the bottom"
(spacing, which we mostly leave to whatever curve we happened to write).

**The breakdown is the secret.** Given two extremes, the single most consequential
choice is where you put the middle position. Don't go straight from A to B — go
somewhere else interesting en route. Williams says he made a living off this one device.
It is the cheapest source of character in a move.

**Weight is the up and down of the masses.** Not smooth level travel. Traced live-action
walks float, and nobody quite knows why, so you *exaggerate* the vertical. You feel the
weight at the **down** position, where the leg is bent and absorbing — not at the contact.
A walk with no vertical on the head reads as weightless (his example: he clocked a walk
as effeminate from fifty yards out of focus, purely from the absence of head bob).

**Contact before deformation.** Put a frame where the thing *just touches* before it
squashes/absorbs. Ball, frog, jumping figure, fist on a table: one extra position at the
moment of touch, then the compression. Free "change", and it is what separates a landing
that lands from one that melts.

**Flexibility from broken joints, not rubber.** "Breaking" a joint means bending it,
including past what anatomy allows, and doing it *successively* — elbow leads, forearm
follows, wrist follows, fingers arrive last. This gives curved, limber motion out of
rigid bones, which is exactly our situation. You do not need squash-and-stretch to look
alive.

**Overlapping action.** Nothing starts or stops at the same time. Most big body actions
originate in the hips; the head is usually delayed; cloth, hair and soft mass arrive last
and counter the body (body up → belly/hair down). The failure mode he names is the
"King Kong effect": everything moving the same amount at the same time.

**Anticipation.** Before you go one way, first go the other. Bigger anticipation = more
latent force. The anticipation is usually slower than the action it precedes. There are
also *invisible* anticipations: 1–3 frames in the opposite direction, too fast to see,
which is where "snap" comes from.

**Hard accent vs soft accent.** A hard accent (hammer on anvil, karate kick, a hard point)
**bounces back** after the hit. A soft accent (a conductor's baton, a friendly gesture)
**keeps going** through it. Getting this distinction right is what he says gave him the
most trouble in his whole career.

**Never use normal timing.** Go slightly too fast, then slightly too slow, and keep
switching. Contrast is the engine — slow against fast, straight against curve, concave
back against convex back.

**The mind is the pilot.** There is always a beat of thinking time before the body acts.
Change of expression shows thought — and you must place the change *where the audience
can see it*, never buried inside a fast move.

**Believability, not realism.** The goal is never to copy life. It is to make an invented
move convincing. Art Babbitt animated Goofy with his feet on backwards and nobody noticed.

**Working method** (this is the part he says is 50% of Milt Kahl's excellence):
keys → extremes → breakdowns → *then several separate straight-ahead passes, one body
part at a time*, primary thing first, secondary next, and flapping bits (hair, cloth,
tails) last. Test at every stage.

---

## 2. The numbers

All at 24 fps, which is how the book counts. The durable unit is **steps per second** —
convert, don't copy frame counts.

| Frames/step | Steps/sec | Reads as |
| --- | --- | --- |
| 4 | 6.0 | very fast run |
| 6 | 4.0 | run, or a very fast walk |
| 8 | 3.0 | slow run / "cartoon" walk |
| **12** | **2.0** | brisk, business-like — the *natural* walk |
| 16 | 1.5 | stroll |
| 20 | 1.2 | elderly or tired |
| 24 | 1.0 | slow deliberate step |

Milt Kahl timed real people downtown with a stopwatch and found they were on 12 frames
"right on the nose", and used that as his reference point for everything else.

**Walk phase structure** (one step = contact to opposite contact):

| Phase | Position | Fraction of the step |
| --- | --- | --- |
| contact | foot touches, no weight on it yet, legs spread widest | 0 % |
| **down** | leg bent, taking the weight — *this is where weight is felt* | ~25 % |
| passing position | support leg straight, swing leg passing | ~50 % |
| **up** | body at its highest, push-off | ~75 % |
| contact | next step | 100 % |

**Spacing within that** (his formula for a 12-frame walk, positions 1/4/7/10/13):
speed *through* the contact → cushion *into* the down → ease out of the down → speed
*through* the passing position → cushion into **and** out of the high. So the curve is
not a sine wave: the top is held, the bottom is approached quickly and left slowly, and
the contact is the fastest-moving moment of the whole step.

**Other numbers worth keeping:**

- Walk: one foot is always on the ground. Run: both feet off for 1–3 frames.
- Runs are always on ones (i.e. densely sampled), because there is too much action per
  unit time. Arm swing is roughly half the amplitude you think.
- Run "drawing counts": 6-position (best-looking, Babbitt's preference), 4-position
  (6 steps/sec — so fast there is no time to swing the arms, so you stretch them out in
  front instead), 3-position (8 steps/sec), 2-position (12 steps/sec — only works if you
  put the two positions *close together* so the eye jumps the gap, and mostly only from
  front or back view).
- On a fast run, never make the second step an exact mirror of the first. Vary the
  silhouette — back concave then convex, feet twisted differently — or the eye reads one
  leg going round in a circle.
- Runners lean into a turn like a motorbike.
- An accent or a hold needs **≥6 frames** to read (Tex Avery got away with 5). Nothing
  under 4 frames reads at all.
- The impact frame of a hit is not the contact — you skip contact and show the *result*,
  displaced, with the sound on the rebound frame after.
- Sound sync: visual accent 2 frames ahead of the sound is the rule of thumb; sharp body
  and head accents go 3–4 frames ahead. Never late.
- Sneaks: 24–32 frames/step slow, 16 fast. A skip is two bounces on one foot.

**Williams' own checklist for putting life into a walk** (paraphrased): lean the body;
straight legs on contacts and push-offs; tilt shoulders against hips; swivel the hips;
tilt the belt line toward the lower leg; flop the feet and twist them off parallel; delay
the toe leaving the ground to the last instant; tip the head; delay parts so nothing moves
together; counteract the soft mass; break the joints; more vertical for weight; run the
arms on a different timing from the legs.

---

## 3. How much of this applies to us

### Directly applicable — close to 1:1

These map onto `warm_clips.py` / `fox_hunter_animate.py` with no translation:

- **The keys → extremes → breakdowns → layered passes order.** This is already roughly
  how the fox hunter clips are written (`keys_from([...])` with named poses). What is
  missing is the *layering*: we pose every bone on the same key grid, which is precisely
  the King Kong failure. Offsetting head/chest/arm keys by 1–3 frames from the hips is
  nearly free in a procedural system and is the single highest-yield change available.
- **Weight = vertical of the pelvis, phased correctly** (see §4 — we have this wrong).
- **Contact before absorption** on every landing: `LandSoft`, dive-roll entry, jump land.
  One extra pose where the sole touches and the knee has *not* yet bent.
- **Successive breaking of joints — elbow leads, fingers last.** This is the same terrain
  as the fox-hunter lesson about the lateral elbow hinge and separate forearm roll, and it
  gives a concrete rule our arm solver does not yet encode: on any arm action, the elbow
  arrives first and the hand and fingers are late.
- **Anticipation, including 1–3 frame invisible ones**, on every committed action: claw
  attacks, kick, jump takeoff, dash. Trivial to prepend procedurally.
- **Hard vs soft accent.** This is a combat-feel rule, not a theory rule. Claw and kick
  impacts are hard accents: snap out, then *bounce back*. And the hit frame should be
  displacement-past-contact with the sound on the rebound — which dovetails exactly with
  hit-stop and with the SFX work in `SOUND_RESEARCH.md`.
- **Vary the silhouette between mirrored steps and mirrored attacks.** Our left/right claw
  attacks are mirrors of each other; per the book they should not be.
- **"Spend it on the eyes."** Relevant the moment the characters carry any performance.

### Applicable, but needs translating for a game

- **Cycles.** Williams hates them and says so repeatedly ("why does the same wave keep
  lapping on the island?"). We cannot avoid them. But his mitigation is directly usable:
  make the cycle *long* — two or more strides with varied extremes and varied passing
  positions, then hook back — which delays the eye reading it as a loop. For an MMO
  brawler where you watch your own character run for minutes, a 2-stride run cycle with
  alternating passing positions is cheap and is exactly what he would prescribe.
- **Don't author in place.** He explicitly says not to build a walk as a cycle with the
  feet sliding backwards — author it travelling across the page, then make the cycle
  afterwards. Our pipeline should author travelling in Blender and derive the in-place /
  root-motion variants at export, not pose in place.
- **Ones vs twos** is dead as a question (we sample continuously), but the point underneath
  survives: his complaint about "dumb mechanical inbetweens" is a complaint about *smooth
  interpolation between sparse poses*, which is precisely what a parametric sine-based
  pose function produces. Dense sampling is not the same as good spacing.
- **The frame tables** become a speed → steps-per-second mapping for the locomotion blend
  space, not fixed clip lengths. Walk ≈ 2 steps/s, jog ≈ 3, run ≈ 4, sprint ≈ 5–6.

### Does not apply

- All the 2D production craft: X-sheets, cel levels, top vs bottom pegs, numbering
  systems, inbetweeners, dry-brush blurs, the elongated "long-headed" inbetween, 2-frame
  dissolves. Historical interest only.
- Squash and stretch of volumes, and the whole chapter on stretching the face. We are on
  skinned low-poly meshes with no blendshapes and no facial rig; "keep the same amount of
  meat" is not a lever we have.
- The entire dialogue/lip-sync chapter — we have no dialogue. If we ever do, keep two
  things: progress the body somewhere while the character speaks (he calls this *the*
  secret of lip sync), and put the head accent 3–4 frames ahead of the sound.
- Most of the directing chapter is 1980s studio politics. Two bits survive: write the
  brief on one page (we already do — `BRIEF.md`, `PLAN.md`), and **separate the
  characters** by contrast of size, shape, silhouette, colour and voice — which is a real
  constraint on the enemy roster as it grows past the fox hunter.

### Rough proportions

The mechanical core — timing/spacing, walks, runs, flexibility, weight, anticipation,
takes and accents, roughly pages 35–300 — is close to fully usable, and a fair amount of
it is what our four fox-hunter revisions rediscovered the expensive way. Maybe a quarter
of the book (2D production, lip sync, drawn squash-and-stretch) does not transfer at all.
The rest — acting, directing, working method — is useful as posture rather than formula.

### The one real tension

Williams is optimising a single non-interactive shot with a fixed camera. We are
optimising a graph of blendable loops watched from a player-controlled camera, where any
clip can be interrupted on any frame. Several of his best devices cost us
interruptibility: a 3-frame anticipation is a liability if the player cancels on frame 1,
and a beautifully delayed head is a liability when blending into the next state.

The resolution is to split the library:

- **Locomotion and idles** (interruptible every frame): no anticipation, short blend-in,
  overlap only on parts that do not affect the pose graph — hair, cloth, fingers.
- **Committed actions** (attacks, dodge, jump takeoff, hurt, defeat): apply the full kit —
  anticipation, invisible anticipation, hard accents with rebound, delayed settles. These
  already own their frames, so the craft is free.

---

## 4. Where our current library departs from the book

Two concrete things I found reading `warm_clips.py` against the walk chapter. Both are
worth a visual check before changing anything, but the reasoning is mechanical.

**(a) The pelvis bob is a quarter-step early.**
`walk_pose` uses `bob = -.012 * cos(2a)`, so the pelvis is at its *lowest exactly at the
contact* (phase 0 and 0.5) and at its *highest exactly at the passing position*. The book
is explicit that the weight goes down *just after* the contact and up *just after* the
passing position — in his 12-frame chart, both extrema sit about 25 % of a step later than
we have them. Delaying the bob by a quarter of a step is a one-line change and is the
difference between a walk that has weight and one that merely bounces.

While in there: the cosine also gives symmetric cushioning at top and bottom, where the
book asks for the high to be cushioned on *both* sides and the contact to be the
fastest-moving instant of the step.

**(b) The arm swing looks a quarter-cycle out of phase with the legs.**
`walk_pose` sets `swing = 27 * sin(a)`, which is zero at phase 0 and 0.5 — i.e. the arms
hang neutral at exactly the moment the legs are at their widest spread, and reach maximum
swing at the passing position where the feet are together. The classic pairing is the
opposite: arms widest when the legs are widest. (Williams adds a refinement — the swing is
actually widest at the *down*, slightly after the contact, with the hand at the bottom of
its arc during the passing position.) Worth confirming against a rendered clip before
touching it, since `rig.arm(swing=…)` is forward-positive from a hanging neutral and I
have not watched the result, but the phase relationship reads as inverted.

---

## 5. What I would do next, in order

1. Confirm (a) and (b) above against rendered walk sheets; fix the pelvis phase, then the
   arm phase.
2. Add an explicit contact / down / passing / up phase model to the gait config, with the
   0 / 25 / 50 / 75 % proportions and the asymmetric cushioning, instead of sinusoids.
3. Add a per-part key offset (1–3 frames) between hips → chest → head → arms across the
   whole library. Biggest aliveness-per-line-of-code in the project.
4. Insert a just-touching contact pose before the absorption on every landing clip.
5. Go through the fox hunter's attack clips and classify each impact hard vs soft, then
   make the hard ones rebound and move the visual accent 3–4 frames ahead of where the
   SFX will land.
6. Lengthen the run cycle to two strides with varied passing positions.

Related: [`FOX_HUNTER_ANIMATION.md`](FOX_HUNTER_ANIMATION.md),
[`CLAUDE_WARM_ORIGINAL_ANIMATIONS.md`](CLAUDE_WARM_ORIGINAL_ANIMATIONS.md),
[`SOUND_RESEARCH.md`](SOUND_RESEARCH.md).
