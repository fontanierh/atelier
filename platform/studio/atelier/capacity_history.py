"""Read retained memory-guard observations without importing or consulting the live guard."""
import json
import math
import os
from pathlib import Path
import re
import stat

MAX_FILE_BYTES = 9 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_ENTRIES = 4096
MAX_FAMILIES = 32
MAX_LINES = 100_000
MAX_LINE_BYTES = 8192
MAX_RECORDS = 100_000
MAX_SESSIONS = 128
MAX_LIMIT_CHANGES = 128
SUFFIXES = ('previous.jsonl', 'jsonl', 'json')
WATCHED = re.compile(r'memory-health-([A-Za-z0-9_.-]{1,128})-([0-9]{1,10})\.(previous\.jsonl|jsonl|json)')
LABELS = frozenset(('UnrealEditor', 'UnrealEditor-Cmd', 'ShaderCompileWorker', 'dotnet', 'mono', 'bash', 'sh'))
STATES = frozenset(('running', 'memory_limit', 'test_duration'))
INTEGERS = ('pid', 'process_start', 'footprint_bytes', 'peak_bytes', 'cpu_ticks', 'limit_bytes')
FIELDS = (*INTEGERS, 'elapsed_seconds', 'state')


def integer(value):
    return type(value) is int and 0 <= value <= 2**64 - 1


def normalize(record):
    result = {key: value if integer(value := record.get(key)) else None for key in INTEGERS}
    if result['pid'] == 0:
        result['pid'] = None
    elapsed = record.get('elapsed_seconds')
    try:
        valid = type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= 0
    except OverflowError:
        valid = False
    result['elapsed_seconds'] = elapsed if valid else None
    state = record.get('state')
    result['state'] = state if isinstance(state, str) and state in STATES else None
    return result


class Sessions:
    """Aggregate one file family in retained order; no tree totals or inferred process lifetime."""
    def __init__(self):
        self.items = []
        self.current = None
        self.last_record = None
        self.final_duplicates = 0

    def add(self, record, *, final=False):
        try:
            duplicate = final and record == self.last_record
        except RecursionError:
            duplicate = False
        if duplicate:
            self.final_duplicates += 1
            return True
        value = normalize(record)
        identity = value['pid'], value['process_start']
        elapsed = value['elapsed_seconds']
        current = self.current
        reset = (current is not None and elapsed is not None and current['_elapsed_last'] is not None
                 and elapsed < current['_elapsed_last'])
        if current is None or None in identity or identity != current['_identity'] or reset:
            if len(self.items) >= MAX_SESSIONS:
                return False
            current = {'pid': identity[0], 'process_start': identity[1], 'segment': len(self.items) + 1,
                       'sample_count': 0, 'elapsed_first_seconds': None, 'elapsed_last_seconds': None,
                       'sampled_span_seconds': None, 'max_footprint_bytes': None, 'max_guard_peak_bytes': None,
                       'first_observed_limit_bytes': None, 'limit_changes': [], 'last_recorded_state': None,
                       'cpu_tick_delta': None, 'unknown_fields': set(), 'diagnostics': [],
                       '_identity': identity, '_elapsed_last': None, '_cpu_first': None, '_cpu_last': None,
                       '_cpu_valid': True, '_elapsed_count': 0, '_limit': None}
            self.items.append(current)
            self.current = current
        current['sample_count'] += 1
        self.last_record = record
        current['unknown_fields'].update(key for key in FIELDS if value[key] is None)
        if elapsed is not None:
            if current['elapsed_first_seconds'] is None:
                current['elapsed_first_seconds'] = elapsed
            current['elapsed_last_seconds'] = current['_elapsed_last'] = elapsed
            current['_elapsed_count'] += 1
        for source, target in (('footprint_bytes', 'max_footprint_bytes'), ('peak_bytes', 'max_guard_peak_bytes')):
            amount = value[source]
            if amount is not None:
                current[target] = max(current[target] or 0, amount)
        footprint, peak = value['footprint_bytes'], value['peak_bytes']
        if footprint is not None and peak is not None and peak < footprint:
            if 'guard peak below retained footprint' not in current['diagnostics']:
                current['diagnostics'].append('guard peak below retained footprint')
        ticks = value['cpu_ticks']
        if ticks is None or current['_cpu_last'] is not None and ticks < current['_cpu_last']:
            current['_cpu_valid'] = False
        if ticks is not None and current['_cpu_last'] is not None and ticks < current['_cpu_last']:
            if 'CPU ticks decreased within retained session' not in current['diagnostics']:
                current['diagnostics'].append('CPU ticks decreased within retained session')
        if ticks is not None:
            if current['_cpu_first'] is None:
                current['_cpu_first'] = ticks
            current['_cpu_last'] = ticks
        limit = value['limit_bytes']
        if limit is not None:
            if current['_limit'] is None:
                current['first_observed_limit_bytes'] = limit
            elif limit != current['_limit']:
                if len(current['limit_changes']) < MAX_LIMIT_CHANGES:
                    current['limit_changes'].append({'sample': current['sample_count'],
                                                    'from_bytes': current['_limit'], 'to_bytes': limit})
                elif 'limit change detail capped' not in current['diagnostics']:
                    current['diagnostics'].append('limit change detail capped')
            current['_limit'] = limit
        current['last_recorded_state'] = value['state']
        return True

    def report(self):
        result = []
        for item in self.items:
            if item['_elapsed_count'] >= 2:
                item['sampled_span_seconds'] = item['elapsed_last_seconds'] - item['elapsed_first_seconds']
            if item['_cpu_valid'] and item['sample_count'] >= 2:
                item['cpu_tick_delta'] = item['_cpu_last'] - item['_cpu_first']
            result.append({key: sorted(value) if isinstance(value, set) else value
                           for key, value in item.items() if not key.startswith('_')})
        return result


