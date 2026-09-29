# Animation references: H3 Max at 480p first

> Moved from the prototype repository on 29 September 2026. Paths are translated to this repository where the file moved; paths still starting with `japan/` or `output/imagegen/` refer to the prototype archive (authoring tools, earlier revisions, review images). See [docs/MIGRATION.md](../../../docs/MIGRATION.md).

Updated 13 September 2026. **The user prefers H3 Max at 480p for new motion-reference videos because it is cheaper.** Use Vercel AI Gateway model `minimax/minimax-h3-max` with the existing root `.env` key. Keep Seedance 2.5 available for cases where a specific reference capability or motion quality justifies its cost. Preserve all existing Seedance references and their provenance; do not regenerate approved footage just to change providers.

This is a reference-video workflow. Astra/Claude still authors the actual skeletal motion with Blender Python, validates the equipped character and exports it for human review. H3 does not deliver a rigged game animation.

## What the trial established

[Phone comparison](<tailnet address>) · [Detailed generation record](../../output/imagegen/yorimichi-yellow-boy-2026-09-12/h3-max-double-jump-r05/README.md)

| Setting or observation | Verified result |
| --- | --- |
| Provider / model | Vercel Gateway → MiniMax, `minimax/minimax-h3-max`; Max, not Turbo |
| Preferred request | One 6-second image-to-video clip, `resolution=480p`, square |
| Actual files | 480×480, 24 fps, 158 frames, 6.58333-second video stream |
| Retrieved generation cost | $0.15 per take; $0.45 for three generated takes (r03–r05) |
| Catalog price at submission | 480p $0.025/s; 768p $0.04/s, or $0.24 for six seconds |
| Motion quality | Readable silhouettes/contacts at 480p; precise game action still needs careful prompting and inspection |

