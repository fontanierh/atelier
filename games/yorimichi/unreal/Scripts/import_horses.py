"""Import the horse library into /Game/Horses: the six breeds with their clips, the seven tack sets, the coat masks
and coat variants, and the master materials their glTF materials are restyled onto.

    UnrealEditor-Cmd Yorimichi.uproject -run=pythonscript -script=Scripts/import_horses.py -unattended -nosplash -NullRHI -stdout

Reads assets/horses/manifest.json (breeds, tack sets, clips, coat masks, palettes), coats/variants/manifest.json and
build/yorimichi/horses/manifest.json (world.horses: each breed's rider contacts). Each breed's horse.glb and tack GLBs
are imported from upright copies (horse_data.upright_glb) under build/yorimichi/horses/glb; Interchange imports each
material's base-colour texture from the GLB itself. Writes Content/Data/horses/roster.json, whose shape is the contract
in horse_data.py, and build/yorimichi/horses/unreal_import.json: the same roster plus `materials`, each mesh's
material instances and the base-colour textures they keep, so the build's check covers every package a mesh loads.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import json, sys, time
from pathlib import Path
import unreal as U
sys.path.insert(0, str(Path(__file__).resolve().parent))
import animation_compression
import horse_data

ASSETS = yori.ASSETS / 'horses'
OUT = yori.OUT / 'horses'
LIBRARY = json.loads((ASSETS / 'manifest.json').read_text())
VARIANTS = json.loads((ASSETS / 'coats' / 'variants' / 'manifest.json').read_text())['variants']
BUILT = json.loads((OUT / 'manifest.json').read_text())
DEST = '/Game/Horses'
CONTENT = Path(__file__).resolve().parents[1] / 'Content'
DATA = CONTENT / 'Data' / 'horses'
E = U.EditorAssetLibrary; AT = U.AssetToolsHelpers.get_asset_tools(); M = U.MaterialEditingLibrary
REGISTRY = U.AssetRegistryHelpers.get_asset_registry()


def upright(src, dst):
    """An upright copy of a library GLB for Interchange (horse_data.upright_glb)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(horse_data.upright_glb(src.read_bytes()))
    return dst


def pipelines(skeleton=None, static=False, animations=False):
    generic = U.InterchangeGenericAssetsPipeline()
    mesh = generic.get_editor_property('mesh_pipeline')
    mesh.set_editor_property('import_static_meshes', static)
    mesh.set_editor_property('import_skeletal_meshes', not static)
    mesh.set_editor_property('combine_static_meshes_behavior', U.InterchangeCombineStaticMeshesBehavior.ALL)
    mesh.set_editor_property('combine_skeletal_meshes_behavior', U.InterchangeCombineSkeletalMeshesBehavior.BY_SKELETON)
    mesh.set_editor_property('create_physics_asset', False)
    mesh.set_editor_property('import_morph_targets', False)
    textures = generic.get_editor_property('material_pipeline').get_editor_property('texture_pipeline')
    textures.set_editor_property('allow_non_power_of_two', True)
    animation = generic.get_editor_property('animation_pipeline')
    animation.set_editor_property('import_animations', animations)
    animation.set_editor_property('use30_hz_to_bake_bone_animation', True)
    if skeleton is not None:
        generic.get_editor_property('common_skeletal_meshes_and_animations_properties').set_editor_property('skeleton', skeleton)
    stack = U.InterchangePipelineStackOverride()
    stack.add_pipeline(generic)
    stack.add_pipeline(U.InterchangeGLTFPipeline())
    return stack


def texture_pipelines():
    generic = U.InterchangeGenericAssetsPipeline()
    textures = generic.get_editor_property('material_pipeline').get_editor_property('texture_pipeline')
    textures.set_editor_property('allow_non_power_of_two', True)
    stack = U.InterchangePipelineStackOverride()
    stack.add_pipeline(generic)
    return stack


def _get_or_create_material(name):
    path = f'{DEST}/{name}'
    mat = E.load_asset(path) if E.does_asset_exist(path) else AT.create_asset(name, DEST, U.Material, U.MaterialFactoryNew())
    M.delete_all_material_expressions(mat)
    return mat


WHITE_SQUARE = '/Engine/EngineResources/WhiteSquareTexture'


