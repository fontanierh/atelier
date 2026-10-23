"""Complete Stable semantic/LOD membership, canonical queries and original native policy."""
import json
import math
from pathlib import Path
import sys

from atelier.atomic_files import atomic_json
from atelier.export_manifest import real_directory, sha, TRIANGLE_LIMIT
from atelier.model_files import regular_files

sys.path.insert(0, str(Path(__file__).resolve().parent / 'world'))
from hidamari_stable.catalogue import SOURCES, PARENTS, PARTS, LOD_PARENTS, selected  # noqa: E402

DESTINATION = '/Game/HidamariStable/Atomic'


def validate_budgets(parents):
    from hidamari_stable import layout as L
    counts = [sum(parents['SM_HS_'+part]['levels'][lod]['triangles'] for part in PARTS) for lod in range(3)]
    if (any(count > L.BUDGETS['LOD'+str(lod)] for lod, count in enumerate(counts))
            or not counts[0] > counts[1] > counts[2]
            or parents['SM_HS_StallDoor']['levels'][0]['triangles'] > L.BUDGETS['door_LOD0']
            or len(parents['SM_HS_Barn']['boxes']) > L.BUDGETS['collision_boxes']):
        raise ValueError('Original Stable logical LOD/door/collision budget failed')


def assemble(out):
    """@cc [owner:fontanierh,label:correctness;performance] complete-stable-atomic-assembly
    Semantic parts MUST retain their coordinated original three LODs, exact material
    channels and original whole Stable bounds for identical screen-size transitions.
    Complete canonical placements/door pivots and original AABB collision union MUST
    remain independently declared data, never reconstructed from sibling exports.
    File-only assembly MUST NOT join geometry or substitute old combined meshes.
    """
    from region_mesh_parts import validate
    from hidamari_stable import layout as L
    from hidamari_stable.placement_data import placements
    out = Path(out)
    root = real_directory(out / 'atomic_regions/hidamari_stable')
    logical = json.loads((root / 'logical-pieces.json').read_text())
    library = json.loads((root / 'assets/manifest.json').read_text())
    if (set(logical.get('parents', {})) != set(SOURCES) or library.get('complete') is not True):
        raise ValueError('Incomplete Stable semantic/LOD inventory')
    receipts = {row['asset']: row for row in library['exports']}
    if len(receipts) != len(library['exports']) or set(receipts) != set(SOURCES):
        raise ValueError('Duplicate, missing or foreign Stable bounded exports')
    levels = {}
    for key in SOURCES:
        value = validate(out / 'planned_exports/hidamari_stable' / key)
        if (value['parent'] != key or len(value['pieces']) != 1 or value['pieces'][0]['name'] != key
                or value['source_collision_hulls'] != 0 or logical['parents'][key] != [key]):
            raise ValueError('Stable requires one independently bounded semantic member per LOD')
        piece = value['pieces'][0]; receipt = receipts[key]
        if (receipt['primary'] != key + '.glb' or receipt['triangles'] != piece['triangles']
                or receipt['bounds'] != [piece['min'], piece['max']]
                or receipt['metadata']['slots'] != value['slots']
                or receipt['metadata']['geometry_sha256'] != piece['sha256']):
            raise ValueError('Stable primary/source ownership differs')
        primary = root / 'assets' / receipt['primary']
        if primary.is_symlink() or not primary.is_file() or sha(primary) != receipt['sha256']:
            raise ValueError('Stable bounded primary changed')
        levels[key] = dict(name=key, triangles=piece['triangles'], bounds=[piece['min'], piece['max']],
            sha256=receipt['sha256'], geometry_sha256=piece['sha256'], slots=value['slots'],
            uv_channels=receipt['metadata']['uv_channels'])
    expected = {'manifest.json', *(key + '.glb' for key in SOURCES)}
    if regular_files(root / 'assets') != expected: raise ValueError('Foreign Stable primary bytes')
    site = json.loads((out / 'stable-sampled-queries/site.json').read_text())
    if (site.get('schema') != 1 or len(site.get('road_heights', [])) != len(L.road_points(2.))
            or any(type(v) not in (int, float) or not math.isfinite(v)
                   for v in [site.get('platform_height'), *site.get('road_heights', [])])):
        raise ValueError('Incomplete canonical Stable road query data')
    slots = {key: [slot.removeprefix('HDS_') for slot in levels[key]['slots']] for key in ('SM_HS_Ground', 'SM_HS_Road')}
    original = placements(L.PAD_Z, site['platform_height'], site['road_heights'], slots)
    whole = [levels['SM_HS_' + part + '_LOD0']['bounds'] for part in PARTS]
    full_bounds = [[min(b[0][axis] for b in whole) for axis in range(3)],
                   [max(b[1][axis] for b in whole) for axis in range(3)]]
    parents = {}
    for parent in PARENTS:
        files = [levels[parent + '_LOD' + str(lod)] for lod in range(3)] if parent in LOD_PARENTS else [levels[parent]]
        if any(row['slots'] != files[0]['slots'] for row in files):
            raise ValueError('Stable coordinated LOD material slots differ')
        semantic = parent.removeprefix('SM_HS_') in PARTS
        policy = 'simple_as_complex' if parent in LOD_PARENTS else 'complex_as_simple'
        boxes = ([entry['box'] for entry in original['collision']] if parent == 'SM_HS_Barn' else
                 [files[0]['bounds'][0] + files[0]['bounds'][1]] if parent in ('SM_HS_StallDoor', 'SM_HS_RoomDoor') else [])
        parents[parent] = dict(levels=files, collision=policy, boxes=boxes,
            bounds=full_bounds if semantic else files[0]['bounds'],
            uv_precision='full' if parent in ('SM_HS_Ground', 'SM_HS_Road') else 'original_interchange_default',
            lod_screen_sizes=list(L.LOD_SCREEN_SIZES) if len(files) == 3 else [])
    validate_budgets(parents)
    meshes = []
    for entry in original['meshes']:
        if entry['name'] == 'SM_HS_Stable':
            meshes.extend(dict(name='SM_HS_' + part, at=entry['at'], yaw=entry['yaw'], blocks=entry['blocks']) for part in PARTS)
        else:
            meshes.append({key: value for key, value in entry.items() if key not in ('file', 'lods', 'collision')})
    runtime = dict(original, meshes=meshes, asset_root=DESTINATION, atomic=True,
                   expected_assets=list(PARENTS))
    atomic_json(out / 'hidamari-stable/atomic-manifest.json', dict(schema=1, complete=True, parents=parents))
    atomic_json(out / 'hidamari-stable/placements.json', runtime)


