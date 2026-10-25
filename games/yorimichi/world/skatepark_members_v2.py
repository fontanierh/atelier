"""Project actual Sunset Pier texture/spec members and validate the final runtime source join."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil

from craterpark_members_v2 import _file, _root, read_json

SURFACES = {'concrete', 'ceramic', 'steel', 'wood', 'basalt', 'mural'}
ROLES = ('albedo', 'normal', 'roughness')
KEY = re.compile(r'[a-z][a-z0-9_]*\Z')


def specifications(root):
    value = read_json(_file(root, 'textures.json'))
    if set(value) != SURFACES:
        raise ValueError('Sunset Pier texture producer has an unknown or missing surface')
    expected = {'textures.json'}
    for key, spec in value.items():
        roles = {'albedo'} if key == 'mural' else set(ROLES)
        if (set(spec['maps']) != roles or set(spec['sha256']) != roles
                or type(spec['metallic']) not in (int, float) or spec['metallic'] != float(key == 'steel')):
            raise ValueError('Sunset Pier texture roles/metallic differ from the original finish')
        for role, member in spec['maps'].items():
            if member != key + '-' + role + '.png':
                raise ValueError('Sunset Pier producer changed its exact image membership')
            path = _file(root, member)
            if hashlib.sha256(path.read_bytes()).hexdigest() != spec['sha256'][role]:
                raise ValueError('Changed Sunset Pier produced pixels')
            expected.add(member)
    if {p.name for p in root.iterdir()} != expected:
        raise ValueError('Sunset Pier texture ROOT has extra or missing members')
    value['painted'] = {**deepcopy(value['steel']), 'metallic': 0.}
    return value


def project(source=None, output=None, kind=None):
    if kind not in ('materials', *ROLES) or output.exists():
        raise ValueError('Unknown Sunset Pier member role or existing output')
    output.mkdir(parents=True)
    scratch = output / '.source'
    try:
        root = _root(source, scratch)
        specs = specifications(root)
        for key, entry in specs.items():
            if kind == 'materials':
                (output / (key + '.json')).write_text(json.dumps({'key': key, 'entry': entry}, sort_keys=True, allow_nan=False) + '\n')
            elif kind in entry['maps']:
                shutil.copyfile(_file(root, entry['maps'][kind]), output / (key + '_' + kind + '.png'))
    finally:
        if scratch.exists(): shutil.rmtree(scratch)


def select(source=None, output=None, piece=None, extension=None):
    source, output = Path(source), Path(output)
    if not KEY.fullmatch(piece) or extension not in ('.json', '.png') or output.exists():
        raise ValueError('Foreign selected Sunset Pier member')
    if {p.name for p in source.iterdir()} != {piece + extension}:
        raise ValueError('Selected Sunset Pier Item has extra or missing members')
    member = _file(source, piece + extension)
    output.mkdir(parents=True)
    shutil.copyfile(member, output / member.name)


def complete(build_archive=None, runtime_archive=None, logical=None, park=(), board=(), trees=(), output=None):
    """Require original runtime/source ownership and the complete current native member roster."""
    from skatepark.pieces import runtime_park
    output = Path(output)
    if output.exists(): raise ValueError('Sunset Pier native summary must be fresh')
    output.mkdir(parents=True)
    source, runtime_file = Path(build_archive), Path(runtime_archive)
    if any(path.is_symlink() or not path.is_file() for path in (source, runtime_file)):
        raise ValueError('Sunset Pier requires decoded original build/runtime ROOTs')
    build, runtime, authored = read_json(source), read_json(runtime_file), read_json(logical)
    if (hashlib.sha256(logical.read_bytes()).hexdigest() != build['identity']['park_json_sha256']
            or hashlib.sha256(runtime_file.read_bytes()).hexdigest() != build['identity']['runtime_park_sha256']
            or runtime != runtime_park(authored, build['pieces']['members'])):
        raise ValueError('Sunset Pier runtime membership differs from the exact original logical/source contract')
    expected = {row['name']: row for row in runtime['meshes']}
    if len(expected) != len(runtime['meshes']): raise ValueError('Duplicate Sunset Pier runtime owner')
    expected_exports = {'assets/' + name + '.fbx' for name in expected}
    expected_exports.update('board/' + name + '.fbx' for name in ('SM_SkateDeck', 'SM_SkateTruck', 'SM_SkateWheel'))
    if set(build['identity']['exports']) != expected_exports:
        raise ValueError('Sunset Pier source build has a foreign or incomplete export roster')
    rows = []
    for values, names, is_board in ((park, set(expected), False), (board, {'SM_SkateDeck', 'SM_SkateTruck', 'SM_SkateWheel'}, True)):
        found = set()
        for child, piece in values:
            if piece in found or piece not in names: raise ValueError('Foreign/duplicate Sunset Pier native owner')
            found.add(piece)
            report = read_json(_file(child.products[0].paths[0], 'data/reports/' + piece + '.json'))
            if (report['name'] != piece or report['triangles'] != build['meshes'][piece]['triangles']
                    or report['blocks'] is not (False if is_board else expected[piece]['blocks'])
                    or report['board'] is not is_board
                    or set(report['materials']) != set(build['material_slots'][piece])
                    or report['source_sha256'] != build['identity']['exports'][('board/' if is_board else 'assets/') + piece + '.fbx']):
                raise ValueError('Sunset Pier native member differs from runtime source')
            rows.append(report)
        if found != names: raise ValueError('Incomplete Sunset Pier current native membership')
    tree_roster = set(runtime.get('trees', {}))
    if set(trees) != tree_roster: raise ValueError('Missing explicit native island tree owner')
    for name, path in trees.items():
        _file(path, 'content/Game/Japan/Assets/' + name + '.uasset')
    (output / 'native.json').write_text(json.dumps({'meshes': rows, 'trees': sorted(tree_roster)}, sort_keys=True) + '\n')
