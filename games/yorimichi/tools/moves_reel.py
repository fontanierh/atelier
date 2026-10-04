"""Film the merged move set (scenarios/botw_moves_film.py) in this checkout's running game, then quit it.

    nice -n 10 uv run atelier play yorimichi -- -nobotw -rider=CairoBotw -nofox -nosound -liveport=8851 \\
        "-ini:Engine:[HTTPServer.Listeners]:DefaultBindAddress=localhost" -ForceDPCVars=r.Streaming.PoolSize=200 \\
        -RenderOffscreen -ForceRes
    uv run python games/yorimichi/tools/moves_reel.py --take cairo-reel --who Cairo --port 8851
    ... and Link in his own game (-rider=Link), then:
    uv run python games/yorimichi/scenarios/botw_moves_film_cut.py --audio build/yorimichi/botw/moves_film/reel.mp4 \\
        cairo-reel link-reel

The reel's sections by default: the sprint, the double jump, the dodges, the sword, the sword guard without the shield,
the shield, and the paraglider (--sections names others, as botw_moves_film.py's SECTIONS do). A -liveport other than
8830 needs the loopback binding above, or the bridge refuses to start. The game must be this checkout's and hold the
render slot; the film keeps the "Shield" setting as it found it. A take that fails keeps its
evidence; use a new take name for every attempt.
"""
import argparse
import json
from pathlib import Path
import time

from atelier import live
from atelier.safety.render_lock import lock_path

GAME = Path(__file__).resolve().parents[1]
ROOT = GAME.parents[1]
REEL = ['Sprint', 'Double jump', 'Lock-on and dodges', 'Sword', 'Sword guard', 'Shield', 'Paraglider']


def game_owner():
    try:
        owner = json.loads(lock_path().read_text())
    except (OSError, ValueError):
        return None
    if not owner.get('checkout') or Path(owner['checkout']).resolve() != ROOT:
        return None
    return owner if owner.get('pid') else None


def execute(code):
    response = live.request('/python', code)
    if not response.get('ok'):
        raise RuntimeError(response.get('result', '') + response.get('output', ''))
    return response.get('output', '')


def film(args):
    live.URL = f'http://127.0.0.1:{args.port}'
    owner = game_owner()
    if not owner:
        raise RuntimeError('Start this checkout with atelier play; its game must own the render slot')
    expected = (owner.get('pid'), owner.get('started'))
    owns = lambda: (o := game_owner()) is not None and (o.get('pid'), o.get('started')) == expected
    deadline = time.monotonic() + args.timeout
    started, said = time.monotonic(), [0.]

    def status(text):
        """A progress line at most every 30 s while waiting (stage, what is observed, what is awaited)."""
        if time.monotonic() - said[0] >= 30.:
            said[0] = time.monotonic()
            print(f'[{time.monotonic() - started:5.0f} s] {text}', flush=True)
    # The bridge answers once the world is up; the move set once the player has spawned with it.
    while True:
        try:
            if Path(execute('print(live.ROOT)').strip()).resolve() != ROOT:
                raise RuntimeError('The live bridge on this port belongs to another checkout')
            state = json.loads(execute('print(live.L.move_state())').strip() or '{}')
            if state.get('mode') == 'ground':
                break
            if state.get('mode') == 'swim':   # left in the lake (botw_moves.py's glide ends there): back to its shore
                execute('live.L.teleport_player(unreal.Vector(-5400., -22300., 7500.), 0.)')
        except OSError:
            pass
        if not owns() or time.monotonic() > deadline:
            raise TimeoutError('The game did not come up with a move set')
        status('waiting for the game: bridge up and the player standing with a move set (no progress yet)')
        time.sleep(2.)
    out = ROOT / 'build/yorimichi/botw/moves_film' / args.take
    if out.exists() and any(out.iterdir()):
        raise RuntimeError(f'{out} exists: use a fresh take name; earlier evidence is preserved')
    try:
        for command in args.console:
            execute(f'unreal.SystemLibrary.execute_console_command(live.L.game_world(), {command!r})')
        time.sleep(3.)   # streaming settles after the resolution changes
        execute(f'TAKE={args.take!r}; WHO={args.who!r}; ONLY={args.sections or REEL!r}; REHEARSE=False')
        print(execute((GAME / 'scenarios/botw_moves_film.py').read_text()), flush=True)
        while not (out / 'done.json').exists():
            if not owns():
                raise RuntimeError('The game released before the take completed')
            if time.monotonic() > deadline:
                raise TimeoutError('The take exceeded its time; evidence retained')
            status(f'filming {args.take}: {len(list(out.glob("frame_*.jpg")))} frames saved, waiting for done.json')
            time.sleep(1.)
        done = json.loads((out / 'done.json').read_text())
        while len(list(out.glob('frame_*.jpg'))) < done['film_frames'] and time.monotonic() < deadline:
            time.sleep(.2)
        print(json.dumps({'take': args.take, 'film_frames': done['film_frames'], 'seconds': round(done['film_frames'] / 30., 1),
                          'errors': [e['section'] for e in done['errors']]}, indent=1), flush=True)
        return 0 if not done['errors'] else 1
    finally:
        if owns() and not args.keep_game:
            execute('unreal.SystemLibrary.quit_game(live.L.game_world(),None,unreal.QuitPreference.QUIT,False)')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--take', required=True)
    ap.add_argument('--who', required=True, help="the name on the captions: 'Cairo' or 'Link'")
    ap.add_argument('--port', type=int, default=8830, help='the game\'s -liveport')
    ap.add_argument('--sections', nargs='*', help=f'the film sections (default: {", ".join(REEL)})')
    ap.add_argument('--console', nargs='*', default=[], help='console commands before filming (resolution, streaming)')
    ap.add_argument('--keep-game', action='store_true')
    ap.add_argument('--timeout', type=float, default=1800.)
    args = ap.parse_args()
    if Path(args.take).name != args.take or args.take in ('', '.', '..'):
        ap.error('--take must be a folder name')
    raise SystemExit(film(args))
