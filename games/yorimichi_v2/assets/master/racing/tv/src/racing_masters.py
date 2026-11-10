"""Racing master builder: M_RacingTv, the racing TVs' picture material.

Extracted from the donor module body games/yorimichi/unreal/Scripts/racing_tv_material.py at the V2 source baseline (docs/DECISIONS.md
D01; blob sha256 ea890e75e712104451256f62acaae1bb304b2fd577d350d3a6bb5a223dc00344). The donor runs its graph at module level; here it is
wrapped in one function, lines 18-53 of the donor kept in order with their values. No import runs at module load, so this module imports
without the editor, where `unreal` is None. The donor's save (line 56) is left to the importer, and the donor's own load of the engine
Black texture (line 36) arrives through reads.

A builder takes the destination package path, the loaded reads ({package: asset}) and the recipe's arguments as keyword arguments, and
returns the rebuilt material.
"""
try:
    import unreal
except ImportError:   # outside the editor: the functions are defined but cannot run
    unreal = None


def _material(package):
    """The material at a package path, reused when it exists (donor: E.load_asset, or AT.create_asset when it does not)."""
    folder, name = package.rsplit('/', 1)
    if unreal.EditorAssetLibrary.does_asset_exist(package):
        return unreal.EditorAssetLibrary.load_asset(package)
    return unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, folder, unreal.Material, unreal.MaterialFactoryNew())


def racing_tv(package, reads, *, brightness):
    """donor racing_tv_material.py lines 18-53. Unlit and opaque: the screen glows with its picture whatever the room's light. The
    picture is the Picture parameter (the broadcast's render target at runtime; its default here is the engine Black texture, read
    through reads), decoded from the display encoding to linear, scaled by Brightness (the donor's default 1), with the room's
    exposure undone and the result on emissive. `brightness` is the donor's default_value of 1."""
    MEL = unreal.MaterialEditingLibrary
    mat = _material(package)
    MEL.delete_all_material_expressions(mat)
    mat.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_UNLIT)
    mat.set_editor_property('blend_mode', unreal.BlendMode.BLEND_OPAQUE)
    mat.set_editor_property('two_sided', False)

    def node(cls, x, y, **properties):
        e = MEL.create_material_expression(mat, cls, x, y)
        for key, value in properties.items():
            e.set_editor_property(key, value)
        return e

    def link(a, out, b, into):
        assert MEL.connect_material_expressions(a, out, b, into), (a, out, b, into)

    picture = node(unreal.MaterialExpressionTextureSampleParameter2D, -700, 0, parameter_name='Picture',
                   texture=reads['/Engine/EngineResources/Black'])
    bright = node(unreal.MaterialExpressionScalarParameter, -700, 300, parameter_name='Brightness', default_value=brightness)
    decode = node(unreal.MaterialExpressionCustom, -350, 0, code='return saturate(pow(max(C, 0.), 2.2) * 1.04 - .004) * B;',
                  output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    inputs = []
    for name in ('C', 'B'):
        arg = unreal.CustomInput()
        arg.set_editor_property('input_name', name)
        inputs.append(arg)
    decode.set_editor_property('inputs', inputs)
    link(picture, 'RGB', decode, 'C')
    link(bright, '', decode, 'B')
    # The room's exposure undone: the screen shows its picture at the same brightness in a dim taproom as in the bright Salon.
    exposure = node(unreal.MaterialExpressionEyeAdaptationInverse, -100, 0)
    assert any(MEL.connect_material_expressions(decode, '', exposure, name)
               for name in ('LightValueInput', 'LightValue', 'Light Value')), 'EyeAdaptationInverse input'
    assert MEL.connect_material_property(exposure, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.recompile_material(mat)
    return mat
