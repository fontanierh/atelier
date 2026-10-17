"""Explicit administrative release of an interrupted, performance-exclusive compile.

This is current quiescence evidence, not reconstructed historical monitor success.
Ordinary close/reconcile never selects this policy.
"""
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from atelier.harness import capacity_protocol as wire

# Specialized, read-only OS indexing workers cannot be compiler/build helpers.
INDEXER = '/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/Metadata.framework/Versions/A/Support/mdworker_shared'
OS_SERVICES = frozenset((INDEXER, '/System/Library/PrivateFrameworks/HelpData.framework/Versions/A/Resources/helpd'))
BUILD_NAMES = frozenset(('Blender', 'blender', 'UnrealEditor', 'UnrealEditor-Cmd', 'ShaderCompileWorker',
    'dotnet', 'mono', 'UnrealBuildTool', 'AutomationTool', 'xcodebuild', 'make', 'ninja', 'cmake', 'cargo', 'rustc'))


def absent(pin):
    """Only ESRCH/ENOENT or a different birth identity establish current absence."""
    try:
        return wire.process_start(pin[0]) != pin[1]
    except OSError as error:
        if error.errno in (errno.ESRCH, errno.ENOENT):
            return True
        raise wire.CapacityError('Interrupted compile identity probe failed') from None


