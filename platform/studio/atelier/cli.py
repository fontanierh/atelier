"""The `atelier` command.

    atelier new <game> [--title T]     start a new game from the sandbox (module, classes, project and paths renamed)
    atelier doctor <game>              check Unreal, Blender, ffmpeg, Python packages and the game's sources
    atelier setup [--headless]         check full Xcode and Metal; repair UE 5.8.2 for SSH-only builds
    atelier pool publish|restore|status|abandon <game> <step>   share explicitly owned portable outputs (docs/ARTIFACT_POOL.md)
    atelier cache status|gc|pin|unpin|forget   inspect and prune automatic local product reuse
    atelier fetch <game>               download what a game needs but may not redistribute (sound masters)
    atelier build <game> [step ...]    restore checkpoints and build changed tasks; --plan --explain
    atelier play <game> [--profile P] [--memory-gib N] [-- unreal args]   launch the game under the render lock and memory guard
    atelier playtest <game> [--tag T] [--download-only] [-- launcher args]   play the latest GitHub release, downloading it if needed
    atelier stream <game> start|stop|status|build-web   stream the game to a phone, a handheld or a friend's browser
    atelier live state|py|shot         talk to the running game through the live bridge
    atelier qa <game> <scenario> ...   run games/<game>/scenarios/<scenario>.py against the running game
    atelier board post|read|thread|task|supervise|retire|wait|status|serve ...   coordinate machine-local agents (docs/AGENT_BOARD.md)
    atelier pr-media push <key> FILE... [--remote R] [--dry-run]   publish PR screenshots/films under refs/pr-media/<key>, outside default clones
    atelier merge <PR> [--source CHECKOUT]   retain existing build artifacts locally, then merge a reviewed PR
    atelier lint                       public-repository rules: no secrets, no personal paths, no game names in the platform
"""
import argparse, datetime, importlib.util, os, re, shutil, subprocess, sys
from pathlib import Path

from . import manifest, paths
from .build import Context, build, list_steps
from .play_limits import GAME_GIB, GAME_MAX_GIB


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


def game_limit(memory_gib=None):
    limit = GAME_GIB if memory_gib is None else memory_gib
    if not GAME_GIB <= limit <= GAME_MAX_GIB:
        raise SystemExit(f'--memory-gib must be {GAME_GIB:g} to {GAME_MAX_GIB:g}')
    return limit


def play(game, profile, settings, extra, memory_gib=None):
    limit = game_limit(memory_gib)
    ctx = Context(game)
    from .build_snapshot import require_complete
    require_complete(ctx.out, game=game)
    data = manifest.game(game)
    profiles = data.get('play', {})
    if profile not in profiles:
        raise SystemExit(f'no play profile {profile!r}; {game} has {sorted(profiles)}')
    spec = profiles[profile]
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    folder = ctx.out / 'logs' / f'play-{profile}-{stamp}'
    folder.mkdir(parents=True, exist_ok=True)
    if 'script' in spec:   # a game-specific launcher (for example the desktop profile)
        script_args = [a.replace('{run}', str(folder)).replace('{memory_gib}', f'{limit:g}')
                       for a in spec.get('args', [])]
        command = [sys.executable, str(ctx.game_dir / spec['script']), *script_args, *extra]
        if settings:
            command += ['--settings', settings]
        return subprocess.call(command, env=ctx.env())
    args = [a.replace('{run}', str(folder)) for a in spec.get('args', [])]   # {run}: this run's log folder (review output)
    command = [str(ctx.unreal_app), str(ctx.uproject), *args, '-stdout', f'-abslog={folder / "game.log"}', *extra]
    if settings:
        command.append(f'-set={settings}')
    from atelier.harness.safety import guarded
    print(f'playing {game} ({profile}); log {folder / "game.log"}')
    if limit != GAME_GIB:
        print(f'memory guard limit {limit:g} GiB for this session')
    return guarded.run(command, folder, timeout=float(spec.get('timeout', 0)), purpose=f'atelier play {game}', env=ctx.env(),
                       kind='game', limit_gib=limit)


