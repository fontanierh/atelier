"""Duplicate original city trees and attach leaf-outline LODs, in Experiments only."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import hashlib
import json
import os
import sys
from pathlib import Path
import unreal as U

ROOT = yori.OUT
sys.path.insert(0, str(Path(__file__).resolve().parent))
from experiment_mesh_import import import_static_mesh


def main():
    tag = os.environ['CITY_TREE_LODS_TAG']
    assert tag.replace('_', '').isalnum()
    folder = ROOT/'city_tree_lods'/tag
    spec = json.loads((folder/'manifest.json').read_text())
    assert spec['complete'] and spec['tag'] == tag
    production = yori.GAME/'unreal/Content/Japan'
    hashes = lambda: {str(p.relative_to(production)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in production.rglob('*') if p.is_file()}
    before = hashes()
    U.SystemLibrary.execute_console_command(None, 'Interchange.FeatureFlags.Import.FBX 0')
    U.SystemLibrary.execute_console_command(None, 'Editor.AsyncStaticMeshCompilation 0')
    U.load_module('StaticMeshEditor')
    meshes = U.get_editor_subsystem(U.StaticMeshEditorSubsystem)
    editor = U.EditorAssetLibrary
    assets = U.AssetToolsHelpers.get_asset_tools()
    destination = '/Game/Experiments/CityTrees/'+tag
    report = {}
    for name, entry in spec['sources'].items():
        original = editor.load_asset('/Game/Japan/Assets/'+name)
        assert original and original.get_num_lods() == 1, name
        assert original.get_num_triangles(0) == entry['original_triangles'], name
        assert original.get_num_sections(0) == 1, name
        target_path = destination+'/'+name+'_'+tag
        assert not editor.does_asset_exist(target_path), ('use a fresh tag', target_path)
        target = editor.duplicate_asset(original.get_path_name(), target_path)
        assert target, name
        material = original.get_material(0)
        collisions = (meshes.get_simple_collision_count(original), meshes.get_convex_collision_count(original))
        for lod in entry['lods']:
            path = folder/lod['file']
            assert hashlib.sha256(path.read_bytes()).hexdigest() == lod['sha256']
            source = import_static_mesh(assets, path, destination+'/lods', path.stem)
            # Validate each imported level; target bounds include unchanged LOD0
            # and would hide a tiny/mis-scaled lower level.
            ratio = source.get_bounds().sphere_radius/original.get_bounds().sphere_radius
            assert .85 < ratio < 1.05, (name,lod['level'],'invalid LOD units/bounds',ratio)
            source.set_material(0, material)
            assert source.get_num_triangles(0) == lod['triangles'], path
            assert meshes.set_lod_from_static_mesh(target, lod['level'], source, 0, True) == lod['level']
            editor.save_loaded_asset(source)
        target.set_editor_property('lod_for_collision', 0)
        target.set_material(0, material)
        assert target.get_num_lods() == 3
        assert target.get_num_triangles(0) == original.get_num_triangles(0), name
        assert (meshes.get_simple_collision_count(target), meshes.get_convex_collision_count(target)) == collisions
        # Combining all LODs can slightly change the fitted sphere; verify
        # actual box coordinates within 1 cm on these ~10 m trees.
        for field in ('origin','box_extent'):
            for axis in ('x','y','z'):
                actual=getattr(getattr(target.get_bounds(),field),axis)
                expected=getattr(getattr(original.get_bounds(),field),axis)
                assert abs(actual-expected)<1., (name,field,axis,actual,expected)
        assert all(target.get_num_sections(i) == 1 for i in range(3)), name
        # Set thresholds last: material/collision edits can rebuild render data.
        assert meshes.set_lod_screen_sizes(target, spec['screen_sizes'])
        editor.save_loaded_asset(target, only_if_is_dirty=False)
        sizes = list(meshes.get_lod_screen_sizes(target))
        assert all(abs(a-b)<1e-5 for a,b in zip(sizes, spec['screen_sizes'])), (name, sizes)
        report[name] = dict(asset=target.get_path_name(), triangles=[target.get_num_triangles(i) for i in range(3)],
            screen_sizes=list(meshes.get_lod_screen_sizes(target)), material=material.get_path_name(),
            dithered_lod_transition=bool(material.get_editor_property('dithered_lod_transition')),
            source_package_sha256=before['Assets/'+name+'.uasset'])
    assert hashes() == before, 'Production Content/Japan changed'
    (folder/'import-report.json').write_text(json.dumps(report, indent=2)+'\n')
    U.log('CITY TREE LODS IMPORT COMPLETE '+json.dumps(report))


if __name__ == '__main__':
    main()
