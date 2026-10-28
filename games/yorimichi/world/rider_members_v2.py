"""Project a playable character's actual ride export (vehicles/bike/rider.py, horses/rider.py) into FileSet members.

``project`` reads the complete declared export Item (<ride>/export.json, <ride>/fbx) and writes one <clip>.json per
exported clip: its export entry (frames, loop, duration) at the export rate with fbx/A_<clip>.fbx's bytes. Before
any output it checks the export rate against the committed rider FPS, every FBX, and, where the roster is committed
(the horse's HORSE_RIDER_CLIPS), the exact clip set. ``select`` unpacks exactly the engine-selected member:
member/ (the FBX with an export receipt, the source form raw_import accepts) and meta/meta.json, so each clip owner
consumes only its own member.
"""
import base64
import hashlib
import json
from pathlib import Path
import re

NAME = re.compile('[A-Za-z][A-Za-z0-9_-]*\\Z')


def _json(path):
    def pairs(rows):
        value = {}
        for key, item in rows:
            if key in value:
                raise ValueError('Duplicate ride export field')
            value[key] = item
        return value
    return json.loads(Path(path).read_bytes(), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite ride export value')))


def members(export, fbx, *, fps, roster=None):
    """{clip: (fbx path, metadata)} after the whole Item checks."""
    config = _json(export)
    clips = config.get('clips')
    if config.get('fps') != fps or not isinstance(clips, dict) or not clips:
        raise ValueError('Ride export rate or clip roster differs from the committed rider FPS')
    if roster is not None and sorted(clips) != sorted(roster):
        raise ValueError('Ride export clips differ from the committed roster')
    result = {}
    for name, entry in clips.items():
        if (not isinstance(name, str) or not NAME.fullmatch(name) or not isinstance(entry, dict)
                or type(entry.get('frames')) is not int or entry['frames'] <= 0 or not isinstance(entry.get('duration'), (int, float))
                or type(entry.get('loop')) is not bool):
            raise ValueError('Invalid ride clip member: ' + str(name))
        path = Path(fbx) / f'A_{name}.fbx'
        if path.is_symlink() or path.resolve() != path or not path.is_file():
            raise ValueError('Ride clip FBX is absent: ' + name)
        result[name] = (path, {'name': name, 'frames': entry['frames'], 'loop': entry['loop'],
                               'duration': entry['duration'], 'fps': fps})
    return result


def project(export=None, fbx=None, output=None, fps=None, roster=None):
    """@cc [owner:fontanierh,label:correctness] actual-ride-export-members
    Membership MUST come from the complete declared ride export Item. The rate
    MUST equal the committed rider FPS, every clip FBX MUST exist and a committed
    roster MUST match exactly before any output. Emit only actual clip entries
    with their FBX bytes; no speculative member, generated scan or native work.
    """
    rows = members(export, fbx, fps=fps, roster=None if roster is None else list(roster))
    if output.exists():
        raise ValueError('Ride member output must be fresh')
    output.mkdir(parents=True)
    for name, (path, meta) in rows.items():
        data = path.read_bytes()
        member = {**meta, 'fbx': base64.b64encode(data).decode('ascii'), 'sha256': hashlib.sha256(data).hexdigest()}
        (output / (name + '.json')).write_text(json.dumps(member, sort_keys=True, separators=(',', ':')) + '\n')


def select(selected=None, destination=None, metadata=None, piece=None):
    """Unpack exactly the engine-selected member: its FBX with the export receipt a raw import reads, and its
    own clip metadata for the finish."""
    found = sorted(Path(selected).iterdir()) if Path(selected).is_dir() else []
    if (len(found) != 1 or found[0].name != piece + '.json' or found[0].is_symlink() or not found[0].is_file()
            or destination.exists() or metadata.exists()):
        raise ValueError('Ride selected member must be one fresh regular <piece>.json')
    member = _json(found[0])
    if set(member) != {'name', 'frames', 'loop', 'duration', 'fps', 'fbx', 'sha256'} or member['name'] != piece:
        raise ValueError('Ride selected member differs from its piece')
    data = base64.b64decode(member['fbx'], validate=True)
    if hashlib.sha256(data).hexdigest() != member['sha256']:
        raise ValueError('Ride selected member bytes differ from their checksum')
    destination.mkdir(parents=True)
    (destination / (piece + '.fbx')).write_bytes(data)
    (destination / 'export.json').write_text(json.dumps({'primary': piece + '.fbx', 'sha256': member['sha256']}, sort_keys=True) + '\n')
    metadata.mkdir(parents=True)
    meta = {key: member[key] for key in ('name', 'frames', 'loop', 'duration', 'fps')}
    (metadata / 'meta.json').write_text(json.dumps(meta, sort_keys=True) + '\n')
