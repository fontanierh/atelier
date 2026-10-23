"""Complete Southwest export, native and logical placement membership."""
import json
import math
from pathlib import Path
import re

from atelier.atomic_files import atomic_json
from atelier.export_manifest import real_directory, sha
from atelier.model_files import regular_files

PARENTS = ('SW_CoconutStand', 'SW_FisherHouseA', 'SW_FisherHouseB', 'SW_BoatShed',
           'SW_StoneStairs', 'SW_Dock', 'SW_Boat', 'SW_DryingRack', 'SW_Temple', 'SW_Island',
           'SW_Boulder_A', 'SW_Boulder_B', 'SW_Boulder_C', 'SW_StoneWall', 'Tree_PineLean_A', 'Tree_PineLean_B')
DESTINATION = '/Game/Japan/Southwest/Pieces'


def owned(name, parent):
    return name == parent or re.fullmatch(re.escape(parent) +
        r'_cell_(?:0|-?[1-9][0-9]*)_(?:0|-?[1-9][0-9]*)(?:_Piece[0-3]{1,16})?', name) is not None


def _bounds(value):
    return (isinstance(value, list) and len(value) == 2 and all(isinstance(row, list) and len(row) == 3
        and all(type(v) in (int, float) and math.isfinite(v) for v in row) for row in value)
        and all(a <= b for a, b in zip(*value)))


def validate_runtime(value):
    """@cc [owner:fontanierh,label:correctness] southwest-complete-native-membership
    Every original logical parent, including both Tree_PineLean names, MUST select a
    complete nonempty bounded native union. Case-fold aliases, partial inventories,
    foreign children, inconsistent totals or non-finite bounds MUST refuse. No old
    whole-parent asset may be loaded as a fallback. Original placement keys and union
    bounds own visibility/fade; every child retains the same authored local frame.
    """
    if (not isinstance(value, dict) or set(value) != {'version', 'complete', 'triangle_limit', 'parents'}
            or value['version'] != 1 or value['complete'] is not True or value['triangle_limit'] != 32768
            or not isinstance(value['parents'], dict) or set(value['parents']) != set(PARENTS)):
        raise ValueError('Incomplete Southwest runtime membership')
    seen = set()
    for parent, row in value['parents'].items():
        if (set(row) != {'source_triangles', 'bounds', 'pieces'} or not _bounds(row['bounds'])
                or type(row['source_triangles']) is not int or row['source_triangles'] < 1
                or not isinstance(row['pieces'], list) or not row['pieces']):
            raise ValueError('Invalid Southwest logical source')
        total = 0
        for piece in row['pieces']:
            if (set(piece) != {'name', 'triangles'} or not isinstance(piece['name'], str)
                    or not owned(piece['name'], parent) or piece['name'].casefold() in seen
                    or type(piece['triangles']) is not int or not 0 < piece['triangles'] <= 32768):
                raise ValueError('Invalid Southwest bounded native piece')
            seen.add(piece['name'].casefold()); total += piece['triangles']
        if total != row['source_triangles']:
            raise ValueError('Southwest piece triangle conservation failed')
    return value


