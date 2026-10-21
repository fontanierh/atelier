"""Certify a completed cook and retain its app as the input to download assembly."""
import hashlib
import json
import os
import shutil
import time


def archived_app(root):
    apps = sorted((root / 'archive').glob('*/*.app'))
    if len(apps) != 1:
        raise RuntimeError(f'expected one cooked app, found {len(apps)}')
    app = apps[0]
    data = list(app.glob('Contents/UE/*/Content/Data'))
    if not data or any(not (data[0] / rel).is_file() for rel in ('world.json', 'heightmap.bin', 'map/map.json')):
        raise RuntimeError('the cooked app lacks staged runtime data')
    if not (app / 'Contents/MacOS' / app.stem).is_file():
        raise RuntimeError('the cooked app lacks its executable')
    return app


def inventory(app, *, hashes=False, log=None):
    """File identity for quick freshness checks; content hashes for the cook and independent copy proof."""
    result, spoken = {}, time.monotonic()
    for path in sorted(app.rglob('*')):
        stat = path.lstat()
        entry = dict(mode=stat.st_mode & 0o777, mtime_ns=stat.st_mtime_ns)
        if path.is_symlink():
            entry['link'] = os.readlink(path)
        elif path.is_file():
            entry['bytes'] = stat.st_size
            if hashes:
                digest = hashlib.sha256()
                with path.open('rb') as source:
                    for chunk in iter(lambda: source.read(1 << 20), b''):
                        digest.update(chunk)
                        if log is not None and time.monotonic() - spoken >= 25:
                            line = f'cook inventory: hashing {path.relative_to(app)}, {len(result)} files complete'
                            log.write(line + '\n'); log.flush(); print(line, flush=True)
                            spoken = time.monotonic()
                entry['sha256'] = digest.hexdigest()
        else:
            continue
        result[str(path.relative_to(app))] = entry
    return result


def read_receipt(root):
    receipt = json.loads((root / 'cook.json').read_text())
    if (receipt['schema'] != 1 or not receipt['files'] or not isinstance(receipt['revision'], str)
            or len(receipt['revision']) != 40 or not isinstance(receipt['engine'], dict)
            or not isinstance(receipt['fingerprint'], str) or not isinstance(receipt['source_dirty'], bool)):
        raise ValueError('invalid cook receipt')
    app = archived_app(root)
    expected = {name: {k: v for k, v in entry.items() if k != 'sha256'} for name, entry in receipt['files'].items()}
    if receipt['app'] != str(app.relative_to(root)) or inventory(app) != expected:
        raise ValueError('cooked app changed or is incomplete')
    return receipt


def cook_present(root):
    try:
        read_receipt(root)
        return True
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError):
        return False


def source_snapshot(ctx):
    from atelier.build import fingerprint, load_recipe, result
    from atelier.provenance import head, status
    steps = {step.name: step for step in load_recipe(ctx.game).steps(ctx)}
    cook = steps['unreal.cook']
    stamps = {name: json.loads((ctx.stamps / (name + '.json')).read_text()) for name in cook.needs}
    done = {name: result(steps[name], stamp['fingerprint'], stamp) for name, stamp in stamps.items()}
    revision, dirty = head(), bool(status(untracked=False))
    engine = json.loads((ctx.unreal_root / 'Engine/Build/Build.version').read_text())
    return dict(revision=revision, source_dirty=dirty, fingerprint=fingerprint(cook, done), engine=engine)


def recovery_config_inputs(ctx):
    """Require generated UBT defaults before freezing their consumed bytes for recovery."""
    from pathlib import Path
    from atelier.setup import headless_user_dir
    headless = os.environ.get('UE_HEADLESS_USER_DIR') or headless_user_dir(ctx.unreal_root)
    if not headless:
        raise RuntimeError('Cook recovery recording requires the supported headless UAT configuration')
    config = Path('Unreal Engine/UnrealBuildTool/BuildConfiguration.xml')
    project = ctx.game_dir / 'unreal/Saved/UnrealBuildTool/BuildConfiguration.xml'
    engine = ctx.unreal_root / 'Engine/Saved/UnrealBuildTool/BuildConfiguration.xml'
    defaults = [project, Path.home() / 'Library/Application Support' / config]
    if not (ctx.unreal_root / 'Engine/Build/InstalledBuild.txt').is_file():
        defaults.append(engine)
    if any(not path.is_file() for path in defaults):
        raise RuntimeError('Cook recovery needs existing UBT default XML files; run an ordinary nonrecording cook first. '
                           'No recording cook was started.')
    return [Path(headless) / config, Path(headless) / 'UnrealEngine/UnrealBuildTool/BuildConfiguration.xml',
            project, engine,
            ctx.unreal_root / 'Engine/Restricted/NotForLicensees/Programs/UnrealBuildTool/BuildConfiguration.xml',
            *(base / config for base in (Path.home() / '.config', Path.home() / '.local/share',
              Path.home() / 'Library/Application Support', Path('/usr/share'), Path('/Library/Application Support')))]


