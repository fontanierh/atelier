"""Measure the slice's plan §15 budgets: one declared warm-up, then N timed runs; median and slowest per operation.

    uv run python games/yorimichi_v2/tools/test/budgets.py OPERATION [--runs 5] --out build/yorimichi_v2/budgets

  check   the read-only content check (check.py). Target: median <= 10 s
  place   one saved actor moved 1 cm through editor.run (move_actor.py), alternately +x and -x, so an even number of
          runs ends where it began. Needs V2_EDITOR_CLAIM, V2_EDITOR_PATHS and V2_MOVE_ACTOR, as move_actor.py does.
          Target: median <= 30 s, slowest <= 60 s
  mesh    a predefined slice prop reimported from alternately the two FBX files given with --sources, under --claim;
          a run the importer skipped as unchanged fails.
          Target: median <= 3 min, slowest <= 6 min
  cpp     one C++ file (--edit) changed by a byte edit (a trailing comment naming the run), the editor module
          recompiled, then the slice played until it is playable. A run whose compile did not rebuild that file fails:
          a reused result is recorded as such, not timed as an edit. The file's bytes are restored at the end.
          Target: median <= 3 min, slowest <= 6 min
  open    the slice played from launch until it is playable. Target: median <= 90 s

Playable means the live bridge answers and the player stands on the ground, walking; the game is then quit through
the bridge. A game that has not exited 120 s after its quit request stops the series (exit 2): no further run starts
while it may still be alive. Each run's resource-queue wait (the guard's last "Waiting for capacity" report) is
recorded separately and subtracted, so the budget times the operation and not the queue. Failed runs stay in the report.

The writing operations change committed files: run them only in a scratch checkout under a claim, then discard the
changes. OUT/OPERATION.json is the receipt: the checkout's revision, every run and the verdict.
"""
import argparse
import hashlib
import json
import os
import re
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
GAME = REPO / 'games/yorimichi_v2'
sys.path.insert(0, str(HERE))
from launch import git  # noqa: E402

# operation: (median target s, slowest target s or None)
TARGETS = {'check': (10, None), 'place': (30, 60), 'mesh': (180, 360), 'cpp': (180, 360), 'open': (90, None)}
QUEUE = re.compile(r'Waiting for capacity: (\d+)')
PLAY = ['nice', '-n', '10', 'uv', 'run', 'atelier', 'play', 'yorimichi_v2', '--profile', 'slice', '--memory-gib', '16',
        '--', '-RenderOffscreen']
PLAYABLE = '''import unreal as U
p = U.LiveLibrary.player()
m = p and p.get_editor_property('character_movement')
walking = m and m.movement_mode == U.MovementMode.MOVE_WALKING and m.is_moving_on_ground()
print('V2 PLAYABLE' if walking else 'V2 LOADING')
'''
QUIT = '''import unreal as U
U.SystemLibrary.execute_console_command(U.LiveLibrary.game_world(), 'quit')
print('quit requested')
'''


class CleanupError(RuntimeError):
    """A launched game did not finish its supported quit: the series must stop."""


def summarize(operation, runs):
    """The receipt's verdict: median and slowest of the operation's own time (queue wait excluded) over the runs."""
    times = [r['operation_s'] for r in runs if r['ok']]
    median_target, slowest_target = TARGETS[operation]
    result = {'runs': len(runs), 'failed': sum(not r['ok'] for r in runs),
              'queue_s': sum(r['queue_s'] for r in runs), 'target_median_s': median_target,
              'target_slowest_s': slowest_target}
    if not times:
        return {**result, 'passed': False}
    median, slowest = round(statistics.median(times), 1), round(max(times), 1)
    passed = not result['failed'] and median <= median_target and (slowest_target is None or slowest <= slowest_target)
    return {**result, 'median_s': median, 'slowest_s': slowest, 'passed': passed}


def timed(command, env=None, log=None):
    """Run a command; (ok, wall seconds, queue seconds, output)."""
    started = time.monotonic()
    done = subprocess.run(command, cwd=REPO, env={**os.environ, **(env or {})}, capture_output=True, text=True,
                          check=False)
    wall = time.monotonic() - started
    output = done.stdout + done.stderr
    if log:
        log.write(f'$ {" ".join(command)}\n{output}\n')
    waits = QUEUE.findall(output)
    return done.returncode == 0, wall, float(waits[-1]) if waits else 0., output


def live(session, code):
    try:
        return subprocess.run(['uv', 'run', 'atelier', 'live', '--session', session, 'py', '-'], cwd=REPO, input=code,
                              capture_output=True, text=True, timeout=30, check=False).stdout
    except subprocess.TimeoutExpired:   # a game still loading may not answer yet
        return ''


