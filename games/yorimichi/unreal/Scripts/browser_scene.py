"""Build the bounded browser map from the normally imported character and park."""
from pathlib import Path
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import unreal as U

CONTENT = Path(__file__).resolve().parents[1] / 'Content'
E = U.EditorAssetLibrary
MAP = '/Game/Browser/SkatePier'
REQUIRED = (
    '/Game/Cairo/BP_Cairo', '/Game/Japan/Materials/M_Painterly',
    '/Game/Japan/Materials/M_Sky', '/Game/Japan/Audio/DA_Footsteps',
    '/Game/SkateRuntime/RuntimeData', '/Game/SkateMotion/MotionData',
    '/Game/SkatePark/Board/SM_SkateDeck', '/Game/SkatePark/Board/SM_SkateTruck',
    '/Game/SkatePark/Board/SM_SkateWheel', '/Game/SkatePark/Board/M_BoardDissolve',
)
for package in REQUIRED:
    if not E.does_asset_exist(package):
        raise RuntimeError('Required browser scene asset is missing: ' + package)

eas = U.get_editor_subsystem(U.EditorActorSubsystem)
# Start from an empty world on every rebuild, including when MAP already exists.
# new_level(MAP) refuses an existing destination instead of replacing it.
world = U.EditorLoadingAndSavingUtils.new_blank_map(False)
if not world:
    raise RuntimeError('Could not create browser scene scratch world')
sun = eas.spawn_actor_from_class(U.DirectionalLight, U.Vector(0, 0, 3000))
sun.set_actor_rotation(U.Rotator(roll=0, pitch=-48, yaw=-30), False)
sun.light_component.set_mobility(U.ComponentMobility.MOVABLE)
sun.light_component.set_intensity(7)
sun.light_component.set_light_color(U.LinearColor(1, .90, .76, 1))
sun.light_component.set_editor_property('forward_shading_priority', 1)
sun.light_component.set_editor_property('dynamic_shadow_distance_movable_light', 20000)
sky = eas.spawn_actor_from_class(U.SkyLight, U.Vector(0, 0, 3000))
sky.light_component.set_mobility(U.ComponentMobility.MOVABLE)
sky.light_component.set_editor_property('real_time_capture', False)
sky.light_component.set_intensity(3.8)
sky.light_component.set_light_color(U.LinearColor(.95, .96, 1, 1))
post = eas.spawn_actor_from_class(U.PostProcessVolume, U.Vector(0, 0, 0))
post.set_editor_property('unbound', True)
s = post.settings
for key, value in {
    'auto_exposure_method': U.AutoExposureMethod.AEM_HISTOGRAM,
    'auto_exposure_bias': 1.24, 'auto_exposure_min_brightness': 1.2,
    'auto_exposure_max_brightness': 1.2, 'motion_blur_amount': 0,
    'screen_space_reflection_intensity': 0,
    'dynamic_global_illumination_method': U.DynamicGlobalIlluminationMethod.NONE,
    'film_toe': .3, 'film_shoulder': .28, 'film_slope': .7,
}.items():
    s.set_editor_property('override_' + key, True)
    s.set_editor_property(key, value)
# Keep the desktop scene's grade and the same painterly material; its mobile
# texture lookup is selected by the material compiler for HTML5.
from setup_project import soft_colour_grade
soft_colour_grade(s)
s.set_editor_property('weighted_blendables', U.WeightedBlendables(array=[
    U.WeightedBlendable(weight=1, object=E.load_asset('/Game/Japan/Materials/M_Painterly'))]))
post.set_editor_property('settings', s)
if not U.EditorLoadingAndSavingUtils.save_map(world, MAP):
    raise RuntimeError('Could not save browser scene map')
root = CONTENT / 'Data/Browser'
scene = json.loads((root / 'scene-source.json').read_text())
scene['required_assets'] = [p + '.' + p.rsplit('/', 1)[1] + ('_C' if '/BP_' in p else '') for p in REQUIRED]
(root / 'scene.json').write_text(json.dumps(scene, indent=2) + '\n')
U.log('BROWSER SCENE IMPORT COMPLETE')