def recovery_inputs(ctx):
    """Native bytes consumed by UAT, outside the declared source/prerequisite identities.

    Game-target Binaries/Intermediate are UAT outputs and are deliberately not frozen. The
    precompiled editor modules, Content (including Data), engine installation and selected SDK
    are inputs. This conservative local proof has no cross-checkout reuse contract.
    """
    from pathlib import Path
    from atelier import paths
    from atelier.build_cook_recovery import NativeCookInputs
    recovery_default_policy(ctx)
    configurations = recovery_config_inputs(ctx)
    dotnet = recovery_dotnet_input(ctx)
    selection = recovery_tool_selection()
    sdkroot = recovery_sdkroot()
    selection['environment_sdkroot'] = str(sdkroot) if sdkroot is not None else None
    selection['environment_sdkroot_links'] = recovery_sdkroot_links()
    developer = Path(selection['developer'])
    toolchains = list(map(Path, selection['toolchains']))
    sdks = [Path(sdk['path']) for sdk in selection['sdks'].values()]
    tools = list(map(Path, selection['tools'].values()))
    roots = [ctx.game_dir / 'unreal/Content', ctx.unreal_root / 'Engine/Build',
             ctx.unreal_root / 'Engine/Binaries', ctx.unreal_root / 'Engine/Content',
             ctx.unreal_root / 'Engine/Config', ctx.unreal_root / 'Engine/Shaders', ctx.unreal_root / 'Engine/Source',
             developer.parent, *sdks, *toolchains, *tools,
             ctx.game_dir / 'build.py', Path(__file__), paths.REPO / 'uv.lock']
    roots.extend(configurations)
    if sdkroot is not None:
        roots.append(sdkroot)
    roots.extend([*recovery_shell_hooks(ctx), Path('/System/Library/CoreServices/SystemVersion.plist')])
    # Cook-all can consume engine plugin content/config and prebuilt native modules.
    for plugins in (ctx.unreal_root / 'Engine/Plugins', paths.ENGINE_PLUGINS, ctx.game_dir / 'unreal/Plugins'):
        if plugins.exists():
            selected = ('Content', 'Config', 'Source', 'Resources')
            if plugins == ctx.unreal_root / 'Engine/Plugins':
                selected += ('Binaries',)
            roots.extend(p for p in plugins.rglob('*') if p.name in selected
                         and not any(parent.name in selected for parent in p.relative_to(plugins).parents))
            roots.extend(p for p in plugins.rglob('UnrealEditor*')
                         if p.parent.name == 'Mac' and 'Binaries' in p.relative_to(plugins).parts
                         and p.suffix in ('.dylib', '.modules', '.target'))
            roots.extend(plugins.rglob('*.uplugin'))
    roots.extend(p for p in sorted((ctx.game_dir / 'unreal/Binaries/Mac').glob('UnrealEditor*'))
                 if p.suffix in ('.dylib', '.modules', '.target'))
    roots.append(ctx.game_dir / 'unreal/Binaries/Mac' / (ctx.uproject.stem + 'Editor.target'))
    return NativeCookInputs(roots, [ctx.unreal_root / 'Engine', developer.parent, *sdks, *toolchains,
                                   *([sdkroot] if sdkroot is not None else [])],
                            dict(**selection, dotnet=str(dotnet)), [dotnet])


def recovery_shell_hooks(ctx):
    from pathlib import Path
    return [Path.home() / '.unrealrc', ctx.unreal_root / 'Engine/.unrealrc', Path.home() / '.config/.autosdk']


def recovery_sdkroot():
    """An explicit SDKROOT remains an exact input, including its complete selected SDK bytes."""
    from pathlib import Path
    value = os.environ.get('SDKROOT')
    if value is None:
        return None
    selected = Path(value)
    if not selected.is_absolute() or not selected.is_dir():
        raise RuntimeError('Cook recovery needs SDKROOT to select an existing absolute .sdk directory')
    selected = selected.resolve(strict=True)
    if selected.suffix != '.sdk':
        raise RuntimeError('Cook recovery needs SDKROOT to select an existing absolute .sdk directory')
    return selected


