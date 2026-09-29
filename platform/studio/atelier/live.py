"""Talk to a running game through the live bridge (the game's HTTP bridge on localhost:8830).

    atelier live state                    # player, camera, aim point, live props
    atelier live py "live.say('hello')"   # run Python in the game (shared namespace; `live`, `unreal` ready)
    atelier live py - < script.py         # ... from stdin
    atelier live shot [out.png]           # screenshot of the game view (waits for the file)

Exit code 1 when the game is unreachable or the Python raised.
"""
import json, sys, time, urllib.request
from pathlib import Path

from .paths import build_root

URL = 'http://127.0.0.1:8830'


def request(path, body=None, timeout=120):
    data = body.encode() if body is not None else None
    req = urllib.request.Request(URL + path, data=data, method='POST' if body is not None else 'GET')
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def run(code):
    out = request('/python', code)
    if out.get('output', '').strip(): print(out['output'].rstrip())
    if not out.get('ok'):
        print(out.get('result', ''), file=sys.stderr)
        return False
    return True


def main(argv=None):
    argv = ["live", *argv] if argv is not None else sys.argv
    if len(argv) < 2: print(__doc__); return 2
    cmd = argv[1]
    try:
        if cmd == 'state':
            print(json.dumps(request('/state'), indent=1)); return 0
        if cmd == 'py':
            code = sys.stdin.read() if len(argv) < 3 or argv[2] == '-' else argv[2]
            return 0 if run(code) else 1
        if cmd == 'shot':
            path = Path(argv[2]).resolve() if len(argv) > 2 else build_root() / 'live' / 'shots' / (time.strftime('%Y%m%d_%H%M%S') + '.png')
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists(): path.unlink()
            if not run(f'live.shot(r"{path}")'): return 1
            for _ in range(100):
                if path.exists() and path.stat().st_size > 0:
                    time.sleep(.2); print(path); return 0
                time.sleep(.1)
            print('screenshot not written (is the game window minimised?)', file=sys.stderr); return 1
    except OSError as error:
        print(f'live bridge unreachable at {URL}: {error}', file=sys.stderr); return 1
    print(__doc__); return 2


if __name__ == '__main__':
    sys.exit(main())
