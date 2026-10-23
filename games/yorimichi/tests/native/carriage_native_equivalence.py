"""Finite unchanged vehicle/door importer fixture; never production service acceptance.

Host preparation binds each independent source vector. Unreal executes only the
checked vehicle loop and actual importer helpers. No main/preflight, furniture,
route, runtime or normal native-cache result is certified by this fixture.
"""
import argparse
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import types

HERE = Path(__file__).resolve().parent
GAME = HERE.parents[1]
sys.path[:0] = [str(HERE), str(GAME / 'world'), str(GAME / 'tools')]
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from atomic_equivalence_io import artifact, canonical, require  # noqa: E402
from track_native_equivalence import (actor_scope, assets, bound_inputs, check_input, check_private_launch,  # noqa: E402,F401
    fixture_files, native_raw_set, private_launch, receiving_startup, release_actor, retire_owned, sha,
    startup_ddc, whole_bounds)

IMPORTER_SHA = '81ed44a62d72e975c6f1c19a98e197fe7fee48ec2e36d40b9f89cf68d44c6174'
LOOP_SHA = '351cdf4a4c6721b65f1afa4fcd60c1ed759167b2ef67c2af6778e23f1b93a914'
SERVICE_NODES = {
    'box_ue': '2e8bf0f8b0f975473219eea4f1df73ed050d70d6c66972b96da2461890c88b51',
    'to_ue': '57731e017130c29676fbad815ed794efc687fd27131588c62511351d0a52d927',
    'door_mesh': '3c505d614fc96eca92ef853a52f6930939f0982bdfaadaa636729239f76f53c2',
    'vehicle_field': 'c6889097739e6925b8f95f1f1cbfefebd76f515d5df996b5ad3d11045e88d7af',
    'doors': 'b2c2a3cd27fd181aab2ed608c7d894f4b2079eda674f594ff20ea07a74168f67',
    'consist': '40949605453ccbc65d5a7d67f27cad4fde53e9d3f7a76962e7eb5416c59238b7',
}
COACHES = ('locomotive', 'tender', 'baggage-van', 'restaurant', 'first-class', 'second-class', 'brake-van')
CENSUS = dict(vehicles=7, meshes=67, lods=81, fixed_boxes=383, switchable_boxes=55, leaves=60)
FIELDS = ('source_lods', 'render_lods', 'cooked', 'hulls', 'policy', 'settings', 'source_presence', 'probes')


def ast_sha(node):
    # Python 3.13+ omits empty optional AST fields; normalize older UE/host
    # interpreters to that same complete semantic tree before its pinned hash.
    def dump(value):
        if isinstance(value, ast.AST):
            fields = []
            for key, child in ast.iter_fields(value):
                if child == [] or (child is None and not (isinstance(value, ast.Constant) and key == 'value')): continue
                fields.append(key + '=' + dump(child))
            return type(value).__name__ + '(' + ', '.join(fields) + ')'
        if isinstance(value, list): return '[' + ', '.join(dump(v) for v in value) + ']'
        return repr(value)
    return hashlib.sha256(dump(node).encode()).hexdigest()


def owner_tree(path):
    """Keep the entire SHA-pinned module except its final main() dispatch."""
    require(sha(path) == IMPORTER_SHA, 'Not the immutable/current unchanged carriage importer')
    tree = ast.parse(Path(path).read_bytes())
    require(ast.unparse(tree.body[-1]) == 'main()', 'Unexpected carriage dispatch')
    tree.body.pop()
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    loops = [n for n in main.body if isinstance(n, ast.For) and ast.unparse(n.iter) == "data['consist']['vehicles']"]
    require(len(loops) == 1 and ast_sha(loops[0]) == LOOP_SHA, 'Vehicle/door finishing slice changed')
    return tree, ast.Module(body=[copy.deepcopy(loops[0])], type_ignores=[])


