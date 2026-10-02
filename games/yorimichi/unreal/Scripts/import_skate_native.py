"""Build and validate the sole cooked skating content in one headless editor session.

`atelier build yorimichi unreal.skate` verifies the tracked source before this
step. Independent failures are collected into build/yorimichi/skate-unreal.
"""
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'world'))
import yori
import unreal

E = unreal.EditorAssetLibrary
ASSET_TOOLS = unreal.AssetToolsHelpers.get_asset_tools()
SOURCE = yori.ASSETS / 'skate'
DESCRIPTOR = json.loads((SOURCE / 'runtime.json').read_text())
PROFILE_SOURCE = json.loads((SOURCE / 'profile.json').read_text())
OUTPUT = yori.OUT / 'skate-unreal'
ROOT = '/Game/SkateNative'


def runtime_report(value):
    fields = {
        'valid': 'bValid', 'saved': 'bSaved', 'roundtrip_verified': 'bRoundTripVerified',
        'semantic_load': 'bSemanticLoadSucceeded', 'file_asset_equivalent': 'bFileAssetEquivalent',
        'compared_ticks': 'ComparedTicks', 'file_word_sha256': 'FileWordSha256',
        'asset_word_sha256': 'AssetWordSha256', 'asset_path': 'AssetPath',
        'snapshot_integrity': 'bSnapshotIntegrityVerified',
        'checksum_corruption_rejected': 'bChecksumCorruptionRejected',
        'snapshot_output_retained': 'bSnapshotOutputRetained',
        'snapshot_immutable': 'bSnapshotImmutable', 'integrity_checks': 'IntegrityChecks',
        'integrity_checks_passed': 'IntegrityChecksPassed',
        'manifest_sha256': 'ManifestSha256', 'source_identity': 'SourceIdentity',
        'record_count': 'RecordCount', 'clip_count': 'ClipCount', 'payload_bytes': 'PayloadBytes',
    }
    result = {name: value.get_editor_property(field) for name, field in fields.items()}
    result['issues'] = [str(v) for v in value.get_editor_property('Issues')]
    return result


def make_profile(data, catalog):
    path = DESCRIPTOR['unreal_assets']['profile']
    factory = unreal.DataAssetFactory()
    factory.set_editor_property('data_asset_class', unreal.SkateProfile)
    profile = E.load_asset(path) if E.does_asset_exist(path) else ASSET_TOOLS.create_asset(
        path.rsplit('/', 1)[1], path.rsplit('/', 1)[0], unreal.SkateProfile, factory)
    if profile is None:
        raise RuntimeError('Could not create skating profile')
    profile.set_editor_property('runtime_data', data)
    profile.set_editor_property('collision_data_catalog', [catalog])
    profile.set_editor_property('difficulty', {
        'easy': unreal.SkateDifficulty.EASY, 'normal': unreal.SkateDifficulty.NORMAL,
        'hardcore': unreal.SkateDifficulty.HARDCORE,
    }[PROFILE_SOURCE['difficulty']])
    profile.set_editor_property('goofy', PROFILE_SOURCE['goofy'])
    for field in ('truck_tightness', 'pop_height_scale', 'air_spin_scale', 'push_speed_scale',
                  'push_power_scale', 'vert_assist', 'collision_scan_period_seconds', 'sound_folder'):
        profile.set_editor_property(field, PROFILE_SOURCE[field])
    for field in ('deck_mesh', 'truck_mesh', 'wheel_mesh'):
        profile.set_editor_property(field, unreal.SoftObjectPath(PROFILE_SOURCE[field]))
    profile.set_editor_property('fall_sounds', [unreal.SoftObjectPath(p) for p in PROFILE_SOURCE['fall_sounds']])
    validation = profile.validate_profile_report()
    if not validation.get_editor_property('valid'):
        raise RuntimeError('; '.join(str(v) for v in validation.get_editor_property('issues')))
    if not E.save_loaded_asset(profile, only_if_is_dirty=False):
        raise RuntimeError('Could not save skating profile')
    return profile


