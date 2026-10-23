"""Freeze Track receiving inputs only. This command never launches Unreal or Blender.

The parent launches each phase through the existing guarded UnrealScript lifecycle,
records exact current_native_build before/after, and finalizes positive whole/empty
evidence before any exact-file fixture cleanup or next-phase launch.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

GAME = Path(__file__).resolve().parents[2]
REPO = GAME.parents[1]
sys.path[:0] = [str(GAME / 'world'), str(GAME / 'tools'), str(Path(__file__).parent)]
import yori  # noqa: E402,F401
from atelier import engine  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.build_inputs import local_imports  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from atomic_equivalence import require  # noqa: E402
import track_native_equivalence as proof  # noqa: E402

SOURCE_HEAD = 'f37d202d475fa509fcf5195d7e486391288f1c25'


def head(root):
    require(not subprocess.check_output(['git', 'status', '--porcelain'], cwd=root), 'Freeze clean source before Track proof')
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root).decode().strip()


def controls(name, runtime, source, *, witnesses=None):
    """Use actual serialized collision-LOD tessellation, never a concave polygon fan."""
    from track_query_surface import controls as make,triangles
    asset=name+'_LOD'+str(max(proof.collision_lods(runtime)[name],0))
    require(Path(source).name==asset+'.glb','Selected Track control source path differs')
    rows,witness=make(name,triangles(Path(source).read_bytes(),asset=asset))
    if witnesses is not None:
        witnesses[name]=dict(source=str(source),sha256=proof.sha(source),triangle=witness,
            frame='baked export_yup glTF (x,y,z) -> native FVector3f cm (100x,100z,100y)')
    if proof.collision_lods(runtime)[name]<0:
        # NoCollision negatives must cross real geometry, not hide outside it.
        rows=[dict(row,id=row['id'].replace('.positive','.negative'),kind=row['kind'].replace('_positive','_negative'))
              for row in rows if row['kind'].endswith('positive')]
    return rows


def prepare(args):
    """Freeze all real inputs before fixture output mutation, with no native admission."""
    root = real_directory(args.output.absolute())
    require(not root.exists() and not root.is_symlink(), 'Fresh Track proof output required')
    source_head, receiver_head = head(REPO), head(args.receiving)
    source = args.proof.absolute(); inputs = {}
    def bind(path, expected=None):
        path = Path(path).absolute()
        digest = proof.sha(path) if expected is None else expected
        proof.check_input(path, digest); inputs[str(path)] = digest
        return path
    result_path = bind(source / 'result.json'); audit_path = bind(source / 'serialized-byte-audit.json')
    authority = bind(source / 'authority.json')
    result, audit = json.loads(result_path.read_bytes()), json.loads(audit_path.read_bytes())
    require(result['complete'] is True and audit['complete'] is True and audit['source_head'] == SOURCE_HEAD
            and proof.sha(result_path) == audit['result_sha256']
            and proof.sha(authority) == result['authority_sha256'] == audit['authority_sha256']
            and audit['logical_meshes'] == proof.SOURCE_COUNT and audit['authored_lods'] == proof.SOURCE_LODS
            and audit['byte_identical_lods'] == proof.SOURCE_LODS, 'Missing exact source138/363 proof authority')
    rows = result['rows']; require(len(rows) == proof.SOURCE_LODS and len({row['asset'] for row in rows}) == len(rows), 'Incomplete source LOD inventory')
    by_asset = {row['asset']: row for row in rows}
    require(len({row['logical'] for row in rows}) == proof.SOURCE_COUNT, 'Incomplete source logical census')
    for row in rows:
        require(len(row['selected']) == 1 and row['original']['sha256'] == row['selected'][0]['sha256'], 'Serialized source identity differs')
        bind(row['original']['path'], row['original']['sha256']); bind(row['selected'][0]['path'], row['selected'][0]['sha256'])
        bind(source / 'selected' / (row['asset'] + '.json'))
    document_path = bind(args.track_document, args.track_document_sha256)
    document = json.loads(document_path.read_bytes())
    require(document.get('schema') == 1 and isinstance(document.get('mesh_order'), list)
            and len(document['mesh_order']) == proof.SOURCE_COUNT
            and set(document['mesh_order']) == {row['logical'] for row in rows}
            and set(document.get('meshes', {})) == set(document['mesh_order'])
            and document.get('editor_only') == ['SM_TK_Marker'],
            'Missing fresh complete current source inventory (old runtime/report is not authority)')
    # This MUST be the output of the actual file-only assembly, not a document
    # synthesized by this receiving harness or a retained old runtime report.
    for name in document['mesh_order']:
        entry = document['meshes'][name]; levels = len(entry['lods'])
        require(1 <= levels <= 3 and len(entry['levels']) == levels
                and {row['level'] for row in rows if row['logical'] == name} == set(range(levels)),
                'Fresh inventory differs from the proven authored source LODs')
        for k in range(levels):
            require(Path(entry['lods'][k]).name == f'{name}_LOD{k}.glb'
                    and entry['triangles'][k] == by_asset[f'{name}_LOD{k}']['triangles'],
                    'Actual assembly metadata differs from proved source')
    converter_path = bind(GAME / 'tools/belmonte_track_data.py')
    converter_spec = importlib.util.spec_from_file_location('actual_track_runtime_converter', converter_path)
    converter = importlib.util.module_from_spec(converter_spec); converter_spec.loader.exec_module(converter)
    runtime = converter.build(document)
    inventory = proof.runtime_inventory(runtime)
    require(set(inventory) == {row['logical'] for row in rows} - {'SM_TK_Marker'}, 'Runtime omitted a non-editor source')
    for name, levels in inventory.items():
        require({row['level'] for row in rows if row['logical'] == name} == set(range(levels)), 'Runtime changed authored LOD count')
    importer = bind(args.receiving / 'games/yorimichi/unreal/Scripts/import_belmonte_track.py', proof.IMPORTER_SHA)
    material_owner = bind(args.receiving / 'games/yorimichi/unreal/Scripts/import_belmonte.py')
    material_report = bind(args.material_report); material_data = args.textures.parent.absolute()
    report = json.loads(material_report.read_bytes()); proof.material_inputs(report, material_data)
    for name in {row['texture'] for row in report['materials'].values() if row['texture']}:
        bind(material_data / 'textures' / name, report['files']['textures/' + name]['sha256'])
    scripts = args.receiving / 'games/yorimichi/unreal/Scripts'
    for entry in (importer, material_owner, scripts / 'atomic_equivalence_capture.py'):
        for path in local_imports(entry, (scripts, args.receiving / 'games/yorimichi/world', args.receiving / 'platform/studio')):
            bind(path)
        bind(entry)
    for name in ('NativeAtomicEquivalence.cpp', 'NativeAtomicEquivalence.h', 'BelmonteTrack.cpp', 'BelmonteTrack.h'):
        bind(args.receiving / 'games/yorimichi/unreal/Source/Yorimichi' / name)
    for path in (Path(__file__), Path(__file__).with_name('run_track_native_equivalence.py'),
                 Path(proof.__file__), GAME / 'tools/atomic_equivalence.py',
                 GAME / 'tools/atomic_equivalence_io.py'):
        bind(path)
    surface = Path(__file__).with_name('track_query_surface.py')
    for path in local_imports(surface, (surface.parent, GAME / 'tools', REPO / 'platform/studio')):
        bind(path)
    control_witnesses = {}
    control_rows = {name: controls(name, runtime, by_asset[f'{name}_LOD{max(proof.collision_lods(runtime)[name],0)}']['original']['path'],witnesses=control_witnesses) for name in inventory}
    proof.validate_controls(control_rows, runtime)
    package = '/Game/AtelierValidation/Track_' + uuid.uuid4().hex[:12]
    proof.owner_tree(importer, package + '/Prerequisites/Materials')
    # The complete input validation above precedes all file staging.
    engine_root = engine.unreal_root()
    bind(engine_root / 'Engine/Config/BaseEngine.ini')
    launches = {phase: proof.private_launch(root, phase, engine_root) for phase in ('original', 'current')}
    root.mkdir(parents=True)
    (root / 'private-ddc').mkdir()
    for phase in ('original', 'current'):
        directory = root / 'frozen' / phase
        document = json.loads(json.dumps(runtime))
        for name, levels in inventory.items():
            document['meshes'][name]['lods'] = []
            for level in range(levels):
                key = f'{name}_LOD{level}'; row = by_asset[key]
                source_path = Path(row['original']['path'] if phase == 'original' else row['selected'][0]['path'])
                target = directory / 'meshes' / (key + '.glb'); target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source_path, target); bind(target, row['original']['sha256'])
                document['meshes'][name]['lods'].append('meshes/' + key + '.glb')
        path = directory / 'runtime/track.json'; atomic_json(path, document); bind(path)
    for phase in ('original', 'current'):
        output = root / phase; output.mkdir()
        (output / 'user').mkdir()
        launch = launches[phase]
        spec = dict(schema=1, phase=phase, source=str(REPO), source_head=source_head, receiving=str(args.receiving),
            receiving_head=receiver_head, package=package, output=str(output), launch=launch,
            content=str(args.receiving / 'games/yorimichi/unreal/Content'), importer=str(importer),
            material_owner=str(material_owner), material_report=str(material_report), material_data=str(material_data),
            original_track=str(root / 'frozen/original'), current_track=str(root / 'frozen/current'),
            controls=control_rows, control_witnesses=control_witnesses, inputs=inputs,
            coverage=dict(source_logical=138, source_lods=363, native_logical=137, native_lods=362,
                editor_only=['SM_TK_Marker'], production_runtime=False, normal_task_reuse=False))
        atomic_json(output / 'spec.json', spec)
    atomic_json(root / 'prepare-result.json', dict(schema=1, prepared=True, launched=False, source_head=source_head,
        receiving_head=receiver_head, source_proof_sha256=proof.sha(result_path), phases=['original', 'current'],
        scope='Exact source files and fixture policy selectors only; no native result or task admission'))
    print('TRACK NATIVE INPUTS PREPARED; NO NATIVE LAUNCH', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('proof', 'track-document', 'material-report', 'textures', 'receiving', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--track-document-sha256', required=True)
    prepare(parser.parse_args())


if __name__ == '__main__': main()
