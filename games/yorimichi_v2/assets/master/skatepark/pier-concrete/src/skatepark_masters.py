"""Skatepark pier master builder: the seven M_Pier_<key> surfaces of the skatepark family.

pier_material is the per-key loop body of the donor generator games/yorimichi/unreal/Scripts/import_skatepark.py at the V2
source baseline (docs/DECISIONS.md D01): lines 132-174 of that file, sha256 5d07f84d217d82a87e6610344bffdbedefadb457e37cf6b472346ff833b7a9ea.
The graph, the expression classes, the parameter names and values, and the wiring are the donor's. Two things move out of
the builder: the texture import (donor lines 115-129, the texture() helper) is replaced by reads[package], which the importer
loads from the texture records; and the donor's per-key save (line 172) is not here. The importer saves the one rebuild it
accepts, after reading it back against the saved original.

The donor's `painted` master takes its metallic from `specs['painted']` (line 134, metallic 0 over the steel maps), and the
other keys from the texture writer's manifest (tools/pier_texture_finish.py lines 69-75: steel 1, the rest 0). Here metallic
is an argument of the family entry, not a value in this file. The mural has only an albedo map and no vertex-colour
modulation (donor line 152), so its base colour is the albedo sample alone.

Nothing runs at import: the module is functions only, so it imports without the Unreal editor, where `unreal` is None.
"""
try:
    import unreal
except ImportError:   # outside the editor: the functions are defined but cannot run
    unreal = None

TEXTURE_FOLDER = '/Game/SkatePark/Textures'
ROLES = ('albedo', 'normal', 'roughness')   # the donor's textures.json maps order


def _material(package):
    """The material at a package path, reused when it exists (donor: E.load_asset, or AT.create_asset when it does not)."""
    folder, name = package.rsplit('/', 1)
    if unreal.EditorAssetLibrary.does_asset_exist(package):
        return unreal.EditorAssetLibrary.load_asset(package)
    return unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, folder, unreal.Material, unreal.MaterialFactoryNew())


def pier_material(package, reads, *, key, metallic):
    """donor materials(), import_skatepark.py lines 132-174: the loop body for one key (lines 136-173).

    `reads` holds the pier's texture packages (T_Pier_<key>_<role>), one per map the texture writer made for this key; a role
    with no read is absent from the graph, as the donor's `if` branches make it."""
    MEL = unreal.MaterialEditingLibrary
    material = _material(package)
    MEL.delete_all_material_expressions(material)

    def node(cls, **values):
        n = MEL.create_material_expression(material, cls)
        for k, v in values.items():
            n.set_editor_property(k, v)
        return n

    def link(a, output, b, input):
        assert MEL.connect_material_expressions(a, output, b, input), (key, output, input)

    samples = {}
    for role in ROLES:
        texture = f'{TEXTURE_FOLDER}/T_Pier_{key}_{role}'
        if texture not in reads:
            continue
        sampler = unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL if role == 'normal' else (
            unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR if role == 'roughness' else unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
        samples[role] = node(unreal.MaterialExpressionTextureSample, texture=reads[texture], sampler_type=sampler)
    if key == 'mural':
        colour = samples['albedo']; colour_output = 'RGB'
    else:
        vc = node(unreal.MaterialExpressionVertexColor)
        colour = node(unreal.MaterialExpressionCustom,
                      code='float3 L=lerp(C/12.92,pow((C+.055)/1.055,2.4),step(.04045,C)); return L*D*2;',
                      output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3)
        args = []
        for k in ('C', 'D'):
            arg = unreal.CustomInput(); arg.set_editor_property('input_name', k); args.append(arg)
        colour.set_editor_property('inputs', args)
        link(vc, '', colour, 'C'); link(samples['albedo'], 'RGB', colour, 'D'); colour_output = ''
    assert MEL.connect_material_property(colour, colour_output, unreal.MaterialProperty.MP_BASE_COLOR)
    if 'normal' in samples:
        MEL.connect_material_property(samples['normal'], 'RGB', unreal.MaterialProperty.MP_NORMAL)
    if 'roughness' in samples:
        MEL.connect_material_property(samples['roughness'], 'R', unreal.MaterialProperty.MP_ROUGHNESS)
    metal = node(unreal.MaterialExpressionConstant, r=metallic)
    MEL.connect_material_property(metal, '', unreal.MaterialProperty.MP_METALLIC)
    fill = node(unreal.MaterialExpressionMultiply, const_b=.035)
    link(colour, colour_output, fill, 'A'); MEL.connect_material_property(fill, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.layout_material_expressions(material); MEL.recompile_material(material)
    return material
