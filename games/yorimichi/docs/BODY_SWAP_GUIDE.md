# Body swap guide: a new outfit for the Warm Original in one afternoon

> Moved from the prototype repository on 29 September 2026. Paths are translated to this repository where the file moved; paths still starting with `japan/` or `output/imagegen/` refer to the prototype archive (authoring tools, earlier revisions, review images). See [docs/MIGRATION.md](../../../docs/MIGRATION.md).

This is the procedure that produced the skate outfit on 14 Sep 2026 (`body-swap-r02-headless`, in the game as
`game-r11`, with the frontflip waistband fix now in `game-r12`). It generates a whole clothed body with AI, keeps the character's own head, hands and skeleton, and
plays all existing clips unchanged. Follow it in order; every step is a script that leaves a ledger behind.

The idea in one line: **ask Tripo for a body that has no head and no hands**, so nothing has to be cut off
afterwards. Cutting a full generated body apart (the r01 attempt) never came out clean.

## 0. Before you start

- Keys in the ignored root `.env` (`OPENAI_API_KEY` for Sunburst, `TRIPO_API_KEY`). Load them with
  `set +x; set -a; source ./.env; set +a`. Never print them, never put them on a command line.
- Tripo credits: one generation is 120 credits (`tripo_asset.py balance` shows the balance).
- Blender 5.2 at `/Applications/Blender.app`, the imagegen venv at `~/.cache/yorimichi/imagegen-venv`, ffmpeg.
- The base character is the game revision, currently `game-r10/WarmOriginal-Game-r10.blend` (skeleton with 53
  bones, 25 clips including Roll, hair morphs). Its clothes are the r07 outfit; the body under them is what we
  dress. Set `BODY_SWAP_SOURCE=game-r10/WarmOriginal-Game-r10.blend` for anything that goes to the game.
- Pick a revision name and export it for every command below:

```sh
export BODY_SWAP_DIR=body-swap-r03-<slug> BODY_SWAP_STEM=WarmOriginal-BodySwap-r03 BODY_SWAP_HEADLESS=1 \
       BODY_SWAP_SOURCE=game-r10/WarmOriginal-Game-r10.blend
```

All paths below are under `output/imagegen/yorimichi-yellow-boy-2026-09-12/`.

## 1. Design the outfit (Sunburst, cheap, iterate here)

Use `games/yorimichi/assets/characters/tools/warm_back_concepts.py` with a new round (`--rev r05`, add the concepts to the script). Rules that
made round 4 work: whole-outfit redesign on the identity captures, **flat solid colours only** (no prints,
stripes, logos or patterns: graphics are added by hand later), at most four colours, no props, hair fully
visible, two figures per panel (back view left, front three-quarter right), and a sentence about hands with
five fingers. Hats need the head rebuilt, so avoid them unless that is the point.

The user picks one image. That image is the only design input from here on.

## 2. Mannequin references

```sh
/Applications/Blender.app/Contents/MacOS/Blender -b --python-exit-code 1 \
  --python games/yorimichi/assets/characters/tools/warm_body_swap_references.py -- --mannequin $BODY_SWAP_DIR
```

Writes `<rev>/references/naked-{front,back,left,right}.png`: a plain grey mannequin (body regions under the
clothes, neck and wrists capped, no head, no hands) in the bind pose, orthographic, 1024². Check that the neck
cap is a clean flat disc and the wrists end flat; a torn cap makes Sunburst draw a neck.

## 3. Dress the mannequin (Sunburst, four views)

```sh
~/.cache/yorimichi/imagegen-venv/bin/python games/yorimichi/assets/characters/tools/warm_body_swap_sunburst.py \
  --headless $BODY_SWAP_DIR --concept output/imagegen/yorimichi-yellow-boy-2026-09-12/back-concepts-r05/<pick>.png
```

