"""Capture the parity poses from a RUNNING game, donor or V2, for compare.py (plan P3.6: the donor runtime baseline).

    uv run python games/yorimichi_v2/tools/parity/capture_runtime.py --source donor-runtime \
        --checkout DONOR_CHECKOUT --live-from DONOR_CHECKOUT --out build/yorimichi_v2/parity/donor
    uv run python games/yorimichi_v2/tools/parity/capture_runtime.py --session ID --source v2 \
        --out build/yorimichi_v2/parity/v2

The donor's island scenery is spawned at run time, so its baseline must come from the running donor game; capturing
V2 the same way (a runtime viewport screenshot, not an editor scene capture) keeps both sides on one render path.
Through the game's live bridge, capture_runtime_game.py travels the player below each pose, hides it and the HUD,
views from a hidden prop at the pose (the pose FOV on the camera manager), settles, and screenshots the viewport. Then this writes the receipt
capture.json (schema, source, revision, map, size, settle time as warmup, poses and their sha256, UTC time, engine
version, render settings) that compare.py requires. The revision is the commit the game was proven to start from: its
session's launch commit (--session), or, for a game without a session record (the donor), HEAD when the process on its
live port runs this checkout and HEAD has not moved since it started. A checkout that has moved is refused. OUT must hold no PNG and no receipt yet.
"""
import argparse
import datetime
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
DEFAULT_POSES = HERE / 'poses.json'