def static_meshes():
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    registry.scan_paths_synchronous(PROFILE_SOURCE['collision_asset_roots'], force_rescan=True)
    registry.wait_for_completion()
    inventory = {}
    registered_packages = set()
    registered_class_names = {}
    for root in PROFILE_SOURCE['collision_asset_roots']:
        for item in registry.get_assets_by_path(root, recursive=True):
            package = str(item.package_name)
            kind = str(item.asset_class_path.asset_name)
            registered_packages.add(package)
            registered_class_names.setdefault(package, set()).add(kind)
            if kind == 'StaticMesh':
                mesh = item.get_asset()
                if mesh is None:
                    raise RuntimeError('Registered static mesh could not be loaded: ' + package)
                inventory[mesh.get_path_name()] = mesh
    registry_paths = set(inventory)
    # Collision-only imported meshes can be referenced by maps before their
    # package metadata appears in a commandlet's registry. Include the actual
    # blocking world meshes as well as the registry's unloaded asset inventory.
    for path in PROFILE_SOURCE['validation_maps']:
        world = unreal.EditorLoadingAndSavingUtils.load_map(path)
        if world is None:
            raise RuntimeError('Could not discover collision in map: ' + path)
        for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor):
            for component in actor.get_components_by_class(unreal.StaticMeshComponent):
                mesh = component.get_editor_property('static_mesh')
                if mesh is not None and any(mesh.get_path_name().startswith(root.rstrip('/') + '/')
                        for root in PROFILE_SOURCE['collision_asset_roots']):
                    inventory[mesh.get_path_name()] = mesh
    map_paths = set(inventory) - registry_paths
    # A synchronous commandlet registry can omit or misclassify meshes spawned
    # later from loose world data. Verify the loaded type of every source
    # package that is not already in the actual mesh inventory.
    content = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir()))
    disk_packages = set()
    for root in PROFILE_SOURCE['collision_asset_roots']:
        name = root.rstrip('/')
        if name != '/Game' and not name.startswith('/Game/'):
            raise RuntimeError('Collision source-file discovery requires a /Game root: ' + root)
        relative = Path(name[6:]) if name != '/Game' else Path()
        if '..' in relative.parts:
            raise RuntimeError('Invalid collision asset root: ' + root)
        directory = content / relative
        if not directory.is_dir():
            raise RuntimeError('Collision asset source directory is missing: ' + root)
        for filename in directory.rglob('*.uasset'):
            disk_packages.add('/Game/' + filename.relative_to(content).with_suffix('').as_posix())
    known_mesh_packages = {path.split('.', 1)[0] for path in inventory}
    disk_loaded, disk_meshes, disk_non_meshes = [], [], []
    metadata_mismatches = []
    for package in sorted(disk_packages - known_mesh_packages):
        # unreal.load_asset uses StaticLoadObject directly; EditorAssetLibrary
        # load_asset would consult the same incomplete registry first.
        asset = unreal.load_asset(package)
        if asset is None:
            raise RuntimeError('Source asset type could not be verified: ' + package)
        disk_loaded.append(package)
        if isinstance(asset, unreal.StaticMesh):
            inventory[asset.get_path_name()] = asset
            disk_meshes.append(asset.get_path_name())
            metadata_mismatches.append({'package': package, 'asset': asset.get_path_name(),
                'registry_class_names': sorted(registered_class_names.get(package, ()))})
        else:
            disk_non_meshes.append(package)
    meshes, skipped = [], []
    for name, mesh in sorted(inventory.items()):
        if mesh is None:
            raise RuntimeError('Static mesh could not be loaded: ' + name)
        if mesh.get_editor_property('body_setup') is None:
            skipped.append(name)
            continue
        meshes.append(mesh)
    discovery = {'valid': True, 'registry_meshes': len(registry_paths),
                 'map_meshes_missing_from_registry': sorted(map_paths),
                 'source_packages_on_disk': len(disk_packages),
                 'source_packages_type_verified': len(disk_loaded),
                 'unregistered_source_packages_loaded': [p for p in disk_loaded if p not in registered_packages],
                 'disk_meshes_missing_from_registry': disk_meshes,
                 'registered_mesh_metadata_mismatches': metadata_mismatches,
                 'non_mesh_source_packages_verified': len(disk_non_meshes),
                 'unregistered_non_mesh_packages': [p for p in disk_non_meshes if p not in registered_packages]}
    return meshes, skipped, discovery


