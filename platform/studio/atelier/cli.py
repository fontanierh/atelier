"""The `atelier` command.

    atelier new <game> [--title T]     start a new game from the sandbox (module, classes, project and paths renamed)
    atelier doctor <game>              check Unreal, Blender, ffmpeg, Python packages and the game's sources
    atelier setup [--headless]         check full Xcode and Metal; repair UE 5.8.2 for SSH-only builds
    atelier reuse <game> --from PATH   seed this fresh worktree from a verified build of the same revision
    atelier fetch <game>               download what a game needs but may not redistribute (sound masters)
    atelier build <game> [step ...]    build what changed; --list, --force, --dry-run, --touch
    atelier play <game> [--profile P] [-- unreal args]   launch the game under the render lock and memory guard
    atelier stream <game> start|stop|status|build-web   stream the game to a phone, a handheld or a friend's browser
    atelier live state|py|shot         talk to the running game through the live bridge
    atelier qa <game> <scenario> ...   run games/<game>/scenarios/<scenario>.py against the running game
    atelier board post|read|subscribe|unsubscribe|status   coordinate machine-local agents
    atelier lint                       public-repository rules: no secrets, no personal paths, no game names in the platform
"""
import argparse, datetime, importlib.util, os, re, shutil, subprocess, sys
from pathlib import Path

from . import manifest, paths
from .build import Context, build, list_steps


def _ok(flag, text):
    print(('  ok    ' if flag else '  MISSING ') + text)
    return flag


def doctor(game):
    ctx = Context(game)
    data = manifest.game(game)
    print(f'{data.get("title", game)}: {ctx.game_dir}')
    good = True
    good &= _ok(ctx.unreal_cmd.exists(), f'Unreal Engine at {ctx.unreal_root} (set UE_ROOT to move it)')
    blender = shutil.which(ctx.blender) or (ctx.blender if Path(ctx.blender).exists() else None)
    version = ''
    if blender:
        result = subprocess.run([blender, '--version'], capture_output=True, text=True)
        version = (result.stdout.splitlines() or [''])[0]
    good &= _ok(bool(blender), f'Blender ({version or "not found; put blender on PATH or set BLENDER"})')
    good &= _ok(bool(shutil.which('ffmpeg')), 'ffmpeg on PATH')
    from .setup import mac_checks
    for ok, message in mac_checks():
        good &= _ok(ok, message)
    for module in ('numpy', 'PIL', 'fontTools'):
        good &= _ok(importlib.util.find_spec(module) is not None, f'Python package {module} ({sys.executable})')
    good &= _ok(ctx.uproject is not None and ctx.uproject.exists(), f'Unreal project {ctx.uproject}')
    for fetch in data.get('fetch', {}).get('needs', []):
        folder = paths.cache_dir(*fetch.split('/'))
        good &= _ok(any(folder.rglob('*.wav')), f'downloaded {fetch} in {folder} (run `atelier fetch {game}`)')
    print('ready' if good else 'fix the MISSING lines above')
    return 0 if good else 1


def fetch(game):
    data = manifest.game(game)
    for script in data.get('fetch', {}).get('scripts', []):
        path = paths.game_dir(game) / script
        print(f'-> {path.relative_to(paths.REPO)}')
        code = subprocess.call([sys.executable, str(path)])
        if code:
            return code
    return 0


def play(game, profile, settings, extra):
    ctx = Context(game)
    data = manifest.game(game)
    profiles = data.get('play', {})
    if profile not in profiles:
        raise SystemExit(f'no play profile {profile!r}; {game} has {sorted(profiles)}')
    spec = profiles[profile]
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    folder = ctx.out / 'logs' / f'play-{profile}-{stamp}'
    folder.mkdir(parents=True, exist_ok=True)
    if 'script' in spec:   # a game-specific launcher (for example the desktop profile)
        command = [sys.executable, str(ctx.game_dir / spec['script']), *spec.get('args', []), *extra]
        if settings:
            command += ['--settings', settings]
        return subprocess.call(command, env=ctx.env())
    args = [a.replace('{run}', str(folder)) for a in spec.get('args', [])]   # {run}: this run's log folder (review output)
    command = [str(ctx.unreal_app), str(ctx.uproject), *args, '-stdout', f'-abslog={folder / "game.log"}', *extra]
    if settings:
        command.append(f'-set={settings}')
    from .safety import guarded
    print(f'playing {game} ({profile}); log {folder / "game.log"}')
    return guarded.run(command, folder, timeout=float(spec.get('timeout', 0)), purpose=f'atelier play {game}', env=ctx.env(),
                       kind='game')


PERSONAL = [
    (re.compile(r'/Users/(?!Shared/)[A-Za-z0-9._-]+/'), 'a home-directory path'),
    (re.compile(r'\b[a-z0-9-]+\.tail[0-9a-f]{4,}\.ts\.net\b'), 'a tailnet hostname'),
    (re.compile(r'\b(sk-[A-Za-z0-9_-]{20,}|tsk_[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|xox[bp]-[A-Za-z0-9-]{10,})'), 'an API token'),
    (re.compile(r'SecurityToken=[A-Za-z0-9]{8,}'), 'an engine security token'),
]


