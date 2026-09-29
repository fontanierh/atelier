"""Import the sword-fight effect textures and build their materials under /Game/FX.

    python3 games/yorimichi/assets/fx/gen_textures.py
    UnrealEditor-Cmd Yorimichi.uproject -run=pythonscript -script=Scripts/import_combat_fx.py -unattended -nosplash -NullRHI -stdout

- M_FX_Additive: unlit, additive, two-sided, for instanced sprites. Colour and intensity come from per-instance
  custom data ([0] intensity, [1..3] colour, set by AJapanCombatFX); the red channel of the "Sprite" texture is
  the mask. Instances MI_FX_Glow, MI_FX_Spark, MI_FX_Ring pick the texture.
- M_FX_Dust / MI_FX_Dust: the same inputs, translucent (dust darkens and covers rather than adds light).
- M_FX_Trail: unlit additive two-sided for the slash ribbon (procedural mesh): vertex colour times vertex alpha
  times the streak texture times an Intensity parameter.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import json
from pathlib import Path
import unreal as U

ROOT = yori.OUT
SRC = ROOT / 'combat_fx'
DEST = '/Game/FX'
E = U.EditorAssetLibrary; AT = U.AssetToolsHelpers.get_asset_tools(); M = U.MaterialEditingLibrary
E.make_directory(DEST)


def texture(name):
    task = U.AssetImportTask()
    for k, v in dict(filename=str(SRC / f'{name}.png'), destination_path=DEST + '/Textures', automated=True, replace_existing=True, save=True).items():
        task.set_editor_property(k, v)
    AT.import_asset_tasks([task])
    tex = E.load_asset(task.imported_object_paths[0])
    tex.set_editor_property('srgb', False)
    tex.set_editor_property('lod_group', U.TextureGroup.TEXTUREGROUP_EFFECTS)
    E.save_loaded_asset(tex)
    return tex


def material(name):
    path = f'{DEST}/{name}'
    mat = E.load_asset(path) if E.does_asset_exist(path) else AT.create_asset(name, DEST, U.Material, U.MaterialFactoryNew())
    M.delete_all_material_expressions(mat)
    mat.set_editor_property('shading_model', U.MaterialShadingModel.MSM_UNLIT)
    mat.set_editor_property('two_sided', True)
    return mat


def node(mat, cls, x, y, **props):
    n = M.create_material_expression(mat, cls, x, y)
    for k, v in props.items(): n.set_editor_property(k, v)
    return n


def sprite_material(name, blend, default_tex):
    mat = material(name)
    mat.set_editor_property('blend_mode', blend)
    mat.set_editor_property('used_with_instanced_static_meshes', True)
    tex = node(mat, U.MaterialExpressionTextureSampleParameter2D, -700, 0, parameter_name='Sprite', texture=default_tex)
    data = [node(mat, U.MaterialExpressionPerInstanceCustomData, -700, 200 + 90 * i, data_index=i, const_default_value=0.) for i in range(4)]
    rg = node(mat, U.MaterialExpressionAppendVector, -480, 300); assert M.connect_material_expressions(data[1], '', rg, 'A'); assert M.connect_material_expressions(data[2], '', rg, 'B')
    rgb = node(mat, U.MaterialExpressionAppendVector, -330, 320); assert M.connect_material_expressions(rg, '', rgb, 'A'); assert M.connect_material_expressions(data[3], '', rgb, 'B')
    mask = node(mat, U.MaterialExpressionMultiply, -330, 60); assert M.connect_material_expressions(tex, 'R', mask, 'A'); assert M.connect_material_expressions(data[0], '', mask, 'B')
    if blend == U.BlendMode.BLEND_ADDITIVE:
        out = node(mat, U.MaterialExpressionMultiply, -120, 120); assert M.connect_material_expressions(rgb, '', out, 'A'); assert M.connect_material_expressions(mask, '', out, 'B')
        assert M.connect_material_property(out, '', U.MaterialProperty.MP_EMISSIVE_COLOR)
    else:
        assert M.connect_material_property(rgb, '', U.MaterialProperty.MP_EMISSIVE_COLOR)
        sat = node(mat, U.MaterialExpressionSaturate, -120, 60); assert M.connect_material_expressions(mask, '', sat, '')
        assert M.connect_material_property(sat, '', U.MaterialProperty.MP_OPACITY)
    M.recompile_material(mat); E.save_loaded_asset(mat)
    return mat


def instance(name, parent, tex):
    path = f'{DEST}/{name}'
    mi = E.load_asset(path) if E.does_asset_exist(path) else AT.create_asset(name, DEST, U.MaterialInstanceConstant, U.MaterialInstanceConstantFactoryNew())
    M.set_material_instance_parent(mi, parent)
    M.set_material_instance_texture_parameter_value(mi, 'Sprite', tex)
    E.save_loaded_asset(mi)
    return mi


textures = {n: texture(f'T_FX_{n}') for n in ['Glow', 'Spark', 'Ring', 'Dust', 'Trail']}
additive = sprite_material('M_FX_Additive', U.BlendMode.BLEND_ADDITIVE, textures['Glow'])
dust = sprite_material('M_FX_Dust', U.BlendMode.BLEND_TRANSLUCENT, textures['Dust'])
made = [instance('MI_FX_Glow', additive, textures['Glow']), instance('MI_FX_Spark', additive, textures['Spark']),
        instance('MI_FX_Ring', additive, textures['Ring']), instance('MI_FX_Dust', dust, textures['Dust'])]

trail = material('M_FX_Trail')
trail.set_editor_property('blend_mode', U.BlendMode.BLEND_ADDITIVE)
vc = node(trail, U.MaterialExpressionVertexColor, -700, 0)
tex = node(trail, U.MaterialExpressionTextureSample, -700, 250, texture=textures['Trail'])
intensity = node(trail, U.MaterialExpressionScalarParameter, -700, 450, parameter_name='Intensity', default_value=4.)
a = node(trail, U.MaterialExpressionMultiply, -450, 150); assert M.connect_material_expressions(vc, 'A', a, 'A'); assert M.connect_material_expressions(tex, 'R', a, 'B')
b = node(trail, U.MaterialExpressionMultiply, -300, 250); assert M.connect_material_expressions(a, '', b, 'A'); assert M.connect_material_expressions(intensity, '', b, 'B')
c = node(trail, U.MaterialExpressionMultiply, -150, 50); assert M.connect_material_expressions(vc, '', c, 'A'); assert M.connect_material_expressions(b, '', c, 'B')
assert M.connect_material_property(c, '', U.MaterialProperty.MP_EMISSIVE_COLOR)
M.recompile_material(trail); E.save_loaded_asset(trail)

report = {'textures': sorted(t.get_path_name() for t in textures.values()), 'materials': [additive.get_path_name(), dust.get_path_name(), trail.get_path_name()] + [m.get_path_name() for m in made]}
(ROOT / 'combat_fx/unreal_import.json').write_text(json.dumps(report, indent=2) + '\n')
U.log('COMBAT FX IMPORT COMPLETE')
