"""Scoped Track receiving proof. The host owns freezing, admission and finalization.

No work runs on import. Each native invocation executes the real legacy importer
once in the same exclusive package namespace. The host must observe whole0/empty
and clear exact fixture remnants before starting the second phase. No production
actor/runtime claim is made.
"""
import argparse
import ast
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import types

GAME = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(GAME / 'world'), str(GAME / 'tools')]
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from atelier.mesh_geometry import SIDECARS  # noqa: E402
from atomic_equivalence import MAX_ARTIFACT_BYTES, artifact, canonical, component_bounds, native_raw_set, require  # noqa: E402

IMPORTER_SHA = 'b311b7322b0030c1d5f4bd44e03f82f2ed092e8001389a8f6e67370119ebe892'
SOURCE_COUNT, SOURCE_LODS = 138, 363
NATIVE_COUNT, NATIVE_LODS = 137, 362
FIELDS = ('source_lods', 'render_lods', 'cooked', 'hulls', 'policy', 'settings', 'source_presence')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_input(path, digest):
    """Declared code may be empty; geometry/spec artifact rules stay unchanged."""
    path = Path(path)
    require(path.is_absolute() and isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest),
            'Invalid exact source input identity')
    real_directory(path.parent); before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_size <= MAX_ARTIFACT_BYTES,
            'Linked, special or oversized source input')
    identity = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    require(sha(path) == digest and identity(path.lstat()) == identity(before), 'Source input bytes/identity changed')


def bound_inputs(spec):
    require(spec.get('schema') == 1 and isinstance(spec.get('inputs'), dict) and spec['inputs'],
            'Missing complete Track input inventory')
    for path, digest in spec['inputs'].items():
        check_input(path, digest)


def assets(editor, root):
    return {str(path).split('.')[0] for path in editor.list_assets(root, recursive=True, include_folder=False)}


def material_inputs(report, folder):
    """Verify the actual report-selected texture vector before creating any assets."""
    require(isinstance(report, dict) and isinstance(report.get('materials'), dict)
            and isinstance(report.get('files'), dict), 'Missing genuine Belmonte material report')
    names = [row['name'] for row in report['materials'].values()]
    require(names and len(set(names)) == len(names) and all(re.fullmatch('[A-Za-z][A-Za-z0-9_]*', name)
            for name in names), 'Aliased or foreign actual material names')
    canonical(report)
    def colour(value):
        return isinstance(value, list) and len(value) in (3, 4) and all(type(x) in (int, float) for x in value)
    for row in report['materials'].values():
        require(all(type(row.get(key)) is bool for key in ('atlas', 'terrain', 'water', 'white_vertex'))
                and colour(row.get('colour')) and colour(row.get('tint'))
                and isinstance(row.get('layers'), dict) and all(colour(x) for x in row['layers'].values())
                and type(row.get('tile_m')) in (int, float) and row['tile_m'] > 0
                and type(row.get('brightness')) in (int, float) and row['brightness'] >= 0,
                'Incomplete actual material parameters')
    require(len({row['texture'] for row in report['materials'].values() if row['terrain']}) == 1
            and all(row['texture'] for row in report['materials'].values() if row['terrain']),
            'Missing actual shared ground texture for join material')
    textures = {row['texture'] for row in report['materials'].values() if row['texture']}
    for name in textures:
        require(isinstance(name, str) and Path(name).name == name, 'Escaping material texture')
        row = report['files']['textures/' + name]
        path = Path(folder) / 'textures' / name
        artifact(dict(path=str(path.absolute()), sha256=row['sha256']))
        require(path.stat().st_size == row['size'], 'Actual material texture size differs')
    return names, textures


def runtime_inventory(value):
    """Keep the actual production census separate from the editor-only source marker."""
    meshes = value.get('meshes')
    require(isinstance(meshes, dict) and len(meshes) == NATIVE_COUNT
            and 'SM_TK_Marker' not in meshes, 'Expected137 production Track meshes without editor marker')
    rows = {}
    for name, row in meshes.items():
        require(re.fullmatch(r'SM_(?:TK|ST)_[A-Za-z0-9_]+', name) and isinstance(row, dict),
                'Foreign Track native name')
        lods, screens = row.get('lods'), row.get('screen_sizes')
        require(isinstance(lods, list) and 1 <= len(lods) <= 3
                and isinstance(screens, list) and len(screens) == len(lods)
                and all(type(x) in (int, float) and 0 < x <= 1 for x in screens)
                and all(screens[i] < screens[i - 1] for i in range(1, len(screens))),
                'Incomplete Track authored LOD/screens')
        require(all(isinstance(path, str) and not Path(path).is_absolute()
                    and '..' not in Path(path).parts and Path(path).name == f'{name}_LOD{k}.glb'
                    for k, path in enumerate(lods)), 'Foreign Track LOD source')
        require(isinstance(row.get('materials'), list) and row['materials'], 'Missing Track material table')
        rows[name] = len(lods)
    require(sum(rows.values()) == NATIVE_LODS, 'Incomplete production362 authored LOD census')
    return rows


