"""Complete island receiving inventory over separately cached bounded primary exports."""
import json
import math
from pathlib import Path
import re

from atelier.export_manifest import TRIANGLE_LIMIT, name, real_directory, sha
from atelier.model_files import regular_files

PARENTS = ('Terrain', 'Road', 'Lane', 'Guardrail', 'Wires', 'FarHills', 'Sea')
REQUIRED = {'Terrain', 'Road', 'Wires', 'FarHills', 'Sea'}
DESTINATION = '/Game/Experiments/IslandTerrain/v1_atomic'
MATERIALS = dict(Terrain=('Ground', 'Coast'), Road=('Road',), Lane=('Sand',),
                 Guardrail=('Paint',), Wires=('Metal',), FarHills=('FarForest', 'CoastRock'), Sea=('Water',))
IDENTITY = [[1., 0., 0., 0.], [0., 1., 0., 0.], [0., 0., 1., 0.], [0., 0., 0., 1.]]


def material_paths(parent, slots):
    if (parent not in PARENTS or not isinstance(slots, list) or not slots
            or len(set(slots)) != len(slots) or any(slot not in MATERIALS[parent] for slot in slots)
            or slots != [slot for slot in MATERIALS[parent] if slot in slots]):
        raise ValueError('Island material ownership differs from the original constructor')
    if parent != 'FarHills' and slots != list(MATERIALS[parent]):
        raise ValueError('Missing original island material slots')
    if parent == 'FarHills' and slots[0] != 'FarForest':
        raise ValueError('Missing original FarHills ground material')
    return {slot: '/Game/Japan/Materials/MI_' + slot for slot in slots}


def native_path(key):
    return DESTINATION + '/' + name(key)


def native_bounds(piece):
    """Original Blender axis conversion: metres xyz -> UE centimetres x,-y,z."""
    return ([piece['min'][0]*100., -piece['max'][1]*100., piece['min'][2]*100.],
            [piece['max'][0]*100., -piece['min'][1]*100., piece['max'][2]*100.])


