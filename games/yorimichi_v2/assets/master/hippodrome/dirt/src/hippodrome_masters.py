"""Hippodrome master builders: M_HD_Structure, and the M_HD_<surface> masters (grass, dirt, stone and rail).

Extracted from the donor generator games/yorimichi/unreal/Scripts/import_hippodrome.py at the V2 source baseline
(docs/DECISIONS.md D01): structure_material is that file's lines 59-78 and surface is its lines 36-55. The expressions,
parameter names, defaults, wiring and order are the donor's. Two things differ, and both move work out of the builder:
no asset is saved here (the importer saves the one it accepts, after reading it back against the saved original), and no
engine or project asset is loaded here (the importer passes every read in). Nothing runs at import: the module is
functions only, so it imports without the Unreal editor, where `unreal` is None and a builder cannot run.

A builder takes the destination package path, the loaded reads ({package: asset}) and the recipe's arguments as keyword
arguments, and returns the rebuilt material.
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


def _constant(material, value, prop):
    """One constant, connected to a material property (the donor's loop body)."""
    node = unreal.MaterialEditingLibrary.create_material_expression(material, unreal.MaterialExpressionConstant)
    node.set_editor_property('r', value)
    assert unreal.MaterialEditingLibrary.connect_material_property(node, '', prop)


def surface(package, reads, *, roughness, two_sided, texture=None, colour_r=None, colour_g=None, colour_b=None):
    """donor surface(), import_hippodrome.py lines 36-55.

    `texture` is the read package of a colour map (the donor's T_HD_Grass.png and T_HD_Dirt.png, here the texture records
    T_Grass and T_Dirt). `colour_r/g/b` are a constant linear base colour (the donor's tuples for stone and rail). Exactly one
    of the two is given."""
    if (texture is None) == (colour_r is None):   # checked before any engine call: a bad recipe touches nothing
        raise ValueError(f'{package}: a surface takes a texture or a colour, exactly one')
    if colour_r is not None and (colour_g is None or colour_b is None):
        raise ValueError(f'{package}: a colour needs colour_r, colour_g and colour_b')
    MEL = unreal.MaterialEditingLibrary
    material = _material(package)
    MEL.delete_all_material_expressions(material)
    material.set_editor_property('two_sided', two_sided)
    if texture is not None:
        node = MEL.create_material_expression(material, unreal.MaterialExpressionTextureSample)
        node.set_editor_property('texture', reads[texture])
        node.set_editor_property('sampler_type', unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
        assert MEL.connect_material_property(node, 'RGB', unreal.MaterialProperty.MP_BASE_COLOR)
    else:
        node = MEL.create_material_expression(material, unreal.MaterialExpressionConstant3Vector)
        node.set_editor_property('constant', unreal.LinearColor(colour_r, colour_g, colour_b, 1.))
        assert MEL.connect_material_property(node, '', unreal.MaterialProperty.MP_BASE_COLOR)
    for value, prop in ((roughness, unreal.MaterialProperty.MP_ROUGHNESS),
                        (0., unreal.MaterialProperty.MP_METALLIC),
                        (.3, unreal.MaterialProperty.MP_SPECULAR)):
        _constant(material, value, prop)
    MEL.layout_material_expressions(material)
    MEL.recompile_material(material)
    return material


def structure_material(package, reads, *, texture):
    """donor structure_material(), import_hippodrome.py lines 59-78: the venue's painted structures, a white base map
    (`texture`, the read package of the engine's WhiteSquareTexture) multiplied into emissive, roughness .7 and specular .3."""
    MEL = unreal.MaterialEditingLibrary
    material = _material(package)
    MEL.delete_all_material_expressions(material)
    material.set_editor_property('two_sided', True)
    base = MEL.create_material_expression(material, unreal.MaterialExpressionTextureSampleParameter2D)
    base.set_editor_property('parameter_name', 'BaseColorTexture')
    base.set_editor_property('texture', reads[texture])
    assert MEL.connect_material_property(base, 'RGB', unreal.MaterialProperty.MP_BASE_COLOR)
    fill = MEL.create_material_expression(material, unreal.MaterialExpressionMultiply)
    fill.set_editor_property('const_b', .3)
    assert MEL.connect_material_expressions(base, 'RGB', fill, 'A')
    assert MEL.connect_material_property(fill, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    _constant(material, .7, unreal.MaterialProperty.MP_ROUGHNESS)
    _constant(material, .3, unreal.MaterialProperty.MP_SPECULAR)
    MEL.recompile_material(material)
    return material