def _default_tex(preferred_path=WHITE_SQUARE):
    """A sampler parameter's default: preferred_path, else the engine's white square, else the imported Solid mask
    (each tried once)."""
    for path in dict.fromkeys((preferred_path, WHITE_SQUARE, f'{DEST}/Coats/Masks/T_Coat_Solid_Mask')):
        if tex := E.load_asset(path):
            return tex
    raise AssertionError(f'Could not load default Texture2D for {preferred_path}')


def _vec_rgb(mat, expr, param_name, default_col, x, y):
    vec = expr(U.MaterialExpressionVectorParameter, x, y)
    vec.set_editor_property('parameter_name', param_name)
    vec.set_editor_property('default_value', default_col)
    rgb = expr(U.MaterialExpressionComponentMask, x + 180, y)
    for ch in 'rgb':
        rgb.set_editor_property(ch, True)
    assert M.connect_material_expressions(vec, '', rgb, '')
    return rgb


def make_coat_master(name):
    """Master material M_HorseCoat: BaseColorTexture * CoatTint blended with MaskTexture * MaskStrength -> MaskColor,
    plus the Yorimichi 30% emissive albedo fill."""
    mat = _get_or_create_material(name)
    mat.set_editor_property('blend_mode', U.BlendMode.BLEND_OPAQUE)
    mat.set_editor_property('two_sided', True)
    mat.set_editor_property('used_with_skeletal_mesh', True)
    expr = lambda cls, x, y: M.create_material_expression(mat, cls, x, y)

    base = expr(U.MaterialExpressionTextureSampleParameter2D, -1000, -100)
    base.set_editor_property('parameter_name', 'BaseColorTexture')
    base.set_editor_property('texture', _default_tex(WHITE_SQUARE))

    tint_rgb = _vec_rgb(mat, expr, 'CoatTint', U.LinearColor(1., 1., 1., 1.), -1000, 150)

    tinted = expr(U.MaterialExpressionMultiply, -700, 0)
    assert M.connect_material_expressions(base, 'RGB', tinted, 'A')
    assert M.connect_material_expressions(tint_rgb, '', tinted, 'B')

    mask_tex = expr(U.MaterialExpressionTextureSampleParameter2D, -1000, 400)
    mask_tex.set_editor_property('parameter_name', 'MaskTexture')
    mask_tex.set_editor_property('texture', _default_tex(f'{DEST}/Coats/Masks/T_Coat_Solid_Mask'))

    mask_str = expr(U.MaterialExpressionScalarParameter, -1000, 650)
    mask_str.set_editor_property('parameter_name', 'MaskStrength')
    mask_str.set_editor_property('default_value', 0.)

    mask_alpha = expr(U.MaterialExpressionMultiply, -700, 500)
    assert M.connect_material_expressions(mask_tex, 'R', mask_alpha, 'A')
    assert M.connect_material_expressions(mask_str, '', mask_alpha, 'B')

    mask_col_rgb = _vec_rgb(mat, expr, 'MaskColor', U.LinearColor(.95, .94, .92, 1.), -780, 280)

    albedo = expr(U.MaterialExpressionLinearInterpolate, -420, 150)
    assert M.connect_material_expressions(tinted, '', albedo, 'A')
    assert M.connect_material_expressions(mask_col_rgb, '', albedo, 'B')
    assert M.connect_material_expressions(mask_alpha, '', albedo, 'Alpha')
    assert M.connect_material_property(albedo, '', U.MaterialProperty.MP_BASE_COLOR)

    fill = expr(U.MaterialExpressionMultiply, -200, 250)
    fill.set_editor_property('const_b', .30)
    assert M.connect_material_expressions(albedo, '', fill, 'A')
    assert M.connect_material_property(fill, '', U.MaterialProperty.MP_EMISSIVE_COLOR)

    for pname, val, prop, y in [
        ('Roughness', .62, U.MaterialProperty.MP_ROUGHNESS, 550),
        ('Metallic', 0., U.MaterialProperty.MP_METALLIC, 650),
        ('Specular', .32, U.MaterialProperty.MP_SPECULAR, 750),
    ]:
        node = expr(U.MaterialExpressionScalarParameter, -300, y)
        node.set_editor_property('parameter_name', pname)
        node.set_editor_property('default_value', val)
        assert M.connect_material_property(node, '', prop)

    M.recompile_material(mat)
    E.save_loaded_asset(mat, False)
    return mat


