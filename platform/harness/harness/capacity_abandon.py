"""Explicit administrative release after reviewed workload quiescence.

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
COMPLETED_XPC = '/System/Library/PrivateFrameworks/AOSKit.framework/Versions/A/XPCServices/com.apple.iCloudHelper.xpc/Contents/MacOS/com.apple.iCloudHelper'
BUILD_NAMES = frozenset(('Blender', 'blender', 'UnrealEditor', 'UnrealEditor-Cmd', 'ShaderCompileWorker',
    'dotnet', 'mono', 'UnrealBuildTool', 'AutomationTool', 'xcodebuild', 'make', 'ninja', 'cmake', 'cargo', 'rustc'))


def absent(pin):
    """Only ESRCH/ENOENT or a different birth identity establish current absence."""
    try:
        return wire.process_start(pin[0]) != pin[1]
    except OSError as error:
        if error.errno in (errno.ESRCH, errno.ENOENT):
            return True
        raise wire.CapacityError('Administrative recovery identity probe failed') from None


def census(*, before_root=None):
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
        raise wire.CapacityError('Administrative recovery census is incomplete')
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
            raise wire.CapacityError('Administrative recovery census identity lookup failed') from None
        if before.exited or after.exited:
            continue
        predates = (before_root is not None and before.started == after.started < before_root)
        if n < 24 or (size <= 0 and not predates) or before.started != after.started:
            raise wire.CapacityError('Administrative recovery census changed or could not read a process')
        fields = tuple(ctypes.c_uint32.from_buffer_copy(info.raw[i:i+4]).value for i in range(0,24,4))
        if size <= 0 and predates:
            checked = ctypes.create_string_buffer(1024)
            n2 = lib.proc_pidinfo(pid, 3, 0, checked, len(checked))
            final = usage(pid)
            # Include PID, parent and UID in the stable kernel binding, not just birth time.
            if n2 < 24 or checked.raw[12:24] != info.raw[12:24] or final.started != before.started or final.exited:
                raise wire.CapacityError('Pre-root census identity changed')
        if fields[3] != pid or fields[5] != os.getuid() or pid in result:
            raise wire.CapacityError('Administrative recovery census has inconsistent identities')
        result[pid] = dict(pid=pid, started=before.started, parent=fields[4], executable=path.value.decode('utf-8'))
        if size <= 0:
            result[pid]['executable_unavailable_before_root'] = True
            result[pid]['uid'] = fields[5]
    if os.getpid() not in result:
        raise wire.CapacityError('Administrative recovery census omitted its observer')
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


def completed_system_service(row):
    """Only the exact Apple XPC service, on the protected system volume, may be excluded."""
    if row['parent'] != 1 or row['executable'] != COMPLETED_XPC:
        return False
    try:
        info = Path(COMPLETED_XPC).stat()
        # SF_RESTRICTED from Darwin sys/stat.h: protected by System Integrity Protection.
        if info.st_uid != 0 or info.st_mode & 0o022 or not info.st_flags & 0x00080000:
            return False
        checked = subprocess.run(['/usr/bin/codesign', '--verify', '-R=anchor apple', COMPLETED_XPC],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=.5)
        return checked.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def validate_snapshot(rows, record, services, *, completed=False):
    root = tuple(record['child'])
    retained = set(map(tuple, record['roster']))
    for row in rows.values():
        pin = (row['pid'], row['started'])
        name = Path(row['executable']).name
        if pin in retained or name in BUILD_NAMES or name.startswith(('clang', 'ShaderCompileWorker')):
            raise wire.CapacityError('Live compiler/build/render process prevents administrative release')
        if row['started'] < root[1] or row['executable'] in OS_SERVICES or pin in services:
            continue
        if completed and completed_system_service(row):
            row['verified_completed_system_service'] = True
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
            raise wire.CapacityError(f'Unclassified process {row["pid"]} born after the workload prevents administrative release')


def recover(record, evidence, *, principal, boot, epoch, scan=None, missing=None, service=None, completed=False, unwitnessed=False):
    """@cc [owner:fontanierh,label:safety] administrative-interrupted-compile-release
    The default action MAY abandon only an uncertain exclusive compile. The separate completed-job
    action MAY abandon a nonexclusive job only with its exact bound normal empty terminal receipt,
    monitor bindings and original report hashes. Both MUST require a positive root exit. Only the
    separate unwitnessed-compile action MAY release without that exit, requiring explicit missing-exit
    acknowledgement and exact monitor/report fences for an uncertain exclusive compile. It MUST
    preserve the missing exit, reject combined completed/unwitnessed modes, and record that no root
    exit was observed. All actions MUST require absent root/controller/guards/retained identities and fresh
    complete same-user censuses. Unknown or live workload identities MUST refuse. A recent
    orphan MUST refuse unless it is an exact independently reviewed live launchd service or
    specialized OS worker. Only completed-job recovery MAY additionally exclude the exact
    iCloudHelper XPC executable with PPID 1, root ownership, no group/other write permission,
    SIP protection and verified Apple signature, recording that exclusion. Its census MAY
    record unavailable executable paths only with stable kernel birth/PID/parent/UID observations
    strictly predating the root. All newer identity/query failures MUST refuse.
    Normal close/reconcile MUST NOT use this policy. The witness
    MUST retain the original evidence hashes and operation binding, and MUST NOT certify outputs.
    """
    if completed and unwitnessed:
        raise wire.CapacityError('Administrative recovery modes cannot be combined')
    scan = scan or ((lambda: census(before_root=record['child'][1])) if completed else census)
    missing, service = missing or absent, service or service_pin
    required = ('id', 'nonce', 'epoch', 'boot_id', 'operator_reference', 'administrator', 'services')
    wire.fields(evidence, required + (('guards', 'report_sha256') if completed or unwitnessed else ())
                + (('acknowledge_missing_root_exit',) if unwitnessed else ()))
    request = record['request']
    if (evidence['id'] != request['id'] or evidence['nonce'] != record.get('nonce')
            or evidence['epoch'] != epoch or evidence['boot_id'] != boot):
        raise wire.CapacityError('Administrative interruption recovery was fenced')
    administrator = wire.text(evidence['administrator'])
    reference = wire.text(evidence['operator_reference'], maximum=512)
    if administrator == request.get('owner') or tuple(principal) == tuple(record['principal']):
        raise wire.CapacityError('Administrative recovery owner cannot administratively release itself')
    eligible = (request.get('phase') == 'job' and request.get('performance') is False if completed
                else request.get('phase') == 'compile' and request.get('performance') is True)
    root = wire.identity(record.get('child'))
    root_exited = list(root) in record.get('exited', [])
    if (record['state'] != 'uncertain' or not eligible
            or (not root_exited and not unwitnessed)):
        raise wire.CapacityError('Administrative recovery requires an eligible uncertain job with root exit')
    if unwitnessed and (root_exited or evidence['acknowledge_missing_root_exit'] is not True):
        raise wire.CapacityError('Unwitnessed compile requires explicit acknowledgement of its missing root exit')
    if (completed or unwitnessed) and evidence['guards'] != record['guards']:
        raise wire.CapacityError('Administrative recovery monitor binding changed')
    pins = set(map(tuple, record['roster'])) | {tuple(record['principal']), root}
    pins.update((g['pid'], g['start']) for g in record['guards'].values())
    if any(not missing(pin) for pin in pins):
        raise wire.CapacityError('Administrative recovery still has a live controller, guard or retained process')
    items = evidence['services']
    if type(items) is not list or len(items) > 8:
        raise wire.CapacityError('Invalid workload service exemptions')
    services = {service(item) for item in items}
    reports = {}
    for kind, guard in record['guards'].items():
        raw = wire.private_file(guard['report'], limit=wire.MAX_FRAME, private=False)
        reports[kind] = hashlib.sha256(raw).hexdigest()
    if (completed or unwitnessed) and evidence['report_sha256'] != reports:
        raise wire.CapacityError('Administrative recovery report binding changed')
    if completed:
        terminal = wire.decode(wire.private_file(record['guards']['tree_guard']['report'], limit=wire.MAX_FRAME, private=False))
        validate_completed_terminal(record, terminal)
    observations = []
    for _ in range(2):
        rows = scan()
        validate_snapshot(rows, record, services, completed=completed)
        observations.append(rows)
    # Recheck every exact identity after the complete observations, still in this actor turn.
    if any(not missing(pin) for pin in pins):
        raise wire.CapacityError('Administrative recovery identity appeared during administrative recovery')
    for kind, guard in record['guards'].items():
        raw = wire.private_file(guard['report'], limit=wire.MAX_FRAME, private=False)
        if hashlib.sha256(raw).hexdigest() != reports[kind]:
            raise wire.CapacityError('Original workload reports changed during recovery')
    if unwitnessed and {service(item) for item in items} != services:
        raise wire.CapacityError('Recovery service identities changed during recovery')
    digest = hashlib.sha256(json.dumps(observations, sort_keys=True).encode()).hexdigest()
    return dict(kind=('administrative-unwitnessed-compile' if unwitnessed else
                      'administrative-completed-job' if completed else 'administrative-interruption'),
        root_exit_observed=root_exited, coverage='current-observed-quiescence',
        operator_reference=reference, administrator=administrator, administrative_principal=list(principal),
        nonce=record['nonce'], request_id=request['id'], epoch=epoch, boot_id=boot, observed_at=time.time(),
        checked_identities=len(pins), missing_historical_exits=len(set(map(tuple,record['roster']))-set(map(tuple,record['exited']))),
        ancestry_unknown=record.get('ancestry_unknown',False), original_report_sha256=reports,
        census_sha256=digest, service_exemptions=items, output_certified=False,
        pre_root_path_exemptions=[row for snapshot in observations for row in snapshot.values()
                                  if row.get('executable_unavailable_before_root') is True],
        system_service_exemptions=[row for snapshot in observations for row in snapshot.values()
                                   if row.get('verified_completed_system_service') is True])


def validate_completed_terminal(record, receipt):
    """@cc [owner:fontanierh,label:safety] administrative-completed-job-terminal
    A completed nonexclusive job MUST retain its normal empty terminal receipt bound to the root,
    controller, ceiling and invocation. This permits only explicit quiescence recovery with the
    administrative checks above, never automatic release or reconstructed historical exits.
    """
    import math
    observed, ready = receipt.get('time'), record.get('first_ready')
    if (receipt.get('owner') != record['child'][0] or receipt.get('owner_started') != record['child'][1]
            or receipt.get('controller') != record['principal']
            or receipt.get('state') != 'child_exited' or receipt.get('cleanup_complete') is not True
            or receipt.get('termination_reason') is not None
            or receipt.get('processes') != [] or type(receipt.get('footprint_bytes')) is not int
            or receipt['footprint_bytes'] != 0
            or type(receipt.get('limit_bytes')) is not int or receipt['limit_bytes'] != record.get('limit_bytes')
            or type(receipt.get('peak_bytes')) is not int or not 0 <= receipt['peak_bytes'] <= receipt['limit_bytes']
            or type(observed) not in (int, float) or not math.isfinite(observed)
            or type(ready) not in (int, float) or not math.isfinite(ready)
            or not 0 < ready <= observed <= time.time()):
        raise wire.CapacityError('Completed job requires its bound normal empty terminal cleanup')
