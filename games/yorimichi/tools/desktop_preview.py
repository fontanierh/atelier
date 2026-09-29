"""The measured desktop profile: forward renderer, 1440 pixels high, full-detail city tiles and tree LODs.

    atelier play yorimichi --profile desktop          # in a window
    atelier play yorimichi --profile desktop-1440     # fullscreen

The profile was measured on 14 September 2026 (a stable 60 fps at native 1440 on an M3 Pro): forward shading, sky
light x0.33, the v1_128m city surface tiles, the v4 city tree LODs and a spot light standing in for the harbor fill.
The renderer is chosen per process with Unreal's -ini override, so DefaultEngine.ini is never rewritten. Startup is
verified from the log: the viewport size, the renderer, and each desktop feature reporting it loaded.

Needs `atelier build yorimichi` (including the unreal.desktop step). Settings are the game's own Saved/settings.txt
with --shared-settings, or a copy per session otherwise.
"""
import argparse, json, os, re, shutil, sys, time
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
CANDIDATE = ('r.SkylightIntensityMultiplier .33,japan.CitySurfaceTiles v1_128m 1,'
             'japan.CityTreeLODs v4 1,japan.ForwardHarborFill 3')
INI = ('-ini:Engine:[/Script/Engine.RendererSettings]:r.ForwardShading={forward},'
       '[/Script/Engine.Engine]:GameViewportClientClassName=/Script/Yorimichi.DesktopPreviewViewportClient')
MARKERS = ('CITY TILES tag=v1_128m enabled=1 originals=3 tiles=85', 'CITY TREE LODS tag=v4 enabled=1 forced=0 groups=3',
           'FORWARD FILL nominal_lux=3.000 lights=1')


def command(ctx, folder, baseline=False, windowed=False, shared_settings=False, settings=''):
    preferences = PROJECT / 'Saved' / 'settings.txt' if shared_settings else folder / 'settings.txt'
    profile = 'desktop=1;performance=1;render_scale=100' if shared_settings else SETTINGS
    if settings:
        profile += ';' + settings
    return [str(ctx.unreal_app), str(ctx.uproject), '-game', '-windowed' if windowed else '-fullscreen', '-ForceRes',
            '-resx=2560', '-resy=1440', '-desktopnative1440', '-previewcapture=' + str(folder / 'ready.png'),
            '-noshaderworker', '-nosplash', '-stdout', '-abslog=' + str(folder / 'game.log'), '-set=' + profile,
            '-preferencesfile=' + str(preferences), INI.format(forward='False' if baseline else 'True'),
            '-ExecCmds=' + COMMON + ',' + ('r.SkylightIntensityMultiplier 1' if baseline else CANDIDATE),
            *os.environ.get('YORIMICHI_EXTRA_ARGS', '').split()]


def parse_ready(log, baseline=False, windowed=False):
    sizes = re.findall(r'DESKTOP PREVIEW viewport=(\d+)x(\d+) fullscreen=(\d) window_aspect=([0-9.]+)', log)
    if not sizes:
        return None
    width, height, full = map(int, sizes[-1][:3])
    if height != 1440 or not 1600 <= width <= 3840 or bool(full) != (not windowed):
        raise ValueError(f'unexpected viewport: {width}x{height}, fullscreen={full}')
    if not re.search(r'r\.ForwardShading = "' + ('0' if baseline else '1') + '"', log):
        raise ValueError('requested renderer not verified')
    if not baseline:
        missing = [m for m in MARKERS if m not in log]
        if missing:
            raise ValueError('desktop profile did not load: ' + '; '.join(missing) + ' (run `atelier build yorimichi unreal.desktop`)')
    return dict(width=width, height=height, fullscreen=bool(full))


def launch(baseline=False, windowed=False, dry_run=False, shared_settings=False, settings=''):
    ctx = Context('yorimichi')
    folder = ctx.out / 'logs' / ('desktop-' + time.strftime('%Y%m%d-%H%M%S'))
    cmd = command(ctx, folder, baseline, windowed, shared_settings, settings)
    if dry_run:
        print(json.dumps(cmd, indent=2))
        return 0
    folder.mkdir(parents=True, exist_ok=True)
    shared = PROJECT / 'Saved' / 'settings.txt'
    if not shared_settings:
        (folder / 'settings.txt').write_bytes(shared.read_bytes() if shared.exists() else b'')
    print(f'Loading Yorimichi (desktop profile). Log: {folder / "game.log"}', flush=True)
    code = guarded.run(cmd, folder, purpose='yorimichi desktop profile', env=ctx.env())
    log = (folder / 'game.log').read_text(errors='replace') if (folder / 'game.log').exists() else ''
    try:
        status = parse_ready(log, baseline, windowed)
        print('verified:', json.dumps(status) if status else 'the game never reported its viewport')
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
    args = parser.parse_args()
    sys.exit(launch(args.baseline, args.windowed, args.dry_run, args.shared_settings, args.settings))
