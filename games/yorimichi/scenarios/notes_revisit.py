#!/usr/bin/env python3
"""Re-shoot the operator's playtest notes from their recorded camera poses.

    uv run atelier qa yorimichi notes_revisit --notes PATH [--out DIR] [--port 8830]

Each note records the free camera that the operator used (location, pitch, yaw, fov) and the player's position. The
scenario teleports the player to that position, restores the review camera at the recorded pose, waits for the frame
rate and streaming to settle, and writes `note-NNN-after.png` beside an `index.json`. The index keeps the requested
and measured poses so a before/after pair can be checked without trusting the capture.
"""
import argparse
import json
import math
import struct
import time
from dataclasses import dataclass
from pathlib import Path

import skate as qa

SETTLE_MIN_FPS = 30.0
SETTLE_SECONDS = 1.0
SETTLE_LIMIT = 90.0
LOCATION_TOLERANCE_CM = 0.5
ANGLE_TOLERANCE_DEG = 0.1
FOV_TOLERANCE_DEG = 0.1
FORWARD_TOLERANCE = 0.02
SHOT_TIMEOUT_SECONDS = 20.0


@dataclass(frozen=True)
class Pose:
    location: tuple
    pitch: float
    yaw: float
    roll: float
    fov: float
    target: tuple
    player: tuple
    player_yaw: float


def _number(value, what):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{what} must be a number')
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f'{what} must be finite')
    return number


def _point(value, what):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f'{what} must be three numbers')
    return tuple(_number(part, what) for part in value)


def forward_from_rotation(pitch, yaw):
    """Unreal's rotation convention: x forward, y right, z up; positive pitch looks up."""
    p, y = math.radians(pitch), math.radians(yaw)
    return (math.cos(p) * math.cos(y), math.cos(p) * math.sin(y), math.sin(p))


def pose_from_note(note):
    """Map one note's recorded camera and player to the pose the review camera and teleport need."""
    if not isinstance(note, dict):
        raise ValueError('each note must be an object')
    camera = note.get('camera')
    if not isinstance(camera, dict):
        raise ValueError('note has no camera object')
    location = _point(camera.get('location_cm'), 'camera location_cm')
    pitch = _number(camera.get('pitch'), 'camera pitch')
    yaw = _number(camera.get('yaw'), 'camera yaw')
    roll = _number(camera.get('roll', 0.0), 'camera roll')
    fov = _number(camera.get('fov'), 'camera fov')
    if not 1.0 <= fov <= 179.0:
        raise ValueError('camera fov must be between 1 and 179 degrees')

    direction = forward_from_rotation(pitch, yaw)
    recorded = camera.get('forward')
    if recorded is not None:
        recorded = _point(recorded, 'camera forward')
        length = math.sqrt(sum(part * part for part in recorded))
        if abs(length - 1.0) > 0.01:
            raise ValueError('camera forward must be a unit vector')
        difference = max(abs(a - b) for a, b in zip(recorded, direction))
        if difference > FORWARD_TOLERANCE:
            raise ValueError('camera forward disagrees with pitch and yaw')

    player = note.get('player_cm')
    player = _point(player, 'player_cm') if player is not None else location
    player_yaw = _number(note.get('player_yaw', yaw), 'player_yaw')
    target = tuple(part + direction[index] * 1000.0 for index, part in enumerate(location))
    return Pose(location, pitch, yaw, roll, fov, target, player, player_yaw)


def load_notes(path):
    """Read and validate a notes.json; return its data and notes ordered by index."""
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data, dict) or not isinstance(data.get('notes'), list):
        raise ValueError('notes.json must contain a notes list')
    notes, seen = [], set()
    for note in data['notes']:
        if not isinstance(note, dict):
            raise ValueError('each note must be an object')
        index = note.get('index')
        if isinstance(index, bool) or not isinstance(index, int) or index < 1:
            raise ValueError('each note needs a positive integer index')
        if index in seen:
            raise ValueError(f'duplicate note index {index}')
        seen.add(index)
        pose_from_note(note)
        notes.append(note)
    if not notes:
        raise ValueError('notes.json has no notes')
    return data, sorted(notes, key=lambda note: note['index'])