def source_metadata(out):
    """Project used material identities from complete bounded inputs before receiving.

    UE may compact unused source slots. The receiving owner needs the exact used
    slot set, not a requirement to retain an unused slot on every spatial piece.
    This cheap data assembly never constructs/exports geometry or joins pieces.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent / 'world'))
    from atelier import mesh_ir
    from region_mesh_parts import validate
    folder = real_directory(Path(out) / 'atomic_regions/island')
    logical = json.loads((folder / 'logical-pieces.json').read_text())
    records = {}
    for parent in logical['parents']:
        if parent not in PARENTS: raise ValueError('Foreign island source metadata owner')
        root = Path(out) / 'planned_exports/island' / parent
        plan = validate(root)
        if (plan['parent'] != parent or logical['parents'][parent] != [row['name'] for row in plan['pieces']]
                or plan['slots'] != logical['ownership'][parent]['slots']):
            raise ValueError('Island source metadata differs from complete assembly')
        for row in plan['pieces']:
            meta, piece = mesh_ir.decode((root / row['payload']).read_bytes())
            used = {int(index) for index in piece['materials']}
            records[row['name']] = dict(geometry_sha256=row['sha256'],
                used_slots=[slot for i, slot in enumerate(meta['slots']) if i in used])
    return dict(schema=1, complete=True, pieces=records)


def read(out):
    """@cc [owner:fontanierh,label:correctness] complete-island-receiving-membership
    Admit only the complete explicit current island roster, with unchanged independent
    primary bytes, bounded counts, original material table, authored origin, and exact
    per-parent render membership. No parent FBX or missing sibling fallback is allowed.
    This inventory MUST NOT replace current native cook/material/UV/bounds validation.
    Sea remains a separate nonblocking owner; every other parent keeps the original
    complex-as-simple collision semantics on its own unchanged triangle union.
    """
    out = Path(out)
    source_root = real_directory(out / 'island-source-data')
    source_path = source_root / 'inventory.json'
    if source_path.is_symlink() or not source_path.is_file():
        raise ValueError('Missing current island source roster')
    sources = json.loads(source_path.read_text())
    folder = real_directory(out / 'atomic_regions/island')
    assets = real_directory(folder / 'assets')
    for path in (folder / 'logical-pieces.json', assets / 'manifest.json', folder / 'receiving.json'):
        if path.is_symlink() or not path.is_file(): raise ValueError('Missing island assembled inventory')
    logical = json.loads((folder / 'logical-pieces.json').read_text())
    manifest = json.loads((assets / 'manifest.json').read_text())
    receiving = json.loads((folder / 'receiving.json').read_text())
    parents, owners = logical.get('parents'), logical.get('ownership')
    if (logical.get('schema') != 1 or not isinstance(parents, dict) or not REQUIRED <= set(parents)
            or set(parents) - set(PARENTS) or not isinstance(owners, dict) or set(owners) != set(parents)
            or sources != dict(schema=1, assets=[key for key in PARENTS if key in parents])
            or manifest.get('schema') != 1 or manifest.get('complete') is not True
            or not isinstance(manifest.get('exports'), list) or not manifest['exports']):
        raise ValueError('Missing or foreign island logical ownership')
    rows = manifest['exports']
    receipts = {row['asset']: row for row in rows}
    expected = [key for parent in PARENTS if parent in parents for key in parents[parent]]
    if (len(receipts) != len(rows) or len(set(key.casefold() for key in expected)) != len(expected)
            or set(receipts) != set(expected) or logical.get('exports') != expected
            or receiving.get('schema') != 1 or receiving.get('complete') is not True
            or not isinstance(receiving.get('pieces'), dict) or set(receiving['pieces']) != set(expected)
            or regular_files(assets) != {'manifest.json', *(key + '.fbx' for key in expected)}):
        raise ValueError('Incomplete, duplicated or foreign island primary membership')
    result = {}
    for parent in PARENTS:
        if parent not in parents: continue
        owner = owners[parent]
        if (owner.get('source_collision_hulls') != 0 or owner.get('matrix') != IDENTITY
                or not isinstance(owner.get('pieces'), list) or not owner['pieces']
                or parents[parent] != [row['name'] for row in owner['pieces']]):
            raise ValueError('Island authored frame or triangle-collision ownership changed')
        slots = owner.get('slots'); material_paths(parent, slots)
        pieces = []; count = polygons = 0
        for piece in owner['pieces']:
            key = name(piece['name']); receipt = receipts[key]
            if key != parent and not key.startswith(parent + '_cell_'):
                raise ValueError('Foreign island piece name')
            triangles = piece.get('triangles'); bounds = [piece.get('min'), piece.get('max')]
            if (type(triangles) is not int or not 0 < triangles <= TRIANGLE_LIMIT
                    or type(piece.get('polygons')) is not int or not 0 < piece['polygons'] <= triangles
                    or piece.get('collision_hulls') != 0
                    or any(not isinstance(v, list) or len(v) != 3 for v in bounds)
                    or any(type(v) not in (float, int) or not math.isfinite(v) for row in bounds for v in row)
                    or any(a > b for a, b in zip(*bounds))):
                raise ValueError('Unbounded or invalid island piece')
            metadata = receipt.get('metadata', {})
            source = receiving['pieces'][key]
            if (receipt.get('schema') != 1 or receipt.get('primary') != key + '.fbx'
                    or receipt.get('triangles') != triangles or receipt.get('bounds') != bounds
                    or metadata.get('slots') != slots or metadata.get('collision_hulls') != 0
                    or metadata.get('polygons') != piece['polygons'] or metadata.get('uv_channels') != ['UVMap']
                    or metadata.get('geometry_sha256') != source.get('geometry_sha256')
                    or not isinstance(source.get('geometry_sha256'), str)
                    or not re.fullmatch('[0-9a-f]{64}', source['geometry_sha256'])
                    or not isinstance(source.get('used_slots'), list) or not source['used_slots']
                    or source['used_slots'] != [slot for slot in slots if slot in source['used_slots']]
                    or sha(assets / receipt['primary']) != receipt.get('sha256')):
                raise ValueError('Island primary differs from its complete assembled receipt')
            pieces.append({**piece, 'sha256': receipt['sha256'], 'path': assets / receipt['primary'],
                           'asset': native_path(key), 'uv_channels': metadata['uv_channels'],
                           'used_slots': source['used_slots']})
            count += triangles; polygons += piece['polygons']
        if count != owner.get('source_triangles') or polygons != owner.get('source_polygons'):
            raise ValueError('Incomplete island parent triangle/polygon union')
        result[parent] = dict(slots=slots, pieces=pieces, source_triangles=count,
                              collision=parent != 'Sea', cast_shadow=parent != 'Sea')
    return result
