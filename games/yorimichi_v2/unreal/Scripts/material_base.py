"""The base-property override flags of a material instance (FMaterialInstanceBasePropertyOverrides), shared by the import
writer (import_asset.py) and the material report (report_materials.py).

UE 5.8's Python does not list a struct's properties in dir(), so the flags are named here from the engine header
(Engine/Public/Materials/MaterialInstanceBasePropertyOverrides.h, the 15 bOverride_* fields) and each one is probed by its
Python name. A flag that cannot be read stops the caller: a writer that cannot clear every flag would keep an override
its record does not state, and a report that cannot read every flag would report an incomplete set as complete.
"""
import re

FLAGS = ('OpacityMaskClipValue', 'BlendMode', 'ShadingModel', 'DitheredLODTransition', 'CastDynamicShadowAsMasked',
         'TwoSided', 'bIsThinSurface', 'OutputTranslucentVelocity', 'bHasPixelAnimation', 'bEnableTessellation',
         'DisplacementScaling', 'bEnableDisplacementFade', 'DisplacementFadeRange', 'MaxWorldPositionOffsetDisplacement',
         'CompatibleWithLumenCardSharing')


def snake(name):
    """C++ field name to UE Python's snake case: DitheredLODTransition -> dithered_lod_transition."""
    name = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', name)
    return re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name).lower()


def candidates(field):
    """The Python names a bOverride_<field> flag may have: a bool field's own b prefix may be kept or dropped."""
    names = ['override_' + snake(field)]
    if field.startswith('b') and field[1:2].isupper():
        names.append('override_' + snake(field[1:]))
    return names


def flags(overrides):
    """The Python name of every bOverride_* flag, probed on this struct; refuses when one cannot be read."""
    out = []
    for field in FLAGS:
        for name in candidates(field):
            try:
                overrides.get_editor_property(name)
            except Exception:
                continue
            out.append(name)
            break
        else:
            raise RuntimeError(f'base_property_overrides has no readable flag for bOverride_{field}')
    return out