def execute_vehicle_loop(owner, loop, vehicles, sizes, manifest, meshes):
    """Wrap the unchanged loop only to release its ordinary local object references."""
    require(len(loop.body) == 1 and ast_sha(loop.body[0]) == LOOP_SHA, 'Unverified vehicle loop')
    fn = ast.parse('def fixture_import(data, sizes, manifest, meshes, report):\n pass').body[0]
    fn.body = [copy.deepcopy(loop.body[0]), ast.Return(value=ast.Name(id='report', ctx=ast.Load()))]
    tree = ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[]))
    exec(compile(tree, owner.__file__, 'exec'), owner.__dict__)
    return owner.fixture_import(dict(consist=dict(vehicles=vehicles)), sizes, manifest, meshes, dict(vehicles={}))


def projection_module(path):
    """Select actual service definitions and exact collision expressions, never fake service data.

    The complete original consist AST is pinned before selecting its boxes,
    switchable and collision expressions. Passing the genuine placements as both
    v and p uses vehicle_field's existing source-record precedence/fallback.
    Furniture iteration is outside this explicit vehicle-only observation scope.
    """
    tree = ast.parse(Path(path).read_bytes())
    functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    for name, digest in SERVICE_NODES.items():
        require(name in functions and ast_sha(functions[name]) == digest, 'Service definition changed: ' + name)
    loop = next(n for n in functions['consist'].body if isinstance(n, ast.For))
    assignments = [copy.deepcopy(n) for n in loop.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id in ('boxes', 'switchable') for t in n.targets)]
    require(len(assignments) == 2, 'Missing original collision assignments')
    append = next(n.value.args[0] for n in loop.body if isinstance(n, ast.Expr)
                  and isinstance(n.value, ast.Call) and ast.unparse(n.value.func) == 'out.append')
    selected = [(k, v) for k, v in zip(append.keys, append.values) if k.value in ('collision', 'switchable', 'doors')]
    require([k.value for k, _ in selected] == ['collision', 'switchable', 'doors'], 'Changed vehicle field slice')
    fn = ast.parse('def project(v, p, name):\n pass').body[0]
    fn.body = [*assignments, ast.Return(value=ast.Dict(keys=[copy.deepcopy(k) for k, _ in selected],
                                                      values=[copy.deepcopy(v) for _, v in selected]))]
    policy = next(n for n in tree.body if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == 'RENDER' for t in n.targets))
    require(ast.literal_eval(policy.value)['screen_sizes'] == [1., .6, .15], 'Changed authored render policy')
    nodes = [ast.parse("MESH_ROOT = '/Game/BelmonteTrain'").body[0], copy.deepcopy(policy),
             *[copy.deepcopy(functions[name]) for name in SERVICE_NODES if name != 'consist'], fn]
    module = types.ModuleType('actual_service_vehicle_projection')
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(path), 'exec'), module.__dict__)
    return module


def inventory(vehicles):
    require(isinstance(vehicles, list) and len(vehicles) == 7 and {v['id'] for v in vehicles} == set(COACHES),
            'Incomplete seven-coach inventory')
    expected, fixed, switchable, leaves = {}, 0, 0, 0
    for v in vehicles:
        require(re.fullmatch('SM_BT_[A-Za-z]+', v['name']) and len(v['levels']) == 3, 'Invalid carriage identity/LODs')
        require(v['name'] not in expected, 'Duplicate body')
        expected[v['name']] = 3; fixed += len(v['collision']); switchable += len(v['switchable'])
        for door in v['doors']:
            for leaf in door['leaves']:
                key = leaf['mesh'].rsplit('/', 1)[1].split('.')[0]
                require(re.fullmatch('SM_BTD_[A-Za-z0-9_]+', key) and key not in expected and leaf.get('glb'),
                        'Missing/duplicate genuine moving leaf')
                require(leaf['motion'] in ('sliding', 'hinged') and len(leaf['pivot']) == 3, 'Missing authored motion')
                expected[key] = 1; leaves += 1
    require(dict(vehicles=len(vehicles), meshes=len(expected), lods=sum(expected.values()), fixed_boxes=fixed,
                 switchable_boxes=switchable, leaves=leaves) == CENSUS, 'Incomplete carriage positive census')
    canonical(vehicles)
    return expected


