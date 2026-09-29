# Tripo P2.0 asset workflow for Yorimichi

> Moved from the prototype repository on 29 September 2026. Paths are translated to this repository where the file moved; paths still starting with `japan/` or `output/imagegen/` refer to the prototype archive (authoring tools, earlier revisions, review images). See [docs/MIGRATION.md](../../../docs/MIGRATION.md).

**19 September update:** the new Smart UV tool has a separate Studio API;
our developer key does not access it, but direct context/generate/apply calls
using the signed-in Chrome session successfully unwrapped Yellow Boy for
0 credits. The token stayed inside the browser. Standalone CLI/session replay
remains untested. Studio's export changes transforms and vertex order and
drops skin/animation; we verified transferring its UVs back onto our intact
53-joint, 25-clip source. This remains a separate UV1 experiment, with packing
and texture baking still needed. See the [character trial and animated
comparison](TRIPO_SMART_UV_CHARACTER_TRIAL.md).
See the [Smart UV investigation](TRIPO_SMART_UV_API_RESEARCH.md) for the working
Studio flow, mesh verification, API findings and texture/rigging caveats.

Researched **12 September 2026**. This is a production proposal informed by official documentation and the current repository. No paid generations, rigging jobs, or import trials were run for the original research. The subsequent completed character/sprint pilot and practical lessons are recorded in the [production handback](WARM_ORIGINAL_PRODUCTION_HANDBACK.md). Settings below are starting points to validate on one character, not measured quality or performance guarantees.

The proposed chain is sound: **Sunburst concepts and turnarounds → Tripo P2.0 geometry and textures → Tripo auto-rigging and skin weights → Astra-assisted Blender cleanup, fitting and rig refinement/integration → H3 Max 480p motion references (Seedance when justified) → authored Blender animation → engine validation.** Astra's rig work builds on Tripo's auto-rigged result. Replacing that rig is a fallback if its quality or compatibility proves inadequate, not a mandatory production step. The main production investment is a stable body/skeleton contract. Once that exists, new clothes and equipment can become reusable assets instead of independent character rebuilds. **Keeping the existing kit is not an assumption: reuse, partial replacement and a full rewrite of the kit remain valid pilot outcomes.**

**Execution requirement:** generation and processing use APIs and local scripts operated by Astra. Each creative stage produces a visible review package and waits for the user's validation before dependent work advances. This includes the concept, every individual reference view, the combined Tripo input set, initial mesh, textures, auto-rig/refinements, clothes/equipment, reference video, animation blockout/polish and engine result. The [API execution and human-review process](ASSET_API_REVIEW_PROCESS.md) specifies the viewing interface, checkpoints, feedback, approvals and revision handling. The narrow Cairo image/model/animation review pipeline is now implemented; a general asset dependency runner remains proposed.

## What the documentation establishes

| Tool | Verified capability | Production interpretation |
| --- | --- | --- |
| Tripo P2.0 Preview | Native quad generation; up to four reference views. Studio advertises 500–25,000 quad faces or 500–50,000 triangle faces. | Promising editable source geometry; joint deformation and silhouette still require inspection. |
| Tripo P2 API | Detailed endpoint documentation identifies `P2-20260801`, including quad and PBR options. | We can explicitly select P2, rather than rely on a product default. |
| Tripo texturing | PBR generation, local texture edits and a Remove Lighting control. | Generate a usable material starting point, then match the game's shading. |
| Tripo rigging | Separate automatic skeleton/skinning stage; FBX and GLB output. | Useful initial rig and weights; compatibility with our skeleton is a separate step. |
| GPT Image 2.5 Sunburst | Image generation and editing; exact model selection and high quality supported. | Use the approved concept as an image input when creating or correcting views. |
| GPT-6 Astra | Coding, image input, tools and computer use. | Operate Blender and author scripts; assess rendered views alongside numeric mesh checks. |
| Seedance 2.5 | Video generation with image/motion references and clay-render guidance. | Design and study motion, then author skeletal animation ourselves. |