The prompt already says: same T-pose, same proportions, same framing, no head, no hands, empty collar, open
sleeve ends, flat colours. If the outfit differs a lot from the skate one (long coat, hood, skirt), update the
garment sentence in `COMMON` so the four views agree on hem length, collar and sleeve ends.

Look at all four images. They must agree on: hem height, collar shape, sleeve length, shoes, colours. If one
view disagrees, rerun only that view with `--only back`. Do not send a disagreeing set to Tripo; it costs 120
credits and comes back wrong.

## 4. Generate the body (Tripo)

Write `references/approval.json` (see the r02 one: event, basis quoting the user's instruction, the four image
hashes), then:

```sh
~/.cache/yorimichi/imagegen-venv/bin/python platform/studio/atelier/ai/tripo_asset.py generate \
  --references output/imagegen/yorimichi-yellow-boy-2026-09-12/$BODY_SWAP_DIR/references \
  --output output/imagegen/yorimichi-yellow-boy-2026-09-12/$BODY_SWAP_DIR --faces 12000
```

Two to four minutes. `job.json` is the ledger; never delete it. The FBX lands in `raw/`. Look at
`raw/output_rendered_image_url.webp`: empty collar, open sleeves, nothing else.

## 5. Fit, assemble, capture, export

```sh
B=/Applications/Blender.app/Contents/MacOS/Blender
$B -b --python-exit-code 1 --python games/yorimichi/assets/characters/tools/warm_body_swap_fit.py
$B -b --python-exit-code 1 --python games/yorimichi/assets/characters/tools/warm_body_swap_assemble.py
$B -b --python-exit-code 1 --python games/yorimichi/assets/characters/tools/warm_body_swap_capture.py
$B -b --python-exit-code 1 --python games/yorimichi/assets/characters/tools/warm_body_swap_export.py
```

What each does and what to read afterwards:

- **fit** aligns the Tripo body on the base body: scale by arm span onto the mannequin's wrist stumps, floor to
  floor, centred on the chest depth, then each sleeve slid onto its forearm axis. Read `fit/align.json`:
  `chest_front_clearance_mm` should be a few mm positive, `*_sleeve_slide_mm` typically 10 to 30 mm; look at
  `fit/both-*.png` (base body must be fully inside the outfit) and `fit/gen-*.png`.