# (pattern, what, literals): a pattern is searched only in text holding one of its literals, which keeps large data quick
PERSONAL = [
    (re.compile(r'/Users/(?!Shared/)[A-Za-z0-9._-]+/'), 'a home-directory path', ('/Users/',)),
    (re.compile(r'\b[a-z0-9-]+\.tail[0-9a-f]{4,}\.ts\.net\b'), 'a tailnet hostname', ('.ts.net',)),
    (re.compile(r'\b(sk-[A-Za-z0-9_-]{20,}|tsk_[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|xox[bp]-[A-Za-z0-9-]{10,})'), 'an API token',
     ('sk-', 'tsk_', 'ghp_', 'xoxb-', 'xoxp-')),
    (re.compile(r'SecurityToken=[A-Za-z0-9]{8,}'), 'an engine security token', ('SecurityToken=',)),
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
        for pattern, what, literals in PERSONAL:
            if not any(literal in text for literal in literals):
                continue
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
    from atelier.harness import board
    board.configure(sub)
    from . import cache_admin
    cache_admin.configure(sub)
    p = sub.add_parser('new'); p.add_argument('game'); p.add_argument('--title')
    p = sub.add_parser('doctor'); p.add_argument('game')
    p = sub.add_parser('setup'); p.add_argument('--headless', action='store_true')
    p.add_argument('--workers', type=int, default=3, help='headless compiler parallelism (default: 3)')
    p = sub.add_parser('pool'); p.add_argument('action', choices=['publish', 'restore', 'status', 'abandon'])
    p.add_argument('game'); p.add_argument('step')
    p = sub.add_parser('fetch'); p.add_argument('game')
    from atelier.harness import capacity_cli
    capacity_cli.configure(sub)
    p = sub.add_parser('build'); p.add_argument('game'); p.add_argument('steps', nargs='*')
    p.add_argument('--list', action='store_true'); p.add_argument('--force', action='store_true')
    p.add_argument('--rebuild-reason', help='record why an unavoidable cold or expensive rebuild is necessary')
    p.add_argument('--rebuild-touched', action='store_true',
                   help='rebuild selected touched certificates; preserve proven current steps and caches')
    p.add_argument('--max-heavy-commands', type=int, metavar='N',
                   help='run at most N heavy commands, then yield before the next one (exit 75)')
    p.add_argument('--dry-run', '--plan', action='store_true', help='read-only build decisions')
    p.add_argument('--explain', action='store_true', help='plan with the reason for each rebuild')
    p.add_argument('--json', action='store_true', help='print the selected read-only report as JSON')
    p.add_argument('--timings', action='store_true', help='read historical execution and phase timings without checking inputs')
    p.add_argument('--changes', action='store_true', help='read changes between the last certified product inventories')
    p.add_argument('--ddc', action='store_true', help='read historical DDC configuration and counts from retained Unreal logs')
    p.add_argument('--cook-mode', choices=('modern-full', 'modern-incremental'),
                   help='experimental UE5.8 package cook; --force recooks packages only')
    p.add_argument('--cook-reason', help='measurement reason required for experimental --force')
    p.add_argument('--cook-memory-gib', type=float, help='explicit cook-only guard ceiling, 10 to 24 GiB; full reservation required')
    p.add_argument('--recover-cook', metavar='ATTEMPT_ID', help='retry only certification of a positively completed same-checkout cook')
    p.add_argument('--record-cook-recovery', action='store_true', help='opt in before cooking to retain complete local recovery evidence (additional input inventory cost)')
    p.add_argument('--verify', action='store_true', help='read all named-product bytes instead of using the local hash index')
    p.add_argument('--touch', action='store_true', help='record the steps as built without running them (after a recipe refactor)')
    p = sub.add_parser('play'); p.add_argument('game'); p.add_argument('--profile', default='play')
    p.add_argument('--set', default='', help='settings overrides, key=value;key=value')
    p.add_argument('--memory-gib', type=float, default=None,
                   help='memory guard limit for this session, 10 (the default) to 24 GiB; full broker admission still required')
    p.add_argument('extra', nargs='*', help='Unreal arguments, after --')
    p = sub.add_parser('playtest'); p.add_argument('game')
    p.add_argument('--tag', help='this release instead of the latest')
    p.add_argument('--download-only', action='store_true', help='download and unpack it, without playing')
    p.add_argument('--memory-gib', type=float, default=None, help='memory guard limit, as for play')
    p.add_argument('extra', nargs='*', help='launcher arguments, after --')
    p = sub.add_parser('release', help='publish an existing independently verified package')
    p.add_argument('action', choices=['publish']); p.add_argument('game'); p.add_argument('package')
    p.add_argument('--tag', required=True, help='new tag under the game release prefix, or the same tag to resume')
    p.add_argument('--verification', required=True, help='existing native package verification report')
    p.add_argument('--source', help='clean package source checkout (default: this repository)')
    p.add_argument('--title', help='release title (default: tag)')
    p.add_argument('--notes-file', help='release notes; must be identical when resuming')
    p.add_argument('--part-mib', type=int, default=200, help='upload part size, 1 to 1900 MiB (default: 200)')
    p.add_argument('--workers', type=int, default=6, help='concurrent uploads, 1 to 6 (default: 6)')
    p.add_argument('--prerelease', action='store_true', help='publish a prerelease instead of a normal release')
    p = sub.add_parser('merge', help='retain existing build artifacts locally, then squash-merge a reviewed PR')
    p.add_argument('pr', help='PR number or GitHub URL')
    p.add_argument('--source', help='completed producer checkout (default: this repository)')
    p = sub.add_parser('stream'); p.add_argument('game'); p.add_argument('action', choices=['start', 'stop', 'status', 'build-web'])
    p.add_argument('--local', action='store_true', help='this machine only: no Tailscale Serve')
    p.add_argument('--install', action='store_true', help='build-web: reinstall platform/web packages (npm ci)')
    p = sub.add_parser('pr-media', help='publish PR screenshots and films under refs/pr-media/<key>')
    p.add_argument('action', choices=['push']); p.add_argument('key', help='the PR number, or a slug before the PR exists')
    p.add_argument('files', nargs='+', metavar='FILE')
    p.add_argument('--remote', default='origin', help='GitHub remote to push to (default: origin)')
    p.add_argument('--dry-run', action='store_true', help='read the remote ref and build the commit locally, but print its links without pushing')
    p = sub.add_parser('lint'); p.add_argument('--staged', action='store_true', help='check the staged files only')
    p = sub.add_parser('contracts', help='check code contract syntax and owners')
    p.add_argument('action', choices=['check'])
    p = sub.add_parser('live'); p.add_argument('rest', nargs=argparse.REMAINDER)
    p = sub.add_parser('qa'); p.add_argument('game'); p.add_argument('scenario'); p.add_argument('rest', nargs=argparse.REMAINDER)
    return parser


def parse_args(argv=None):
    """For `play` and `playtest`, everything after the first `--` goes to the game as is, wherever the options sit.
    argparse alone rejects it when an option follows the game (`play <game> --profile P -- -RenderOffscreen`): `extra`
    has already been matched, empty, right after the game."""
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] in (['play'], ['playtest']) and '--' in argv:
        cut = argv.index('--')
        args = make_parser().parse_args(argv[:cut])
        args.extra += argv[cut + 1:]
        return args
    return make_parser().parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.command == 'board':
        from atelier.harness import board
        return board.main(args)
    if args.command == 'new':
        from . import new
        return new.main(args.game, args.title)
    if args.command == 'doctor':
        return doctor(args.game)
    if args.command == 'setup':
        from . import setup
        return setup.main(args.headless, args.workers)
    if args.command == 'pool':
        from . import artifact_pool
        return artifact_pool.main(args.action, args.game, args.step)
    if args.command == 'cache':
        from . import cache_admin
        return cache_admin.main(args)
    if args.command == 'fetch':
        return fetch(args.game)
    if args.command == 'capacity':
        from atelier.harness import capacity_cli
        return capacity_cli.main(args)
    if args.command == 'build':
        cook_memory = {}
        if args.cook_memory_gib is not None:
            from .build import cook_memory_limit
            try:
                cook_memory_limit(args.cook_memory_gib, args.steps)
            except ValueError as error:
                raise SystemExit(str(error)) from None
            if args.list or args.ddc or args.changes or args.timings or args.touch or args.recover_cook is not None:
                raise SystemExit('--cook-memory-gib requires cook/package execution or a read-only plan')
            cook_memory['cook_memory_gib'] = args.cook_memory_gib
        if args.rebuild_touched and (args.force or args.touch or args.recover_cook is not None
                                    or args.record_cook_recovery or args.list or args.ddc or args.changes or args.timings):
            raise SystemExit('--rebuild-touched requires a separate build or plan, without force/touch/cook recovery')
        if args.record_cook_recovery:
            if (args.steps not in (['unreal.cook'], ['unreal.package']) or args.list or args.ddc or args.changes
                    or args.timings or args.dry_run or args.explain or args.json or args.touch
                    or args.cook_mode is not None or args.recover_cook is not None):
                raise SystemExit('--record-cook-recovery requires ordinary unreal.cook or unreal.package execution')
        if args.recover_cook is not None:
            if (args.steps not in (['unreal.cook'], ['unreal.package']) or args.list or args.ddc or args.changes
                    or args.timings or args.dry_run or args.explain or args.json or args.force or args.touch
                    or args.cook_mode is not None or args.max_heavy_commands is not None):
                raise SystemExit('--recover-cook requires unreal.cook or unreal.package execution without force/touch/plan/experimental/budget flags')
        if args.max_heavy_commands is not None:
            if args.max_heavy_commands < 1:
                raise SystemExit('--max-heavy-commands must be a positive integer')
            if args.list or args.ddc or args.changes or args.timings or args.dry_run or args.explain or args.json or args.touch:
                raise SystemExit('--max-heavy-commands requires build execution')
        experimental = {'cook_mode': args.cook_mode, 'cook_reason': args.cook_reason} if args.cook_mode is not None else {}
        if args.cook_reason is not None and not experimental:
            raise SystemExit('--cook-reason requires --cook-mode')
        if experimental and (args.list or args.ddc or args.changes or args.timings or args.touch):
            raise SystemExit('--cook-mode combines only with execution or an existing build plan')
        if args.ddc:
            if args.timings or args.changes or args.list or args.dry_run or args.explain or args.force or args.touch or args.verify:
                raise SystemExit('--ddc combines only with step selection and --json')
            from .build_ddc import show
            return show(args.game, args.steps, as_json=args.json)
        if args.changes:
            if args.timings or args.list or args.dry_run or args.explain or args.force or args.touch or args.verify:
                raise SystemExit('--changes combines only with step selection and --json')
            from .build_changes import show
            return show(args.game, args.steps, as_json=args.json)
        if args.timings:
            if args.list or args.dry_run or args.explain or args.force or args.touch or args.verify:
                raise SystemExit('--timings combines only with step selection and --json')
            from .build_timings import show
            return show(args.game, args.steps, as_json=args.json)
        if args.list:
            list_steps(args.game)
            return 0
        if args.dry_run or args.explain or args.json:
            if args.touch:
                raise SystemExit('--touch cannot be combined with a read-only plan')
            from .build_plan import show
            return show(args.game, args.steps, force=args.force, explain=args.explain, as_json=args.json, verify=args.verify,
                        **({'rebuild_touched': True} if args.rebuild_touched else {}), **experimental, **cook_memory)
        bounded = {'max_heavy_commands': args.max_heavy_commands} if args.max_heavy_commands is not None else {}
        if args.rebuild_reason is not None:
            from .build_checkpoints import reason
            bounded['rebuild_reason'] = reason(args.rebuild_reason)
        if args.recover_cook is not None:
            bounded['recover_cook'] = args.recover_cook
        if args.record_cook_recovery:
            bounded['record_cook_recovery'] = True
        if args.rebuild_touched:
            bounded['rebuild_touched'] = True
        return build(args.game, args.steps, force=args.force, dry=args.dry_run, touch=args.touch, verify=args.verify,
                     **experimental, **bounded, **cook_memory)
    if args.command == 'play':
        return play(args.game, args.profile, args.set, args.extra, args.memory_gib)
    if args.command == 'playtest':
        from . import playtest
        return playtest.main(args.game, args.tag, args.download_only, args.extra, game_limit(args.memory_gib))
    if args.command == 'release':
        from . import release
        return release.main(args.game, args.package, tag=args.tag, verification=args.verification,
                            title=args.title, notes_file=args.notes_file, source=args.source,
                            part_mib=args.part_mib, workers=args.workers, prerelease=args.prerelease)
    if args.command == 'merge':
        from . import pr_merge
        return pr_merge.merge(args.pr, source=args.source)
    if args.command == 'stream':
        from . import stream
        return stream.main(args.game, args.action, local=args.local, install=args.install)
    if args.command == 'pr-media':
        from . import pr_media
        return pr_media.push(args.key, args.files, remote=args.remote, dry_run=args.dry_run)
    if args.command == 'lint':
        return lint(args.staged)
    if args.command == 'contracts':
        from . import contracts
        return contracts.check()
    if args.command == 'qa':
        from .build_snapshot import require_complete
        require_complete(paths.build_root() / args.game, game=args.game)
        script = paths.game_dir(args.game) / 'scenarios' / f'{args.scenario}.py'
        if not script.exists():
            raise SystemExit(f'no scenario {script}')
        return subprocess.call([sys.executable, str(script), *args.rest])
    if args.command == 'live':
        from . import live
        return live.main(args.rest)


if __name__ == '__main__':
    sys.exit(main())
