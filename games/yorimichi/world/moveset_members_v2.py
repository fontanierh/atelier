"""Project a character's actual adventure export (adventure/retarget.py) into FileSet groups, and select one member.

``project`` reads the complete declared export Item (export.json, fbx/) and writes one group's members as
<name>.fbx copies of fbx/A_<name>.fbx: ``clips`` (the merged library's clips, at bake.FPS) or ``own`` (the donor's
clips retargeted onto a non-donor, at the donor's rate). Before any output it checks the export rate, each member's
rate against its committed group, each FBX, and that the donor carries no own clips. ``select`` packages exactly
the engine-selected member with an export receipt, the source form raw_import accepts.
"""
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
            rows[name] = path
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
    for name, path in rows[kind].items():
        shutil.copyfile(path, output / (name + '.fbx'))


def select(selected=None, destination=None, piece=None):
    """Package exactly the engine-selected member, with the export receipt a raw import reads."""
    found = sorted(Path(selected).iterdir()) if Path(selected).is_dir() else []
    if (len(found) != 1 or found[0].stem != piece or found[0].is_symlink() or not found[0].is_file()
            or destination.exists()):
        raise ValueError('Adventure selected member must be one fresh regular file named by its piece')
    destination.mkdir(parents=True)
    shutil.copyfile(found[0], destination / found[0].name)
    receipt = {'primary': found[0].name, 'sha256': hashlib.sha256(found[0].read_bytes()).hexdigest()}
    (destination / 'export.json').write_text(json.dumps(receipt, sort_keys=True) + '\n')
