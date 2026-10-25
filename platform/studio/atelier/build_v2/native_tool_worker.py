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
    changed = False
    for group in ('BuildProducts', 'RuntimeDependencies'):
        for index, row in enumerate(value.get(group, [])):
            raw = row.get('Path') if isinstance(row, dict) else row
            if isinstance(raw, str) and raw.startswith('/') and ops._inside(Path(raw), (owned_root,)):
                portable = '$(ProjectDir)/' + os.path.relpath(raw, project.parent).replace(os.sep, '/')
                if isinstance(row, dict):
                    row['Path'] = portable
                else:
                    value[group][index] = portable
                changed = True
    if changed:
        receipt.write_text(json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n')
    if (value.get('TargetName'), value.get('Platform'), value.get('Configuration')) != (target, 'Mac', configuration):
        raise Refused('game receipt target/platform/configuration differs')
    files = {receipt}
    products = value.get('BuildProducts')
    if not isinstance(products, list) or not products:
        raise Refused('game receipt lacks complete products')
    for row in [*products, *value.get('RuntimeDependencies', [])]:
        path = ops._receipt_path(row['Path'] if isinstance(row, dict) else row, project=project.parent, engine=engine / 'Engine', receipt=receipt)
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


def staged_mac_zip(job, job_dir, slot):
    incoming = [row for row in job['inputs'] if row['name'] == slot]
    if len(incoming) != 1:
        raise Refused('native package requires its actual produced ' + slot + ' Item')
    source = job_dir / recipe_job.relative(incoming[0]['path'])
    archives = sorted(source.rglob('*.mac.zip')) if source.is_dir() else [source]
    if len(archives) != 1 or not archives[0].name.endswith('.mac.zip'):
        raise Refused(slot + ' Item must contain one complete Mac binary archive')
    return archives[0]


def package_project_view(job, job_dir, view, project, run):
    """Use independent game binaries for UAT while retaining the editor input for finalisation."""
    archive = staged_mac_zip(job, job_dir, 'game')
    destination = job_dir / '.recipe-runtime/package-view'
    shutil.copytree(view, destination, symlinks=True)
    _tree(destination)
    packaging_project = destination / project.relative_to(view)
    binaries = packaging_project.parent / 'Binaries/Mac'
    if binaries.exists():
        shutil.rmtree(binaries)  # Only the new independent package-view copy.
    restore_mac_zip(archive, binaries, run)
    return destination, packaging_project


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


def cook_argv(engine, project, packages, source_key, *, global_data=False):
    if (not isinstance(packages, list) or not packages or packages != sorted(set(packages))
            or any(not isinstance(name, str) or not re.fullmatch(r'/(?:[A-Za-z0-9_]+/)+[A-Za-z0-9_]+', name)
                   or name.startswith('/Script/') for name in packages)):
        raise Refused('source-cook requires an exact canonical package roster')
    if not re.fullmatch('[a-f0-9]{64}', source_key):
        raise Refused('source-cook key is not the complete controller input key')
    selection = (['-NoDefaultMaps', '-NoGameAlwaysCook', '-SkipHardReferences', '-SkipSoftReferences']
                 if global_data else ['-cooksinglepackagenorefs'])
    shader_settings = ['-ini:Game:[/Script/UnrealEd.ProjectPackagingSettings]:bShareMaterialShaderCode=True',
                       '-ini:Game:[/Script/UnrealEd.ProjectPackagingSettings]:bSharedMaterialNativeLibraries=True']
    return [str(engine / 'Engine/Binaries/Mac/UnrealEditor-Cmd'), str(project), '-run=cook',
            '-targetplatform=Mac', '-package=' + '+'.join(packages), *selection, *shader_settings,
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


def semantic_global_data(cooked, destination, project_name, *, engine_root=None, project_root=None):
    """@cc [owner:fontanierh,label:correctness] semantic-native-global-output
    Complete emitted Global shader triples, Engine GlobalShaderCache files and
    cooker-ledger runtime loose bytes MUST enter the semantic ROOT. Namespace markers,
    reports and statistics MUST stay in the separate complete transport ROOT.
    Missing, aliased or ambiguous roles MUST refuse before publication.
    """
    cooked, destination = Path(cooked), Path(destination)
    if (not re.fullmatch('[A-Za-z0-9_-]+', project_name) or cooked.resolve() != cooked
            or not cooked.is_dir() or os.path.lexists(destination)):
        raise Refused('semantic global projection requires an existing cook and fresh output')
    source_root = cooked / project_name / 'Metadata/ShaderLibrarySource'
    if source_root.resolve() != source_root or not source_root.is_dir():
        raise Refused('stock cooker omitted its canonical global shader source directory')
    roles = {'ShaderAssetInfo': '.assetinfo.json', 'ShaderArchive': '.ushaderbytecode',
             'ShaderTypeInfo': '.stinfo'}
    formats = {}
    for path in sorted(source_root.iterdir()):
        if '-Global-' not in path.name:
            continue
        info = path.lstat()
        match = re.fullmatch(r'(ShaderAssetInfo|ShaderArchive|ShaderTypeInfo)-Global-([A-Za-z0-9_]+-[A-Za-z0-9_]+)(\.assetinfo\.json|\.ushaderbytecode|\.stinfo)', path.name)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise Refused('global shader source role is an alias, hard link or special file')
        if not match or roles[match[1]] != match[3] or not info.st_size:
            raise Refused('unknown or empty emitted global shader role')
        group = formats.setdefault(match[2], {})
        if match[1] in group:
            raise Refused('ambiguous emitted global shader role')
        group[match[1]] = path
    if not formats or any(set(group) != set(roles) for group in formats.values()):
        raise Refused('stock cooker omitted a complete Global shader archive triple')
    files = [(path, Path('Content') / path.name) for group in formats.values() for path in group.values()]
    caches = set()
    for shader_format in formats:
        platform = shader_format.split('-')[1]
        cache = cooked / 'Engine' / ('GlobalShaderCache-' + platform + '.bin')
        if cache.resolve() != cache:
            raise Refused('global shader cache role contains an alias')
        info = cache.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not info.st_size:
            raise Refused('global shader cache is missing, empty or not a regular file')
        if cache not in caches:
            files.append((cache, Path('Engine') / cache.name)); caches.add(cache)
    if engine_root is not None or project_root is not None:
        engine_root, project_root = Path(engine_root), Path(project_root)
        ledger = _sibling('zen_package_finalise').source_manifest(source_root.parent / 'zenfs.manifest')
        replaced = {'AssetRegistry.bin', 'Metadata/DevelopmentAssetRegistry.bin', 'Metadata/CookMetadata.ucookmeta',
                    'Metadata/CookedIniVersion.txt', 'Metadata/CookedSettings.txt', 'Metadata/ValidationCookArtifact.json',
                    'Metadata/ReferencedSet.txt'}
        for shader_format in formats:
            platform = shader_format.split('-')[1]
            replaced.add('Metadata/ShaderTypeStats-' + platform + '.csv')
            replaced.add('Metadata/ShaderDebug/global_' + shader_format.lower() + '.zip')
            for stem, suffix in roles.items():
                for directory in ('Content', 'Metadata/ShaderLibrarySource'):
                    replaced.add(directory + '/' + stem + '-Global-' + shader_format + suffix)
            replaced.update({'Content/global_' + shader_format.lower() + '.0.metallib',
                             'Content/global_' + shader_format.lower() + '.metalmap'})
        for row in ledger:
            client = row['clientpath']
            domain = 'Engine' if client.startswith('/{engine}/') else 'Project'
            relative = client.split('}/', 1)[1]
            if domain == 'Project' and relative in replaced:
                continue  # Rebuilt from selected histories or kept in certified private transport.
            if domain == 'Project' and not (relative.startswith('Config/') or relative == project_name + '.uproject'):
                raise Refused('unknown source-cook project runtime file role')
            if domain == 'Engine' and relative in {'GlobalShaderCache-' + f.split('-')[1] + '.bin' for f in formats}:
                continue  # Already copied above from the actual stock cook.
            source = (engine_root / 'Engine' if domain == 'Engine' else project_root) / relative
            server = Path(os.path.normpath(engine_root / row['serverpath']))
            if domain == 'Engine':
                # The cooker deliberately remaps selected ICU culture data into
                # its runtime path. Both paths remain within the selected SDK.
                if not server.is_relative_to(engine_root / 'Engine'):
                    raise Refused('cooker runtime file escapes the selected engine')
                source = server
            if (domain == 'Project' and server != source) or source.resolve() != source:
                raise Refused('cooker runtime file does not match its anchored declared tool/project role')
            files.append((source, Path('RuntimeFiles') / domain / relative))
    destination.mkdir(mode=0o700)
    for source, relative in files:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        before = source.lstat()
        descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, 'rb') as incoming, target.open('xb') as outgoing:
            opened = os.fstat(incoming.fileno())
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise Refused('global shader artifact changed before projection')
            shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
            after = os.fstat(incoming.fileno())
        named = source.lstat()
        identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        if identity(before) != identity(after) or identity(after) != identity(named):
            raise Refused('global shader artifact changed during projection')
        target.chmod(stat.S_IMODE(opened.st_mode) & 0o777)
    return sorted(formats)


def source_cook(params, view, project, engine, source_key, state, job_dir, run, environment, export_project, source_digest):
    packages = params['packages']
    argv = cook_argv(engine, project, packages, source_key, global_data='global_data' in params)
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
        semantic_global_data(cooked, destination, project.stem, engine_root=engine, project_root=project.parent)
    return tuple(record_outputs.values())


PACKAGE_FINALISE_SOURCE = """import importlib.util, json, os
from pathlib import Path
import unreal
control=json.loads(Path(os.environ['ATELIER_NATIVE_PACKAGE_FINALISE']).read_bytes())
actual=json.loads(unreal.AtelierBuildWorkerLibrary.native_context())
if actual.get('worker_source_digest') != control['native_source_digest']:
    raise RuntimeError('native package exporter does not match keyed implementation')
spec=importlib.util.spec_from_file_location('atelier_fixed_finalise',control['helper'])
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
def call(method,request):
    return json.loads(getattr(unreal.AtelierBuildWorkerLibrary,method)(json.dumps(request,sort_keys=True,separators=(',',':'))))
result=helper.finalise(**control['arguments'],call=call)
Path(control['report']).write_text(json.dumps(result,sort_keys=True,separators=(',',':')))
"""


def package_runtime(job_dir):
    """@cc [owner:fontanierh,label:correctness;safety] private-package-bootstrap-roles
    Only the fixed controller carrier, exact hashed history archives and uncooked primaries
    MAY precede view construction. This validates bootstrap layout, never native
    authority; the sealed Rust source evidence and finalization checks remain required.
    Unknown entries, links, writable files and paths outside these roles MUST refuse.
    """
    root = job_dir / recipe_job.RUNTIME
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
        raise Refused('package bootstrap runtime is not its owned directory')
    def readonly(path, mode, digest=None):
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
            before = os.fstat(stream.fileno())
            if (not stat.S_ISREG(before.st_mode) or stat.S_IMODE(before.st_mode) != mode
                    or before.st_uid != os.getuid() or before.st_nlink != 1):
                raise Refused('package bootstrap file is not its read-only regular role')
            if digest is None:
                if before.st_size > 64 * 1024 * 1024:
                    raise Refused('package bootstrap carrier exceeds bound')
                raw = stream.read()
            elif (not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest)
                  or hashlib.file_digest(stream, 'sha256').hexdigest() != digest):
                raise Refused('package bootstrap archive differs from its carrier')
            after = os.fstat(stream.fileno())
        identity = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if identity(before) != identity(after) or identity(after) != identity(path.lstat()):
            raise Refused('package bootstrap file changed while checked')
        return raw if digest is None else None
    carrier = json.loads(readonly(root / 'native-packages.json', 0o400))
    if (not isinstance(carrier, dict) or carrier.get('version') != 1
            or not isinstance(carrier.get('packages'), list) or not carrier['packages']):
        raise Refused('package bootstrap carrier has no selected packages')
    global_archive = root / 'global-metadata.tree.tar'
    if carrier.get('global_metadata_archive') != str(global_archive):
        raise Refused('package bootstrap global archive has the wrong role')
    readonly(global_archive, 0o444, carrier.get('global_metadata_sha256'))
    histories = root / 'native-histories'
    info = histories.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
        raise Refused('package bootstrap histories are not an owned directory')
    names = set()
    for row in carrier['packages']:
        slot = row.get('slot') if isinstance(row, dict) else None
        if not isinstance(slot, str) or not re.fullmatch('[A-Za-z0-9_.-]+', slot):
            raise Refused('package bootstrap history slot is invalid')
        name = slot + '.tree.tar'
        archive = histories / name
        if name in names or row.get('metadata_archive') != str(archive):
            raise Refused('package bootstrap history archive has the wrong role')
        names.add(name)
        readonly(archive, 0o444, row.get('metadata_sha256'))
        source = row.get('source')
        source_path = histories / (slot + '.source')
        if not isinstance(source, dict) or set(source) != {'path', 'sha256'} or source['path'] != str(source_path):
            raise Refused('package bootstrap uncooked primary has the wrong role')
        names.add(source_path.name)
        readonly(source_path, 0o444, source['sha256'])
    if {path.name for path in histories.iterdir()} != names:
        raise Refused('package bootstrap histories contain unknown entries')
    return ('native-packages.json', 'global-metadata.tree.tar', 'native-histories')