def collision_lods(runtime):
    """Exactly the legacy importer's piece/solid-instance collision selectors."""
    rows = {p['name']: p['collision'] for p in runtime['pieces']}
    for group in runtime['instances']:
        if group['collision']:
            name = group['mesh'].rsplit('/', 1)[1].split('.')[0]
            rows[name] = len(runtime['meshes'][name]['lods']) - 1
    return {name: rows.get(name, -1) for name in runtime['meshes']}


def validate_controls(controls, runtime):
    """All controls are SHA-bound host inputs, never inferred from desired outcomes."""
    expected = runtime_inventory(runtime)
    require(isinstance(controls, dict) and set(controls) == set(expected), 'Missing Track query census')
    collision = collision_lods(runtime)
    for name, rows in controls.items():
        require(isinstance(rows, list) and rows and all(isinstance(row, dict)
            and set(row) == {'id', 'kind', 'input'} for row in rows), 'Malformed Track control')
        kinds = {row['kind'] for row in rows}
        required = {'ray_negative', 'capsule_negative'}
        if collision[name] >= 0: required |= {'ray_positive', 'capsule_positive'}
        require(kinds == required and len(rows) == len(kinds)
                and len({row['id'] for row in rows}) == len(rows), 'Incomplete Track query controls')
        canonical(rows)
        for row in rows:
            query = row['input']; capsule = row['kind'].startswith('capsule_')
            fields = {'start', 'end', 'channel', 'trace_complex'}
            if capsule: fields |= {'radius_cm', 'half_height_cm', 'orientation'}
            require(isinstance(query, dict) and set(query) == fields and query['channel'] == 'Pawn'
                and type(query['trace_complex']) is bool and all(isinstance(query[k], list) and len(query[k]) == 3
                    and all(type(x) in (int, float) for x in query[k]) for k in ('start', 'end'))
                and query['start'] != query['end'], 'Malformed Track query input')
            if capsule:
                require(type(query['radius_cm']) in (int, float) and query['radius_cm'] > 0
                    and type(query['half_height_cm']) in (int, float) and query['half_height_cm'] >= query['radius_cm']
                    and isinstance(query['orientation'], list) and len(query['orientation']) == 4
                    and abs(sum(x * x for x in query['orientation']) - 1) < 1e-5, 'Invalid Track capsule input')


def owner_tree(path, material_root=None):
    """Remove only the final dispatch and map exactly two known material-root literals.

    The complete SHA-pinned original AST is otherwise unchanged. This namespace
    isolation is a fixture boundary, not a production importer/policy exception.
    """
    require(sha(path) == IMPORTER_SHA, 'Track importer is not the exact reviewed legacy source')
    tree = ast.parse(Path(path).read_bytes())
    require(isinstance(tree.body[-1], ast.Expr) and ast.dump(tree.body[-1].value) ==
            ast.dump(ast.Call(func=ast.Name(id='main', ctx=ast.Load()), args=[], keywords=[])),
            'Expected exact final importer dispatch')
    tree.body.pop()
    if material_root is None:
        return tree
    require(re.fullmatch(r'/Game/AtelierValidation/Track_[0-9a-f]{12}/Prerequisites/Materials', material_root),
            'Material mapping must stay in the exclusive fixture')
    original = ast.dump(tree)
    mapped = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value in (
                '/Game/Belmonte/Materials/', '/Game/Belmonte/Materials/M_Belmonte'):
            mapped.append((node, node.value))
    require(sorted(value for _, value in mapped) == [
        '/Game/Belmonte/Materials/', '/Game/Belmonte/Materials/M_Belmonte'],
        'Track material mapping boundary changed')
    for node, value in mapped:
        node.value = material_root + value.removeprefix('/Game/Belmonte/Materials')
    # The reverse transform MUST reconstruct the complete original AST.
    new_values = [(node, node.value) for node, _ in mapped]
    for node, value in mapped:
        node.value = value
    require(ast.dump(tree) == original, 'Material mapping changed unrelated Track declarations')
    for node, value in new_values:
        node.value = value
    return ast.fix_missing_locations(tree)


