"""Finite members of the original complete coastal library; no receiver discovery."""
import hashlib
import json
import math
from pathlib import Path
import re
import shutil

from atelier import encoded_glb
from craterpark_members_v2 import _file, read_json
from brinecove_material_v2 import descriptor

NAME = re.compile(r'[A-Za-z][A-Za-z0-9_-]*\Z')
ROOT = '/Game/Brinecove'


def texture_names(materials):
    result = set()
    for entry in materials.values():
        if entry.get('texture'): result.add(entry['texture'])
        for field in ('layers', 'normals'):
            result.update(entry.get(field, {}).values())
    return result


def library(report, runtime, textures):
    report, runtime = read_json(report), read_json(runtime)
    materials = report['materials']
    if not isinstance(materials, dict) or not materials:
        raise ValueError('Missing complete coastal material roster')
    for key, entry in materials.items():
        if not isinstance(key, str) or not NAME.fullmatch(key) or descriptor(entry)['name'] != 'MI_BC_' + key:
            raise ValueError('Coastal descriptor identity differs')
    names = texture_names(materials)
    auxiliary = report.get('auxiliary_textures', {})
    if not isinstance(auxiliary, dict) or names & auxiliary.keys():
        raise ValueError('Aliased coastal auxiliary ownership')
    for name in names | auxiliary.keys():
        if (not isinstance(name, str) or Path(name).name != name or not NAME.fullmatch(Path(name).stem)
                or not name.startswith('T_BC_') or Path(name).suffix not in ('.png', '.jpg')):
            raise ValueError('Invalid coastal texture member')
        path = _file(textures, name)
        if name in auxiliary and hashlib.sha256(path.read_bytes()).hexdigest() != auxiliary[name]:
            raise ValueError('Changed coastal auxiliary texture')
    if {p.name for p in textures.iterdir()} != names | auxiliary.keys():
        raise ValueError('Incomplete or foreign coastal texture ROOT')
    meshes = {}
    for row in report['meshes']:
        name = row['name']
        if (not NAME.fullmatch(name) or not name.startswith('SM_BC_') or name in meshes
                or row['path'] != 'glb/' + name + '.glb' or type(row['collision']) is not bool
                or ('lods' in row and type(row['lods']) is not bool)
                or not row['slots'] or set(row['slots']) - materials.keys()
                or len(row['slots']) != len(set(row['slots']))):
            raise ValueError('Invalid original coastal mesh membership')
        meshes[name] = row
    if not meshes or len({n.casefold() for n in meshes}) != len(meshes):
        raise ValueError('Empty or aliased coastal mesh roster')
    used = set()
    for group in runtime['groups']:
        path = group['asset']; name = path.rsplit('/', 1)[-1].split('.')[0]
        if name not in meshes or path != ROOT + '/Meshes/' + name + '.' + name:
            raise ValueError('Foreign coastal runtime mesh')
        row = meshes[name]
        expected = [ROOT + '/Materials/MI_BC_' + key + '.MI_BC_' + key for key in row['slots']]
        if group['materials'] != expected or group['collision'] is not row['collision']:
            raise ValueError('Coastal runtime policy differs from source report')
        used.add(name)
    if used != set(meshes): raise ValueError('Incomplete coastal runtime membership')
    return report, runtime, meshes


def project(report=None, runtime=None, textures=None, glb=None, output=None, kind=None):
    """@cc [owner:fontanierh,label:correctness] original-coastal-fileset-members
    Every member MUST come from the declared complete original library/report and
    runtime roster. Preserve actual descriptors and texture bytes, losslessly wrap
    original meshes with their explicit source collision/LOD/material policy.
    Validate complete membership and source digests before writing; never discover
    ambient generated files or synthesize a missing material or source owner.
    """
    report, _, meshes = library(report, runtime, textures)
    if kind not in ('materials', 'textures', 'meshes') or output.exists():
        raise ValueError('Unknown coastal projection or existing output')
    values = {}
    if kind == 'materials':
        values = {entry['name'] + '.json': (json.dumps({'key': key, 'descriptor': entry}, sort_keys=True, allow_nan=False) + '\n').encode()
                  for key, entry in report['materials'].items()}
    elif kind == 'textures':
        # Keep the source extension inside each one-member texture packet.
        values = {name: _file(textures, name).read_bytes() for name in texture_names(report['materials'])}
    else:
        if {p.name for p in glb.iterdir()} != {name + '.glb' for name in meshes}:
            raise ValueError('Incomplete or foreign coastal GLB ROOT')
        for name, row in meshes.items():
            raw = _file(glb, name + '.glb').read_bytes()
            if hashlib.sha256(raw).hexdigest() != row['sha256']:
                raise ValueError('Changed coastal source GLB')
            policy = {'collision': row['collision'], 'lods': row.get('lods', False),
                      'material_kinds': {'BC_' + key: report['materials'][key]['kind'] for key in row['slots']}}
            packet = encoded_glb.encode(raw, key=name, metadata={'native_policy': policy})
            identity, _ = encoded_glb.decode(packet, key=name)
            if (identity['triangles'] != row['triangles'] or identity['bounds'] != row['bounds_m']
                    or identity['slots'] != ['BC_' + key for key in row['slots']]):
                raise ValueError('Coastal GLB differs from complete original report')
            values[name + '.mesh'] = packet
    if len({Path(n).stem.casefold() for n in values}) != len(values):
        raise ValueError('Aliased coastal selected members')
    output.mkdir(parents=True)
    for name, raw in values.items(): (output / name).write_bytes(raw)


