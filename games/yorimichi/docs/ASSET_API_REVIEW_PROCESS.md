# API execution and human review for Yorimichi assets

> Moved from the prototype repository on 29 September 2026. Paths are translated to this repository where the file moved; paths still starting with `japan/` or `output/imagegen/` refer to the prototype archive (authoring tools, earlier revisions, review images). See [docs/MIGRATION.md](../../../docs/MIGRATION.md).

Process specification, 12 September 2026. Complements the [Tripo P2 production guide](TRIPO_P2_ASSET_WORKFLOW.md). A narrow Warm Original pilot is now implemented; the general runner and asset dependency system remain proposed.

**Current checkpoint, 13 September:** the user positively reviewed the authored sprint and selected the tailored r04 outfit after its waist/arm-clearance refinement. The subsequent r05 elbow correction has independent visual review and is ready for user inspection; it is the current handoff baseline. The root `.env` contains the OpenAI, Vercel H3 Max/Seedance and Tripo credentials. The [Claude animation handoff](CLAUDE_WARM_ORIGINAL_ANIMATIONS.md) is the current execution brief: remaining legacy motions, double jump and two forward dashes; no skateboarding, cloth simulation or separate Jog. The pilot/checkpoint paragraphs below preserve the chronology and do not override this latest state. The general reusable runner and engine integration remain separate work.

**Pilot update, 13 September:** reviewed concepts, base body, multiviews and P2 reconstruction have progressed through approved Blender cleanup, Tripo auto-rigging and locally authored finger rigging. The current [body-and-finger review](../../output/imagegen/yorimichi-yellow-boy-2026-09-12/tripo-rig-r02/review.html) provides movement selection, scrubbing, slow playback, skeleton display, closeups and a reel; the matching native rig is open in Blender. The user has requested the first sprint motion reference using the current character. The original auto-rig had 23 bones and merged materials; transfer back to the approved native mesh preserved the five materials before adding 30 finger bones. Clothes, facial controls, body IK and engine animation validation are still pending.

**Sprint checkpoint:** the user switched to Vercel AI Gateway after the BytePlus activation problems. Its live catalog includes `bytedance/seedance-2.5`. The initial Vercel request returned HTTP 402 (minimum $10 balance for video); after the user funded the account, [revision 04](../../output/imagegen/yorimichi-yellow-boy-2026-09-12/sprint-reference-r04/README.md) completed from the actual character renders: 6.04 seconds, 24 fps, 1112 × 834, with no audio. The original video, timestamped overview and stride sheets are available in the phone preview. Playback, quarter speed and exact one-frame seeking were verified through Tailscale; the user selected the reference for Blender sprint authoring. The [Vercel adapter](../tools/seedance_vercel.mjs) saves a ledger before the paid request, retains accepted operation handles for resume/download, and refuses duplicate submission. The iPhone review puts media and playback controls first, with collapsible secondary controls. The [authored sprint](../../output/imagegen/yorimichi-yellow-boy-2026-09-12/sprint-animation-r01/README.md) is now ready for review: a 40-frame, 60 fps in-place loop matched to eight video poses, with preserved body/finger rig, native/GLB validation and synchronized phone comparison. The user subsequently reviewed the sprint with “It is really good” and authorized autonomous clothing production, explicitly waiving intermediate approvals until the finished outfit review. Engine integration remains pending. See the [complete production record and lessons](WARM_ORIGINAL_PRODUCTION_HANDBACK.md).

**Wardrobe checkpoint:** the user authorized autonomous clothing production without intermediate approvals. The [first four-piece outfit](../../output/imagegen/yorimichi-yellow-boy-2026-09-12/outfit-r01/README.md) is ready for finished-product review: separate sweatshirt, shorts, socks and shoes, baked fabric/suede atlases, the same 53-bone bind skeleton, reversible coverage, individual GLBs and dressed sprint checks. This fitting trial used local Blender construction from the approved concept/body, with no additional paid generation. The phone preview has equip switches and a pinned model view. The old kit and game importer remain unchanged.

