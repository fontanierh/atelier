"""Capture one bounded Pier batch in this checkout's running game, then quit.

    uv run python games/yorimichi/tools/pier_film.py --take street-01 --batch street

Start the game under `atelier play` first. This refuses another checkout's
render owner before contacting the bridge. Failed takes retain their complete
evidence; use a new take name for every attempt.
"""
import argparse
import json
from pathlib import Path
import sys
import time

from atelier import live
from atelier.safety.render_lock import lock_path

GAME=Path(__file__).resolve().parents[1]
ROOT=GAME.parents[1]
sys.path.insert(0,str(GAME/'world'))
import yori  # noqa: E402
sys.path.insert(0,str(GAME/'scenarios'))
from pier_part_check import assess  # noqa: E402

BATCHES={'street':['arrival','promenade','granite'],
         'detail':['rail_line','manuals'],
         'transition':['bowl','east_air','mini']}
DURATIONS={'promenade':10,'granite':6,'bowl':8,'east_air':8}


def game_owner():
    try: owner=json.loads(lock_path().read_text())
    except (OSError,ValueError): return None
    if not owner.get('checkout') or Path(owner['checkout']).resolve()!=ROOT: return None
    return owner if owner.get('pid') else None


def owns_game(expected):
    owner=game_owner()
    return owner and (owner.get('pid'),owner.get('started'))==expected


def execute(code):
    response=live.request('/python',code)
    if not response.get('ok'):
        raise RuntimeError(response.get('result','')+response.get('output',''))
    return response.get('output','')


def capture(args, shots=None):
    owner=game_owner()
    if not owner: raise RuntimeError('Start this checkout with atelier play; its game must own the render slot')
    expected=(owner.get('pid'),owner.get('started'))
    if Path(execute('print(live.ROOT)').strip()).resolve()!=ROOT:
        raise RuntimeError('The live bridge belongs to another checkout')
    out=yori.OUT/'skatefilm'/args.take
    if out.exists(): raise RuntimeError('Use a fresh take name; earlier evidence is preserved')
    try:
        deadline=time.monotonic()+args.timeout
        execute((GAME/'scenarios/skate_live_skate.py').read_text())
        execute('live.skate_park();live.skate_input()')
        ready=time.monotonic()+30
        while 'simulation=PhysicsGround' not in execute('print(live.skate_state())'):
            if not owns_game(expected): raise RuntimeError('The game released during skater preparation')
            if time.monotonic()>min(ready,deadline): raise TimeoutError('Skater failed to become ready')
            time.sleep(.5)
        # ExecuteFile interprets a leading settings line followed by a script docstring
        # as a filename; set globals separately, then send the unmodified script.
        execute('TAKE='+repr(args.take)+';FILM='+repr(not args.rehearse)+
                ';ONLY='+repr(None if shots else BATCHES[args.batch])+
                ';SHOTS_OVERRIDE='+repr(shots)+';DURATIONS='+repr(DURATIONS))
        print(execute((GAME/'scenarios/pier_part.py').read_text()),flush=True)
        while not (out/'done.json').exists():
            if not owns_game(expected): raise RuntimeError('The game released before this take completed')
            if time.monotonic()>deadline: raise TimeoutError('Capture exceeded its bounded time; evidence retained')
            time.sleep(.5)
        if not args.rehearse:
            done=json.loads((out/'done.json').read_text())
            # A viewport screenshot may still be saving when the final behaviour
            # tick writes done.json. Keep the owned game alive for that last PNG.
            while len(list(out.glob('frame_*.png')))<done['film_frames']:
                if not owns_game(expected): raise RuntimeError('The game released before its last frame saved')
                if time.monotonic()>deadline: raise TimeoutError('Final frame did not save before the capture deadline')
                time.sleep(.1)
        report=assess(out)
        print(json.dumps(report,indent=2),flush=True)
        return 0 if report['ok'] else 1
    finally:
        if owns_game(expected):
            if args.keep_game:
                execute("live.stop('pier_part');live.skate_release();live.L.fixed_step(0)")
            else:
                execute('unreal.SystemLibrary.quit_game(live.L.game_world(),None,unreal.QuitPreference.QUIT,False)')


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--take',required=True)
    ap.add_argument('--batch',choices=BATCHES,required=True)
    ap.add_argument('--rehearse',action='store_true')
    ap.add_argument('--keep-game',action='store_true')
    ap.add_argument('--timeout',type=float,default=300)
    args=ap.parse_args()
    if not args.take or args.take in ('.','..') or Path(args.take).name!=args.take:
        ap.error('--take must be a folder name')
    if args.timeout<=0: ap.error('--timeout must be positive')
    raise SystemExit(capture(args))
