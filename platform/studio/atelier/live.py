"""Talk to a running game through its live bridge (loopback HTTP), selected by its live session.

    atelier live state                    # player, camera, aim point, live props
    atelier live py "unreal.LiveLibrary.say('hello', 4.0)"   # run Python in the game (shared namespace; `unreal`
                                          # ready, and the game's helper module as `live` when it has one)
    atelier live py - < script.py         # ... from stdin
    atelier live shot [out.png]           # screenshot of the game view (waits for the file)
    atelier live sessions [--prune]       # this machine's session records; --prune removes those whose launcher is gone

Which game: `atelier play` records each game it starts (a session; see `atelier.live_sessions`). With no option, the one
live session launched from this checkout; otherwise pass, before the command:

    --session ID     that session (an ID or a unique prefix; also ATELIER_LIVE_SESSION)
    --game GAME      the one live session of that game (also ATELIER_LIVE_GAME)
    --checkout PATH  sessions launched from another checkout instead of this one
    --port N         a game without a session record on loopback port N, unverified (explicit legacy use)

The bridge's identity is checked against the record before any command; a mismatch, a stale record or several
candidates is an error, never a fallback to another game. Exit code 1 when there is no verified target, the game is
unreachable or the Python raised.
"""
import argparse, base64, json, os, sys, time, urllib.request
from pathlib import Path

from . import live_sessions
from .live_sessions import SessionError
from .paths import build_root

URL = None        # an explicit target ('http://127.0.0.1:N'), set by a script that launched its own game; else selection
_selected = None  # (url, record or None) once selected and verified in this process


def python_body(code):
    """The /python body that runs `code` as it is. The bridge hands a body to Unreal's ExecuteFile, which takes a
    first token ending in .py for a script to open (a module docstring that names one ran as a missing file): the code
    goes as data instead, decoded and executed in the shared namespace, its tracebacks naming <atelier live>."""
    data = base64.b64encode(code.encode()).decode()
    return f"import base64 as _live_b64\nexec(compile(_live_b64.b64decode('{data}').decode(), '<atelier live>', 'exec'))\n"


def select(session=None, game=None, checkout=None, port=None):
    """Choose and verify this process's target; returns its URL. `port` alone is an explicit, unverified legacy target
    unless a session record owns that port, which is then verified like any other."""
    global _selected
    if port is not None:
        if session:
            raise SessionError('pass --session or --port, not both')
        owned = [r for r in live_sessions.records() if r.get('port') == port
                 and live_sessions.launcher_state(r) != 'gone']
        if owned:
            record = owned[0]
            if record.get('checkout_id') != live_sessions.checkout_id(checkout) or (game and record.get('game') != game):
                raise SessionError(f'loopback port {port} belongs to session {record["session"]} '
                                   f'({record.get("game")} from {record.get("checkout")}), not to this selection')
            live_sessions.verify(record)
            _selected = (f'http://127.0.0.1:{port}', record)
        else:
            _selected = (f'http://127.0.0.1:{port}', None)
        return _selected[0]
    record = live_sessions.select(session, game, checkout)
    live_sessions.verify(record)
    _selected = (f'http://127.0.0.1:{record["port"]}', record)
    return _selected[0]


def target():
    """The URL requests go to: an explicit URL, else the selection made in this process, else the selection the
    environment names (ATELIER_LIVE_SESSION / _GAME / _CHECKOUT / _PORT, as `atelier qa` passes them)."""
    if URL:
        return URL
    if _selected is None:
        port = os.environ.get('ATELIER_LIVE_PORT')
        select(os.environ.get('ATELIER_LIVE_SESSION') or None, os.environ.get('ATELIER_LIVE_GAME') or None,
               os.environ.get('ATELIER_LIVE_CHECKOUT') or None, int(port) if port else None)
    return _selected[0]


def request(path, body=None, timeout=120):
    if path == '/python' and body is not None:
        body = python_body(body)
    data = body.encode() if body is not None else None
    req = urllib.request.Request(target() + path, data=data, method='POST' if body is not None else 'GET')
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def free_port():
    """A loopback port nothing listens on now, for a game started with -liveport=N beside another game."""
    return live_sessions.free_port()


def run(code):
    out = request('/python', code)
    if out.get('output', '').strip(): print(out['output'].rstrip())
    if not out.get('ok'):
        print(out.get('result', ''), file=sys.stderr)
        return False
    return True


def sessions(prune=False):
    """Print this machine's session records with the state of each launcher and bridge."""
    if prune:
        for record in live_sessions.prune():
            print(f'removed {record["session"]} ({record.get("game")}, port {record.get("port")}): launcher gone')
    here = live_sessions.checkout_id()
    found = live_sessions.load_all()
    if not found:
        print('no live sessions')
    for record, problem in found:
        if record is None:
            print(f'invalid record {problem}'); continue
        state = live_sessions.launcher_state(record)
        if state == 'live':
            try:
                live_sessions.verify(record, timeout=.5); state = 'ready'
            except SessionError as error:
                state = 'starting or unverified: ' + str(error).split(': ', 1)[-1]
        elif state == 'gone':
            state = 'stale (launcher gone)'
        where = 'this checkout' if record.get('checkout_id') == here else record.get('checkout')
        print(f'{record["session"]}  {record.get("game")}  port {record.get("port")}  {record.get("agent") or "-"}  '
              f'{where}  {str(record.get("revision", ""))[:10]}  {state}')
    return 0


def parse(argv):
    parser = argparse.ArgumentParser(prog='atelier live', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--session', default=os.environ.get('ATELIER_LIVE_SESSION') or None)
    parser.add_argument('--game', default=os.environ.get('ATELIER_LIVE_GAME') or None)
    parser.add_argument('--checkout', default=os.environ.get('ATELIER_LIVE_CHECKOUT') or None)
    parser.add_argument('--port', type=int, default=None)
    parser.add_argument('--prune', action='store_true', help='sessions: remove records whose launcher is gone')
    parser.add_argument('command', choices=['state', 'py', 'shot', 'sessions'])
    parser.add_argument('rest', nargs=argparse.REMAINDER)
    return parser.parse_args(argv)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv: print(__doc__); return 2
    args = parse(argv)
    if args.command == 'sessions':
        return sessions(args.prune or '--prune' in args.rest)
    try:
        select(args.session, args.game, args.checkout, args.port)
        if args.command == 'state':
            print(json.dumps(request('/state'), indent=1)); return 0
        if args.command == 'py':
            code = sys.stdin.read() if not args.rest or args.rest[0] == '-' else args.rest[0]
            return 0 if run(code) else 1
        if args.command == 'shot':
            path = Path(args.rest[0]).resolve() if args.rest else build_root() / 'live' / 'shots' / (time.strftime('%Y%m%d_%H%M%S') + '.png')
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists(): path.unlink()
            if not run(f'import unreal\nunreal.LiveLibrary.screenshot(r"{path}")'): return 1   # the generic verb: any game
            for _ in range(100):
                if path.exists() and path.stat().st_size > 0:
                    time.sleep(.2); print(path); return 0
                time.sleep(.1)
            print('screenshot not written (is the game window minimised?)', file=sys.stderr); return 1
    except SessionError as error:
        print(f'live: {error}', file=sys.stderr); return 1
    except OSError as error:
        print(f'live bridge unreachable at {target_text()}: {error}', file=sys.stderr); return 1
    return 2


def target_text():
    return URL or (_selected[0] if _selected else 'no selected session')


if __name__ == '__main__':
    sys.exit(main())
