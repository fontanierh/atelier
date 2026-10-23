"""Prepare saved original Stable controls through the immutable native functions/loop.

Run only in an isolated exact fixture Content root supplied by the host. Reload and
observe these saved controls in a separate editor process before claiming native parity.
"""
import ast
import hashlib
import json
import os
from pathlib import Path

import unreal
from atelier.export_manifest import real_directory
from atelier.model_files import member


def prepare(original_script, expected_sha256, build, destination):
    """Return saved original control paths, without altering the disabled world switch."""
    original_script, build = Path(original_script), Path(build)
    real_directory(original_script.parent); real_directory(build)
    if original_script.is_symlink() or hashlib.sha256(original_script.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError('Original Stable native script identity differs')
    if destination != '/Game/StableOriginalAtomicCanary': raise ValueError('Exact original Stable fixture root required')
    content = Path(unreal.Paths.project_content_dir()).absolute()
    real_directory(content)
    fixture_root = content / 'StableOriginalAtomicCanary'
    if os.path.lexists(fixture_root): raise ValueError('Fresh nonlinked original Stable disk root required')
    library = unreal.EditorAssetLibrary
    if library.does_directory_exist(destination): raise ValueError('Fresh isolated original Stable package root required')
    manifest = json.loads((build / 'manifest.json').read_text())
    placements = json.loads((build / 'placements.json').read_text())
    for row in manifest['files'].values():
        path = build / member(row['path']); real_directory(path.parent)
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('Original Stable GLB differs from its completed original manifest')
    material = library.load_asset('/Game/Japan/Materials/M_Arcade')
    if material is None: raise ValueError('Original current Stable material prerequisite missing')
    for entry in placements['meshes']:
        for slot in entry.get('slots', []):
            if library.load_asset('/Game/Japan/Hidamari/Materials/MI_HD_'+slot) is None:
                raise ValueError('Original current Stable surface prerequisite missing')
    tree = ast.parse(original_script.read_text())
    names = {'pipeline', 'sha', 'import_mesh', 'with_lods', 'box', 'box_cm', 'finish', 'bounds_cm'}
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    loops = [node for node in tree.body if isinstance(node, ast.For) and isinstance(node.target, ast.Name)
             and node.target.id == 'entry' and ast.unparse(node.iter) == "placements['meshes']"]
    if {node.name for node in functions} != names or len(loops) != 1:
        raise ValueError('Exact immutable Stable native function/owner-loop boundary differs')
    namespace = dict(unreal=unreal, Path=Path, hashlib=hashlib, BUILD=build, ROOT=destination,
        E=library, AT=unreal.AssetToolsHelpers.get_asset_tools(),
        REGISTRY=unreal.AssetRegistryHelpers.get_asset_registry(), CITY='/Game/Japan/Hidamari/Materials',
        material=material, placements=placements, manifest=manifest, report={})
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(original_script), 'exec'), namespace)
    unreal.SystemLibrary.execute_console_command(None, 'Editor.AsyncStaticMeshCompilation 0')
    unreal.load_module('StaticMeshEditor')
    namespace.update(meshes=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem),
        library=unreal.BelmonteTrainImportLibrary,
        SIMPLE=unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX,
        COMPLEX=unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    if namespace['meshes'] is None: raise ValueError('StaticMeshEditor unavailable for original control')
    exec(compile(ast.Module(body=loops, type_ignores=[]), str(original_script), 'exec'), namespace)
    # The actual original loop, collision finishing and three-LOD attachment have run.
    # Persist ALL controls and original auxiliary LOD packages, then exit this editor.
    paths = list(library.list_assets(destination, recursive=True, include_folder=False))
    for path in paths:
        asset = library.load_asset(path)
        if asset is None or not library.save_loaded_asset(asset, False):
            raise ValueError('Original Stable control failed to save: '+path)
    primary = {entry['name']: destination+'/'+entry['name'] for entry in placements['meshes']}
    if set(primary) != set(namespace['report']): raise ValueError('Incomplete original Stable native controls')
    if hashlib.sha256(original_script.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError('Original Stable native script changed during control creation')
    return dict(primary=primary, all_packages=list(map(str, paths)), original_report=namespace['report'],
        source_sha256=expected_sha256, complete=True, reloaded_observation_complete=False)