def controls_for_boxes(boxes):
    """A real fixed box supplies the positive segment; independent far segment supplies the negative."""
    require(boxes and all(len(b) == 6 for b in boxes), 'Missing actual fixed boxes')
    boxes = [[b[:3], b[3:]] for b in boxes]
    lo, hi = boxes[0]; center = [(a + b) / 2 for a, b in zip(lo, hi)]
    require(all(b > a for a, b in zip(lo, hi)), 'Degenerate authored fixed box')
    span = max(b - a for a, b in zip(lo, hi)) + 100.
    positive = dict(start=[center[0], center[1], center[2] + span],
                    end=[center[0], center[1], center[2] - span], channel='Pawn', trace_complex=True)
    far = [max(b[1][axis] for b in boxes) + 10000. for axis in range(3)]
    negative = dict(start=far, end=[far[0], far[1], far[2] + 100.], channel='Pawn', trace_complex=True)
    return [dict(id=kind + '.' + shape, kind=shape + '_' + kind,
                 input=query if shape == 'ray' else dict(query, radius_cm=.1, half_height_cm=.1, orientation=[0., 0., 0., 1.]))
            for kind, query in [('positive', positive), ('negative', negative)] for shape in ('ray', 'capsule')]


def export_object(U, obj, path, exporter):
    require(not path.exists(), 'Fresh actual object export required')
    path.parent.mkdir(parents=True, exist_ok=True)
    task = U.AssetExportTask()
    for key, value in dict(object=obj, filename=str(path), automated=True, prompt=False,
                           replace_identical=False, exporter=exporter).items(): task.set_editor_property(key, value)
    require(U.Exporter.run_asset_export_task(task), 'Actual object export refused: ' + obj.get_path_name())
    row = dict(path=str(path), sha256=sha(path)); artifact(row)
    return row


def material_capture(U, editor, packages, output, package):
    """Capture actual complete reflected object text and source texture pixels, no placeholder shaders."""
    records = {}; pending = []
    def allowed(path):
        return (path.startswith(package + '/') or path.startswith('/InterchangeAssets/gltf/')
                or path.startswith('/Engine/'))
    def add(obj):
        require(obj is not None and allowed(obj.get_path_name().split('.')[0]), 'Foreign/missing actual material reference')
        require(isinstance(obj, (U.MaterialInterface, U.Texture)), 'Unsupported actual material dependency')
        pending.append(obj)
    for key in sorted(packages):
        obj = editor.load_asset(key); require(obj is not None, 'Missing created package')
        if isinstance(obj, U.StaticMesh):
            for slot in obj.get_editor_property('static_materials'): add(slot.get_editor_property('material_interface'))
        else: add(obj)
    while pending:
        obj = pending.pop(); key = obj.get_path_name().split('.')[0]
        if key in records: continue
        stem = hashlib.sha256(key.encode()).hexdigest()
        row = dict(class_path=obj.get_class().get_path_name(),
                   text=export_object(U, obj, output / (stem + '.t3d'), U.ObjectExporterT3D()))
        if isinstance(obj, U.Texture):
            require(isinstance(obj, U.Texture2D), 'Unsupported genuine texture kind')
            row['pixels'] = export_object(U, obj, output / (stem + '.png'), U.TextureExporterPNG())
        else:
            require(isinstance(obj, (U.Material, U.MaterialInstanceConstant)), 'Unsupported actual material class')
            if isinstance(obj, U.MaterialInstanceConstant): add(obj.get_editor_property('parent'))
            for name in U.MaterialEditingLibrary.get_texture_parameter_names(obj):
                texture = U.MaterialEditingLibrary.get_material_default_texture_parameter_value(obj, name) if isinstance(obj, U.Material) else U.MaterialEditingLibrary.get_material_instance_texture_parameter_value(obj, name)
                if texture is not None: add(texture)
        records[key] = row
    require(records and any('pixels' in row for row in records.values()), 'Missing genuine glTF material/texture exports')
    return records