def object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def read_file(directory_fd, name, budget):
    """Bound one regular file without following its symlink; omit raw text and error details."""
    if budget <= 0:
        return None, {'status': 'unread', 'reason': 'invocation byte limit reached'}, 0
    data = b''
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=directory_fd)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                return None, {'status': 'unread', 'reason': 'not a regular file'}, 0
            data = stream.read(min(MAX_FILE_BYTES, budget))
            after = os.fstat(stream.fileno())
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None, {'status': 'missing'}, len(data)
    except OSError:
        return None, {'status': 'unread', 'reason': 'file could not be read'}, len(data)
    identity = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    truncated = len(data) < before.st_size
    changed = identity(before) != identity(after) or identity(after) != identity(current)
    return data, {'status': 'partial' if truncated or changed else 'read', 'bytes_read': len(data),
                  'byte_limited': truncated, 'changed_while_reading': changed}, len(data)


def consume(data, source, sessions, remaining):
    """Parse bounded records, retaining only normalized aggregate values."""
    malformed, parsed, limited = 0, 0, False
    if source == 'json':
        chunks = [data]
        limited = len(data) > MAX_LINE_BYTES or data.count(b'\n') > MAX_LINES
    else:
        chunks = data.splitlines(keepends=True)
    for number, chunk in enumerate(chunks, 1):
        if limited or number > MAX_LINES or parsed >= remaining or len(chunk) > MAX_LINE_BYTES:
            limited = True
            break
        if source != 'json' and not chunk.endswith(b'\n'):
            malformed += 1
            break
        if source != 'json' and not chunk.strip():
            continue
        try:
            record = json.loads(chunk, object_pairs_hook=object_pairs)
            if not isinstance(record, dict):
                raise ValueError
        except (ValueError, UnicodeError, RecursionError):
            malformed += 1
            continue
        parsed += 1
        if not sessions.add(record, final=source == 'json'):
            limited = True
            break
    return {'parsed_records': parsed, 'malformed_records': malformed,
            'record_limited': limited}, parsed


