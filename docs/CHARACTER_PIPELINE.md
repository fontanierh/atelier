# Making a character

Each step is a prompt or a script an agent runs, followed by a human look (often with a second AI reviewer). Cairo,
Yorimichi's default player, is the example.

**1. Concepts.** A text prompt to *GPT Image 2.5 Sunburst* asks for four directions (for Cairo: "a youthful boy for a
warm Japanese exploration game, around four head heights tall, dark softly rectangular eyes without visible
whites..."). One gets picked.

<img src="media/character/01-concepts.jpg" alt="Four concept images of the boy; the first is picked">

**2. A turnaround for 3D.** The picked concept is redrawn in a neutral T-pose and a grey fitting suit, then from the
back and both sides, each view an edit of the approved front so the face and proportions hold.

<img src="media/character/02-turnaround.jpg" alt="Front, left, back and right views in a T-pose">

**3. A 3D model.** The four views go to [Tripo](https://www.tripo3d.ai) (multiview to 3D, model P2) for a textured
mesh, about two minutes and 120 credits. Blender scripts then clean up details such as the brows, mouth and collar.

<table><tr>
<td width="70%"><img src="media/character/03-mesh.jpg" alt="Tripo's raw model and the cleaned model"></td>
<td width="30%"><img src="media/character/03-turntable.gif" alt="The model turning"></td>
</tr></table>

```sh
uv run python platform/studio/atelier/ai/tripo_asset.py generate --references <revision>/references --output <revision> --faces 8000
blender -b --python games/yorimichi/assets/characters/tools/review_tripo_model.py -- --input model.glb --output review
```

**4. A skeleton with fingers.** Tripo's auto-rig gives a 23-bone body (25 credits); a Blender script adds 30 finger
bones and reweights the hands, so the character can grip a sword or a skateboard. Every rig follows the same
[humanoid bone contract](../platform/conventions/rigs/humanoid.toml), which is what lets animation, foot planting and
gameplay code work for any character.

<table><tr>
<td width="70%"><img src="media/character/04-rig.jpg" alt="Rest pose and three hand poses"></td>
<td width="30%"><img src="media/character/04-fingers.gif" alt="The fingers closing and opening"></td>
</tr></table>

```sh
uv run python platform/studio/atelier/ai/tripo_asset.py rig --source <cleanup>.glb --output <revision>
blender -b --python games/yorimichi/assets/characters/tools/add_tripo_fingers.py
```

**5. Outfits.** An outfit changes without changing the rig: the image model draws the outfit and dresses a headless
mannequin rendered from the rigged body, Tripo builds the clothes, and a script fits them onto the skeleton
([body swap guide](../games/yorimichi/docs/BODY_SWAP_GUIDE.md)). The image model also paints the bare body green in the
same four views, so the script knows exactly which skin to keep (V necks, bare arms and legs), and coats and hakama
hang as a skirt rather than splitting into trouser legs. One command runs it all, from an outfit spec to a review
sheet, and stops before anything paid until someone has looked at the images. The same rules handle skate, hoodie,
keikogi with hakama, basketball jersey and long coat outfits
([the three fixes](../games/yorimichi/docs/BODY_SWAP_GUIDE.md#13-the-three-fixes)).

<img src="media/character/05-outfit.jpg" alt="Outfit concept, the dressed mannequin, the final character">

**6. Motion from video.** AI video models act a move out with the character: MiniMax H3 Max at 480p by default (about
$0.15 for the dodge roll), [Seedance](https://seed.bytedance.com) when its quality justifies the cost (about $1.40 a
take), both through the Vercel AI Gateway. The video is a reference, not the animation: an agent reads it frame by
frame and writes the clip in Blender pose by pose, with foot planting and clipping checks, so it loops, lands and
reads well in the game ([H3 workflow](H3_ANIMATION_REFERENCE_WORKFLOW.md)).

<table><tr>
<td width="62%"><img src="media/character/06-motion.jpg" alt="Seedance sprint frames above, the authored Blender sprint below"></td>
<td width="38%"><img src="media/character/06-h3-roll.gif" alt="An H3 Max reference video of Cairo doing a forward shoulder roll"></td>
</tr></table>

```sh
node --env-file=.env platform/studio/node/h3_max_reference.mjs submit --resolution 480p --out <revision>
node --env-file=.env platform/studio/node/seedance_vercel.mjs submit --out <revision>
uv run python platform/studio/atelier/review/video_reference.py <revision>        # timestamped frame sheets to author from
```

**7. Motion capture, retargeted.** For the sword, a great-sword combo from Adobe's
[Mixamo](https://www.mixamo.com/) library is moved onto Cairo's own skeleton by a Blender script. Bones are matched by
anatomy (not by axes), travel is scaled to his height, palms are aligned separately, and the second hand is re-solved
onto the grip every frame. A correction layer lifts the overhead cuts clear of his head, checked at 240 samples a
second. The combo is then cut into strikes, a charge and a parry; the capture's full-turn spin is taken out with the
feet re-planted, the strikes are sped up, and each one records where it lands so the game can aim it.

<table><tr>
<td width="34%"><img src="media/character/06-mixamo-combo.gif" alt="Cairo performing the retargeted Mixamo great-sword combo"></td>
<td width="66%"><img src="media/character/06-despun.jpg" alt="A game strike cut from the combo: guard, raise, cut, contact, follow-through"></td>
</tr></table>

```sh
blender -b --python games/yorimichi/assets/characters/tools/cairo_mixamo_test.py -- --source combo.fbx --out <r01>
blender -b --python games/yorimichi/assets/characters/tools/cairo_mixamo_clearance.py -- --source <r01>/... --out <r02>
blender -b --python games/yorimichi/assets/characters/tools/cairo_sword_combat_r02.py   # strikes: de-spun, faster, aimed
```

The settings, the maths and the pitfalls are in the [Mixamo guide](../games/yorimichi/docs/MIXAMO_WORKFLOW.md).

**8. A reviewed clip library.** Every clip is rendered from several cameras and checked before it ships. Clips are
named by [role](../platform/conventions/clip-roles.toml) (`Run`, `DashAir`, `SwordParry`...), so game code asks for a
role, never for a file.

<img src="media/character/07-clip-review.jpg" alt="The third sword strike from the front, the side and three-quarter, eight frames each">

**9. Into the game.** `atelier build` exports the character's body, donor clips and textures, then imports its
merged moves, sword and paraglider into Unreal; scripted QA runs check it in motion.

```sh
atelier build yorimichi unreal.cairo_adventure
atelier play yorimichi
# In another terminal, against the running game:
atelier live py "ONLY=['sword']; TAKE='combat_review'"
atelier live py - < games/yorimichi/scenarios/adventure_moves.py
```

The tools for each step and their options are in
[games/yorimichi/assets/characters/tools](../games/yorimichi/assets/characters/tools/README.md) and
[games/yorimichi/docs](../games/yorimichi/docs). The fox hunter goes through the same steps (`fox_hunter_pipeline.py`).

## Fixing details with human input

Generating a character and retargeting its animation does not settle every detail. The fingers of Modori, Yorimichi's
playable rival, could close around a sword handle, yet the hand sat differently on it from one clip to another. An AI agent built a bespoke
[browser grip poser](../games/yorimichi/docs/GRIPS.md) to collect the correction that was hard to describe in words.
It shows his actual rigged hand against the actual sword or paraglider. A person drags fingertips, moves and turns
the wrist, and checks the contact colours: green touches the handle; red goes through it.

The saved pose supplies concrete targets: where each hand belongs on the prop, its orientation and the bend of
each finger joint. The agent used those targets to build the runtime solver. The sword follows the carrying
hand at the calibrated offset; two-bone arm IK keeps the other sword hand and both glider hands on their handles,
while the fingers take their saved rotations. The constraints blend in with the animation and are checked across
swings, guards and glider banks.

That is a useful part of the process: AI makes the first version, a person spots a visual problem, the agent builds
a small tool to capture their intent, and code applies that correction consistently. To fix another bad grip,
edit the saved pose, export it and restart the game; the solver can use the new targets without recompiling.
The [grip guide](../games/yorimichi/docs/GRIPS.md#fix-a-grip-on-modori) gives the commands and checks. Modori's four
calibrated sword and paraglider grips are committed, so a normal build already uses them.