The 480p request was 37.5% cheaper than 768p at that timestamp. These rates include a [Vercel promotion through September 13](https://vercel.com/changelog/minimax-h3-and-h3-max-are-50-off-on-ai-gateway); query the [live model catalog](https://ai-gateway.vercel.sh/v1/models) for future jobs. The helper retrieves `getGenerationInfo.totalCost` after success. Compare generation-specific costs, not balance differences while other tasks may also spend credits. Probe the output rather than assuming requested duration/dimensions exactly match the returned file.

## Precise prompt guidance is required

**Always state constant framing and real-time speed** (added 13 September after the fox-hunter set). In thirteen
enemy clips, four (run, kick, dash backward, jump) ignored "locked camera, no zoom" and pushed in until the
character was cropped, and two (kick, jump) played the action in slow motion. Both failures make the clip useless
for measuring travel, height or timing. Every prompt now carries, in the shared appearance paragraph:

> CONSTANT FRAMING: the camera never zooms, pushes in or reframes; the character stays the same size on screen
> from the first frame to the last, exactly as in the starting image. REAL-TIME SPEED: the whole clip plays at
> normal speed, no slow motion, no time stretching; a fast action takes the time it would take in real life and
> the character simply holds his ready stance afterwards.

Give fast actions their real duration inside the six seconds (a kick is over in about 1.5 s, a jump in under 2 s)
and say what the character does with the remaining time, otherwise the model stretches the action to fill the clip.

**Do not submit a vague action name such as “double jump.”** Write the desired mechanics as observable events and give the model one useful action family per clip:

1. **Appearance and camera:** use a render of the current approved equipped model; state facing direction, fixed side/three-quarter camera, complete body, visible support surface and enough room for the entire trajectory. Preserve proportions, clothing and equipment explicitly.
2. **Ordered phases:** describe anticipation → takeoff/drive → action → recovery → landing/settle, with approximate times inside the requested duration. For cycles, ask for several consistent repetitions instead of unrelated actions.
3. **Contacts and trajectory:** say which feet/hands are planted, when support is released and how many landings occur. For double jump, explicitly require a second upward impulse while airborne, no contact between impulses, a higher second apex and only one final landing.
4. **Direction and count:** disambiguate forward/backward rotation with screen-space and anatomical cues. For a right-facing profile forward somersault: clockwise on screen, chin to chest, head down/right, hips and feet passing above the head, exactly one complete rotation, then upright recovery. State direction relative to the camera; it changes when the view changes.
5. **Likely substitutions:** explicitly exclude the specific failures relevant to the action: backflip, two separate ground hops, extra rotations, camera spin, hidden contacts, ground roll or equipment changes. Avoid an unrelated list of effects that distracts from the movement.
6. **Reviewable success criteria:** record the contact count, impulse count, rotation direction/count and entry/exit pose before generation. Inspect those events in the actual MP4 at normal speed and frame by frame before accepting it.

Exact wording helps but **does not guarantee compliance**. In this trial, r03 made a backflip; r04's explicit clockwise/anatomical instructions corrected the rotation, but it landed before the second jump. Neither is a faithful double-jump reference. Retain those mismatches in the review; do not call a generated flip a successful double jump or copy its wrong contact timing onto the game rig.

A further user-requested r05 trial used much more explicit guidance: one continuous flight, game-physics permission, a timed no-contact interval, the second impulse before descent and a repeated forbidden sequence. It removed the extra touchdown, but the camera reframed and obscured the floor; the second upward acceleration was still not distinct enough to verify. See the recorded take rather than treating stronger wording as proof of success.

Revise the prompt to address a concrete observed failure, keep other inputs fixed when comparing, and limit paid iterations. If further trials are not justified, use only the clearly labeled useful poses and author missing mechanics locally, or explain why another model is needed. Human review remains the creative acceptance step.

## API execution and resumption

Use [h3_max_reference.mjs](../../../platform/studio/node/h3_max_reference.mjs). It loads the official SDK from `~/.cache/yorimichi/vercel-video/`; the working version is `@ai-sdk/gateway@4.0.80`. `AI_GATEWAY_API_KEY` is in the ignored repository-root `.env`. Never print or commit credentials.

Prepare a **new** revision with:

- `prompt.txt`, `inputs/starting-frame.png`, and `inputs/inputs.json` containing source/image SHA-256 and render provenance.
- `.gitignore` excluding `api-private/`, `analysis-frames/` and `*.part`.
- Private `api-private/starting-frame-url.json` containing `{"url":"https://…","commit":"…"}`. Keep the directory mode 0700 and private files 0600.

The 969 KB PNG exceeded Gateway's **300 KB async persistence limit** when sent inline (r01, HTTP 413). Use a hosted HTTPS URL instead. Our working route commits the input to a private GitHub repository, retrieves its temporary scoped `download_url` with authenticated `gh api repos/<owner>/<private-repo>/contents/<input-path>?ref=<commit>`, captures that response privately and verifies an unauthenticated download against the local SHA-256. Do not print the signed URL. Refresh it immediately before submission; for longer queues prefer appropriate existing signed storage. Never make the repository or Tailscale review public to host inputs.

Vercel also requires **at least $10 of available balance to start video jobs**, independently of this clip's small price (r02, HTTP 402). The helper checks credits before submitting and retains financial account details privately.

After preparing the revision, from the repository root:

```sh
# Set this to the actual NEW prepared revision, not one already submitted.
node --env-file=.env platform/studio/node/h3_max_reference.mjs submit --resolution 480p --out "$animation_reference_revision"
# Resume the saved operation; this never starts a second generation.
node --env-file=.env platform/studio/node/h3_max_reference.mjs status --out "$animation_reference_revision"
```

480p is the helper default; `--resolution 768p` is available when there is a specific reason. It writes an exclusive ledger before submission, retains the operation privately, checks catalog pricing, downloads without forwarding the API key to the CDN, validates the MP4 and records its hash and cost. Poll `status` at reasonable intervals. Never delete a ledger to force another paid submission. Reconcile an uncertain submission first; rejected revisions remain history.

## Inspection, phone review and Blender handoff

Run `~/.cache/yorimichi/imagegen-venv/bin/python platform/studio/atelier/review/video_reference.py REVISION`. Keep the original MP4 unchanged and extract timestamped frames around contacts, takeoff, apex, rotations and landing. The helper's early stride sheet is designed for runs; use the whole-clip overview and more targeted frames for other actions.

Publish the actual MP4 with native inline controls, ¼×/½× speed, frame stepping, timestamped failure checkpoints, input image, prompt, cost and honest motion notes. Follow the existing [private Tailscale review service](ASSET_REVIEW_TAILSCALE.md), preserve its current root entry and refresh its tracked-file manifest. Verify HTTP 200, MP4 byte-range 206, playback and narrow-screen layout. Phone-size browser checks do not substitute for physical iPhone validation. Do not expose `api-private/`.

For Blender, name which accepted video phases/poses are useful and which need correction. Keep the approved character proportions and rig authoritative, solve game timing/root ownership/contacts explicitly, and compare the equipped model in motion. Commit and push the prompt, inputs, originals, derived review, findings and reproduction code at task boundaries.