def exports(out):
    """Read the exact completed file-only assembly and all original planner ownership."""
    root = real_directory(Path(out) / 'atomic_regions/southwest')
    real_directory(root / 'assets')
    for path in (root / 'logical-pieces.json', root / 'assets/manifest.json'):
        if path.is_symlink() or not path.is_file():
            raise ValueError('Missing regular Southwest assembly manifest')
    logical = json.loads((root / 'logical-pieces.json').read_text())
    manifest = json.loads((root / 'assets/manifest.json').read_text())
    if (logical.get('schema') != 1 or set(logical.get('parents', {})) != set(PARENTS)
            or set(logical.get('ownership', {})) != set(PARENTS)
            or manifest.get('schema') != 1 or manifest.get('complete') is not True):
        raise ValueError('Incomplete Southwest assembly')
    receipts, seen = {}, set()
    for row in manifest['exports']:
        key = row['asset']
        if not isinstance(key, str) or key.casefold() in seen or row['primary'] != key + '.fbx':
            raise ValueError('Duplicate or non-FBX Southwest export')
        seen.add(key.casefold()); receipts[key] = row
    if regular_files(root / 'assets') != {'manifest.json', *(row['primary'] for row in receipts.values())}:
        raise ValueError('Foreign or incomplete Southwest assembly files')
    if set(logical['exports']) != set(receipts) or len(logical['exports']) != len(receipts):
        raise ValueError('Southwest export roster differs from assembly')
    runtime = dict(version=1, complete=True, triangle_limit=32768, parents={})
    selected = []
    identity = [[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]
    for parent in PARENTS:
        source = logical['ownership'][parent]
        if (source['matrix'] != identity or source['slots'] != ['Southwest_Palette']
                or source['source_collision_hulls'] != 0 or not source['pieces']):
            raise ValueError('Southwest source frame/material/effective collision changed')
        if logical['parents'][parent] != [r['name'] for r in source['pieces']]:
            raise ValueError('Southwest parent membership differs from its source')
        pieces, lower, upper = [], [float('inf')]*3, [-float('inf')]*3
        for row in source['pieces']:
            key = row['name']; receipt = receipts[key]
            bounds = receipt['bounds']
            if (row['collision_hulls'] != 0 or receipt['triangles'] != row['triangles']
                    or bounds != [row['min'], row['max']] or not _bounds(bounds)
                    or receipt['metadata']['slots'] != ['Southwest_Palette']
                    or receipt['metadata']['uv_channels'] != ['UVMap']
                    or receipt['metadata']['collision_hulls'] != 0):
                raise ValueError('Southwest piece geometry metadata changed')
            path = root / 'assets' / receipt['primary']
            if path.is_symlink() or not path.is_file() or sha(path) != receipt['sha256']:
                raise ValueError('Southwest export bytes differ from completed assembly')
            pieces.append(dict(name=key, triangles=row['triangles']))
            selected.append((parent, row, receipt, path))
            lower = [min(a,b) for a,b in zip(lower,bounds[0])]
            upper = [max(a,b) for a,b in zip(upper,bounds[1])]
        runtime['parents'][parent] = dict(source_triangles=source['source_triangles'], bounds=[lower,upper], pieces=pieces)
    if len(selected) != len(receipts):
        raise ValueError('Foreign Southwest assembled exports')
    return validate_runtime(runtime), selected


def assemble(out, log):
    runtime, _ = exports(out)
    atomic_json(Path(out) / 'southwest/runtime.json', runtime)
    log.write('Southwest complete logical membership: ' + str(sum(len(v['pieces']) for v in runtime['parents'].values())) + ' independent meshes\n')
    return runtime


def native_inventory(editor):
    result, seen = set(), set()
    for asset in editor.list_assets(DESTINATION, recursive=True, include_folder=False):
        if not isinstance(asset, str) or not asset.startswith(DESTINATION + '/'):
            raise ValueError('Southwest native inventory escaped its owner')
        relative = asset[len(DESTINATION)+1:]; key = relative.split('.')[0]
        if (asset not in (DESTINATION+'/'+key, DESTINATION+'/'+key+'.'+key)
                or not any(owned(key,parent) for parent in PARENTS) or key.casefold() in seen):
            raise ValueError('Foreign Southwest native package')
        seen.add(key.casefold()); result.add(DESTINATION+'/'+key)
    return result


def native_files(content):
    """Complete fixed native owner inventory, including every supported package sidecar."""
    root = real_directory(Path(content) / 'Japan/Southwest/Pieces')
    files = regular_files(root) if root.exists() else set()
    allowed = {'.uasset', '.uexp', '.ubulk', '.uptnl'}
    for relative in files:
        path = Path(relative)
        if len(path.parts) != 1 or path.suffix not in allowed or not any(owned(path.stem,parent) for parent in PARENTS):
            raise ValueError('Foreign files in Southwest native owner')
    return tuple(root / relative for relative in sorted(files))
