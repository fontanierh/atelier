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
import argparse, errno, json, math, os, re, shlex, socket, sys, time
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


def renderer_arguments(lumen, desktop_viewport=False):
    """Keep scripted probes and normal play on the same renderer startup path."""
    ini = '-ini:Engine:[/Script/Engine.RendererSettings]:r.ForwardShading=' + ('False' if lumen else 'True')
    if desktop_viewport:
        ini += ',[/Script/Engine.Engine]:GameViewportClientClassName=/Script/Yorimichi.DesktopPreviewViewportClient'
    # Forward play does not use these expensive editor mesh derivatives. Lumen still needs them.
    return ['-noshaderworker', ini, *([] if lumen else
            ['-ForceDPCVars=r.GenerateMeshDistanceFields=0,r.MeshCardRepresentation=0'])]


def bridge_bind_error(text, port):
    """A listening announcement alone does not prove the requested socket bound."""
    pattern = r'HttpListener unable to bind to (?:127\.0\.0\.1|localhost|\[?::1\]?):' + re.escape(str(port)) + r'(?!\d)'
    return next((line.strip() for line in text.splitlines() if re.search(pattern, line)), None)


def command(ctx, folder, baseline=False, windowed=False, shared_settings=False, settings='', extra=(), preferences=None):
    preferences = Path(preferences) if preferences is not None else preference_path(folder, shared_settings)
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
            '-nosplash', '-stdout', '-abslog=' + str(folder / 'game.log'), '-set=' + profile,
            '-preferencesfile=' + str(preferences), '-renderrestart',
            '-renderrestartrequest=' + str(folder / 'renderer-restart.txt'),
            *renderer_arguments(lumen, desktop_viewport=True),
            '-ExecCmds=' + commands, *shlex.split(os.environ.get('YORIMICHI_EXTRA_ARGS', '')), *extra]


LAUNCHER = """#!/bin/bash
# Yorimichi with the desktop profile: the forward renderer, the native 1440 viewport and the optimized city tiles and
# trees. Generated from games/yorimichi/tools/desktop_preview.py for the packaged game. Settings are kept in
# the app's macOS sandbox container. The package is cooked for forward shading only, so it always
# starts Forward: a Lumen choice saved in the menu does not apply to the packaged game.
set -u
cd "$(dirname "$0")"
GAME="$PWD/Yorimichi.app/Contents/MacOS/Yorimichi"
# Xcode signs the app with App Sandbox. Absolute paths outside its container are denied even when the launcher
# can create them. Read the shipped bundle identity rather than hard-coding a project or machine-specific path.
BUNDLE_ID=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$PWD/Yorimichi.app/Contents/Info.plist") || exit 1
case "$BUNDLE_ID" in
  ''|*[!A-Za-z0-9.-]*) echo "Invalid application bundle identifier" >&2; exit 1 ;;
esac
APP_DATA="$HOME/Library/Containers/$BUNDLE_ID/Data"
SUPPORT="$APP_DATA/Library/Application Support/Yorimichi"
LOGS="$APP_DATA/Library/Logs/Yorimichi"
mkdir -p "$SUPPORT" "$LOGS"
PREFS="$SUPPORT/settings.txt"
touch "$PREFS"
xattr -dr com.apple.quarantine "$PWD" 2>/dev/null || true
saved() { grep -E "^[[:space:]]*$1[[:space:]]*=" "$PREFS" | tail -1 | cut -d= -f2- | tr -d '[:space:]'; }
PROFILE="desktop=1"
[ -n "$(saved performance)" ] || PROFILE="$PROFILE;performance=1"
[ -n "$(saved render_scale)" ] || PROFILE="$PROFILE;render_scale=100"
RENDERER=0; RENDER=(@FORWARD@); COMMANDS=@FORWARD_COMMANDS@
LOG="$LOGS/game.log"
ARGS=(-fullscreen -ForceRes -resx=2560 -resy=1440 -desktopnative1440 -nosplash -abslog="$LOG"
  -set="$PROFILE;renderer=$RENDERER" -preferencesfile="$PREFS" "${RENDER[@]}" -ExecCmds="$COMMANDS" "$@")
# A Development package can segfault at startup: the engine's memory tracker frees itself on the game thread while
# AppKit's launch event allocates through it on the main thread (docs/PACKAGING.md). Retry that crash once, and only
# when it ended the game within @STARTUP_SECONDS@ s without touching game.log; a crash after the engine started is real.
log_identity() { stat -f '%i:%z:%m' "$LOG" 2>/dev/null || echo none; }
BEFORE=$(log_identity); START=$SECONDS
"$GAME" "${ARGS[@]}"; STATUS=$?
if [ "$STATUS" -eq 139 ] && [ $((SECONDS - START)) -lt @STARTUP_SECONDS@ ] && [ "$(log_identity)" = "$BEFORE" ]; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') Yorimichi crashed at startup after $((SECONDS - START)) s, before game.log;" \\
    "opening it once more. macOS kept the report in ~/Library/Logs/DiagnosticReports." | tee -a "$LOGS/launcher.log" >&2
  exec "$GAME" "${ARGS[@]}"
fi
exit "$STATUS"
"""