def select(source=None, output=None, piece=None, kind=None):
    if not NAME.fullmatch(piece) or kind not in ('materials', 'textures', 'meshes') or output.exists():
        raise ValueError('Invalid selected coastal member')
    extensions = ('.mesh',) if kind == 'meshes' else ('.png', '.jpg') if kind == 'textures' else ('.json',)
    names = {p.name for p in source.iterdir()}
    if len(names) != 1 or next(iter(names)) not in {piece + ext for ext in extensions}:
        raise ValueError('Selected coastal Item has extra or missing members')
    member = _file(source, next(iter(names)))
    output.mkdir(parents=True)
    if kind == 'meshes':
        encoded_glb.export(member, output)
        receipt = read_json(output / 'export.json')
        receipt['metadata']['payload_sha256'] = hashlib.sha256(member.read_bytes()).hexdigest()
        (output / 'export.json').write_text(json.dumps(receipt, sort_keys=True, allow_nan=False) + '\n')
    elif kind == 'textures':
        raw = member.read_bytes(); filename = member.name
        shutil.copyfile(member, output / filename)
        (output / 'export.json').write_text(json.dumps({'primary': filename, 'sha256': hashlib.sha256(raw).hexdigest()}, sort_keys=True) + '\n')
    else:
        spec = read_json(member)
        if descriptor(spec['descriptor'])['name'] != piece or piece != 'MI_BC_' + spec['key']:
            raise ValueError('Selected coastal descriptor identity differs')
        shutil.copyfile(member, output / member.name)


def complete(report=None, runtime=None, textures=None, meshes=(), materials=(), images=(), reports=(), output=None):
    """Require the original runtime/report roster and actual finished native Items."""
    report, runtime, expected = library(report, runtime, textures)
    rosters = ((meshes, set(expected), ROOT + '/Meshes/'),
               (materials, {d['name'] for d in report['materials'].values()}, ROOT + '/Materials/'),
               (images, {Path(n).stem for n in texture_names(report['materials'])}, ROOT + '/Textures/'))
    for members, names, prefix in rosters:
        found = set()
        for child, piece in members:
            if piece in found or piece not in names: raise ValueError('Foreign or duplicate coastal native Item')
            found.add(piece)
            _file(child.products[0].paths[0], 'content/Game/' + prefix.removeprefix('/Game/') + piece + '.uasset')
        if found != names: raise ValueError('Incomplete coastal finished native roster')
    imported = {}
    for child, piece in reports:
        if piece in imported or piece not in expected: raise ValueError('Foreign coastal native report')
        observed = read_json(_file(child.products[0].paths[0], 'data/reports/' + piece + '.json'))
        row = expected[piece]
        low, high = row['bounds_m']
        bounds = [low[0] * 100, -high[1] * 100, low[2] * 100, high[0] * 100, -low[1] * 100, high[2] * 100]
        actual = observed.get('bounds_cm')
        if (observed.get('name') != piece or not row['triangles'] * .98 <= observed.get('triangles', -1) <= row['triangles']
                or observed.get('collision') is not row['collision'] or observed.get('lods') is not row.get('lods', False)
                or observed.get('slots') != ['BC_' + key for key in row['slots']]
                or type(observed.get('uv_channels')) is not int or observed['uv_channels'] < 0
                or not isinstance(actual, list) or len(actual) != 6
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in actual)
                or any(abs(a-b) >= 2. for a, b in zip(actual, bounds))):
            raise ValueError('Coastal native report differs from current source policy/geometry')
        imported[piece] = {key: observed[key] for key in ('triangles', 'bounds_cm', 'collision')}
    if set(imported) != set(expected): raise ValueError('Incomplete coastal native report roster')
    if output.exists(): raise ValueError('Coastal summary must be fresh')
    output.mkdir(parents=True)
    (output / 'runtime.json').write_text(json.dumps(runtime, sort_keys=True, allow_nan=False) + '\n')
    (output / 'import-report.json').write_text(json.dumps(imported, sort_keys=True, allow_nan=False) + '\n')
    (output / 'native.json').write_text(json.dumps({'meshes': sorted(expected), 'materials': sorted(report['materials'])}, sort_keys=True) + '\n')
