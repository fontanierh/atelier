"""Project a character's actual adventure export (adventure/retarget.py) into FileSet groups, and select one member.

``project`` reads the complete declared export Item (export.json, fbx/) and writes one group's members as
<name>.json, each the clip's own export entry with fbx/A_<name>.fbx's bytes: ``clips`` (the merged library's clips,
at bake.FPS) or ``own`` (the donor's clips retargeted onto a non-donor, at the donor's rate). Before any output it
checks the export rate, each member's rate against its committed group, each FBX, and that the donor carries no
own clips. ``select`` unpacks exactly the engine-selected member: member/ (the FBX with an export receipt, the
source form raw_import accepts) and meta/meta.json (its name, kind, frames and fps), so each clip owner consumes
only its own member, never the whole export.
"""
import base64
import hashlib
import json
from pathlib import Path
import re
import shutil

NAME = re.compile('[A-Za-z][A-Za-z0-9_-]*\\Z')


def _json(path):
    def pairs(rows):
        value = {}
        for key, item in rows:
            if key in value:
                raise ValueError('Duplicate adventure export field')
            value[key] = item
        return value
    return json.loads(Path(path).read_bytes(), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite adventure export value')))


def members(export, fbx, *, rates):
    """{kind: {name: fbx path}} for every committed group (``rates = {kind: fps}``), after the whole Item checks."""
    config = _json(export)
    if config.get('fps') != rates.get('clips') or not isinstance(config.get('clips'), dict) or not config['clips']:
        raise ValueError('Adventure export rate or clip roster differs from the committed bake rate')
    own = config.get('own') or {}
    if not isinstance(own, dict) or bool(own) != ('own' in rates):
        raise ValueError('Adventure own clips differ from the committed donor roster')
    result = {}
    for kind, table in (('clips', config['clips']), ('own', own)):
        if kind not in rates:
            continue
        rows = result[kind] = {}
        for name, entry in table.items():
            if (not isinstance(name, str) or not NAME.fullmatch(name) or not isinstance(entry, dict)
                    or entry.get('fps') != rates[kind] or type(entry.get('frames')) is not int or entry['frames'] <= 0):
                raise ValueError(f'Adventure {kind} member differs from its committed rate: {name}')
            path = Path(fbx) / f'A_{name}.fbx'
            if path.is_symlink() or path.resolve() != path or not path.is_file():
                raise ValueError(f'Adventure {kind} FBX is absent: {name}')
            rows[name] = (path, {'name': name, 'kind': kind, 'frames': entry['frames'], 'fps': entry['fps']})
    if set(result.get('clips', ())) & set(result.get('own', ())):
        raise ValueError('An adventure clip and own clip share A_ names')
    return result


def project(export=None, fbx=None, output=None, kind=None, rates=None):
    """@cc [owner:fontanierh,label:correctness] actual-adventure-export-members
    Membership MUST come from the complete declared adventure export Item. The
    export and member rates MUST equal their committed groups, every FBX MUST
    exist and the donor MUST carry no own clips before any output. Emit only the
    actual exported FBX bytes; no speculative member, generated scan or native work.
    """
    rows = members(export, fbx, rates=dict(rates))
    if kind not in rows:
        raise ValueError('Unknown adventure projection kind')
    if output.exists():
        raise ValueError('Adventure member output must be fresh')
    output.mkdir(parents=True)
    for name, (path, meta) in rows[kind].items():
        member = {**meta, 'fbx': base64.b64encode(path.read_bytes()).decode('ascii'),
                  'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        (output / (name + '.json')).write_text(json.dumps(member, sort_keys=True, separators=(',', ':')) + '\n')


def select(selected=None, destination=None, metadata=None, piece=None):
    """Unpack exactly the engine-selected member: its FBX with the export receipt a raw import reads, and its
    own clip metadata for the finish."""
    found = sorted(Path(selected).iterdir()) if Path(selected).is_dir() else []
    if (len(found) != 1 or found[0].name != piece + '.json' or found[0].is_symlink() or not found[0].is_file()
            or destination.exists() or metadata.exists()):
        raise ValueError('Adventure selected member must be one fresh regular <piece>.json')
    member = _json(found[0])
    if set(member) != {'name', 'kind', 'frames', 'fps', 'fbx', 'sha256'} or member['name'] != piece:
        raise ValueError('Adventure selected member differs from its piece')
    data = base64.b64decode(member['fbx'], validate=True)
    if hashlib.sha256(data).hexdigest() != member['sha256']:
        raise ValueError('Adventure selected member bytes differ from their checksum')
    destination.mkdir(parents=True)
    (destination / (piece + '.fbx')).write_bytes(data)
    (destination / 'export.json').write_text(json.dumps({'primary': piece + '.fbx', 'sha256': member['sha256']}, sort_keys=True) + '\n')
    metadata.mkdir(parents=True)
    meta = {key: member[key] for key in ('name', 'kind', 'frames', 'fps')}
    (metadata / 'meta.json').write_text(json.dumps(meta, sort_keys=True) + '\n')