def play_until_playable(log, timeout=600):
    """Launch the slice and wait until it is playable; quit it. (ok, wall seconds to playable, queue seconds)."""
    from atelier import live_sessions
    known = {r['session'] for r in live_sessions.records()}
    started = time.monotonic()
    game = subprocess.Popen(PLAY, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    output, session, ready = [], None, None
    reader = threading.Thread(target=lambda: output.extend(game.stdout), daemon=True)   # lines as the game prints
    reader.start()
    try:
        while time.monotonic() - started < timeout and game.poll() is None:
            if session is None:   # this launch's record: new since the start, for this checkout
                fresh = [r['session'] for r in live_sessions.records()
                         if r['session'] not in known and Path(r.get('checkout', '')) == REPO]
                session = fresh[0] if len(fresh) == 1 else None
            if session and 'V2 PLAYABLE' in live(session, PLAYABLE):
                ready = time.monotonic() - started
                break
            time.sleep(0.5)
    finally:
        if session and game.poll() is None:
            live(session, QUIT)   # never signal the guarded game: it quits through its own bridge
        try:
            game.wait(timeout=120)
            reader.join(timeout=10)
        except subprocess.TimeoutExpired:
            log.write(f'$ {" ".join(PLAY)}\n{"".join(output)}\n')
            raise CleanupError(f'the game (launcher pid {game.pid}, session {session}) did not quit within 120 s of '
                               'its quit request') from None
    text = ''.join(output)
    log.write(f'$ {" ".join(PLAY)}\n{text}\n')
    waits = QUEUE.findall(text)
    return ready is not None, ready or time.monotonic() - started, float(waits[-1]) if waits else 0.


def run_once(operation, index, args, log):
    extra = {}
    if operation == 'check':
        ok, wall, queue, _ = timed(['uv', 'run', 'python', str(GAME / 'tools/content/check.py')], log=log)
    elif operation == 'place':
        offset = '1 0 0' if index % 2 == 0 else '-1 0 0'
        ok, wall, queue, _ = timed(['nice', '-n', '10', 'uv', 'run', 'atelier', 'build', 'yorimichi_v2', 'editor.run'],
                                   env={'V2_EDITOR_SCRIPT': str(GAME / 'unreal/Scripts/move_actor.py'),
                                        'V2_MOVE_BY_CM': offset}, log=log)
    elif operation == 'mesh':
        source, target = args.sources[index % 2], args.target
        target.write_bytes(source.read_bytes())
        ok, wall, queue, output = timed(['nice', '-n', '10', 'uv', 'run', 'python', str(GAME / 'tools/import/run.py'),
                                         args.asset, '--claim', args.claim], log=log)
        extra['imported'] = f'imported   {args.asset}' in output   # not a skip of unchanged inputs
        ok = ok and extra['imported']
    elif operation == 'cpp':
        args.edit.write_bytes(args.original + f'// budget run {index}\n'.encode())
        extra['source_sha256'] = hashlib.sha256(args.edit.read_bytes()).hexdigest()
        ok, wall, queue, _ = timed(['nice', '-n', '10', 'uv', 'run', 'atelier', 'build', 'yorimichi_v2',
                                    'unreal.compile'], log=log)
        step_log = REPO / 'build/yorimichi_v2/logs/unreal.compile.log'   # UnrealBuildTool's actions go there
        extra['compiled'] = compiled(step_log.read_text(errors='replace') if step_log.is_file() else '', args.edit.name)
        ok = ok and extra['compiled']
        if ok:
            ok, opened, waited = play_until_playable(log)
            wall, queue = wall + opened, queue + waited
    else:
        ok, wall, queue = play_until_playable(log)
    return {'run': index, 'ok': ok, 'wall_s': round(wall, 1), 'queue_s': queue,
            'operation_s': round(max(wall - queue, 0), 1), **extra}


def compiled(output, name):
    """Did this build's compiler actually rebuild the edited file? `log` is the compile step's own log, which holds
    UnrealBuildTool's `[n/m] Compile [Apple] <name>` actions."""
    return any('Compile' in line and line.rstrip().endswith(name) for line in output.splitlines())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('operation', choices=sorted(TARGETS))
    parser.add_argument('--runs', type=int, default=5, help='timed runs after the warm-up')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--sources', type=Path, nargs=2, help='mesh: the two FBX files to alternate')
    parser.add_argument('--target', type=Path, help='mesh: the committed FBX the prop imports from')
    parser.add_argument('--asset', default='prop/lantern', help='mesh: the asset ID')
    parser.add_argument('--claim', help='mesh: the claim (task ID) authorizing the import')
    parser.add_argument('--edit', type=Path, help='cpp: the C++ file to change')
    args = parser.parse_args(argv)
    if args.operation == 'mesh' and not (args.sources and args.target and args.claim):
        parser.error('mesh needs --sources A B, --target and --claim')
    if args.operation == 'cpp' and not (args.edit and args.edit.is_file()):
        parser.error('cpp needs --edit FILE')
    args.original = args.edit.read_bytes() if args.edit else None
    args.out.mkdir(parents=True, exist_ok=True)
    runs, stopped = [], None
    with open(args.out / f'{args.operation}.log', 'w') as log:
        try:
            for index in range(args.runs + 1):
                result = run_once(args.operation, index, args, log)
                result['warm_up'] = index == 0
                print(json.dumps(result), flush=True)
                runs.append(result)
        except CleanupError as error:
            stopped = str(error)
        finally:
            if args.original is not None:
                args.edit.write_bytes(args.original)
    measured = summarize(args.operation, [r for r in runs if not r['warm_up']])
    if stopped:
        measured.update(passed=False, stopped=stopped)
    receipt = {'schema': 1, 'operation': args.operation, 'revision': git(REPO, 'rev-parse', 'HEAD').strip(),
               'measured': measured, 'all_runs': runs}
    (args.out / f'{args.operation}.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(measured))
    if stopped:
        print(f'STOPPED: {stopped}; retain {args.out} and the play logs, and quit that game before another run',
              file=sys.stderr)
        return 2
    return 0 if measured['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
