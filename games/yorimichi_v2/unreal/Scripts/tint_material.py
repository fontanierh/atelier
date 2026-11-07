"""Set one vector parameter of a saved material instance and save only its package (C19: a shared definition edit).

Run through `editor.run` with V2_EDITOR_CLAIM and V2_EDITOR_PATHS naming the instance's package file. V2_TINT_ASSET
names the instance (/Game/...), V2_TINT_PARAMETER the vector parameter (default Tint) and V2_TINT_RGBA its new value
"r g b a". Nothing else is loaded for writing or saved.
"""
import os

import unreal as U

PATH = os.environ['V2_TINT_ASSET']
PARAMETER = os.environ.get('V2_TINT_PARAMETER') or 'Tint'
VALUE = U.LinearColor(*(float(v) for v in os.environ['V2_TINT_RGBA'].split()))

instance = U.EditorAssetLibrary.load_asset(PATH)
if not isinstance(instance, U.MaterialInstanceConstant):
    raise RuntimeError(f'{PATH} is not a material instance')
MEL = U.MaterialEditingLibrary
before = MEL.get_material_instance_vector_parameter_value(instance, PARAMETER)
names = sorted(str(n) for n in MEL.get_vector_parameter_names(instance.get_editor_property('parent')))
if PARAMETER not in names:
    raise RuntimeError(f'{PATH} has no vector parameter {PARAMETER}; its parent has {names}')
# UE 5.8's setter always returns False (MaterialEditingLibrary.cpp), so the value read back is the proof.
MEL.set_material_instance_vector_parameter_value(instance, PARAMETER, VALUE)
MEL.update_material_instance(instance)
after = MEL.get_material_instance_vector_parameter_value(instance, PARAMETER)
if max(abs(after.r - VALUE.r), abs(after.g - VALUE.g), abs(after.b - VALUE.b), abs(after.a - VALUE.a)) > 1e-4:
    raise RuntimeError(f'{PATH} {PARAMETER} reads {after} after setting {VALUE}')
if not U.EditorAssetLibrary.save_loaded_asset(instance, False):
    raise RuntimeError(f'could not save {PATH}')
U.log(f'V2 TINTED {PATH} {PARAMETER} {before} -> {after}')
