"""Retain the three production trees' cooked CPU buffers without reimporting the world.

The desktop LOD swap compares their vertices with the optimized variants. Unreal strips cooked CPU buffers unless
allow_cpu_access is set. This metadata overlay follows the world import and runs before the desktop variants.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'world'))
import yori  # noqa: E402
import json
import hashlib
import unreal as U

TREES = ('HD_ArcadeTree', 'HD_PlazaTreeGold', 'HD_PlazaTreeOrange')


def geometry(mesh):
    bounds = mesh.get_bounds()
    return dict(lods=mesh.get_num_lods(), triangles=mesh.get_num_triangles(0), sections=mesh.get_num_sections(0),
                material=mesh.get_material(0).get_path_name(),
                bounds={field: [getattr(getattr(bounds, field), axis) for axis in ('x', 'y', 'z')]
                        for field in ('origin', 'box_extent')})


def main():
    report = {}
    for name in TREES:
        mesh = U.EditorAssetLibrary.load_asset('/Game/Japan/Assets/' + name)
        assert mesh and mesh.get_num_lods() == 1, ('Missing production tree', name)
        before = geometry(mesh)
        changed = not mesh.get_editor_property('allow_cpu_access')
        if changed:
            mesh.set_editor_property('allow_cpu_access', True)
            assert U.EditorAssetLibrary.save_loaded_asset(mesh, only_if_is_dirty=False), name
        assert mesh.get_editor_property('allow_cpu_access'), name
        assert geometry(mesh) == before, ('CPU metadata changed production geometry/material', name)
        package = yori.GAME / 'unreal' / 'Content' / 'Japan' / 'Assets' / (name + '.uasset')
        report[name] = dict(asset=mesh.get_path_name(), allow_cpu_access=True, changed=changed, geometry=before,
                            sha256=hashlib.sha256(package.read_bytes()).hexdigest())
        U.log('CITY TREE CPU ACCESS ' + name + ' enabled=1 changed=' + str(int(changed)))
    folder = yori.OUT / 'city_tree_lods'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'production-cpu-access.json').write_text(json.dumps(report, indent=2) + '\n')
    U.log('CITY TREE CPU ACCESS COMPLETE')


if __name__ == '__main__':
    main()