Sources: [P2 announcement](https://www.tripo3d.ai/blog/tripo-p2-0-preview), [P-series multiview API](https://developers.tripo3d.ai/en/docs/generation-multiview-to-model/p), [Tripo texturing](https://www.tripo3d.ai/features/ai-texturing), [auto rigging](https://developers.tripo3d.ai/en/docs/animations-rig), [Sunburst](https://developers.openai.com/api/docs/models/gpt-image-2.5-sunburst), [Astra](https://developers.openai.com/api/docs/models/gpt-6-astra), [Seedance 2.5](https://seed.bytedance.com/en/seedance2_5).

P2 is the topology-focused Smart Mesh family. Tripo's HD family has a different emphasis on visual detail; the version numbers are not one interchangeable sequence. The P2 announcement still calls it **Preview** and anticipates further stability improvements. Its production claims are vendor claims, not evidence that a generated shoulder, hand or garment will deform correctly. [Tripo P2 announcement](https://www.tripo3d.ai/blog/tripo-p2-0-preview)

Documentation is uneven: the [model overview](https://developers.tripo3d.ai/en/models) and [quick start](https://developers.tripo3d.ai/en/docs/quick-start) still emphasize P1. Follow the detailed P2 endpoint documentation, record actual request/response data, and verify account access before automating a batch.

## 1. Establish the character contract first

**Recommendation: start with one body size and Tripo's auto-rigged result, validate and refine it, then establish the production contract.** Do not force new characters to fit the old kit before testing whether it meets the new visual and animation goals. Matching bone names alone does not make two rigs interchangeable.

The existing [character kit](../characters/kit/README.md) already assembles parts on a shared skeleton. [build_kit.py](../characters/kit/build_kit.py) constructs that skeleton and adjusts existing parts to its rest positions. [GUIDE_ITEMS.md](../characters/kit/GUIDE_ITEMS.md) supplies body landmarks and accessory bones. These are useful evidence and possible reusable components, not an approved quality baseline.

Evaluate the default path first, and consider alternatives if the pilot exposes problems:

| Candidate | What the pilot should establish |
| --- | --- |
| Refine and standardize the Tripo rig — default | Can we retain its skeleton and useful weights while adding stable controls, equipment attachments and modular clothing? |
| Adapt parts of the existing kit — optional | Do its controls, accessory behavior or integration tools help? Adopting its skeleton would require a demonstrated benefit. |
| Author a replacement rig — fallback | If Tripo's rig cannot meet the requirements with reasonable corrections, does a new skeleton provide better deformation and simpler authoring? |

Use shoulder/hip deformation, hand grips, garment swaps, animation authoring, engine round trips and measured performance to validate the choice. Reuse isolated good components if helpful; an existing codebase is not a reason to preserve a poor body or rig. The modular kit can be rewritten around a refined Tripo skeleton without replacing that skeleton. Freeze the chosen body and skeleton after the pilot, before scaling up the wardrobe.

Record this contract in an asset manifest:

| Contract field | Decision to freeze |
| --- | --- |
| Body | Body ID/version, height, limb lengths, head scale, shoulder/hip widths and standard fitting mesh. |
| Skeleton | ID/version, parents, local rest transforms, bone rolls, deform bones, allowed accessory bones. |
| Coordinates | Explicit units and axes. Meters/Z-up/-Y-forward in Blender is a reasonable starting convention from the current playbook, subject to the chosen pipeline. |
| Pose | One approved reference pose for final binding and all garment fitting. If generation needs a wider pose for visibility, reconcile it before binding. |
| Equipment | Hand grips, back/hip mounts, head attachment and item pivots, each with explicit transforms. |
| Appearance | Palette, material slots, texel density and recolor masks. |
| Runtime | Triangle, material, texture-memory, skin-influence and animation budgets for the target hardware. |

Keep an approved complete body in a simple close-fitting base layer, with enough geometry beneath removable clothes. Make runtime body hiding a reversible outfit rule. A clothed surface generated from a picture may have no usable torso beneath its coat.

For the first prototype, test roughly **5,000–10,000 source quads for the base character**, and try to keep the assembled hero around **20,000–30,000 runtime triangles**. These are proposed experiment budgets, not current project limits. The existing characters are much lighter; profile the dressed character and an NPC group before raising budgets. Count the assembled outfit, hair and equipment together.

## 2. Sunburst: concept approval and consistent views

Use **`gpt-image-2.5-sunburst` with `quality=high` explicitly**, following [AGENTS.md](../../AGENTS.md). The documented snapshot is `gpt-image-2.5-sunburst-2026-09-08`; record the selected model and returned provenance. Do not silently switch to Flare or an older image model. An image tool without a model selector does not establish which variant it used. [Sunburst model documentation](https://developers.openai.com/api/docs/models/gpt-image-2.5-sunburst)

Recommended sequence:

1. Generate a few concept directions using the game's existing visual references. Approve proportions, face, palette, silhouettes and materials.
2. Separate the **body design** from the **assembled outfit design**. Keep outfit art for style and fit, and produce body-only and item-only references for generation.
3. Derive front, back, left and right images through edits/reference-conditioned generation using the approved image. Do not independently redesign each angle from text.
4. Review a four-view contact sheet. Fix disagreements before sending anything to Tripo.
5. Supply four separate image files to the corresponding Tripo view slots. Keep labels, measurement marks and contact-sheet borders outside the actual inputs.

### Official Tripo guidance for reference images

The evidence below separates **P2-specific documentation**, **Tripo's production case study using P2.0**, and **general Tripo guidance**. These recommendations inform a starting preset; they are not a published benchmark proving an optimal configuration.

| Evidence | What Tripo recommends or documents |
| --- | --- |
| [P-series multiview API](https://developers.tripo3d.ai/en/docs/generation-multiview-to-model/p) | Fixed front/left/back/right slots; front plus at least one other view. Same subject and consistent lighting. PNG, JPEG or WebP; at least 256 × 256 is **recommended**, not described as a hard validation minimum. |
| [P2.0 game-character case study](https://www.tripo3d.ai/blog/game-industry-character-workflow) | Defined silhouettes and resolved surface details, without shadows concealing shape. **T-pose when rigging is the priority; A-pose suits armor placement.** Separate components for better control; isolate the head when it merits its own detail budget. Material cues should approach the intended result; PBR-style treatment is a general starting point, adjustable to the art direction. |
| [General image-quality guide](https://www.tripo3d.ai/blog/best-images-for-image-to-3d) | Sharp, centered, uncropped subjects; a simple contrasting background and diffuse illumination. Prefer **1024 × 1024 or higher** when possible. Avoid compression damage, blur, strong reflections and distorted perspective. This quality recommendation is distinct from the API's 256-pixel baseline. |
| [General multiview guide](https://www.tripo3d.ai/blog/multiple-reference-images-3d-generation) | Keep identity, apparent scale, framing and illumination consistent across angles. Use one subject per image and avoid obscuring relevant surfaces. |

Tripo's [general reference guide](https://www.tripo3d.ai/blog/explore/using-reference-images-to-guide-ai-3d-generation) accepts orthographic or mild perspective. Its [image-quality guide](https://www.tripo3d.ai/blog/best-images-for-image-to-3d) also recommends a three-quarter angle for **single-image** reconstruction. That does not change the named cardinal views expected by P2's multiview endpoint: do not place a three-quarter or top view in a side slot.

### Our proposed Sunburst input preset

The following are project choices that operationalize the guidance, to validate on the pilot:

- Generate **four separate square PNGs**, starting at 1024 × 1024, with orthographic-style front, back and true side views. Review original pixels; upscaling alone does not resolve missing detail.
- Use **T-pose for the base body's first rigging trial**, with the same limb and hand positions throughout. Approve a different pose deliberately if fitting or reconstruction tests justify it. In a true side view some limbs naturally overlap; do not change pose or rotate the camera to invent visibility.
- Keep the same canvas, body height and floor baseline, with room around the complete silhouette. Use a plain light-gray background unless another solid color separates the subject better. Keep labels, guides and contact sheets out of submitted files.
- Show the approved stylized materials clearly, without baked dramatic lighting. Design the base body in its simple fitting layer; give removable clothes and held equipment their own input sets.
- Review the front/back hands, feet, armpits and silhouette closely. Resolve contradictory hems, seams and asymmetric features before submission. Use isolated detail references as separate asset work when necessary, not extra images inserted into unrelated P2 slots.

I did not find a P2-specific, quantitatively validated optimum for resolution, camera field of view, subject fill percentage or pose angles, nor a requirement for transparent backgrounds. Record these settings and compare actual reconstructions before standardizing them. We retain **Sunburst via API** for preparing the images; adopting the case study's visual criteria does not require its Studio image tools or chosen image model.

Left/right mean the character's anatomical sides in our filenames. Validate the API view-slot mapping with labeled examples and an asymmetric pilot asset; the review page must show that exact mapping. Do not mirror a left-side image when the right side has different clothing or equipment.

Sunburst supports iterative image edits, but OpenAI documents remaining consistency and composition limitations. A request for orthographic views is a useful constraint, not calibrated geometry. Compare head/body ratio, shoulder/hip/knee heights, garment hems, footwear thickness and asymmetric features across the images. [OpenAI image generation guide](https://developers.openai.com/api/docs/guides/image-generation)

Example reference-edit prompt, adapted per angle:

> Create one full-body BACK reference view of the attached approved Yorimichi character. Preserve the exact identity, proportions, base clothing, palette and materials. Keep the approved T-pose, hand positions, image scale, floor baseline and head height from the front view. Use orthographic-style projection, a plain light-gray background and soft even illumination. Fit the complete silhouette within the image, including fingertips and feet. Preserve the blue patch on the character's anatomical left upper sleeve. Include only this view, without labels, a border, props or a ground shadow.

After the first mesh is approved, render actual orthographic views from Blender. Use these as the fitting references for later clothes: they give Sunburst a much stronger geometric anchor than another invented turnaround.

## 3. Tripo P2.0 generation

### API route — production default

Send `POST https://openapi.tripo3d.ai/v3/generation/multiview-to-model`. Example with placeholder uploaded-file tokens and our proposed starting settings:

```json
{
  "inputs": [
    {"front": "<uploaded-front-token>"},
    {"back": "<uploaded-back-token>"},
    {"left": "<uploaded-left-token>"},
    {"right": "<uploaded-right-token>"}
  ],
  "model": "P2-20260801",
  "quad": true,
  "face_limit": 5000,
  "texture": true,
  "pbr": true,
  "export_uv": true
}
```

Use named views; positional order is **front, left, back, right**. Front plus another view is required. For geometry-only iterations set **both** `texture=false` and `pbr=false`: PBR forces texturing on. Leave `export_orientation` unset until final conversion; Tripo warns early changes can silently misorient downstream results. The API lists a 48-face minimum versus Studio's advertised 500; follow the selected route's limits. [P-series multiview API](https://developers.tripo3d.ai/en/docs/generation-multiview-to-model/p)

Each asynchronous step returns a task ID. Save it before polling; persist successful outputs locally immediately. The quick start says output URLs expire after five minutes. Handle failure/cancellation and use bounded retries; a lost HTTP response should not automatically trigger another paid generation. [Tripo API introduction](https://developers.tripo3d.ai/en/docs/introduction), [download guidance](https://developers.tripo3d.ai/en/docs/quick-start)

The official [Tripo CLI](https://developers.tripo3d.ai/en/docs/cli) offers browser login and `tripo doctor`, and can be useful for agent-operated work. Before choosing it over direct API calls, verify that its installed version exposes the exact P2 settings. Browser login is preferable to copying credentials into chat. No CLI or plugin installation is required to use this document.

Use the first result as an evaluation candidate. Present the downloaded model in our review viewer and Blender, with front, rear, both sides and three-quarter views in untextured and textured modes. Obtain visual validation before dependent production stages.

### Studio — optional inspection aid

P2 also appears in **Tripo Studio → 3D Workspace → Smart Topology Mesh / Smart Mesh → P2.0 Preview**. The announcement says Studio multiview requires a subscription. This is optional product context; the production workflow must not depend on manually submitting or downloading jobs there. [P2 Studio instructions](https://www.tripo3d.ai/blog/tripo-p2-0-preview)

### Preserve the editable source

Keep the untouched Tripo output separately from the working `.blend` and runtime exports. **GLB is a runtime/interchange artifact, not a native-quad archive:** glTF export triangulates quads and may split vertices at UV or shading boundaries. Obtain a quad-preserving FBX from the original Tripo task and inspect it in Blender before declaring the source archived. [Blender glTF documentation](https://docs.blender.org/manual/en/4.3/addons/import_export/scene_gltf2.html)

Tripo's conversion endpoint supports `quad=true`, forces FBX in that mode and defaults to 10,000 faces if no face limit is supplied. Treat this as a potentially topology-changing operation. Test whether the selected route preserves P2's native mesh; do not assume converting an already triangulated GLB recovers its original edge flow. Avoid automatic pivot recentering for garments already aligned to the body. [Tripo conversion API](https://developers.tripo3d.ai/en/docs/models-convert)

## 4. Blender cleanup and your review loop

Astra will use Blender Python for repeatable inspection and editing, and open the **actual Blender UI** with the working file for your review. The model's documented image input and computer-use support make this a tool-assisted workflow; they do not establish perfect 3D understanding or automatic production-quality repair. [Astra documentation](https://developers.openai.com/api/docs/models/gpt-6-astra)

For each candidate:

1. Import and save a versioned working `.blend`. Preserve raw meshes, UVs, textures and any supplied rig.
2. Inspect dimensions, disconnected components, degenerate faces, normals, unintended intersections, UVs and mesh density. Distinguish intentional garment openings from accidental holes.
3. Prepare front/back/side cameras, a turntable, neutral clay shading, textured shading and a wireframe view. Open Blender with the character framed and the Outliner organized by body, clothing and equipment.
4. You point out artifacts. Record the object, side, camera and pose/frame so a report such as “the elbow spike” is reproducible. Capture a before view.
5. Make the smallest appropriate correction and show the same view afterward. Check nearby geometry and deformation, not just the marked pixel.
6. Save the accepted revision, cleanup script where practical, and a short change log. Preserve manual UI edits in the source file so a rebuild cannot erase them.

Repair decisions:

| Observation | Likely next action |
| --- | --- |
| Floating fragment, duplicate faces or stray spike | Local mesh cleanup; preserve nearby UVs and weights. |
| Wrong silhouette visible from several angles | Correct geometry, or regenerate early if the mismatch is widespread. |
| Painted shadow, seam or color spill | Texture/material repair. |
| Elbow collapse only when bent | Inspect skin weights and edge flow before changing the rest shape. |
| Coat fused to torso or legs | Separate/rebuild the garment and recover a usable underlying body. |
| Distorted hand or facial structure | Local remodeling/retopology; use a proven reusable hand/face component when that is more reliable. |

Finalize substantial geometry and topology changes before final skinning and animation. After later topology edits, explicitly recheck or transfer UVs, weights and any shape keys. A good-looking rest pose is only the first review.

## 5. Textures and the game's material system

Tripo Studio documents global texturing, Magic Brush local edits and **Remove Lighting**. These inform the desired result: assets should relight under the game's sun and interiors, with intentional painted shading preserved only as an art-direction choice. Inspect base color, normal and roughness maps independently. Studio's local-edit and lighting controls are not established API features by this research; use the programmatic correction routes and capability checks in the [review-process specification](ASSET_API_REVIEW_PROCESS.md#programmatic-execution-routes). [Tripo texturing](https://www.tripo3d.ai/features/ai-texturing)

Our proposed treatment is restrained, stylized materials matched to Yorimichi's palette. Begin with 1K or 2K working textures according to screen coverage, then profile. Avoid giving every wearable its own large material set by default. Define shared texel density and reusable materials; add recolor masks for cloth/leather/metal instead of baking every color variation into another atlas.

Check UV stretching and seams, mip padding, normal-map convention and tangents, correct color-space interpretation, and accidental shiny cloth or metallic skin. If topology changes invalidate the maps, reproject/bake from the retained source onto the final mesh. Inspect the same material under several in-game lighting conditions.

**Repository integration work is required if these paths are reused.** [import_cape_boy.py](../unreal/JapanProto/Scripts/import_cape_boy.py) currently sets `import_materials=False` and `import_textures=False`, then asserts one palette material. The kit builder also rewrites appearance into recolorable vertex colors. Adapt or replace these paths to preserve UVs and textures, create the intended Unreal materials and support texture-aware recoloring. Importing a PBR FBX through the existing code unchanged will not satisfy this workflow. The new asset format and quality goals should determine whether extending or rewriting is simpler.

Unreal's FBX documentation describes limited automatic material/texture translation. Build and verify our material graph explicitly rather than assuming every PBR map will wire itself correctly. [Epic FBX skeletal mesh pipeline](https://dev.epicgames.com/documentation/en-us/unreal-engine/fbx-skeletal-mesh-pipeline-in-unreal-engine)

## 6. Rigging: use Tripo to bootstrap, then standardize

Tripo's [P2 production case study](https://www.tripo3d.ai/blog/game-industry-character-workflow) recommends custom rigging for production characters, describing rigging/animation as below industry standards in that workflow. Our chosen trial still starts with Tripo auto-rigging, followed by Astra's Blender refinement. The pilot must establish whether that refinement is sufficient; substantial rig work or replacement remains possible.

Run Tripo's rig-compatibility check before its rigging stage. The rigging API offers native Tripo or Mixamo naming through `spec`, with FBX/GLB outputs. Its parameter table recommends `v1.0-20240301` for bipeds and lists `v2.5-20260210` for non-humanoid creatures; one example mixes the latter with a biped. Use the documented type recommendation and verify the result rather than copying that example blindly. These are **rigging model versions**, separate from the P2 geometry model. [Auto Rig API](https://developers.tripo3d.ai/en/docs/animations-rig)

**Tripo provides the initial skeleton and skin weights; Astra's Blender work is on top of that.** Inspect and correct deformation, fit and bind separate clothes, add animation controls and equipment attachments, and integrate the result into the game. Keep useful generated bones and weights. Consider replacing the rig only if the pilot demonstrates that refinement is insufficient. If major mesh defects prevent auto-rigging, repair them first and rerun the Tripo stage before final refinement.

The final character must use the approved skeleton contract. Mapping animation between skeletons is **retargeting**; copying skin weights between meshes is **weight transfer**. They solve different problems. Renaming a Mixamo rig does not reproduce another skeleton's joint positions, rolls, bind transforms or accessory behavior.

Keep an animator-friendly Blender control rig with IK targets and constraints, and bake to the stable deform skeleton for export. Check root/pelvis separation, feet, hands, finger articulation and accessory pivots. Eye movement, blinks, facial expressions, twist corrections and cloth controls may need explicit authoring; automatic body rigging does not establish that these are present.

Minimum deformation pass: arms overhead, arms forward, deep squat, seated pose, knee lift, elbow bend, wrist rotation, hand grip and torso twist. Check both sides and the back with the full outfit. Fix the body and weights before multiplying garments.

## 7. Separately designed clothes, weapons and items

### Clothes: generated designs fitted to a real body

Use Sunburst to design each garment **on renders of the approved body**, in the approved fitting pose. Make a second set showing only the garment with consistent volume. This preserves the design context while avoiding unwanted mannequin geometry in the Tripo input.

A recommended garment pipeline:

1. Generate a separate P2 garment candidate, or extract it from an assembled candidate when that gives better shape.
2. Fit it in Blender against the actual body. Match neck, shoulder, waist and cuff landmarks. Use cage deformation/sculpting and selective shrinkwrap with clearance; preserve loose volumes instead of shrinking every surface tightly to skin.
3. Clean interior debris; author hems, thickness and openings where visible. Avoid unnecessary hidden geometry.
4. Transfer weights from the approved body or a similar approved garment to the **same skeleton**. Blender Data Transfer supports vertex-group transfer between differing meshes; nearest-face interpolation is a useful starting point, followed by regional correction. [Blender Data Transfer](https://docs.blender.org/manual/en/4.3/modeling/modifiers/modify/data_transfer.html)
5. Inspect armpits, crotch, cuffs and inner thighs. Nearest-surface transfer can accidentally borrow influence from the opposite limb or torso. Skirts, capes and loose sleeves usually need purpose-built weights and secondary bones.
6. Add outfit metadata: body version, slot/layer, hidden body regions, incompatible items, attachment/deform bones and material masks.
7. Run the deformation pass and representative gameplay clips with several garment combinations.

Tripo Segmentation v2 documents semantic splitting, editable parts and mesh completion. It is useful assistance when extracting a coat or accessory, but it does not establish a reusable wardrobe contract. Check P2 compatibility, preserved textures, garment interiors and the completed body on a real trial. [Tripo segmentation](https://www.tripo3d.ai/features/ai-model-segmentation)

A garment fitted to one body size does not automatically fit another. Add new size variants through controlled mesh adaptation and pose checks. Animation retargeting alone will not fix clothing fit.

### Rigid equipment: sockets and grip transforms

Generate weapons, tools, bags and handheld props independently at a defined size. A rigid item usually needs no skinning: its pivot and socket transform determine attachment. Unreal sockets are bone-relative attachment points. [Epic skeletal mesh sockets](https://dev.epicgames.com/documentation/unreal-engine/skeletal-mesh-sockets-in-unreal-engine)

Define the main grip, optional second-hand grip, stowed transform, collision and gameplay interaction points. Constrain the hands to shared grip targets during animation; avoid independently animating a hand and weapon and hoping they stay aligned. Test drawing, holding, stowing and dropping. A bending bag strap, articulated tool or moving mechanism needs its own deforming or rigid-part setup.

Example proposed item metadata—not an existing implemented schema:

```yaml
id: raincoat_01
body: yorimichi_body_v1
skeleton: approved_humanoid_v1
slot: outer
layers: [torso, arms]
hides_body_regions: [torso_under_coat, upper_arms]
conflicts_with: [cape]
binding: skinned
```

For Unreal modular characters, **Leader Pose** is a useful starting point when all pieces follow the same bones. It requires matching skeleton structure, does not give child pieces independent animation/physics, and does not eliminate their draw calls. Use **Copy Pose** with additional animation for pieces needing independent secondary behavior; investigate mesh merging for fixed outfits or crowds after profiling. [Epic modular character guidance](https://dev.epicgames.com/documentation/unreal-engine/working-with-modular-characters-in-unreal-engine)

### Non-character assets

Use the same concept → references → P2 → Blender QA chain. Static props need scale, pivots, collision, LODs and material checks. Doors, wheels and mechanisms need separately usable moving parts. Modular buildings need exact snap dimensions and seams that we author and measure in Blender. Foliage needs an explicit plan for alpha/overdraw and wind. Use separate creature skeleton families for animals; do not force everything onto the humanoid kit.

## 8. Animation references: H3 Max first

**September 13 decision:** prefer H3 Max at 480p through Vercel for new motion references, using the [H3 workflow](H3_ANIMATION_REFERENCE_WORKFLOW.md). It is cheaper and sufficient for gross poses/timing, but requires precise phase/contact/direction guidance and actual-video inspection. The two double-jump trials each cost $0.15 and still missed a requested mechanic. Keep skeletal authoring and validation in Blender. Existing Seedance references retain their provenance; the documented Seedance capabilities below remain an alternative when justified.

### Seedance 2.5 capabilities and historical route

ByteDance's July 31 announcement confirms 30-second generation, multimodal references, motion guidance and clay-render reference control. These are useful for our workflow, particularly feeding a simple Blender motion blockout into Seedance for performance ideas. The documentation describes video outputs; it does not establish skeletal animation or FBX/BVH motion export. [ByteDance Seedance 2.5 announcement](https://seed.bytedance.com/en/blog/one-take-creation-flexible-referencing-introducing-seedance-2-5)

Use renders of the **final cleaned character**, so the motion reference reflects its proportions. Our recommended clips are short, typically 4–6 seconds, with one action and a fixed camera. Keep the full body and ground contact visible, with even lighting, readable clothes, no cuts and little motion blur. Generate a side or three-quarter view first; a second angle can clarify intent but is not a synchronized calibrated camera.

The alternative Vercel AI Gateway route (`bytedance/seedance-2.5`) and alternative BytePlus model ID are recorded in the [execution specification](ASSET_API_REVIEW_PROCESS.md#programmatic-execution-routes). Submit and retrieve reference videos programmatically, then present them for review before authoring dependent animation.

Assign each reference a role: character image for identity/proportions, motion reference for timing, optional clay blockout for contacts and trajectory. Use the chosen provider's actual input syntax; service-specific asset labels and API IDs must be verified at implementation time.

Example motion brief:

> Use the supplied character render for appearance and body proportions. Show a single standing jump on flat ground in a fixed side view. Keep the full body and floor visible throughout. Over four seconds: hold neutral briefly, crouch in anticipation, push off with both feet, reach an apex, land on both feet, absorb the landing, and settle to neutral. Keep the camera still, with consistent lighting, no cuts and clear feet. Emphasize readable weight shift and balance. Do not add camera effects or loose equipment.

Reject references with implausible joints, changing limb lengths, sliding planted feet, teleporting props or hidden contact events. We should borrow useful posing and timing, not reproduce a generated error.

### Extract frames with timestamps

Save the original video and prompt, inspect frame rate/duration, then extract a lightweight contact-sheet sequence and selected original frames around important contacts. Example commands for a local downloaded reference:

```sh
ffprobe -v error -select_streams v:0 \
  -show_entries stream=avg_frame_rate,r_frame_rate,time_base,duration \
  -of json reference.mp4

mkdir -p reference_frames
ffmpeg -i reference.mp4 -vf "fps=6" reference_frames/frame_%04d.png
```

The 6 fps images are analysis samples, not the animation's final frame rate. Preserve original frame presentation timestamps when identifying takeoff, impact or foot plants; do not infer timing solely from a numbered screenshot. FFmpeg's frame-rate filter samples/drops/duplicates frames, while ffprobe can report individual frame timestamps. [FFmpeg filters](https://ffmpeg.org/ffmpeg-filters.html#fps), [ffprobe](https://ffmpeg.org/ffprobe.html)

### Astra authors the animation in Blender

1. Write a motion specification: duration, start/end pose, contact times, root displacement, speed, looping rules and gameplay events.
2. Block key poses on the control rig: anticipation, contact, passing pose, apex, impact and recovery as relevant.
3. Set pelvis/root motion and solve limb contacts with IK. Use FK where it gives better arcs. Constrain equipment grips to shared targets.
4. Refine timing, spacing, balance and arcs in all views. A single video cannot uniquely determine hidden limbs or motion toward the camera; resolve those intentionally from anatomy and gameplay needs.
5. Add restrained secondary motion after the main body works. Simulate or animate cloth-like pieces, then bake the exportable result.
6. Bake clips to the deform skeleton, inspect interpolation and loop seams, export and compare in engine.

The existing [CapeBoy importer](../unreal/JapanProto/Scripts/import_cape_boy.py) imports animation at 60 Hz and disables root motion. Treat this as current integration context, not a mandatory design for the replacement pipeline. Decide controller-driven versus authored root motion during the pilot, and match foot speed and stride accordingly. For jumps, choose who owns the world trajectory: avoid adding authored root translation on top of controller displacement.

Your animation review should include Blender timeline scrubbing and a live game test at the actual camera distance. Check contact/sliding, outfit clipping, equipment alignment, transition blends and interruption behavior. A pleasing video alone is not evidence of a working gameplay animation.

## 9. Delivery, acceptance and provenance

Each asset should retain:

```text
asset_id/
  brief.md
  manifest.json              # models, settings, task IDs, source hashes, body/rig versions
  references/                # approved concept and separate views
  raw/                       # original Tripo files and maps
  blender/                   # editable source and repeatable cleanup/build scripts
  textures/                  # runtime maps and recolor masks
  animation/reference/       # original H3/Seedance videos, frames and timestamps
  animation/specs/           # contacts, poses, events and motion decisions
  exports/                   # mesh FBX, clip FBXs, preview GLB
  review/                    # versioned manifests, previews, feedback, user decisions and reports
```

Use version control for scripts, manifests and reviews; store large source binaries with an appropriate durable asset-storage/LFS policy. Do not rely on temporary provider URLs. Preserve historical model provenance. The repository's [build-stamp validation](../characters/cape_boy/pipeline.py) is one possible reusable mechanism; extend it or implement an equivalent for generated source meshes, textures and skeleton contracts, so stale or partial exports cannot silently enter the game.

An asset is accepted when:

- Its silhouette and materials match the approved references at game-camera distance.
- The source mesh is editable, with no accidental debris, broken normals or unintended holes.
- The dressed character passes extreme poses and representative gameplay clips.
- Garments swap without changing the body skeleton or breaking approved combinations.
- Textures, UVs, weights, scale, orientation and clip timing survive a clean export/import round trip.
- Animation plays correctly with the controller, including contacts, transitions and equipment events.
- Measured triangle counts, material sections, texture memory, skinning and frame cost meet the project budget.
- Source assets, generation provenance and the applicable commercial-use entitlement are recorded.

For Unreal, retain separate mesh and animation exports as our existing pipeline does, and import clips onto the approved skeleton without updating its reference pose as a side effect. Epic documents an FBX 2020.2 pipeline; verify our actual Blender/Tripo export against the installed engine rather than assuming a format preset is sufficient. [Epic FBX pipeline](https://dev.epicgames.com/documentation/en-us/unreal-engine/fbx-skeletal-mesh-pipeline-in-unreal-engine)

## 10. Access, cost and the first experiment

Tripo's current Studio pricing labels free outputs public/non-commercial and paid production tiers private/commercial. Use an appropriately licensed production route and retain its terms/plan at generation time. Studio offers and API billing are distinct surfaces; verify entitlements and per-operation costs for the selected account rather than deriving a P2 budget from advertised “models per month.” [Studio pricing](https://www.tripo3d.ai/pricing), [Tripo terms](https://www.tripo3d.ai/terms)

Track **cost per accepted asset**, including reference revisions, rejected meshes, textures, rigging, conversion, Blender cleanup and QA. No credible estimate of cleanup time can be made from this documentation alone. Generate a small pilot before committing to volume.

The proposed pilot is one character, two interchangeable upper garments, one rigid handheld item, one simple static prop, and three short clips: idle, walk and jump. Use these to answer the remaining practical questions:

| Experiment | Evidence needed |
| --- | --- |
| P2 four-view reconstruction | Consistent identity and silhouette at a useful mesh budget. |
| Quad source export | Native source topology reaches Blender without an unnoticed remesh. |
| P2 → texturing → rigging | Material/UV/geometry integrity survives the selected processing chain. |
| Rig refinement and kit selection | Validate Tripo's auto-rig plus Blender corrections first; decide which kit components to reuse or rewrite, and justify any replacement skeleton. |
| Separate garment generation | Both garments fit and deform across the same body and clips. |
| Material integration | PBR maps and recolor behavior work in Unreal and the browser kit. |
| Video-guided authoring | Readable authored motion with correct contacts and controller behavior. |
| Runtime profile | The fully dressed hero and a representative NPC group fit the frame/memory budget. |

The most uncertain labor is likely to be hands/faces, loose clothing, deformation and material integration. If those remain manageable in the pilot, this workflow can become the game's asset pipeline with reusable bodies, garments, equipment and animation libraries.


## 11. Completed garment pilot: generation versus tailoring and simulation

The [parallel clothing experiment](../../output/imagegen/yorimichi-yellow-boy-2026-09-12/outfit-comparison-r01/README.md) now supplies concrete evidence for the separate-garment question. It compares a tailored shirt, a P2-generated layered shirt, and a bounded torso/hem cloth simulation on the same body and motion. The comparison includes source files, exact-camera stills, gray geometry views, exported animation checks and phone playback.

For P2, the actual fitted shirt envelope was rendered in the approved horizontal bind pose. Sunburst/high combined that dimensional guide with the approved original art into one isolated garment image. A single P2 reconstruction with quad output, a 12,000-face target, detailed PBR and UV export produced 22,675 triangles after triangulation. It cost 120 credits. Generated openings, thickness and folds were retained while a local cage fit and weight transfer attached it to the existing skeleton. A generated garment is a useful shape/material starting point; it still needs pose-specific fitting and deformation review.

The experiment demonstrates why outer and inner cloth walls should move together during fitting, and why exported animation timing must be checked after FBX import. The raw generated shirt, reference prompt and generation settings remain intact. The single-image result does not establish that single-view input always outperforms a coherent multiview set.

The simulation branch supplies actual solver data and rejected full-shirt trials. Its final scope is yellow torso/hem physics with rigged sleeves and substantial pins, converted to a periodic morph bake for browser review. It is neither unconstrained full-garment cloth nor a runtime simulation implementation. Compare the actual deformation and production cost before adding physics to every garment; the final report records which of these particular candidates worked best.
