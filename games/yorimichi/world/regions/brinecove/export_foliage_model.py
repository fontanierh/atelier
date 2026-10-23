"""Export one independent plant model, without terrain, layout or placements."""
import hashlib
import json
import math
from pathlib import Path
import sys

_source = Path(__file__).resolve()
for _path in (_source.parents[5] / 'platform/studio', _source.parents[1]):
    sys.path.insert(0, str(_path))
from brinecove import foliage_models, foliage_names  # noqa: E402
from atelier.model_export import mesh_object, glb_info  # noqa: E402
from atelier.blender.gltf import export_atomic_glb  # noqa: E402
from atelier.export_manifest import real_directory, TRIANGLE_LIMIT  # noqa: E402
from atelier.model_files import regular_files  # noqa: E402


def main(definition, destination):
    import bpy
    definition, destination = Path(definition), Path(destination)
    real_directory(definition.parent); destination = real_directory(destination)
    if definition.is_symlink() or not definition.is_file(): raise ValueError('Linked plant definition')
    if destination.exists() and (regular_files(destination) - {'model.glb', 'model.json'}
                                 or any(p.is_dir() for p in destination.iterdir())):
        raise ValueError('Foreign independent plant product')
    builder = foliage_models.build(json.loads(definition.read_text()))
    builder.name = foliage_names.name(definition.stem)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    materials = {}
    for slot in sorted(set(builder.mats)):
        material = bpy.data.materials.new('BC_' + slot)
        material.use_nodes = True
        materials[slot] = material
    obj = mesh_object(builder, materials)
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / 'model.glb'
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True); bpy.context.view_layer.objects.active = obj
    export_atomic_glb(path, options=dict(export_apply=True, export_image_format='NONE'))
    triangles, names, bounds = glb_info(path)
    if (not 0 < triangles <= TRIANGLE_LIMIT or not names or any(not slot.startswith('BC_') for slot in names)
            or any(not math.isfinite(value) for point in bounds for value in point)):
        raise ValueError('Invalid independent foliage model export: ' + builder.name)
    model = dict(name=builder.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                 triangles=triangles, bounds_m=bounds, slots=[slot[3:] for slot in names],
                 collision=False, lods=True)
    (destination / 'model.json').write_text(json.dumps(model, sort_keys=True, separators=(',', ':')) + '\n')
    print('FOLIAGE MODEL COMPLETE: ' + builder.name, flush=True)


if __name__ == '__main__':
    main(*sys.argv[sys.argv.index('--') + 1:])