def png_size(path: Path) -> list[int]:
    with path.open('rb') as f:
        head = f.read(24)
    if head[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError(f'{path} is not a PNG')
    return list(struct.unpack('>II', head[16:24]))


def camera_glb(path: Path) -> Path:
    """Write a one-triangle GLB: the game spawns it hidden as the capture camera's view target (LiveLibrary.SpawnModel;
    the Python API cannot spawn a CameraActor in a game world)."""
    vertices = struct.pack('<9f', 0, 0, 0, 1, 0, 0, 0, 1, 0)
    gltf = {'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{'nodes': [0]}], 'nodes': [{'mesh': 0}],
            'meshes': [{'primitives': [{'attributes': {'POSITION': 0}}]}],
            'accessors': [{'bufferView': 0, 'componentType': 5126, 'count': 3, 'type': 'VEC3',
                           'min': [0, 0, 0], 'max': [1, 1, 0]}],
            'bufferViews': [{'buffer': 0, 'byteLength': len(vertices)}], 'buffers': [{'byteLength': len(vertices)}]}
    text = json.dumps(gltf).encode()
    text += b' ' * (-len(text) % 4)
    chunks = struct.pack('<II', len(text), 0x4E4F534A) + text + struct.pack('<II', len(vertices), 0x004E4942) + vertices
    path.write_bytes(struct.pack('<III', 0x46546C67, 2, 12 + len(chunks)) + chunks)
    return path


def git(checkout: Path, *argv) -> str:
    return subprocess.run(['git', '-C', str(checkout), *argv], capture_output=True, text=True, check=True).stdout


def revision(checkout: Path, launched: str, how: str) -> dict:
    """The checkout's commit and dirty state, refused unless it is `launched`, the commit the running game was proven
    to start from (`how`: its live session record, or the process start check for a game without one)."""
    commit = git(checkout, 'rev-parse', 'HEAD').strip()
    if launched != commit:
        raise ValueError(f'the game was launched at {launched[:10] or "an unknown revision"}, but {checkout} is now at '
                         f'{commit[:10]}: relaunch the game from this checkout')
    return {'commit': commit, 'dirty': bool(git(checkout, 'status', '--porcelain').strip()), 'launch': how}


def launch_revision(session: str, checkout: Path) -> str:
    """The revision recorded when this live session was launched; the session must have started from `checkout`."""
    from atelier import live_sessions
    record = live_sessions.select(session, checkout=checkout)
    live_sessions.verify(record)
    return record.get('revision') or ''


def head_moved(checkout: Path) -> int:
    """When the checkout's HEAD last changed (its newest reflog entry, Unix seconds)."""
    entry = git(checkout, 'reflog', '-1', '--date=unix', '--format=%gd').strip()
    if not entry.startswith('HEAD@{') or not entry[6:-1].isdigit():
        raise ValueError(f'{checkout}: no HEAD reflog, so the launch revision cannot be proven')
    return int(entry[6:-1])


def process_revision(checkout: Path, port: int) -> str:
    """For a game without a session record (the donor's live CLI predates sessions): the process listening on loopback
    `port` must run a project of `checkout`, and HEAD must not have moved since that process started. Returns HEAD."""
    pids = subprocess.run(['lsof', '-nP', f'-iTCP@127.0.0.1:{int(port)}', '-sTCP:LISTEN', '-t'], capture_output=True,
                          text=True).stdout.split()
    if len(set(pids)) != 1:
        raise ValueError(f'expected one process listening on loopback port {port}, found {len(set(pids))}')
    pid = pids[0]
    command = subprocess.run(['ps', '-o', 'command=', '-p', pid], capture_output=True, text=True).stdout
    if f'{checkout.resolve()}/' not in command or '.uproject' not in command:
        raise ValueError(f'the process on port {port} (PID {pid}) does not run a project of {checkout}')
    start = subprocess.run(['ps', '-o', 'lstart=', '-p', pid], capture_output=True, text=True, env={'LC_ALL': 'C'})
    started = datetime.datetime.strptime(' '.join(start.stdout.split()), '%a %b %d %H:%M:%S %Y').timestamp()
    if head_moved(checkout) >= started:
        raise ValueError(f'{checkout} HEAD moved after the game (PID {pid}) started: relaunch it')
    return git(checkout, 'rev-parse', 'HEAD').strip()


def receipt(source, checkout, done, poses_file, names, sizes, settle, launched, how):
    if len(set(map(tuple, sizes))) != 1:
        raise ValueError(f'the captures have different sizes: {sizes}')
    return {'schema': 1, 'source': source, 'revision': revision(checkout, launched, how), 'map': done['map'], 'size': sizes[0],
            'warmup': int(round(settle)), 'poses_sha256': hashlib.sha256(poses_file.read_bytes()).hexdigest(),
            'poses': names, 'captured_utc': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'engine_version': done['engine_version'], 'render': done['render']}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--session', help='live session ID of the running game (omit for a checkout whose live CLI '
                        'predates sessions, like the donor: it addresses its one running game)')
    parser.add_argument('--live-from', type=Path, default=REPO,
                        help='checkout whose `atelier live` talks to the game (default this one; the donor its own)')
    parser.add_argument('--source', required=True, choices=['donor-runtime', 'v2'])
    parser.add_argument('--checkout', type=Path, default=REPO, help='the checkout the game runs from (its revision)')
    parser.add_argument('--port', type=int, default=8830, help='without --session: the loopback live port of the game')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--poses', type=Path, default=DEFAULT_POSES)
    parser.add_argument('--settle', type=float, default=8., help='seconds at each pose before its screenshot')
    parser.add_argument('--timeout', type=float, default=900)
    args = parser.parse_args(argv)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    stale = sorted(p.name for p in out.iterdir() if p.suffix.lower() == '.png' or p.name in ('capture.json', 'done.json'))
    if stale:
        print(f'{out} already holds {", ".join(stale[:5])}: capture into an empty folder', file=sys.stderr)
        return 2
    how = 'session' if args.session else 'process'
    try:
        launched = (launch_revision(args.session, args.checkout) if args.session
                    else process_revision(args.checkout, args.port))
        revision(args.checkout, launched, how)  # refuse a moved checkout before capturing anything
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'cannot bind the capture to its game: {error}', file=sys.stderr)
        return 2
    poses = json.loads(args.poses.read_text())['poses']
    names = [p['name'] for p in poses]
    glb = camera_glb(Path(tempfile.mkdtemp(prefix='parity-camera-')) / 'camera.glb')
    params = {'out': str(out), 'poses': poses, 'settle_s': args.settle, 'camera_glb': str(glb)}
    code = f'PARAMS = {json.dumps(params)!r}\nimport json as _j\nPARAMS = _j.loads(PARAMS)\n' + \
        (HERE / 'capture_runtime_game.py').read_text()
    session = ['--session', args.session] if args.session else []
    result = subprocess.run(['uv', 'run', 'atelier', 'live', *session, 'py', '-'], cwd=args.live_from, input=code,
                            text=True)
    if result.returncode:
        print('the capture could not start: is the game running with that live session?', file=sys.stderr)
        return 1
    deadline = time.monotonic() + args.timeout
    while not (out / 'done.json').is_file():
        if time.monotonic() > deadline:
            print(f'the capture did not finish in {args.timeout:.0f} s', file=sys.stderr)
            return 1
        time.sleep(1)
    done = json.loads((out / 'done.json').read_text())
    (out / 'done.json').unlink()
    if 'error' in done:
        print(f'capture failed in the game: {done["error"]}', file=sys.stderr)
        return 1
    sizes = [png_size(out / f'{n}.png') for n in names]
    data = receipt(args.source, args.checkout, done, args.poses, names, sizes, args.settle, launched, how)
    (out / 'capture.json').write_text(json.dumps(data, indent=2) + '\n')
    print(f'{len(names)} captures in {out}, {data["size"][0]}x{data["size"][1]}, receipt capture.json')
    return 0


if __name__ == '__main__':
    sys.exit(main())
