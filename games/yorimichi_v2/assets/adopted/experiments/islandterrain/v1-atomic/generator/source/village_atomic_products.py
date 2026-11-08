"""Complete Village source/primary/native ownership with unchanged whole authored hulls."""
import json
from pathlib import Path
import re
import sys

from atelier.atomic_files import atomic_json
from atelier.conventions import to_unreal
from atelier.export_manifest import name, real_directory, sha, TRIANGLE_LIMIT
from atelier.model_files import regular_files

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / 'world'))
sys.path.insert(0, str(Path(__file__).resolve().parent / 'world/regions'))
from village.catalogue import ASSETS  # noqa: E402
from city_tile_products import native_bounds, collision_matches  # noqa: E402,F401

DESTINATION = '/Game/Experiments/VillageAtomic/v1_atomic'
MATERIAL = '/Game/Japan/Materials/M_Village'


def ground_native_count(metadata, piece):
    """Project only unambiguous ground FBX degenerate removal, preserving exported faces.

    Installed FbxStaticMeshImport.cpp tests the squared float32 cross product
    against SMALL_NUMBER (1e-8). Native/source counts remain separate: no face
    is removed from the source payload or serialized FBX. Only already triangular
    source polygons qualify; n-gons retain their full n-2 expected count. Borderline
    triangular cases require a stronger proof and refuse.
    """
    import numpy as np
    matrix = np.asarray(metadata['matrix'])
    points = piece['positions'] @ matrix[:3, :3].T + matrix[:3, 3]
    points = np.asarray([to_unreal(point) for point in points], dtype=np.float32)
    removed = []
    for index, face in enumerate(piece['faces']):
        if len(face) != 3: continue
        a, b, c = points[list(face)]
        normal = np.cross(b-c, a-c)
        squared = float(np.dot(normal, normal))
        if squared <= 2.5e-9:
            removed.append(index)
        elif squared <= 4e-8:
            raise ValueError('Borderline Village legacy FBX degeneracy')
    return dict(native_triangles=piece['triangles']-len(removed), native_removed_polygons=removed)


def owned(key, parent):
    return key == parent or re.fullmatch(re.escape(parent) + r'_cell_-?\d+_-?\d+(?:_Piece[0-3]{1,16})?', key) is not None


def assemble(out):
    """@cc [owner:fontanierh,label:correctness;performance] complete-independent-village-assembly
    Current Village membership MUST come from all twelve selected constructors, with
    complete original corner attributes, unmodified placements and whole authored hull
    ownership. Assembly MUST preserve primary bytes without joining/exporting geometry, and
    MUST preserve each logical parent's collision mode even on zero-hull render leaves.
    Old whole FBX files MUST NOT supply missing children or enter current native inputs.
    """
    import numpy as np
    from atelier import mesh_ir
    from region_mesh_parts import validate
    out = Path(out)
    root = real_directory(out / 'atomic_regions/village')
    logical = json.loads((root / 'logical-pieces.json').read_text())
    exports = json.loads((root / 'assets/manifest.json').read_text())
    if set(logical.get('parents', {})) != set(ASSETS) or exports.get('complete') is not True:
        raise ValueError('Incomplete normal Village logical assembly')
    receipts = {row['asset']: row for row in exports['exports']}
    if len(receipts) != len(exports['exports']): raise ValueError('Duplicate Village source export')
    placement = json.loads((out / 'village-source-data/placements.json').read_text())
    if placement.get('schema') != 1 or set(placement.get('instances', {})) != set(ASSETS):
        raise ValueError('Incomplete Village placement inventory')
    groups = {}
    for parent in ASSETS:
        plan_root = out / 'planned_exports/village' / parent
        plan = validate(plan_root)
        if (plan['parent'] != parent or plan['slots'] != ['VillagePalette']
                or logical['parents'][parent] != [row['name'] for row in plan['pieces']]):
            raise ValueError('Village plan differs from its original material/member owner')
        first, _ = mesh_ir.decode((plan_root / plan['pieces'][0]['payload']).read_bytes())
        hulls = []
        for hull in first['collisions']:
            transform = np.asarray(hull['matrix'])
            vertices = np.asarray(hull['vertices']) @ transform[:3, :3].T + transform[:3, 3]
            hulls.append([[float(value) for value in to_unreal(point)] for point in vertices])
        pieces = []
        for row in plan['pieces']:
            metadata, source_piece = mesh_ir.decode((plan_root / row['payload']).read_bytes())
            native_projection = (ground_native_count(metadata, source_piece) if parent == 'Village_Ground'
                                 else dict(native_triangles=row['triangles'], native_removed_polygons=[]))
            receipt = receipts.get(row['name'], {})
            if (receipt.get('primary') != row['name'] + '.fbx' or receipt.get('triangles') != row['triangles']
                    or receipt.get('bounds') != [row['min'], row['max']]
                    or receipt.get('metadata', {}).get('geometry_sha256') != row['sha256']
                    or receipt['metadata'].get('slots') != plan['slots']
                    or receipt['metadata'].get('collision_hulls') != row['collision_hulls']):
                raise ValueError('Village primary differs from its complete source geometry')
            pieces.append({key: row[key] for key in ('name', 'triangles', 'min', 'max', 'collision_hulls')}
                          | dict(sha256=receipt['sha256'], geometry_sha256=row['sha256'],
                                 uv_channels=receipt['metadata']['uv_channels']))
            pieces[-1].update(native_projection)
            primary = root / 'assets' / receipt['primary']
            if primary.is_symlink() or not primary.is_file() or sha(primary) != receipt['sha256']:
                raise ValueError('Village assembled primary bytes changed')
        groups[parent] = dict(source_triangles=plan['source_triangles'], source_collision_hulls=plan['source_collision_hulls'],
                              source_collision_vertices=hulls, slots=plan['slots'], pieces=pieces,
                              collision='complex_as_simple' if parent == 'Village_Ground' else 'simple_and_complex')
    if set(receipts) != {row['name'] for group in groups.values() for row in group['pieces']}:
        raise ValueError('Foreign Village export inventory')
    if regular_files(root / 'assets') != {'manifest.json', *(key + '.fbx' for key in receipts)}:
        raise ValueError('Village assembled primary set is incomplete or foreign')
    value = dict(schema=1, complete=True, parents=groups)
    atomic_json(out / 'village/atomic-manifest.json', value)
    runtime = dict(schema=1, complete=True, parents={parent: dict(
        assets=[DESTINATION + '/' + row['name'] for row in group['pieces']],
        instances=placement['instances'][parent], collision=group['collision']) for parent, group in groups.items()})
    atomic_json(out / 'village/pieces.json', runtime)
    return value


