"""Mega Park retail master builder: M_RetailOpaque, M_RetailMasked and M_RetailTranslucent (retail_material, alpha 0, 1 and 2).

Extracted from the donor generator games/yorimichi/unreal/Scripts/import_megapark.py at the V2 source baseline (docs/DECISIONS.md D01;
blob sha256 ac0c1df05fd3ff3b48862ad68a07c28189afb7fc3663652f7020a33106f80a7a, the same bytes as the committed copy in
adopted/megapark/base-materials/source). The graph is donor material(alpha, defaults), lines 68-163, kept in order with its values; the
only changes are the ones that move work out of the builder: the donor's own name, folder and load-or-create are replaced by _material,
the donor's save is left to the importer, and the donor's default textures arrive through reads. No import runs at module load, so this
module imports without the editor, where `unreal` is None and a builder cannot run.

The donor's default textures (import_megapark.py lines 183-188) are T_DefaultWhite, T_DefaultLinear, T_DefaultBlack and T_DefaultNormal,
owned by adopted/megapark/shared-textures-common. They are named here so the builder can pick them out of reads.

A builder takes the destination package path, the loaded reads ({package: asset}) and the recipe's arguments as keyword arguments, and
returns the rebuilt material.
"""
try:
    import unreal
except ImportError:   # outside the editor: the functions are defined but cannot run
    unreal = None

WHITE = '/Game/MegaPark/Textures/T_DefaultWhite'
LINEAR = '/Game/MegaPark/Textures/T_DefaultLinear'
BLACK = '/Game/MegaPark/Textures/T_DefaultBlack'
NORMAL = '/Game/MegaPark/Textures/T_DefaultNormal'


def _material(package):
    """The material at a package path, reused when it exists (donor: E.load_asset, or AT.create_asset when it does not)."""
    folder, name = package.rsplit('/', 1)
    if unreal.EditorAssetLibrary.does_asset_exist(package):
        return unreal.EditorAssetLibrary.load_asset(package)
    return unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, folder, unreal.Material, unreal.MaterialFactoryNew())


