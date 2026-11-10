"""FX master builders: M_FX_Additive and M_FX_Dust (sprite_material) and M_FX_Trail (trail).

Extracted from the donor generator games/yorimichi/unreal/Scripts/import_combat_fx.py at the V2 source baseline (docs/DECISIONS.md
D01; blob sha256 bf9820e1db843baee6fc4454ecc6ca4da1aec637efe67a8fefcba57923fd1c7d): the material helper is that file's lines 37-43,
the node helper its lines 46-49, sprite_material its lines 52-69 and the trail its lines 87-96 (a module body, wrapped here in one
function with its order and values kept). The expressions, parameter names, defaults, wiring and order are the donor's. Three things
differ, and each moves work out of the builder: no texture is imported here (the sprite and trail textures arrive through reads),
no asset is saved (the importer saves the one it accepts), and no import runs at module load, so the module imports without the
editor, where `unreal` is None and a builder cannot run.

A builder takes the destination package path, the loaded reads ({package: asset}) and the recipe's arguments as keyword arguments,
and returns the rebuilt material.
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


def _unlit_material(package):
    """donor material(name), import_combat_fx.py lines 37-43: cleared, unlit and two-sided."""
    material = _material(package)
    unreal.MaterialEditingLibrary.delete_all_material_expressions(material)
    material.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_UNLIT)
    material.set_editor_property('two_sided', True)
    return material


def _node(material, cls, x, y, **properties):
    """donor node(), import_combat_fx.py lines 46-49."""
    node = unreal.MaterialEditingLibrary.create_material_expression(material, cls, x, y)
    for key, value in properties.items():
        node.set_editor_property(key, value)
    return node


def sprite_material(package, reads, *, blend, texture):
    """donor sprite_material(name, blend, default_tex), import_combat_fx.py lines 52-69. `blend` is 'additive' (M_FX_Additive:
    the colour and the mask multiply into emissive) or 'translucent' (M_FX_Dust: the emissive colour, and the mask as opacity).
    `texture` is the read package of the sprite's default texture (the donor's textures['Glow'] or textures['Dust']).
    The donor's constants (the custom-data indices, the default 0 and the Saturate) are kept literal here."""
    if blend not in ('additive', 'translucent'):
        raise ValueError(f'{package}: blend is additive or translucent, not {blend!r}')
    MEL = unreal.MaterialEditingLibrary
    additive = blend == 'additive'
    mat = _unlit_material(package)
    mat.set_editor_property('blend_mode', unreal.BlendMode.BLEND_ADDITIVE if additive else unreal.BlendMode.BLEND_TRANSLUCENT)
    mat.set_editor_property('used_with_instanced_static_meshes', True)
    tex = _node(mat, unreal.MaterialExpressionTextureSampleParameter2D, -700, 0, parameter_name='Sprite', texture=reads[texture])
    data = [_node(mat, unreal.MaterialExpressionPerInstanceCustomData, -700, 200 + 90 * i, data_index=i, const_default_value=0.)
            for i in range(4)]
    rg = _node(mat, unreal.MaterialExpressionAppendVector, -480, 300)
    assert MEL.connect_material_expressions(data[1], '', rg, 'A')
    assert MEL.connect_material_expressions(data[2], '', rg, 'B')
    rgb = _node(mat, unreal.MaterialExpressionAppendVector, -330, 320)
    assert MEL.connect_material_expressions(rg, '', rgb, 'A')
    assert MEL.connect_material_expressions(data[3], '', rgb, 'B')
    mask = _node(mat, unreal.MaterialExpressionMultiply, -330, 60)
    assert MEL.connect_material_expressions(tex, 'R', mask, 'A')
    assert MEL.connect_material_expressions(data[0], '', mask, 'B')
    if additive:
        out = _node(mat, unreal.MaterialExpressionMultiply, -120, 120)
        assert MEL.connect_material_expressions(rgb, '', out, 'A')
        assert MEL.connect_material_expressions(mask, '', out, 'B')
        assert MEL.connect_material_property(out, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    else:
        assert MEL.connect_material_property(rgb, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
        sat = _node(mat, unreal.MaterialExpressionSaturate, -120, 60)
        assert MEL.connect_material_expressions(mask, '', sat, '')
        assert MEL.connect_material_property(sat, '', unreal.MaterialProperty.MP_OPACITY)
    MEL.recompile_material(mat)
    return mat


def trail(package, reads, *, texture, intensity):
    """donor M_FX_Trail, import_combat_fx.py lines 87-96 (module body, wrapped): unlit, additive, two-sided, for the slash ribbon.
    Emissive is the vertex colour times the vertex alpha times the streak texture's red times the Intensity parameter. `texture`
    is the read package of the streak texture (the donor's textures['Trail']); `intensity` is the donor's default of 4."""
    MEL = unreal.MaterialEditingLibrary
    tr = _unlit_material(package)
    tr.set_editor_property('blend_mode', unreal.BlendMode.BLEND_ADDITIVE)
    vc = _node(tr, unreal.MaterialExpressionVertexColor, -700, 0)
    tex = _node(tr, unreal.MaterialExpressionTextureSample, -700, 250, texture=reads[texture])
    param = _node(tr, unreal.MaterialExpressionScalarParameter, -700, 450, parameter_name='Intensity', default_value=intensity)
    a = _node(tr, unreal.MaterialExpressionMultiply, -450, 150)
    assert MEL.connect_material_expressions(vc, 'A', a, 'A')
    assert MEL.connect_material_expressions(tex, 'R', a, 'B')
    b = _node(tr, unreal.MaterialExpressionMultiply, -300, 250)
    assert MEL.connect_material_expressions(a, '', b, 'A')
    assert MEL.connect_material_expressions(param, '', b, 'B')
    c = _node(tr, unreal.MaterialExpressionMultiply, -150, 50)
    assert MEL.connect_material_expressions(vc, '', c, 'A')
    assert MEL.connect_material_expressions(b, '', c, 'B')
    assert MEL.connect_material_property(c, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.recompile_material(tr)
    return tr
