"""Validate and assemble separate ferry ship files without constructing or joining meshes."""
import importlib.util
import json
from pathlib import Path

from atelier.atomic_files import atomic_json
from atelier import export_assembly, export_manifest

GAME = Path(__file__).resolve().parent
KIT = GAME / 'assets/vehicles/ferry'
WORLD = GAME / 'world'
spec = importlib.util.spec_from_file_location('ferry_ship_source_inventory', WORLD / 'regions/ferry/ship_sources.py')
sources = importlib.util.module_from_spec(spec); spec.loader.exec_module(sources)


def assemble(out):
    out = Path(out)
    root = out / 'ferry'
    assembled = out / 'atomic_regions/ferry_ship'
    value = json.loads((assembled / 'logical-pieces.json').read_text())
    if value.get('schema') != 1 or set(value['parents']) != set(sources.BUILDERS):
        raise ValueError('Incomplete or foreign atomic ferry ship parents')
    audit = json.loads((root / 'ship-audit.json').read_text())
    if audit.get('schema') != 1 or audit.get('complete') is not True or set(audit['meshes']) != set(sources.BUILDERS):
        raise ValueError('Incomplete original ferry audit proof')
    members = []
    physical = {}
    for parent in sources.BUILDERS:
        group = value['ownership'][parent]
        if (group['source_triangles'] != audit['meshes'][parent]['triangles']
                or group['source_collision_hulls'] != 0
                or value['parents'][parent] != [row['name'] for row in group['pieces']]):
            raise ValueError('Atomic ferry geometry differs from its audited logical source')
        for row in group['pieces']:
            key = row['name']
            if key in physical:
                raise ValueError('Duplicate physical ferry mesh')
            item = export_assembly.Item(key, out / 'exports/world.ferry_ship.export' / key)
            receipt = export_manifest.validate(item.root, key=key)
            if receipt['triangles'] != row['triangles']:
                raise ValueError('Ferry export count differs from its complete logical plan')
            members.append(item)
            physical[key] = dict(audit['meshes'][parent], triangles=row['triangles'], logical_parent=parent,
                                 min=row['min'], max=row['max'])
    collision = out / 'exports/world.ferry_ship.collision/FY_Collision'
    collision_receipt = export_manifest.validate(collision, key='FY_Collision')
    hulls = collision_receipt['metadata']['collision_hulls']
    if type(hulls) is not int or hulls <= 0:
        raise ValueError('Ferry authored collision is incomplete')
    members.append(export_assembly.Item('FY_Collision', collision))
    palette = json.loads((root / 'ship-source-data/FY_Hull.json').read_text())
    # Material values are published as data by the source action, never reconstructed in assembly.
    materials = palette['materials']
    manifest = dict(sources={str(path.relative_to(GAME.parents[1])): export_manifest.sha(path)
                             for path in (KIT / 'build.py', WORLD / 'solid_mesh.py')},
        materials=materials, meshes=physical, mesh_order=list(physical), logical_meshes=audit['meshes'],
        units='metres, +X bow, z up, waterline z=0',
        **{field: audit[field] for field in ('dimensions', 'boarding_openings', 'decks', 'stair', 'deck_audit')},
        triangles=sum(row['triangles'] for row in physical.values()),
        collision=dict(file='atomic-assets/FY_Collision.fbx', convex_hulls=hulls))
    result = export_assembly.assemble(members, root / 'atomic-assets')
    manifest['files'] = {str(path.relative_to(root)): export_manifest.sha(path)
        for path in [*(root / 'atomic-assets').glob('FY_*.fbx'), root / 'deck_layout.json']}
    atomic_json(root / 'atomic-manifest.json', value | dict(exports=result['exports']))
    atomic_json(root / 'manifest.json', manifest)
    return manifest
