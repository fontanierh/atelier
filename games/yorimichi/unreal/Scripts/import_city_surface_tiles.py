"""Import a completed, isolated partition; never reimport production geometry/materials.

Set CITY_SURFACE_TILES_TAG to the tag produced by city_surface_tiles.py.
Use a guarded commandlet with -noshaderworker. No level is saved.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import hashlib
import json
import os
import sys
from pathlib import Path
import unreal

ROOT = yori.OUT
sys.path.insert(0, str(Path(__file__).resolve().parent))
from import_village import import_mesh


def main():
    tag = os.environ['CITY_SURFACE_TILES_TAG']
    assert tag.replace('_', '').isalnum()
    folder = ROOT / 'city_surface_tiles' / tag
    manifest = json.loads((folder / 'manifest.json').read_text())
    assert manifest['complete'] and manifest['tag'] == tag
    production = yori.GAME / 'unreal/Content/Japan'
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in production.rglob('*') if p.is_file()}
    destination = '/Game/Experiments/CitySurfaces/' + tag
    unreal.SystemLibrary.execute_console_command(None, 'Interchange.FeatureFlags.Import.FBX 0')
    report = {}
    for name, source in manifest['sources'].items():
        original = unreal.EditorAssetLibrary.load_asset('/Game/Japan/Assets/' + name)
        assert original and original.get_num_triangles(0) == source['source_triangles'], name
        # The textured city meshes have one slot per surface (world/regions/hidamari/surfaces.py): match them by name.
        slots = {str(s.get_editor_property('imported_material_slot_name')): s.get_editor_property('material_interface')
                 for s in original.static_materials}
        assert slots and all(slots.values()), (name, 'production materials')
        material = original.get_material(0)
        imported = []
        lower, upper = [float('inf')]*3, [-float('inf')]*3
        for tile in source['tiles']:
            path = folder / (tile['name'] + '.fbx')
            assert hashlib.sha256(path.read_bytes()).hexdigest() == tile['sha256']
            mesh = import_mesh(path, destination, tile['name'], fresh_slots=True)   # the slots of this partition, not a previous one's
            for i, s in enumerate(mesh.static_materials):
                key = str(s.get_editor_property('imported_material_slot_name'))
                assert key in slots, (tile['name'], 'unknown slot', key)
                mesh.set_material(i, slots[key])
            assert mesh.get_num_triangles(0) == tile['triangles'], (tile['name'], 'triangle count changed')
            box = mesh.get_bounding_box()
            for i, axis in enumerate(('x','y','z')):
                lower[i] = min(lower[i], getattr(box.min, axis))
                upper[i] = max(upper[i], getattr(box.max, axis))
            # Collision remains on the untouched hidden original runtime component.
            unreal.EditorAssetLibrary.save_loaded_asset(mesh)
            imported.append(dict(name=tile['name'], triangles=mesh.get_num_triangles(0),
                                 material=material.get_path_name(), asset=mesh.get_path_name()))
        assert sum(t['triangles'] for t in imported) == source['source_triangles'], name
        box = original.get_bounding_box()
        for i, axis in enumerate(('x','y','z')):
            assert abs(lower[i]-getattr(box.min, axis)) < .2, (name, 'minimum bounds', axis)
            assert abs(upper[i]-getattr(box.max, axis)) < .2, (name, 'maximum bounds', axis)
        report[name] = imported
    after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in production.rglob('*') if p.is_file()}
    assert after == before, 'Production Content/Japan changed during isolated import'
    (folder / 'import-report.json').write_text(json.dumps(report, indent=2) + '\n')
    unreal.log('CITY SURFACE TILE IMPORT COMPLETE ' + tag)


if __name__ == '__main__':
    main()
