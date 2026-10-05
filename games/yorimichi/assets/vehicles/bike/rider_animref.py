"""Cairo's bike set: H3 Max reference revisions (docs/H3_ANIMATION_REFERENCE_WORKFLOW.md).

    python3 games/yorimichi/assets/vehicles/bike/rider_animref.py FRAMES OUT

FRAMES holds the starting frames rider.py renders (`blender -b --python rider.py -- --frames FRAMES`): Cairo beside the
teal mamachari, and Cairo riding it, on the approved rig and the approved bike. OUT receives one revision folder per
action (<slug>-r01/) with prompt.txt and inputs/ (the frame, its SHA-256 and provenance). The revisions and their
videos live with the other reference history in the archive; hosting the frame and submitting follow the workflow doc.
The clips themselves are authored in rider.py; the videos are only for timing, contacts and weight.
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

APPEARANCE = (
    "A small stylised boy with big spiky black hair, a yellow T-shirt over white long sleeves, baggy olive cargo trousers "
    "and black-and-white sneakers, and a teal Japanese mamachari city bicycle with a low step-through frame, cream "
    "mudguards, a wicker front basket, a chrome bell on the right handlebar, a rear rack with a navy skateboard strapped "
    "to it and a sunburst chain guard. Keep his proportions, clothes and the bicycle exactly as in the starting image; "
    "plain light grey studio floor and backdrop, soft daylight. CONSTANT FRAMING: the camera never zooms, pushes in, pans "
    "or reframes; the boy and the bicycle stay the same size on screen from the first frame to the last, exactly as in "
    "the starting image. REAL-TIME SPEED: the whole clip plays at normal speed, no slow motion, no time stretching; each "
    "action takes the time it would take in real life and the boy simply holds still afterwards. ")

ACTIONS = {
    'mount': ('start_beside.png',
              "He stands on the bicycle's left side, left hand on the left grip, right hand on the saddle, the bicycle upright "
              "on its stand. 0-0.6s he shifts his weight onto his left foot and lifts his right knee; 0.6-1.2s he swings his "
              "right leg forward and over the LOW step-through part of the frame (not over the saddle or the rack), his right "
              "hand moving from the saddle to the right grip; 1.2-1.6s he stands astride the bicycle with both feet on the floor "
              "and both hands on the grips; 1.6-2.2s he sits down on the saddle and puts his right foot on the right pedal; "
              "2.2-3s he pushes off with the left foot and starts pedalling slowly; 3-6s he rides gently forward toward the "
              "lower right, upright posture, pedalling smoothly. Contacts: two feet on the floor until he sits; then one foot "
              "on a pedal and one pushing off; then both feet on the pedals. Not: a leg swung over the saddle or the rear, a "
              "jump onto the seat, a running mount, the bicycle falling over, extra riders. Success: one leg swing through the "
              "low frame, a seated push-off, smooth pedalling with both hands on the grips."),
    'bunny-hop': ('start_riding.png',
                  "He rides toward the lower right at an easy speed, seated, both hands on the grips. 0-1s he pedals; 1-1.4s he "
                  "stands up on level pedals and crouches low over the bicycle; 1.4-1.7s he springs up and pulls the handlebars "
                  "up so the front wheel lifts first, then both wheels leave the floor; 1.7-2.0s the bicycle is airborne about "
                  "a hand's height off the floor, level; 2.0-2.2s both wheels land together and he absorbs the landing by "
                  "bending his knees and elbows; 2.2-3s he sits back down and keeps riding; 3-6s he pedals on smoothly. "
                  "Contacts: hands never leave the grips and feet never leave the pedals. Exactly one hop and one landing. "
                  "Not: a wheelie ride, a backflip, a jump off the bicycle, a crash, a ramp. Success: one crouch, front wheel "
                  "up first, both wheels airborne once, one two-wheel landing, riding on."),
    'skid-stop': ('start_riding.png',
                  "He rides toward the lower right at a brisk speed, seated, both hands on the grips. 0-1s he pedals; 1-1.3s "
                  "he stops pedalling with the pedals level and leans his weight back; 1.3-2.4s the rear wheel locks and "
                  "slides out sideways so the bicycle skids and swings about a quarter turn, the rear tyre scuffing the floor; "
                  "around 2.0s his left foot comes off the pedal and touches down on the floor beside the bicycle; 2.4s the "
                  "bicycle stops, leaning slightly toward his planted left foot; 2.4-6s he stays seated, balanced on his left "
                  "foot with the bicycle leaning a little left, both hands on the grips, looking around calmly. Contacts: one "
                  "foot down on the left, the right foot stays on its pedal. Not: falling over, a jump, both feet down, "
                  "getting off the bicycle, a full spin. Success: a sliding rear wheel, about a quarter turn, one foot down, "
                  "a balanced stop."),
    'coast-wave': ('start_riding.png',
                   "He rides toward the lower right at an easy speed, seated. 0-1s he pedals; 1-1.3s he stops pedalling and "
                   "coasts with the pedals level, the bicycle rolling straight on; 1.3-1.6s he lifts his LEFT hand off the grip "
                   "and raises it above his shoulder, keeping his right hand on the right grip; 1.6-3.2s he waves the left hand "
                   "side to side in a friendly wave while turning his head toward the camera with a smile; 3.2-3.6s he puts "
                   "the left hand back on the left grip and looks ahead; 3.6-6s he pedals on smoothly. Contacts: the right hand "
                   "never leaves its grip; both feet stay on the pedals. Not: both hands off, standing up, stopping, swerving. "
                   "Success: one left-hand wave while coasting in a straight line, then both hands back on the grips."),
    'crash': ('start_riding.png',
              "He rides toward the lower right at a brisk speed, seated. 0-0.8s he pedals; 0.8-1.0s the front wheel stops "
              "abruptly as if it hit a kerb; 1.0-1.4s the rear of the bicycle kicks up and he is thrown forward over the "
              "handlebars, arms reaching forward; 1.4-1.8s he lands on his feet in front of the bicycle and stumbles forward "
              "three quick steps, arms windmilling for balance; 1.8-2.6s he catches himself with his hands on his knees, "
              "unhurt; 2.6-3.4s he straightens up and turns to look back; meanwhile the bicycle tips over onto its side behind "
              "him and comes to rest; 3.4-6s he stands upright looking back at the fallen bicycle, scratching his head. "
              "Contacts: he leaves the pedals at about 1.0s and lands feet first; he never lies on the floor or rolls. Not: "
              "an injury, blood, a somersault landing on his back, the bicycle flying away, a second crash. Success: one "
              "pitch over the bars, a feet-first stumble of about three steps, the bicycle on its side, the boy standing."),
}


def main(frames, out):
    frames, out = Path(frames), Path(out)
    for slug, (frame, action) in ACTIONS.items():
        rev = out / f'{slug}-r01'; inputs = rev / 'inputs'; inputs.mkdir(parents=True, exist_ok=True)
        if (rev / 'job.json').exists(): continue   # submitted revisions stay as they are
        shutil.copyfile(frames / frame, inputs / 'starting-frame.png')
        digest = hashlib.sha256((inputs / 'starting-frame.png').read_bytes()).hexdigest()
        (rev / 'prompt.txt').write_text(APPEARANCE + action + '\n')
        (inputs / 'inputs.json').write_text(json.dumps({
            'source': 'games/yorimichi/assets/vehicles/bike/rider.py --frames', 'starting_frame': frame,
            'image_sha256': digest,
            'method': 'Cairo on the approved rig (Cairo-Game-r18, sha checked by export_unreal.prepare) posed by rider.py at the '
                      'first frame of BikeMount (beside) or BikeRide (riding), with the approved bike model; Blender Eevee 768 px, '
                      'no generative editing'}, indent=2) + '\n')
        (rev / '.gitignore').write_text('api-private/\n*.part\nanalysis-frames/\n')
        print('prepared', rev.name, digest[:12])


if __name__ == '__main__':
    main(*sys.argv[1:3])
