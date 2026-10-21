"""Export one independent plant model, without terrain, layout or placements."""
import hashlib
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from brinecove import foliage_models, foliage_names  # noqa: E402
from atelier.model_export import mesh_object, export, glb_info  # noqa: E402


def main(definition, destination):
    import bpy
    definition, destination = Path(definition), Path(destination)
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
    export(obj, path)
    triangles, names, bounds = glb_info(path)
    if (triangles <= 0 or not names or any(not slot.startswith('BC_') for slot in names)
            or any(not math.isfinite(value) for point in bounds for value in point)):
        raise ValueError('Invalid independent foliage model export: ' + builder.name)
    model = dict(name=builder.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                 triangles=triangles, bounds_m=bounds, slots=[slot[3:] for slot in names],
                 collision=False, lods=True)
    (destination / 'model.json').write_text(json.dumps(model, sort_keys=True, separators=(',', ':')) + '\n')
    print('FOLIAGE MODEL COMPLETE: ' + builder.name, flush=True)


if __name__ == '__main__':
    main(*sys.argv[sys.argv.index('--') + 1:])
