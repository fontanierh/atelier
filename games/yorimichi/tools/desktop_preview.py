"""The measured desktop profile: forward renderer, 1440 pixels high, full-detail city tiles and tree LODs.

    atelier play yorimichi --profile desktop          # in a window
    atelier play yorimichi --profile desktop-1440     # fullscreen

The profile was measured on 14 September 2026 (a stable 60 fps at native 1440 on an M3 Pro): forward shading, sky
light x0.33, the v1_128m city surface tiles, the v4 city tree LODs and a spot light standing in for the harbor fill.
Forward is the default; the menu can save a Lumen choice after its resource warning. The renderer is chosen per
process with Unreal's -ini override, so DefaultEngine.ini is never rewritten. Startup is
verified from the log: the viewport size, the renderer, and each desktop feature reporting it loaded.

Needs `atelier build yorimichi` (including the unreal.desktop step). Settings are the game's own Saved/settings.txt
with --shared-settings, or a copy per session otherwise.
"""
import argparse, json, math, os, re, shlex, sys, time
from pathlib import Path

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME / 'world')); import yori  # noqa: E402
from atelier.safety import guarded  # noqa: E402
from atelier.build import Context  # noqa: E402

PROJECT = GAME / 'unreal'
SETTINGS = ('desktop=1;performance=1;render_scale=100;painterly=0.35;paint_radius=2;'
            'toon=0;outline=0;exposure=0.9;saturation=1;wind=3.5;sun_height=48;sun_yaw=15;show_fps=1')
COMMON = ('r.DynamicRes.OperationMode 0,r.ScreenPercentage 100,r.RHISetGPUCaptureOptions 0,'
          'r.Shadow.CSMCaching 0,r.Shadow.CSMSlopeScaleDepthBias 3,t.MaxFPS 60,r.VSync 1,'
          'r.ForwardShading,japan.PreviewInfo')
CANDIDATE = 'r.SkylightIntensityMultiplier .33,japan.ForwardHarborFill 3'
INI = ('-ini:Engine:[/Script/Engine.RendererSettings]:r.ForwardShading={forward},'
       '[/Script/Engine.Engine]:GameViewportClientClassName=/Script/Yorimichi.DesktopPreviewViewportClient')
TILE_TAG = 'v1_128m'
TREE_TAG = 'v4'


def read_preferences(path, overrides=''):
    values = {}
    if path.exists():
        for line in path.read_text().splitlines():
            key, separator, value = line.partition('=')
            if separator:
                values[key.strip()] = value.strip()
    for pair in overrides.split(';'):
        key, separator, value = pair.partition('=')
        if separator:
            values[key.strip()] = value.strip()
    return values


def toggle(values, key, default):
    try:
        value = float(values.get(key, default))
        return value > .5 if math.isfinite(value) else bool(default)
    except (ValueError, TypeError):
        return bool(default)


def preference_path(folder, shared_settings):
    return PROJECT / 'Saved' / 'settings.txt' if shared_settings else folder / 'settings.txt'


def command(ctx, folder, baseline=False, windowed=False, shared_settings=False, settings='', extra=()):
    preferences = preference_path(folder, shared_settings)
    saved = read_preferences(preferences, settings)
    lumen = baseline or toggle(saved, 'renderer', 0)
    # Shared play keeps the user's quality, light and art choices. Performance
    # and native render scale are defaults only when no saved choice exists.
    profile = 'desktop=1' if shared_settings else SETTINGS
    if shared_settings:
        for key, value in (('performance', '1'), ('render_scale', '100')):
            if key not in saved:
                profile += f';{key}={value}'
    if settings:
        profile += ';' + settings
    profile += f';renderer={int(lumen)}'
    commands = COMMON.replace('r.ScreenPercentage 100,', '') if shared_settings else COMMON
    commands += ',japan.CitySurfaceTiles ' + TILE_TAG + ' 1,'
    commands += 'r.SkylightIntensityMultiplier 1' if lumen else CANDIDATE
    return [str(ctx.unreal_app), str(ctx.uproject), '-game', '-windowed' if windowed else '-fullscreen', '-ForceRes',
            '-resx=2560', '-resy=1440', '-desktopnative1440', '-previewcapture=' + str(folder / 'ready.png'),
            '-noshaderworker', '-nosplash', '-stdout', '-abslog=' + str(folder / 'game.log'), '-set=' + profile,
            '-preferencesfile=' + str(preferences), '-renderrestart',
            '-renderrestartrequest=' + str(folder / 'renderer-restart.txt'),
            INI.format(forward='False' if lumen else 'True'),
            # These expensive editor mesh derivatives are unused by forward
            # play. Retain normal generation for the deferred Lumen path.
            *([] if lumen else ['-ForceDPCVars=r.GenerateMeshDistanceFields=0,r.MeshCardRepresentation=0']),
            '-ExecCmds=' + commands, *shlex.split(os.environ.get('YORIMICHI_EXTRA_ARGS', '')), *extra]


def tile_counts(path):
    try:
        manifest = json.loads(path.read_text())
        sources = manifest['sources']
        if manifest.get('complete') is not True or manifest['tag'] != TILE_TAG or set(sources) != {'HD_Terrain', 'HD_Streets', 'HD_Square'}:
            raise ValueError('manifest identity or completion')
        names = [tile['name'] for source in sources.values() for tile in source['tiles']]
        if not all(source['tiles'] for source in sources.values()) or not all(isinstance(name, str) and name for name in names) or len(names) != len(set(names)):
            raise ValueError('empty or duplicate tiles')
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ValueError('missing or invalid completed city tile manifest; run `atelier build yorimichi`') from error
    return len(sources), len(names)


