"""Compose selected verified package records in an already-owned native cook namespace."""
import hashlib
from pathlib import Path
import re
import stat


class Refused(ValueError):
    pass


def _hash(value, length):
    return isinstance(value, str) and re.fullmatch('[a-f0-9]{' + str(length) + '}', value) and value != '0' * length


def _file(path, digest):
    value = Path(path)
    if not value.is_absolute() or value.resolve() != value:
        raise Refused('native finalization file must be a canonical declared path')
    info = value.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not _hash(digest, 64):
        raise Refused('native finalization file must be regular and explicitly hashed')
    with value.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != digest:
            raise Refused('native finalization input changed')
    return str(value)


def select_runtime_globals(rows, *, project, engine):
    """@cc [owner:fontanierh,label:correctness] sdk-owned-config-staging
    Only Config INI files byte-identical to their selected SDK/project source MAY
    leave the injected runtime roster, so stock UAT stages their platform roles.
    All other globals MUST remain selected. Complete captured archives MUST remain
    untouched; malformed roles, aliases and changed source bytes MUST refuse.
    """
    project, engine = Path(project), Path(engine)
    if (not project.is_absolute() or project.resolve() != project
            or not stat.S_ISREG(project.lstat().st_mode)
            or not engine.is_absolute() or engine.resolve() != engine
            or not stat.S_ISDIR(engine.lstat().st_mode) or not isinstance(rows, list)):
        raise Refused('runtime globals require the selected canonical project and SDK')
    selected, seen = [], set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'clientpath', 'path', 'sha256'}:
            raise Refused('invalid runtime global descriptor')
        client = row['clientpath']
        if not isinstance(client, str):
            raise Refused('invalid runtime global role')
        domain = next((part for part in ('engine', 'project') if client.startswith('/{' + part + '}/')), None)
        tail = client[len(domain) + 4:] if domain else ''
        parts = tail.split('/')
        if (not tail or '\\' in tail or any(part in ('', '.', '..') for part in parts)
                or any(ord(c) < 32 for c in client) or client in seen):
            raise Refused('invalid or duplicate runtime global role')
        seen.add(client)
        _file(row['path'], row['sha256'])
        config = parts[0] == 'Config' or (parts[0] == 'Plugins' and 'Config' in parts[1:-1])
        if config and parts[-1].endswith('.ini'):
            base = engine / 'Engine' if domain == 'engine' else project.parent
            _file(base.joinpath(*parts), row['sha256'])
        else:
            selected.append(row)
    return selected


def source_manifest(path):
    """Read the stock cooker's frozen ledger; its server paths never grant reads."""
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path or not stat.S_ISREG(path.lstat().st_mode):
        raise Refused('stock cooker file ledger is not an anchored regular file')
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    _file(path, digest)
    lines = raw.decode('utf-8-sig').splitlines()
    if len(lines) < 2 or not lines[0].startswith(';ServerRoot=') or lines[1] != 'FileId, ServerPath, ClientPath':
        raise Refused('unsupported stock cooker file ledger')
    rows, ids, paths = [], set(), set()
    for line in lines[2:]:
        fields = line.split(', ')
        if len(fields) != 3:
            raise Refused('ambiguous stock cooker file ledger row')
        identity, server, client = fields
        relative = client.removeprefix('/{engine}/') if client.startswith('/{engine}/') else client.removeprefix('/{project}/') if client.startswith('/{project}/') else ''
        if (not _hash(identity, 24) or identity in ids or client in paths or not relative
                or '\\' in relative or any(part in ('', '.', '..') for part in relative.split('/'))
                or any(ord(c) < 32 for c in client + server)):
            raise Refused('invalid or duplicate stock cooker file ledger role')
        rows.append({'id': identity, 'clientpath': client, 'serverpath': server})
        ids.add(identity); paths.add(client)
    if not rows or len(rows) > 32768:
        raise Refused('stock cooker file ledger is empty or too large')
    _file(path, digest)
    return rows