def recovery_sdkroot_links():
    """Retain every link in the selected path/target chain, even when its SDK tree is covered."""
    from pathlib import Path
    import stat
    value = os.environ.get('SDKROOT')
    if value is None:
        return {}
    pending, seen, links = [Path(value)], set(), {}
    token = lambda info: [info.st_dev,info.st_ino,info.st_mode,info.st_size,info.st_mtime_ns,info.st_ctime_ns]
    while pending:
        path = pending.pop()
        for part in [*reversed(path.parents),path]:
            if part in seen:
                continue
            seen.add(part)
            info = part.lstat()
            if not stat.S_ISLNK(info.st_mode):
                continue
            if len(links) >= 64:
                raise RuntimeError('Cook recovery SDKROOT selector exceeds 64 links')
            target = os.readlink(part)
            if token(info) != token(part.lstat()):
                raise RuntimeError('Cook recovery SDKROOT link changed during discovery')
            links[str(part)] = dict(identity=token(info),link=target)
            pending.append(Path(os.path.normpath(target if os.path.isabs(target) else part.parent / target)))
    return links


def recovery_default_policy(ctx):
    """Recovery supports default tools only; never source or sanitize unknown launch hooks."""
    names = {'DEVELOPER_DIR', 'TOOLCHAINS', 'BASH_ENV', 'ENV', 'UE-CmdLineArgs',
             'CDPATH', 'IFS', 'BASHOPTS', 'SHELLOPTS', 'POSIXLY_CORRECT',
             'UE_DOTNET_DIR', 'UE_USE_SYSTEM_DOTNET', 'UE_SDKS_ROOT', 'MSBuildSDKsPath', 'MSBuildExtensionsPath'}
    unsupported = sorted(name for name in os.environ if name in names
                         or name.startswith(('UE_AUTOSDK_', 'DOTNET_', 'COREHOST_', 'CORECLR_', 'COMPlus_',
                                             'DYLD_', 'MSBUILD', 'NUGET_', 'BASH_FUNC_'))
                         or (name.startswith(('UnrealBuildTool_', 'UBT_')) and '__' in name)
                         or name.endswith(('AutoSDKSetup', 'ManualSDKSetup')))
    if unsupported:
        raise RuntimeError('Cook recovery supports default launch/tool inputs only; unsupported environment names: '
                           + ', '.join(unsupported))
    if any(path.exists() or path.is_symlink() for path in recovery_shell_hooks(ctx)):
        raise RuntimeError('Cook recovery does not support .unrealrc or .autosdk startup hooks')
    recovery_sdkroot()  # Reject unsupported selectors before removing an earlier archive.


def recovery_dotnet_input(ctx):
    """The UE 5.8 SetupDotnet script's bundled default; alternative runtimes are refused."""
    import stat
    architecture = 'arm64' if os.uname().machine == 'arm64' else 'x64'
    executable = ctx.unreal_root / 'Engine/Binaries/ThirdParty/DotNet/10.0' / ('mac-' + architecture) / 'dotnet'
    if executable.is_symlink() or not executable.is_file() or not executable.stat().st_mode & stat.S_IXUSR:
        raise RuntimeError('Cook recovery requires the already executable bundled default dotnet runtime')
    return executable.resolve(strict=True)