After the user authorized acceptance of BytePlus's displayed agreements, those agreements were accepted in Dia. ModelArk's authenticated model catalog confirms the exact Seedance 2.5 ID; a second request now returns `ModelNotOpen`, requiring console activation. This is an account activation issue, not a missing credential or an unavailable model version. No cross-service cloud grants were made. BytePlus also provides an [official Ark CLI](https://docs.byteplus.com/en/docs/modelark/2536875) with `models activate`; version 1.0.27 is installed locally. Its account SSO sign-in succeeded, but activating Seedance 2.5 was rejected because available balance and eligible coupons did not cover the activation reserve. The backend did not disclose the reserve amount. The current model parameter catalog also marks `seed` unsupported, so future requests omit it and set the task type explicitly to `reference`. Prefer this supported control API over browser automation for future activation.

**Astra operates the pipeline through APIs and local scripts. The user reviews the actual result at every creative stage and decides whether it can become an input to the next stage.** Each stage produces a complete, inspectable candidate before requesting validation. Uploads, polling, downloads, conversions and preview generation belong to that stage's execution.

Tripo provides the initial skeleton and skin weights. Astra refines that result in Blender, including clothes, animation controls and equipment attachments. The existing character kit remains optional; a new kit can be built around the refined Tripo rig.

## The recurring loop

1. **Produce:** Astra runs the stage using approved inputs and explicit model/settings selection.
2. **Check:** Astra inspects the actual output, runs applicable technical checks and fixes obvious execution failures. A successful API response is not a visual acceptance decision.
3. **Present:** Astra opens a review page at the exact asset/stage/revision, displays representative media in the task, and opens Blender or the game when the checkpoint calls for it.
4. **Review:** the user inspects, requests changes or approves the named revision. Feedback can be ordinary conversation, a selected image region, a saved 3D view or a timestamped annotation.
5. **Revise:** Astra addresses feedback, creates a new revision and presents a matched before/after comparison.
6. **Advance:** only the approved revision becomes the selected input to dependent work.

Silence, elapsed time and an automated quality score never count as approval. One explicit approval is enough for the named stage/revision; avoid asking again for its internal operations. The user can deliberately approve a bundle or waive a checkpoint, and that scope must be recorded. Independent work on other already-approved assets can continue while one candidate awaits review.

## What the user sees at each checkpoint

Apply the relevant rows separately to each character, garment, weapon or prop. Non-character assets skip irrelevant rig/animation stages explicitly.

| Checkpoint | Astra prepares and opens | The user's decision |
| --- | --- | --- |
| Brief and production constraints | Short brief with intended role, art references, proportions, equipment list and proposed runtime budget. | Confirm the design target and scope. |
| Initial concept | Full-resolution Sunburst candidates with stable labels, zoom and a comparison against the brief's references. | Select a design or request changes. |
| Front reference | Actual front image alongside the approved concept, at full resolution. | Approve identity, silhouette, pose and framing. |
| Back reference | Actual back image beside the front and concept, with matched scale. | Approve back design and asymmetry. |
| Left reference | Actual left-side image beside approved views. | Approve profile, depth and limb separation. |
| Right reference | Actual right-side image beside approved views; do not substitute a mirror for an asymmetric design. | Approve the other profile and details. |
| Complete Tripo input set | Four-view sheet plus access to each original file; visibly label the exact mapping to Tripo's view slots. | Approve the consistency of the assembled input set. |
| Initial Tripo mesh | Interactive orbit/zoom, fixed front/back/side views, clay and textured modes, wireframe and a turntable. Open the imported raw result in Blender too. | Accept the reconstruction as a base, identify defects or request regeneration. |
| Mesh cleanup | Same views before/after, close-ups of reported defects and the editable Blender file. | Validate each correction and the overall shape. |
| Textures/materials | Textured model under neutral and representative game lighting, material/map inspection and comparison with the concept. | Approve palette, surface detail, seams and material response. |
| Tripo auto-rig | Original auto-rigged model in Blender with skeleton visible, rest pose and an automatically produced deformation test reel. | Identify failures and validate the rig as a refinement starting point. |
| Refined rig | Blender control/deform rig, matched before/after poses and tests of hands, feet and attachment points. | Approve the body/skeleton contract for clothes and animation. |
| Each separate garment/item | Repeat concept and applicable reference/mesh/texture reviews, then show the item alone and on the approved body. | Approve design, scale and fit. |
| Outfit and equipment integration | Outfit toggles, body isolation, extreme poses, clipping views and grip/stowed-item tests. | Approve the usable combinations and attachments. |
| Animation brief | Action, timing beats, contacts, start/end pose, looping and controller/root-motion intent. | Confirm the motion to develop. |
| Seedance reference video | Playable original video, speed controls, frame stepping, timestamps and contact-sheet/keyframe views. | Select the reference and identify motion details to follow or disregard. |
| Blender animation blockout | Scrubbable 3D key poses beside the reference, with foot/hand contacts and trajectory visible; open Blender at the relevant action. | Approve posing, timing, weight shift and contacts before polish. |
| Polished animation | Interactive clip playback, frame stepping, looping, multiple views, outfit variants and before/after comparison. | Approve motion, secondary movement and equipment alignment. |
| Engine validation | Actual imported asset in the playable game plus a reproducible capture, game-camera framing, transitions and runtime measurements. | Accept it for game integration or request corrections. |

All four side images can be generated in one execution batch, but each remains independently reviewable and revisable. The input-set checkpoint verifies that individually good views still describe the same object. If one P2 job returns geometry and textures together, present both review tabs in the same session and record both decisions. We need checkpoints for meaningful outputs, not an artificial API call for every row.

At the reference checkpoints, apply the [official Tripo guidance and our proposed input preset](TRIPO_P2_ASSET_WORKFLOW.md#official-tripo-guidance-for-reference-images). Show resolution/format and the selected pose alongside the images. Check the complete silhouette, lighting, anatomical asymmetry and consistency of proportions, framing and materials. The first body trial uses T-pose; a pose change creates a revised input set. Automated file checks supplement the user's visual decision, and must not claim to measure P2 reconstruction quality before a model exists.

The normal sequence reviews the initial mesh/materials before spending effort on rig integration. Small Blender repairs can precede Tripo auto-rigging when needed for rig compatibility. Keep the original generation and original auto-rig as separate immutable stages.

## One review interface, with native Blender and game inspection

Build a small local review application that reads versioned asset manifests. Open it in the Codex browser panel at the current checkpoint; show representative images/videos inline as well. Each review must remain accessible by a durable local route after task restarts. A directory path or a provider's expiring download link is not a sufficient handoff.

The interface should expose four simple areas: **Current result**, **Compare**, **Feedback** and **History**. Keep the asset name, stage and revision visible. The primary actions are **Approve this revision** and **Request changes**. Technical reports can live in an expandable area; the artwork and review controls should dominate the page.

Required viewing behavior:

- **Images:** show the exact generated files with zoom, pan and 1:1 inspection. Compare the same view across revisions and offer a four-view layout. Store labels/annotations separately from the image bytes submitted to Tripo.
- **3D:** orbit, pan, zoom, reset to standard cameras, isolate body/clothes/items, and switch clay/textured/wireframe/skeleton modes. Retain camera position and lighting when switching revisions. Include a game-distance view so close-up detail does not dominate acceptance.
- **Native mesh review:** automatically open the matching `.blend` at mesh, cleanup and rig checkpoints. Frame the subject, select the relevant object, expose the Outliner and prepare useful workspaces. Preserve any unsaved user edits; use a separate review file/session when necessary. GLB wireframe is only a triangulated preview; inspect native quad topology and weights in Blender.
- **Motion:** play/pause, loop, scrub, single-frame step and change speed. Show clip name and time. Compare rendered/reference video and 3D animation on an explicit timeline; allow marked events to align clips with different durations instead of pretending their frame numbers match.
- **Engine:** Astra launches the relevant scene/build and selects the test character/outfit. Retain a recorded replay or capture when immediate interactive access is unavailable, and record which kind of review actually happened.

Use neutral, fixed review lighting and matching cameras for comparisons. Attractive thumbnails supplement the actual mesh/video; they do not replace it. If interactive preview loading fails, provide a turntable and standard renders plus Blender access, clearly identify the failure and keep the affected interactive check incomplete.

For phone review, publish the candidate through the [persistent private Tailscale review service](ASSET_REVIEW_TAILSCALE.md). Its stable URL opens the selected checkpoint, with the same model, controls, renders and video. Refresh the asset manifest when adding new review files, verify the actual HTTPS route and video seeking, and keep provider secrets and private job responses outside the served manifest.

The current [character builder](../characters/kit/web/index.html) and [item preview script](../characters/kit/preview.py) are possible sources of reusable viewing code. This review tool must accept arbitrary generated assets and skeletons without requiring the old kit's body, palette or part names.

## Feedback and approval records

Every feedback item names the asset, stage and revision. It can additionally contain an image region, object/material name, clip and timestamp, saved camera, or selected mesh location. Store a screenshot with 3D feedback so it remains understandable if topology changes. Mesh selections tied to old vertex indices must not silently move onto unrelated geometry after a rebuild.

Ordinary feedback is sufficient: “Back r03: shorten the coat hem” or “Jump r02 at 1.4 seconds: the left boot enters the ground.” Astra translates this into an actionable entry, repairs it and returns to the same view. Resolve ambiguity from the visible selection/context where possible; ask a short clarification only when the intended change cannot be determined.

Record user approval from the review UI or an explicit message tied to a single displayed revision. When several candidates are visible, name the selected one before recording approval. Never manufacture a user decision from Astra's own evaluation.

Each revision retains:

| Record | Contents |
| --- | --- |
| Identity | Asset, stage, revision and parent revision. |
| Inputs | Exact approved upstream revisions and source-file hashes. |
| Execution | Provider/model, settings, prompt, task IDs, timestamps and measured usage when available. |
| Outputs | Original files, derived previews, hashes and source-to-preview mapping. |
| Checks | Automated results and Astra's visual findings. |
| Feedback | User comments, locations/timestamps and linked corrections. |
| Decision | Pending/changes requested/approved, exact revision and user message or UI event supporting it. |

Distinguish **provider job completion**, **technical checks passed** and **human approval** in storage and in the UI. An asset can have all files downloaded and still be awaiting review.

Revisions never overwrite approved files. A new concept or changed reference marks its dependent work out of date on the current production branch; historical approvals remain attached to their original artifacts. Rebuild and re-review affected descendants. Independent branches remain usable. For example, a coat texture change need not invalidate the body's skeleton; a changed body rest pose affects garment binding and animation validation.

## Preferred motion-reference route

As of September 13, the user prefers **H3 Max at 480p through Vercel AI Gateway** for new animation references because it is cheaper. Follow the [complete H3 workflow](H3_ANIMATION_REFERENCE_WORKFLOW.md) for exact prompt guidance, hosted inputs, `.env`, resumable jobs and phone review. Specify timing, contacts, airborne impulses and rotation direction/count precisely, then verify the actual video; the double-jump trial shows that even explicit prompts can produce the wrong mechanics. Preserve approved Seedance footage and use Seedance when its capabilities or quality justify the expense.

## Programmatic execution routes

Production operations use provider APIs and scriptable local applications. Vendor websites are optional inspection aids. Initial account setup/authentication may require the user; routine generation and file handling are Astra's responsibility.

| Stage | Programmatic route |
| --- | --- |
| Concept and per-side references | OpenAI Image API generations/edits, with explicit `gpt-image-2.5-sunburst` and `quality=high`. |
| P2 reconstruction | Tripo v3 multiview generation using `P2-20260801`, followed by task-status retrieval and immediate artifact download. |
| Texture/segmentation/conversion | Tripo processing APIs where supported; Blender scripts and image editing APIs for corrections. Validate each feature's API availability and P2 compatibility. |
| Initial rig | Tripo rig-check and auto-rig APIs. |
| Mesh cleanup, fitting, rig refinement, previews and animation | Blender Python API with command-line execution; open the resulting file in the native UI for review. |
| Motion references | Prefer Vercel `minimax/minimax-h3-max` at 480p via `h3_max_reference.mjs`; Seedance `bytedance/seedance-2.5` remains an alternative. Both use official Gateway asynchronous start/status. |
| Frame extraction | Local FFmpeg/ffprobe. |
| Engine import and tests | Unreal's scriptable import/build/test paths; launch the actual game for visual validation. |

API sources: [OpenAI image generation](https://developers.openai.com/api/docs/guides/image-generation), [Tripo endpoint overview](https://developers.tripo3d.ai/en/docs/introduction), [P2 multiview](https://developers.tripo3d.ai/en/docs/generation-multiview-to-model/p), [auto-rig](https://developers.tripo3d.ai/en/docs/animations-rig).

**Alternative Seedance route (successful historical pilot):** [Vercel's official Seedance 2.5 documentation](https://vercel.com/ai-gateway/models/seedance-2.5) lists `bytedance/seedance-2.5`, image references tagged with explicit media types and `[Image 1]` / `[Image 2]` prompt labels. Inputs are URLs; do not expose the private review service to serve them. Keep upload/signed URLs in private metadata. [Asynchronous generation](https://vercel.com/docs/ai-gateway/modalities/video-generation) requires AI SDK 7.0.50+ and Gateway 4.0.44+; the pilot uses Gateway 4.0.80. Check the exact catalog capabilities, use one video per candidate, preserve the operation before polling, and download the original before its provider URL expires. The supplied key works. The live API requires a minimum $10 balance before video generation; after funding, the pilot generated and downloaded a reference successfully.

**Seedance API candidate verified in official documentation:** BytePlus LAS lists `dreamina-seedance-2-5-260628` for its enhanced video-generation API, with submission at `POST /api/v1/contents/generations/tasks` and task retrieval by ID. Its documented Singapore host is `https://operator.las.ap-southeast-1.bytepluses.com`; choose the account's actual region. This establishes a programmatic route, not that our account already has access. Verify authentication, entitlement and the exact request schema before the first paid call. [BytePlus video-generation API](https://docs.byteplus.com/en/docs/Byteplus_LAS/video_gen_enhanced)

**Do not equate Tripo Studio features with documented API parameters.** The inspected texture endpoint supports reference-guided retexturing, but does not document a Remove Lighting flag or Magic Brush interface. Those Studio features must not become mandatory manual steps. Use API-supported regeneration or scripted/local corrections, and verify how closely they satisfy the same visual goal. Tripo recommends resupplying reference images for texture jobs. [Tripo texture API](https://developers.tripo3d.ai/en/docs/models-texture)

## Runner and review-service contract

Use a persistent job ledger and an asset dependency graph. Submit jobs with immutable input snapshots; save the returned provider ID immediately and resume polling after interruptions. Use idempotency where the provider supports it; otherwise reconcile uncertain submissions before retrying a paid request. Download originals promptly, then generate previews from the downloaded files.

The local review service should serve only the project's review artifacts and record decisions on the exact revision shown. API credentials stay in the backend environment/key store and never enter browser bundles, manifests or logs. The browser's Approve action must persist a real user event; merely loading a page cannot advance the pipeline. Prevent stale tabs from approving a newer revision than the one displayed.

Suggested internal operations are `run_stage`, `get_stage_status`, `build_review`, `open_review`, `record_feedback`, `record_user_decision` and `resume_asset`. These are interface requirements, **not commands or tools that already exist**. The runner only schedules a dependent stage when its selected inputs are approved and its required checks have passed.

When a review is ready, Astra presents the result, states what changed and what needs validation, and waits at that dependency boundary. Persisting the pending state is required; unattended wakeups or notifications require a separately configured task/automation. Approval resumes from the recorded checkpoint instead of regenerating accepted work.

## First implementation milestone

Before building a large asset library, implement a narrow complete loop: **brief → Sunburst concept → reviewed individual views/input set → P2 mesh → visual review → Tripo auto-rig → Blender refinement/review → one motion reference → one authored animation → engine review**. Include one garment to test fitting and feedback in context.

Start with a local manifest-driven image/3D/video viewer and chat-based feedback/approval records. Then add region pins, saved 3D viewpoints and timestamp annotations. Both versions must display real artifacts, retain revision history and open Blender at the relevant stages.

The system is ready for the pilot when we can demonstrate that a requested correction creates a new inspectable revision, unapproved work cannot advance, stale approvals cannot accept newer outputs, failed/restarted jobs do not lose artifacts or duplicate known paid jobs, and the approved mesh/animation matches the file actually imported into the game. Verify provider access and perform a real end-to-end trial before claiming the pipeline is operational.
