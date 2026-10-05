"""Import Cairo's bike (assets/vehicles/bike) into /Game/Japan/Assets on M_Bike. UBikeComponent assembles the parts
at runtime from the pivots in manifest.json, which is staged with the game data."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import json
import sys
from pathlib import Path

import unreal

HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
from import_village import import_mesh
from bike_material import material

OUT = yori.OUT / 'bike'
unreal.SystemLibrary.execute_console_command(None, 'Interchange.FeatureFlags.Import.FBX 0')
mat = material(); report = {}
for name, entry in json.loads((OUT / 'manifest.json').read_text())['parts'].items():
    mesh = import_mesh(OUT / 'assets' / (name + '.fbx'), '/Game/Japan/Assets', name); mesh.set_material(0, mat)
    b = mesh.get_bounding_box()
    # Unreal's FBX import mirrors Y into its left-handed frame, so check X and Z.
    assert abs(b.max.x - entry['max'][0] * 100) < .3 and abs(b.max.z - entry['max'][2] * 100) < .3, (name, 'axis/scale', b.max, entry['max'])
    unreal.EditorAssetLibrary.save_loaded_asset(mesh)
    report[name] = {'min': [b.min.x, b.min.y, b.min.z], 'max': [b.max.x, b.max.y, b.max.z], 'triangles': entry['triangles']}
(OUT / 'import-report.json').write_text(json.dumps(report, indent=2) + '\n')
unreal.log('BIKE IMPORT COMPLETE')