def read(out):
    root = real_directory(Path(out) / 'hidamari-stable')
    manifest = root / 'atomic-manifest.json'
    if manifest.is_symlink() or not manifest.is_file(): raise ValueError('Missing current Stable membership')
    value = json.loads(manifest.read_text())
    if value.get('schema') != 1 or value.get('complete') is not True or set(value.get('parents', {})) != set(PARENTS):
        raise ValueError('Incomplete current Stable parents')
    assets = real_directory(Path(out) / 'atomic_regions/hidamari_stable/assets')
    source_manifest = assets / 'manifest.json'
    if source_manifest.is_symlink() or not source_manifest.is_file(): raise ValueError('Missing Stable primary receipts')
    library = json.loads(source_manifest.read_text())
    if library.get('schema') != 1 or library.get('complete') is not True or not isinstance(library.get('exports'), list):
        raise ValueError('Incomplete Stable primary receipts')
    receipts = {row['asset']: row for row in library['exports']}
    if len(receipts) != len(library['exports']) or set(receipts) != set(SOURCES):
        raise ValueError('Duplicate, missing or foreign Stable receipt')
    expected = {'manifest.json'}
    for parent in PARENTS:
        group = value['parents'][parent]
        keys = [parent + '_LOD' + str(lod) for lod in range(3)] if parent in LOD_PARENTS else [parent]
        rows = group.get('levels', [])
        if [row.get('name') for row in rows] != keys: raise ValueError('Stable coordinated LOD set differs')
        if group.get('collision') != ('simple_as_complex' if parent in LOD_PARENTS else 'complex_as_simple'):
            raise ValueError('Stable native collision policy differs')
        if group.get('uv_precision') != ('full' if parent in ('SM_HS_Ground', 'SM_HS_Road') else 'original_interchange_default'):
            raise ValueError('Stable original UV precision policy differs')
        boxes = group.get('boxes')
        if (not isinstance(boxes, list) or (parent == 'SM_HS_Barn' and not boxes)
                or (parent in ('SM_HS_StallDoor', 'SM_HS_RoomDoor') and len(boxes) != 1)
                or (parent not in ('SM_HS_Barn', 'SM_HS_StallDoor', 'SM_HS_RoomDoor') and boxes)
                or any(not isinstance(box, list) or len(box) != 6
                       or any(type(v) not in (int, float) or not math.isfinite(v) for v in box)
                       or any(box[i+3] <= box[i] for i in range(3)) for box in boxes)):
            raise ValueError('Stable original AABB ownership differs')
        for row in rows:
            if (type(row['triangles']) is not int or not 0 < row['triangles'] <= TRIANGLE_LIMIT
                    or row['slots'] != rows[0]['slots'] or row.get('uv_channels') != ['UVMap']):
                raise ValueError('Unbounded Stable or incompatible LOD material table')
            key = row['name']; selected(key)
            receipt = receipts[key]
            if (receipt.get('primary') != key + '.glb' or receipt.get('triangles') != row['triangles']
                    or receipt.get('bounds') != row['bounds'] or receipt.get('sha256') != row['sha256']
                    or receipt.get('metadata', {}).get('geometry_sha256') != row.get('geometry_sha256')
                    or receipt['metadata'].get('slots') != row['slots']
                    or receipt['metadata'].get('collision_hulls') != 0
                    or receipt['metadata'].get('uv_channels') != row['uv_channels']):
                raise ValueError('Stable primary receipt differs from its source')
            path = assets / (key + '.glb'); expected.add(path.name)
            if path.is_symlink() or not path.is_file() or sha(path) != row['sha256']:
                raise ValueError('Stable source primary bytes differ')
    if regular_files(assets) != expected: raise ValueError('Foreign or incomplete Stable primary membership')
    validate_budgets(value['parents'])
    return value['parents']