def packaged_launcher(startup_seconds=20):
    """`Play Yorimichi.command` beside the packaged .app: this profile's shared-settings launch, without the repository,
    Python or the guard. It honours saved settings like --shared-settings, except the renderer: the package is cooked
    for forward shading only (the project's r.ForwardShading), so it always starts Forward."""
    commands = COMMON.replace('r.ScreenPercentage 100,', '') + ',japan.CitySurfaceTiles ' + TILE_TAG + ' 1,'
    return (LAUNCHER.replace('@FORWARD@', ' '.join(map(shlex.quote, renderer_arguments(False, desktop_viewport=True))))
            .replace('@FORWARD_COMMANDS@', shlex.quote(commands + CANDIDATE))
            .replace('@STARTUP_SECONDS@', str(int(startup_seconds))))


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


def tree_lod_choice(values):
    try:
        value = float(values.get('tree_lod_mode', 0))
        return int(math.floor(max(0, min(3, value)) + .5)) if math.isfinite(value) else 0
    except (ValueError, TypeError):
        return 0


def parse_ready(log, baseline=False, windowed=False, tile_manifest=None, tree_optimization=True, tree_lod_mode=0):
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
               f'CITY TREE LODS tag={TREE_TAG} enabled={int(tree_optimization)} forced={tree_lod_mode} groups=3']
    if not baseline:
        markers.append('FORWARD FILL nominal_lux=3.000 lights=1')
    missing = [marker for marker in markers if not re.search(re.escape(marker) + r'(?=\s|$)', log)]
    if missing:
        raise ValueError('desktop profile did not load: ' + '; '.join(missing) + ' (run `atelier build yorimichi unreal.desktop`)')
    return dict(width=width, height=height, fullscreen=bool(full))


def wait_for_bridge_port(command, timeout=90.):
    """Wait without a render slot for the old listener's TCP state to expire; never share an occupied port."""
    port = next((int(arg.split('=', 1)[1]) for arg in command if arg.lower().startswith('-liveport=')), 8830)
    if not 1 <= port <= 65535:
        raise ValueError('live bridge port must be 1 to 65535')
    started = time.monotonic()
    deadline = started + timeout
    last_note = None
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(('127.0.0.1', port))
                return
            except OSError as error:
                if error.errno != errno.EADDRINUSE:
                    raise
        now = time.monotonic()
        if now >= deadline:
            raise TimeoutError(f'renderer restart: loopback bridge port {port} stayed occupied for {timeout:g} s')
        if last_note is None or now-last_note >= 10:
            print(f'Renderer restart waiting for loopback bridge port {port}: {now-started:.0f} s; no render slot held.', flush=True)
            last_note = now
        time.sleep(min(1., deadline-now))


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
            # A fast restart can outrun TCP TIME_WAIT on the bridge. Do not enable
            # address/port sharing: wait before seeking normal render admission.
            wait_for_bridge_port(cmd)
            attempt += 1
            continue
        try:
            status = parse_ready(log, lumen, windowed, tree_optimization=trees,
                                 tree_lod_mode=tree_lod_choice(values))
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
