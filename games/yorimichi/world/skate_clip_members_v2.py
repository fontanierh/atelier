"""Project the assembled skate simulation package (skate.runtime) into the Ride clip owners' narrow views.

The package Item is the complete simulation package folder; the committed package-manifest.json names every clip file.
``project`` writes one FileSet member per clip of one bank (its Clips/B<bank> folder), <clip>.json: the clip's .skate bytes, its ClipMetadata (the record
import_clips.main picks: the last same-name record over both banks) and its clips.json record, computed by the original
attribute_record, motion_record and channel_record and make_clip's snap-guard count. ``rig`` writes the fixed views:
rig/ (SK_SkateRider.glb by the original rider_mesh.write_glb, with its export receipt) and bundle/ (the rig file and
the mesh statistics). ``select`` unpacks one member. ``original`` reads scoped functions of the original scripts.
"""
import ast
import base64
from dataclasses import asdict
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import shutil
import sys

NAME = re.compile('[A-Za-z0-9_]+\\Z')
RECORDS = ('round_list', 'attribute_record', 'motion_record', 'channel_record')


def module(path, name):
    """A sibling original module by path, registered so its dataclasses resolve."""
    if name in sys.modules and getattr(sys.modules[name], '__file__', None) == str(path):
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); sys.modules[name] = value; spec.loader.exec_module(value)
    return value


def original(path, names, scope):
    """Exactly the named top-level functions of an original script, executed in ``scope``; its top level never runs."""
    tree = ast.parse(Path(path).read_bytes(), filename=str(path))
    found = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    if sorted(n.name for n in found) != sorted(names):
        raise ValueError(f'{Path(path).name} no longer defines {sorted(set(names) - {n.name for n in found})}')
    exec(compile(ast.Module(body=found, type_ignores=[]), str(path), 'exec'), scope)
    return scope


def constants(path, names):
    """Literal top-level constants of an original script."""
    tree = ast.parse(Path(path).read_bytes(), filename=str(path))
    values = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and getattr(node.targets[0], 'id', None) in names:
            value = node.value
            if (isinstance(value, ast.Call) and getattr(value.func, 'id', None) == 'dict' and not value.args
                    and all(k.arg for k in value.keywords)):   # dict(name=literal, ...)
                values[node.targets[0].id] = {k.arg: ast.literal_eval(k.value) for k in value.keywords}
            else:
                values[node.targets[0].id] = ast.literal_eval(value)
    if sorted(values) != sorted(names):
        raise ValueError(f'{Path(path).name} constants differ')
    return values


def roster(package, manifest, N):
    """The package clip files, exactly the committed manifest's clips with their checksums."""
    committed = json.loads(Path(manifest).read_bytes())
    files = {k: v for k, v in committed['files'].items() if k.startswith('animation/clips/')}
    paths = N.Bundle(package).clip_paths()
    found = {f'animation/clips/{p.parent.name}/{p.name}': p for p in paths}
    if sorted(found) != sorted(files) or len(paths) != committed['clips']:
        raise ValueError('The skate package clips differ from the committed package manifest')
    for relative, path in found.items():
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != files[relative]['sha256']:
            raise ValueError('Skate clip differs from its committed checksum: ' + relative)
    return paths


def guarded_keys(N, clip, rig, reference):
    """make_clip's count of keys moved by simulation.snap_guard."""
    guarded = 0
    for b in range(len(rig.bones)):
        rest = N.sample_to_unreal(N.runtime_sample(N.split_sample(reference.samples[b])))
        for f in range(clip.frame_count):
            guarded += N.snap_guard(N.sample_to_unreal(N.local_pose(clip, f, b, reference)), rest)[1]
    return guarded


