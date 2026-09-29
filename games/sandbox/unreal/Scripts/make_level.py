"""The sandbox's content, all generated: /Game/Sandbox/M_Prop (the live bridge's runtime-prop material: a Tint colour
times a Tex texture) and /Game/Sandbox/Sandbox, a 200 m floor with a few blocks, sun, sky and fog (auto exposure). Engine basic shapes
are referenced, not copied. Run by `atelier build sandbox` (UnrealEditor-Cmd -run=pythonscript)."""
import unreal

EAL = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary
LEVEL = '/Game/Sandbox/Sandbox'


def prop_material():
    path = '/Game/Sandbox/M_Prop'
    if EAL.does_asset_exist(path):
        EAL.delete_asset(path)
    m = unreal.AssetToolsHelpers.get_asset_tools().create_asset('M_Prop', '/Game/Sandbox', unreal.Material, unreal.MaterialFactoryNew())
    tex = MEL.create_material_expression(m, unreal.MaterialExpressionTextureSampleParameter2D, -600, 0)
    tex.set_editor_property('parameter_name', 'Tex')
    tex.set_editor_property('texture', unreal.load_asset('/Engine/EngineResources/WhiteSquareTexture'))
    tint = MEL.create_material_expression(m, unreal.MaterialExpressionVectorParameter, -600, 250)
    tint.set_editor_property('parameter_name', 'Tint')
    tint.set_editor_property('default_value', unreal.LinearColor(1, 1, 1, 1))
    mul = MEL.create_material_expression(m, unreal.MaterialExpressionMultiply, -300, 100)
    MEL.connect_material_expressions(tex, 'RGB', mul, 'A')
    MEL.connect_material_expressions(tint, '', mul, 'B')
    MEL.connect_material_property(mul, '', unreal.MaterialProperty.MP_BASE_COLOR)
    rough = MEL.create_material_expression(m, unreal.MaterialExpressionConstant, -300, 300)
    rough.set_editor_property('r', .8)
    MEL.connect_material_property(rough, '', unreal.MaterialProperty.MP_ROUGHNESS)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    return m


def colour(name, rgb):
    path = f'/Game/Sandbox/{name}'
    if EAL.does_asset_exist(path):
        EAL.delete_asset(path)
    mi = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, '/Game/Sandbox', unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    MEL.set_material_instance_parent(mi, unreal.load_asset('/Game/Sandbox/M_Prop'))
    MEL.set_material_instance_vector_parameter_value(mi, 'Tint', unreal.LinearColor(*rgb, 1))
    MEL.update_material_instance(mi)
    EAL.save_loaded_asset(mi)
    return mi


def main():
    prop_material()
    ground, block = colour('MI_Ground', (.32, .36, .30)), colour('MI_Block', (.75, .55, .35))
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if EAL.does_asset_exist(LEVEL):
        EAL.delete_asset(LEVEL)
    levels.new_level(LEVEL)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    cube = unreal.load_asset('/Engine/BasicShapes/Cube')

    def mesh(name, asset, location, scale, rotation=(0, 0, 0), material=block):
        a = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(*location), unreal.Rotator(*rotation))
        a.set_actor_label(name)
        c = a.static_mesh_component
        c.set_static_mesh(asset)
        c.set_material(0, material)
        a.set_actor_scale3d(unreal.Vector(*scale))
        return a

    mesh('Ground', cube, (0, 0, -10), (200, 200, .2), material=ground)   # 200 m square, top at 0
    mesh('Step', cube, (800, 0, 25), (4, 4, .5))
    mesh('Block', cube, (800, 600, 100), (4, 4, 2))
    mesh('Ramp', cube, (1400, -600, 60), (8, 4, .3), rotation=(0, 12, 0))   # pitch 12 degrees (Rotator: roll, pitch, yaw)
    mesh('Wall', cube, (2000, 0, 200), (.5, 16, 4))
    sun = actors.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 1000), unreal.Rotator(0, -40, -35))
    sun.set_actor_label('Sun')
    sun.light_component.set_editor_property('atmosphere_sun_light', True)
    actors.spawn_actor_from_class(unreal.SkyAtmosphere, unreal.Vector(0, 0, 0)).set_actor_label('Sky')
    sky = actors.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 500))
    sky.set_actor_label('SkyLight')
    sky.light_component.set_editor_property('real_time_capture', True)
    actors.spawn_actor_from_class(unreal.ExponentialHeightFog, unreal.Vector(0, 0, 0)).set_actor_label('Fog')
    actors.spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(0, 0, 120)).set_actor_label('PlayerStart')
    levels.save_current_level()
    unreal.log('SANDBOX LEVEL SAVED')


main()
