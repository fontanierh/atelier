"""Fixed native TOOL routes under the controller's existing whole-tree guard.

No admission, scheduler, arbitrary argv or result authority lives here. Frozen
recipe roots are copied with recipe_job; the controller validates and publishes
only after its normal guard has positively completed cleanup.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import selectors
import re
import shutil
import stat
import subprocess
import sys
import time
import zipfile


def _sibling(name):
    spec = importlib.util.spec_from_file_location('atelier_native_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


protocol = _sibling('protocol')
recipe_job = _sibling('recipe_job')
ops = _sibling('unreal_tool_ops')
WORKER_VERSION = 'atelier-native-tool-job-1'
KINDS = frozenset(('unreal.compile', 'unreal.game', 'unreal.cook.produce', 'unreal.package', 'package.archive'))


class Refused(ValueError):
    pass


def _path(view, name):
    return view / recipe_job.relative(name)


def _digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _tree(root):
    """Nofollow complete product inventory, retaining only internal app symlinks."""
    rows = []
    def visit(path):
        info = path.lstat()
        name = path.relative_to(root).as_posix()
        if stat.S_ISLNK(info.st_mode):
            target = os.readlink(path)
            if Path(target).is_absolute() or not path.resolve(strict=True).is_relative_to(root.resolve()):
                raise Refused('native product link escapes its owned root')
            rows.append((name, 'link', target))
        elif stat.S_ISDIR(info.st_mode):
            rows.append((name, 'directory', stat.S_IMODE(info.st_mode)))
            for child in sorted(path.iterdir()):
                visit(child)
        elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
            rows.append((name, 'file', _digest(path), stat.S_IMODE(info.st_mode)))
        else:
            raise Refused('native product contains a special file or hard link')
    visit(root)
    return rows


def receipt_files(engine, project, target, configuration, kind, *, owned_root=None):
    owned_root = owned_root or project.parent
    if kind == 'editor':
        files = set(ops.compile_products(engine, project, target, owned_roots=[owned_root],
                                        kind=kind, configuration=configuration)['files'])
        for binary in tuple(files):
            if binary.suffix != '.dylib' or not binary.name.startswith('libUnrealEditor-'):
                continue
            modules = binary.parent / 'UnrealEditor.modules'
            data = json.loads(modules.read_bytes())
            if (not data.get('BuildId') or not isinstance(data.get('Modules'), dict)
                    or binary.name not in data['Modules'].values()
                    or any(not isinstance(name, str) or Path(name).name != name
                           or modules.parent / name not in files for name in data['Modules'].values())):
                raise Refused('project plugin module map differs from complete receipt products')
            files.add(modules)
        return tuple(sorted(files))
    receipt = project.parent / 'Binaries/Mac' / (target + '.target')
    value = json.loads(receipt.read_bytes())
    if (value.get('TargetName'), value.get('Platform'), value.get('Configuration')) != (target, 'Mac', configuration):
        raise Refused('game receipt target/platform/configuration differs')
    files = {receipt}
    products = value.get('BuildProducts')
    if not isinstance(products, list) or not products:
        raise Refused('game receipt lacks complete products')
    for row in [*products, *value.get('RuntimeDependencies', [])]:
        path = ops._receipt_path(row['Path'], project=project.parent, engine=engine / 'Engine', receipt=receipt)
        if ops._inside(path, (engine / 'Engine',)):
            if not path.exists():
                raise Refused('installed runtime product is absent')
            continue
        if not ops._inside(path, (owned_root,)):
            raise Refused('game receipt product is outside the owned project')
        _tree(path)
        if row in products:
            files.add(path)
    return tuple(sorted(files))


def _covers(roots, paths):
    if any(not any(path == root or path.is_relative_to(root) for root in roots) for path in paths):
        raise Refused('declared outputs omit receipt-listed project products')


def zip_argv(root, destination):
    return ['/usr/bin/ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', str(root), str(destination)]


def restore_mac_zip(source, destination, run):
    """Restore one frozen native ZIP into fresh owned staging, preserving internal links."""
    source, destination = Path(source), Path(destination)
    if os.path.lexists(destination):
        raise Refused('native ZIP destination already exists')
    names, links = set(), set()
    with zipfile.ZipFile(source) as archive:
        members = archive.infolist()
        if not members or len(members) > 1_000_000:
            raise Refused('native ZIP has no bounded complete membership')
        for member in members:
            name = member.filename.rstrip('/')
            recipe_job.relative(name)
            if name in names:
                raise Refused('duplicate native ZIP member')
            names.add(name)
            parts = Path(name).parts
            if parts[0] == '__MACOSX':
                if not ((len(parts) == 1 and member.is_dir())
                        or (len(parts) >= 2 and parts[1] == destination.name)
                        or (len(parts) == 2 and parts[1] == '._' + destination.name)):
                    raise Refused('native ZIP resource fork has another root')
            elif parts[0] != destination.name:
                raise Refused('native ZIP has another root')
            mode = member.external_attr >> 16
            kind = stat.S_IFMT(mode)
            if kind == stat.S_IFLNK:
                if parts[0] == '__MACOSX' or member.file_size > 4096:
                    raise Refused('invalid native ZIP link')
                target = archive.read(member).decode('utf-8')
                resolved = Path(os.path.normpath(str(Path(name).parent / target)))
                if (Path(target).is_absolute() or not target or '\\' in target
                        or not resolved.is_relative_to(destination.name)):
                    raise Refused('native ZIP link escapes its root')
                links.add(name)
            elif kind not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise Refused('native ZIP contains a special file')
        if any(any(parent.as_posix() in links for parent in Path(name).parents) for name in names):
            raise Refused('native ZIP member descends through a link')
    scratch = destination.parent / ('.' + destination.name + '.native-unpack')
    scratch.mkdir(mode=0o700)
    try:
        run(['/usr/bin/ditto', '-x', '-k', str(source), str(scratch)], cwd=scratch)
        root = scratch / destination.name
        if {path.name for path in scratch.iterdir()} != {destination.name}:
            raise Refused('native ZIP extracted unexpected roots')
        _tree(root)
        root.rename(destination)
    finally:
        # Only this fresh, owned extraction scope is removed; caller source is retained.
        shutil.rmtree(scratch)


def restore_native_inputs(recipe, view, run):
    for logical, staged in recipe['paths'].items():
        if staged.endswith('.mac.zip'):
            destination = _path(view, logical)
            source = destination.with_name(destination.name + '.native-input.mac.zip')
            if os.path.lexists(source):
                raise Refused('native ZIP input scratch name is occupied')
            destination.rename(source)
            restore_mac_zip(source, destination, run)
            source.unlink()


def export_outputs(recipe, view, output, run, raw_roots=()):
    """Use ROOT for ordinary roots, regular ditto ZIP payloads for explicit mac-zip roots."""
    for row in recipe['outputs']:
        root, destination = _path(view, row['path']), _path(output, row['file'])
        if row['path'] in raw_roots:
            if not stat.S_ISREG(root.lstat().st_mode):
                raise Refused('native record is not a regular file')
            destination.parent.mkdir(parents=True, exist_ok=True)
            with root.open('rb') as incoming, destination.open('xb') as outgoing:
                shutil.copyfileobj(incoming, outgoing)
        elif row.get('encoding', 'root') == 'root':
            recipe_job.pack_root(root, destination, required=row.get('required', True))
        elif row['encoding'] == 'mac-zip':
            if not root.exists():
                raise Refused('required native archive root is absent')
            before = _tree(root)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                raise Refused('native archive destination exists')
            run(zip_argv(root, destination), cwd=view)
            if _tree(root) != before or not destination.is_file() or not destination.stat().st_size:
                raise Refused('native product changed during archive')
        else:
            raise Refused('unsupported native output encoding')


# This exact builtin body is part of NativeToolBundle's source identity. Requests
# carry execution destinations only; the controller separately seals producer origin.
NATIVE_SOURCE_PREFIX = 'platform/build-v2/unreal/AtelierBuildWorker/'


def native_source_digest(job, job_dir):
    rows = []
    names = set()
    for name in sorted(job['code']):
        if not name.startswith(NATIVE_SOURCE_PREFIX):
            continue
        relative = name[len(NATIVE_SOURCE_PREFIX):]
        if relative == 'AtelierBuildWorker.uplugin' or (relative.startswith('Source/')
                and relative.endswith(('.cs', '.cpp', '.h'))):
            path = job_dir / name
            if path.is_symlink() or not path.is_file():
                raise Refused('native exporter implementation source is missing or linked')
            rows.append(relative + '\0' + _digest(path) + '\n')
            names.add(relative)
    required = {'AtelierBuildWorker.uplugin', 'Source/AtelierBuildWorker/AtelierBuildWorker.Build.cs',
                'Source/AtelierBuildWorker/Private/AtelierBuildWorkerLibrary.cpp',
                'Source/AtelierBuildWorker/Private/AtelierBuildWorkerModule.cpp',
                'Source/AtelierBuildWorker/Private/AtelierZenFinalise.cpp',
                'Source/AtelierBuildWorker/Private/AtelierZenPackage.cpp',
                'Source/AtelierBuildWorker/Public/AtelierBuildWorkerLibrary.h',
                'Source/AtelierBuildWorker/Public/AtelierZenFinalise.h'}
    if not required <= names:
        raise Refused('native source cook must key the complete exporter implementation')
    return hashlib.sha256(''.join(rows).encode()).hexdigest()


EXPORT_SOURCE = """import json, os\nfrom pathlib import Path\nimport unreal\np=Path(os.environ['ATELIER_NATIVE_COOK_EXPORT'])\nc=json.loads(p.read_text())\nactual=json.loads(unreal.AtelierBuildWorkerLibrary.native_context())\nif actual.get('worker_source_digest')!=c['native_source_digest']:\n    raise RuntimeError('native exporter does not match keyed implementation source')\nreports=[]\nfor request in c['requests']:\n    report=json.loads(unreal.AtelierBuildWorkerLibrary.zen_package_request(json.dumps(request,sort_keys=True,separators=(',',':'))))\n    if report.get('status')!='verified':\n        raise RuntimeError('native source cook capture refused: '+str(report))\n    reports.append(report)\nPath(c['report']).write_text(json.dumps(reports,sort_keys=True,separators=(',',':')))\n"""


def persistent_cook_view(view, protected, source_key, state_root):
    if not isinstance(source_key, str) or not re.fullmatch('[a-f0-9]{64}', source_key):
        raise Refused('source-cook requires the controller frozen source key')
    if state_root is None:
        raise Refused('source-cook requires owned persistent Zen execution context')
    state = Path(state_root)
    if not state.is_absolute() or '..' in state.parts or state.resolve() != state:
        raise Refused('persistent Zen scope is not canonical absolute storage')
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    if state.stat().st_uid != os.getuid() or state.stat().st_mode & 0o022:
        raise Refused('persistent Zen scope is not owned storage')
    parent = state / 'projects'
    parent.mkdir(mode=0o700, exist_ok=True)
    if parent.is_symlink():
        raise Refused('persistent Zen project parent is a link')
    scope = parent / source_key
    scope.mkdir(mode=0o700)  # Never overwrite/adopt an interrupted or foreign source view.
    destination = scope / 'view'
    remapped = [str(destination / Path(name).relative_to(view)) for name in protected]
    view.rename(destination)
    return destination, remapped


def cook_argv(engine, project, packages, source_key):
    if (not isinstance(packages, list) or not packages or packages != sorted(set(packages))
            or any(not isinstance(name, str) or not re.fullmatch(r'/(?:[A-Za-z0-9_]+/)+[A-Za-z0-9_]+', name)
                   or name.startswith('/Script/') for name in packages)):
        raise Refused('source-cook requires an exact canonical package roster')
    if not re.fullmatch('[a-f0-9]{64}', source_key):
        raise Refused('source-cook key is not the complete controller input key')
    return [str(engine / 'Engine/Binaries/Mac/UnrealEditor-Cmd'), str(project), '-run=cook',
            '-targetplatform=Mac', '-package=' + '+'.join(packages), '-cooksinglepackagenorefs',
            '-Cook.DependencyTracking=1', '-ZenStore', '-ZenStoreProject=AtelierV2_' + source_key,
            '-unattended', '-nop4', '-nosplash', '-nullrhi', '-stdout', '-FullStdOutLogOutput']


class CookCallbacks:
    def __init__(self, folder, engine, environment):
        self.zen = ops.package_lifecycle(folder, engine, environment)
        self.observer = ops.cook_observer(folder, 'default')

    def line(self, line):
        self.zen.line(line)
        match = re.search(r'Using (\d+) local workers for shader compilation', line)
        if match and int(match[1]) > 3:
            raise Refused('native shader compiler exceeded the three-worker policy')

    def poll(self, pid):
        self.zen.poll(pid)
        self.observer.poll(pid)

    def close(self, success):
        try:
            self.observer.finish(success=success)
        finally:
            self.zen.close()


def semantic_global_data(cooked, destination):
    """@cc [owner:fontanierh,label:correctness] semantic-native-global-output
    Only complete emitted Global shader triples MAY enter the semantic global ROOT.
    Namespace markers, metadata reports, statistics and private paths MUST stay in
    the separate complete transport ROOT. Missing, aliased or ambiguous roles MUST
    refuse before publication; this projection MUST NOT fabricate SDK artifacts.
    """
    cooked, destination = Path(cooked), Path(destination)
    if cooked.is_symlink() or not cooked.is_dir() or os.path.lexists(destination):
        raise Refused('semantic global projection requires an existing cook and fresh output')
    roles = {'ShaderAssetInfo': '.assetinfo.json', 'ShaderArchive': '.ushaderbytecode',
             'ShaderTypeInfo': '.stinfo'}
    formats = {}
    def visit(directory):
        for path in sorted(directory.iterdir()):
            info = path.lstat()
            if stat.S_ISDIR(info.st_mode):
                visit(path)
            elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                if '-Global-' not in path.name:
                    continue
                match = re.fullmatch(r'(ShaderAssetInfo|ShaderArchive|ShaderTypeInfo)-Global-([A-Za-z0-9_]+)(\.assetinfo\.json|\.ushaderbytecode|\.stinfo)', path.name)
                if not match or roles[match[1]] != match[3] or not info.st_size:
                    raise Refused('unknown or empty emitted global shader role')
                group = formats.setdefault(match[2], {})
                if match[1] in group:
                    raise Refused('ambiguous emitted global shader role')
                group[match[1]] = path
            else:
                raise Refused('cook output contains an alias, hard link or special file')
    visit(cooked)
    if not formats or any(set(group) != set(roles) for group in formats.values()):
        raise Refused('stock cooker omitted a complete Global shader archive triple')
    destination.mkdir(mode=0o700)
    content = destination / 'Content'
    content.mkdir()
    for group in formats.values():
        for source in group.values():
            before = source.lstat()
            descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(descriptor, 'rb') as incoming, (content / source.name).open('xb') as outgoing:
                opened = os.fstat(incoming.fileno())
                if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                    raise Refused('global shader artifact changed before projection')
                shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
                after = os.fstat(incoming.fileno())
            named = source.lstat()
            identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
            if identity(before) != identity(after) or identity(after) != identity(named):
                raise Refused('global shader artifact changed during projection')
    return sorted(formats)


def source_cook(params, view, project, engine, source_key, state, job_dir, run, environment, export_project, source_digest):
    packages = params['packages']
    argv = cook_argv(engine, project, packages, source_key)
    record_outputs = params['record_outputs']
    if not isinstance(record_outputs, dict) or set(record_outputs) != set(packages):
        raise Refused('source-cook record outputs differ from the selected package roster')
    declared = {row['path'] for row in params['recipe']['outputs']}
    if (len(set(record_outputs.values())) != len(packages)
            or not set(record_outputs.values()) <= declared or params['cook_root'] not in declared
            or params['cook_root'] in record_outputs.values()):
        raise Refused('source-cook must declare each native CB and complete cook metadata output')
    folder = job_dir / '.recipe-runtime/source-cook'
    folder.mkdir()
    callbacks, success = CookCallbacks(folder, engine, environment), False
    try:
        run(argv, cwd=view, env=environment, lifecycle=callbacks, log_file=folder / 'stdout.log')
        success = True
    finally:
        callbacks.close(success)
    cooked = project.parent / 'Saved/Cooked/Mac'
    marker = cooked / 'ue.projectstore'
    if not marker.is_file() or marker.is_symlink():
        raise Refused('stock cooker did not create its actual Zen lifetime marker')
    records = state / 'records'
    records.mkdir(mode=0o700, exist_ok=True)
    if records.is_symlink():
        raise Refused('native record destination is a link')
    requests = []
    for package in packages:
        suffix = '' if len(packages) == 1 else '-' + hashlib.sha256(package.encode()).hexdigest()
        record = records / (source_key + suffix + '.cb')
        requests.append(dict(version=1, mode='capture', project='AtelierV2_' + source_key, oplog='Mac',
            source_package=package, expected_stored_key='', expected_root_hash='', record_path=str(record),
            project_file=str(project), marker_path=str(marker), input_key=source_key, runtime_project_file=str(export_project)))
    request_file, report_file, script = folder / 'export.json', folder / 'native-report.json', folder / 'export.py'
    request_file.write_text(json.dumps({'requests': requests, 'report': str(report_file), 'native_source_digest': source_digest}, sort_keys=True))
    script.write_text(EXPORT_SOURCE)
    script.chmod(0o444)
    exporting = dict(environment, ATELIER_NATIVE_COOK_EXPORT=str(request_file))
    run([str(engine / 'Engine/Binaries/Mac/UnrealEditor-Cmd'), str(export_project), '-run=pythonscript',
         '-script=' + str(script), '-unattended', '-nop4', '-nosplash', '-nullrhi', '-stdout',
         '-FullStdOutLogOutput'], cwd=view, env=exporting)
    reports = json.loads(report_file.read_bytes())
    if not isinstance(reports, list) or len(reports) != len(requests):
        raise Refused('native source-cook export report is incomplete')
    for request, report in zip(requests, reports):
        if (report.get('version') != 1 or report.get('status') != 'verified'
                or any(report.get(key) != request[key] for key in ('mode', 'project', 'oplog', 'source_package', 'input_key', 'runtime_project_file'))
                or report.get('source_dependency_evaluation') != 'recorded_only'
                or not re.fullmatch('[a-f0-9]{40}', report.get('native_stored_key', ''))
                or not re.fullmatch('[a-f0-9]{40}', report.get('root_hash', ''))
                or report.get('installed_root_hash') != ''
                or not re.fullmatch('[a-f0-9]{40}', report.get('record_io_hash', ''))
                or not re.fullmatch('[a-f0-9]{40}', report.get('request_io_hash', ''))
                or type(report.get('attachments')) is not int or report['attachments'] < 1
                or report.get('native_stored_key') == '0' * 40 or report.get('root_hash') == '0' * 40):
            raise Refused('native source-cook capture report differs from the fixed request')
        record = Path(request['record_path'])
        if not stat.S_ISREG(record.lstat().st_mode) or not record.stat().st_size:
            raise Refused('native source-cook did not retain a complete regular CB record')
        record.chmod(0o444)
        destination = _path(view, record_outputs[request['source_package']])
        with record.open('rb') as incoming, destination.open('xb') as outgoing:
            shutil.copyfileobj(incoming, outgoing)
        report['record_sha256'] = _digest(record)
        report['record_path'], report['project_file'], report['marker_path'] = str(record), str(project), str(marker)
    target = _path(view, params['cook_root'])
    if target != cooked:
        shutil.copytree(cooked, target)
    # This is transport metadata only, never the sealed producer/source proof.
    (target / 'atelier-native-cook.json').write_text(json.dumps({'version': 1, 'source_key': source_key,
                                                               'packages': reports}, sort_keys=True))
    if 'global_data' in params:
        logical = params['global_data']
        if logical not in declared or logical == params['cook_root'] or logical in record_outputs.values():
            raise Refused('semantic global data needs its independent declared output root')
        destination = _path(view, logical)
        if destination == cooked or destination.is_relative_to(cooked) or cooked.is_relative_to(destination):
            raise Refused('semantic global root overlaps complete cook transport')
        semantic_global_data(cooked, destination)
    return tuple(record_outputs.values())


def dispatch(job, job_dir, engine, run, *, source_key=None, zen_state_root=None, export_project=None):
    """@cc [owner:fontanierh,label:correctness;safety] fixed-native-tool-routes
    Only the five fixed version-1 operations MAY dispatch. SDK/interpreter locators
    MUST remain execution context. Compilation MUST use the private frozen project,
    three actions, complete real receipts and declared output coverage. Package MUST
    verify an independently completed exact cooked set and skip build/cook. Source
    cook MUST execute the stock cooker before native CB capture, using controller-only
    complete source-key context and preserving the actual native namespace/marker.
    This worker MUST NOT issue source-currentness certificates or CAS records.
    """
    kind = job['op']['kind']
    if kind not in KINDS or job['op']['version'] != '1':
        raise Refused('unsupported native tool operation')
    params, output = job['params'], job_dir / 'output'
    recipe = params['recipe']
    if recipe['version'] != 1 or output.is_symlink() or not output.is_dir() or any(output.iterdir()):
        raise Refused('native job needs an empty staged output and recipe version 1')
    view, protected, writes = recipe_job.prepare_view(job, job_dir)
    restore_native_inputs(recipe, view, run)
    raw_roots = ()
    if kind == 'unreal.cook.produce':
        if (export_project is None or not Path(export_project).is_absolute() or Path(export_project).suffix != '.uproject'
                or not Path(export_project).is_file() or Path(export_project).is_symlink()):
            raise Refused('source-cook needs the existing owned compiled C3 export project')
        view, protected = persistent_cook_view(view, protected, source_key, zen_state_root)
    frozen_inputs = {name: _tree(Path(name)) for name in protected}
    # Runtime modules are loaded only from the same explicitly frozen source view.
    sys.path[:0] = [str(view / 'platform/studio'), str(view / 'platform/harness'), str(view)]
    project = _path(view, params['project']) if kind != 'package.archive' else None
    target = params.get('target')
    configuration = params.get('configuration', 'Development')
    environment = dict(os.environ)
    environment['TMPDIR'] = str(job_dir / recipe_job.RUNTIME / 'tmp')
    roots = [_path(view, row['path']) for row in recipe['outputs']]
    if kind in ('unreal.compile', 'unreal.game'):
        role = 'editor' if kind == 'unreal.compile' else 'game'
        run(ops.compile_argv(engine, project, target, kind=role, configuration=configuration),
            cwd=view, env=environment)
        _covers(roots, receipt_files(engine, project, target, configuration, role, owned_root=view))
    elif kind == 'unreal.package':
        # Inventory comes from the controller's frozen upstream item, not a writer report.
        inventory = params.get('cooked_files')
        cooked = project.parent / 'Saved/Cooked/Mac'
        archive = _path(view, params['archive'])
        argv = ops.package_argv(engine, project, target, archive, cooked_root=cooked,
                                cooked_files=inventory, configuration=configuration)
        environment = ops.package_environment(engine, environment)
        lifecycle = ops.package_lifecycle(job_dir, engine, environment)
        try:
            run(argv, cwd=view, env=environment, lifecycle=lifecycle)
        finally:
            lifecycle.close()
        ops.verify_cooked_files(cooked, inventory)
    elif kind == 'package.archive':
        # The original archive script/arguments are frozen in the original declaration.
        commands = recipe['commands']
        if len(commands) != 1 or commands[0]['kind'] != 'python':
            raise Refused('package archive requires one declared Python script')
        command = commands[0]
        script = _path(view, command['script'])
        if script.name != 'package_archive.py' or command.get('env'):
            raise Refused('unknown package archive producer')
        if command['script'] not in job['code']:
            raise Refused('archive producer is outside frozen code')
        args = recipe_job._value(command['args'], view)
        run([sys.executable, '-I', '-B', str(script), *map(str, args)], cwd=view, env=environment)
    else:
        raw_roots = source_cook(params, view, project, engine, source_key, Path(zen_state_root), job_dir, run, environment, Path(export_project), native_source_digest(job, job_dir))
    if recipe.get('verify') is not None:
        previous = Path.cwd()
        try:
            os.chdir(view)
            if not recipe_job.bind(recipe['verify'], view)():
                raise Refused('original native producer verification refused outputs')
        finally:
            os.chdir(previous)
    if any(_tree(Path(name)) != rows for name, rows in frozen_inputs.items()):
        raise Refused('native producer changed frozen input bytes or modes')
    export_outputs(recipe, view, output, run, raw_roots)
    return sorted(str(path.relative_to(output)) for path in output.rglob('*') if path.is_file())


class Worker:
    def __init__(self, requests, responses, engine_root, *, source_key=None, zen_state_root=None, export_project=None):
        self.requests, self.responses = requests, responses
        self.engine = Path(engine_root)
        if not self.engine.is_absolute():
            raise Refused('engine locator must be absolute')
        self.active = None
        self.stop = False
        self.source_key, self.zen_state_root, self.export_project = source_key, zen_state_root, export_project

    def send(self, value):
        protocol.write_frame(self.responses, protocol.RESPONSE, value)

    def command(self, argv, *, cwd, env=None, lifecycle=None, log_file=None):
        # No new session/group: all descendants remain owned by the C5 outer guard.
        retained = Path(log_file).open('xb') if log_file is not None else None
        try:
            child = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        except BaseException:
            if retained:
                retained.close()
            raise
        started, spoken, buffered = time.monotonic(), time.monotonic(), b''
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout, selectors.EVENT_READ)
                selector.register(self.requests, selectors.EVENT_READ)
                logs_open = True
                while child.poll() is None or logs_open:
                    for key, _ in selector.select(timeout=1):
                        if key.fileobj is self.requests:
                            request = protocol.read_frame(self.requests, protocol.REQUEST)
                            if request is not None and request['type'] == 'cancel' and request['job_id'] != self.active:
                                continue
                            self.stop = True
                            raise Refused('cancelled by controller' if request else 'controller pipe closed')
                        chunk = os.read(child.stdout.fileno(), 65536)
                        if not chunk:
                            selector.unregister(child.stdout)
                            logs_open = False
                            continue
                        if retained:
                            retained.write(chunk)
                            retained.flush()
                        sys.stderr.buffer.write(chunk)
                        sys.stderr.buffer.flush()
                        if lifecycle:
                            buffered += chunk
                            lines = buffered.split(b'\n')
                            buffered = lines.pop()
                            for line in lines:
                                lifecycle.line(line.decode('utf-8', errors='replace'))
                    if lifecycle:
                        lifecycle.poll(child.pid)
                    if time.monotonic() - spoken >= 25:
                        print(f'native tool running: elapsed={time.monotonic()-started:.0f}s; awaiting tool completion',
                              file=sys.stderr, flush=True)
                        spoken = time.monotonic()
            if child.wait() != 0:
                raise Refused(f'native tool exited {child.returncode}')
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
            child.stdout.close()
            if retained:
                retained.close()

    def serve(self):
        self.send({'type': 'hello', 'worker_version': WORKER_VERSION})
        while not self.stop:
            request = protocol.read_frame(self.requests, protocol.REQUEST)
            if request is None:
                return
            if request['type'] == 'shutdown':
                self.send({'type': 'stopped'})
                return
            if request['type'] != 'run':
                continue
            job = request['job']
            self.active = job['job_id']
            self.send({'type': 'started', 'job_id': self.active})
            try:
                directory = Path(job['job_dir'])
                if not directory.is_absolute() or directory.is_symlink():
                    raise Refused('job directory must be owned absolute staging')
                files = dispatch(job, directory, self.engine, self.command,
                                 source_key=self.source_key, zen_state_root=self.zen_state_root, export_project=self.export_project)
                self.send({'type': 'completed', 'job_id': self.active, 'outputs': {'files': files}})
            except (ValueError, OSError, KeyError, TypeError, RuntimeError) as error:
                self.send({'type': 'failed', 'job_id': self.active,
                           'failure': {'kind': 'cancelled' if self.stop else 'dependency', 'message': str(error)}})
            self.active = None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request-fd', type=int, required=True)
    parser.add_argument('--response-fd', type=int, required=True)
    parser.add_argument('--engine-root', required=True)
    parser.add_argument('--source-key')
    parser.add_argument('--zen-state-root')
    parser.add_argument('--export-project')
    args = parser.parse_args(argv)
    for fd in (args.request_fd, args.response_fd):
        os.set_inheritable(fd, False)
    with os.fdopen(args.request_fd, 'rb', buffering=0) as requests, os.fdopen(args.response_fd, 'wb', buffering=0) as responses:
        Worker(requests, responses, args.engine_root, source_key=args.source_key, zen_state_root=args.zen_state_root, export_project=args.export_project).serve()


if __name__ == '__main__':
    main()