def whole_bounds(record):
    require(isinstance(record.get('component_policies'), list) and len(record['component_policies']) == 1,
            'Each whole Track mesh needs one actual fixture component')
    row = json.loads(artifact(record['component_policies'][0]))
    physical, logical = component_bounds(row)
    require(record['meshes'] == [row.get('mesh')], 'Track bounds identify a different mesh')
    box = row.get('mesh_bounds')
    require(isinstance(box, list) and len(box) == 2 and all(isinstance(x, list) and len(x) == 3 for x in box)
            and all(type(x) in (int, float) for r in box for x in r)
            and all(b >= a for a, b in zip(*box)), 'Missing Track physical mesh box')
    return canonical(dict(component_bounds=physical, logical_bounds=logical, mesh_bounds=box,
                          scale=row['bounds_scale'], coordinated=row['lod_coordinated']))


def compare(records, runtime):
    """@cc [owner:fontanierh,label:correctness] actual-track-fixture-coverage
    Every production137 mesh and362 authored LOD MUST have complete original/current
    saved source/GPU/cooked/hull/settings/material and exact physical bounds proof.
    The editor-only marker MUST NOT be inserted into runtime to inflate coverage.
    Actual fixture query outcomes MUST compare exactly; unavailable or refused
    observations MUST fail. Fixture evidence MUST NOT certify production placement,
    HISM/light/exposure behavior, game/cook or normal native-owner task reuse.
    """
    expected = runtime_inventory(runtime)
    require(set(records) == {'original', 'current'} and all(set(rows) == set(expected) for rows in records.values()),
            'Incomplete paired Track receiving census')
    result = {}
    for name, levels in expected.items():
        old, new = records['original'][name], records['current'][name]
        require(old['policy_scope'] == new['policy_scope'] == 'fixture', 'Track policy scope must remain fixture')
        require(whole_bounds(old) == whole_bounds(new), name + ' exact whole bounds differ')
        a, b = native_raw_set(old, name), native_raw_set(new, name)
        require(set(a['render_lods']) == set(b['render_lods']) == set(range(levels)), name + ' authored LOD census differs')
        for field in FIELDS:
            require(a[field] == b[field], name + ' native ' + field + ' differs')
        require(a['probes'] == b['probes'], name + ' exact selected-component queries differ')
        controls = a['probes']['controls']
        kinds = {row['kind'] for row in controls}
        required = {'ray_negative', 'capsule_negative'}
        if collision_lods(runtime)[name] >= 0: required |= {'ray_positive', 'capsule_positive'}
        require(kinds == required and len(controls) == len(required), name + ' query coverage incomplete')
        require(controls and all(row['kind'].endswith('_negative') == (row['hit'] is None) for row in controls),
                name + ' query positive/negative control failed')
        result[name] = dict(native_geometry_complete=True, whole_bounds_exact=True, lods=levels,
                            query_controls=len(controls))
    return dict(schema=1, native_geometry_complete=True, meshes=NATIVE_COUNT, authored_lods=NATIVE_LODS,
                complete=False, native_complete=False, production_runtime_complete=False, assets=result,
                scope='Paired unchanged importer/isolated actual materials and saved native fixtures; no production actor/task/game/cook claim')


def definitions(path, label):
    """Load the actual material module without executing its final main dispatch."""
    tree = ast.parse(Path(path).read_bytes())
    require(ast.unparse(tree.body[-1]) == 'main()', 'Expected actual material owner final dispatch')
    tree.body.pop()
    module = types.ModuleType(label); module.__file__ = str(path)
    exec(compile(ast.fix_missing_locations(tree), str(path), 'exec'), module.__dict__)
    return module


class ObserveDeletion:
    """Observe only the actual owner's two deletion boundaries, preserving API results.

    Imported temporary packages are real fixture outputs too. Their package/file
    identities must be retained before the unchanged importer deletes Source.
    This observer never invents assets, reports success or bypasses a refusal.
    """
    def __init__(self, editor, root, allowed):
        self.editor, self.root, self.allowed = editor, root, allowed

    def __getattr__(self, name):
        return getattr(self.editor, name)

    def delete_directory(self, path):
        require(path in (self.root, self.root + '/Source'), 'Importer deletion escaped fixture owner')
        self.allowed.update(assets(self.editor, path))
        return self.editor.delete_directory(path)


