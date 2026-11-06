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
    --port N         a game without a session record on loopback port N, unverified (explicit legacy use);
                     a port a record owns is verified as that session

The bridge's identity is checked against the record before every request; a mismatch, a stale record or several
candidates is an error, never a fallback to another game.

Scripts: `atelier qa` names the game (and `--session ID`) in the environment, and requests select from it. A scenario's
own `--port N` goes through `use_port(N)` (None: the session route); a script that launched its own game may set `URL`.
Either explicit port is checked like `--port`, and refused when the environment names a session on another port.

Exit code 1 when there is no verified target, the game is unreachable or the Python raised.
"""
import argparse, base64, json, os, sys, time, urllib.parse, urllib.request
from pathlib import Path

from . import live_sessions
from .live_sessions import SessionError
from .paths import build_root

URL = None        # an explicit loopback target ('http://127.0.0.1:N'), set by a script that launched its own game
PORT = None       # an explicit loopback port, set by use_port (a scenario's --port N)
_selected = None  # (url, record or None, its verified identity, the (URL, PORT) it was chosen for, fresh)


def python_body(code):
    """The /python body that runs `code` as it is. The bridge hands a body to Unreal's ExecuteFile, which takes a
    first token ending in .py for a script to open (a module docstring that names one ran as a missing file): the code
    goes as data instead, decoded and executed in the shared namespace, its tracebacks naming <atelier live>."""
    data = base64.b64encode(code.encode()).decode()
    return f"import base64 as _live_b64\nexec(compile(_live_b64.b64decode('{data}').decode(), '<atelier live>', 'exec'))\n"


def _owner(port):
    """The record whose launcher may still run and which owns loopback `port`, or None."""
    return next((r for r in live_sessions.records() if r.get('port') == port
                 and live_sessions.launcher_state(r) != 'gone'), None)


def select(session=None, game=None, checkout=None, port=None):
    """Choose and verify this process's target; returns its URL. `port` alone is an explicit, unverified legacy target
    unless a session record owns that port, which is then verified like any other. With both, `port` must be that
    session's own port: an explicit port never overrides a selected session."""
    global _selected
    if port is not None and not session:
        record = _owner(port)
        if record is not None and (record.get('checkout_id') != live_sessions.checkout_id(checkout)
                                   or (game and record.get('game') != game)):
            raise SessionError(f'loopback port {port} belongs to session {record["session"]} '
                               f'({record.get("game")} from {record.get("checkout")}), not to this selection')
    else:
        record = live_sessions.select(session, game, checkout)
        if port is not None and port != record['port']:
            raise SessionError(f'port {port} is not the port of session {record["session"]} ({record["port"]}): '
                               'pass the session or the port, not both')
    found = live_sessions.verify(record) if record is not None else None
    url = f'http://127.0.0.1:{record["port"] if record is not None else port}'
    _selected = (url, record, found, (URL, PORT), True)
    return url


def use_port(port):
    """A scenario's `--port`: N targets loopback port N explicitly, as `atelier live --port N` does (verified when a
    record owns it, refused when the environment names a session on another port); None leaves the target to session
    selection. Takes effect at the next request."""
    global PORT
    PORT = None if port is None else int(port)


def _explicit_port():
    if PORT is not None:
        return PORT
    if URL:
        parts = urllib.parse.urlsplit(URL)
        if parts.scheme != 'http' or parts.hostname not in ('127.0.0.1', 'localhost') or not parts.port:
            raise SessionError(f'live.URL {URL!r} is not a loopback bridge URL (http://127.0.0.1:N)')
        return parts.port
    port = os.environ.get('ATELIER_LIVE_PORT')
    return int(port) if port else None


def target():
    """The URL the next request goes to, verified for that request. The selection is made once (an explicit URL or
    use_port, else this process's select, else the one the environment names: ATELIER_LIVE_SESSION / _GAME / _CHECKOUT /
    _PORT, as `atelier qa` passes them) and made again when URL or PORT changes. Before every later request the selected
    record is verified again; an unrecorded port is checked again for a record that now owns it."""
    global _selected
    if _selected is None or _selected[3] != (URL, PORT):
        env = os.environ.get
        select(env('ATELIER_LIVE_SESSION') or None, env('ATELIER_LIVE_GAME') or None,
               env('ATELIER_LIVE_CHECKOUT') or None, _explicit_port())
    url, record, found, key, fresh = _selected
    if fresh:   # verified by select just now
        _selected = (url, record, found, key, False)
    elif record is not None:
        _selected = (url, record, live_sessions.verify(record, verified=found), key, False)
    elif _owner(urllib.parse.urlsplit(url).port) is not None:   # a game with a record took the unrecorded port
        env = os.environ.get
        select(env('ATELIER_LIVE_SESSION') or None, env('ATELIER_LIVE_GAME') or None,
               env('ATELIER_LIVE_CHECKOUT') or None, urllib.parse.urlsplit(url).port)
        _selected = _selected[:4] + (False,)
    return url


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
    return _selected[0] if _selected else (URL or 'no selected session')


if __name__ == '__main__':
    sys.exit(main())