def finalise(*, destination, packages, histories, global_histories, global_files, output_dir, library, formats,
             runtime_project, input_key, call, source_files=()):
    """@cc [owner:fontanierh,label:correctness] selected-native-package-finalization
    Only an actual already-owned global-cook namespace MAY be the destination.
    Every selected package MUST come from its separately verified immutable CB;
    native restore/readback MUST precede native registry/shader composition and
    EndCook. Namespace and source-key provenance MUST NOT become item identities.
    Missing globals, changed records, refused SDK calls and incomplete final reports
    MUST fail; no package scope, native libraries or dependency checks MAY be omitted.
    The caller MUST supply the private controller-validated destination and declared
    input paths, and retain its C5 guard through all native calls and cleanup.
    """
    fields = ('project', 'oplog', 'project_file', 'lifetime_marker')
    if (not isinstance(destination, dict) or any(not isinstance(destination.get(key), str) or not destination[key] for key in fields)
            or destination['oplog'] != 'Mac' or not _hash(input_key, 64)
            or not isinstance(packages, list) or not packages or not histories or not global_histories or not isinstance(global_files, list)):
        raise Refused('native finalization requires an actual global destination and complete package/global inputs')
    for path in (destination['project_file'], destination['lifetime_marker'], runtime_project):
        value = Path(path)
        if not value.is_absolute() or value.resolve() != value or not stat.S_ISREG(value.lstat().st_mode):
            raise Refused('native namespace execution context is not a retained regular file')
    output = Path(output_dir)
    if not output.is_absolute() or output.resolve() != output or output.exists() or output.is_symlink():
        raise Refused('native finalization output must be a fresh owned absolute directory')
    def invoke(method, request, status):
        report = call(method, request)
        if not isinstance(report, dict) or report.get('version') != 1 or report.get('status') != status:
            raise Refused('native ' + method + ' refused: ' + str(report))
        return report
    chosen, seen = [], set()
    for row in packages:
        locator = row.get('locator')
        if not isinstance(locator, dict):
            raise Refused('selected package lacks its private verified locator')
        name = locator.get('package')
        if (not isinstance(name, str) or not re.fullmatch(r'/(?:[A-Za-z0-9_-]+/)+[A-Za-z0-9_-]+', name)
                or name in seen or not _hash(locator.get('dependency_key'), 40) or not _hash(locator.get('entry_hash'), 40)
                or row.get('record_sha256') != locator.get('record_sha256')):
            raise Refused('selected native package identity is malformed or duplicated')
        record = _file(locator['record_path'], row['record_sha256'])
        request = dict(version=1, mode='restore', project=destination['project'], oplog='Mac', source_package=name,
            expected_stored_key=locator['dependency_key'], expected_root_hash=locator['entry_hash'], record_path=record,
            project_file=destination['project_file'], marker_path=destination['lifetime_marker'], input_key=input_key,
            runtime_project_file=runtime_project)
        report = invoke('zen_package_request', request, 'restored')
        if (any(report.get(key) != request[key] for key in ('mode', 'project', 'oplog', 'source_package', 'input_key', 'runtime_project_file'))
                or report.get('native_stored_key') != locator['dependency_key']
                or report.get('root_hash') != locator['entry_hash'] or not _hash(report.get('installed_root_hash'), 40)):
            raise Refused('native selected package restore identity differs')
        chosen.append({'name': name, 'installed_root_hash': report['installed_root_hash']})
        seen.add(name)
    global_output = output.parent / (output.name + '-global')
    global_composed = invoke('zen_finalise_request', dict(version=2, library='Global', formats=list(formats),
        histories=global_histories, output_dir=str(global_output), global_library=True, native_libraries=True), 'composed')
    if global_composed.get('global_library') is not True or global_composed.get('native_libraries') is not True:
        raise Refused('native global shader library composition was incomplete')
    composed = invoke('zen_finalise_request', dict(version=2, library=library, formats=list(formats),
        histories=histories, output_dir=str(output), global_library=False, native_libraries=True), 'composed')
    if composed.get('packages') != len(chosen) or composed.get('native_libraries') is not True:
        raise Refused('native registry/shader composition omitted selected packages or native libraries')
    files, names = [], set()
    for row in global_files:
        if not isinstance(row, dict) or set(row) != {'clientpath', 'path', 'sha256'}:
            raise Refused('native global file is not an exact declared descriptor')
        _file(row['path'], row['sha256'])
        if row['clientpath'] in names:
            raise Refused('duplicate native global file')
        names.add(row['clientpath']); files.append(dict(row))
    projected = []
    for report, base, name in ((composed, output, library), (global_composed, global_output, 'Global')):
        diagnostics = report.get('diagnostic_files', [])
        allowed = {'Metadata/ShaderDebug/' + (name + '_' + fmt).lower() + '.zip' for fmt in formats}
        if (not isinstance(diagnostics, list) or any(not isinstance(path, str) or path not in allowed for path in diagnostics)
                or len(diagnostics) != len(set(diagnostics))):
            raise Refused('native shader diagnostics differ from exact SDK-derived roles')
        observed = set()
        for row in report.get('files', []):
            relative = row.get('path')
            if relative in diagnostics:
                _file(base / relative, row['sha256'])
                observed.add(relative)
            else:
                projected.append((row, base))
        if observed != set(diagnostics):
            raise Refused('native diagnostic census is incomplete')
    for row, base in projected:
        relative = row.get('path')
        if (not isinstance(relative, str) or not relative or Path(relative).is_absolute()
                or any(part in ('', '.', '..') for part in relative.split('/'))):
            raise Refused('native finalization output path is not canonical')
        path = base / relative
        _file(path, row['sha256'])
        client = '/{project}/' + relative
        if client in names:
            raise Refused('composed native global file has two owners')
        names.add(client)
        files.append({'clientpath': client, 'path': str(path), 'sha256': row['sha256']})
    if not composed.get('files'):
        raise Refused('native finalization produced no registry/shader files')
    ending = output.parent / (output.name + '-endcook')
    report = invoke('zen_end_cook_request', dict(version=1, project=destination['project'], oplog='Mac',
        project_file=destination['project_file'], marker_path=destination['lifetime_marker'],
        runtime_project_file=runtime_project, input_key=input_key, packages=chosen, globals=files,
        output_dir=str(ending), source_files=list(source_files)), 'finalized')
    return {'composition': composed, 'global_composition': global_composed, 'endcook': report, 'packages': chosen, 'globals': files}