def release_actor(actor, actor_editor, mesh_class, actors):
    """Release one recorded fixture actor only after reflected null readback."""
    require(actor in actors, 'Cannot clean an unrecorded fixture actor')
    for component in actor.get_components_by_class(mesh_class):
        if component.get_editor_property('static_mesh') is not None:
            require(component.set_static_mesh(None), 'Track component detach failed')
        require(component.get_editor_property('static_mesh') is None, 'Track component still holds its mesh')
    require(actor_editor.destroy_actor(actor), 'Track fixture actor destroy failed')
    actors.remove(actor)


@contextmanager
def actor_scope(actors, actor_editor, mesh_class, output, partial_state):
    """@cc [owner:fontanierh,label:safety;correctness] own-track-actors-on-failure
    Every exit MUST attempt bounded cleanup of only recorded fixture actors, verify
    reflected mesh detachment and require actor destruction. Cleanup failures MUST
    remain visible without replacing the original capture/save/query exception.
    Failure cleanup MUST NOT delete packages; retain the partial namespace for
    explicit recovery and never publish a successful receiving marker.
    """
    primary = None
    try:
        yield
    except BaseException as error:
        primary = error
        raise
    finally:
        failures = []
        for actor in tuple(actors):
            try:
                release_actor(actor, actor_editor, mesh_class, actors)
            except BaseException as error:
                failures.append(type(error).__name__ + ': ' + str(error))
        if primary is not None or failures:
            row = dict(original_error=None if primary is None else dict(type=type(primary).__name__, message=str(primary)),
                       cleanup_failures=failures, remaining_own_actors=len(actors), actor_cleanup_only=True,
                       packages_left_for_explicit_recovery=True)
            try:
                row['partial_namespace'] = partial_state()
            except BaseException as error:
                row['partial_namespace_error'] = type(error).__name__ + ': ' + str(error)
            try:
                atomic_json(Path(output) / 'failed-fixture-state.json', row)
            except BaseException as error:
                failures.append('failure-state reporting: ' + type(error).__name__ + ': ' + str(error))
            if failures:
                message = 'TRACK OWN ACTOR CLEANUP FAILED: ' + '; '.join(failures)
                if primary is not None:
                    primary.add_note(message)
                try:
                    print(message, flush=True)
                except BaseException as error:
                    if primary is not None:
                        primary.add_note('Cleanup stdout reporting failed: ' + type(error).__name__)
                    else:
                        raise RuntimeError(message) from error
                if primary is None:
                    raise RuntimeError(message)


