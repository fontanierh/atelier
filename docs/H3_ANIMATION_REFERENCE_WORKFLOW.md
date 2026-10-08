# Animation reference videos: H3 Max at 480p

A reference video shows a move on the character before anyone animates it. The image-to-video model gets a render of
the approved character and a precise prompt, and returns six seconds of motion to study: contacts, timing, travel,
rotation. The skeletal animation itself is always authored locally in Blender on the character's rig, checked on the
equipped character and reviewed by a human; a generated video is never the game animation. New references use
**MiniMax H3 Max at 480p** (`minimax/minimax-h3-max`) through the Vercel AI Gateway, because it is the cheapest model
whose silhouettes and contacts read well. Keep existing references and their provenance; do not regenerate approved
footage just to change providers.

## Models

| Model | Client (`platform/studio/node/`) | Request | Use |
| --- | --- | --- | --- |
| H3 Max | `h3_max_reference.mjs` | one 6 s image-to-video clip, square, 480p (default) or 768p | every new reference |
| Seedance 2.5 (`bytedance/seedance-2.5`) | `seedance_vercel.mjs` | 6 s, 1280×720, 4:3, from reference images | when a specific capability or motion quality justifies its cost |

Install the clients once with `cd platform/studio/node && npm install` (the package pins `@ai-sdk/gateway` 4.0.80).
`AI_GATEWAY_API_KEY` is in the ignored repository-root `.env`; never print or commit it.

The H3 helper reads the price from the live model catalog before submitting and refuses a rate above $0.05 per second
at 480p ($0.08 at 768p). After success it records the settled cost from `getGenerationInfo.totalCost` in `job.json`.
Compare those generation costs, not balance differences: other tasks may spend credits at the same time. Probe the
returned file rather than assuming it matches the request: a 6 s request at 480p comes back as 480×480 at 24 fps,
about 6.6 s long.

## Writing the prompt

**Always state constant framing and real-time speed.** Without them H3 often pushes in until the character is
cropped, or plays a fast action in slow motion; either makes the clip useless for measuring travel, height or timing.
Every prompt carries, in its appearance paragraph:

> CONSTANT FRAMING: the camera never zooms, pushes in or reframes; the character stays the same size on screen
> from the first frame to the last, exactly as in the starting image. REAL-TIME SPEED: the whole clip plays at
> normal speed, no slow motion, no time stretching; a fast action takes the time it would take in real life and
> the character simply holds his ready stance afterwards.

Give fast actions their real duration inside the six seconds (a kick is over in about 1.5 s, a jump in under 2 s) and
say what the character does with the remaining time, otherwise the model stretches the action to fill the clip.

**Never submit a bare action name such as "double jump".** Write the mechanics as observable events, one useful
action family per clip:

1. **Appearance and camera:** a render of the current approved equipped model; facing direction, a fixed side or
   three-quarter camera, the complete body, a visible support surface and room for the whole trajectory. Name the
   proportions, clothing and equipment to preserve.
2. **Ordered phases:** anticipation, takeoff or drive, action, recovery, landing and settle, with approximate times
   inside the clip. For cycles, ask for several consistent repetitions rather than unrelated actions.
3. **Contacts and trajectory:** which feet or hands are planted, when support is released, how many landings occur.
   For a double jump: a second upward impulse while airborne, no contact between the impulses, a higher second apex
   and a single final landing.
4. **Direction and count:** disambiguate forward and backward rotation with screen-space and anatomical cues. For a
   right-facing profile forward somersault: clockwise on screen, chin to chest, head down and to the right, hips and
   feet passing above the head, exactly one complete rotation, then an upright recovery. Directions are relative to
   the camera and change with the view.
5. **Likely substitutions:** exclude the specific failures the action invites (a backflip, two separate ground hops,
   extra rotations, a camera spin, hidden contacts, a ground roll, equipment changes). Leave out unrelated effects
   that distract from the movement.
6. **Reviewable success criteria:** before generating, write down the contact count, impulse count, rotation
   direction and count, and the entry and exit poses.

Exact wording helps but does not guarantee compliance. A double jump can come back as a backflip, land between the
two impulses, or have the camera reframe and hide the floor, even with explicit instructions. Revise the prompt
against a concrete observed failure, keep the other inputs fixed when comparing, and limit paid iterations. When a
take is only partly right, use the clearly useful poses and author the missing mechanics locally. Human review is the
creative acceptance step.

For example, Yorimichi's [`fox_hunter_animref.py`](../games/yorimichi/assets/characters/tools/fox_hunter_animref.py)
follows these rules: it renders the starting frames and writes one revision folder per action with the shared
appearance paragraph.

## Preparing a revision

Each take is a new revision folder:

- `prompt.txt`, `inputs/starting-frame.png`, and `inputs/inputs.json` with the source and image SHA-256 and the render
  provenance.
- `api-private/starting-frame-url.json`: `{"url": "https://…", "commit": "…"}`, the starting frame at a hosted HTTPS
  address. Gateway async jobs have a **300 KB persistence limit**, so a full-size PNG cannot be sent inline. Host it
  privately (a private repository's scoped download URL, or signed storage), refresh a signed URL just before
  submitting, and never print it. The helper downloads it and checks that it matches the local frame before paying.
  Never make a repository or review service public to host an input.

The helper keeps `api-private/` at mode 0700 with private files at 0600, and writes a `.gitignore` that excludes
`api-private/`, `analysis-frames/` and `*.part`. Vercel requires **at least $10 of available credit** to start a video
job, whatever the clip costs; the helper checks the balance first.

## Submitting and resuming

From the repository root:

```sh
# The revision must be new: one that has never been submitted.
node --env-file=.env platform/studio/node/h3_max_reference.mjs submit --out "$REVISION"
# Resume the saved operation; this never starts a second generation.
node --env-file=.env platform/studio/node/h3_max_reference.mjs status --out "$REVISION"
```

`--resolution 768p` is there when a specific reason calls for it. `submit` writes the `job.json` ledger exclusively
before submitting (a revision with a ledger refuses a second submission), keeps the operation privately, and records
the price. `status` downloads the video without forwarding the API key to the CDN, validates it, and records
`reference.mp4` with its hash and cost. Poll `status` at reasonable intervals. Never delete a ledger to force another
paid submission; reconcile an uncertain submission first. Rejected revisions stay as they are.

## Inspecting a take

```sh
uv run python platform/studio/atelier/review/video_reference.py "$REVISION"
```

It probes `reference.mp4` (it needs `ffmpeg` and `ffprobe`) and builds timestamped overview and stride sheets; the
original MP4 stays unchanged. The stride sheet suits runs; for other actions use the whole-clip overview and extract
frames around contacts, takeoff, apex, rotations and landing. Check the success criteria from the prompt in the actual
MP4, at normal speed and frame by frame, before accepting it. Record mismatches in the review: a generated flip is not
a successful double jump, and its wrong contact timing must not be copied onto the game rig.

For review on a phone, `platform/studio/atelier/review/review_service.py` serves Git-tracked review files on
localhost:8790 for Tailscale Serve; it never serves `api-private/`. A phone-size browser check does not replace a check
on a real phone.

## Handing over to Blender

Name which phases and poses of the accepted video are useful and which need correction. The approved character's
proportions and rig stay authoritative: solve the game timing, root ownership and contacts explicitly, and compare the
equipped model in motion. Keep the prompt, inputs, original video, review and findings together in the revision folder
(Yorimichi keeps its existing characters' revisions in the prototype archive, under `$YORIMICHI_ARCHIVE`), and the
code that reproduces them in this repository.
