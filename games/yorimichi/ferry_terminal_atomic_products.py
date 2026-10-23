"""Complete independently owned terminal file assembly; no mesh construction or joins."""
import json
import importlib.util
from pathlib import Path

from atelier.atomic_files import atomic_json
from atelier import export_assembly, export_manifest

spec = importlib.util.spec_from_file_location('terminal_product_roster', Path(__file__).with_name('ferry_terminal_atomic_build.py'))
roster = importlib.util.module_from_spec(spec); spec.loader.exec_module(roster)
MODELS = roster.MODELS
service_spec = importlib.util.spec_from_file_location('terminal_product_validation', Path(__file__).parent / 'world/regions/ferry/service.py')
service = importlib.util.module_from_spec(service_spec); service_spec.loader.exec_module(service)


def assemble(out):
    out = Path(out); root = out / 'ferry/terminals'
    data = json.loads((out / 'atomic_regions/ferry_terminals/logical-pieces.json').read_text())
    if data.get('schema') != 1 or set(data['parents']) != set(MODELS):
        raise ValueError('Incomplete independent terminal roster')
    manifest = json.loads((root / 'atomic-audit.json').read_text())
    service.validate_terminal_audits(manifest)
    walks = json.loads((root / 'walk.json').read_text())
    if set(walks) != set(manifest['terminals']): raise ValueError('Terminal walking roster is incomplete')
    for owner, row in manifest['terminals'].items():
        if walks[owner]['audit'] != row['walk'] or walks[owner]['ship_clash'] != row['ship_clash']:
            raise ValueError('Terminal current walk/contact proof differs from assembly')
    items = []
    for owner, terminal in manifest['terminals'].items():
        physical = {}
        for parent in service.model_order(terminal):
            row = terminal['meshes'][parent]
            if parent not in MODELS: raise ValueError('Foreign terminal logical mesh')
            group = data['ownership'][parent]
            if (group['source_triangles'] != row['triangles']
                    or data['parents'][parent] != [piece['name'] for piece in group['pieces']]):
                raise ValueError('Terminal source/audit membership differs')
            if parent.endswith('_Brow') and len(group['pieces']) != 1:
                raise ValueError('Moving terminal brow must retain its single small original frame')
            for piece in group['pieces']:
                key = piece['name']
                item = export_assembly.Item(key, out / 'exports/world.ferry_terminals.export' / key)
                receipt = export_manifest.validate(item.root, key=key)
                if receipt['triangles'] != piece['triangles'] or receipt['metadata']['collision_hulls'] != piece['collision_hulls']:
                    raise ValueError('Terminal bounded export differs from its declared source')
                if key in physical: raise ValueError('Duplicate physical terminal mesh')
                physical[key] = dict(row, triangles=piece['triangles'], logical_parent=parent,
                                     materials=receipt['metadata']['slots'],
                                     authored_hulls=row['authored_hulls'] if piece['collision_hulls'] else [])
                if len(physical[key]['authored_hulls']) != piece['collision_hulls']:
                    raise ValueError('Terminal authored hulls have no complete single physical owner')
                items.append(item)
        terminal['meshes'] = physical
        terminal['mesh_order'] = list(physical)
        key = 'FT_' + ('HD' if owner == 'hidamari' else 'BC') + '_Collision'
        collision = export_assembly.Item(key, out / 'exports/world.ferry_terminals.collision' / key)
        receipt = export_manifest.validate(collision.root, key=key)
        if receipt['metadata']['collision_hulls'] != terminal['collision']['convex_hulls']:
            raise ValueError('Terminal fixed authored hull membership differs')
        terminal['collision']['file'] = 'atomic-assets/' + key + '.fbx'
        items.append(collision)
    if {parent for terminal in manifest['terminals'].values() for parent in
            {row['logical_parent'] for row in terminal['meshes'].values()}} != set(MODELS):
        raise ValueError('Terminal logical parent membership is incomplete')
    assembled = export_assembly.assemble(items, root / 'atomic-assets')
    manifest['files'] = {str(path.relative_to(root)): export_manifest.sha(path)
        for path in [*(root / 'atomic-assets').glob('FT_*.fbx'), root / 'walk.json']}
    atomic_json(root / 'atomic-manifest.json', data | dict(exports=assembled['exports']))
    atomic_json(root / 'manifest.json', manifest)
    return manifest