def finalise_package(job, params, view, project, engine, job_dir, run, environment, source_key):
    carrier_path = job_dir / '.recipe-runtime/native-packages.json'
    info = carrier_path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o400
            or info.st_size > 64 * 1024 * 1024):
        raise Refused('native package composition requires the controller private carrier')
    carrier = json.loads(carrier_path.read_bytes())
    slot = params.get('native_global')
    if (carrier.get('version') != 1 or carrier.get('globals') != [slot]
            or not isinstance(slot, str) or not isinstance(carrier.get('packages'), list) or not carrier['packages']):
        raise Refused('native package carrier differs from declared global input')
    global_inputs = [row for row in job['inputs'] if row['name'] == slot]
    if len(global_inputs) != 1:
        raise Refused('native global input is missing or ambiguous')
    staged = job_dir / recipe_job.relative(global_inputs[0]['path'])
    archive = staged / 'global-data.tree.tar' if staged.is_dir() else staged
    scope = job_dir / '.recipe-runtime/native-finalise'
    scope.mkdir(mode=0o700)
    global_root = scope / 'global-input'
    recipe_job.unpack_root(archive, global_root)
    helper = _sibling('zen_package_finalise')
    histories = helper.prepare_histories(carrier=carrier, global_root=global_root, folder=scope / 'histories',
                                        project_name=project.stem, library=project.stem, unpack=recipe_job.unpack_root)
    bootstrap = Path(carrier['export_project'])
    plugin = bootstrap.parent / 'Plugins/AtelierBuildWorker/AtelierBuildWorker.uplugin'
    if not plugin.is_file() or plugin.is_symlink():
        raise Refused('native package exporter lacks the actual compiled worker plugin')
    descriptor = json.loads(project.read_bytes())
    plugin_dirs = [str((project.parent / path).resolve()) for path in descriptor.get('AdditionalPluginDirectories', [])]
    plugin_dirs.append(str(plugin.parent.parent))
    descriptor['AdditionalPluginDirectories'] = sorted(set(plugin_dirs))
    plugins = [row for row in descriptor.get('Plugins', []) if row.get('Name') != 'AtelierBuildWorker']
    descriptor['Plugins'] = [*plugins, {'Name': 'AtelierBuildWorker', 'Enabled': True}]
    runtime_project = project.with_name('AtelierV2Finalise.uproject')
    with runtime_project.open('x') as stream:
        json.dump(descriptor, stream, sort_keys=True)
    arguments = dict(destination=carrier['destination'], packages=carrier['packages'], **histories,
                     output_dir=str(scope / 'composed'), library=project.stem,
                     runtime_project=str(runtime_project), input_key=source_key)
    request, script, report = scope / 'request.json', scope / 'finalise.py', scope / 'report.json'
    request.write_text(json.dumps({'arguments': arguments, 'helper': str(Path(helper.__file__).resolve()),
                                  'native_source_digest': native_source_digest(job, job_dir), 'report': str(report)}, sort_keys=True))
    script.write_text(PACKAGE_FINALISE_SOURCE); script.chmod(0o444)
    run([str(engine / 'Engine/Binaries/Mac/UnrealEditor-Cmd'), str(runtime_project), '-run=pythonscript',
         '-script=' + str(script), '-unattended', '-nop4', '-nosplash', '-nullrhi', '-stdout', '-FullStdOutLogOutput'],
        cwd=view, env=dict(environment, ATELIER_NATIVE_PACKAGE_FINALISE=str(request)))
    result = json.loads(report.read_bytes())
    endcook = result.get('endcook', {})
    if (endcook.get('status') != 'finalized' or endcook.get('input_key') != source_key
            or endcook.get('project') != carrier['destination']['project']
            or endcook.get('oplog') != 'Mac' or endcook.get('packages') != len(carrier['packages'])):
        raise Refused('native EndCook did not certify the complete selected package set')
    metadata_archive = carrier.get('global_metadata_archive')
    helper._file(metadata_archive, carrier.get('global_metadata_sha256'))
    cooked = project.parent / 'Saved/Cooked/Mac'
    recipe_job.unpack_root(Path(metadata_archive), cooked)
    # The private source transport is an execution context. Replace its registry
    # and shader globals with the selected, native-composed values, never a union
    # of source-history package memberships.
    for row in result['globals']:
        client = row['clientpath']
        if client.startswith('/{project}/'):
            root, relative = project.stem, client.removeprefix('/{project}/')
        elif client.startswith('/{engine}/'):
            root, relative = 'Engine', client.removeprefix('/{engine}/')
        else:
            raise Refused('native global client path is outside project and engine roots')
        source = Path(row['path'])
        helper._file(source, row['sha256'])
        destination = cooked / root / recipe_job.relative(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if not stat.S_ISREG(destination.lstat().st_mode):
                raise Refused('native final globals overlap a non-file transport entry')
            destination.unlink()
        with source.open('rb') as incoming, destination.open('xb') as outgoing:
            shutil.copyfileobj(incoming, outgoing)
        helper._file(destination, row['sha256'])
    marker = cooked / 'ue.projectstore'
    if not marker.is_file() or marker.is_symlink():
        raise Refused('native final package lacks the certified projectstore context')
    return {path.relative_to(cooked).as_posix(): _digest(path) for path in cooked.rglob('*') if path.is_file()}



def compile_candidate(job, fresh, protected, candidate):
    """@cc [owner:fontanierh,label:correctness] incremental-compile-current-inputs
    A compile candidate MUST match every current declared input before UBT. Missing
    or changed inputs MUST be independently refreshed from current staging. Only
    this owned derived view and frozen worker code MAY change; original staged inputs remain untouched. Reuse
    MUST still run current UBT, validate its receipt and publish through the new guard.
    A candidate is execution context, never evidence of prior task success.
    """
    candidate = Path(candidate)
    if (not candidate.is_absolute() or candidate.name != 'view'
            or candidate.parent.name != recipe_job.RUNTIME
            or candidate.parent.parent.name != 'job'
            or len(candidate.parents) < 4 or len(fresh.parents) < 4
            or candidate.parents[3] != fresh.parents[3]
            or candidate.resolve(strict=True) != candidate
            or candidate.stat().st_uid != os.getuid()):
        raise Refused('compile candidate is not an owned closed native view')
    cleanups = sorted((candidate.parent.parent.parent / 'guard').glob('attempt-*/cleanup.json'))
    if not cleanups or any(json.loads(path.read_bytes()).get('confirmed') is not True for path in cleanups):
        raise Refused('compile candidate lacks confirmed prior guard cleanup')
    # Each mapped input includes its COMPLETE frozen membership, not only a receipt
    # or current Git revision. Current staged bytes refresh changed source inputs.
    mapped = [fresh / relative for relative in job['params']['recipe']['paths']]
    for source in mapped:
        target = candidate / source.relative_to(fresh)
        if not os.path.lexists(target):
            if target.parent.resolve(strict=False) != target.parent:
                raise Refused('compile candidate input ancestor is aliased')
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                shutil.copyfile(source, target)
                shutil.copymode(source, target, follow_symlinks=False)
        if target.resolve(strict=True) != target:
            raise Refused('compile candidate input is aliased')
        expected, actual = _tree(source), _tree(target)
        staged = job['params']['recipe']['paths'][source.relative_to(fresh).as_posix()]
        # File inputs key their bytes. A source also staged as worker code is 0444;
        # that harmless materialization mode must not invalidate the same bytes.
        if source.is_file() and not staged.endswith('.tree.tar'):
            expected = [row[:-1] if row[1] == 'file' else row for row in expected]
            actual = [row[:-1] if row[1] == 'file' else row for row in actual]
        if expected != actual:
            # This is an ordinary incremental source update. Original prior staged
            # inputs and CAS products remain untouched; only this derived view changes.
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                shutil.copyfile(source, target)
                shutil.copymode(source, target, follow_symlinks=False)
            if _tree(source) != _tree(target):
                raise Refused('compile candidate input refresh differs from current staging')
    for name in job['code']:
        source, target = fresh / name, candidate / name
        if os.path.lexists(target) and (target.is_symlink() or not target.is_file()):
            raise Refused('compile candidate code path is not a regular file')
        if target.parent.resolve(strict=False) != target.parent:
            raise Refused('compile candidate code ancestor is aliased')
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.chmod(0o644)
        shutil.copyfile(source, target)
        target.chmod(0o444)
    return candidate, [str(candidate / Path(name).relative_to(fresh)) for name in protected]

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
    reserved = package_runtime(job_dir) if kind == 'unreal.package' and params.get('native_global') else ()
    view, protected, writes = recipe_job.prepare_view(job, job_dir, reserved=reserved)
    restore_native_inputs(recipe, view, run)
    raw_roots = ()
    if kind == 'unreal.cook.produce':
        if (export_project is None or not Path(export_project).is_absolute() or Path(export_project).suffix != '.uproject'
                or not Path(export_project).is_file() or Path(export_project).is_symlink()):
            raise Refused('source-cook needs the existing owned compiled C3 export project')
        view, protected = persistent_cook_view(view, protected, source_key, zen_state_root)
    candidate = os.environ.get('ATELIER_V2_COMPILE_VIEW')
    if candidate and kind in ('unreal.compile', 'unreal.game'):
        view, protected = compile_candidate(job, view, protected, candidate)
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
        inventory = finalise_package(job, params, view, project, engine, job_dir, run, environment, source_key) if params.get('native_global') else params.get('cooked_files')
        cooked = project.parent / 'Saved/Cooked/Mac'
        package_view, packaging_project = (package_project_view(job, job_dir, view, project, run)
                                           if params.get('native_global') else (view, project))
        package_cooked = packaging_project.parent / 'Saved/Cooked/Mac'
        archive = _path(package_view, params['archive'])
        argv = ops.package_argv(engine, packaging_project, target, archive, cooked_root=package_cooked,
                                cooked_files=inventory, configuration=configuration)
        environment = ops.package_environment(engine, environment)
        lifecycle = ops.package_lifecycle(job_dir, engine, environment)
        try:
            run(argv, cwd=package_view, env=environment, lifecycle=lifecycle)
        finally:
            lifecycle.close()
        ops.verify_cooked_files(package_cooked, inventory)
        if package_view != view:
            archive.rename(_path(view, params["archive"]))
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
        if not isinstance(source_key, str) or not re.fullmatch('[a-f0-9]{64}', source_key):
            raise Refused('package archive requires its actual controller input key')
        if len(args) != 2 or args[0] != '--out' or not isinstance(args[1], Path):
            raise Refused('v2 package archive requires one exact declared output root')
        package_root = args[1]
        if (not package_root.is_relative_to(view) or package_root == view
                or not any(_path(view, row['path']) == package_root for row in recipe['outputs'])):
            raise Refused('package archive output is outside its declared owned roots')
        package_root.mkdir(parents=True, exist_ok=False)
        restore_mac_zip(staged_mac_zip(job, job_dir, 'archive'), package_root / 'archive', run)
        run([sys.executable, '-I', '-B', str(script), *map(str, args), '--revision', 'v2-' + source_key],
            cwd=view, env=environment)
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
