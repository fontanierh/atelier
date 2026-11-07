"""Capture each visual parity pose (tools/parity/poses.json) as `<pose>.png` for tools/parity/compare.py (plan P3.6).

V2_CAPTURE_DIR names the output folder (required); it must hold no PNG and no capture.json yet, so a stale screenshot
can never stand in for the current scene. V2_OPEN_MAP names the map to open first (default
/Game/V2/Maps/Slice; empty keeps the editor's current map), V2_CAPTURE_POSES another poses file, V2_CAPTURE_SIZE the
resolution (default 2560x1440, the play profile's), V2_CAPTURE_WARMUP the renders before the kept one (default 8,
so streaming and temporal effects settle) and V2_CAPTURE_LOAD_M the radius of World Partition actors loaded around
each pose (default 500 m; a partitioned map opens in the editor with none loaded).

editor.run's commandlet editor has no viewport, so each pose is rendered by a transient SceneCapture2D (final
tone-mapped colour, with the world's post process volumes) into a transient render target and exported as PNG.
It saves nothing: the
capture actor is transient and destroyed, the render target is never an asset, and the dirty packages are reported
as in open_close.py.

After the last pose it writes the receipt capture.json next to the PNGs: the V2 git revision (and whether
games/yorimichi_v2 had uncommitted changes), the map, capture size, warmup, load radius, the poses file's sha256, the
UTC time, the engine version, the render settings (renderer and the scalability and screen-percentage values in
QUALITY) and `source` ("v2"; V2_CAPTURE_SOURCE may name another, e.g. "donor-runtime").
compare.py requires it on both sides.

Opening an editor map does NOT instantiate the donor's runtime-spawned scenery (docs/INVENTORY.md), so this script
on the donor's map is no donor baseline. The donor baseline must come from a real initialized donor scene (the
running game); that capture route is pending.
"""
import datetime
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

import unreal as U

MARKER = 'V2 CAPTURE DONE'
QUALITY = ('r.ForwardShading', 'r.ScreenPercentage', 'sg.ResolutionQuality', 'sg.ViewDistanceQuality', 'sg.AntiAliasingQuality',
           'sg.ShadowQuality', 'sg.GlobalIlluminationQuality', 'sg.ReflectionQuality', 'sg.PostProcessQuality',
           'sg.TextureQuality', 'sg.EffectsQuality', 'sg.FoliageQuality', 'sg.ShadingQuality')
EAS = U.get_editor_subsystem(U.EditorActorSubsystem)
V2_ROOT = Path(__file__).resolve().parents[2]
if not os.environ.get('V2_CAPTURE_DIR'):
    raise RuntimeError('V2_CAPTURE_DIR must name the folder for the captures')
out = Path(os.environ['V2_CAPTURE_DIR']).resolve()
out.mkdir(parents=True, exist_ok=True)
stale = sorted(p.name for p in out.iterdir() if p.suffix.lower() == '.png' or p.name == 'capture.json')
if stale:
    raise RuntimeError(f'{out} must start empty of captures; it holds {stale}')


def git(*args):
    return subprocess.run(['git', '-C', str(V2_ROOT), *args], check=True, capture_output=True, text=True).stdout


revision = {'commit': git('rev-parse', 'HEAD').strip(), 'dirty': bool(git('status', '--porcelain', '--', '.').strip())}
poses_file = Path(os.environ.get('V2_CAPTURE_POSES') or V2_ROOT / 'tools/parity/poses.json')
poses_bytes = poses_file.read_bytes()
poses = json.loads(poses_bytes)
if poses.get('schema') != 1:
    raise RuntimeError(f'{poses_file}: unknown poses schema {poses.get("schema")!r}')
bad = [p.get('name') for p in poses['poses'] if not re.fullmatch(r'[a-z0-9_]+', str(p.get('name')))]
if bad:
    raise RuntimeError(f'pose names must be lower-case file names: {bad}')
width, height = (int(v) for v in os.environ.get('V2_CAPTURE_SIZE', '2560x1440').lower().split('x'))
warmup = int(os.environ.get('V2_CAPTURE_WARMUP', '8'))
load_cm = float(os.environ.get('V2_CAPTURE_LOAD_M', '500')) * 100.