def recovery_tool_selection():
    """Pin actual default Xcode and both Metal SDK selections, including downloaded tool resources."""
    import subprocess
    from pathlib import Path
    started = time.monotonic()
    def output(argv):
        remaining = 30 - (time.monotonic() - started)
        if remaining <= 0:
            raise RuntimeError('Cook recovery tool selection exceeded 30 seconds')
        return subprocess.check_output(argv, text=True, timeout=min(10, remaining)).strip()
    def selected(argv):
        return Path(output(argv)).resolve(strict=True)
    selectors = {}
    commands = {name: '/usr/bin/' + name for name in ('xcode-select', 'xcrun', 'uname', 'which', 'dirname', 'env')}
    commands.update({name: '/bin/' + name for name in ('realpath', 'chmod', 'bash', 'sh')})
    for name, system_path in commands.items():
        expected = Path(system_path)
        found = shutil.which(name)
        if not found or Path(found).resolve(strict=True) != expected.resolve(strict=True):
            raise RuntimeError('Cook recovery refuses a PATH-shadowed tool selector: ' + name)
        selectors[name] = str(expected.resolve(strict=True))
    developer = selected(['/usr/bin/xcode-select', '-p'])
    if developer.name != 'Developer' or not (developer / 'Toolchains').is_dir():
        raise RuntimeError('Cook recovery requires a complete default Xcode developer installation')
    sdks, toolchains = {}, set()
    for sdk in ('macosx', 'iphoneos'):
        sdk_path = selected(['/usr/bin/xcrun', '--sdk', sdk, '--show-sdk-path'])
        if sdk == 'macosx':
            alias = developer / 'Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
            if alias.resolve(strict=True) != sdk_path:
                raise RuntimeError('Cook recovery cannot reconcile the UBT and xcrun macOS SDK selections')
        chosen = {}
        for tool in ('metal', 'metal-ar', 'metallib', 'metal-pack', 'metal-strip'):
            executable = selected(['/usr/bin/xcrun', '--sdk', sdk, '--find', tool])
            if not executable.is_file() or not os.access(executable, os.X_OK):
                raise RuntimeError('Cook recovery requires an executable selected Metal tool')
            owner = next((parent for parent in executable.parents if parent.suffix == '.xctoolchain'), None)
            if owner is None or not owner.is_dir():
                raise RuntimeError('Cook recovery cannot prove the selected Metal tool resource owner')
            toolchains.add(owner)
            chosen[tool] = str(executable)
            if tool == 'metal':
                search = ['/usr/bin/xcrun', '--sdk', sdk, 'metal', '--print-search-dirs']
                lines = [line[len('libraries: ='):].strip() for line in output(search).splitlines()
                         if line.startswith('libraries: =')]
                if len(lines) != 1:
                    raise RuntimeError('Cook recovery cannot resolve the selected Metal library resource')
                library = Path(lines[0]).resolve(strict=True)
                if not library.is_dir() or not library.is_relative_to(owner):
                    raise RuntimeError('Cook recovery cannot prove the selected Metal library resource owner')
                chosen['library'] = str(library)
        sdks[sdk] = dict(path=str(sdk_path), metal=chosen)
    tools = dict(selectors)
    for name in ('xcodebuild', 'ibtool', 'actool', 'codesign', 'ditto', 'strip', 'install_name_tool', 'dsymutil'):
        tools[name] = str(selected(['/usr/bin/xcrun', '--find', name]))
    return dict(developer=str(developer), sdks=sdks, toolchains=sorted(map(str, toolchains)), tools=tools)


def prepare(ctx, log):
    if getattr(ctx, 'record_cook_recovery', False):
        recovery_default_policy(ctx)
        recovery_config_inputs(ctx)  # Refuse unprimed UAT defaults before deleting an earlier archive.
        recovery_dotnet_input(ctx)
        recovery_tool_selection()
    root = ctx.out / 'package'
    root.mkdir(parents=True, exist_ok=True)
    (root / 'cook.json').unlink(missing_ok=True)
    ctx.cook_source = source_snapshot(ctx)
    shutil.rmtree(root / 'archive', ignore_errors=True)
    log.write(f'cook source {ctx.cook_source["revision"]}\n'); log.flush()


def certify_restored(ctx, log):
    """@cc [owner:fontanierh,label:correctness] restored-cook-payload-certification
    Reused payload certification MUST preserve the archive bytes and record receiving source
    provenance only after source and complete archive inventories are stable. It MUST NOT run
    destructive cook preparation or claim native parity from a successful cache transfer.
    """
    ctx.cook_source = source_snapshot(ctx)
    finish(ctx, log)


def finish(ctx, log):
    if ctx.cook_source != source_snapshot(ctx):
        raise RuntimeError('source or prerequisite stamps changed during the cook; no receipt written')
    root = ctx.out / 'package'
    app = archived_app(root)
    files = inventory(app, hashes=True, log=log)
    if files != inventory(app, hashes=True, log=log):
        raise RuntimeError('cooked app changed during certification; no receipt written')
    if ctx.cook_source != source_snapshot(ctx):
        raise RuntimeError('cook inputs changed during certification; no receipt written')
    receipt = dict(schema=1, app=str(app.relative_to(root)), files=files, **ctx.cook_source)
    candidate = root / '.cook.json.tmp'
    candidate.write_text(json.dumps(receipt, indent=2) + '\n')
    candidate.replace(root / 'cook.json')
    log.write(f'cook certified: {len(files)} files\n'); log.flush()


def verify_copy(app, receipt, log):
    # ditto may recreate a symlink's timestamp. Its target, permissions and all file contents must match.
    identity = lambda entries: {name: {k: v for k, v in entry.items() if k != 'mtime_ns'} for name, entry in entries.items()}
    if identity(inventory(app, hashes=True, log=log)) != identity(receipt['files']):
        raise RuntimeError('download app differs from the certified cook')
