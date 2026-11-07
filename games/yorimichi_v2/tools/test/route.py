"""Play the slice's walk/skate route in the running slice game and check it (plan P3: the slice plays).

    uv run atelier play yorimichi_v2 --profile slice -- -RenderOffscreen      # first, and wait for the world
    uv run python games/yorimichi_v2/tools/test/route.py --session ID --out build/yorimichi_v2/route

Through the game's live bridge (YorimichiLive.Drive, SkateToggle, SkatePlace, SkateInput) Cairo walks 5 s down the
village road from start_road, then rides the skate pier from its park spawn: 4 s pushing, 1 s coasting. route_game.py
plays the steps on game frames and samples the player every 0.5 s into OUT/route.jsonl; this script then writes
OUT/report.json and exits 0 only when every check holds:

  walk   every sample walks on the ground (MOVE_WALKING); Cairo covers >= 12 m at >= 2.5 m/s
  skate  every sample rides the board (board=ride); top speed >= 6 m/s; the deck height varies < 0.5 m
  frame  no walking or skating sample under 20 fps (the teleports' streaming frames are not play). The game samples
         one frame every 0.5 s, so this is the lowest sampled fps, not the minimum over every frame

The report records the live session and the checkout's revision, so a later run cannot pass as this one.

It saves nothing and leaves Cairo on foot at the end of the pier run.
"""
import argparse
import json
import math
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(HERE))
from launch import launch_revision, revision  # noqa: E402
WALK_MIN_M, WALK_MIN_SPEED, SKATE_MIN_SPEED, SKATE_MAX_DZ, MIN_FPS = 12, 250, 600, 50, 20


def phase(rows, name):
    return [r for r in rows if r['phase'] == name]


def evaluate(rows):
    """The failed checks of a recorded route, and its measurements."""
    failures, walk, skate = [], phase(rows, 'walk'), phase(rows, 'skate') + phase(rows, 'skate_coast')
    measured = {}
    if len(walk) < 4:
        failures.append(f'walk: {len(walk)} samples')
    else:
        moving = walk[1:]   # the first sample is taken as the drive starts
        metres = math.hypot(walk[-1]['x'] - walk[0]['x'], walk[-1]['y'] - walk[0]['y']) / 100
        speed = min(r['speed'] for r in moving)
        measured.update(walk_m=round(metres, 1), walk_min_speed=speed)
        if any(r['movement_mode'] != 'MOVE_WALKING' for r in walk):
            failures.append(f'walk: not walking on the ground ({sorted({r["movement_mode"] for r in walk})})')
        if metres < WALK_MIN_M or speed < WALK_MIN_SPEED:
            failures.append(f'walk: {metres:.1f} m at >= {speed:.0f} cm/s (needs {WALK_MIN_M} m at {WALK_MIN_SPEED})')
    if len(skate) < 4:
        failures.append(f'skate: {len(skate)} samples')
    else:
        top = max(r['speed'] for r in skate)
        dz = max(r['z'] for r in skate) - min(r['z'] for r in skate)
        measured.update(skate_top_speed=top, skate_dz=round(dz, 1),
                        skate_m=round(math.hypot(skate[-1]['x'] - skate[0]['x'], skate[-1]['y'] - skate[0]['y']) / 100, 1))
        if any(r['board'] != 'ride' for r in skate):
            failures.append(f'skate: not riding the board ({sorted({str(r["board"]) for r in skate})})')
        if top < SKATE_MIN_SPEED:
            failures.append(f'skate: top speed {top:.0f} cm/s < {SKATE_MIN_SPEED}')
        if dz >= SKATE_MAX_DZ:
            failures.append(f'skate: the rider height varies {dz:.0f} cm on a flat deck')
    played = walk + skate   # the teleports' frames stream a new area in and are no play
    if played:
        measured['min_sampled_fps'] = min(r['fps'] for r in played)   # one frame every 0.5 s
        measured['sampled_frames'] = len(played)
        if measured['min_sampled_fps'] < MIN_FPS:
            failures.append(f'frame: a sampled frame at {measured["min_sampled_fps"]} fps < {MIN_FPS}')
    return failures, measured


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--session', required=True, help='live session ID of the running slice game')
    parser.add_argument('--out', type=Path, required=True, help='folder for route.jsonl and report.json')
    parser.add_argument('--timeout', type=float, default=90, help='seconds to wait for the route to finish')
    args = parser.parse_args(argv)
    out = args.out.resolve()
    for stale in ('route.jsonl', 'done.json', 'report.json'):
        (out / stale).unlink(missing_ok=True)
    try:
        launched = launch_revision(args.session, REPO)
        revision(REPO, launched, 'session')  # refuse a moved checkout before driving the game
    except (OSError, ValueError, RuntimeError) as error:
        print(f'cannot bind the route to its game: {error}', file=sys.stderr)
        return 2
    code = f'PARAMS = {json.dumps({"out": str(out)})}\n' + (HERE / 'route_game.py').read_text()
    result = subprocess.run(['uv', 'run', 'atelier', 'live', '--session', args.session, 'py', '-'], cwd=REPO,
                            input=code, text=True)
    if result.returncode:
        print('the route could not start: is the slice game running with that live session?', file=sys.stderr)
        return 1
    deadline = time.monotonic() + args.timeout
    while not (out / 'done.json').is_file():
        if time.monotonic() > deadline:
            print(f'the route did not finish in {args.timeout:.0f} s', file=sys.stderr)
            return 1
        time.sleep(1)
    done = json.loads((out / 'done.json').read_text())
    rows = [json.loads(line) for line in (out / 'route.jsonl').read_text().splitlines() if line]
    failures, measured = evaluate(rows)
    if 'error' in done:
        failures.insert(0, f'game: {done["error"]}')
    try:
        rev = revision(REPO, launched, 'session')
    except ValueError as error:
        failures.insert(0, str(error))
        rev = None
    report = {'schema': 1, 'passed': not failures, 'failures': failures, 'measured': measured, 'samples': len(rows),
              'session': args.session, 'revision': rev}
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(measured))
    for failure in failures:
        print(f'  FAIL {failure}')
    print('ROUTE PASSED' if not failures else 'ROUTE FAILED', out / 'report.json')
    return 0 if not failures else 1


if __name__ == '__main__':
    sys.exit(main())