def material_text(binding, class_path):
    """Normalize only MIC.ParameterStateId, an editor change-detection identity.

    Installed MaterialInstanceConstant.cpp PostEditChangeProperty assigns NewGuid;
    Guid.cpp exports precisely 32 hex digits. Keep all raw T3D artifacts. No other
    GUID, source/provenance, parent, parameter, override or texture field is waived.
    Any additional generated differences remain a strict unsupported boundary.
    """
    payload = artifact(binding)
    if class_path != '/Script/Engine.MaterialInstanceConstant': return payload
    lines = payload.decode('utf-8').splitlines(keepends=True); depth = 0; found = 0
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('Begin Object'): depth += 1
        if 'ParameterStateId=' in line:
            require(depth == 1 and re.fullmatch(r'[ \t]+ParameterStateId=[0-9A-Fa-f]{32}\r?\n?', line),
                    'Unexpected MIC generated-ID grammar/scope')
            require(found == 0, 'Duplicate MIC parameter state identity')
            lines[index] = re.sub(r'(?<=ParameterStateId=)[0-9A-Fa-f]{32}', '0' * 32, line); found += 1
        if stripped == 'End Object': depth -= 1
        require(depth >= 0, 'Malformed actual material object text')
    require(found == 1 and depth == 0, 'Missing complete MIC object/parameter state identity')
    return ''.join(lines).encode('utf-8')


