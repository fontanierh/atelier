"""Build /Game/MegaPark/Maps/SuperUltraMegaPark from the committed native source.

Only /Game/MegaPark is written. The committed library source and build exports are
needed. The saved level owns ordinary mesh actors, Chaos collision and rails.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'world'))
import yori
import hashlib
import json
import unreal

OUT = yori.OUT / 'megapark'
SOURCE = yori.ASSETS / 'megapark'
RESTYLE = OUT / 'textures'
ROOT = '/Game/MegaPark'
# The rock and stone textures (tools/megapark_textures.py SURFACES rock, rock_smooth, stone_cut): their materials grow
# moss where they face up.
MOSSY = {'0x2c70170a001d0133', '0x2c70170a001d0135', '0x2c70170a001d014f'}
# The natural surfaces: the rock and stone, the earth and the grass. Their banks and hillsides end at the park's rim, and
# the island's ground outside meets the rim lower than their tops, so from the forest the backs of those sheets show.
# Drawn from both sides they read as the hill there instead of a window into the park (docs/MEGAPARK.md, "Seam").
NATURAL = MOSSY | {'0x2c70170a001d00aa', '0x2c70170a00040094'}
LEVEL = ROOT + '/Maps/SuperUltraMegaPark'
E = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ue(point):
    return unreal.Vector(point[0]*100., point[2]*100., point[1]*100.)


def texture(path, name, linear=False, normal=False, clamp=False, dest=None, wrap=False):
    """Import once, and again whenever the source image changes (its hash is kept in the asset's metadata)."""
    dest = dest or ROOT + '/Textures'
    asset = dest + '/' + name
    digest = sha(Path(path))
    tex = E.load_asset(asset) if E.does_asset_exist(asset) else None
    if tex is None or E.get_metadata_tag(tex, 'AtelierSourceSha256') != digest:
        task = unreal.AssetImportTask()
        task.filename = str(path); task.destination_path = dest; task.destination_name = name
        task.automated = True; task.save = True; task.replace_existing = True
        AT.import_asset_tasks([task])
        tex = E.load_asset(asset)
        assert tex, path
        E.set_metadata_tag(tex, 'AtelierSourceSha256', digest)
    assert tex, path
    tex.set_editor_property('srgb', not linear and not normal)
    tex.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_NORMALMAP if normal
                            else unreal.TextureCompressionSettings.TC_DEFAULT)
    if clamp or wrap:
        address = unreal.TextureAddress.TA_CLAMP if clamp else unreal.TextureAddress.TA_WRAP
        tex.set_editor_property('address_x', address); tex.set_editor_property('address_y', address)
    E.save_loaded_asset(tex)
    return tex


def material(alpha, defaults):
    """Translate original texture bindings into a shared, lit Unreal material graph.

    Diffuse and decals use their authored UVs; macro overlay and detail retain their source scale. The island's sun,
    sky and Lumen light the park like the terrain around it (docs/MEGAPARK.md, "Restyle"). The original baked
    irradiance (4*L*L, UV1) stays only as ambient occlusion: divided by the lightmap's sunlit level (LightmapNorm)
    and applied at LightmapOcclusion strength, so its baked sun shadows never compete with the island's.
    """
    name = ('M_RetailOpaque', 'M_RetailMasked', 'M_RetailTranslucent')[alpha]
    dest = ROOT + '/Materials'
    m = E.load_asset(dest+'/'+name) if E.does_asset_exist(dest+'/'+name) else AT.create_asset(name, dest, unreal.Material, unreal.MaterialFactoryNew())
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
    MEL.layout_material_expressions(m); MEL.recompile_material(m); E.save_loaded_asset(m)
    return m