def read(out):
    out = Path(out)
    root = real_directory(out / 'village')
    path = root / 'atomic-manifest.json'
    if path.is_symlink() or not path.is_file(): raise ValueError('Missing current Village atomic manifest')
    value = json.loads(path.read_text())
    groups = value.get('parents')
    if value.get('schema') != 1 or value.get('complete') is not True or not isinstance(groups, dict) or set(groups) != set(ASSETS):
        raise ValueError('Incomplete current Village source families')
    assets = real_directory(out / 'atomic_regions/village/assets')
    library_manifest = assets / 'manifest.json'
    if library_manifest.is_symlink() or not library_manifest.is_file(): raise ValueError('Missing Village primary receipt inventory')
    library = json.loads(library_manifest.read_text())
    if library.get('schema') != 1 or library.get('complete') is not True or not isinstance(library.get('exports'), list):
        raise ValueError('Incomplete Village primary receipts')
    receipts = {row['asset']: row for row in library['exports']}
    if len(receipts) != len(library['exports']): raise ValueError('Duplicate Village primary receipts')
    expected, seen = {'manifest.json'}, set()
    for parent in ASSETS:
        group = groups[parent]
        if (group.get('slots') != ['VillagePalette'] or group.get('collision') != (
                'complex_as_simple' if parent == 'Village_Ground' else 'simple_and_complex')
                or not isinstance(group.get('pieces'), list) or not group['pieces']
                or type(group.get('source_collision_hulls')) is not int or group['source_collision_hulls'] < 0
                or len(group.get('source_collision_vertices', [])) != group['source_collision_hulls']):
            raise ValueError('Village original collision/material policy differs')
        triangles = hulls = 0
        for index, row in enumerate(group['pieces']):
            key = name(row['name'])
            removed = row.get('native_removed_polygons')
            polygons = receipts.get(key, {}).get('metadata', {}).get('polygons')
            if (not owned(key, parent) or key.casefold() in seen or type(row.get('triangles')) is not int
                    or not 0 < row['triangles'] <= TRIANGLE_LIMIT
                    or row.get('collision_hulls') != (group['source_collision_hulls'] if index == 0 else 0)
                    or type(row.get('native_triangles')) is not int or not 0 < row['native_triangles'] <= row['triangles']
                    or type(polygons) is not int or not 0 < polygons <= row['triangles']
                    or not isinstance(removed, list) or any(type(i) is not int or not 0 <= i < polygons for i in removed)
                    or len(removed) != row['triangles'] - row['native_triangles'] or len(set(removed)) != len(removed)
                    or row.get('uv_channels') != ['UVMap']):
                raise ValueError('Unbounded, foreign or duplicate Village piece')
            seen.add(key.casefold()); expected.add(key + '.fbx')
            native_bounds(row)
            receipt = receipts.get(key, {})
            if (receipt.get('primary') != key + '.fbx' or receipt.get('triangles') != row['triangles']
                    or receipt.get('sha256') != row.get('sha256') or receipt.get('bounds') != [row['min'], row['max']]
                    or receipt.get('metadata', {}).get('slots') != ['VillagePalette']
                    or receipt['metadata'].get('collision_hulls') != row['collision_hulls']
                    or receipt['metadata'].get('uv_channels') != ['UVMap']
                    or receipt['metadata'].get('geometry_sha256') != row.get('geometry_sha256')
                    or not isinstance(row.get('geometry_sha256'), str)
                    or not re.fullmatch('[0-9a-f]{64}', row['geometry_sha256'])):
                raise ValueError('Village primary receipt differs from source ownership')
            path = assets / (key + '.fbx')
            if path.is_symlink() or not path.is_file() or sha(path) != row.get('sha256'):
                raise ValueError('Village bounded source bytes changed')
            triangles += row['triangles']; hulls += row['collision_hulls']
        if triangles != group.get('source_triangles') or hulls != group['source_collision_hulls']:
            raise ValueError('Incomplete Village logical geometry/collision union')
    if regular_files(assets) != expected or set(receipts) != {key[:-4] for key in expected if key.endswith('.fbx')}:
        raise ValueError('Foreign or missing Village primary member')
    return groups
