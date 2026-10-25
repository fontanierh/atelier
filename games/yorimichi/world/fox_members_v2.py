"""Project the actual fox hunter export (assets/characters/fox-hunter/export_unreal.py) into FileSet members and the
fixed body view for Scripts/import_fox_hunter.py's native owners.

The export Item is export.json with fbx/ (FoxHunter.fbx, A_Fox<clip>.fbx) and textures/. ``project`` writes one group:
- ``clips``: per committed clip (fox-hunter/manifest.json), its export entry with A_Fox<clip>.fbx's bytes;
- ``images``: each texture a material names, as <stem> bytes (the original texture package name is the file stem);
- ``materials``: each export material's configuration with its texture stem.
Every clip MUST import at the committed manifest fps, the one sample rate the clip template declares. ``body``
writes member/ (FoxHunter.fbx with its export receipt) and facts/facts.json: the bones, reference pose, speeds,
DA_FoxHunter clip entries, capsule, sole and source checksum the fixed owners consume. ``select`` unpacks one member.
"""
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

NAME = re.compile('[A-Za-z][A-Za-z0-9_-]*\\Z')
CLIP_FIELDS = ('duration', 'sample_rate', 'root_motion', 'loop', 'holds_last_pose', 'travel_cm', 'yaw_degrees',
               'travel_speed_cm_s', 'hit_window', 'strike_bone', 'strike_tip_bone', 'reach_cm')
MATERIAL_FIELDS = ('two_sided', 'roughness', 'metallic', 'specular')