def inspect(directory):
    """@cc [owner:fontanierh,label:correctness] retained-guard-observations
    Inspection MUST only read bounded retained files, with no native guard imports, process scans,
    writes or admission. Sessions MUST separate process identity changes and elapsed resets.
    Missing observations MUST stay unknown; process footprints MUST NOT be summed into a job peak.
    Historical state and sampled spans MUST NOT imply duration, success, liveness or admission.
    """
    result = {'schema': 1, 'historical': True, 'read_status': 'complete', 'families': [], 'diagnostics': [],
              'limitations': ['Only retained samples are observed; missing files and overwritten rotations limit coverage.',
                              'Sampled spans and last states do not establish duration, success, liveness or admission.',
                              'Process footprints remain separate; the root is not a job-wide memory requirement.',
                              'CPU deltas are raw recorded ticks; no time unit or utilization is inferred.']}
    try:
        fd = os.open(Path(directory), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        result.update(read_status='unread', diagnostics=['directory could not be read'])
        return result
    try:
        stems = {}
        try:
            with os.scandir(fd) as entries:
                for index, entry in enumerate(entries):
                    if index >= MAX_ENTRIES:
                        result['diagnostics'].append('directory entry limit reached')
                        break
                    match = WATCHED.fullmatch(entry.name)
                    if match:
                        stems.setdefault(entry.name.rsplit('.', 2)[0] if match[3] == 'previous.jsonl'
                                         else entry.name.rsplit('.', 1)[0], match[1])
        except OSError:
            result['diagnostics'].append('directory entries could not be read')
        if len(stems) > MAX_FAMILIES - 1:
            result['diagnostics'].append('watched family limit reached')
        families = [('memory-health', None)] + sorted(stems.items())[:MAX_FAMILIES - 1]
        remaining_bytes, remaining_records = MAX_TOTAL_BYTES, MAX_RECORDS
        for family_index, (stem, label) in enumerate(families):
            sessions = Sessions()
            family = {'kind': 'owned' if family_index == 0 else 'watched', 'index': family_index,
                      'label': label if label in LABELS else 'other' if label else None, 'files': []}
            for source in SUFFIXES:
                data, status, used = read_file(fd, f'{stem}.{source}', remaining_bytes)
                remaining_bytes -= used
                if data is not None:
                    observations, parsed = consume(data, source, sessions, remaining_records)
                    remaining_records -= parsed
                    status.update(observations)
                    if observations['malformed_records'] or observations['record_limited']:
                        status['status'] = 'partial'
                    if not observations['parsed_records']:
                        status.update(status='partial', reason='no retained records parsed')
                family['files'].append({'source': source, **status})
            family.update(sessions=sessions.report(), deduplicated_final_records=sessions.final_duplicates)
            result['families'].append(family)
        if result['diagnostics'] or any(file['status'] != 'read'
                                        for family in result['families'] for file in family['files']):
            result['read_status'] = 'partial'
        return result
    finally:
        os.close(fd)


def show(directory, as_json=False, echo=print):
    report = inspect(directory)
    if as_json:
        echo(json.dumps(report, indent=2))
        return 0
    echo('Historical retained guard observations; no duration, success, liveness or admission is established.')
    echo('Process footprints are separate. CPU deltas are raw ticks with no inferred unit.')
    echo(f"Read coverage: {report['read_status']}")
    for diagnostic in report['diagnostics']:
        echo('  ' + diagnostic)
    for family in report['families']:
        echo(f"{family['kind']} family {family['index']}" + (f" ({family['label']})" if family['label'] else ''))
        for source in family['files']:
            echo(f"  {source['source']}: {source['status']}")
            if source.get('reason'):
                echo('    ' + source['reason'])
            if source.get('malformed_records'):
                echo(f"    {source['malformed_records']} malformed records omitted")
        for session in family['sessions']:
            display = lambda key: 'unknown' if session[key] is None else str(session[key])
            echo(f"  pid {display('pid')}, start {display('process_start')}, segment {session['segment']}: "
                 f"{session['sample_count']} samples; sampled span {display('sampled_span_seconds')} s")
            echo(f"    max retained footprint {display('max_footprint_bytes')} bytes; "
                 f"max guard-reported peak {display('max_guard_peak_bytes')} bytes")
            echo(f"    last recorded state {display('last_recorded_state')}; CPU tick delta {display('cpu_tick_delta')}")
            echo(f"    first observed limit {display('first_observed_limit_bytes')} bytes; "
                 f"{len(session['limit_changes'])} retained limit changes")
            for change in session['limit_changes']:
                echo(f"      observed limit change at sample {change['sample']}: "
                     f"{change['from_bytes']} to {change['to_bytes']} bytes")
            if session['unknown_fields']:
                echo('    unknown fields in retained samples: ' + ', '.join(session['unknown_fields']))
            for diagnostic in session['diagnostics']:
                echo('    ' + diagnostic)
    return 0