def compare(records, vehicles, materials, poses):
    """@cc [owner:fontanierh,label:correctness] actual-carriage-fixture-only
    All67 final meshes/81 LODs MUST compare exact saved source/GPU/cooked/hull,
    material/texture/settings/bounds and real selected queries after both whole0/
    empty guards. Missing observations MUST refuse; no texture tolerance applies.
    This finite slice MUST NOT certify main/preflight/furniture/route/runtime or
    native task reuse. Each side MUST retain its independently bound source vector.
    """
    expected = inventory(vehicles)
    boxes = {v['name']: len(v['collision']) for v in vehicles}
    require(set(records) == set(materials) == set(poses) == {'original', 'current'}, 'Missing paired phase')
    require(all(set(r) == set(expected) for r in records.values()), 'Incomplete67 native mesh census')
    require(materials['original'] and set(materials['original']) == set(materials['current'])
            and any('pixels' in row for row in materials['original'].values()), 'Material/texture package census differs')
    for name, old in materials['original'].items():
        new = materials['current'][name]
        require(set(old) == set(new) and old['class_path'] == new['class_path'], 'Material class/coverage differs')
        for field in set(old) - {'class_path'}:
            require((material_text(old[field], old['class_path']) == material_text(new[field], new['class_path'])) if field == 'text'
                    else artifact(old[field]) == artifact(new[field]), 'Actual material/texture differs: ' + name + '/' + field)
    for name, count in expected.items():
        a, b = records['original'][name], records['current'][name]
        require(a['policy_scope'] == b['policy_scope'] == 'fixture', 'Fixture policy scope required')
        require(whole_bounds(a) == whole_bounds(b), name + ' exact whole bounds differ')
        for phase, record in [('original', a), ('current', b)]:
            first = json.loads(artifact(record['raw_pages'][0]))
            require(all(slot['material'].split('.')[0] in materials[phase] for slot in first['slots']),
                    'Missing actual material graph for a consumed native slot')
        x, y = native_raw_set(a, name), native_raw_set(b, name)
        require(set(x['render_lods']) == set(y['render_lods']) == set(range(count)), 'Incomplete81 LOD pages')
        for field in FIELDS: require(x[field] == y[field], name + ' native ' + field + ' differs')
        if name.startswith('SM_BT_'):
            require(sum(x['hulls'].values()) == boxes[name], 'Actual authored fixed-box multiplicity differs')
            controls = x['probes']['controls']
            require(len(controls) == 4 and {r['kind'] for r in controls} ==
                    {'ray_positive', 'ray_negative', 'capsule_positive', 'capsule_negative'}, 'Missing actual body query controls')
            require(all(r['kind'].endswith('_negative') == (r['hit'] is None) for r in controls), 'Query positive/negative failed')
    leaf_names = {name for name in expected if name.startswith('SM_BTD_')}
    for phase in ('original', 'current'):
        require(set(poses[phase]) == leaf_names, 'Incomplete authored door pose membership')
        for name, rows in poses[phase].items():
            require(len(rows) == 2 and [r['open'] for r in rows] == [False, True], 'Missing actual closed/open pose')
            for row in rows:
                require(set(row) == {'open', 'bounds', 'matrix', 'queries'} and set(row['bounds']) ==
                        {'origin', 'extent', 'sphere_radius'} and len(row['matrix']) == 4
                        and all(len(r) == 4 for r in row['matrix']), 'Missing actual posed bounds/matrix')
                require(len(row['queries']) == 4 and {q['id'] for q in row['queries']} ==
                        {'positive.ray', 'positive.capsule', 'negative.ray', 'negative.capsule'}, 'Missing posed query controls')
                for query in row['queries']:
                    value = query['observed']; blocking = value.get('blocking')
                    require(type(blocking) is bool and value.get('query_channel') == 'Pawn'
                            and value.get('selected_component') is True and value.get('mesh') == records[phase][name]['meshes'][0]
                            and query['input']['channel'] == 'Pawn' and query['input']['trace_complex'] is True,
                            'Missing/escaped actual posed query flags')
                    require(set(value) == {'blocking', 'query_channel', 'selected_component', 'mesh'} |
                            ({'position', 'normal', 'distance'} if blocking else set()), 'Incomplete posed query outcome')
    canonical(poses)
    require(poses['original'] == poses['current'], 'Exact authored door posed bounds/queries differ')
    return dict(schema=1, fixture_geometry_complete=True, census=CENSUS, complete=False, native_complete=False,
                production_runtime_complete=False, main_preflight_exercised=False, native_task_reuse=False,
                scope='Conditional81 source oracle; exact vehicle/door slice only; no furniture/service/route/runtime acceptance')