def materials(report):
    role = {}
    for p in report['materials'].values():
        for key, tid in p.get('retail_texture_ids', {}).items(): role.setdefault(tid, set()).add(key)
    # The restyle (tools/megapark_textures.py finish): island-style images in place of some originals, and each
    # lightmap's sunlit level.
    restyle = json.loads((RESTYLE/'textures.json').read_text())
    for tid, r in restyle['textures'].items():
        assert sha(RESTYLE/r['png']) == r['sha256'], tid
    textures = {}
    for tid, t in report['textures'].items():
        assert sha(SOURCE/t['png']) == t['sha256'], tid
        roles = role.get(tid, set())
        path = RESTYLE/restyle['textures'][tid]['png'] if tid in restyle['textures'] else SOURCE/t['png']
        textures[tid] = texture(path, 'T_'+tid[2:], linear=bool(roles & {'lightmap', 'normal', 'detail', 'specular'}),
                                normal=bool(roles & {'normal', 'detail'}), clamp='lightmap' in roles)
    # Tiny fallback pixels are generated by the build, not an external dependency.
    white = texture(OUT/'white.png', 'T_DefaultWhite')
    linear = texture(OUT/'white.png', 'T_DefaultLinear', linear=True)
    black = texture(OUT/'black.png', 'T_DefaultBlack', linear=True)
    flat = texture(OUT/'normal.png', 'T_DefaultNormal', normal=True)
    defaults = {'Diffuse': white, 'Decal': white, 'Macro': white, 'Lightmap': linear,
                'Normal': flat, 'Detail': flat, 'Specular': black, 'Transparent': white}
    parents = {a: material(a, defaults) for a in range(3)}
    aliases = {'diffuse': 'Diffuse', 'decal': 'Decal', 'macrooverlay': 'Macro', 'lightmap': 'Lightmap',
               'normal': 'Normal', 'detail': 'Detail', 'specular': 'Specular', 'transparent': 'Transparent'}
    result = {}
    for key, p in report['materials'].items():
        name = 'MI_'+key[2:]; dest = ROOT+'/Materials'; path = dest+'/'+name
        mi = E.load_asset(path) if E.does_asset_exist(path) else AT.create_asset(name, dest, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        MEL.set_material_instance_parent(mi, parents[p.get('alpha_mode', 0)])
        channels = p.get('retail_texture_ids', {})
        for role, parameter in aliases.items():
            MEL.set_material_instance_texture_parameter_value(mi, parameter, textures[channels[role]] if role in channels else defaults[parameter])
        params = p.get('retail_parameters', {})
        def number(name, default):
            try: return float(params[name][0])
            except (KeyError, ValueError): return default
        scalars = {'MacroScale': number('macroOverlayUVScale', 1.), 'DetailScale': number('detailNormalUVScale', 1.),
                   'MacroOpacity': number('macroOverlayOpacity', 0.) if 'macrooverlay' in channels else 0.,
                   'UseDecal': float('decal' in channels), 'HasLightmap': float('lightmap' in channels),
                   'HasTransparent': float('transparent' in channels),
                   'LightmapNorm': restyle['lightmaps'].get(channels.get('lightmap'), 3.),
                   'Moss': float(channels.get('diffuse') in MOSSY)}
        if p.get('seam'):
            # The seam is hillside the island's ground runs up to: matte like it (the original specular maps catch the
            # sky's blue at the grazing angles the hillside is seen at from the footpath), its baked occlusion lighter.
            scalars.update(SpecularScale=0., Gloss=0., LightmapOcclusion=.25)
        for k, v in scalars.items(): MEL.set_material_instance_scalar_parameter_value(mi, k, v)
        natural = p.get('alpha_mode', 0) == 0 and channels.get('diffuse') in NATURAL
        overrides = mi.get_editor_property('base_property_overrides')
        overrides.set_editor_property('override_two_sided', natural); overrides.set_editor_property('two_sided', natural)
        mi.set_editor_property('base_property_overrides', overrides)
        MEL.update_material_instance(mi); E.save_loaded_asset(mi); result[key] = mi
    return result


def import_mesh(path, name, dest=None, seed=None, vertex_colors=False):
    """Faithful FBX import; another park may supply its own destination and seed."""
    dest = dest or ROOT+'/Meshes'; seed = seed or OUT/'fbx/SM_MP_ImportSeed.fbx'
    asset = dest+'/'+name
    if not E.does_asset_exist(asset) and path.resolve() != seed.resolve():
        import_mesh(seed, name, dest, seed, vertex_colors)
    task = unreal.AssetImportTask()
    task.filename = str(path); task.destination_path = dest; task.destination_name = name
    task.automated = True; task.replace_existing = True; task.replace_existing_settings = True; task.save = True
    ui = unreal.FbxImportUI(); ui.automated_import_should_detect_type = False
    ui.reset_to_fbx_on_material_conflict = True
    ui.import_mesh = True; ui.import_materials = False; ui.import_textures = False; ui.import_animations = False
    ui.import_as_skeletal = False; ui.mesh_type_to_import = unreal.FBXImportType.FBXIT_STATIC_MESH
    options = dict(combine_meshes=True, generate_lightmap_u_vs=False, auto_generate_collision=False,
                   convert_scene=True, convert_scene_unit=True, import_uniform_scale=1., build_nanite=False,
                   remove_degenerates=False, normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
    if vertex_colors:
        options['vertex_color_import_option'] = unreal.VertexColorImportOption.REPLACE
    for k, v in options.items(): ui.static_mesh_import_data.set_editor_property(k, v)
    existing = E.load_asset(asset) if E.does_asset_exist(asset) else None
    if existing:
        editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        settings = editor.get_lod_build_settings(existing, 0)
        settings.set_editor_property('distance_field_resolution_scale', 0.)
        editor.set_lod_build_settings(existing, 0, settings)
        # Legacy reimport otherwise conserves the seed's unused material slot.
        # This generated asset's authoritative slots always come from this FBX.
        existing.set_editor_property('static_materials', [])
        prior = existing.get_editor_property('asset_import_data')
        if isinstance(prior, unreal.FbxStaticMeshImportData):
            for k, v in options.items():
                if k != 'build_nanite': prior.set_editor_property(k, v)
    task.options = ui; AT.import_asset_tasks([task])
    mesh = E.load_asset(asset); assert mesh and task.imported_object_paths, name
    mesh.set_editor_property('allow_cpu_access', True)
    # Keep authored UVs at float precision; half UVs noticeably distort long ramps.
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    settings = editor.get_lod_build_settings(mesh, 0)
    settings.set_editor_property('use_full_precision_u_vs', True)
    settings.set_editor_property('remove_degenerates', False)
    settings.set_editor_property('distance_field_resolution_scale', 0.)
    editor.set_lod_build_settings(mesh, 0, settings)
    return mesh


def mesh_actor(entry, collision, mis, actors, editor, results, place=True):
    """Import one mesh, check it, and (when place) stand it in the standalone level."""
    assert sha(OUT/entry['fbx']) == entry['sha256'], entry['name']
    mesh = import_mesh(OUT/entry['fbx'], entry['name'])
    triangles = mesh.get_num_triangles(0)
    assert triangles == entry['triangles'], (entry['name'], triangles, entry['triangles'])
    body = mesh.get_editor_property('body_setup')
    body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    body.set_editor_property('double_sided_geometry', collision and not entry.get('one_sided', True))
    if not collision:
        found = set()
        slots = list(mesh.get_editor_property('static_materials'))
        for slot in slots:
            key = str(slot.get_editor_property('imported_material_slot_name'))
            assert key in mis, (entry['name'], key)
            slot.set_editor_property('material_interface', mis[key]); found.add(key)
        assert found == set(entry['materials']), (entry['name'], found, entry['materials'])
        mesh.set_editor_property('static_materials', slots)
    E.save_loaded_asset(mesh)
    audit = OUT/'imported-geometry'; audit.mkdir(exist_ok=True)
    assert unreal.MegaParkValidation.dump_mesh_triangles(mesh, ue(entry['native_origin']), str(audit/(entry['name']+'.bin')))
    actual = mesh.get_bounding_box()
    expected_lo = ue(entry['bounds']['minimum']) - ue(entry['native_origin'])
    expected_hi = ue(entry['bounds']['maximum']) - ue(entry['native_origin'])
    error = max((actual.min-expected_lo).length(), (actual.max-expected_hi).length())
    assert error < .05, (entry['name'], error, actual)
    results.append({'name': entry['name'], 'triangles': triangles, 'bounds_error_cm': error,
                    'uv_channels': editor.get_num_uv_channels(mesh, 0), 'collision': collision, 'placed': place})
    print('MEGAPARK mesh', entry['name'], triangles, flush=True)
    if not place:
        return
    actor = actors.spawn_actor_from_class(unreal.StaticMeshActor, ue(entry['native_origin']))
    actor.set_actor_label(entry['name']); actor.set_folder_path('OriginalCollision' if collision else 'OriginalGeometry')
    actor.set_mobility(unreal.ComponentMobility.STATIC)
    component = actor.static_mesh_component
    component.set_static_mesh(mesh)
    component.set_collision_profile_name('BlockAll' if collision else 'NoCollision')
    if collision:
        actor.set_actor_hidden_in_game(True); component.set_visibility(False)
        component.set_editor_property('cast_shadow', False)


def main():
    report = json.loads((OUT/'build.json').read_text())
    assert sha(SOURCE/'map.json') == report['source_sha256'], 'Rebuild current map source first'
    unreal.SystemLibrary.execute_console_command(None, 'Interchange.FeatureFlags.Import.FBX 0')
    unreal.load_module('StaticMeshEditor')
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    E.make_directory(ROOT+'/Maps')
    world = unreal.EditorLoadingAndSavingUtils.new_blank_map(False)
    assert world, 'Could not create park level'
    world.get_world_settings().set_editor_property('default_game_mode', unreal.MegaParkGameMode)
    mis = materials(report); results = []
    for entry in report['render']: mesh_actor(entry, False, mis, actors, editor, results)
    for entry in report['collision']: mesh_actor(entry, True, mis, actors, editor, results)
    # The seam (docs/MEGAPARK.md, "Seam") is a piece of the source's own hills: the standalone level keeps them whole, so
    # only the island places it.
    for entry in report['seam']: mesh_actor(entry, entry['name'].startswith('UC_'), mis, actors, editor, results, place=False)
    anchor = actors.spawn_actor_from_class(unreal.SuperUltraMegaPark, unreal.Vector())
    anchor.set_actor_label('OriginalGrindPaths')
    anchor.set_editor_property('source_manifest_hash', report['source_sha256'])
    rails = []
    for source in report['rails']:
        rail = unreal.MegaParkRail()
        rail.set_editor_property('source_id', source['id']); rail.set_editor_property('closed', source['closed'])
        rail.set_editor_property('points', [ue(p) for p in source['points']])
        rail.set_editor_property('original_segments', source['original_segments']); rails.append(rail)
    anchor.set_editor_property('rails', rails)
    ground = ue(report['spawn']['position']); yaw = report['spawn']['heading_degrees']
    services = actors.spawn_actor_from_class(unreal.MegaParkWorld, unreal.Vector())
    services.set_actor_label('StandalonePlayerServices'); services.set_editor_property('spawn_ground', ground)
    services.set_editor_property('spawn_yaw', yaw)
    start = actors.spawn_actor_from_class(unreal.PlayerStart, ground+unreal.Vector(0,0,80), unreal.Rotator(yaw=yaw))
    start.set_actor_label('UpperDeckStart')
    sun = actors.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(33000,-71000,25000), unreal.Rotator(pitch=-35,yaw=-40))
    sun.light_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    sun.light_component.set_editor_property('intensity', 3.)
    sun.light_component.set_editor_property('atmosphere_sun_light', True)
    actors.spawn_actor_from_class(unreal.SkyAtmosphere, unreal.Vector())
    sky = actors.spawn_actor_from_class(unreal.SkyLight, unreal.Vector())
    sky.light_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    sky.light_component.set_editor_property('real_time_capture', True)
    volume = actors.spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector())
    volume.set_editor_property('unbound', True)
    settings = volume.get_editor_property('settings')
    for k, v in dict(override_auto_exposure_method=True, auto_exposure_method=unreal.AutoExposureMethod.AEM_MANUAL,
                     override_auto_exposure_bias=True, auto_exposure_bias=0.,
                     override_auto_exposure_apply_physical_camera_exposure=True, auto_exposure_apply_physical_camera_exposure=False,
                     override_motion_blur_amount=True, motion_blur_amount=0.).items(): settings.set_editor_property(k, v)
    volume.set_editor_property('settings', settings)
    assert unreal.EditorLoadingAndSavingUtils.save_map(world, LEVEL), 'Failed to save native map'
    E.save_directory(ROOT, only_if_is_dirty=True, recursive=True)
    result = {'level': LEVEL, 'source_sha256': report['source_sha256'], 'meshes': results,
              'textures': len(report['textures']), 'materials': len(mis), 'rails': len(rails),
              'render_triangles': sum(e['triangles'] for e in results if not e['collision']),
              'collision_triangles': sum(e['triangles'] for e in results if e['collision'])}
    (OUT/'import-report.json').write_text(json.dumps(result, indent=2)+'\n')
    print('MEGAPARK IMPORT COMPLETE', result['render_triangles'], result['collision_triangles'], flush=True)


if __name__ == '__main__': main()