def _json(path):
    def pairs(rows):
        value = {}
        for key, item in rows:
            if key in value:
                raise ValueError('Duplicate fox export field')
            value[key] = item
        return value
    return json.loads(Path(path).read_bytes(), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite fox export value')))


def _regular(path):
    path = Path(path)
    if path.is_symlink() or path.resolve() != path or not path.is_file():
        raise ValueError('Fox export file is absent or aliased: ' + str(path))
    return path


def members(export, fbx, textures, manifest):
    """{kind: {piece: member value}} and the export config, after the whole Item checks."""
    config = _json(_regular(export))
    committed = _json(_regular(manifest))
    roster, fps = list(committed['clips']), committed['fps']
    clips = config.get('clips')
    if not isinstance(clips, dict) or sorted(clips) != sorted(roster):
        raise ValueError('Fox export clips differ from the committed manifest roster')
    if config.get('mesh') != 'fbx/FoxHunter.fbx':
        raise ValueError('Fox export mesh is not fbx/FoxHunter.fbx')
    result = {'clips': {}, 'images': {}, 'materials': {}}
    for name in roster:
        entry = clips[name]
        if (not NAME.fullmatch(name) or not isinstance(entry, dict) or type(entry.get('root_motion')) is not bool
                or not isinstance(entry.get('duration'), (int, float)) or entry['duration'] <= 0
                or entry.get('sample_rate', 30) != fps):
            raise ValueError('Invalid fox clip: ' + name)
        data = _regular(Path(fbx) / f'A_Fox{name}.fbx').read_bytes()
        result['clips'][name] = {'name': name, **{k: entry[k] for k in CLIP_FIELDS if k in entry}, 'fbx': data}
    materials = config.get('materials')
    if not isinstance(materials, dict) or not materials:
        raise ValueError('Fox export has no materials')
    for name, cfg in materials.items():
        texture = PurePosixPath(str(cfg.get('texture')))
        if (not NAME.fullmatch(name) or texture.parent != PurePosixPath('textures')
                or texture.suffix not in ('.png', '.jpg') or not NAME.fullmatch(texture.stem)):
            raise ValueError('Fox material has no exported texture: ' + name)
        data = _regular(Path(textures) / texture.name).read_bytes()
        previous = result['images'].get(texture.stem)
        if previous is not None and previous['image'] != data:
            raise ValueError('Aliased fox texture: ' + texture.stem)
        result['images'][texture.stem] = {'name': texture.stem, 'mime': 'image/png' if texture.suffix == '.png' else 'image/jpeg',
                                          'image': data}
        result['materials'][name] = {'name': name, 'texture': texture.stem, **{k: cfg[k] for k in MATERIAL_FIELDS}}
    return result, config


def _encode(value):
    encoded = {key: (base64.b64encode(item).decode('ascii') if isinstance(item, bytes) else item) for key, item in value.items()}
    blob = next((value[key] for key in ('fbx', 'image') if key in value), None)
    if blob is not None:
        encoded['sha256'] = hashlib.sha256(blob).hexdigest()
    return json.dumps(encoded, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n'


def project(export=None, fbx=None, textures=None, manifest=None, output=None, kind=None):
    """@cc [owner:fontanierh,label:correctness] actual-fox-export-members
    Membership MUST come from the complete declared fox export Item: exactly the
    committed manifest clips, each with its own FBX, and the export's materials
    with the textures they name. Each member carries only its owner's narrow view;
    no speculative member, generated scan or native work.
    """
    rows = members(export, fbx, textures, manifest)[0]
    if kind not in rows:
        raise ValueError('Unknown fox projection kind')
    if output.exists():
        raise ValueError('Fox member output must be fresh')
    output.mkdir(parents=True)
    for piece, value in rows[kind].items():
        (output / (piece + '.json')).write_text(_encode(value))


def body(export=None, fbx=None, textures=None, manifest=None, member=None, facts=None):
    """The fixed owners' views: member/ (FoxHunter.fbx and its receipt) and facts/facts.json."""
    rows, config = members(export, fbx, textures, manifest)
    data = _regular(Path(fbx) / 'FoxHunter.fbx').read_bytes()
    clips = config['clips']
    value = {'bones': sorted(set(config['bones'].values())), 'rest_bones_cm': config['rest_bones_cm'],
             'speeds': {n: float(clips[n]['travel_speed_cm_s']) for n in ('Idle', 'Creep', 'Run')},
             'clips': {name: {k: clips[name][k] for k in CLIP_FIELDS if k in clips[name]} for name in clips},
             'materials': sorted(rows['materials']), 'capsule': config['capsule'], 'sole_cm': config['sole_cm'],
             'source_sha256': config['source_sha256']}
    if member.exists() or facts.exists():
        raise ValueError('Fox body outputs must be fresh')
    member.mkdir(parents=True); facts.mkdir(parents=True)
    (member / 'FoxHunter.fbx').write_bytes(data)
    (member / 'export.json').write_text(json.dumps({'primary': 'FoxHunter.fbx', 'sha256': hashlib.sha256(data).hexdigest()},
                                                   sort_keys=True) + '\n')
    (facts / 'facts.json').write_text(json.dumps(value, sort_keys=True, allow_nan=False) + '\n')


def select(selected=None, destination=None, metadata=None, piece=None):
    """Unpack exactly the engine-selected member: its bytes (an FBX or image with its export receipt) in member/,
    when it has any, and its own metadata in meta/meta.json."""
    found = sorted(Path(selected).iterdir()) if Path(selected).is_dir() else []
    if (len(found) != 1 or found[0].name != piece + '.json' or found[0].is_symlink() or not found[0].is_file()
            or destination.exists() or metadata.exists()):
        raise ValueError('Fox selected member must be one fresh regular <piece>.json')
    member = _json(found[0])
    if member.get('name') != piece:
        raise ValueError('Fox selected member differs from its piece')
    destination.mkdir(parents=True)
    for key in ('fbx', 'image'):
        if key in member:
            data = base64.b64decode(member[key], validate=True)
            if hashlib.sha256(data).hexdigest() != member['sha256']:
                raise ValueError('Fox selected member bytes differ from their checksum')
            name = piece + ('.fbx' if key == 'fbx' else '.png' if member['mime'] == 'image/png' else '.jpg')
            (destination / name).write_bytes(data)
            (destination / 'export.json').write_text(json.dumps({'primary': name, 'sha256': member['sha256']}, sort_keys=True) + '\n')
    metadata.mkdir(parents=True)
    meta = {key: value for key, value in member.items() if key not in ('fbx', 'image', 'sha256')}
    (metadata / 'meta.json').write_text(json.dumps(meta, sort_keys=True) + '\n')