def make_hair_master(name):
    """Master material M_HorseHair: masked two-sided mane/tail shader supporting 18 HAIR_COLORS (PrimaryColor,
    SecondaryColor) and 4 HAIR_PATTERNS (PatternMix)."""
    mat = _get_or_create_material(name)
    mat.set_editor_property('blend_mode', U.BlendMode.BLEND_OPAQUE)
    mat.set_editor_property('opacity_mask_clip_value', .35)
    mat.set_editor_property('two_sided', True)
    mat.set_editor_property('used_with_skeletal_mesh', True)
    expr = lambda cls, x, y: M.create_material_expression(mat, cls, x, y)

    base = expr(U.MaterialExpressionTextureSampleParameter2D, -1000, 0)
    base.set_editor_property('parameter_name', 'BaseColorTexture')
    base.set_editor_property('texture', _default_tex(WHITE_SQUARE))

    prim_rgb = _vec_rgb(mat, expr, 'PrimaryColor', U.LinearColor(.22, .11, .06, 1.), -1000, 260)
    sec_rgb = _vec_rgb(mat, expr, 'SecondaryColor', U.LinearColor(.36, .20, .12, 1.), -1000, 480)

    pmix = expr(U.MaterialExpressionScalarParameter, -1000, 700)
    pmix.set_editor_property('parameter_name', 'PatternMix')
    pmix.set_editor_property('default_value', 0.)

    blend_alpha = expr(U.MaterialExpressionMultiply, -720, 580)
    assert M.connect_material_expressions(base, 'R', blend_alpha, 'A')
    assert M.connect_material_expressions(pmix, '', blend_alpha, 'B')

    hair_col = expr(U.MaterialExpressionLinearInterpolate, -500, 320)
    assert M.connect_material_expressions(prim_rgb, '', hair_col, 'A')
    assert M.connect_material_expressions(sec_rgb, '', hair_col, 'B')
    assert M.connect_material_expressions(blend_alpha, '', hair_col, 'Alpha')

    detail_scale = expr(U.MaterialExpressionMultiply, -720, 80)
    detail_scale.set_editor_property('const_b', .75)
    assert M.connect_material_expressions(base, 'RGB', detail_scale, 'A')
    detail_bias = expr(U.MaterialExpressionAdd, -520, 80)
    detail_bias.set_editor_property('const_b', .45)
    assert M.connect_material_expressions(detail_scale, '', detail_bias, 'A')

    albedo = expr(U.MaterialExpressionMultiply, -300, 180)
    assert M.connect_material_expressions(hair_col, '', albedo, 'A')
    assert M.connect_material_expressions(detail_bias, '', albedo, 'B')
    assert M.connect_material_property(albedo, '', U.MaterialProperty.MP_BASE_COLOR)

    fill = expr(U.MaterialExpressionMultiply, -140, 280)
    fill.set_editor_property('const_b', .30)
    assert M.connect_material_expressions(albedo, '', fill, 'A')
    assert M.connect_material_property(fill, '', U.MaterialProperty.MP_EMISSIVE_COLOR)
    mat.set_editor_property('blend_mode', U.BlendMode.BLEND_MASKED)
    assert M.connect_material_property(base, 'A', U.MaterialProperty.MP_OPACITY_MASK)

    for val, prop, y in [(.68, U.MaterialProperty.MP_ROUGHNESS, 520), (0., U.MaterialProperty.MP_METALLIC, 600), (.28, U.MaterialProperty.MP_SPECULAR, 680)]:
        node = expr(U.MaterialExpressionConstant, -200, y)
        node.set_editor_property('r', val)
        assert M.connect_material_property(node, '', prop)

    M.recompile_material(mat)
    E.save_loaded_asset(mat, False)
    return mat


