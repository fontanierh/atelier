"""Editor-side setup (headless), run after the C++ module is built:

    "$UE/Engine/Binaries/Mac/UnrealEditor-Cmd" "$PROJ/Yorimichi.uproject" -run=pythonscript -script="$PROJ/Scripts/setup_project.py" -unattended -nop4 -nosplash

- replaces legacy /Game/Japan assets, preserving independent material and foliage owners
- imports props, terrain, sea and the traveler, and binds the shared materials by stable path
- builds the level /Game/Japan/Maps/Slice: terrain, sun, sky light, fog, post-process, player start
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import os, glob, sys, unreal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from asset_catalog import FOLIAGE, independently_owned, material_bindings
from material_assets import opt, instance
from forest_ground import material as forest_ground_material
ROOT = str(yori.OUT)
OUT = ROOT; TEX = os.path.join(ROOT, "textures")
REPORT = None
def LOG(msg):
    global REPORT
    if REPORT is None:
        REPORT = open(os.path.join(OUT, "setup_report.txt"), "w")
    unreal.log(msg); REPORT.write(str(msg) + "\n"); REPORT.flush()
AT = unreal.AssetToolsHelpers.get_asset_tools()
MEL = unreal.MaterialEditingLibrary
EAL = unreal.EditorAssetLibrary


def import_fbx(path, dest, name, skeletal=False, materials=False, animations=False):
    task = unreal.AssetImportTask()
    task.filename = path; task.destination_path = dest; task.destination_name = name
    task.automated = True; task.replace_existing = True; task.save = True
    ui = unreal.FbxImportUI()
    ui.import_mesh = True; ui.import_materials = materials; ui.import_textures = materials
    ui.import_animations = animations; ui.import_as_skeletal = skeletal
    ui.mesh_type_to_import = unreal.FBXImportType.FBXIT_SKELETAL_MESH if skeletal else unreal.FBXImportType.FBXIT_STATIC_MESH
    if skeletal:
        d = ui.skeletal_mesh_import_data
        opt(d, "normal_import_method", unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
        opt(d, "convert_scene", True); opt(d, "import_meshes_in_bone_hierarchy", True); opt(d, "use_t0_as_ref_pose", False)
        opt(d, "vertex_color_import_option", unreal.VertexColorImportOption.REPLACE)
        if animations:
            a = ui.anim_sequence_import_data
            opt(a, "import_bone_tracks", True); opt(a, "animation_length", unreal.FBXAnimationLengthImportType.FBXALIT_EXPORTED_TIME)
    else:
        d = ui.static_mesh_import_data
        opt(d, "combine_meshes", True); opt(d, "generate_lightmap_u_vs", False); opt(d, "auto_generate_collision", False)
        opt(d, "normal_import_method", unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
        opt(d, "convert_scene", True); opt(d, "build_nanite", False)
        opt(d, "vertex_color_import_option", unreal.VertexColorImportOption.REPLACE)
    task.options = ui
    AT.import_asset_tasks([task])
    paths = list(task.imported_object_paths)
    LOG(f"imported {os.path.basename(path)} -> {paths}")
    return paths


def purge():
    """Replace only the legacy world's packages. Independent owners keep their package identity.

    Animations go first: deleting their skeleton first makes sequence deletion fail.
    """
    reg = unreal.AssetRegistryHelpers.get_asset_registry()
    assets = [a for a in reg.get_assets_by_path("/Game/Japan", recursive=True)]
    order = {"AnimSequence": 0, "SkeletalMesh": 1, "PhysicsAsset": 2, "Skeleton": 3}
    assets.sort(key=lambda a: order.get(str(a.asset_class_path.asset_name), 5))
    for a in assets:
        if independently_owned(str(a.package_name)):
            continue
        try:
            EAL.delete_asset(str(a.package_name))
        except Exception as e:
            LOG(f"  purge failed for {a.package_name}: {e}")
    LOG("purged legacy world packages; preserved independent material and foliage owners")




def soft_colour_grade(settings):
    """Soft painted light, retaining broad value gradients and warm/cool depth."""
    values = {
        'color_contrast': unreal.Vector4(.98, .98, .98, 1),
        'color_gain': unreal.Vector4(1.02, 1.0, .98, 1),
        'color_gamma': unreal.Vector4(1.025, 1.025, 1.025, 1),
        'color_gain_shadows': unreal.Vector4(.94, .98, 1.055, 1),
        'color_gain_highlights': unreal.Vector4(1.025, 1.005, .97, 1),
        'bloom_intensity': .18,
        'vignette_intensity': .16,
        'ambient_occlusion_intensity': .45,
    }
    for name, value in values.items():
        settings.set_editor_property('override_' + name, True)
        settings.set_editor_property(name, value)


def assign(mesh_path, MI):
    m = EAL.load_asset(mesh_path)
    if not m: return
    mats = list(m.get_editor_property("static_materials"))
    changed = False
    for i, sm in enumerate(mats):
        slot = str(sm.get_editor_property("imported_material_slot_name")) or str(sm.get_editor_property("material_slot_name"))
        key = slot.split(".")[0]
        if key in MI:
            m.set_material(i, MI[key]); changed = True
        else:
            LOG(f"  no material for slot '{slot}' on {mesh_path}")
    if changed: EAL.save_loaded_asset(m)


# ------------------------------------------------------------------ level
def build_level(terrain_mesh, W, MI):
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    map_path = "/Game/Japan/Maps/Slice"
    if True:
        les.new_level(map_path)
        t = eas.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 0))
        t.set_actor_label("Terrain"); t.static_mesh_component.set_static_mesh(terrain_mesh); t.set_mobility(unreal.ComponentMobility.STATIC)
        sun = eas.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 3000))
        # unreal.Rotator(roll, pitch, yaw): the sun sits 48 deg up and shines toward yaw -30 (east-north-east), so it stands in
        # the west-south-west, over the sea and behind the traveler: the road is lit along its length, tree shadows fall
        # forward. The settings menu's Light section (JapanPreferences.cpp) sets the player's sun over this one.
        sun.set_actor_rotation(unreal.Rotator(roll=0.0, pitch=-48.0, yaw=-30.0), False)
        L = sun.light_component
        L.set_editor_property("forward_shading_priority", 1)
        L.set_mobility(unreal.ComponentMobility.MOVABLE); L.set_intensity(7.0)
        L.set_light_color(unreal.LinearColor(1.0, 0.90, 0.76, 1.0))
        opt(L, "light_source_angle", 5.0); opt(L, "dynamic_shadow_distance_movable_light", 30000.0); opt(L, "dynamic_shadow_cascades", 4)
        opt(L, "cascade_distribution_exponent", 2.5); opt(L, "atmosphere_sun_light", False); opt(L, "shadow_bias", 0.6)
        sky = eas.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 3000))
        S = sky.light_component; S.set_mobility(unreal.ComponentMobility.MOVABLE)
        S.set_editor_property("real_time_capture", False); S.set_intensity(3.8)     # captured once at load: the painted dome lights the shadows
        S.set_light_color(unreal.LinearColor(0.95, 0.96, 1.0, 1.0))
        opt(S, "lower_hemisphere_color", unreal.LinearColor(0.30, 0.36, 0.46, 1.0))
        fog = eas.spawn_actor_from_class(unreal.ExponentialHeightFog, unreal.Vector(0, 0, 0))
        F = fog.component
        F.set_editor_property("fog_density", 0.0); F.set_editor_property("fog_height_falloff", 6.0)   # height fog off: any layer thick enough to see fogs the sky dome; haze lives in the materials   # haze hugs the valleys: thick along the road, thin from above
        opt(F, "second_fog_data", unreal.ExponentialHeightFogData(fog_density=0.0, fog_height_falloff=1.0, fog_height_offset=0.0))   # no tall layer: it fogs the sky dome
        F.set_editor_property("fog_inscattering_luminance", unreal.LinearColor(0.72, 0.80, 0.90, 1.0)) if hasattr(F, "fog_inscattering_luminance") else None
        opt(F, "fog_inscattering_luminance", unreal.LinearColor(0.62, 0.70, 0.83, 1.0)); opt(F, "start_distance", 3000.0); opt(F, "fog_cutoff_distance", 1200000.0)
        opt(F, "fog_max_opacity", 0.55)
        LOG(f"fog readback: cutoff={F.get_editor_property('fog_cutoff_distance')} density={F.get_editor_property('fog_density')} start={F.get_editor_property('start_distance')}")
        ppv = eas.spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector(0, 0, 0))
        ppv.set_editor_property("unbound", True)
        s = ppv.settings
        def ov(name, value):
            s.set_editor_property("override_" + name, True); s.set_editor_property(name, value)
        # fixed exposure in EV100: the sun is 7 lux, lit ground sits near EV 3; 1.2 keeps it bright with the painted sky brighter still
        ov("auto_exposure_method", unreal.AutoExposureMethod.AEM_HISTOGRAM); ov("auto_exposure_bias", 1.24)
        ov("auto_exposure_min_brightness", 1.2); ov("auto_exposure_max_brightness", 1.2)
        ov("color_saturation", unreal.Vector4(1.0, 1.0, 1.0, 1.0))
        ov("indirect_lighting_intensity", 3.0); ov("lumen_scene_lighting_quality", 1.0); ov("lumen_final_gather_quality", 1.0)
        ov("dynamic_global_illumination_method", unreal.DynamicGlobalIlluminationMethod.LUMEN)
        ov("film_toe", 0.3); ov("film_shoulder", 0.28); ov("film_slope", 0.7)
        ov("ambient_occlusion_radius", 120.0)
        ov("screen_space_reflection_intensity", 0.0); ov("motion_blur_amount", 0.0)
        soft_colour_grade(s)
        s.set_editor_property("weighted_blendables", unreal.WeightedBlendables(array=[unreal.WeightedBlendable(weight=1.0, object=MI["_painterly"])]))
        ppv.set_editor_property("settings", s)
        ps = W["player_start"]
        p = eas.spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(ps[0] * 100, -ps[1] * 100, ps[2] * 100 + 100))
        p.set_actor_rotation(unreal.Rotator(roll=0.0, pitch=0.0, yaw=-ps[3]), False)
    world = unreal.EditorLevelLibrary.get_editor_world()
    ok = unreal.EditorLoadingAndSavingUtils.save_map(world, map_path)
    if not ok:
        raise RuntimeError(f"Failed to save {map_path}")
    LOG(f"level saved: {map_path} ok={ok}")


def main():
    """@cc [owner:fontanierh,label:correctness] world-terrain-single-source-pass
    With a city manifest, the city importer MUST perform the sole final-source Terrain import,
    including its fresh slots, unit conversion, material bindings, complex collision and save.
    The level MUST reference that final mesh; without a city, the legacy setup path MUST remain.
    """
    if os.environ.get('JAPAN_ONLY'):
        raise RuntimeError('JAPAN_ONLY is retired; select unreal.materials or unreal.foliage.<asset>')
    import json
    W = json.load(open(os.path.join(OUT, "world.json")))
    purge()
    MI = {name: EAL.load_asset(path) for name, path in material_bindings().items()}
    if not all(MI.values()):
        raise RuntimeError('Build unreal.materials before importing the world')
    MI['FarForest'] = instance('MI_FarForest', forest_ground_material())
    from forest_ground import coast_instance
    MI['Coast'] = coast_instance(MI['FarForest'].get_editor_property('parent'))
    for path in sorted(glob.glob(os.path.join(OUT, "assets", "*.fbx"))):
        name = os.path.splitext(os.path.basename(path))[0]
        if name in FOLIAGE:
            continue  # stale pre-split exports may still exist; their independent owner imports them
        import_fbx(path, "/Game/Japan/Assets", name)
        assign(f"/Game/Japan/Assets/{name}", MI)
    # props need collision too (trees, poles, rails): complex-as-simple is fine for a demo; the houses have their own import
    for name in ("Pole", "Pole_Lamp", "Guardrail", "Lantern", "Torii"):
        m = EAL.load_asset(f"/Game/Japan/Assets/{name}")
        if m:
            bs = m.get_editor_property("body_setup")
            if bs: bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
            EAL.save_loaded_asset(m)
    import runpy
    runpy.run_path(os.path.join(os.path.dirname(__file__), "import_wanderer.py"), run_name="__main__")
    if W.get("village"):
        import import_village
        import_village.main(terrain=False)
    if os.path.exists(os.path.join(OUT,"hidamari","manifest.json")):
        # The volcano (HD_North*) is unreal.north's: a snow or rock change reimports only it.
        runpy.run_path(os.path.join(os.path.dirname(__file__),"import_hidamari.py"),init_globals={"NORTH":False},run_name="__main__")
        # The city owner already imports this exact terrain.fbx, refreshes its material slots,
        # binds all terrain materials and saves complex collision. An earlier setup import
        # only built a second copy before that final pass; no preceding owner consumes Terrain.
        terrain = EAL.load_asset("/Game/Japan/Terrain")
        if terrain is None:
            raise RuntimeError("City import did not produce /Game/Japan/Terrain")
    else:
        import_fbx(os.path.join(OUT, "terrain.fbx"), "/Game/Japan", "Terrain")
        assign("/Game/Japan/Terrain", MI)
        terrain = EAL.load_asset("/Game/Japan/Terrain")
        if terrain:
            bs = terrain.get_editor_property("body_setup")
            if bs: bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
            EAL.save_loaded_asset(terrain)
    if os.path.exists(os.path.join(OUT,"sailboat","manifest.json")):
        runpy.run_path(os.path.join(os.path.dirname(__file__),"import_sailboat.py"),run_name="__main__")
    if W.get("zeppelin"):
        runpy.run_path(os.path.join(os.path.dirname(__file__),"import_zeppelin.py"),init_globals={"ASSETS_ONLY":True},run_name="__main__")
    build_level(terrain, W, MI)


if __name__ == "__main__":
    main()
