"""File-only railway assembly, retaining authored LOD and logical source ownership."""
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

from atelier.atomic_files import atomic_json
from atelier import export_assembly, export_manifest

GAME = Path(__file__).resolve().parent


def assemble(out):
    """@cc [owner:fontanierh,label:correctness;performance] railway-complete-file-only-assembly
    Assembly MUST validate every current source/LOD and bounded export before copying
    files. Every plan MUST bind the current consumed source digest and each export MUST
    bind that plan's geometry and material digests, even when triangle counts match.
    It MUST preserve every logical authored LOD, original material order, source
    frame, budget and placement record. It MUST NOT construct, join, render or export
    geometry, read rendered siblings as query data, or retire native parent packages.
    """
    out = Path(out); root = out / 'belmonte-track'
    sources = root / 'source-data'
    doc = json.loads((sources / 'inventory.json').read_text())
    library = out / 'atomic_regions/belmonte_track'
    membership = json.loads((library / 'logical-pieces.json').read_text())
    parents = membership['parents']; ownership = membership['ownership']
    expected = [f'{parent}_LOD{k}' for parent in doc['mesh_order'] for k in range(doc['meshes'][parent]['levels'])]
    if set(parents) != set(expected) or set(ownership) != set(expected): raise ValueError('Incomplete authored railway LOD membership')
    manifest = json.loads((library / 'assets/manifest.json').read_text())
    exports = {row['asset']: row for row in manifest['exports']}
    items = []; meshes = {}; triangles = {}
    for parent in doc['mesh_order']:
        levels = []; slots = []; counts = []
        for k in range(doc['meshes'][parent]['levels']):
            key = f'{parent}_LOD{k}'
            source_path = sources / (key + '.json')
            plan_path = out / 'planned_exports/belmonte_track' / key / 'plan.json'
            for path in (source_path, plan_path):
                export_manifest.real_directory(path.parent)
                if path.is_symlink() or not path.is_file(): raise ValueError('Invalid railway source/plan file')
            source_bytes = source_path.read_bytes()
            source = json.loads(source_bytes)
            plan = json.loads(plan_path.read_text())
            if (plan.get('source_sha256') != hashlib.sha256(source_bytes).hexdigest()
                    or plan.get('parent') != key or plan.get('complete') is not True
                    or [row['name'] for row in plan['pieces']] != parents[key]):
                raise ValueError('Railway plan differs from current source')
            planned = {row['name']: row for row in plan['pieces']}
            if source['asset'] != key or ownership[key]['source_triangles'] != source['triangles']:
                raise ValueError('Changed railway source after planning')
            counts.append(source['triangles']); slots.extend(source['materials'])
            rows = []
            for piece in parents[key]:
                row = exports[piece]
                actual = export_manifest.validate(out / f'exports/world.belmonte_track.export/{piece}', key=piece)
                if actual != row: raise ValueError('Railway export differs from complete assembly admission')
                piece_plan = planned[piece]
                if (row['metadata'].get('geometry_sha256') != piece_plan['sha256']
                        or row['metadata'].get('material_sha256') != piece_plan['material_sha256']):
                    raise ValueError('Railway export differs from current source plan')
                if row['triangles'] <= 0 or row['triangles'] > export_manifest.TRIANGLE_LIMIT: raise ValueError('Unbounded railway export')
                items.append(export_assembly.Item(piece, out / f'exports/world.belmonte_track.export/{piece}'))
                rows.append(dict(name=piece, file='meshes/' + row['primary'], triangles=row['triangles']))
            levels.append(dict(level=k, pieces=rows))
        triangles[parent] = counts
        if any(len(level['pieces']) != 1 for level in levels):
            raise ValueError('Railway native receiver requires explicit multi-piece authored LOD admission')
        meshes[parent] = dict(levels=levels, lods=['atomic/' + level['pieces'][0]['file'] for level in levels],
                              triangles=counts, materials=list(dict.fromkeys(slots)))
    total = sum((item.root / exports[item.key]['primary']).stat().st_size for item in items)
    spec = importlib.util.spec_from_file_location('railway_source_budgets', GAME / 'world/train/track.py')
    import sys
    world = str(GAME / 'world')
    if world not in sys.path: sys.path.insert(0, world)
    module = importlib.util.module_from_spec(spec);sys.modules[spec.name] = module;spec.loader.exec_module(module)
    budget = module.triangle_report({key: [SimpleNamespace(triangles=n) for n in values] for key, values in triangles.items()})
    if not all(row['ok'] for row in budget.values()) or total > 15e6: raise ValueError('Original railway triangle/disk budgets exceeded')
    dest = root / 'atomic'
    assembled = export_assembly.assemble(items, dest / 'meshes')
    doc['meshes'] = meshes
    atomic_json(dest / 'track.json', doc)
    atomic_json(dest / 'manifest.json', dict(schema=1, complete=True, exports=assembled, triangles=triangles,
        budgets=budget, bytes=total, checks=dict(budgets_ok=True, disk_ok=True)))
