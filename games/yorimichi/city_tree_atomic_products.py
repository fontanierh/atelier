"""Complete per-piece city-tree LOD ownership without another mesh export or join."""
import argparse
import json
import re
import sys
from pathlib import Path

from atelier.atomic_files import atomic_json
from atelier.export_manifest import name, real_directory, sha
from atelier.model_files import regular_files
sys.path.insert(0, str(Path(__file__).resolve().parent / 'world'))
import yori  # noqa: E402,F401
from city_atomic_products import DESTINATION, production_groups  # noqa: E402
from hidamari.tree_policy import TREES, SCREEN_SIZES  # noqa: E402


def read(spec, city):
    """Require exactly two bounded lower levels for every current logical tree child."""
    production_groups(city)
    if (spec.get('version') != 3 or spec.get('complete') is not True or spec.get('tag') != 'v4'
            or spec.get('screen_sizes') != SCREEN_SIZES or set(spec.get('sources', {})) != set(TREES)):
        raise ValueError('Incomplete atomic city tree LOD owner')
    seen = set()
    for parent in TREES:
        expected = {row['name']: row for row in city['sources'][parent]['tiles']}
        pieces = spec['sources'][parent]
        if not isinstance(pieces, list) or {row['name'] for row in pieces} != set(expected) or len(pieces) != len(expected):
            raise ValueError('Tree LOD membership differs from current city pieces')
        for row in pieces:
            key = name(row['name'])
            if (key in seen or row['asset'] != DESTINATION+'/'+key+'.'+key
                    or row['original_triangles'] != expected[key]['triangles'] or len(row['lods']) != 2):
                raise ValueError('Invalid atomic tree base owner')
            seen.add(key)
            for level, lod in enumerate(row['lods'], 1):
                child = parent+'_LOD'+str(level)+key[len(parent):]
                if (type(lod.get('level')) is not int or lod.get('level') != level or lod.get('name') != child
                        or lod.get('file') != 'atomic_regions/city_tree_lods/assets/'+child+'.fbx'
                        or type(lod.get('triangles')) is not int or not 0 < lod['triangles'] <= row['original_triangles']
                        or not isinstance(lod.get('sha256'), str) or not re.fullmatch('[0-9a-f]{64}', lod['sha256'])):
                    raise ValueError('Invalid bounded atomic tree lower level')
                from city_atomic_products import native_bounds
                native_bounds(dict(min=lod['bounds'][0],max=lod['bounds'][1]))
    return spec


def assemble(out, log=print):
    """@cc [owner:fontanierh,label:correctness;performance] tree-lod-assembly-keeps-base-membership
    Every base piece MUST have both independently exported lower levels, preserving
    the same complete original polygon membership. Assembly MUST gather their exact
    bytes and current base paths without joining or regenerating geometry. Current
    source hashes and bounded triangle counts MUST agree before publishing metadata.
    """
    from region_mesh_parts import validate
    out = Path(out)
    folder = real_directory(out / 'atomic_regions/city_tree_lods/assets')
    exports = json.loads((folder / 'manifest.json').read_text())
    receipts = {row['asset']: row for row in exports['exports']}
    if (exports.get('schema') != 1 or exports.get('complete') is not True
            or len(receipts) != len(exports['exports'])
            or regular_files(folder) != {'manifest.json', *(row['primary'] for row in receipts.values())}):
        raise ValueError('Incomplete atomic tree LOD exports')
    city = json.loads((out / 'city_surface_tiles/v1_128m/manifest.json').read_text())
    result = dict(version=3, complete=True, tag='v4', screen_sizes=SCREEN_SIZES, sources={})
    consumed = set()
    for parent in TREES:
        base = validate(out / 'planned_exports/hidamari' / parent)
        levels = {level: validate(out / 'planned_exports/city_tree_lods' / (parent+'_LOD'+str(level))) for level in (1,2)}
        children = {level: {row['name']: row for row in value['pieces']} for level, value in levels.items()}
        result['sources'][parent] = []
        for row in base['pieces']:
            key = row['name']
            record = dict(name=key, asset=DESTINATION+'/'+key+'.'+key,
                          original_triangles=row['triangles'], lods=[])
            for level in (1,2):
                child = parent+'_LOD'+str(level)+key[len(parent):]
                piece = children[level][child]
                receipt = receipts[child]
                if (piece['source_faces'] != row['source_faces'] or piece['collision_hulls']
                        or receipt['metadata']['geometry_sha256'] != piece['sha256']
                        or receipt['triangles'] != piece['triangles'] or receipt['primary'] != child+'.fbx'
                        or sha(folder / receipt['primary']) != receipt['sha256']):
                    raise ValueError('Tree LOD lost its exact base polygon ownership')
                consumed.add(child)
                record['lods'].append(dict(name=child, level=level, triangles=piece['triangles'],
                    file='atomic_regions/city_tree_lods/assets/'+receipt['primary'], sha256=receipt['sha256'], bounds=receipt['bounds']))
            result['sources'][parent].append(record)
        for level, value in levels.items():
            if len(children[level]) != len(base['pieces']) or value['source_polygons'] != base['source_polygons']:
                raise ValueError('Tree LOD has extra or missing base polygons')
    if consumed != set(receipts): raise ValueError('Foreign tree LOD exports')
    read(result, city)
    destination = out / 'city_tree_lods/v4/manifest.json'
    real_directory(destination.parent)
    if destination.is_symlink() or (destination.exists() and not destination.is_file()):
        raise ValueError('Tree LOD metadata requires a regular destination')
    atomic_json(destination, result)
    log('CITY ATOMIC TREE LODS assembled '+str(len(consumed)))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    assemble(args.out)
