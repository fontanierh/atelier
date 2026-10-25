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


def finalise(*, destination, packages, histories, global_histories, global_files, output_dir, library, formats,
             runtime_project, input_key, call):
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
    for row, base in [(row, output) for row in composed.get('files', [])] + [(row, global_output) for row in global_composed.get('files', [])]:
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
        output_dir=str(ending)), 'finalized')
    return {'composition': composed, 'global_composition': global_composed, 'endcook': report, 'packages': chosen, 'globals': files}