def run_native(spec_path, spec_sha):
    """Receiving only; the enclosing supported guarded caller remains the authority."""
    import unreal as U
    payload = artifact(dict(path=str(Path(spec_path).absolute()), sha256=spec_sha))
    spec = json.loads(payload); bound_inputs(spec)
    package = spec['package']; output = real_directory(spec['output']); content = Path(spec['content'])
    require(re.fullmatch(r'/Game/AtelierValidation/Track_[0-9a-f]{12}', package), 'Invalid fixture namespace')
    require(Path(U.Paths.project_content_dir()).resolve() == content.resolve(), 'Wrong receiving Content root')
    real_directory(content)
    folder = content / package.removeprefix('/Game/')
    require(not folder.exists() and not folder.is_symlink(), 'Fresh exclusive Track fixture required')
    E = U.EditorAssetLibrary
    require(not assets(E, package), 'Fixture registry is not empty')
    phase = spec.get('phase')
    require(phase in ('original', 'current'), 'Select one bounded Track receiving phase')
    runtime = json.loads((Path(spec[phase + '_track']) / 'runtime/track.json').read_bytes())
    expected = runtime_inventory(runtime); validate_controls(spec['controls'], runtime)
    report = json.loads(Path(spec['material_report']).read_bytes())
    material_names, texture_names = material_inputs(report, spec['material_data'])
    aliases = {key.rsplit('/', 1)[-1].split('.')[0] for key in report['materials']}
    require({name for row in runtime['meshes'].values() for name in row['materials'] if name.startswith('MI_B_')} <= aliases,
            'Actual material report lacks a consumed Track binding')
    owner_tree(spec['importer'], package + '/Prerequisites/Materials')
    sys.path.insert(0, str(Path(spec['receiving']) / 'games/yorimichi/unreal/Scripts'))
    import atomic_equivalence_capture as capture
    require(all(callable(getattr(U.NativeAtomicEquivalence, key, None)) for key in ('snapshot', 'component_policy', 'probe')),
            'Actual compiled native readback API missing')
    world = U.EditorLoadingAndSavingUtils.new_blank_map(False)
    require(world is not None, 'Fresh query physics world unavailable')
    U.SystemLibrary.execute_console_command(None, 'Editor.AsyncStaticMeshCompilation 0')
    # Only the modal notification is suppressed; import warnings/errors and validators remain.
    U.SystemLibrary.execute_console_command(None, 'MessageLog.DisablePopup 1')
    require(U.SystemLibrary.get_console_variable_int_value('MessageLog.DisablePopup') == 1,
            'Import modal notification suppression unavailable')
    actors = []
    actor_editor = U.get_editor_subsystem(U.EditorActorSubsystem)
    require(actor_editor is not None, 'Track actor subsystem unavailable')
    partial_state = lambda: dict(package=package, folder=str(folder), observed_packages=sorted(assets(E, package)))
    with actor_scope(actors, actor_editor, U.StaticMeshComponent, output, partial_state):
        material = definitions(spec['material_owner'], 'actual_track_fixture_materials')
        material.ROOT = package + '/Prerequisites'; material.OUT = Path(spec['material_data'])
        material.surfaces(report, material.parent(), material.textures(report))
        common_assets = assets(E, package + '/Prerequisites')
        require(common_assets == {package + '/Prerequisites/Materials/' + name for name in
                ['M_Belmonte', 'M_BelmonteJoin', *material_names]} |
                {package + '/Prerequisites/Textures/' + Path(name).stem for name in texture_names},
                'Incomplete or foreign actual material prerequisites')
        records = {}
        allowed = set()
        for phase in (phase,):
            runtime = json.loads((Path(spec[phase + '_track']) / 'runtime/track.json').read_bytes())
            expected = runtime_inventory(runtime)
            owner = types.ModuleType('actual_track_' + phase); owner.__file__ = spec['importer']
            exec(compile(owner_tree(spec['importer'], package + '/Prerequisites/Materials'), spec['importer'], 'exec'), owner.__dict__)
            owner.ROOT = package + '/Library'; owner.TRACK = Path(spec[phase + '_track'])
            owner.RUNTIME = owner.TRACK / 'runtime/track.json'; owner.DATA = output / 'runtime-copy' / phase
            owner.BELMONTE_REPORT = Path(spec['material_report'])
            require(not assets(E, owner.ROOT), 'Previous Track phase remains live')
            owner.E = ObserveDeletion(E, owner.ROOT, allowed)
            owner.main()  # Exact production import/LOD assembly/material/collision/save body.
            imported = json.loads((owner.TRACK / 'runtime/import-report.json').read_text())
            require(set(imported['meshes']) == set(expected) and all(row['collision_lod'] == collision_lods(runtime)[name]
                    for name, row in imported['meshes'].items()), 'Actual importer omitted or changed a collision selector')
            paths = {name: owner.ROOT + '/' + name for name in expected}
            loaded = [E.load_asset(path) for path in paths.values()]
            require(all(loaded), 'Missing saved Track mesh')
            for mesh in loaded:
                require(E.save_loaded_asset(mesh, only_if_is_dirty=True), 'Track save failed')
            packages = [mesh.get_outermost() for mesh in loaded]
            loaded.clear(); mesh = None
            changed, error = U.EditorLoadingAndSavingUtils.reload_packages(packages, U.ReloadPackagesInteractionMode.ASSUME_POSITIVE)
            require(changed and not str(error), 'Track saved package reload failed')
            packages.clear(); U.SystemLibrary.collect_garbage()
            records[phase] = {}
            for index, name in enumerate(sorted(expected)):
                mesh = E.load_asset(paths[name]); require(mesh is not None and mesh.get_num_lods() == expected[name], 'Wrong actual Track LOD count')
                actor = actor_editor.spawn_actor_from_class(U.StaticMeshActor, U.Vector(0, 0, 0)); require(actor is not None, 'No Track fixture actor')
                actors.append(actor); component = actor.get_component_by_class(U.StaticMeshComponent)
                component.set_mobility(U.ComponentMobility.MOVABLE); require(component.set_static_mesh(mesh), 'Track mesh assignment failed')
                # Fixture components are deliberately not claimed as ABelmonteTrack.
                component.set_collision_profile_name('BlockAll')
                component.set_collision_enabled(U.CollisionEnabled.QUERY_AND_PHYSICS if imported['meshes'][name]['collision_lod'] >= 0 else U.CollisionEnabled.NO_COLLISION)
                controls = spec['controls'][name]
                controls = [dict(row, target=component.get_path_name()) for row in controls]
                descriptor = capture.capture([component], name, output / 'captures' / phase / name,
                                             controls=controls, inputs=[spec_path], policy_scope='fixture')
                archived = []
                for row in descriptor['saved_packages']:
                    source = Path(row['path']); target = output / 'saved-packages' / phase / (hashlib.sha256(str(source).encode()).hexdigest() + source.suffix)
                    target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, target)
                    require(sha(source) == sha(target) == row['sha256'], 'Saved Track copy differs')
                    archived.append(dict(path=str(target), sha256=row['sha256']))
                descriptor['saved_packages'] = archived; records[phase][name] = descriptor
                release_actor(actor, actor_editor, U.StaticMeshComponent, actors)
                component = actor = mesh = None
                print('TRACK ACTUAL SAVED NATIVE ' + phase + ' ' + str(index + 1) + '/137 ' + name, flush=True)
            owner = None; U.SystemLibrary.collect_garbage()
            packages = assets(E, package + '/Library')
            require(packages == {path for path in paths.values()} | {package + '/Library/Materials/M_TK_Glow'} |
                    {package + '/Library/Materials/' + name for name in imported['materials'] if name.startswith('MI_TK_')},
                    'Foreign or leftover imported Track assets')
            allowed.update(packages); allowed.update(common_assets)
            bound_inputs(spec)
            atomic_json(output / 'native.json', records)
        retire_owned(U, packages | common_assets, allowed)
        require(not assets(E, package), 'Track fixture registry not empty')
        remaining = fixture_files(folder, allowed, package)
        atomic_json(output / 'cleanup.json', dict(root=str(folder), remaining=remaining, allowed_packages=sorted(allowed)))
        bound_inputs(spec); require(sha(spec_path) == spec_sha, 'Track spec changed')
    print('TRACK ACTUAL ORIGINAL/CURRENT137/362 NATIVE FIXTURE COMPLETE ' + phase + ' ' + spec_sha, flush=True)


