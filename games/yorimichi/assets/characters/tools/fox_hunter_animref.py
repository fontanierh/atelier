#!/usr/bin/env python3
"""Fox hunter animation set: brief, starting frames and H3 Max reference revisions.

Stage A (Blender):  blender -b --python-exit-code 1 --python games/yorimichi/assets/characters/tools/fox_hunter_animref.py -- render
    Renders the approved rig (tripo-rig-r02, frozen contract) in a relaxed standing pose from three cameras
    into animref/inputs/: side-centred, side-left-third (for rightward travel) and three-quarter front.
Stage B (plain python):  python games/yorimichi/assets/characters/tools/fox_hunter_animref.py prepare
    Writes one revision folder per action under animref/<slug>-r01/ with prompt.txt, inputs/ and .gitignore,
    following games/yorimichi/docs/H3_ANIMATION_REFERENCE_WORKFLOW.md. Submission is done by the shell loop in
    animref/submit_all.sh (gh-hosted input URL, then platform/studio/node/h3_max_reference.mjs submit/status).
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import hashlib, json, sys
from pathlib import Path

# ROOT (the archive) comes from _archive
ASSET = ROOT / 'output/imagegen/yorimichi-fox-hunter-2026-09-13'
RIG = ASSET / 'tripo-rig-r02/blender/FoxHunter-Rig-r02.blend'
AREF = ASSET / 'animref'
INPUTS = AREF / 'inputs'

APPEARANCE = (
    "Animate the exact character from the starting image: a thin hunched humanoid enemy in a white fox mask with "
    "pointed ears, dark hood, rust-red scarf, thick rope collar with two hanging paper tags, short pointed shoulder "
    "cape in grey-green and rust, dark ragged tunic, thin dark sleeves with bandaged forearms, long clawed hands, "
    "dark cropped trousers, bandaged shins and flat sandals. Preserve these proportions, clothing and colours "
    "exactly; no accessories, weapons, text or dialogue. Clean 6-second game-animation reference, locked camera, "
    "no cuts, no camera tracking, no motion effects, full body visible at all times, level grey floor, "
    "fixed plain background. CONSTANT FRAMING: the camera never zooms, pushes in or reframes; the character stays "
    "the same size on screen from the first frame to the last, exactly as in the starting image. REAL-TIME SPEED: "
    "the whole clip plays at normal speed, no slow motion, no time stretching; a fast action takes the time it "
    "would take in real life and the character simply holds his ready stance afterwards. "
)
SIDE = "The camera is a fixed side view; he faces RIGHT. "
THREEQ = "The camera is a fixed three-quarter front view; he faces toward the camera's left-front. "
NO = "Never: "

# slug, view key, label, kind, prompt body, success criteria (what to check in the MP4)
ACTIONS = [
    ('idle', 'threeq', 'Idle', 'loop',
     "He stands in place, watchful and hostile, weight shifting slowly from one foot to the other, shoulders hunched, "
     "arms low with claws opening and closing a little, head turning slowly left and right as if scanning. Both feet "
     "stay planted the whole time; no steps. Repeat the same slow sway three times so it can loop. "
     + NO + "walking, attacking, jumping, looking at the camera, changing pose drastically.",
     "feet never leave the floor; three similar sway cycles; no big pose change"),
    ('walk', 'side_left', 'Walk', 'loop',
     "He walks slowly to the right in a stalking, hunched prowl, knees bent, arms hanging low with claws forward, "
     "head level and fixed on something ahead. Steady pace, four complete stride cycles, heel-to-toe contact on every "
     "step, covering about half the frame width over the six seconds. "
     + NO + "running, stopping, turning, jumping, arm flailing.",
     "four even cycles; clear alternating foot contacts; constant speed"),
    ('run', 'side_left', 'Run', 'loop',
     "He runs fast to the right in a low predatory sprint, torso pitched forward, arms trailing behind with claws "
     "open, long bounding strides with a short airborne moment in each. Five complete stride cycles at constant speed, "
     "moving across the frame from left to right. "
     + NO + "walking, slowing down, stumbling, flipping, four-legged running.",
     "five cycles; airborne phase each stride; forward lean held"),
    ('attack_claw_right', 'threeq', 'Claw attack, right', 'one-shot',
     "Standing in place, he attacks with his RIGHT claw: 0-1s he draws the right arm back and up above the shoulder "
     "while the left foot steps slightly forward; 1-1.6s a fast diagonal slash with the right claw from upper right "
     "down across the body to lower left, torso twisting into it; 1.6-3s he holds the follow-through with the claw "
     "low, then 3-6s slowly returns to the hunched ready stance. Exactly one slash. "
     + NO + "two slashes, using the left arm, stepping more than one step, jumping, spinning.",
     "one slash; right arm only; one small step; returns to ready"),
    ('attack_claw_left', 'threeq', 'Claw attack, left', 'one-shot',
     "Standing in place, he attacks with his LEFT claw: 0-1s he draws the left arm back and up above the shoulder "
     "while the right foot steps slightly forward; 1-1.6s a fast diagonal slash with the left claw from upper left "
     "down across the body to lower right, torso twisting into it; 1.6-3s he holds the follow-through with the claw "
     "low, then 3-6s slowly returns to the hunched ready stance. Exactly one slash. "
     + NO + "two slashes, using the right arm, stepping more than one step, jumping, spinning.",
     "one slash; left arm only; mirror of the right attack"),
    ('kick', 'side', 'Kick', 'one-shot',
     "Standing in place, he delivers ONE fast front kick to the right with his RIGHT leg, at real fighting speed: "
     "0-0.4s weight shifts onto the left foot and the right knee lifts to hip height; 0.4-0.7s the right foot snaps "
     "straight out to the right at chest height, arms swinging back for balance; 0.7-1.0s the leg retracts; "
     "1.0-1.4s the right foot plants back down; from 1.4s to the end he holds the hunched ready stance, almost "
     "still. The left foot stays planted throughout. The kick is over within a second and a half. "
     + NO + "slow motion, jumping, spinning, kicking with the left leg, hopping, punching, a second kick.",
     "one kick within 1.5 s; left foot planted; right foot returns to floor; still afterwards"),
    ('dash_forward', 'side_left', 'Dash forward', 'one-shot',
     "From a standstill he dashes to the RIGHT: 0-0.8s he crouches low, loading the legs; 0.8-2s an explosive low "
     "leap forward, body stretched almost horizontal, claws reaching ahead, briefly airborne; 2-3s he lands on both "
     "feet and slides to a stop in a low crouch, one hand touching the floor; 3-6s he rises back into the hunched "
     "ready stance. He travels about half the frame width. "
     + NO + "flipping, rolling, running steps, jumping high, dashing left.",
     "one leap; lands on both feet; slide stop; ends standing"),
    ('dash_backward', 'side', 'Dash backward', 'one-shot',
     "From a standstill he springs BACKWARD to the LEFT while still facing right, at real speed: 0-0.4s a quick "
     "crouch; 0.4-1.0s one strong backward leap, both feet clearly off the floor, body leaning back, arms thrown "
     "forward for balance, covering about a third of the frame width to the left; 1.0-1.4s lands on both feet in a "
     "crouch; 1.4-2.2s recovers into the hunched ready stance, still facing right; then holds it to the end. "
     + NO + "slow motion, turning around, flipping, rolling, walking backward, jumping high, a second leap.",
     "one backward leap within 1.5 s; faces right throughout; both feet land; clear travel left"),
    ('turn_left', 'threeq', 'Turn left 180', 'one-shot',
     "Standing in place, he turns around to his LEFT by 180 degrees: 0-0.5s the head looks left first; 0.5-2s the "
     "torso follows and the feet reposition in two small steps, pivoting on the balls of the feet, so that he ends "
     "facing the opposite direction; 2-6s he settles into the hunched ready stance facing the new direction and "
     "stays still. Exactly one half turn. "
     + NO + "walking away, turning right, spinning a full circle, jumping.",
     "half turn to the left; two foot steps; ends still"),
    ('turn_right', 'threeq', 'Turn right 180', 'one-shot',
     "Standing in place, he turns around to his RIGHT by 180 degrees: 0-0.5s the head looks right first; 0.5-2s the "
     "torso follows and the feet reposition in two small steps, pivoting on the balls of the feet, so that he ends "
     "facing the opposite direction; 2-6s he settles into the hunched ready stance facing the new direction and "
     "stays still. Exactly one half turn. "
     + NO + "walking away, turning left, spinning a full circle, jumping.",
     "half turn to the right; two foot steps; ends still"),
    ('hurt', 'threeq', 'Hurt', 'one-shot',
     "Standing in place, he takes a hard hit to the chest from the front: 0-0.3s impact, head and shoulders snap "
     "back, arms fly out; 0.3-1.2s he staggers one step backward, bent over, one claw clutching the chest; 1.2-3s he "
     "steadies himself; 3-6s he straightens back into the hunched ready stance, angry. "
     + NO + "falling down, jumping, attacking, turning around, taking more than one step.",
     "one flinch; one step back; recovers standing"),
    ('death', 'threeq', 'Defeat', 'one-shot',
     "Standing in place, he is defeated: 0-0.5s a hard hit knocks his head back; 0.5-1.5s his knees buckle and he "
     "drops to both knees, arms hanging; 1.5-3s he folds forward and collapses face-down onto the floor, claws "
     "sliding out to the sides; 3-6s he lies completely still. The mask stays on. "
     + NO + "getting back up, exploding, disappearing, falling backward, rolling.",
     "drops to knees then face down; still by 3 s; mask stays on"),
    ('jump', 'side', 'Jump', 'one-shot',
     "Standing in place, ONE quick vertical jump at real speed: 0-0.3s crouch; 0.3-0.5s takeoff straight up with "
     "arms swinging up, both feet leaving the floor; 0.5-1.0s rises to an apex about half his height above the "
     "floor, knees tucked slightly, claws spread; 1.0-1.4s descends and lands softly on both feet with a knee bend; "
     "1.4-2.0s stands up into the hunched ready stance; then holds it to the end. No travel to the side. The whole "
     "jump takes under two seconds. " + NO + "slow motion, flipping, double jump, running, kicking, a second jump.",
     "one takeoff and one landing within 1.5 s; no travel; still afterwards"),
]
VIEWS = {'side': 'starting-side.png', 'side_left': 'starting-side-left.png', 'threeq': 'starting-threeq.png'}


def render():
    import bpy
    from mathutils import Vector
    bpy.ops.wm.open_mainfile(filepath=str(RIG))
    sc = bpy.context.scene
    arm = next(o for o in sc.objects if o.type == 'ARMATURE')
    body = next(o for o in sc.objects if o.type == 'MESH' and o.vertex_groups)
    # Relaxed standing pose built directly: arms lowered to ~20 degrees from vertical, then rotated about their own
    # hanging axis so the PALMS FACE THE BODY (user rule: hands naturally along the body, never palms forward).
    import math
    from mathutils import Matrix
    sc.frame_set(0)
    arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.rotation_mode = 'QUATERNION'; pb.rotation_quaternion = (1, 0, 0, 0)
    def local_q(pb, R):
        M = pb.bone.matrix_local.to_3x3()
        return (M.inverted() @ R @ M).to_quaternion()
    for side, sgn in (('Left', 1), ('Right', -1)):
        pb = arm.pose.bones[f'mixamorig:{side}Arm']
        lower = Matrix.Rotation(math.radians(-70 * sgn), 3, 'X')            # arm down, as in the shoulders test
        hang = lower @ Vector((0, sgn, 0))                                   # the arm's direction once lowered
        twist = Matrix.Rotation(math.radians(90 * sgn), 3, hang)             # palm normal +X turns toward the body
        pb.rotation_quaternion = local_q(pb, twist @ lower)
        fa = arm.pose.bones[f'mixamorig:{side}ForeArm']
        fa.rotation_quaternion = local_q(fa, Matrix.Rotation(math.radians(-12), 3, 'Y') if False else Matrix.Identity(3))
        hand = arm.pose.bones[f'mixamorig:{side}Hand']
        for prop, v in (('index_curl', .25), ('middle_curl', .3), ('ring_curl', .3), ('pinky_curl', .25), ('thumb_curl', .2), ('thumb_opposition', .2), ('finger_spread', 0.0)):
            hand[prop] = v
    bpy.context.view_layer.update()
    h = body.dimensions.z
    # floor plane so the model sees a support surface
    bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, 0))
    floor = bpy.context.active_object
    m = bpy.data.materials.new('Floor'); m.use_nodes = True
    m.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.58, 0.59, 0.61, 1)
    m.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = 1.0
    floor.data.materials.append(m)
    sc.world.node_tree.nodes['Background'].inputs[0].default_value = (0.66, 0.67, 0.70, 1)
    cam = sc.camera; cam.data.type = 'ORTHO'; cam.data.ortho_scale = 2.0
    sc.render.resolution_x = sc.render.resolution_y = 1024
    sc.render.engine = 'BLENDER_EEVEE'
    INPUTS.mkdir(parents=True, exist_ok=True)
    shots = {
        'starting-side.png': (Vector((0.0, 0, h * 0.5)), Vector((0, -6, 0))),
        'starting-side-left.png': (Vector((0.55, 0, h * 0.5)), Vector((0, -6, 0))),   # he stands in the left third, room to travel right
        'starting-threeq.png': (Vector((0.0, 0, h * 0.5)), Vector((4.2, -4.2, 0.6))),
    }
    rec = {}
    for name, (target, offset) in shots.items():
        cam.location = target + offset
        cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = str(INPUTS / name)
        bpy.ops.render.render(write_still=True)
        rec[name] = dict(sha256=hashlib.sha256((INPUTS / name).read_bytes()).hexdigest(), camera_target=list(target),
                         camera_offset=list(offset), orthographic_scale=2.0)
    (INPUTS / 'inputs.json').write_text(json.dumps(dict(
        source=str(RIG.relative_to(ROOT)), source_sha256=hashlib.sha256(RIG.read_bytes()).hexdigest(),
        pose_frame=None, pose='relaxed stand authored on the approved rig r02: arms lowered ~20 deg from vertical and twisted so palms face the thighs, claws slightly curled; no mesh or rig edits',
        method='Actual rigged enemy rendered in Blender (Eevee, orthographic 1024 px) on a grey floor; no generative editing',
        images=rec), indent=2) + '\n')
    print('RENDER OK', list(rec))


def write_submit_script():
    (AREF / 'submit_all.sh').write_text('''#!/bin/zsh
# Submit every prepared fox-hunter reference revision that has no job.json yet, then poll all until downloaded.
# Usage (from repo root, after committing and pushing animref/*/inputs):  zsh output/.../animref/submit_all.sh
set -u
cd "$(git rev-parse --show-toplevel)"
AREF=output/imagegen/yorimichi-fox-hunter-2026-09-13/animref
COMMIT=$(git rev-parse HEAD)
for rev in $AREF/*-r0[0-9]; do
  [ -f "$rev/job.json" ] && continue
  mkdir -p "$rev/api-private"; chmod 700 "$rev/api-private"
  url=$(gh api "repos/${ANIMREF_INPUT_REPO:?set ANIMREF_INPUT_REPO=owner/private-repo holding the inputs}/contents/$rev/inputs/starting-frame.png?ref=$COMMIT" --jq .download_url)
  [ -z "$url" ] && { echo "no url for $rev"; continue; }
  printf '{"url":"%s","commit":"%s"}\\n' "$url" "$COMMIT" > "$rev/api-private/starting-frame-url.json"; chmod 600 "$rev/api-private/starting-frame-url.json"
  echo "== submit $rev"; node --env-file=.env platform/studio/node/h3_max_reference.mjs submit --resolution 480p --out "$rev" || echo "submit failed: $rev"
done
for i in $(seq 1 60); do
  pending=0
  for rev in $AREF/*-r0[0-9]; do
    [ -f "$rev/reference.mp4" ] && continue
    [ -f "$rev/api-private/operation.json" ] || continue
    node --env-file=.env platform/studio/node/h3_max_reference.mjs status --out "$rev" 2>&1 | grep -v "^$" | sed "s|^|$(basename $rev): |"
    [ -f "$rev/reference.mp4" ] || pending=$((pending+1))
  done
  [ $pending -eq 0 ] && break
  sleep 20
done
echo "DONE: $(ls $AREF/*-r0[0-9]/reference.mp4 2>/dev/null | wc -l) videos"
''')


def prepare(rev_name='r01', only=None):
    inputs = json.loads((INPUTS / 'inputs.json').read_text())
    brief = []
    for slug, view, label, kind, body, criteria in ACTIONS:
        if only and slug not in only:
            continue
        rev = AREF / f'{slug}-{rev_name}'
        (rev / 'inputs').mkdir(parents=True, exist_ok=True)
        img = VIEWS[view]
        src = INPUTS / img
        dst = rev / 'inputs/starting-frame.png'
        dst.write_bytes(src.read_bytes())
        cam = SIDE if view.startswith('side') else THREEQ
        prompt = APPEARANCE + cam + body + '\n'
        (rev / 'prompt.txt').write_text(prompt)
        (rev / '.gitignore').write_text('api-private/\n*.part\nanalysis-frames/\n')
        (rev / 'inputs/inputs.json').write_text(json.dumps(dict(
            source=inputs['source'], source_sha256=inputs['source_sha256'], image='starting-frame.png',
            image_sha256=inputs['images'][img]['sha256'], shared_render=f'animref/inputs/{img}',
            pose=inputs['pose'], method=inputs['method'], camera=view,
            action=slug, label=label, kind=kind, success_criteria=criteria), indent=2) + '\n')
        brief.append(dict(slug=slug, label=label, kind=kind, camera=view, revision=rev.name, success_criteria=criteria))
    write_submit_script()
    if only:
        (AREF / f'brief-{rev_name}.json').write_text(json.dumps(dict(revision=rev_name, actions=brief, reason='user review of r01'), indent=2) + '\n')
        print('PREPARE OK', len(brief), 'revisions', rev_name); return
    (AREF / 'brief.json').write_text(json.dumps(dict(
        asset='fox-hunter', rig='tripo-rig-r02 (approved, frozen)', provider='minimax/minimax-h3-max via Vercel AI Gateway',
        resolution='480p', seconds=6, actions=brief), indent=2) + '\n')
    print('PREPARE OK', len(brief), 'revisions')


if __name__ == '__main__':
    stage = (sys.argv[sys.argv.index('--') + 1] if '--' in sys.argv else (sys.argv[1] if len(sys.argv) > 1 else ''))
    if stage == 'render':
        render()
    elif stage == 'prepare':
        rev = sys.argv[sys.argv.index('--rev') + 1] if '--rev' in sys.argv else 'r01'
        only = sys.argv[sys.argv.index('--only') + 1].split(',') if '--only' in sys.argv else None
        prepare(rev, only)
    else:
        sys.exit('stage must be render (in Blender) or prepare')