def shot_name(index):
    return f'note-{index:03d}-after.png'


def png_size(path):
    """(width, height) from a PNG's IHDR, or None when the file is not a PNG."""
    try:
        with open(path, 'rb') as stream:
            header = stream.read(24)
    except OSError:
        return None
    if len(header) < 24 or header[:8] != b'\x89PNG\r\n\x1a\n' or header[12:16] != b'IHDR':
        return None
    return struct.unpack('>II', header[16:24])


def _code(pose):
    location, target, player = pose.location, pose.target, pose.player
    fov, yaw = pose.fov, pose.player_yaw
    return (
        'import unreal\n'
        f"assert unreal.LiveLibrary.teleport_player(unreal.Vector({player[0]!r}, {player[1]!r}, {player[2]!r}), {yaw!r})\n"
        f"assert unreal.YorimichiLive.hold_camera({SHOT_TIMEOUT_SECONDS!r})\n"
        f"assert unreal.MegaParkValidation.review_camera(unreal.Vector({location[0]!r}, {location[1]!r}, {location[2]!r}), "
        f"unreal.Vector({target[0]!r}, {target[1]!r}, {target[2]!r}), {fov!r})\n"
    )


def _capture_code(path):
    return f'import unreal\nunreal.LiveLibrary.screenshot({json.dumps(str(path))})\n'


def _cleanup_code():
    return 'import unreal\nunreal.YorimichiLive.hold_camera(0.0)\nunreal.MegaParkValidation.restore_player_camera()\n'


