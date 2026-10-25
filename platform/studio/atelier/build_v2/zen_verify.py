import hashlib
import json
import re
from pathlib import Path
import unreal

def run(context):
    p = context.params
    if set(p) != {'package', 'mode'} or p['mode'] not in ('verify', 'restore'):
        raise ValueError('Expected fixed logical native verification parameters')
    request = dict(context.zen_request)
    fields = {'version', 'mode', 'project', 'oplog', 'source_package', 'expected_stored_key', 'expected_root_hash',
              'record_path', 'project_file', 'marker_path', 'input_key', 'runtime_project_file'}
    if set(request) != fields or request['version'] != 1 or request['mode'] != p['mode']:
        raise ValueError('Missing trusted native execution context')
    if (request['source_package'] != p['package'] or not request['project'].startswith('AtelierV2_')
            or request['oplog'] != 'Mac'):
        raise ValueError('Native execution context differs from the logical source/package identity')
    if not re.fullmatch('[a-f0-9]{64}', request['project'].removeprefix('AtelierV2_')):
        raise ValueError('Unknown owned native namespace')
    runtime = Path(context.content_dir).parent / 'Atelier.uproject'
    if Path(request['runtime_project_file']) != runtime:
        raise ValueError('Native verification must run in the owned C3 scratch project')
    raw = json.dumps(request, sort_keys=True, separators=(',', ':'))
    report = json.loads(unreal.AtelierBuildWorkerLibrary.zen_package_request(raw))
    wanted_status = 'restored' if p['mode'] == 'restore' else 'verified'
    if (report.get('version') != 1 or report.get('status') != wanted_status
            or any(report.get(k) != request[k] for k in ('mode', 'project', 'oplog', 'source_package', 'input_key', 'runtime_project_file'))
            or report.get('native_stored_key') != request['expected_stored_key']
            or (request['expected_root_hash'] and report.get('root_hash') != request['expected_root_hash'])):
        raise ValueError('Independent native package verification refused or differed')
    record_path = Path(request['record_path'])
    with record_path.open('rb') as source:
        record_sha256 = hashlib.file_digest(source, 'sha256').hexdigest()
    locator = dict(version=2, record_sha256=record_sha256, project=request['project'], oplog=request['oplog'], package=p['package'],
                   source_key=request['project'].removeprefix('AtelierV2_'), dependency_key=report['native_stored_key'], entry_hash=report['root_hash'], installed_entry_hash=report['installed_root_hash'],
                   lifetime_marker=request['marker_path'], record_path=request['record_path'], project_file=request['project_file'])
    result = dict(version=1, locator=locator, record_io_hash=report['record_io_hash'], record_sha256=record_sha256, attachments=report['attachments'], mode=p['mode'], source_dependency_evaluation=report['source_dependency_evaluation'])
    return result