def prepare_histories(*, carrier, global_root, folder, project_name, library, unpack):
    """Project complete certified transport archives onto selected native SDK histories.

    Archive paths and digests must come from the controller's private carrier. Only
    the selected package list enters each history; transport namespaces never do.
    The SDK still validates registry linkage, native dependencies and shader ownership.
    """
    if (not isinstance(carrier, dict) or carrier.get('version') != 1
            or not isinstance(carrier.get('packages'), list) or not carrier['packages']
            or not re.fullmatch('[A-Za-z0-9_-]+', project_name)
            or not re.fullmatch('[A-Za-z0-9_-]+', library)):
        raise Refused('package histories require the controller carrier and explicit native project')
    folder, global_root = Path(folder), Path(global_root)
    if not folder.is_absolute() or folder.resolve() != folder or folder.exists() or folder.is_symlink():
        raise Refused('package history projection needs a fresh owned scope')
    folder.mkdir(mode=0o700)

    def shaders(content, name, output, formats=None, allow_shaderless=False):
        if allow_shaderless and not content.exists() and not content.is_symlink():
            output.mkdir(mode=0o700)
            return [], {'content_dir': str(output), 'files': {}, 'packages': []}
        if not content.is_dir() or content.is_symlink():
            raise Refused('declared shader content directory is absent or linked')
        pattern = re.compile(r'ShaderArchive-' + re.escape(name) + r'-([A-Za-z0-9_]+-[A-Za-z0-9_]+)\.ushaderbytecode')
        found = sorted(match.group(1) for path in content.iterdir() if (match := pattern.fullmatch(path.name)))
        if allow_shaderless and not found:
            if any(path.name.startswith(('ShaderArchive-', 'ShaderAssetInfo-', 'ShaderTypeInfo-')) for path in content.iterdir()):
                raise Refused('partial or unsupported shader history cannot be shaderless')
            output.mkdir(mode=0o700)
            return [], {'content_dir': str(output), 'files': {}, 'packages': []}
        if not found or len(found) != len(set(found)) or (formats is not None and found != formats):
            raise Refused('native shader format roster differs or is incomplete')
        output.mkdir(mode=0o700)
        files = {}
        for shader_format in found:
            for stem, suffix in (('ShaderAssetInfo', '.assetinfo.json'), ('ShaderArchive', '.ushaderbytecode'),
                                 ('ShaderTypeInfo', '.stinfo')):
                filename = stem + '-' + name + '-' + shader_format + suffix
                source = content / filename
                info = source.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not info.st_size:
                    raise Refused('native shader history is incomplete or aliased')
                digest = hashlib.sha256(source.read_bytes()).hexdigest()
                _file(source, digest)
                target = output / filename
                with target.open('xb') as stream:
                    stream.write(source.read_bytes())
                _file(target, digest)
                files[filename] = digest
        return found, {'content_dir': str(output), 'files': files, 'packages': []}

    formats, global_history = shaders(global_root / 'Content', 'Global', folder / 'global')
    histories, archives, names = [], {}, set()
    for row in carrier['packages']:
        locator = row.get('locator')
        name = locator.get('package') if isinstance(locator, dict) else None
        if not isinstance(name, str) or name in names:
            raise Refused('selected native package history is missing or duplicated')
        names.add(name)
        archive = _file(row.get('metadata_archive'), row.get('metadata_sha256'))
        source = row.get('source')
        if not isinstance(source, dict) or set(source) != {'path', 'sha256'}:
            raise Refused('selected package lacks its certified uncooked primary')
        _file(source['path'], source['sha256'])
        selected = {'name': name, 'source': source,
                    'record': {'path': locator.get('record_path'), 'sha256': row.get('record_sha256')},
                    'root_hash': locator.get('entry_hash')}
        _file(selected['record']['path'], selected['record']['sha256'])
        identity = (archive, row['metadata_sha256'])
        if identity in archives:
            archives[identity]['packages'].append(selected)
            continue
        index = len(histories)
        root = folder / ('history-' + str(index))
        unpack(Path(archive), root)
        project = root / project_name
        # The stock cooker retains archive-capable source code here before removing
        # Content's .ushaderbytecode during native library packaging.
        _, history = shaders(project / 'Metadata/ShaderLibrarySource', library,
                             folder / ('shaders-' + str(index)), formats, allow_shaderless=True)
        for key, filename in (('registry', 'DevelopmentAssetRegistry.bin'), ('metadata', 'CookMetadata.ucookmeta')):
            source = project / 'Metadata' / filename
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            history[key] = {'path': _file(source, digest), 'sha256': digest}
        history['packages'] = [selected]
        archives[identity] = history
        histories.append(history)
    global_files = []
    for shader_format in formats:
        platform = shader_format.split('-')[1]
        filename = 'GlobalShaderCache-' + platform + '.bin'
        source = global_root / 'Engine' / filename
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        global_files.append({'clientpath': '/{engine}/' + filename,
                             'path': _file(source, digest), 'sha256': digest})
    runtime = global_root / 'RuntimeFiles'
    if runtime.exists():
        for source in sorted(runtime.rglob('*')):
            if source.is_dir() and not source.is_symlink():
                continue
            relative = source.relative_to(runtime).as_posix()
            domain, separator, tail = relative.partition('/')
            if not separator or domain not in ('Engine', 'Project'):
                raise Refused('unknown semantic runtime file role')
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            global_files.append({'clientpath': '/{' + domain.lower() + '}/' + tail,
                                 'path': _file(source, digest), 'sha256': digest})
    source_files = []
    if 'global_metadata_archive' in carrier:
        archive = _file(carrier['global_metadata_archive'], carrier['global_metadata_sha256'])
        metadata_root = folder / 'global-metadata'
        unpack(Path(archive), metadata_root)
        source_files = [{key: row[key] for key in ('id', 'clientpath')} for row in
                        source_manifest(metadata_root / project_name / 'Metadata/zenfs.manifest')]
    return {'histories': histories, 'global_histories': [global_history], 'formats': formats,
            'global_files': global_files, 'source_files': source_files}
