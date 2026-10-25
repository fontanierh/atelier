"""Project a character's actual export membership (pipeline/export.py) into FileSet groups, and select one member.

``project`` reads the complete declared export Item (export.json, fbx/, textures/) and writes one group's
members: ``materials`` as <M>.json (its export.json entry), ``textures`` as the exported images each material names,
``clips_<rate>`` as <clip>.fbx copies of fbx/A_<clip>.fbx for the clips exported at that sample rate. Before any
output it checks the body FBX, every clip FBX and texture, the cloth report against the committed hooks, and that
every clip's rate is one the committed source declares. ``select`` packages exactly the engine-selected member with
an export receipt, the source form raw_import accepts.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil

NAME = re.compile('[A-Za-z][A-Za-z0-9_-]*\\Z')
IMAGES = ('.png', '.jpg')


def _json(path):
    def pairs(rows):
        value = {}
        for key, item in rows:
            if key in value:
                raise ValueError('Duplicate character export field')
            value[key] = item
        return value
    return json.loads(Path(path).read_bytes(), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite character export value')))


def _file(root, name):
    path = Path(root) / name
    if (PurePosixPath(name).is_absolute() or len(PurePosixPath(name).parts) != 1 or path.is_symlink()
            or path.resolve() != path or not path.is_file()):
        raise ValueError('Character export member is absent or aliased: ' + str(name))
    return path


def members(export, fbx, textures, *, name, cloth, rates):
    """{kind: {piece: (payload name, source path or encoded JSON)}} for every group, after the whole Item checks."""
    config = _json(export)
    if not isinstance(config.get('materials'), dict) or not config['materials'] or not isinstance(config.get('clips'), dict):
        raise ValueError('Character export has no material/clip roster')
    _file(fbx, name + '.fbx')
    if bool(config.get('cloth')) != bool(cloth):
        raise ValueError('Character export cloth differs from its committed export hooks')
    result = {'materials': {}, 'textures': {}, **{f'clips_{rate}': {} for rate in rates}}
    for material, cfg in config['materials'].items():
        if not isinstance(material, str) or not NAME.fullmatch(material) or not isinstance(cfg, dict):
            raise ValueError('Invalid character material member: ' + str(material))
        result['materials'][material] = (material + '.json', json.dumps(cfg, sort_keys=True, separators=(',', ':'),
                                                                         allow_nan=False) + '\n')
        texture = cfg.get('texture')
        if texture is None:
            continue
        path = PurePosixPath(texture) if isinstance(texture, str) else None
        if (path is None or len(path.parts) != 2 or path.parts[0] != 'textures' or path.suffix not in IMAGES
                or not NAME.fullmatch(path.stem)):
            raise ValueError('Invalid character texture member: ' + str(texture))
        source = _file(textures, path.name)
        if result['textures'].get(path.stem, (path.name, source)) != (path.name, source):
            raise ValueError('Aliased character texture: ' + path.stem)
        result['textures'][path.stem] = (path.name, source)
    for clip, cfg in config['clips'].items():
        rate = cfg.get('sample_rate') if isinstance(cfg, dict) else None
        if not isinstance(clip, str) or not NAME.fullmatch(clip) or type(rate) is not int or rate not in rates:
            raise ValueError('Character clip is outside the committed rate groups: ' + str(clip))
        result[f'clips_{rate}'][clip] = (clip + '.fbx', _file(fbx, 'A_' + clip + '.fbx'))
    for kind, rows in result.items():
        if not rows:
            raise ValueError('Committed character group has no actual exported member: ' + kind)
    return result


def project(export=None, fbx=None, textures=None, output=None, kind=None, name=None, cloth=None, rates=()):
    """@cc [owner:fontanierh,label:correctness] actual-character-export-members
    Membership MUST come from the complete declared export Item. The body,
    every clip FBX and texture, cloth agreement and committed clip rates MUST
    validate before any output. Emit only actual material entries, images and
    clip FBX bytes; no speculative member, generated scan or native work.
    """
    rows = members(export, fbx, textures, name=name, cloth=cloth, rates=tuple(rates))
    if kind not in rows:
        raise ValueError('Unknown character projection kind')
    if output.exists():
        raise ValueError('Character member output must be fresh')
    output.mkdir(parents=True)
    for payload, value in rows[kind].values():
        if isinstance(value, str):
            (output / payload).write_text(value)
        else:
            shutil.copyfile(value, output / payload)


def select(selected=None, destination=None, piece=None):
    """Package exactly the engine-selected member, with the export receipt a raw import reads."""
    found = sorted(Path(selected).iterdir()) if Path(selected).is_dir() else []
    if (len(found) != 1 or found[0].stem != piece or found[0].is_symlink() or not found[0].is_file()
            or destination.exists()):
        raise ValueError('Character selected member must be one fresh regular file named by its piece')
    destination.mkdir(parents=True)
    shutil.copyfile(found[0], destination / found[0].name)
    receipt = {'primary': found[0].name, 'sha256': hashlib.sha256(found[0].read_bytes()).hexdigest()}
    (destination / 'export.json').write_text(json.dumps(receipt, sort_keys=True) + '\n')