def parse_ready(log, baseline=False, windowed=False, tile_manifest=None, tree_optimization=True):
    sizes = re.findall(r'DESKTOP PREVIEW viewport=(\d+)x(\d+) fullscreen=(\d) window_aspect=([0-9.]+)', log)
    if not sizes:
        return None
    width, height, full = map(int, sizes[-1][:3])
    if height != 1440 or not 1600 <= width <= 3840 or bool(full) != (not windowed):
        raise ValueError(f'unexpected viewport: {width}x{height}, fullscreen={full}')
    if not re.search(r'r\.ForwardShading = "' + ('0' if baseline else '1') + '"', log):
        raise ValueError('requested renderer not verified')
    originals, tiles = tile_counts(tile_manifest or PROJECT / 'Content' / 'Data' / 'city_surface_tiles' / TILE_TAG / 'manifest.json')
    markers = [f'CITY TILES tag={TILE_TAG} enabled=1 originals={originals} tiles={tiles}',
               f'CITY TREE LODS tag={TREE_TAG} enabled={int(tree_optimization)} forced=0 groups=3']
    if not baseline:
        markers.append('FORWARD FILL nominal_lux=3.000 lights=1')
    missing = [marker for marker in markers if not re.search(re.escape(marker) + r'(?=\s|$)', log)]
    if missing:
        raise ValueError('desktop profile did not load: ' + '; '.join(missing) + ' (run `atelier build yorimichi unreal.desktop`)')
    return dict(width=width, height=height, fullscreen=bool(full))


def launch(baseline=False, windowed=False, dry_run=False, shared_settings=False, settings='', memory_gib=10., extra=()):
    if not math.isfinite(memory_gib) or not 10 <= memory_gib <= 14:
        raise ValueError('--memory-gib must be 10 to 14 GiB')
    ctx = Context('yorimichi')
    folder = ctx.out / 'logs' / ('desktop-' + time.strftime('%Y%m%d-%H%M%S'))
    preferences = preference_path(folder, shared_settings)
    if not shared_settings and not dry_run:
        folder.mkdir(parents=True, exist_ok=True)
        shared = PROJECT / 'Saved' / 'settings.txt'
        preferences.write_bytes(shared.read_bytes() if shared.exists() else b'')
    cmd = command(ctx, folder, baseline, windowed, shared_settings, settings, extra)
    if dry_run:
        print(json.dumps(cmd, indent=2))
        return 0
    folder.mkdir(parents=True, exist_ok=True)
    attempt = 0
    while True:
        run = folder if attempt == 0 else folder / f'restart-{attempt}'
        run.mkdir(parents=True, exist_ok=True)
        restart_request = run / 'renderer-restart.txt'
        restart_request.unlink(missing_ok=True)
        cmd = command(ctx, folder, baseline, windowed, shared_settings, settings, extra)
        # Keep the preference file across relaunches but never overwrite logs.
        cmd = [('-abslog=' + str(run / 'game.log')) if arg.startswith('-abslog=') else
               ('-previewcapture=' + str(run / 'ready.png')) if arg.startswith('-previewcapture=') else
               ('-renderrestartrequest=' + str(restart_request)) if arg.startswith('-renderrestartrequest=') else arg for arg in cmd]
        values = read_preferences(preferences, settings)
        lumen = baseline or toggle(values, 'renderer', 0)
        trees = toggle(values, 'tree_optimization', 1)
        if lumen:
            print('Lumen uses more GPU resources and memory; its first launch may compile additional mesh/shader data.', flush=True)
        print(f'Loading Yorimichi ({"Lumen" if lumen else "forward"}, tree optimization={int(trees)}). Log: {run / "game.log"}', flush=True)
        code = guarded.run(cmd, run, purpose='yorimichi desktop profile', env=ctx.env(), kind='game', limit_gib=memory_gib)
        log = (run / 'game.log').read_text(errors='replace') if (run / 'game.log').exists() else ''
        if code == 0 and restart_request.exists():
            request = restart_request.read_text()
            restart_request.unlink()
            saved = read_preferences(preferences)
            saved_renderer = toggle(saved, 'renderer', 0)
            if 'renderer' not in saved or request not in ('renderer=0\n', 'renderer=1\n') or request != f'renderer={int(saved_renderer)}\n' or saved_renderer == lumen:
                print('renderer restart request does not match a changed saved choice; stopping', flush=True)
                return 1
            print('Renderer preference saved; restarting Yorimichi after releasing the render slot.', flush=True)
            # The warning-confirmed menu choice must win over an earlier CLI
            # override or comparison flag on the next process.
            settings = ';'.join(pair for pair in settings.split(';') if pair.partition('=')[0].strip() != 'renderer')
            baseline = False
            attempt += 1
            continue
        try:
            status = parse_ready(log, lumen, windowed, tree_optimization=trees)
            print('verified:', json.dumps(status) if status else 'the game never reported its viewport')
            if status is None:
                return 1
        except ValueError as error:
            print('not verified:', error)
            return 1
        return code


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--baseline', action='store_true', help='the original deferred look, for comparison')
    parser.add_argument('--windowed', action='store_true', help='a window instead of fullscreen')
    parser.add_argument('--dry-run', action='store_true', help='print the launch command')
    parser.add_argument('--shared-settings', action='store_true', help='use and save the game\'s own settings')
    parser.add_argument('--settings', default='', help='extra key=value;key=value overrides for this session')
    parser.add_argument('--memory-gib', type=float, default=10., help='memory guard limit, 10 to 14 GiB')
    args, extra = parser.parse_known_args()
    if extra[:1] == ['--']:
        extra = extra[1:]
    sys.exit(launch(args.baseline, args.windowed, args.dry_run, args.shared_settings, args.settings, args.memory_gib, extra))
