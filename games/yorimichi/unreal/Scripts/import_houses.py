"""Targeted import of the houses on the main road (games/yorimichi/world/regions/houses/README.md).

Imports build/yorimichi/houses/assets/*.fbx into /Game/Japan/Assets, where JapanWorld places them from world.json
(House_A/B/C on their lots, HouseLot_1..5). Houses carry one slot, M_Village, and block with their UCX boxes (simple
and complex). Lots carry two slots: 'Village' (kerb, hedge, walls, stones) gets M_Village and 'Ground' (the terrace)
gets the terrain's MI_Ground so it matches the hillside; a lot collides with its render mesh (complex as simple) so
the terrace, steps, hedge and walls are all solid. No other asset is touched. Writes
build/yorimichi/houses/import-report.json.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import hashlib
import json
import runpy
from pathlib import Path
import unreal

HERE = Path(__file__).resolve().parent
ROOT = yori.OUT
OUT = ROOT / 'houses'
helper = runpy.run_path(str(HERE / 'import_village.py'))     # import_mesh only; its main() does not run
E = unreal.EditorAssetLibrary
unreal.SystemLibrary.execute_console_command(None, 'Interchange.FeatureFlags.Import.FBX 0')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


identity = json.loads((OUT / 'build-identity.json').read_text())
for source, digest in identity['sources'].items():
    assert sha(yori.REGIONS / source) == digest, 'Rebuild houses: source changed: ' + source
assert sha(ROOT / 'world.json') == identity['world_sha256'], 'Rebuild houses for the current layout'
assert sha(ROOT / 'heightmap.npy') == identity['heightmap_sha256'], 'Rebuild houses for the current terrain'
for filename, digest in identity['exports'].items():
    assert sha(OUT / 'assets' / filename) == digest, 'Incomplete houses export: ' + filename
manifest = json.loads((OUT / 'manifest.json').read_text())

materials = {'Village': E.load_asset('/Game/Japan/Materials/M_Village'), 'Ground': E.load_asset('/Game/Japan/Materials/MI_Ground')}
assert materials['Village'], 'M_Village is missing: import the village first'
assert materials['Ground'], 'MI_Ground is missing: import the world first'

report = {}
for name, entry in manifest.items():
    mesh = helper['import_mesh'](OUT / 'assets' / f'{name}.fbx', '/Game/Japan/Assets', name)
    slots = [str(s.get_editor_property('imported_material_slot_name')).split('.')[0] for s in mesh.static_materials]
    assert sorted(slots) == sorted(entry['materials']), (name, 'material slots', slots, entry['materials'])
    for i, slot in enumerate(slots):
        mesh.set_material(i, materials[slot])
    body = mesh.get_editor_property('body_setup'); assert body
    lot = name.startswith('HouseLot_')
    body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE if lot
                             else unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AND_COMPLEX)
    convex = len(body.get_editor_property('agg_geom').get_editor_property('convex_elems'))
    assert convex >= entry['collision_boxes'], (name, convex, entry['collision_boxes'])
    box = mesh.get_bounding_box()
    assert abs(box.max.z - entry['max'][2] * 100) < .5, (name, 'metres-to-centimetres conversion', box.max.z)
    E.save_loaded_asset(mesh)
    report[name] = {'imported': True, 'materials': slots, 'collision_hulls': convex,
                    'bounds_min': [box.min.x, box.min.y, box.min.z], 'bounds_max': [box.max.x, box.max.y, box.max.z]}
(OUT / 'import-report.json').write_text(json.dumps(report, indent=2) + '\n')
unreal.log('HOUSES IMPORT COMPLETE')