def members(package, manifest, scripts, bank):
    """{clip: member} for every committed clip of one bank, after the complete package roster checks."""
    scripts = Path(scripts)
    N = module(scripts / 'simulation.py', 'skate_ride_simulation')
    helpers = original(scripts / 'import_clips.py', RECORDS, {'N': N, 'math': math})
    bundle = N.Bundle(package)
    rig = bundle.rig()
    reference = rig.named_pose(0, 'RIG_TPOSE')
    metadata = {c.name: c for bank in bundle.metadata() for c in bank.clips}
    paths = roster(package, manifest, N)
    if len({p.stem for p in paths}) != len(paths):
        raise ValueError('Skate clip names repeat across banks')
    result = {}
    for path in paths:
        if path.parent.name != str(bank):
            continue
        data = path.read_bytes()
        clip = N.load_clip(data)
        if clip.name != path.stem or str(clip.bank) != path.parent.name or not NAME.fullmatch(clip.name) or clip.name in result:
            raise ValueError('Skate clip identity differs from its package path: ' + path.name)
        meta = metadata.get(clip.name)
        duration, fps = clip.duration, clip.fps
        names = {a.name for a in meta.attributes} if meta else set()
        record = dict(
            bank=clip.bank, record=clip.record, fps=fps, frames=clip.frame_count, duration=duration,
            looping=bool(meta and meta.looping), phase_controlled=bool(meta and meta.phase_controlled),
            flags=f'0x{meta.flags_word:08x}' if meta else None,
            base_speed=N.as_float(meta.base_speed_bits) if meta else None,
            motion=helpers['motion_record'](clip, rig, reference), channel_weights=helpers['channel_record'](clip, rig),
            snap_guarded_keys=guarded_keys(N, clip, rig, reference),
            events=[helpers['attribute_record'](a, duration, fps) for a in meta.attributes] if meta else [],
            curves=sorted(names), mirror=dict(mirrored_attribute='MIRRORED' in names, switch_attribute='SWITCH' in names))
        result[clip.name] = {'name': clip.name, 'bank': clip.bank, 'clip': data,
                             'metadata': asdict(meta) if meta else None, 'record': record}
    return result


def clip_metadata(N, value):
    """The original ClipMetadata (with its Attributes) from its asdict form."""
    if value is None:
        return None
    attributes = [N.Attribute(**{**a, 'payload_words': tuple(a['payload_words'])}) for a in value['attributes']]
    return N.ClipMetadata(**{**value, 'attributes': attributes})


def project(package=None, manifest=None, scripts=None, output=None, bank=None):
    """@cc [owner:fontanierh,label:correctness] skate-clip-members
    Membership MUST be exactly the committed package-manifest clips, checked
    against their checksums in the complete declared package: one member per clip
    with only its own bytes, metadata record and clips.json record from the
    original helpers. No speculative member, foreign bank data or native work.
    """
    rows = members(package, manifest, scripts, bank)
    if output.exists():
        raise ValueError('Skate clip member output must be fresh')
    output.mkdir(parents=True)
    for piece, value in rows.items():
        encoded = {**value, 'clip': base64.b64encode(value['clip']).decode('ascii'),
                   'sha256': hashlib.sha256(value['clip']).hexdigest()}
        (output / (piece + '.json')).write_text(json.dumps(encoded, sort_keys=True, separators=(',', ':')) + '\n')


def rig(package=None, scripts=None, mesh=None, bundle=None):
    """The fixed views: mesh/ SK_SkateRider.glb (original rider_mesh.write_glb) and bundle/ the rig file and stats."""
    scripts = Path(scripts)
    N = module(scripts / 'simulation.py', 'skate_ride_simulation')
    rider = module(scripts / 'rider_mesh.py', 'skate_ride_rider_mesh')
    source = Path(package) / 'animation' / 'rig.skate'
    if source.is_symlink() or not source.is_file():
        raise ValueError('The skate package has no regular rig file')
    value = N.load_rig(source.read_bytes())
    if mesh.exists() or bundle.exists():
        raise ValueError('Skate rig views must be fresh')
    mesh.mkdir(parents=True); (bundle / 'animation').mkdir(parents=True)
    stats = rider.write_glb(mesh / 'SK_SkateRider.glb', value, value.named_pose(0, 'RIG_TPOSE'), N.split_sample)
    digest = hashlib.sha256((mesh / 'SK_SkateRider.glb').read_bytes()).hexdigest()
    (mesh / 'export.json').write_text(json.dumps({'primary': 'SK_SkateRider.glb', 'sha256': digest}, sort_keys=True) + '\n')
    shutil.copyfile(source, bundle / 'animation' / 'rig.skate')
    (bundle / 'stats.json').write_text(json.dumps(stats, sort_keys=True) + '\n')


def select(selected=None, destination=None, piece=None):
    """Unpack exactly the engine-selected member: member/clip.skate and member/member.json (metadata and record)."""
    found = sorted(Path(selected).iterdir()) if Path(selected).is_dir() else []
    if (len(found) != 1 or found[0].name != piece + '.json' or found[0].is_symlink() or not found[0].is_file()
            or destination.exists()):
        raise ValueError('Skate selected member must be one fresh regular <piece>.json')
    member = json.loads(found[0].read_bytes())
    data = base64.b64decode(member['clip'], validate=True)
    if member.get('name') != piece or hashlib.sha256(data).hexdigest() != member['sha256']:
        raise ValueError('Skate selected member differs from its piece or checksum')
    destination.mkdir(parents=True)
    (destination / 'clip.skate').write_bytes(data)
    (destination / 'member.json').write_text(json.dumps(
        {k: member[k] for k in ('name', 'bank', 'metadata', 'record')}, sort_keys=True) + '\n')
