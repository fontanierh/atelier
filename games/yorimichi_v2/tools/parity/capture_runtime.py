"""Capture the parity poses from a RUNNING game, donor or V2, for compare.py (plan P3.6: the donor runtime baseline).

    uv run python games/yorimichi_v2/tools/parity/capture_runtime.py --source donor-runtime \
        --checkout DONOR_CHECKOUT --out build/yorimichi_v2/parity/donor
    uv run python games/yorimichi_v2/tools/parity/capture_runtime.py --session ID --source v2 \
        --out build/yorimichi_v2/parity/v2
--poses FILE --only GLOB (e.g. 'w07_*') captures a subset of a poses file, such as island_poses.json (the receipt
names only the subset; compare.py then needs the same --only).

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
import base64
import datetime
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(HERE.parent / 'test'))
from launch import git, launch_revision, revision  # noqa: E402
sys.path.insert(0, str(HERE))
from poseset import load_poses, select  # noqa: E402
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


def head_moved(checkout: Path) -> int:
    """When the checkout's HEAD last changed (its newest reflog entry, Unix seconds)."""
    entry = git(checkout, 'reflog', '-1', '--date=unix', '--format=%gd').strip()
    if not entry.startswith('HEAD@{') or not entry[6:-1].isdigit():
        raise ValueError(f'{checkout}: no HEAD reflog, so the launch revision cannot be proven')
    return int(entry[6:-1])


def listener(port: int) -> tuple[int, str, float]:
    """(PID, command line, start time) of the one process listening on loopback `port`."""
    pids = set(subprocess.run(['lsof', '-nP', f'-iTCP@127.0.0.1:{int(port)}', '-sTCP:LISTEN', '-t'],
                              capture_output=True, text=True).stdout.split())
    if len(pids) != 1:
        raise ValueError(f'expected one process listening on loopback port {port}, found {len(pids)}')
    pid = pids.pop()
    command = subprocess.run(['ps', '-o', 'command=', '-p', pid], capture_output=True, text=True).stdout
    start = subprocess.run(['ps', '-o', 'lstart=', '-p', pid], capture_output=True, text=True, env={'LC_ALL': 'C'})
    started = datetime.datetime.strptime(' '.join(start.stdout.split()), '%a %b %d %H:%M:%S %Y').timestamp()
    return int(pid), command, started


def process_revision(checkout: Path, port: int) -> tuple[str, tuple]:
    """For a game without a session record (the donor's live CLI predates sessions): the process listening on loopback
    `port` must run a project of `checkout`, and HEAD must not have moved since that process started. Returns HEAD and
    the listener, which must still hold the port when the capture ends."""
    pid, command, started = found = listener(port)
    if f'{checkout.resolve()}/' not in command or '.uproject' not in command:
        raise ValueError(f'the process on port {port} (PID {pid}) does not run a project of {checkout}')
    if head_moved(checkout) >= started:
        raise ValueError(f'{checkout} HEAD moved after the game (PID {pid}) started: relaunch it')
    return git(checkout, 'rev-parse', 'HEAD').strip(), found


def post_python(port: int, code: str) -> bool:
    """Run `code` in the game on loopback `port` through its live bridge (the body format of `atelier live py`)."""
    data = base64.b64encode(code.encode()).decode()
    body = f"import base64 as _live_b64\nexec(compile(_live_b64.b64decode('{data}').decode(), '<atelier live>', 'exec'))\n"
    request = urllib.request.Request(f'http://127.0.0.1:{int(port)}/python', data=body.encode(), method='POST')
    with urllib.request.urlopen(request, timeout=120) as response:
        out = json.loads(response.read().decode())
    if not out.get('ok'):
        print(out.get('result', ''), file=sys.stderr)
    return bool(out.get('ok'))


def receipt(source, checkout, done, poses_file, names, sizes, settle, launched, how):
    if len(set(map(tuple, sizes))) != 1:
        raise ValueError(f'the captures have different sizes: {sizes}')
    return {'schema': 1, 'source': source, 'revision': revision(checkout, launched, how), 'map': done['map'], 'size': sizes[0],
            'warmup': int(round(settle)), 'poses_sha256': hashlib.sha256(poses_file.read_bytes()).hexdigest(),
            'poses': names, 'captured_utc': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'engine_version': done['engine_version'], 'render': done['render']}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--session', help='live session ID of the running game, launched from --checkout (omit for a '
                        'game without a session record, like the donor: the capture then goes to --port directly)')
    parser.add_argument('--source', required=True, choices=['donor-runtime', 'v2'])
    parser.add_argument('--checkout', type=Path, default=REPO, help='the checkout the game runs from (its revision)')
    parser.add_argument('--port', type=int, default=8830, help='without --session: the loopback live port of the game '
                        '(verified, captured through and checked again afterwards)')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--poses', type=Path, default=DEFAULT_POSES)
    parser.add_argument('--only', action='append', help='capture only the poses named by this glob (e.g. w07_*), '
                        'comma separated or repeated; the receipt then names only those poses')
    parser.add_argument('--settle', type=float, default=8., help='seconds at each pose before its screenshot')
    parser.add_argument('--timeout', type=float, default=900)
    args = parser.parse_args(argv)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    stale = sorted(p.name for p in out.iterdir() if p.suffix.lower() == '.png' or p.name in ('capture.json', 'done.json'))
    if stale:
        print(f'{out} already holds {", ".join(stale[:5])}: capture into an empty folder', file=sys.stderr)
        return 2
    how, found = ('session' if args.session else 'process'), None
    try:
        if args.session:
            launched = launch_revision(args.session, args.checkout)
        else:
            launched, found = process_revision(args.checkout, args.port)
        revision(args.checkout, launched, how)  # refuse a moved checkout before capturing anything
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'cannot bind the capture to its game: {error}', file=sys.stderr)
        return 2
    try:
        poses = select(load_poses(args.poses), args.only)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    names = [p['name'] for p in poses]
    glb = camera_glb(Path(tempfile.mkdtemp(prefix='parity-camera-')) / 'camera.glb')
    params = {'out': str(out), 'poses': poses, 'settle_s': args.settle, 'camera_glb': str(glb)}
    code = f'PARAMS = {json.dumps(params)!r}\nimport json as _j\nPARAMS = _j.loads(PARAMS)\n' + \
        (HERE / 'capture_runtime_game.py').read_text()
    if args.session:
        started = not subprocess.run(['uv', 'run', 'atelier', 'live', '--session', args.session, 'py', '-'],
                                     cwd=args.checkout, input=code, text=True).returncode
    else:
        try:
            started = post_python(args.port, code)
        except (OSError, ValueError) as error:
            print(f'live bridge on port {args.port}: {error}', file=sys.stderr)
            started = False
    if not started:
        print('the capture could not start in that game', file=sys.stderr)
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
    if found is not None and listener(args.port) != found:
        print(f'another process holds port {args.port} now: the captures cannot be attributed', file=sys.stderr)
        return 1
    sizes = [png_size(out / f'{n}.png') for n in names]
    data = receipt(args.source, args.checkout, done, args.poses, names, sizes, args.settle, launched, how)
    (out / 'capture.json').write_text(json.dumps(data, indent=2) + '\n')
    print(f'{len(names)} captures in {out}, {data["size"][0]}x{data["size"][1]}, receipt capture.json')
    return 0


if __name__ == '__main__':
    sys.exit(main())