- **assemble** builds `assembled/<stem>.blend`: opens the neck stump cap if Tripo closed it, keeps the original
  head, hands, a capped 3.5 cm of forearm inside each sleeve mouth and the front chest skin inside the collar,
  transfers weights from the base body, applies per-garment rules (sleeves ride the arm, tee body never takes
  leg weights, hems copy the trousers' weights), prunes to four influences, smooths, adds 2 mm cloth thickness,
  dual-quaternion skinning. Read `assembled/assembly.json`: `garment_faces` must list the tee (1) and trousers
  (3); `bones` 53; `actions` 25 for a game source.
- **capture** renders 52 views (9 poses × 4 views + neck and wrist close-ups) into `captures/`. Look at
  `standing--front-left`, `standing--neck`, `standing--neck-back`, `standing--wrist-left`, `sprint27--back`,
  `crouch--back`, `sit--front`, `doublejump--back` before anything else.
- **export** writes `assembled/<stem>.glb` with all clips.

## 6. Independent QA (do not skip)

Launch three Opus reviewers in parallel with the prompts used in this session (neck seam, wrist seams, whole
body). Give them: the captures folder, the naming scheme, the instruction to crop and upscale every region with
PIL and to sample pixel colours to tell shading from holes (background is (130,132,135)), and the clean / minor /
blocker table format. Save their reports in `<rev>/qa/findings-<area>-r<n>.md` (they usually cannot write files;
copy the text). Fix, re-capture, re-review. Wrists and neck converged in three rounds on the skate outfit; the
body took four and still had one open item (see 9).

Things the reviewers found that I had not: palm stubs inside the cuff, the neck's open ring showing through the
collar, sleeves separating from forearms (which turned out to be a 3 cm fit offset), the hem band crossing the
trouser seat. Assume they will find something.

## 7. Into the game

Choose the next unused revision; `game-r12` already contains the accepted
frontflip correction. The example below uses `game-r13`.

```sh
R=output/imagegen/yorimichi-yellow-boy-2026-09-12
mkdir -p $R/game-r13 && cp $R/$BODY_SWAP_DIR/assembled/$BODY_SWAP_STEM.blend $R/game-r13/WarmOriginal-Game-r13.blend
# source-manifest.json: copy game-r11's, update native, native_sha256, garment_source(+sha256), note
/Applications/Blender.app/Contents/MacOS/Blender -b --threads 4 --python-exit-code 1 \
  --python games/yorimichi/assets/characters/warm-original/export_unreal.py -- --revision game-r13 > build/yorimichi/logs/warm-export-r13.log 2>&1
"/Users/Shared/Epic Games/UE_5.8/Engine/Build/BatchFiles/Mac/Build.sh" JapanProtoEditor Mac Development \
  -project="$PWD/games/yorimichi/unreal/Yorimichi.uproject" -WaitMutex        # only if C++ changed
python3 games/yorimichi/streaming/guarded_game.py build/yorimichi/warm_original/import-r13 \
  "/Users/Shared/Epic Games/UE_5.8/Engine/Binaries/Mac/UnrealEditor-Cmd" "$PWD/games/yorimichi/unreal/Yorimichi.uproject" \
  -run=pythonscript -script="$PWD/games/yorimichi/unreal/Scripts/import_warm_original.py" -unattended -nosplash -NullRHI -stdout
```

The export selects meshes by `outfit_slot` or an unhidden `body_region`; the assembled outfit carries
`body_region = outfit_body` and `equipment_id`, so it is picked up without changes. Materials must have their base
colour either constant or a single image texture; Tripo's material satisfies that. Expect `UNREAL_CLIP_EXPORTED`
for 25 clips and the import to end with exit 0.

## 8. Film it in the game

```sh
E="/Users/Shared/Epic Games/UE_5.8"; P="$PWD/games/yorimichi/unreal"; OUT="$PWD/build/yorimichi/warm_original/film-r13"
for VIEW in front back; do D="$OUT/$VIEW"; mkdir -p "$D"
  python3 games/yorimichi/streaming/guarded_game.py "$D" "$E/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor" \
    "$P/Yorimichi.uproject" -game -windowed -resx=1280 -resy=720 -warmqa -warmfilm -framestride=2 \
    -UseFixedTimeStep -FPS=60 -warmview=$VIEW "-reviewdir=$D" -stdout "-abslog=$D/game.log"
done
python3 japan/tools/warm_film_assemble.py "$OUT"      # -> film-r13/warm-r13-front-back.mp4
```

`-warmqa` drives walk, run, sprint, dash, jump, double jump and rolls on a flat floor and writes `warm.csv`
(time, action, speed) and `result.json`; the film mode records one frame in two at a fixed 60 fps step (30 fps
video). `warmview` accepts `front`, `back`, `side`. The assembler cuts run, sprint, dash, jump and roll and stacks
front and back side by side. One QA check fails by design with a one-piece outfit ("waist corrective survives
runtime graph": the old shorts' morph no longer exists).

## 9. Constants that may need re-measuring for a different outfit

All in `warm_body_swap_assemble.py` unless noted.

| What | Value now | Why | Re-measure when |
| --- | --- | --- | --- |
| collar fill | r ≤ 42 mm, z ≥ .13, front half, shrunk 5 mm | covers the neck's open cut ring without peeking past the collar | a wider or lower neckline |
| neck stump cap removal | z > .15, r < 30 mm, face normal mostly vertical | opens the cap Tripo puts on the stump | a high collar or hood |
| kept forearm | 30 mm before the sleeve end (|y| > .30), capped, shrunk 3 mm fading at the wrist | forearm continuous with the hand, hidden inside a slimmer sleeve | sleeves ending elsewhere than the wrist (edit the .30) |
| sleeve slide (fit) | measured per side over |y| .25–.33 | Tripo puts the arms ~3 cm forward and 1 cm low | never; it is measured |
| sleeve vertices | tee vertices with |y| > .16, or above the armpit and |y| > .105, or nearest body was the arm | ride the upper-arm bone, blend .09–.14 | sleeveless or long-sleeved tee |
| hem copy | tee and band vertices below z −.04 copy the nearest trouser vertex within 4 cm | layers move together | a coat over bare legs (no trousers to copy) |
| garment tags | tee: > 800 faces, top above z .15, wider than |y| .2; trousers: reaching below z −.4 | drives the rules above | anything that is not tee-over-trousers |
| wrist stumps (references) | mannequin cut at |y| .335 (the r07 hands region) | Sunburst ends the sleeves there | never |

## 10. Pitfalls that cost hours

- **Never classify faces by baked colour.** Tripo paints skin colour onto the inside of cuffs and collars; a
  colour rule shortened the sleeve once and punched a hole in the tee once. Geometry only.
- **Never cut a full generated body apart.** The hand grows out of the cuff as one surface. Generate headless
  and handless instead.
- **Align on something that exists in both meshes.** Whole-mesh means are biased by baggy clothes; the head is
  absent; legs are wide. Chest depth for front/back, arm span for scale, per-sleeve slide for the arms.
- **Creating a bmesh layer invalidates every BMVert/BMFace reference you hold.** Create layers right after
  `from_mesh`, before walking components or holding vertices.
- **Diagnostic renders must not un-hide objects.** The grey fitting-suit body is hidden by slot; a render script
  that sets `hide_render` on every object showed it through the sleeves and sent me chasing a phantom.
- **Reviewers read the captures that exist when they start.** Re-rendering mid-review makes their findings
  stale; wait, or version the capture folders.
- **Artifacts:** the host blocks runtime fetch and blob URLs. Embed the mesh as base64 in the page and ship
  textures as plain image files loaded through image tags (`createImageBitmap` disabled).

## 11. Open items on the skate outfit

- The tee's short sleeve leaves the far-swung arm from behind in sprint and dash (weights are right; cause not
  found; visible in the in-game film).
- Doublejump tuck: a small trouser patch through the tee on the upper back.
- Minor: white band z-fights the tee rim at the front; dark crevice at the nape corner; hands enter the baggy
  trousers in crouch (animation, not asset).
- No corrective morphs on the outfit; one merged outfit slot replaces shirt, shorts, socks and shoes.

## Where things are

- Tools: `japan/tools/warm_body_swap_{references,sunburst,fit,assemble,capture,export}.py`,
  `warm_film_assemble.py`, `warm_back_concepts.py`, `tripo_asset.py`, `export_warm_original_unreal.py`,
  `games/yorimichi/unreal/Scripts/import_warm_original.py`.
- Revisions: `body-swap-r01` (cut-based, failed, kept for reference), `body-swap-r02-headless` (this guide),
  `game-r11` (in the game), `back-concepts-r04` (the design studies).
- Reports: `body-swap-r02-headless/qa/findings-*.md`, the review page artifact from 14 Sep, the front/back film
  `build/yorimichi/warm_original/film-r11/warm-r11-front-back.mp4`.

## 16 September: frontflip waistband clearance

The body swap needed a concealed-waist correction after review of the full
double-jump tuck. `game-r12` lowers the upper trousers smoothly by 12 mm in
source units; the visible tee and all animation curves stay unchanged.
`japan/tools/fix_warm_frontflip_waist.py` reproduces the change and checks the
rear shirt panel at 240 Hz in both Blender DQ and game/glTF linear skinning.
Check the deepest tuck, not only frame 14 used in the original capture sweep.
See [the revision report](../../output/imagegen/yorimichi-yellow-boy-2026-09-12/game-r12/README.md)
for before/after captures, scope and game mesh-only reimport commands.
