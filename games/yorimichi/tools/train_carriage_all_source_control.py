"""Actual seven-coach normal source CLI, then immutable consumers of its exact original-code atlas queries."""
import argparse
import ast
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
from types import ModuleType

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME / 'world'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import yori  # noqa: E402
import bpy  # noqa: E402
from atelier.atomic_files import atomic_json
from train_carriage_source_control import same_original_constructor_prefix

COACHES = ('locomotive', 'tender', 'baggage-van', 'restaurant', 'first-class', 'second-class', 'brake-van')


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def namespace(folder, output):
    for key in list(sys.modules):
        if key == 'train' or key.startswith('train.') or key == 'definition': sys.modules.pop(key)
    package = ModuleType('train'); package.__path__ = [str(folder)]; sys.modules['train'] = package
    yori.OUT = output


def service_functions(path, subset):
    functions = {'to_ue', 'mesh_path', 'box_ue', 'vehicle_field', 'door_mesh', 'doors', 'split_meshes'}
    tree = ast.parse(Path(path).read_text())
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in functions]
    if {node.name for node in selected} != functions: raise ValueError('Missing immutable service consumer closure')
    module = ModuleType('immutable_carriage_service')
    vars(module).update(os=os, G=subset, MESH_ROOT='/Game/BelmonteTrain')
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), vars(module))
    return module


def vehicle(service, coach, mesh, placements):
    switchable = [dict(name=row['name'], box=service.box_ue(row['box']))
                  for row in placements['collision_boxes'] if row['group'] != 'fixed']
    return dict(id=coach, name=mesh, doors=service.doors(dict(id=coach), placements, mesh, switchable))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authority', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    authority = json.loads(args.authority.read_text()); frozen = authority['frozen']; root = args.output.parent
    for path, row in authority['files'].items():
        if sha(path) != row['sha256']: raise ValueError('Frozen all-coach source/input/tool changed')
    same_original_constructor_prefix(Path(frozen['games/yorimichi/world/train/build.py']), GAME / 'world/train/build.py')
    for leaf in ('parts.py', 'fittings.py', 'layout.py', 'textures.py'):
        if Path(frozen['games/yorimichi/world/train/' + leaf]).read_bytes() != (GAME / 'world/train' / leaf).read_bytes():
            raise ValueError('Original atlas producer source changed')
    current = root / 'current'
    addon = root / 'addon.json'; atomic_json(addon, dict(schema=1, files=authority['addon']))
    infos = {}; placements = {}; queries = {}
    for coach in COACHES:
        print('NORMAL COACH SOURCE CLI START', coach, flush=True)
        bpy.ops.wm.read_factory_settings(use_empty=True)
        namespace(GAME / 'world/train', current)
        constructor = importlib.import_module('train.construct_carriage')
        request = Path(authority['requests'][coach]['path'])
        if sha(request) != authority['requests'][coach]['sha256']: raise ValueError('Normal coach request changed')
        folder = current / 'belmonte-train-sources' / coach
        constructor.main(['--request', str(request), '--coach', coach, '--output', str(folder), '--addon', str(addon)])
        inventory = json.loads((folder / 'packets/inventory.json').read_text())
        infos[coach] = json.loads((folder / 'packets/info.json').read_text())
        placements[coach] = json.loads((folder / 'packets/placements.json').read_text())
        mesh = inventory['mesh']; atlas = folder / 'textures' / ('T_BT_' + mesh.removeprefix('SM_BT_') + 'Interior.png')
        if atlas.exists():
            sidecar = atlas.with_suffix('.json')
            queries[coach] = dict(path=str(atlas), sha256=sha(atlas),
                tiles=json.loads(sidecar.read_text())['tiles'], actual_current_key=json.loads(sidecar.read_text())['key'])
        print('NORMAL COACH SOURCE CLI COMPLETE', coach, len(inventory['pieces']), flush=True)
    atomic_json(root / 'atlas-inputs.json', dict(schema=1, origin='actual current normal CLI; original-exact renderer source',
        key_or_stamp_transplanted=False, queries=queries))
    namespace(Path(frozen['games/yorimichi/world/train/build.py']).parent, root / 'original')
    old = importlib.import_module('train.build')
    spec = importlib.util.spec_from_file_location('immutable_all_carriage_subset', frozen['games/yorimichi/tools/gltf_subset.py'])
    subset = importlib.util.module_from_spec(spec); spec.loader.exec_module(subset)
    service = service_functions(frozen['games/yorimichi/tools/belmonte_train_service.py'], subset)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    old.FU.stage(old.OUT / 'furniture'); images = old.make_textures()
    def actual_atlas_query(coach, path, furniture_dir, hide):
        if coach.name not in queries:
            if old.PT.window_tiles(coach)[0]: raise ValueError('Missing actual original-code atlas query')
            return []
        value = queries[coach.name]; source = Path(value['path'])
        if sha(source) != value['sha256']: raise ValueError('Actual atlas query changed')
        shutil.copyfile(source, path)
        if sha(path) != value['sha256'] or sha(source) != value['sha256']: raise ValueError('Atlas input changed during independent copy')
        return value['tiles']
    production_atlas = old.PT.atlas; old_train = dict(vehicles=[]); originals = {}
    try:
        old.PT.atlas = actual_atlas_query
        for coach in old.L.vehicles():
            print('IMMUTABLE COACH CONSUMER START', coach.name, flush=True)
            info = old.build(coach, dict(images))
            expected = infos[coach.name]
            if expected != {key: info[key] for key in expected}: raise ValueError('Immutable/current constructor/check census differs')
            original_placements = json.loads((old.OUT / coach.name / (coach.name + '-placements.json')).read_text())
            if original_placements != placements[coach.name]: raise ValueError('Immutable/current complete layout/door/collision/boarding/seating data differs')
            old_train['vehicles'].append(vehicle(service, coach.name, info['mesh'], original_placements))
            originals[coach.name] = dict(triangles=info['triangles'], mesh=info['mesh'])
            print('IMMUTABLE COACH CONSUMER COMPLETE', coach.name, info['triangles'], flush=True)
    finally: old.PT.atlas = production_atlas
    service.split_meshes(old.OUT, old_train, old.OUT / 'service/glb')
    controls = {}
    for row in old_train['vehicles']:
        for level, relative in enumerate(row['levels']): controls[f'{row["name"]}_LOD{level}'] = str(old.OUT / relative)
        for door in row['doors']:
            for leaf in door['leaves']:
                if leaf.get('mesh') is None or not leaf.get('glb'): raise ValueError('Immutable expected moving leaf is absent')
                controls[leaf['mesh'].rsplit('/', 1)[1].split('.')[0]] = str(old.OUT / leaf['glb'])
    for path, row in authority['files'].items():
        if sha(path) != row['sha256']: raise ValueError('Frozen source changed during all-coach source control')
    atomic_json(args.output, dict(schema=1, complete=True, phase='actual_source_and_immutable_consumers',
        current=str(current), original_root=str(old.OUT), current_normal_source_cli_exercised=True,
        current_production_atlas_render_exercised=True, independent_original_atlas_render_exercised=False,
        original_combined=originals, controls=controls, original_service=old_train,
        atlas_inputs_sha256=sha(root / 'atlas-inputs.json'), authority_sha256=sha(args.authority)))
    print('ALL SEVEN NORMAL SOURCE AND IMMUTABLE CONSUMERS COMPLETE', len(controls), flush=True)


if __name__ == '__main__': main()