def make_tack_master(name, masked):
    """Master material M_HorseTack / M_HorseTackMasked for saddles, reins, hooves, feet and eyes."""
    mat = _get_or_create_material(name)
    mat.set_editor_property('blend_mode', U.BlendMode.BLEND_OPAQUE)
    mat.set_editor_property('opacity_mask_clip_value', .5)
    mat.set_editor_property('two_sided', True)
    mat.set_editor_property('used_with_skeletal_mesh', True)
    expr = lambda cls, x, y: M.create_material_expression(mat, cls, x, y)

    base = expr(U.MaterialExpressionTextureSampleParameter2D, -900, 0)
    base.set_editor_property('parameter_name', 'BaseColorTexture')
    base.set_editor_property('texture', _default_tex(WHITE_SQUARE))
    assert M.connect_material_property(base, 'RGB', U.MaterialProperty.MP_BASE_COLOR)

    fill = expr(U.MaterialExpressionMultiply, -500, 200)
    fill.set_editor_property('const_b', .30)
    assert M.connect_material_expressions(base, 'RGB', fill, 'A')
    assert M.connect_material_property(fill, '', U.MaterialProperty.MP_EMISSIVE_COLOR)

    for value, prop, y in [(.58, U.MaterialProperty.MP_ROUGHNESS, 620), (0., U.MaterialProperty.MP_METALLIC, 700), (.35, U.MaterialProperty.MP_SPECULAR, 780)]:
        node = expr(U.MaterialExpressionConstant, -300, y)
        node.set_editor_property('r', value)
        assert M.connect_material_property(node, '', prop)

    if masked:
        mat.set_editor_property('blend_mode', U.BlendMode.BLEND_MASKED)
        cutoff = expr(U.MaterialExpressionScalarParameter, -900, 900)
        cutoff.set_editor_property('parameter_name', 'AlphaCutoff')
        cutoff.set_editor_property('default_value', .5)
        cut = expr(U.MaterialExpressionSubtract, -600, 850)
        assert M.connect_material_expressions(base, 'A', cut, 'A')
        assert M.connect_material_expressions(cutoff, '', cut, 'B')
        mask = expr(U.MaterialExpressionAdd, -400, 850)
        mask.set_editor_property('const_b', .5)
        assert M.connect_material_expressions(cut, '', mask, 'A')
        assert M.connect_material_property(mask, '', U.MaterialProperty.MP_OPACITY_MASK)

    M.recompile_material(mat)
    E.save_loaded_asset(mat, False)
    return mat


def assets_in(folder, recursive=True):
    found = {}
    for data in REGISTRY.get_assets_by_path(folder, recursive=recursive):
        found.setdefault(str(data.asset_class_path.asset_name), []).append(str(data.package_name))
    return found


def rename(path, name):
    folder = path.rsplit('/', 1)[0]
    target = f'{folder}/{name}'
    if path != target:
        assert E.rename_asset(path, target), ('rename failed', path, target)
    return target


def import_glb(path, folder, options):
    task = U.AssetImportTask()
    for key, value in dict(filename=str(path), destination_path=folder, automated=True, replace_existing=True, save=True).items():
        task.set_editor_property(key, value)
    task.set_editor_property('options', options)
    AT.import_asset_tasks([task])
    return assets_in(folder, recursive=True)


def import_textures_batch(file_dest_pairs):
    """Batch-import (filepath, dest_folder, dest_name) texture files: the coat masks and variants."""
    opts = texture_pipelines()
    tasks = []
    for fpath, folder, dname in file_dest_pairs:
        E.make_directory(folder)
        t = U.AssetImportTask()
        for k, v in dict(filename=str(fpath), destination_path=folder, destination_name=dname,
                         automated=True, replace_existing=True, save=True, options=opts).items():
            t.set_editor_property(k, v)
        tasks.append(t)
    AT.import_asset_tasks(tasks)
    out = {}
    for (_, folder, dname), t in zip(file_dest_pairs, tasks):
        paths = list(t.get_editor_property('imported_object_paths'))
        out[dname] = paths[0] if paths else f'{folder}/{dname}'
    return out


