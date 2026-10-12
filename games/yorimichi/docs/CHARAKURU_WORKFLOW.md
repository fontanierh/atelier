# Charakuru: heads and bodies made separately

[Charakuru](https://github.com/nanocle/Charakuru) (きゃらくる) is a kit that turns one character illustration into a
VRM avatar with Tripo, an image model, Blender and an AI agent (Codex). Tripo sponsors it. These notes come from its
public docs and its v1.0.3 release (8 October 2026): `AGENTS.md`, the seven Skills, the Blender scripts and the app's
data checks. Nothing from the kit is copied into this repository. They are here for experiments with our own pipeline
([Making a character](../../../docs/CHARACTER_PIPELINE.md), [Tripo characters](TRIPO_CHARACTERS.md)).

**The main idea: the head and the body are two separate Tripo jobs.** Each has its own four views, its own mesh budget
and its own textures. They use the same Tripo model as we do (Smart Mesh P2.0); the difference is how much of every
budget the face gets.

## Why our faces come out badly

Our characters go to Tripo as one full-body T-pose turnaround with an 8,000-face limit
(`tripo_asset.py generate --faces 8000`). In that turnaround the face covers a few percent of each image, and it ends up
with a few hundred faces and a small share of one texture. Eyes, ears and mouths suffer first; the
[face fix](TRIPO_CHARACTERS.md#eyes-light-and-noise-the-fix-almost-every-tripo-character-needs) and Modori's painted
face work around it afterwards. [Modori's README](../assets/characters/modori/README.md#known-limits) also notes
about 1 mm texels behind the ears, from Tripo's UVs.

Charakuru gives the head a square image of its own in every view, up to 25,000 quads and its own 4K textures.

**What they tried and dropped.** Earlier versions split the character three ways: a bald head, the hair and the body
(twelve images), and they kept expression and separate-eye data. Version 1 merged the head and hair into one part
(eight images) and dropped expressions, separate eyes and look-at. The old three-way files still load, but new work is
never converted to them. Generating hair apart from the head, or a bald skull under it, is now explicitly ruled out.

## The workflow, step by step

👤 marks a checkpoint where a person decides. The agent never picks a candidate and stops at every checkpoint. The kit
names the agent (Codex) but not the image model behind Codex's built-in image generation. Every Tripo step is done
by the agent clicking through the Tripo Studio website in the user's signed-in browser, not through an API. Blender
5.2 with the official VRM add-on and Blender MCP does the mesh work; scripts handle anything repetitive, and the
agent judges anything visual by looking.

### 1. Load the illustration

One full-body illustration (PNG, JPEG or WebP, up to 20 MB) showing the hairstyle, outfit and shoes. A character sheet
with a face close-up or a back view helps. Several panels are read for their own roles (a back view for the back);
different expressions or poses are never mixed, and anything not visible is marked as a guess.

### 2. Write a painting brief from finished art

**Tool:** the agent, browsing Pinterest.

- It searches for *finished* character art and close-ups ("VTuber model art close up", "Live2D model illustration face
  closeup", "VTuber full body illustration outfit", "Live2D character art hair closeup"), adding material words such
  as "white jacket" or "dark hair". Japanese, Korean and Chinese queries are suggested too. It steers away from
  "tutorial", "how to draw", "beginner" and "step by step", which return lessons instead of finished work.
- Images are opened and looked at; titles and captions do not count. It picks work where the layered colour, hard and
  soft edges, material differences and quiet areas are readable, and rejects pieces that rely on background effects
  or show only a base colour and one shadow.
- It writes what it sees as place → colour, edge or highlight → how to use it here. For example: a thin warm line on
  the upper eyelid, a deeper rim on the lower lid, wider pale colour across the cheek → join them from the eye to the
  cheek, changing width and strength, in this character's skin tone.
- Character-specific design (eye symbols, freckles, cheek hatching, palettes, motifs) is left out; artist names are
  never used as style words.
- **Only the words go into prompts.** Third-party images are never passed to the image model, and the agent names
  exactly which images a call may use so that recently viewed references do not slip in.

### 3. Draw eight images: head and body, four views each

**Tool:** Codex's image generation.

**Order and inputs**

- **One part, one view, one figure per call.** The front comes first and must be fully finished (face, hair and
  clothes) before the other views. The first call already asks for finished quality; there is no flat draft stage.
- **The other views are edits of the approved front.** Each prompt gives every image a role, for example "Image 1 is
  the approved front: identity, proportions, pose, palette and painting density. Image 2 is a source view, used only
  for depth and design."
- Crops or aspect-preserving zooms of the source are used to *look* at details, never as a substitute for drawing
  them. Redrawing, flipping or warping by code is not allowed.

**Head**

- The face, the ears as they naturally show, and *all* the hair down to the longest tips; head accessories belong to
  the head. Even waist-length hair stays with the head and is never cut at the neck. No neck, shoulders or collar.
- Hair hidden by the removed body is filled in; the hairstyle is otherwise kept. A fringe that covers the face is not
  opened up to show more face.
- The hair hangs still: no wind, the same fall in all four views.
- The pose is corrected: the eyes are level, the face's centre line is vertical, the face is straight on to the
  camera, with no tilt and no looking up or down. Natural asymmetry in the face, hair and accessories is kept, not
  made symmetrical.
- The expression is neutral: lips naturally closed, brows and eyes relaxed, eyes naturally open. The prompt says not
  to keep the illustration's smile or open mouth, and keeps that apart from the painting brief so the brief does not
  bring the smile back.
- If long hair makes the face small, the agent also checks a zoomed-in crop. It never trims hair or changes the head
  proportions to enlarge the face.

**Body**

- Neck down: the neck, clothes, hands, legs, shoes, collars, hoods and clothing accessories. No head, face, hair, held
  objects or floating effects. Clothing that the hair used to hide is completed from the existing design.
- The neck ends bare at the top "so it can insert into the head", with no stand, cap or visible cut.
- A strict T-pose: upper arms level at shoulder height, elbows and wrists straight, legs a natural distance apart
  and not stepped forward or back. The same joint pose in every view; the arms are not lowered because they overlap in
  the side views.

**Left and right**

Every prompt says both which side is visible and which way the face points on screen. Views are never mirrored, so
one-sided details stay on the right side. Side views are a true 90°. Tripo's own Left and Right names are not assumed
to match.

| File | Visible side | Nose, chest and toes point | The character's left-side detail |
|---|---|---|---|
| front | front | at the viewer | screen right |
| left | the character's left | screen left | nearest the viewer |
| right | the character's right | screen right | far side, hidden as it would be |
| back | back | away | screen left |

**Canvas and scale**

- Square, the whole outline with a margin, a real transparent background (never a drawn checkerboard). The same size,
  scale and baseline in all four views of a part.
- Landmarks are read off the approved front and matched in the other views: the top of the head, the eyes, the chin
  and the longest hair tip; the top of the neck, shoulders, wrists, hems and soles.
- The head and body images may use different scales. Hair length is kept relative to the body (shoulders, waist,
  knees). How much of the image a part fills says nothing about its real size.

**Painting**

The aim is a fully painted character illustration seen up close, one standard for face, hair, skin and clothes. A
plain source sets the design, not a ceiling on the finish.

- The prompts never ask for "flat colors", "single shadow tone", "no highlights" or "minimal shading", and never rely
  on "neutral lighting", "VTuber", "rich" or "high detail" alone to describe the finish.
- **Face:** connected colour across the upper eyelids, outer eye corners, lower lid rims, cheeks, ears, nose and mouth,
  varying in width and strength; lashes painted with deep coloured tones and a fine sheen without changing their shape
  or count; light shading on the white of the eye; irises darker at the top, brighter below, with tidy reflections;
  lips with soft modelling and a small gloss. The same skin treatment carries onto the neck and hands. Not a uniform
  pink, dark face shadows or extra sparkles.
- **Hair:** layered colour inside the existing locks, deeper colour at roots and overlaps, a broad soft sheen with a
  few sharper reflections. No new strands, no identical white stripe on every lock; white hair is not flat white and
  black hair is not a black mass.
- **Clothes:** only the materials that exist, each with its own sheen: broad soft modelling on matte cloth or knit,
  flowing reflections on smooth or satin cloth, structured sheen on leather and hard parts, narrow crisp highlights on
  metal and gems. Pale fabrics keep some colour; dark fabrics stay readable. No new folds, seams, embroidery or
  hardware to fake detail.
- **Light:** remove background colour casts, floor shadows, backlight and glow, and shadows cast by removed parts.
  Keep the shading where the hair overlaps the face. Don't copy the front's highlight positions onto the side views;
  highlights follow each surface.

**Checks and fixes**

- Each image is checked separately for the part boundary (no collar in the head, no back hair in the body), direction
  and scale, head pose and expression, the painting of every material, and how the parts match (hair length against
  the body; skin colour across face, neck and hands; equal finish on hair and clothes).
- A fix names the exact place and what is missing ("the lower lid and the skin around it don't connect", "one flat
  colour inside each lock", "cloth and metal have the same sheen"). Shape errors and paint errors are fixed
  separately, never with a vague "more detail". **If two fixes in a row do not help, stop** and report what is left.
- Saved as `head/{front,left,right,back}.png` and `body/{front,left,right,back}.png`, with the real prompt inside each
  PNG's metadata.

👤 A person reviews the eight images and can ask for any one to be redone or swap in their own.

### 4. Make 3D candidates

**Tool:** Tripo Studio, **Smart Mesh P2.0** (the generate page offers 500 to 25,000 quads and 1, 2 or 4 results).

- **Quads, 25,000 faces, 4 candidates**, one job for the head and one for the body (each from its four views). The
  kit's data checks refuse any other setting.
- Missing images, an A-pose or mismatched directions send the work back to step 3; it never falls back to a
  single-image job.
- Use the cube icon (four-view multiview), not the stacked-images icon (batch input of up to 30 images).
- Studio saves its settings automatically, so every value is checked at the start.
- Every candidate is downloaded as FBX with its textures, named so its candidate and source images can be traced.
  If the browser blocks a download, the person saves that file by hand; **nothing is generated again**, since it
  would cost credits.

👤 A person picks one head and one body, comparing them from every side and in wireframe.

### 5. Split into parts

**Tool:** Tripo Studio segmentation, **coarse** setting (the kit names no version); then the agent, by eye.

- The chosen head and body are first triangulated in Blender and exported as **GLB** (Y up), then uploaded again for
  segmentation. The result comes back as FBX and replaces the candidate as the reference mesh; its vertices, face
  order and UVs are never changed again.
- A script splits each mesh into its loose (unconnected) pieces. The agent labels every piece head, hair or body by
  looking at it from the front, side and back, alone and in place, never by its size, position or vertex count.
- At most **7 texture groups** (for example skin, hair, top, waist, legs and shoes), following the design and how much
  texture each part deserves. Every piece is in exactly one group. **Head pieces and body pieces never share a
  group**, so each part keeps its own placement.
- Swinging parts are listed separately as `hair`, `skirt`, `ribbon`, `strap` or `other`; a skirt and a ribbon can share
  one texture group and still be two swing groups. Only hair pieces can swing on the head. "Nothing swings" is
  recorded only after checking.
- If a cut would have to go through joined faces, the agent shows a picture and asks. Its two options: cut it in
  Blender (described as unreliable and expensive in tokens) or regenerate or pick another candidate in Tripo
  (described as more reliable). A mesh edited by hand is registered as a new candidate and the steps from here run
  again.

### 6. Redo the textures

**Tools:** Codex's image generation for reference paintings; Tripo Studio **Smart UV**, then Tripo's **texture**
tool.

1. Each group's pieces are merged into one mesh (without welding them) and exported as FBX, Y up, transforms baked.
   The script checks Smart UV's limits first: 80,000 triangles or 40,000 quads, 150 MB.
2. A script renders a **wireframe front and back of the real mesh** for each group.
3. The agent paints a new front and back picture of *only that group*: "Image 1 is the wire guide (shape and part
   boundaries). Images 2 onward are the approved views (colour, pattern and finish). Keep the exact set of pieces,
   including separate pieces in their places. Remove the wireframe, viewport UI and grey clay shading. Straight-on
   orthographic view, square transparent PNG, full outline, same scale and baseline as the paired view. No floor
   shadows or coloured lighting; no added body parts, accessories or seams." The two pictures are square, 512 to
   8,192 px and normally the same size. A crop, upscale or UV sheet of the turnaround does not count. Colour across
   neighbouring groups (skin against clothes) is checked.
4. Each group is uploaded to Tripo on its own. **Smart UV runs first**; its output is saved before going on, since Smart
   UV erases existing textures. Then Tripo's texture tool repaints it from the two pictures (front and back
   reference mode) at **4K (2K and 8K are offered), with Remove Lighting off, no remesh and no polygon reduction**.
5. Uploads use 0° rotation; the agent checks in Tripo's preview which way the face points and never adds a second 90°.
   Any correction is recorded as Blender XYZ degrees after checking the downloaded file, never copied from Tripo's
   upload dial and never guessed from a symmetrical shape.
6. A script copies the returned UVs and texture back onto the **original mesh**. It matches faces by position (after
   undoing Tripo's move and scale), not by vertex order, allowing split vertices on UV seams. It refuses the result if
   the shape no longer matches within 0.001% of the group's size, a face is missing, changed or duplicated, or the
   group does not have exactly one 4096 × 4096 base-colour image.
7. **Toon materials** (VRM MToon) go on here and stay to the end. Settings: the base texture also drives the shade,
   shade colour = base × 0.64, toony 0.9, shading shift 0, GI 1, no outline. Rotated texture UVs must be baked first,
   and a separate alpha image must be merged into the base colour's alpha. The export refuses any leftover
   non-toon material.

The UVs are only a container for Tripo's repaint. Nothing is painted in UV space by hand or by an image model.
**Each group gets its own 4K sheet**, so the face and skin group alone has a full 4K texture. Because the painted
texture already carries the shading, the toon shade is just a darker copy of the same texture.

### 7. Put the head on the body

**Tool:** sliders in the kit's app.

- The parts arrive at standard sizes: the body 1.45 m tall, the head 0.30 m, both centred. The hair shares the
  head's scale and position.

👤 A person moves and scales the head, hair and body until the neck sits right, from the front and the side (with an
option to move the hair with the head, and undo). An optional total height (1.7 m is only an example) scales the
whole model. The placement is then baked in; changing it later means exporting and rigging again.

### 8. Rig

**Tools:** Tripo Studio auto-rig; weights by a script in Blender 5.2.

1. The placed head and body go to Tripo **without the hair**, with the clothes and swinging parts, as one FBX: meshes
   baked into world space (Y up, metres, no parents), textures embedded, so Tripo has nothing to misread. Whether to
   leave the swinging parts out is still an open question in the kit; clothing is never filled in with a body that
   is not there.
2. Only Tripo's **bone positions** come back, scaled back to the model's own size. Tripo's weights and rigged mesh are
   thrown away and never replace the textured parts.
3. **The final skeleton is the bundled base body's.** Its bones keep their names and hierarchy and are moved so
   every joint that matches Tripo's sits exactly on it (checked to 0.01 mm); unmatched bones follow a scaled copy of
   the base. Hips, chest, head, hands, feet, forearms and shins must match. Mirroring is off so Tripo's asymmetry is
   kept. The joint name table reads Mixamo and VRoid-style (`J_Bip_C_…`) names.
4. **The base body is stretched to fit** that skeleton, then its weights are copied:
   - The torso is fitted top to bottom through the hips, neck and head. The neck is the anchor because rigs split the
     spine differently, and fitting each spine bone pulls the chest and stretches the head. Torso sections may differ
     from the base by 0.5 to 2 times, width and depth corrections by 0.8 to 1.2; anything beyond stops for a look.
   - Limbs are matched by bone direction and length; their thickness follows the overall scale.
   - Each body vertex takes the weights of the **nearest point on the fitted base surface** (blending that triangle's
     corners), keeps its **4 strongest bones**, and renormalises. The report counts vertices more than 5 cm from the
     base, which flags clothes that stand away from the body (and fingers) for a closer look.
5. **The head is 100% on the head bone**, a rigid shell.
6. Swinging parts are pulled out first and pinned to the hips for now.

👤 A person watches a walk cycle from the front and side: shoulders, elbows, knees and neck, and clothes breaking or
clipping. The kit says this check covers bones and skin only; physics are checked in the exported file.

**Fallback: placing joints by hand.** If Tripo's rig does not fit, the person can place 21 body markers (and up to 40
finger markers) on the model instead, and the agent builds the rig from them: joints placed on the original pose,
temporary automatic weights, the arms turned into a T-pose bone by bone (keeping bone lengths), then the mesh and
skeleton both made the new rest pose, shape keys included. Shoulder and underarm fixes must happen before that last
step, never after the squashed shape is baked in. The kit calls this path experimental and slower.

### 9. Swinging parts and export

**Tools:** Blender with Blender MCP and the VRM add-on.

- The hair goes back on, rooted to the head. Only the long hair, fringe, skirt and ribbons swing; the agent picks each
  chain's root, tip and parent bone by looking, fixes the root and fades the weights smoothly to the tip, and checks
  that nothing was weighted to a nearby part on the wrong side.
- VRM 1.0 humanoid bone mapping, swing bones, and colliders on the head, chest, hips and legs. The body's rest pose
  and weights are not changed.
- A scripted test turns the head left and right, leans the body a little and bends the knees, then looks for jitter,
  clipping, roots lifting off and overstretching. The pose is restored afterwards.
- It exports `avatar.vrm` and an editable `avatar.blend` (textures packed), then **loads the VRM again** to check
  that the physics move. Anything it could not check is reported as a remaining issue. The model name, author and
  usage terms are asked for, never guessed.
- No eye bones, look-at or expressions on purpose.

👤 A person checks the result, with any motion file (VRMA) and toon or original lighting.

## How the head meets the body

Nothing is stitched. The join holds because of four choices:

1. **The neck plugs into the head.** The head ends at the chin and the back of the skull; the body keeps the whole
   neck. The top of the neck sits inside the head, so no edge shows. The image prompts forbid a cut face or a cap,
   which Tripo would otherwise close the cut with.
2. **A person places it once** (step 7), and that placement is baked in before rigging.
3. **One skeleton for both** (step 8): the base body's, on Tripo's joint positions.
4. **The weights make it move together.** The rigid head turns about the top of the neck, which follows the base body's
   neck weights and stays hidden inside the shell.

Skin colour across the join is checked by eye only: the head and body are always in different texture groups.

**Where it breaks:** with a rigid head nothing deforms under the chin, so a big turn or tilt can open a gap on a bare
neck. Their anime outfits mostly have collars, which hide it (Modori's collar would too). Nothing measures how deep
the plug sits. Their own motion check only turns the head left and right.

**Ideas for us** (not in the kit):

- Taper the top of the neck and bury it a few centimetres. Check the widest head turns and look-ups in our clips for a
  gap, as we already check clearances on Cairo.
- Instead of a fully rigid head, blend the top 2 to 3 cm of the neck from the neck bone to the head bone.
- Sample the skin under the chin and match the neck's texture to it with a script.
- Keep the head and body as separate sections of one skeletal mesh in Unreal; that also gives the face its own
  material, for a painted face and later expressions.

## Tripo's API

Charakuru uses no API, and its rules forbid guessing private ones. Our client (`atelier.ai.tripo_asset`) already uses
Tripo's v3 API, which accepts uploaded files: that is how we rig a cleaned GLB. No documented Smart UV endpoint turned
up (October 2026). The public Python SDK (VAST-AI-Research/tripo-python-sdk, last updated 30 June 2026) lists
texturing, conversion, segmentation, mesh completion, smart low poly and rigging tasks, all working from a Tripo task
ID. Its only UV options are `export_uv` at generation and `convert_model(pack_uv=True)`, which repacks existing UVs.
The v3 docs site renders only in a browser, so an undocumented route cannot be ruled out. Ask Tripo before building
on Smart UV.

Our own Smart UV uses were by hand in Studio: Modori's body, and one outfit whose 407 overlapping islands became 33
([BODY_SWAP_GUIDE.md](BODY_SWAP_GUIDE.md)).

## What it does not do

- The face is neutral with a fixed gaze: eyes are painted into the texture, so there is no blinking, expression or eye
  movement.
- Its painting guide says the quality bar is a goal, not something verified to come out reliably from any model.
- There are no measurements of results, and as a Tripo-sponsored kit it says nothing about other generators.

## Which model for heads

Charakuru does not show that heads need a different model; the budget is the lever. For context, the
[Top 3D AI Season 11](https://www.top3d.ai/leaderboard/seasons/sep-26) blind vote (26 September to 1 October 2026):

| Arena | Tripo | Meshy | Hunyuan 3D v3.1 |
|---|---|---|---|
| Textured | v3.1: 1,094 (1st) | 7.1: 1,057 (3rd, 196 votes); 7: 1,050 | 1,046 (7th) |
| Geometry | v3.1: 1,146 (1st) | 7: 1,122 (3rd); 7.1: 1,041 (11th, 137 votes) | 1,079 (6th) |
| Low poly | P2.0: 1,098 (1st, 91 votes) | T2: 999 | not in the top five |

The gaps are small and some samples are thin. P2.0 is entered only in low poly. Hunyuan 3D 3.0 and 3.1 are hosted
only; the newest open weights are 2.1. Meshy 7 and 7.1 market image-matched surface detail, so Meshy is the one to
try on heads if P2 at a full head budget is still weak.

## Experiments to try

In order of cost:

1. **A head-only P2 job.** Draw a head-only four-view set for an existing character (Cairo) to the rules in step 3,
   approve it, and run `tripo_asset.py generate --references <head>/references --output <head> --faces 25000`. Compare
   the eyes, ears and mouth with the current head at the same screen size. About 120 credits. Our client asks for
   `texture_quality: detailed` and fixed seeds; the kit's Studio settings have no equivalent to compare.
2. **A blank face.** The same job with the face left blank, then our painted face
   ([face spec](TRIPO_CHARACTERS.md#writing-the-face-spec), Modori's `FACE` table) on its own front-projected UV
   region. This keeps a painted face clean in our low-detail style and is the only route to blinking and expressions.
3. **The join.** Put the new head on the current body with the plug and the weight blend above, and check the widest
   head turns in Cairo's clips.
4. **Meshy on heads.** If 1 is still weak, the same approved head images through Meshy 7.1.
5. **Per-group retexturing** for bodies and clothes, by hand in Studio (segmentation, Smart UV, then a 4K repaint from
   wireframe-guided pictures, copied back with a position-matching script like theirs), until there is an API for it.
6. **The base-body weights.** Their nearest-surface weight copy from a fitted base body, with the neck as the torso
   anchor, is an alternative to Tripo's own skin weights on bodies whose shoulders or chest deform badly.
