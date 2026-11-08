"""Blend foliage detail levels and fade coverage at instance cull distances."""
import unreal as U


def enable_distance_fade(material):
    # HISM only blends LODs when EVERY section opts in, including opaque bark.
    material.set_editor_property('dithered_lod_transition',True)
    edit = U.MaterialEditingLibrary
    source = edit.get_material_property_input_node(material,U.MaterialProperty.MP_OPACITY_MASK)
    if source.get_editor_property('desc') == 'Japan instance distance fade': return
    output = edit.get_material_property_input_node_output_name(material,U.MaterialProperty.MP_OPACITY_MASK)
    fade = edit.create_material_expression(material,U.MaterialExpressionPerInstanceFadeAmount,-300,-350)
    multiply = edit.create_material_expression(material,U.MaterialExpressionMultiply,0,-350)
    multiply.set_editor_property('desc','Japan instance distance fade')
    assert edit.connect_material_expressions(source,output,multiply,'A')
    assert edit.connect_material_expressions(fade,'',multiply,'B')
    assert edit.connect_material_property(multiply,'',U.MaterialProperty.MP_OPACITY_MASK)


def enable_bark_lod_blend(material):
    # Bark shares the opaque master with buildings/props. Override this one
    # instance instead of enabling a masked shader permutation for the world.
    overrides = material.get_editor_property('base_property_overrides')
    overrides.set_editor_property('override_dithered_lod_transition',True)
    overrides.set_editor_property('dithered_lod_transition',True)
    material.set_editor_property('base_property_overrides',overrides)
    U.MaterialEditingLibrary.update_material_instance(material)


def supports_lod_blend(material):
    """Resolve overrides, as HISM requires blending on all slots, even bark."""
    if isinstance(material,U.Material):
        return bool(material.get_editor_property('dithered_lod_transition'))
    overrides = material.get_editor_property('base_property_overrides')
    if overrides.get_editor_property('override_dithered_lod_transition'):
        return bool(overrides.get_editor_property('dithered_lod_transition'))
    return supports_lod_blend(material.get_editor_property('parent'))
