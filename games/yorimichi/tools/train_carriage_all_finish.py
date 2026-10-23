"""Managed-Python bounded planners, independent exports and strict all-seven service assembly controls."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME)); sys.path.insert(0, str(GAME / 'world'))
from atelier.atomic_files import atomic_json
from train import plan_carriage, export_carriage
import train_carriage_products as products


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def finish(root):
    root = Path(root); stage = json.loads((root / 'source-stage.json').read_text())
    if stage.get('phase') != 'actual_source_and_immutable_consumers' or stage.get('complete') is not True:
        raise ValueError('Incomplete actual current/original carriage source stage')
    current = Path(stage['current']); rows = []; expected = set(stage['controls'])
    for coach in products.COACHES:
        _, inventory, _ = products.source(current / 'belmonte-train-sources' / coach, coach)
        for row in inventory['pieces']:
            key = row['name']; packet = current / 'belmonte-train-sources' / coach / 'packets' / row['source']
            plan = current / 'planned_exports/belmonte_train' / key
            product = current / 'exports/world.belmonte_train.export' / key
            plan_carriage.main(['--source', str(packet), '--asset', key, '--output', str(plan)])
            export_carriage.main(['--input', str(plan / (key + '.glbdata')), '--output', str(product), '--format', '.glb'])
            original = Path(stage['controls'][key]); actual = product / (key + '.glb')
            if original.read_bytes() != actual.read_bytes(): raise ValueError('Current normal/original complete carriage bytes differ: ' + key)
            expected.remove(key)
            rows.append(dict(coach=coach, asset=key, triangles=row['triangles'],
                original=dict(path=str(original), sha256=sha(original)), current=dict(path=str(actual), sha256=sha(actual))))
            print('ALL COACH NORMAL EXPORT BYTE EXACT', len(rows), key, row['triangles'], flush=True)
    if expected: raise ValueError('Missing current normal carriage members')
    products.assemble(current)
    spec = importlib.util.spec_from_file_location('current_all_carriage_service', GAME / 'tools/belmonte_train_service.py')
    service = importlib.util.module_from_spec(spec); spec.loader.exec_module(service)
    current_train = copy.deepcopy(stage['original_service'])
    # Remove the old serialization consumer's output paths before exercising the
    # actual current strict file-only branch with the same complete runtime data.
    for vehicle in current_train['vehicles']:
        vehicle.pop('levels', None)
        for door in vehicle['doors']:
            for leaf in door['leaves']: leaf.pop('glb', None)
    train_root = current / 'belmonte-train'
    service.split_meshes(train_root, current_train, train_root / 'service/glb', source_library=train_root / 'service-meshes.json')
    if current_train != stage['original_service']: raise ValueError('Current/original complete service body/door metadata differs')
    for vehicle in current_train['vehicles']:
        for relative in [*vehicle['levels'], *(leaf['glb'] for door in vehicle['doors'] for leaf in door['leaves'])]:
            if (train_root / relative).read_bytes() != (Path(stage['original_root']) / relative).read_bytes():
                raise ValueError('Final assembled service file differs from immutable original')
    atomic_json(root / 'result.json', dict(schema=1, complete=True,
        coverage='actual_normal_source_cli_and_atlas_then_managed_planners_exports_all_seven_file_assembly_and_service_body_door_copy',
        current_normal_source_cli_exercised=True, current_production_atlas_render_exercised=True,
        independent_original_atlas_render_exercised=False, normal_build_graph_exercised=False,
        native_exercised=False, furniture_lod_bake_and_route_schedule_not_rerun=True,
        current_members=len(rows), maximum_triangles=max(row['triangles'] for row in rows), rows=rows,
        original_combined=stage['original_combined'], atlas_inputs_sha256=stage['atlas_inputs_sha256'],
        source_stage_sha256=sha(root / 'source-stage.json'), authority_sha256=stage['authority_sha256']))
    print('ALL SEVEN NORMAL SOURCE/EXPORT/ASSEMBLY/SERVICE BODY BYTES COMPLETE', len(rows), flush=True)