def _write_index(path, index):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(index, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def _measured_camera(qa_module):
    state = qa_module.bridge.request('/state')
    location = _point(state.get('camera'), 'camera state')
    rotation = _point(state.get('camera_rotation'), 'camera rotation state')
    return location, rotation


def _measured_fov(qa_module):
    output = qa_module.py(
        'import unreal\n'
        'print(unreal.GameplayStatics.get_player_camera_manager(unreal.LiveLibrary.game_world(), 0).get_fov_angle())\n'
    )
    lines = [line.strip() for line in str(output).splitlines() if line.strip()]
    if not lines:
        raise ValueError('camera fov state is empty')
    try:
        return float(lines[-1])
    except ValueError as error:
        raise ValueError(f'camera fov state is not a number: {lines[-1]!r}') from error


def _pose_errors(pose, location, rotation, fov):
    distance = math.dist(location, pose.location)
    pitch = abs(((rotation[0] - pose.pitch + 180.0) % 360.0) - 180.0)
    yaw = abs(((rotation[1] - pose.yaw + 180.0) % 360.0) - 180.0)
    fov_error = abs(fov - pose.fov)
    errors = []
    if distance > LOCATION_TOLERANCE_CM:
        errors.append(f'camera is {distance:.2f} cm from the recorded position')
    if pitch > ANGLE_TOLERANCE_DEG:
        errors.append(f'camera pitch is {pitch:.2f} degrees off')
    if yaw > ANGLE_TOLERANCE_DEG:
        errors.append(f'camera yaw is {yaw:.2f} degrees off')
    if fov_error > FOV_TOLERANCE_DEG:
        errors.append(f'camera fov is {fov_error:.2f} degrees off')
    return distance, pitch, yaw, fov_error, errors


def _wait_for_shot(path, monotonic, sleep):
    deadline = monotonic() + SHOT_TIMEOUT_SECONDS
    while monotonic() < deadline:
        if path.exists() and path.stat().st_size > 0:
            return
        sleep(0.15)
    raise RuntimeError(f'screenshot was not written: {path}')


def capture(notes_path, out_dir, qa_module=qa, monotonic=time.monotonic, sleep=time.sleep):
    """Re-shoot every note, writing the numbered stills and index.json. Returns 0 when every pose was reproduced."""
    notes_path, out_dir = Path(notes_path), Path(out_dir)
    data, notes = load_notes(notes_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    index = {
        'scenario': 'notes_revisit',
        'notes': str(notes_path.resolve()),
        'out': str(out_dir.resolve()),
        'units': data.get('units', 'unreal cm'),
        'started': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'settle': {'minimum_fps': SETTLE_MIN_FPS, 'seconds': SETTLE_SECONDS},
        'tolerance': {'location_cm': LOCATION_TOLERANCE_CM, 'angle_deg': ANGLE_TOLERANCE_DEG,
                      'fov_deg': FOV_TOLERANCE_DEG},
        'captures': [],
    }
    index_path = out_dir / 'index.json'
    try:
        for note in notes:
            pose = pose_from_note(note)
            shot = out_dir / shot_name(note['index'])
            shot.unlink(missing_ok=True)
            print(f"note {note['index']:03d}: camera at {pose.location}, fov {pose.fov:g}", flush=True)
            qa_module.py(_code(pose))
            qa_module.settle(minimum=SETTLE_MIN_FPS, seconds=SETTLE_SECONDS, limit=SETTLE_LIMIT)
            location, rotation = _measured_camera(qa_module)
            fov = _measured_fov(qa_module)
            distance, pitch, yaw, fov_error, errors = _pose_errors(pose, location, rotation, fov)
            qa_module.py(_capture_code(shot))
            _wait_for_shot(shot, monotonic, sleep)
            size = png_size(shot)
            if size is None:
                errors.append('capture is not a PNG')
            record = {
                'index': note['index'],
                'time': note.get('time'),
                'text': note.get('text'),
                'map': note.get('map'),
                'before': note.get('screenshot') or f"note-{note['index']:03d}.png",
                'after': shot.name,
                'size': list(size) if size else None,
                'requested': {
                    'location_cm': list(pose.location),
                    'pitch': pose.pitch,
                    'yaw': pose.yaw,
                    'roll': pose.roll,
                    'fov': pose.fov,
                    'player_cm': list(pose.player),
                    'player_yaw': pose.player_yaw,
                    'player_yaw_source': 'notes' if 'player_yaw' in note else 'camera yaw',
                },
                'camera': {
                    'location_cm': list(location),
                    'pitch': rotation[0],
                    'yaw': rotation[1],
                    'roll': rotation[2],
                    'fov': fov,
                },
                'error': {'location_cm': round(distance, 3), 'pitch_deg': round(pitch, 3), 'yaw_deg': round(yaw, 3),
                          'fov_deg': round(fov_error, 3)},
                'look_at': note.get('look_at'),
                'look_target': note.get('look_target'),
                'ok': not errors,
                'errors': errors,
            }
            index['captures'].append(record)
            _write_index(index_path, index)
            print(('PASS' if record['ok'] else 'FAIL') + f" {shot.name}" + (f": {'; '.join(errors)}" if errors else ''),
                  flush=True)
    finally:
        try:
            qa_module.py(_cleanup_code())
        except Exception as error:  # keep the partial index when the bridge has gone away
            print(f'warning: could not restore the player camera: {error}', flush=True)
        index['finished'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        index['ok'] = bool(index['captures']) and all(record['ok'] for record in index['captures'])
        _write_index(index_path, index)
    return 0 if index['ok'] else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--notes', required=True, type=Path, help='the notes.json written by the operator notes tool')
    parser.add_argument('--out', type=Path, help='capture folder (default: build/yorimichi/notes_revisit/<notes folder>)')
    parser.add_argument('--port', type=int, default=8830)
    args = parser.parse_args(argv)
    qa.bridge.URL = f'http://127.0.0.1:{args.port}'
    out = args.out or qa.yori.OUT / 'notes_revisit' / args.notes.resolve().parent.name
    return capture(args.notes, out)


if __name__ == '__main__':
    raise SystemExit(main())