def retail_material(package, reads, *, alpha):
    """Translate original texture bindings into a shared, lit Unreal material graph.

    Diffuse and decals use their authored UVs; macro overlay and detail retain their source scale. The island's sun,
    sky and Lumen light the park like the terrain around it (docs/MEGAPARK.md, "Restyle"). The original baked
    irradiance (4*L*L, UV1) stays only as ambient occlusion: divided by the lightmap's sunlit level (LightmapNorm)
    and applied at LightmapOcclusion strength, so its baked sun shadows never compete with the island's.
    """
    if alpha not in (0, 1, 2):
        raise ValueError(f'{package}: alpha is 0 (opaque), 1 (masked) or 2 (translucent), not {alpha!r}')
    MEL = unreal.MaterialEditingLibrary
    # The donor's `defaults` (import_megapark.py lines 183-188): the same for every retail parent, so they are kept here.
    defaults = {'Diffuse': reads[WHITE], 'Decal': reads[WHITE], 'Macro': reads[WHITE], 'Lightmap': reads[LINEAR],
                'Normal': reads[NORMAL], 'Detail': reads[NORMAL], 'Specular': reads[BLACK], 'Transparent': reads[WHITE]}
    m = _material(package)
    MEL.delete_all_material_expressions(m)
    m.set_editor_property('blend_mode', (unreal.BlendMode.BLEND_OPAQUE, unreal.BlendMode.BLEND_MASKED, unreal.BlendMode.BLEND_TRANSLUCENT)[alpha])
    m.set_editor_property('two_sided', alpha != 0)
    m.set_editor_property('opacity_mask_clip_value', .5)

    def node(cls, **values):
        n = MEL.create_material_expression(m, cls)
        for key, value in values.items(): n.set_editor_property(key, value)
        return n

    def scalar(name, value):
        return node(unreal.MaterialExpressionScalarParameter, parameter_name=name, default_value=value)

    def link(a, output, b, input):
        assert MEL.connect_material_expressions(a, output, b, input), (output, input)

    def custom(code, inputs, kind=unreal.CustomMaterialOutputType.CMOT_FLOAT3):
        n = node(unreal.MaterialExpressionCustom, code=code, output_type=kind)
        args = []
        for key, (source, output) in inputs.items():
            arg = unreal.CustomInput(); arg.set_editor_property('input_name', key); args.append(arg)
        n.set_editor_property('inputs', args)
        for key, (source, output) in inputs.items(): link(source, output, n, key)
        return n

    uv = [node(unreal.MaterialExpressionTextureCoordinate, coordinate_index=i) for i in range(3)]
    macro_uv = node(unreal.MaterialExpressionMultiply)
    link(uv[0], '', macro_uv, 'A'); link(scalar('MacroScale', 1.), '', macro_uv, 'B')
    detail_uv = node(unreal.MaterialExpressionMultiply)
    link(uv[0], '', detail_uv, 'A'); link(scalar('DetailScale', 1.), '', detail_uv, 'B')
    bindings = {'Diffuse': (uv[0], False), 'Decal': (uv[2], False), 'Macro': (macro_uv, False),
                'Lightmap': (uv[1], True), 'Normal': (uv[0], True), 'Detail': (detail_uv, True),
                'Specular': (uv[0], True), 'Transparent': (uv[0], False)}
    samples = {}
    for key, (coords, linear) in bindings.items():
        sampler = unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL if key in ('Normal', 'Detail') else (
            unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR if linear else unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
        samples[key] = node(unreal.MaterialExpressionTextureSampleParameter2D, parameter_name=key,
                            texture=defaults[key], sampler_type=sampler)
        link(coords, '', samples[key], 'UVs')
    base = custom('float3 B=lerp(D, C, saturate(CA*UseDecal)); return B*lerp(1.0, M, MacroOpacity);',
        {'D': (samples['Diffuse'], 'RGB'), 'C': (samples['Decal'], 'RGB'), 'CA': (samples['Decal'], 'A'),
         'M': (samples['Macro'], 'RGB'), 'UseDecal': (scalar('UseDecal', 0.), ''), 'MacroOpacity': (scalar('MacroOpacity', 0.), '')})
    normal = custom('float3 T=float3(N.xy+D.xy,N.z*D.z); return normalize(T);',
                    {'N': (samples['Normal'], 'RGB'), 'D': (samples['Detail'], 'RGB')})
    occlusion = custom('float l=dot(4.0*L*L,float3(.2126,.7152,.0722))/max(Norm,.001);'
                       'return lerp(1.0,sqrt(saturate(l)),Strength*HasLightmap);',
                       {'L': (samples['Lightmap'], 'RGB'), 'Norm': (scalar('LightmapNorm', 3.), ''),
                        'Strength': (scalar('LightmapOcclusion', .45), ''), 'HasLightmap': (scalar('HasLightmap', 0.), '')},
                       unreal.CustomMaterialOutputType.CMOT_FLOAT1)
    # Moss and lichen on the rock where it faces up (the paintover concepts/improve-riding): in patches, and within them
    # in the texture's dark cracks, with a little on the faces between. World-space normal and position, so it follows
    # the placed park, not the UVs. Moss is 0 everywhere but the rock.
    moss = custom('float3 C=B*Albedo; float l=dot(B,float3(.2126,.7152,.0722));'
                  'float up=saturate((N.z-.6)/.3);'
                  'float a=sin(W.x*.0131+sin(W.y*.0107)*2.3)*sin(W.y*.0119+sin(W.x*.0083)*1.9);'
                  'float b=sin(W.x*.047+W.z*.031+sin(W.y*.043)*1.7)*sin(W.y*.051-W.z*.027);'
                  'float c=sin(W.x*.11+sin(W.y*.093)*1.4)*sin(W.y*.12+W.z*.07+sin(W.x*.081)*1.2);'
                  'float patch=saturate((up*(.55+.45*a+.25*b)-.5)*3.);'
                  'float crack=saturate((.17-l)*10.);'
                  'float m=patch*saturate(crack*1.3+.2*(.5+.5*c))*Moss;'
                  'float3 G=lerp(float3(.035,.05,.014),float3(.075,.095,.026),saturate(.5+.5*c));'
                  'return lerp(C,G*(.75+.5*saturate(l*3.)),m);',
                  {'B': (base, ''), 'Albedo': (scalar('Albedo', 1.), ''), 'Moss': (scalar('Moss', 0.), ''),
                   'N': (node(unreal.MaterialExpressionVertexNormalWS), ''),
                   'W': (node(unreal.MaterialExpressionWorldPosition), '')})
    colour = moss
    # Matte like the terrain; the original specular map keeps a little sheen on polished concrete and metal.
    specular = custom('return S*SpecularScale;', {'S': (samples['Specular'], 'R'), 'SpecularScale': (scalar('SpecularScale', .35), '')},
                      unreal.CustomMaterialOutputType.CMOT_FLOAT1)
    rough = custom('return lerp(1.0,clamp(1.0-S*.6,.25,1.0),Gloss);', {'S': (samples['Specular'], 'R'), 'Gloss': (scalar('Gloss', .5), '')},
                   unreal.CustomMaterialOutputType.CMOT_FLOAT1)
    # No emissive, said explicitly: deleting the expressions leaves an older graph's emissive input pointing at a
    # half-deleted node, which then fails the whole material's compile.
    dark = node(unreal.MaterialExpressionConstant3Vector, constant=unreal.LinearColor(0., 0., 0., 1.))
    for n, prop in ((colour, unreal.MaterialProperty.MP_BASE_COLOR), (normal, unreal.MaterialProperty.MP_NORMAL),
                    (occlusion, unreal.MaterialProperty.MP_AMBIENT_OCCLUSION), (specular, unreal.MaterialProperty.MP_SPECULAR),
                    (rough, unreal.MaterialProperty.MP_ROUGHNESS), (dark, unreal.MaterialProperty.MP_EMISSIVE_COLOR)):
        assert MEL.connect_material_property(n, '', prop)
    if alpha:
        opacity = custom('return lerp(A,T,HasTransparent);', {'A': (samples['Diffuse'], 'A'), 'T': (samples['Transparent'], 'A'),
                         'HasTransparent': (scalar('HasTransparent', 0.), '')}, unreal.CustomMaterialOutputType.CMOT_FLOAT1)
        MEL.connect_material_property(opacity, '', unreal.MaterialProperty.MP_OPACITY_MASK if alpha == 1 else unreal.MaterialProperty.MP_OPACITY)
    MEL.layout_material_expressions(m)
    MEL.recompile_material(m)
    return m
