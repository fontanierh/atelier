"""Private actual query-inventory/file-assembly stage; no Blender/Unreal/mesh generation.

The parent runs this Python stage through the ordinary guard because query time
can be uncertain. It reads independent frozen inputs and emits ordinary data only,
never stamps, receipts or cache/native admission certificates.
"""
import argparse
import importlib.util
import io
import json
from pathlib import Path
import sys

GAME = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(GAME / 'world'), str(GAME), str(GAME / 'tools')]
import yori  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.build import Call  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from atelier.file_copy import copy_file  # noqa: E402
from atelier.model_files import regular_files  # noqa: E402
from atomic_equivalence import artifact, require  # noqa: E402


def sha(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(label, path):
    spec = importlib.util.spec_from_file_location(label, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def run(spec_path, spec_sha):
    payload = artifact(dict(path=str(spec_path.absolute()), sha256=spec_sha)); spec = json.loads(payload)
    def recheck():
        require(artifact(dict(path=str(spec_path.absolute()), sha256=spec_sha)) == payload, 'Source-stage spec changed')
        for path, digest in spec['inputs'].items(): artifact(dict(path=path, sha256=digest))
    recheck()
    donor = Path(spec['proof']); out = real_directory(spec['output'])
    require(not out.exists(), 'Fresh independent Track source-stage output required')
    result = json.loads((donor / 'result.json').read_bytes()); rows = result['rows']
    require(result['complete'] is True and len(rows) == 363
            and len({r['logical'] for r in rows}) == 138, 'Missing complete source census')
    def clone_tree(source, target):
        source = real_directory(source); names = regular_files(source)
        require(names, 'Cannot copy an empty source product')
        for name in names:
            path = source / name; destination = target / name
            require(str(path.absolute()) in spec['inputs'], 'Undeclared source-stage copy member')
            destination.parent.mkdir(parents=True, exist_ok=True); copy_file(path, destination)
            require(sha(path) == sha(destination), 'Independent source-stage copy differs')
    clone_tree(donor / 'fixture', out)
    for index, row in enumerate(rows):
        key = row['asset']; packet = donor / 'selected' / (key + '.json')
        require(str(packet.absolute()) in spec['inputs'], 'Undeclared selected source packet')
        target = out / 'belmonte-track/source-data' / packet.name
        target.parent.mkdir(parents=True, exist_ok=True); copy_file(packet, target)
        clone_tree(donor / 'selected/plans' / key, out / 'planned_exports/belmonte_track' / key)
        clone_tree(donor / 'selected/exports' / key, out / 'exports/world.belmonte_track.export' / key)
        if (index + 1) % 30 == 0: print('TRACK INDEPENDENT SOURCE COPY ' + str(index + 1) + '/363', flush=True)
    # Fresh process only: modules must see the independent OUT before their first
    # import. No old14b logical document or normal-task result is consumed.
    require(not any(name == 'train' or name.startswith('train.') for name in sys.modules), 'Track source modules loaded before independent root')
    yori.OUT = out
    from train import track_sources
    document = track_sources.inventory(); document['schema'] = 1
    expected = {row['logical']: sum(r['logical'] == row['logical'] for r in rows) for row in rows}
    require(set(document['meshes']) == set(expected) and all(document['meshes'][name]['levels'] == count
            for name, count in expected.items()), 'Fresh query inventory changed the source census')
    inventory = out / 'belmonte-track/source-data/inventory.json'; atomic_json(inventory, document)
    print('TRACK FRESH QUERY INVENTORY COMPLETE138/363', flush=True)
    graph = load('actual_track_region_graph', GAME / 'region_exports.py')
    context = type('FixtureContext', (), dict(out=out))()
    logical = [graph.LogicalAsset(row['asset'], GAME / 'world/train/plan_track.py', suffix='.glb') for row in rows]
    # Only the actual discover/assembly Call bodies execute. Every constructor and
    # exported GLB remains the independently copied real proof product.
    calls = 0
    for step in graph.steps(context, region='belmonte_track', assets=logical):
        for command in step.commands:
            if isinstance(command, Call): command.fn(context, io.StringIO()); calls += 1
    require(calls == 2, 'Unexpected additional fixture callbacks')
    assembly = load('actual_track_library_assembly', GAME / 'train_track_atomic_products.py')
    assembly.assemble(out)
    current_doc = out / 'belmonte-track/atomic/track.json'
    converter = load('actual_track_runtime_data', GAME / 'tools/belmonte_track_data.py')
    runtime = converter.build(json.loads(current_doc.read_bytes()))
    require(len(runtime['meshes']) == 137 and sum(len(row['lods']) for row in runtime['meshes'].values()) == 362
            and 'SM_TK_Marker' not in runtime['meshes'], 'Actual runtime converter changed native census')
    runtime_path = out / 'belmonte-track/runtime/track.json'; atomic_json(runtime_path, runtime)
    recheck()
    atomic_json(out / 'source-stage-result.json', dict(schema=1, fixture_complete=True, normal_task_certificate=False,
        source_document=dict(path=str(current_doc), sha256=sha(current_doc)),
        runtime=dict(path=str(runtime_path), sha256=sha(runtime_path)),
        inventory=dict(path=str(inventory), sha256=sha(inventory)), inputs=spec['inputs'],
        source_meshes=138, source_lods=363, native_meshes=137, native_lods=362,
        scope='Actual fresh query inventory + actual file-only assembly/runtime converter; no mesh generation/native task/stamp'))
    print('TRACK ACTUAL FRESH SOURCE ASSEMBLY/RUNTIME COMPLETE ' + spec_sha, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, required=True); parser.add_argument('--sha256', required=True)
    args = parser.parse_args(); run(args.spec, args.sha256)


if __name__ == '__main__': main()