def census():
    """Complete bounded same-UID kernel listing; no command-name-only ownership inference."""
    if sys.platform != 'darwin':
        raise wire.CapacityError('Administrative compile recovery currently requires macOS')
    from atelier.harness.safety.memory_guard import usage
    lib = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
    lib.proc_listpids.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_int]
    lib.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
    lib.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    capacity = 16384
    buffer = (ctypes.c_int * capacity)()
    count = lib.proc_listpids(4, os.getuid(), buffer, ctypes.sizeof(buffer))  # PROC_UID_ONLY
    if count <= 0 or count >= ctypes.sizeof(buffer) or count % ctypes.sizeof(ctypes.c_int):
        raise wire.CapacityError('Interrupted compile census is incomplete')
    result = {}
    for pid in buffer[:count // ctypes.sizeof(ctypes.c_int)]:
        if pid <= 0:
            continue
        try:
            before = usage(pid)
            info = ctypes.create_string_buffer(1024)
            n = lib.proc_pidinfo(pid, 3, 0, info, len(info))  # PROC_PIDTBSDINFO
            path = ctypes.create_string_buffer(4096)
            size = lib.proc_pidpath(pid, path, len(path))
            after = usage(pid)
        except OSError as error:
            if error.errno in (errno.ESRCH, errno.ENOENT):
                continue
            raise wire.CapacityError('Interrupted compile census identity lookup failed') from None
        if before.exited or after.exited:
            continue
        if n < 24 or size <= 0 or before.started != after.started:
            raise wire.CapacityError('Interrupted compile census changed or could not read a process')
        fields = tuple(ctypes.c_uint32.from_buffer_copy(info.raw[i:i+4]).value for i in range(0,24,4))
        if fields[3] != pid or fields[5] != os.getuid() or pid in result:
            raise wire.CapacityError('Interrupted compile census has inconsistent identities')
        result[pid] = dict(pid=pid, started=before.started, parent=fields[4], executable=path.value.decode('utf-8'))
    if os.getpid() not in result:
        raise wire.CapacityError('Interrupted compile census omitted its observer')
    return result


def service_pin(item):
    """One explicitly reviewed live service exemption, bound to its exact plist and identity."""
    wire.fields(item, ('pid', 'started', 'label', 'plist_sha256'))
    pin = wire.identity((item['pid'], item['started']))
    label = wire.text(item['label'])
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', label):
        raise wire.CapacityError('Invalid recovery service label')
    path = Path.home() / 'Library/LaunchAgents' / (label + '.plist')
    raw = wire.private_file(path, limit=wire.MAX_FRAME, private=False)
    if hashlib.sha256(raw).hexdigest() != item['plist_sha256']:
        raise wire.CapacityError('Recovery service binding changed')
    value = subprocess.run(['/bin/launchctl', 'print', f'gui/{os.getuid()}/{label}'],
        capture_output=True, timeout=.5)
    if value.returncode or len(value.stdout) > 128 * 1024 or re.search(rb'(?m)^\s*pid = '+str(pin[0]).encode()+rb'\s*$', value.stdout) is None:
        raise wire.CapacityError('Recovery service is not owned by its live launchd binding')
    if absent(pin):
        raise wire.CapacityError('Recovery service identity changed')
    return pin


def validate_snapshot(rows, record, services):
    root = tuple(record['child'])
    retained = set(map(tuple, record['roster']))
    for row in rows.values():
        pin = (row['pid'], row['started'])
        name = Path(row['executable']).name
        if pin in retained or name in BUILD_NAMES or name.startswith(('clang', 'ShaderCompileWorker')):
            raise wire.CapacityError('Live compiler/build/render process prevents administrative release')
        if row['started'] < root[1] or row['executable'] in OS_SERVICES or pin in services:
            continue
        # Current positive ancestry to a process predating this launch excludes an
        # orphan of the compile. launchd itself is never such an exemption.
        seen, current = set(), row
        while current['pid'] not in seen:
            seen.add(current['pid'])
            parent = rows.get(current['parent'])
            if parent is None or parent['pid'] == 1 or parent['started'] > current['started']:
                break
            if parent['started'] < root[1]:
                break
            current = parent
        else:
            raise wire.CapacityError('Recovery census ancestry contains a cycle')
        if parent is None or parent['pid'] == 1 or parent['started'] >= root[1] or parent['started'] > current['started']:
            raise wire.CapacityError(f'Unclassified process {row["pid"]} born after the compile prevents administrative release')


def recover(record, evidence, *, principal, boot, epoch, scan=None, missing=None, service=None):
    """@cc [owner:fontanierh,label:safety] administrative-interrupted-compile-release
    Explicit operator-directed administration MAY abandon only an uncertain exclusive compile
    with a recorded positive root exit, absent controller/guards/retained identities and fresh
    complete same-user censuses. Unknown or live workload identities MUST refuse. A recent
    orphan MUST refuse unless it is an exact independently reviewed live launchd service or
    the specialized OS indexer. Normal close/reconcile MUST NOT use this policy. The witness
    MUST retain the original evidence hashes and operation binding, and MUST NOT certify outputs.
    """
    scan, missing, service = scan or census, missing or absent, service or service_pin
    wire.fields(evidence, ('id', 'nonce', 'epoch', 'boot_id', 'operator_reference', 'administrator', 'services'))
    request = record['request']
    if (evidence['id'] != request['id'] or evidence['nonce'] != record.get('nonce')
            or evidence['epoch'] != epoch or evidence['boot_id'] != boot):
        raise wire.CapacityError('Administrative interruption recovery was fenced')
    administrator = wire.text(evidence['administrator'])
    reference = wire.text(evidence['operator_reference'], maximum=512)
    if administrator == request.get('owner') or tuple(principal) == tuple(record['principal']):
        raise wire.CapacityError('Interrupted compile owner cannot administratively release itself')
    if (record['state'] != 'uncertain' or request.get('phase') != 'compile'
            or request.get('performance') is not True or record.get('child') not in record.get('exited', [])):
        raise wire.CapacityError('Administrative recovery requires an interrupted exclusive compile with root exit')
    pins = set(map(tuple, record['roster'])) | {tuple(record['principal'])}
    pins.update((g['pid'], g['start']) for g in record['guards'].values())
    if any(not missing(pin) for pin in pins):
        raise wire.CapacityError('Interrupted compile still has a live controller, guard or retained process')
    items = evidence['services']
    if type(items) is not list or len(items) > 8:
        raise wire.CapacityError('Invalid interrupted compile service exemptions')
    services = {service(item) for item in items}
    reports = {}
    for kind, guard in record['guards'].items():
        raw = wire.private_file(guard['report'], limit=wire.MAX_FRAME, private=False)
        reports[kind] = hashlib.sha256(raw).hexdigest()
    observations = []
    for _ in range(2):
        rows = scan()
        validate_snapshot(rows, record, services)
        observations.append(rows)
    # Recheck every exact identity after the complete observations, still in this actor turn.
    if any(not missing(pin) for pin in pins):
        raise wire.CapacityError('Interrupted compile identity appeared during administrative recovery')
    for kind, guard in record['guards'].items():
        raw = wire.private_file(guard['report'], limit=wire.MAX_FRAME, private=False)
        if hashlib.sha256(raw).hexdigest() != reports[kind]:
            raise wire.CapacityError('Original interrupted compile reports changed during recovery')
    digest = hashlib.sha256(json.dumps(observations, sort_keys=True).encode()).hexdigest()
    return dict(kind='administrative-interruption', coverage='current-observed-quiescence',
        operator_reference=reference, administrator=administrator, administrative_principal=list(principal),
        nonce=record['nonce'], request_id=request['id'], epoch=epoch, boot_id=boot, observed_at=time.time(),
        checked_identities=len(pins), missing_historical_exits=len(set(map(tuple,record['roster']))-set(map(tuple,record['exited']))),
        ancestry_unknown=record.get('ancestry_unknown',False), original_report_sha256=reports,
        census_sha256=digest, service_exemptions=items, output_certified=False)