def fixture_files(folder, packages, package):
    real_directory(folder)
    expected = {path.removeprefix(package + '/') + suffix for path in packages for suffix in SIDECARS}
    if not folder.exists(): return {}
    rows = {}
    for path in folder.rglob('*'):
        require(not path.is_symlink(), 'Linked Track cleanup member')
        if path.is_file():
            relative = path.relative_to(folder).as_posix()
            require(relative in expected, 'Foreign Track cleanup file')
            rows[relative] = sha(path)
        else: require(path.is_dir(), 'Special Track cleanup member')
    return rows


def retire_owned(U, packages, allowed):
    """Exact complete external-reference preflight before supported editor deletion."""
    E = U.EditorAssetLibrary
    require(packages <= allowed, 'Cleanup membership escaped current fixture')
    for path in packages:
        refs = E.find_package_referencers_for_asset(path, load_assets_to_confirm=True)
        require(refs is not None and set(refs) <= allowed, 'External reference blocks Track cleanup')
    objects = [E.load_asset(path) for path in sorted(packages)]
    require(all(objects), 'Missing Track cleanup package')
    require(U.get_editor_subsystem(U.EditorAssetSubsystem).delete_loaded_assets(objects), 'Track native deletion failed')
    objects.clear(); U.SystemLibrary.collect_garbage()
    require(not any(E.does_asset_exist(path) for path in packages), 'Track cleanup registry member survived')
    # The host may remove only recorded SHA-exact remnants after whole0/empty,
    # then MUST prove physical absence before admitting the second phase.


def main():
    if 'ATELIER_TRACK_NATIVE_SPEC' in os.environ:
        run_native(Path(os.environ['ATELIER_TRACK_NATIVE_SPEC']), os.environ['ATELIER_TRACK_NATIVE_SHA256'])
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, required=True); parser.add_argument('--sha256', required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else None)
    run_native(args.spec, args.sha256)


if __name__ == '__main__': main()
