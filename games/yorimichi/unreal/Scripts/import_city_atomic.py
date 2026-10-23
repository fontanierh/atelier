"""Receive all logical city owners as separate bounded mesh assets; never load parents."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import hashlib
import json
import os
import sys
from pathlib import Path
import unreal

ROOT = yori.OUT
sys.path.insert(0, str(yori.GAME))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mesh_import import import_mesh
from atelier import native_membership
from city_atomic_products import (obsolete_assets, owned_tiles, production_groups, native_bounds,
                                piece_material_paths, collision_matches, protected_files)


from import_city_surface_tiles import prepare_collision_import, finish_empty_collision
from city_distance_lods import distance_lods

def main():
    tag = os.environ['CITY_SURFACE_TILES_TAG']
    assert tag == 'v1_128m', 'Production city pieces require their canonical owner tag'
    folder = ROOT / 'city_surface_tiles' / tag
    manifest = json.loads((folder / 'manifest.json').read_text())
    groups = production_groups(manifest)
    production = yori.GAME / 'unreal/Content/Japan'
    before = protected_files(production)
    destination = '/Game/Experiments/CitySurfaces/' + tag
    # The source exporter replaces its folder; enumerate the native owner's
    # independent output root before importing, without relying on that report.
    previous = owned_tiles(unreal.EditorAssetLibrary.list_assets(destination, recursive=False,
                                                                 include_folder=False), destination)
    unreal.SystemLibrary.execute_console_command(None, 'Interchange.FeatureFlags.Import.FBX 0')
    unreal.SystemLibrary.execute_console_command(None, 'Editor.AsyncStaticMeshCompilation 0')
    unreal.load_module('StaticMeshEditor')
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    assert editor is not None
    report = {}
    for name, source in manifest['sources'].items():
        assert source['tiles'], ('Missing city surface pieces', name)
        # Material assets have their own world owner. Opening a whole render
        # parent just to discover these bindings defeats bounded preparation.
        slots = {slot: unreal.EditorAssetLibrary.load_asset(path)
                 for slot, path in piece_material_paths(name, source['source_material_slots']).items()}
        assert slots and all(slots.values()), (name, 'production materials')
        material = next(iter(slots.values()))
        imported = []
        lower, upper = [float('inf')]*3, [-float('inf')]*3
        for index, tile in enumerate(source['tiles'], 1):
            path = folder / name / (tile['name'] + '.fbx')
            assert hashlib.sha256(path.read_bytes()).hexdigest() == tile['sha256']
            mesh = import_mesh(path, destination, tile['name'], fresh_slots=True,
                before_import=lambda: prepare_collision_import(destination, tile['name'], editor))
            for i, s in enumerate(mesh.static_materials):
                key = str(s.get_editor_property('imported_material_slot_name'))
                assert key in slots, (tile['name'], 'unknown slot', key)
                if mesh.get_material(i) != slots[key]:
                    mesh.set_material(i, slots[key])
            assert mesh.get_num_triangles(0) == tile['triangles'], (tile['name'], 'triangle count changed')
            box = mesh.get_bounding_box()
            expected_min, expected_max = native_bounds(tile)
            for i, axis in enumerate(('x','y','z')):
                assert abs(getattr(box.min, axis) - expected_min[i]) < .2, (tile['name'], 'piece minimum bounds', axis)
                assert abs(getattr(box.max, axis) - expected_max[i]) < .2, (tile['name'], 'piece maximum bounds', axis)
                lower[i] = min(lower[i], getattr(box.min, axis))
                upper[i] = max(upper[i], getattr(box.max, axis))
            settings = editor.get_lod_build_settings(mesh, 0)
            if not settings.get_editor_property('use_full_precision_u_vs'):
                settings.set_editor_property('use_full_precision_u_vs', True)
                editor.set_lod_build_settings(mesh, 0, settings)
            body = mesh.get_editor_property('body_setup')
            collision = (unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AND_COMPLEX if source['source_collision_hulls']
                         else unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
            if body.get_editor_property('collision_trace_flag') != collision:
                body.set_editor_property('collision_trace_flag', collision)
            finish_empty_collision(mesh, tile, editor)
            assert collision_matches(mesh, source, tile), (tile['name'], 'authored UCX geometry')
            assert unreal.CitySurfaceValidation.validate_collision(mesh, tile['triangles'],
                bool(source['source_collision_hulls'])), (tile['name'], 'current cooked query surface')
            if (name.startswith('HD_Shop_') and name[8:].isdigit()) or name in ('HD_Station', 'HD_Shrine'):
                distance_lods(mesh, tile['name'], [(1.,1.),(.5,.28),(.15,.12),(.04,.05)])
            elif name.startswith('HD_House_'):
                distance_lods(mesh, tile['name'], [(1.,1.),(.4,.3),(.12,.12)])
            assert mesh.get_num_triangles(0) == tile['triangles'], (tile['name'], 'final render count')
            assert editor.get_lod_build_settings(mesh, 0).get_editor_property('use_full_precision_u_vs'), (tile['name'], 'full precision UVs')
            assert editor.get_num_uv_channels(mesh, 0) == len(tile['uv_channels']), (tile['name'], 'UV channel count')
            assert collision_matches(mesh, source, tile), (tile['name'], 'final authored UCX geometry')
            assert unreal.CitySurfaceValidation.validate_collision(mesh, tile['triangles'],
                bool(source['source_collision_hulls'])), (tile['name'], 'final cooked query surface')
            assert unreal.EditorAssetLibrary.save_loaded_asset(mesh, True), ('City tile save failed', tile['name'])
            imported.append(dict(name=tile['name'], triangles=mesh.get_num_triangles(0),
                                 material=material.get_path_name(), asset=mesh.get_path_name()))
            # The owner retains paths and counts, not all loaded piece geometry.
            # Collect in bounded batches, never once per unchanged mesh.
            mesh = body = None
            if index % 16 == 0:
                unreal.SystemLibrary.collect_garbage()
            unreal.log('CITY PIECES '+name+' '+str(index)+'/'+str(len(source['tiles'])))
        assert sum(t['triangles'] for t in imported) == source['source_triangles'], name
        expected_min, expected_max = native_bounds(source['source_bounds'])
        for i, axis in enumerate(('x','y','z')):
            assert abs(lower[i]-expected_min[i]) < .2, (name, 'minimum bounds', axis)
            assert abs(upper[i]-expected_max[i]) < .2, (name, 'maximum bounds', axis)
        report[name] = imported
    after = protected_files(production)
    assert after == before, 'Production Content/Japan changed during isolated import'
    # Current membership is complete before the previous owner's exact packages
    # retire. Unknown names and other tags never enter the deletion list.
    obsolete = obsolete_assets(previous, report, destination)
    # One preflight covers both former pieces and parents before any deletion.
    # Current/foreign package references must refuse the complete retirement.
    parents = {'/Game/Japan/Assets/'+name:[piece['asset'].split('.')[0] for piece in pieces]
               for name, pieces in groups.items()}
    current = [tile['asset'].split('.')[0] for tiles in report.values() for tile in tiles]
    replacements = {**parents, **{asset.split('.')[0]: current for asset in obsolete}}
    retired = native_membership.retire_replaced(unreal.EditorAssetLibrary, replacements)
    unreal.log('CITY PIECES retired packages=' + str(len(retired)))
    (folder / 'import-report.json').write_text(json.dumps(report, indent=2) + '\n')
    unreal.log('CITY SURFACE TILE IMPORT COMPLETE ' + tag)


if __name__ == '__main__':
    main()
