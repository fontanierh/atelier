"""Host-only carriage fixture preparation. Never builds, imports or launches native tools."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

HERE = Path(__file__).resolve().parent
GAME = HERE.parents[1]
REPO = GAME.parents[1]
sys.path[:0] = [str(HERE), str(GAME / 'world'), str(GAME / 'tools')]
import yori  # noqa: E402,F401
from atelier import engine  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.build_inputs import local_imports  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
import carriage_native_equivalence as proof  # noqa: E402
from run_track_native_equivalence import head  # noqa: E402

ORACLE_SHA = '0755caa92a957519c6ed5916b739fca8d7048377778102155aa77f8f4e42c3c7'
AUTHORITY_SHA = 'e1268615832887e7a1da2cf1c027e92800960c8cd801a1e52beb9a08f3ae59af'
ORIGINAL = '283329c07ea04bee34587022a3d43827468c66d7'
IMPORTER = 'games/yorimichi/unreal/Scripts/import_belmonte_train.py'
SERVICE = 'games/yorimichi/tools/belmonte_train_service.py'


def source_vectors(control, result, bind):
    """Read both independent retained vectors; no side is substituted for its peer."""
    rows = result['rows']
    proof.require(result['complete'] is True and len(rows) == 81 and len({r['asset'] for r in rows}) == 81,
                  'Missing complete conditional81 original/current source oracle')
    library = json.loads(bind(control / 'current/belmonte-train/service-meshes.json').read_bytes())
    proof.require(library['complete'] is True and set(library['coaches']) == set(proof.COACHES), 'Missing genuine seven-coach bindings')
    documents = {}; copies = {}
    for phase in ('original', 'current'):
        service = bind(control / 'immutable' / SERVICE) if phase == 'original' else bind(GAME / 'tools/belmonte_train_service.py')
        converter = proof.projection_module(service); vehicles = []; manifest = {}; source_rows = {}
        for row in rows:
            binding = row[phase]; source = bind(Path(binding['path']), binding['sha256'])
            proof.require(row['original']['sha256'] == row['current']['sha256'], 'Conditional source oracle is not exact81')
            source_rows[row['asset']] = source
        for coach in proof.COACHES:
            entry = library['coaches'][coach]; name = entry['mesh']
            path = bind(control / phase / 'belmonte-train' / coach / (coach + '-placements.json'))
            placements = json.loads(path.read_bytes()); native = converter.project(placements, placements, name)
            vehicle = dict(id=coach, name=name, **native, levels=['sources/' + name + '_LOD' + str(i) + '.glb' for i in range(3)])
            # These are fixture file bindings to actual independent oracle rows, never service.json.
            for door in vehicle['doors']:
                for leaf in door['leaves']:
                    key = leaf['mesh'].rsplit('/', 1)[1].split('.')[0]
                    proof.require(leaf['node'] in entry['doors'] and entry['doors'][leaf['node']]['asset'] == key,
                                  'Authored door and source library membership differs')
                    leaf['glb'] = 'sources/' + key + '.glb'
            vehicles.append(vehicle)
            body = next(r for r in rows if r['asset'] == name + '_LOD0' and r['coach'] == coach)
            manifest[coach] = dict(triangles=dict(LOD0=body['triangles']))
        expected = proof.inventory(vehicles)
        proof.require(set(source_rows) == {name + '_LOD' + str(k) if count == 3 else name
                                          for name, count in expected.items() for k in range(count)}, 'Foreign/missing source primary')
        controls = {v['name']: proof.controls_for_boxes(v['collision']) for v in vehicles}
        # Door controls use genuine named door collision extents, without predicting a hit.
        for vehicle in vehicles:
            for door in vehicle['doors']:
                for leaf in door['leaves']:
                    key = leaf['mesh'].rsplit('/', 1)[1].split('.')[0]
                    controls[key] = proof.controls_for_boxes([door['collision']])
        documents[phase] = dict(vehicles=vehicles, screen_sizes=converter.RENDER['screen_sizes'], coaches=manifest,
                               controls=controls, source_rows={k: str(v) for k, v in source_rows.items()},
                               manifest_scope='Per-side actual body-source triangle audit; no production service manifest', census=proof.CENSUS)
        copies[phase] = source_rows
    proof.require(documents['original']['vehicles'] == documents['current']['vehicles'], 'Actual placement/source projection differs')
    return documents, copies


def prepare(args):
    root = real_directory(args.output.absolute()); control = real_directory(args.proof.absolute())
    receiving = real_directory(args.receiving.absolute())
    proof.require(not root.exists() and not root.is_symlink(), 'Fresh fixture workspace required')
    source_head, receiving_head = head(REPO), head(receiving)
    inputs = {}
    def bind(path, expected=None):
        path = Path(path).absolute(); digest = proof.sha(path) if expected is None else expected
        proof.check_input(path, digest); inputs[str(path)] = digest
        return path
    result_path = bind(control / 'result.json', ORACLE_SHA); authority_path = bind(control / 'authority.json', AUTHORITY_SHA)
    result, authority = json.loads(result_path.read_bytes()), json.loads(authority_path.read_bytes())
    proof.require(authority['original'] == ORIGINAL and result['authority_sha256'] == proof.sha(authority_path),
                  'Missing immutable original source authority')
    # Retain the exact normal producer differences separately; never waive the known two atlases.
    normal = bind(args.normal_receipt.absolute()); bind(control / 'current/belmonte-train/manifest.json')
    documents, copies = source_vectors(control, result, bind)
    importer = bind(receiving / IMPORTER, proof.IMPORTER_SHA); proof.owner_tree(importer)
    original_importer = subprocess.check_output(['git', 'show', ORIGINAL + ':' + IMPORTER], cwd=REPO)
    proof.require(hashlib.sha256(original_importer).hexdigest() == proof.IMPORTER_SHA, 'Original importer authority changed')
    for path in (Path(__file__), HERE / 'carriage_native_equivalence.py', HERE / 'run_carriage_native_equivalence.py',
                 HERE / 'track_native_equivalence.py', HERE / 'run_track_native_equivalence.py',
                 GAME / 'tools/atomic_equivalence.py', GAME / 'tools/atomic_equivalence_io.py'):
        for item in local_imports(path, (HERE, GAME / 'world', GAME / 'tools', REPO / 'platform/studio')): bind(item)
        bind(path)
    scripts = receiving / 'games/yorimichi/unreal/Scripts'
    for entry in (importer, scripts / 'atomic_equivalence_capture.py'):
        for path in local_imports(entry, (scripts, receiving / 'games/yorimichi/world', receiving / 'platform/studio')): bind(path)
        bind(entry)
    for name in ('NativeAtomicEquivalence.cpp', 'NativeAtomicEquivalence.h', 'BelmonteTrainService.cpp', 'BelmonteTrainService.h'):
        bind(receiving / 'games/yorimichi/unreal/Source/Yorimichi' / name)
    engine_root = engine.unreal_root(); bind(engine_root / 'Engine/Config/BaseEngine.ini')
    # Actual installed exporter implementation API is an explicit fixture prerequisite.
    for name in ('ObjectExporterT3D.h', 'TextureExporterPNG.h'):
        bind(engine_root / 'Engine/Source/Editor/UnrealEd/Classes/Exporters' / name)
    for relative in ('Editor/UnrealEd/Private/EditorExporters.cpp',
                     'Editor/UnrealEd/Private/Factories/EditorFactories.cpp',
                     'Runtime/Engine/Public/Materials/MaterialInstanceConstant.h',
                     'Runtime/Engine/Private/Materials/MaterialInstanceConstant.cpp',
                     'Runtime/Core/Private/Misc/Guid.cpp'):
        bind(engine_root / 'Engine/Source' / relative)
    for path in (engine_root / 'Engine/Plugins/Interchange/Assets/Content/gltf').rglob('*.uasset'):
        bind(path)
    launches = {p: proof.private_launch(root, p, engine_root) for p in ('original', 'current')}
    package = '/Game/AtelierValidation/Carriage_' + uuid.uuid4().hex[:12]
    root.mkdir(parents=True); (root / 'private-ddc').mkdir()
    for phase in ('original', 'current'):
        output = root / phase; output.mkdir(); (output / 'user').mkdir()
        train = root / 'frozen' / phase; train.mkdir(parents=True)
        for key, source in copies[phase].items():
            target = train / 'sources' / (key + '.glb'); target.parent.mkdir(exist_ok=True)
            shutil.copyfile(source, target); bind(target, proof.sha(source))
        document = train / 'vehicle-fixture.json'; atomic_json(document, documents[phase]); bind(document)
        path = train / 'import_belmonte_train.py'
        path.write_bytes(original_importer if phase == 'original' else importer.read_bytes()); bind(path, proof.IMPORTER_SHA)
    for phase in ('original', 'current'):
        train = root / 'frozen' / phase; output = root / phase
        spec = dict(schema=1, phase=phase, source=str(REPO), source_head=source_head, receiving=str(receiving),
                    receiving_head=receiving_head, package=package, output=str(output), launch=launches[phase],
                    content=str(receiving / 'games/yorimichi/unreal/Content'), importer=str(train / 'import_belmonte_train.py'),
                    train=str(train), document=str(train / 'vehicle-fixture.json'), inputs=inputs, census=proof.CENSUS,
                    original_authority=ORIGINAL, conditional_source_oracle=str(result_path), normal_receipt=str(normal),
                    exclusions=['importer.main', 'preflight_service', 'furniture', 'service', 'route', 'runtime', 'normal native task reuse'],
                    diagnostic_suppression=['MessageLog.DisablePopup=1; notifications only'], geometry_or_policy_suppression=[])
        atomic_json(output / 'spec.json', spec)
    for path, digest in inputs.items(): proof.check_input(path, digest)
    proof.require(head(REPO) == source_head and head(receiving) == receiving_head, 'Source changed during preparation')
    atomic_json(root / 'prepare-result.json', dict(schema=1, prepared=True, launched=False, census=proof.CENSUS,
                source_head=source_head, receiving_head=receiving_head, conditional_oracle_sha256=proof.sha(result_path),
                normal_receipt_sha256=proof.sha(normal), native_accepted=False))
    print('CARRIAGE67/81 FIXTURE PREPARED; NO NATIVE LAUNCH', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('proof', 'receiving', 'output', 'normal-receipt'): parser.add_argument('--' + name, type=Path, required=True)
    prepare(parser.parse_args())


if __name__ == '__main__': main()