def run_native(spec_path, digest):
    import unreal as U
    spec = json.loads(artifact(dict(path=str(Path(spec_path).absolute()), sha256=digest))); bound_inputs(spec)
    output = real_directory(spec['output']); package = spec['package']; phase = spec['phase']
    require(re.fullmatch('/Game/AtelierValidation/Carriage_[0-9a-f]{12}', package), 'Invalid exclusive carriage namespace')
    require(Path(U.Paths.project_content_dir()).resolve() == Path(spec['content']).resolve(), 'Wrong receiver Content')
    startup = receiving_startup(spec, U); atomic_json(output / 'startup-ddc.json', startup)
    E = U.EditorAssetLibrary; folder = Path(spec['content']) / package.removeprefix('/Game/')
    require(not folder.exists() and not folder.is_symlink() and not assets(E, package), 'Fixture already exists')
    document = json.loads(Path(spec['document']).read_bytes()); vehicles = document['vehicles']; expected = inventory(vehicles)
    sys.path.insert(0, str(Path(spec['receiving']) / 'games/yorimichi/unreal/Scripts'))
    import atomic_equivalence_capture as capture
    require(all(callable(getattr(U.NativeAtomicEquivalence, key, None)) for key in ('snapshot', 'component_policy', 'probe')),
            'Compiled actual native readback unavailable')
    require(U.EditorLoadingAndSavingUtils.new_blank_map(False) is not None, 'No fresh query world')
    U.SystemLibrary.execute_console_command(None, 'Editor.AsyncStaticMeshCompilation 0')
    U.SystemLibrary.execute_console_command(None, 'MessageLog.DisablePopup 1')
    require(U.SystemLibrary.get_console_variable_int_value('MessageLog.DisablePopup') == 1, 'Modal suppression unavailable')
    U.load_module('StaticMeshEditor'); meshes = U.get_editor_subsystem(U.StaticMeshEditorSubsystem)
    tree, loop = owner_tree(spec['importer']); owner = types.ModuleType('actual_carriage_' + phase); owner.__file__ = spec['importer']
    exec(compile(tree, spec['importer'], 'exec'), owner.__dict__)
    owner.ROOT = package; owner.TRAIN = Path(spec['train'])
    # Observe every actual created package before production door cleanup, without changing its API result.
    allowed = set()
    class EditorObserver:
        def __getattr__(self, name): return getattr(E, name)
        def delete_directory(self, path):
            require(path.startswith(package + '/Source/SM_BTD_'), 'Unexpected production slice deletion')
            allowed.update(assets(E, package)); return E.delete_directory(path)
    owner.E = EditorObserver()
    actors = []; actor_editor = U.get_editor_subsystem(U.EditorActorSubsystem)
    partial = lambda: dict(package=package, folder=str(folder), observed_packages=sorted(assets(E, package)))
    with actor_scope(actors, actor_editor, U.StaticMeshComponent, output, partial):
        imported = execute_vehicle_loop(owner, loop, vehicles, document['screen_sizes'], document['coaches'], meshes)
        current = assets(E, package); allowed.update(current)
        paths = {name: package + ('/Doors/' if name.startswith('SM_BTD_') else '/') + name for name in expected}
        require(set(imported['vehicles']) == {v['name'] for v in vehicles}, 'Production slice omitted body')
        require({p for p in current if isinstance(E.load_asset(p), U.StaticMesh) and '/Source/' not in p} == set(paths.values()),
                'Incomplete final67 native assets')
        # Include helper meshes/materials/textures in save, reload, archive and cleanup membership.
        objects = [E.load_asset(p) for p in sorted(current)]; require(all(objects), 'Missing created package')
        for obj in objects: require(E.save_loaded_asset(obj, only_if_is_dirty=False), 'Actual package save refused')
        packages = [obj.get_outermost() for obj in objects]; objects.clear(); obj = None
        changed, error = U.EditorLoadingAndSavingUtils.reload_packages(packages, U.ReloadPackagesInteractionMode.ASSUME_POSITIVE)
        require(changed and not str(error), 'Saved actual package reload refused')
        packages.clear(); owner = None; U.SystemLibrary.collect_garbage()
        materials = material_capture(U, E, current, output / 'materials', package)
        records = {}; posed = {}
        leaf_data = {leaf['mesh'].rsplit('/', 1)[1].split('.')[0]: leaf for v in vehicles for d in v['doors'] for leaf in d['leaves']}
        for index, name in enumerate(sorted(expected)):
            mesh = E.load_asset(paths[name]); require(mesh is not None and mesh.get_num_lods() == expected[name], 'Actual LOD census differs')
            actor = actor_editor.spawn_actor_from_class(U.StaticMeshActor, U.Vector(0, 0, 0)); require(actor is not None, 'Missing fixture actor')
            actors.append(actor); component = actor.get_component_by_class(U.StaticMeshComponent)
            component.set_mobility(U.ComponentMobility.MOVABLE); require(component.set_static_mesh(mesh), 'Mesh assignment refused')
            component.set_collision_profile_name('BlockAll'); component.set_collision_enabled(U.CollisionEnabled.QUERY_AND_PHYSICS)
            controls = document['controls'].get(name, [])
            descriptor = capture.capture([component], name, output / 'captures' / name,
                controls=[dict(r, target=component.get_path_name()) for r in controls], inputs=[spec_path], policy_scope='fixture')
            records[name] = descriptor
            if name in leaf_data:
                leaf = leaf_data[name]; rows = []
                for opened in (False, True):
                    # Genuine authored local door motion, observed on the actual imported leaf mesh.
                    pivot = U.Vector(*leaf['pivot'])
                    if leaf['motion'] == 'hinged':
                        rotation = U.Rotator(yaw=leaf['yaw'] if opened else 0)
                        shifted = U.MathLibrary.subtract_vector_vector(pivot, U.MathLibrary.rotate_angle_axis(pivot, leaf['yaw'] if opened else 0, U.Vector(0, 0, 1)))
                    else:
                        rotation = U.Rotator(); shifted = U.Vector(*(leaf['offset'] if opened else [0, 0, 0]))
                    require(component.set_world_location_and_rotation(shifted, rotation, False, False) is not None,
                            'Actual authored pose refused')
                    row = json.loads(U.NativeAtomicEquivalence.component_policy(component)); require('refusal' not in row, 'Pose readback refused')
                    query_rows = []
                    for control in controls:
                        query = control['input']; capsule = control['kind'].startswith('capsule_')
                        observed = json.loads(U.NativeAtomicEquivalence.probe(component, U.Vector(*query['start']),
                            U.Vector(*query['end']), U.Quat(*query.get('orientation', [0., 0., 0., 1.])),
                            query.get('radius_cm', 0.) if capsule else 0., query.get('half_height_cm', 0.) if capsule else 0.,
                            query['trace_complex']))
                        require('refusal' not in observed and observed.get('selected_component') is True
                                and type(observed.get('blocking')) is bool, 'Posed selected query refused')
                        query_rows.append(dict(id=control['id'], input=query,
                                               observed={k: v for k, v in observed.items() if k != 'component'}))
                    rows.append(dict(open=opened, bounds=row['component_bounds'], matrix=row['matrix'], queries=query_rows))
                posed[name] = rows
            release_actor(actor, actor_editor, U.StaticMeshComponent, actors); component = actor = mesh = None
            print('CARRIAGE ACTUAL SAVED NATIVE ' + phase + ' ' + str(index + 1) + '/67 ' + name, flush=True)
        # Archive every live saved package; observed also records packages retired by the unchanged door loop.
        archived = {}
        from atelier.mesh_geometry import SIDECARS
        for p in sorted(current):
            for suffix in SIDECARS:
                source = Path(spec['content']) / (p.removeprefix('/Game/') + suffix)
                if not source.exists(): continue
                target = output / 'saved-packages' / (hashlib.sha256(p.encode()).hexdigest() + suffix)
                target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, target)
                require(sha(source) == sha(target), 'Saved actual package archive differs')
                archived[str(source)] = dict(path=str(target), sha256=sha(target))
        for record in records.values(): record['saved_packages'] = [archived[r['path']] for r in record['saved_packages']]
        bound_inputs(spec); atomic_json(output / 'native.json', {phase: records})
        atomic_json(output / 'materials.json', materials); atomic_json(output / 'poses.json', posed)
        atomic_json(output / 'package-roster.json', dict(live=sorted(current), observed=sorted(allowed), archived=archived))
        retire_owned(U, current, allowed)
        require(not assets(E, package), 'Carriage namespace registry remains')
        atomic_json(output / 'cleanup.json', dict(root=str(folder), remaining=fixture_files(folder, allowed, package), allowed_packages=sorted(allowed)))
        bound_inputs(spec); require(sha(spec_path) == digest, 'Spec changed')
    print('CARRIAGE ACTUAL67/81 VEHICLE FIXTURE COMPLETE ' + phase + ' ' + digest, flush=True)


def main():
    if 'ATELIER_CARRIAGE_NATIVE_SPEC' in os.environ:
        run_native(Path(os.environ['ATELIER_CARRIAGE_NATIVE_SPEC']), os.environ['ATELIER_CARRIAGE_NATIVE_SHA256']); return
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--sha256', required=True); args = parser.parse_args()
    run_native(args.spec, args.sha256)


if __name__ == '__main__': main()
