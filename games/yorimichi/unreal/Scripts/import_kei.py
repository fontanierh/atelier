"""Import the Mega Park car park's kei cars (assets/vehicles/kei) into /Game/Japan/Assets on M_Village, with their box
collision. ASuperUltraMegaPark::Spawn parks them from park.json "props"."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import json
import sys
from pathlib import Path

import unreal

HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
from import_village import import_mesh

OUT = yori.OUT / 'kei'
unreal.SystemLibrary.execute_console_command(None, 'Interchange.FeatureFlags.Import.FBX 0')
material = unreal.EditorAssetLibrary.load_asset('/Game/Japan/Materials/M_Village'); assert material
report = {}
for name, entry in json.loads((OUT / 'manifest.json').read_text()).items():
    mesh = import_mesh(OUT / 'assets' / (name + '.fbx'), '/Game/Japan/Assets', name); mesh.set_material(0, material)
    b = mesh.get_bounding_box(); assert abs(b.max.x - entry['max'][0] * 100) < .3, (name, 'axis/scale', b.max)
    boxes = len(mesh.get_editor_property('body_setup').get_editor_property('agg_geom').get_editor_property('convex_elems'))
    assert boxes == entry['collision_boxes'], (name, 'collision', boxes)
    unreal.EditorAssetLibrary.save_loaded_asset(mesh)
    report[name] = {'min': [b.min.x, b.min.y, b.min.z], 'max': [b.max.x, b.max.y, b.max.z], 'triangles': entry['triangles'],
                    'collision_boxes': boxes}
(OUT / 'import-report.json').write_text(json.dumps(report, indent=2) + '\n')
unreal.log('KEI IMPORT COMPLETE')