def lint(staged=False):
    """Checks for the public repository and for the platform's independence from games. `staged` checks the files
    about to be committed (the pre-commit hook), reading their staged content."""
    listing = ['git', 'diff', '--cached', '--name-only', '--diff-filter=ACMR'] if staged else ['git', 'ls-files']
    tracked = subprocess.run(listing, cwd=paths.REPO, capture_output=True, text=True).stdout.split()
    problems = []
    games = sorted(p.name for p in paths.GAMES.iterdir() if p.is_dir())
    for rel in tracked:
        path = paths.REPO / rel
        if rel == '.env' or rel.startswith('.env.') and rel != '.env.example':
            problems.append(f'{rel}: credentials file is tracked')
        if path.suffix.lower() in ('.wav', '.mp3', '.flac', '.ogg'):
            problems.append(f'{rel}: audio files are not committed (licences); build them from fetched masters')
        if path.suffix.lower() not in ('.py', '.md', '.toml', '.json', '.ini', '.cpp', '.h', '.cs', '.txt', '.mjs', '.js',
                                       '.cjs', '.html', '.css', '.sh', '.uproject', '.uplugin', '.yml', '.yaml', ''):
            continue
        try:
            if staged:
                text = subprocess.run(['git', 'show', f':{rel}'], cwd=paths.REPO, capture_output=True).stdout.decode(errors='ignore')
            else:
                text = path.read_text(errors='ignore')
        except OSError:
            continue
        for pattern, what in PERSONAL:
            for match in pattern.finditer(text):
                line = text.count('\n', 0, match.start()) + 1
                problems.append(f'{rel}:{line}: {what}')
        if rel.startswith('platform/') and rel != 'platform/studio/atelier/cli.py':
            for game in games:
                if game != 'sandbox' and re.search(rf'\b{re.escape(game)}\b', text, re.IGNORECASE):
                    problems.append(f'{rel}: the platform names the game {game!r}')
    for problem in problems:
        print(problem)
    print(f'{len(tracked)} files checked, {len(problems)} problems')
    return 1 if problems else 0


def make_parser():
    parser = argparse.ArgumentParser(prog='atelier', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    from . import board
    board.configure(sub)
    p = sub.add_parser('new'); p.add_argument('game'); p.add_argument('--title')
    p = sub.add_parser('doctor'); p.add_argument('game')
    p = sub.add_parser('setup'); p.add_argument('--headless', action='store_true')
    p.add_argument('--workers', type=int, default=3, help='headless compiler parallelism (default: 3)')
    p = sub.add_parser('reuse'); p.add_argument('game'); p.add_argument('--from', dest='source', required=True)
    p.add_argument('--to', dest='target', help='fresh worktree path (default: this checkout)')
    p = sub.add_parser('fetch'); p.add_argument('game')
    p = sub.add_parser('build'); p.add_argument('game'); p.add_argument('steps', nargs='*')
    p.add_argument('--list', action='store_true'); p.add_argument('--force', action='store_true'); p.add_argument('--dry-run', action='store_true')
    p.add_argument('--touch', action='store_true', help='record the steps as built without running them (after a recipe refactor)')
    p = sub.add_parser('play'); p.add_argument('game'); p.add_argument('--profile', default='play')
    p.add_argument('--set', default='', help='settings overrides, key=value;key=value')
    p.add_argument('extra', nargs='*', help='Unreal arguments, after --')
    p = sub.add_parser('stream'); p.add_argument('game'); p.add_argument('action', choices=['start', 'stop', 'status', 'build-web'])
    p.add_argument('--local', action='store_true', help='this machine only: no Tailscale Serve')
    p.add_argument('--install', action='store_true', help='build-web: reinstall platform/web packages (npm ci)')
    p = sub.add_parser('lint'); p.add_argument('--staged', action='store_true', help='check the staged files only')
    p = sub.add_parser('live'); p.add_argument('rest', nargs=argparse.REMAINDER)
    p = sub.add_parser('qa'); p.add_argument('game'); p.add_argument('scenario'); p.add_argument('rest', nargs=argparse.REMAINDER)
    return parser


def parse_args(argv=None):
    """For `play`, everything after the first `--` goes to Unreal as is, wherever the options sit. argparse alone
    rejects it when an option follows the game (`play <game> --profile P -- -RenderOffscreen`): `extra` has already
    been matched, empty, right after the game."""
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ['play'] and '--' in argv:
        cut = argv.index('--')
        args = make_parser().parse_args(argv[:cut])
        args.extra += argv[cut + 1:]
        return args
    return make_parser().parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.command == 'board':
        from . import board
        return board.main(args)
    if args.command == 'new':
        from . import new
        return new.main(args.game, args.title)
    if args.command == 'doctor':
        return doctor(args.game)
    if args.command == 'setup':
        from . import setup
        return setup.main(args.headless, args.workers)
    if args.command == 'reuse':
        from . import reuse
        return reuse.main(args.game, args.source, args.target)
    if args.command == 'fetch':
        return fetch(args.game)
    if args.command == 'build':
        if args.list:
            list_steps(args.game)
            return 0
        return build(args.game, args.steps, force=args.force, dry=args.dry_run, touch=args.touch)
    if args.command == 'play':
        return play(args.game, args.profile, args.set, args.extra)
    if args.command == 'stream':
        from . import stream
        return stream.main(args.game, args.action, local=args.local, install=args.install)
    if args.command == 'lint':
        return lint(args.staged)
    if args.command == 'qa':
        script = paths.game_dir(args.game) / 'scenarios' / f'{args.scenario}.py'
        if not script.exists():
            raise SystemExit(f'no scenario {script}')
        return subprocess.call([sys.executable, str(script), *args.rest])
    if args.command == 'live':
        from . import live
        return live.main(args.rest)


if __name__ == '__main__':
    sys.exit(main())