path = os.environ.get('V2_OPEN_MAP', '/Game/V2/Maps/Slice')
if path and not U.get_editor_subsystem(U.LevelEditorSubsystem).load_level(path):
    raise RuntimeError(f'cannot open {path}')
world = U.get_editor_subsystem(U.UnrealEditorSubsystem).get_editor_world()


def load_around(location):
    """Load the World Partition actors within load_cm of a pose; nothing to do on a map without a partition."""
    library = getattr(U, 'WorldPartitionBlueprintLibrary', None)
    if library is None:
        return 0
    r = U.Vector(load_cm, load_cm, load_cm)
    descs = library.get_intersecting_actor_descs(U.Box(min=location - r, max=location + r, is_valid=True)) or []
    guids = [d.get_editor_property('guid') for d in descs]
    if guids:
        library.load_actors(guids)
    return len(guids)


def finish_loading():
    """Flush async loading, finish shader and asset compilation, stream textures in (as the donor's skate scripts)."""
    library = getattr(U, 'AutomationLibrary', None) or getattr(U, 'AutomationBlueprintFunctionLibrary')
    library.finish_loading_before_screenshot()


loaded = sum(load_around(U.Vector(*p['location'])) for p in poses['poses'])
U.log(f'V2 CAPTURE {path or world.get_name()}: {len(poses["poses"])} poses at {width}x{height}, '
      f'{loaded} partition actors loaded')
finish_loading()
target = U.RenderingLibrary.create_render_target2d(world, width, height, U.TextureRenderTargetFormat.RTF_RGBA8)
camera = EAS.spawn_actor_from_class(U.SceneCapture2D, U.Vector(0, 0, 0), U.Rotator(roll=0, pitch=0, yaw=0),
                                    transient=True)
if camera is None:
    raise RuntimeError('could not spawn the capture camera')
try:
    capture = camera.get_component_by_class(U.SceneCaptureComponent2D)
    capture.set_editor_property('texture_target', target)
    capture.set_editor_property('capture_source', U.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
    capture.set_editor_property('capture_every_frame', False)
    capture.set_editor_property('capture_on_movement', False)
    capture.set_editor_property('always_persist_rendering_state', True)
    for pose in poses['poses']:
        name, r = pose['name'], pose['rotation']
        if pose.get('todo'):
            U.log_warning(f'  {name}: placeholder pose (todo), captured anyway')
        camera.set_actor_location_and_rotation(U.Vector(*pose['location']),
                                               U.Rotator(roll=r['roll'], pitch=r['pitch'], yaw=r['yaw']), False, True)
        capture.set_editor_property('fov_angle', float(pose['fov']))
        finish_loading()
        for _ in range(warmup + 1):
            capture.capture_scene()
        U.RenderingLibrary.export_render_target(world, target, str(out), f'{name}.png')
        if not (out / f'{name}.png').is_file():
            raise RuntimeError(f'the capture of {name} was not written to {out}')
        U.log(f'V2 CAPTURED {name}: {out / (name + ".png")}')
finally:
    EAS.destroy_actor(camera)
receipt = {'schema': 1, 'source': os.environ.get('V2_CAPTURE_SOURCE') or 'v2', 'revision': revision,
           'map': path or world.get_path_name(), 'size': [width, height], 'warmup': warmup,
           'load_radius_m': load_cm / 100., 'poses_sha256': hashlib.sha256(poses_bytes).hexdigest(),
           'poses': [p['name'] for p in poses['poses']],
           'captured_utc': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
           'engine_version': U.SystemLibrary.get_engine_version(),
           'render': {'renderer': 'SceneCapture2D SCS_FINAL_COLOR_LDR',
                      'quality': {cvar: U.SystemLibrary.get_console_variable_float_value(cvar) for cvar in QUALITY}}}
(out / 'capture.json').write_text(json.dumps(receipt, indent=2) + '\n')
dirty =[p.get_name() for p in U.EditorLoadingAndSavingUtils.get_dirty_map_packages() +
         U.EditorLoadingAndSavingUtils.get_dirty_content_packages()]
U.log(f'{MARKER}: {len(poses["poses"])} captures in {out}; dirty (not saved): {dirty or "none"}')