def collision_report(value):
    # Python removes a bool return when a UFunction also has out parameters;
    # a report struct retains both failure details and the success flag.
    return {'valid': value.get_editor_property('valid'),
            'issues': [str(v) for v in value.get_editor_property('errors')],
            'warnings': [str(v) for v in value.get_editor_property('warnings')]}


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = {'version': 1, 'valid': False, 'issues': [], 'stages': {}}
    stages = report['stages']

    def stage(name, operation):
        print('SKATE UNREAL stage: ' + name, flush=True)
        try:
            result = operation()
            stages[name] = result
            if not result.get('valid', False):
                report['issues'].append(name + ': validation failed')
            return result
        except Exception as error:
            stages[name] = {'valid': False, 'issues': [str(error)], 'traceback': traceback.format_exc()}
            report['issues'].append(name + ': ' + str(error))
            unreal.log_error(name + ': ' + str(error))
            return None

    stage('runtime_data', lambda: runtime_report(unreal.SkateRuntimeAssetLibrary.build_runtime_asset(
        str(yori.GAME / DESCRIPTOR['data_directory']), DESCRIPTOR['unreal_assets']['runtime_data'],
        DESCRIPTOR['manifest_sha256'], DESCRIPTOR['expected']['payloads'])))
    data = E.load_asset(DESCRIPTOR['unreal_assets']['runtime_data'])
    catalog = None

    def collision():
        nonlocal catalog
        meshes, skipped, discovery = static_meshes()
        stages['collision_discovery'] = discovery
        # The existing tree-LOD console tool validates every LOD's units from CPU
        # positions. Skating does not need them, but preserve that separate tool.
        cpu_meshes = [m for m in meshes if not m.get_path_name().startswith('/Game/Experiments/CityTrees/')]
        stripped = collision_report(unreal.SkateCollisionBuilderLibrary.strip_world_mesh_cpu_access_report(cpu_meshes, True))
        stages['static_mesh_cpu_strip'] = {**stripped, 'mesh_count': len(cpu_meshes),
            'retained_for_tree_lod_diagnostic': [m.get_path_name() for m in meshes if m not in cpu_meshes]}
        if not stripped['valid']:
            raise RuntimeError('Static mesh CPU stripping failed: ' + '; '.join(stripped['issues']))
        catalog, errors, warnings = unreal.SkateCollisionBuilderLibrary.build_catalog(
            meshes, DESCRIPTOR['unreal_assets']['collision_catalog'], True)
        return {'valid': catalog is not None and not errors, 'source_meshes': len(meshes),
                'skipped_no_collision': skipped, 'issues': [str(v) for v in errors],
                'warnings': [str(v) for v in warnings]}

    stage('collision_bake', collision)
    if catalog is not None:
        def validate_catalog():
            return collision_report(unreal.SkateCollisionBuilderLibrary.validate_catalog_report(catalog, True))
        stage('collision_words', validate_catalog)
        for map_path in PROFILE_SOURCE['validation_maps']:
            def validate_map(path=map_path):
                world = unreal.EditorLoadingAndSavingUtils.load_map(path)
                if world is None:
                    raise RuntimeError('Could not load validation map: ' + path)
                return {**collision_report(unreal.SkateCollisionBuilderLibrary.validate_world_report(world, catalog)), 'map': path}
            stage('collision_map:' + map_path, validate_map)
        def surface_and_scene():
            world = unreal.EditorLoadingAndSavingUtils.load_map(PROFILE_SOURCE['validation_maps'][0])
            mesh = E.load_asset('/Game/SkatePark/SM_SkatePath')
            if world is None or mesh is None:
                raise RuntimeError('Could not load collision fixture world/mesh')
            return collision_report(unreal.SkateCollisionBuilderLibrary.validate_surface_and_scene_report(world, mesh, catalog))
        stage('surface_and_scene', surface_and_scene)
    if data is not None and catalog is not None:
        def profile():
            asset = make_profile(data, catalog)
            return {'valid': True, 'asset_path': asset.get_path_name(), 'tuning': PROFILE_SOURCE}
        stage('profile', profile)
    stage('animation', lambda: json.loads(unreal.SkateAnimationValidationLibrary.validate_skate_animation(
        '/Game/Cairo/SK_Cairo.SK_Cairo', DESCRIPTOR['unreal_assets']['profile'],
        '/Script/Yorimichi.WandererAnimInstance')))
    report['valid'] = not report['issues']
    (OUTPUT / 'validation.json').write_text(json.dumps(report, indent=2) + '\n')
    if not report['valid']:
        raise RuntimeError('Skating Unreal integration failed: ' + '; '.join(report['issues']))
    print('SKATE UNREAL IMPORT COMPLETE', flush=True)


main()