def restyle_instance(material, masters, hair_colour):
    """Reparent an Interchange glTF MaterialInstanceConstant to M_HorseCoat, M_HorseHair or M_HorseTack(Masked),
    keeping the base-colour texture Interchange imported from the GLB. Mane and Tail take the breed's hair colour."""
    mname = material.get_name()
    parent = material.get_editor_property('parent')
    parent_name = parent.get_name() if parent else ''
    masked = 'Opaque' not in parent_name and 'M_HorseTack' != parent_name
    keep_base = M.get_material_instance_texture_parameter_value(material, 'BaseColorTexture')
    assert keep_base and keep_base.get_name() not in ('WhiteSquareTexture', 'Black', 'T_Coat_Solid_Mask'), \
        (mname, 'no base-colour texture imported from its GLB')
    keep_cutoff = M.get_material_instance_scalar_parameter_value(material, 'AlphaCutoff')

    M.clear_all_material_instance_parameters(material)
    if mname == 'Coat':
        M.set_material_instance_parent(material, masters['coat'])
    elif mname in ('Mane', 'Tail'):
        M.set_material_instance_parent(material, masters['hair'])
        c = hair_colour
        M.set_material_instance_vector_parameter_value(material, 'PrimaryColor', U.LinearColor(c[0], c[1], c[2], 1.))
        M.set_material_instance_vector_parameter_value(material, 'SecondaryColor', U.LinearColor(min(1., c[0] * 1.35), min(1., c[1] * 1.35), min(1., c[2] * 1.35), 1.))
    else:
        M.set_material_instance_parent(material, masters['tack_masked'] if masked else masters['tack'])
        if masked:
            M.set_material_instance_scalar_parameter_value(material, 'AlphaCutoff', keep_cutoff or .5)
    M.set_material_instance_texture_parameter_value(material, 'BaseColorTexture', keep_base)
    M.update_material_instance(material)
    E.save_loaded_asset(material, False)
    return keep_base.get_path_name()


def match_clip(imported_paths, clip_name):
    for p in imported_paths:
        stem = Path(p).name
        if stem in (clip_name, f'horse{clip_name}', f'horse_{clip_name}'):
            return p
    matches = [p for p in imported_paths if Path(p).name.endswith(clip_name)]
    return matches[0] if len(matches) == 1 else None


def import_breed(slug, breed, masters):
    """The breed's mesh, skeleton, clips and tack, as its roster entry (mesh, skeleton, clips, saddles, reins), and
    each of its meshes' material instances with the texture each keeps."""
    started = time.time()
    bname = breed['name']  # PascalCase: Arabian, Thoroughbred, Friesian, Andalusian, Clydesdale, Quarter
    folder = f'{DEST}/{bname}'
    E.make_directory(folder)

    # The upright horse.glb: SkeletalMesh, Skeleton, AnimSequences and its materials' textures
    norm_glb = upright(ASSETS / slug / 'horse.glb', OUT / 'glb' / f'SK_Horse_{bname}.glb')
    found = import_glb(norm_glb, folder, pipelines(skeleton=None, static=False, animations=True))
    meshes = found.get('SkeletalMesh', [])
    skeletons = found.get('Skeleton', [])
    assert len(meshes) == 1 and len(skeletons) == 1, (bname, 'expected 1 mesh and 1 skeleton', found)
    skeleton = E.load_asset(rename(skeletons[0], f'SKEL_Horse_{bname}'))
    mesh_path = rename(meshes[0], f'SK_Horse_{bname}')
    mesh = E.load_asset(mesh_path)
    assert mesh.skeleton == skeleton, (bname, mesh.skeleton, skeleton)

    imported_anims = found.get('AnimSequence', [])
    clips = {}
    for clip_name, clip in LIBRARY['clips'].items():
        apath = match_clip(imported_anims, clip_name)
        assert apath, (bname, 'missing horse clip', clip_name, imported_anims)
        seq = E.load_asset(rename(apath, f'A_Horse_{bname}_{clip_name}'))
        assert seq.get_editor_property('skeleton') == skeleton
        seq.set_editor_property('enable_root_motion', False)
        animation_compression.apply_to(seq)
        E.save_loaded_asset(seq, False)
        clips[clip_name] = {
            'path': seq.get_path_name(),
            'length': round(seq.get_editor_property('sequence_length'), 4),
            'loop': clip['loop'],
        }

    materials = {mesh.get_path_name(): {mat_path: restyle_instance(E.load_asset(mat_path), masters, breed['hair_colour'])
                                        for mat_path in found.get('MaterialInstanceConstant', [])}}

    E.save_loaded_asset(skeleton, False)
    E.save_loaded_asset(mesh, False)

    # Every tack set's saddle and reins onto SKEL_Horse_<Breed>
    tack_opts = pipelines(skeleton=skeleton, static=False, animations=False)
    tack_tasks = []
    tack_meta = []
    for sid in LIBRARY['tack_sets']:
        for part in ('Saddle', 'Reins'):
            sub = f'{folder}/Tack/{part}_{sid}'
            E.make_directory(sub)
            glb_path = upright(
                ASSETS / slug / 'tack' / f'{part}_{sid}.glb',
                OUT / 'glb' / f'SK_Horse_{bname}_{part}_{sid}.glb',
            )
            t = U.AssetImportTask()
            for k, v in dict(filename=str(glb_path), destination_path=sub, automated=True,
                             replace_existing=True, save=True, options=tack_opts).items():
                t.set_editor_property(k, v)
            tack_tasks.append(t)
            tack_meta.append((part, sid, sub))

    AT.import_asset_tasks(tack_tasks)
    saddles = {}
    reins = {}
    for (part, sid, sub) in tack_meta:
        sub_found = assets_in(sub, recursive=True)
        smeshes = sub_found.get('SkeletalMesh', [])
        assert len(smeshes) == 1, (bname, part, sid, 'expected 1 tack skeletal mesh', sub_found)
        tmesh_path = rename(smeshes[0], f'SK_Horse_{bname}_{part}_{sid}')
        tmesh = E.load_asset(tmesh_path)
        materials[tmesh.get_path_name()] = {mat_path: restyle_instance(E.load_asset(mat_path), masters, breed['hair_colour'])
                                            for mat_path in sub_found.get('MaterialInstanceConstant', [])}
        E.save_loaded_asset(tmesh, False)
        if part == 'Saddle':
            saddles[sid] = tmesh.get_path_name()
        else:
            reins[sid] = tmesh.get_path_name()

    U.log(f'Horse breed {bname}: {len(clips)} clips, {len(saddles)} saddles, {len(reins)} reins in {time.time() - started:.1f}s')
    assert all(materials.values()), (bname, 'a mesh imported without material instances', materials)
    return {'mesh': mesh.get_path_name(), 'skeleton': skeleton.get_path_name(), 'clips': clips, 'saddles': saddles, 'reins': reins}, materials


