"""Import the go-kart (assets/vehicles/kart) into /Game/Japan/Kart with its matte painted material.

UDrivingComponent loads four meshes: the body with its origin on the ground, a separate seat, one wheel whose axle is +Y, and
the steering wheel whose hub is the origin and whose plane faces +X.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import json
import shutil
import sys
from pathlib import Path

import unreal

HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
from mesh_import import import_mesh
from kart_material import material as kart_material

sys.path.insert(0, str(HERE.parents[1] / 'tools/kart_grip_editor'))
from source_identity import playable_ids, profile_path, prepared_models

OUT = yori.OUT / 'kart'
unreal.SystemLibrary.execute_console_command(None, 'Interchange.FeatureFlags.Import.FBX 0')
material = kart_material()
manifest = json.loads((OUT / 'manifest.json').read_text())
report = {}
for name in ('SM_Kart_Body', 'SM_Kart_Seat', 'SM_Kart_Wheel', 'SM_Kart_SteeringWheel'):
    entry = manifest[name]
    source = OUT / 'assets' / (name + '.fbx')
    mesh = import_mesh(source, '/Game/Japan/Kart', name, seed=source, fresh_slots=True); mesh.set_material(0, material)
    b = mesh.get_bounding_box()
    expected_min = (entry['min'][0], -entry['max'][1], entry['min'][2])
    expected_max = (entry['max'][0], -entry['min'][1], entry['max'][2])
    for actual, expected in ((b.min, expected_min), (b.max, expected_max)):
        assert all(abs(a - e * 100) < .3 for a, e in zip((actual.x, actual.y, actual.z), expected)), (name, 'axis/scale', actual, expected)
    unreal.EditorAssetLibrary.save_loaded_asset(mesh)
    report[name] = {'min': [b.min.x, b.min.y, b.min.z], 'max': [b.max.x, b.max.y, b.max.z],
                    'triangles': entry['triangles']}
(OUT / 'import-report.json').write_text(json.dumps(report, indent=2) + '\n')
data = Path(__file__).resolve().parents[1] / 'Content/Data/kart/cockpit.json'
data.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(OUT / 'cockpit.json', data)
# The runtime checks a saved grip against the prepared model it was authored on, not against the live fit.
(data.parent / 'prepared-models.json').write_text(json.dumps(prepared_models(), indent=2) + '\n')
# Authoring is explicit: shipping never substitutes guessed curls for an unsaved character.
for character in playable_ids():
    source = profile_path(character)
    if not source.is_file():
        raise RuntimeError(f'Save the {character} grip in the kart grip editor before importing the kart')
    pose = json.loads(source.read_text())
    if pose.get('schema') != 1 or pose.get('character') != character or pose.get('layout') != manifest['layout']:
        raise RuntimeError(f'Stale or invalid kart grip: {character}; reopen and save in the current editor')
    target = data.parent / 'grips' / f'{character}.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
unreal.log('KART IMPORT COMPLETE')
