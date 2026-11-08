"""Verify the production furniture bake without Blender or mutable source reports."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path

_spec = importlib.util.spec_from_file_location('train_furniture_budgets', Path(__file__).with_name('budgets.py'))
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(furniture, *, summary_path=None):
    """@cc [owner:fontanierh,label:correctness] complete-production-furniture-bake
    Production consumers MUST require every budgeted asset and its expected LODs, bound to the
    current fitted source by checksum. Every LOD MUST match its recorded bytes/checksum/triangles
    and material/texture/triangle budgets. Missing, stale or corrupt bakes MUST fail, without
    substituting fitted source meshes. Source fitting reports MUST remain unchanged by baking.
    """
    furniture = Path(furniture)
    lod = furniture / 'lod'
    summary = json.loads(Path(summary_path or lod / 'summary.json').read_text())
    if not isinstance(summary, dict) or set(summary) != set(B.FURNITURE):
        raise ValueError('furniture bake must contain every production asset')
    for aid, item in summary.items():
        if item['source'] != f'{aid}.glb' or item['source_sha256'] != sha(furniture / f'{aid}.glb'):
            raise ValueError(f'{aid}: stale furniture bake source')
        expected = [0, 1] if B.FURNITURE[aid][1] else [0]
        if [level['level'] for level in item['levels']] != expected:
            raise ValueError(f'{aid}: incomplete furniture LOD chain')
        sizes = [level['screen_size'] for level in item['levels']] + [item['cull_screen_size']]
        if sizes[0] != 1.0 or not all(math.isfinite(v) and v > 0 for v in sizes) or not all(a > b for a, b in zip(sizes, sizes[1:])):
            raise ValueError(f'{aid}: invalid furniture LOD screen sizes')
        if not math.isfinite(item['bounds_radius_m']) or item['bounds_radius_m'] <= 0:
            raise ValueError(f'{aid}: invalid furniture bounds')
        for level in item['levels']:
            k = level['level']
            if level['glb'] != f'{aid}_LOD{k}.glb':
                raise ValueError(f'{aid}: furniture must reference baked LODs')
            path = lod / level['glb']
            if path.stat().st_size != level['bytes'] or sha(path) != level['sha256']:
                raise ValueError(f'{aid}: corrupt furniture LOD{k}')
            stats = B.glb_stats(path)
            cap = B.LOD1_AIM.get(aid, B.FURNITURE[aid][k]) if k == 1 else B.FURNITURE[aid][k]
            extra = [m for m in stats['materials'] if m in B.EXTRA_MATERIALS.get(aid, ())]
            if (stats['triangles'] != level['triangles'] or not 0 < stats['triangles'] <= cap
                    or len(stats['materials']) - len(extra) > 1 or not stats['images']
                    or any(not B.is_power_of_two(w) or not B.is_power_of_two(h) or max(w, h) > B.texture_cap(aid)
                           for w, h in stats['images'])):
                raise ValueError(f'{aid}: furniture LOD{k} exceeds its production budget')
    return summary


def preflight_service(train, service):
    """@cc [owner:fontanierh,label:correctness] train-import-before-mutation
    Before changing Unreal assets, the importer MUST validate the complete furniture bake,
    bind service data to its summary checksum, require matching baked level metadata and
    verify every referenced vehicle/door mesh. Raw furniture paths MUST never reach import.
    """
    train = Path(train).resolve()
    summary = read(train / 'furniture')
    if service['sources'].get('furniture_bake') != sha(train / 'furniture' / 'lod' / 'summary.json'):
        raise ValueError('train service is stale relative to its furniture bake')
    if not service['furniture'] or not set(service['furniture']) <= set(summary):
        raise ValueError('train service has an invalid furniture inventory')
    for aid, item in service['furniture'].items():
        expected = [dict(r, glb='lod/' + r['glb']) for r in summary[aid]['levels']]
        if item['levels'] != expected:
            raise ValueError(f'{aid}: service differs from the furniture bake')
    for vehicle in service['consist']['vehicles']:
        if len(vehicle['levels']) != 3:
            raise ValueError('train vehicle requires all three LODs')
        meshes = list(vehicle['levels']) + [leaf['glb'] for door in vehicle['doors'] for leaf in door['leaves'] if leaf.get('glb')]
        for name in meshes:
            path = (train / name).resolve()
            if not path.is_relative_to(train) or not path.is_file():
                raise ValueError(f'train mesh missing or outside the build: {name}')
    return summary