if E.does_directory_exist(DEST):
    E.delete_directory(DEST)
E.make_directory(DEST)

# The coat masks first, so T_Coat_Solid_Mask is there as the coat master's default mask
imported_masks = import_textures_batch([(ASSETS / 'coats' / f'T_Coat_{mask}_Mask.png', f'{DEST}/Coats/Masks', f'T_Coat_{mask}_Mask')
                                        for mask in LIBRARY['coat_masks']])
coat_masks = {mask: imported_masks[f'T_Coat_{mask}_Mask'] for mask in LIBRARY['coat_masks']}

masters = {
    'coat': make_coat_master('M_HorseCoat'),
    'hair': make_hair_master('M_HorseHair'),
    'tack': make_tack_master('M_HorseTack', False),
    'tack_masked': make_tack_master('M_HorseTackMasked', True),
}

name = lambda variant: 'T_CoatVariant_' + variant['id'].replace('-', '_')
imported_variants = import_textures_batch([(ASSETS / 'coats' / 'variants' / v['file'], f'{DEST}/Coats/Variants', name(v)) for v in VARIANTS])
coat_variants = [{**v, 'texture': imported_variants[name(v)]} for v in VARIANTS]

imported = {slug: import_breed(slug, breed, masters) for slug, breed in LIBRARY['breeds'].items()}
breeds = {slug: entry for slug, (entry, _) in imported.items()}
materials = {mesh: used for _, breed_materials in imported.values() for mesh, used in breed_materials.items()}
roster = horse_data.roster(LIBRARY, BUILT, {k: v.get_path_name() for k, v in masters.items()}, coat_masks, coat_variants, breeds)
problems = horse_data.roster_problems(roster)
assert not problems, problems
DATA.mkdir(parents=True, exist_ok=True)
(DATA / 'roster.json').write_text(json.dumps(roster, indent=1) + '\n')
(OUT / 'unreal_import.json').write_text(json.dumps({**roster, 'materials': materials}, indent=1) + '\n')
U.log('HORSES IMPORT COMPLETE: %d breeds, %d tack sets, %d coat variants' % (
    len(breeds), len(LIBRARY['tack_sets']), len(coat_variants)))
