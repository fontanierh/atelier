"""Bounded, read-only observations from retained Unreal derived-data-cache logs."""
import io
import json
import math
import os
import re
import stat

MAX_LOG_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_LINES = 100_000
MAX_LINE = 8192
MAX_SUMMARIES = 16
COUNTS = frozenset('''TotalGetHits TotalGetMisses TotalGets TotalPutHits TotalPutMisses TotalPuts
    LocalGetHits LocalGetMisses LocalGetTotal SharedGetHits SharedGetTotal ZenLocalGetHits ZenLocalGetTotal
    ZenRemoteGetHits ZenRemoteGetTotal CloudGetHits CloudGetTotal'''.split())
FRACTIONS = frozenset('''TotalGetHitPct GetMissPct TotalPutHitPct PutMissPct LocalGetHitPct SharedGetHitPct
    ZenLocalGetHitPct ZenRemoteGetHitPct CloudGetHitPct'''.split())
FLAGS = frozenset('HasLocalCache HasSharedCache HasCloudCache HasZenCache'.split())
FIELDS = COUNTS | FRACTIONS | FLAGS
GET_TOTALS = ('TotalGetHits', 'TotalGetMisses', 'TotalGets')
CATEGORY = re.compile(r'(?:^|\s|\])(LogDerivedDataCache|LogCookStats):\s*(?:Display:\s*)?(.*)$')


def configuration(message):
    """Allowlisted node/state pairs only; paths, endpoints and namespaces never leave the parser."""
    match = re.fullmatch(r'(ZenLocal|ZenShared): Using ZenServer HTTP service at .+ with namespace .+\. Status: OK!\.', message)
    if match:
        return match[1], 'available'
    match = re.fullmatch(r'(Local|Shared): Using data cache path .+: Writable', message)
    if match:
        return match[1], 'writable'
    match = re.fullmatch(r"(ZenLocal|ZenShared|Cloud): Disabled because Host is set to 'None'", message)
    if match:
        return match[1], 'disabled'
    if message == 'Shared: Disabled because no path is configured.':
        return 'Shared', 'disabled'
    match = re.fullmatch(r'(ProjectPak|InstalledProjectPak|Pak|EnginePak|EnterprisePak): Pak cache file .+ not found, will not use a pak cache\.', message)
    if match:
        return match[1], 'unavailable'
    if re.fullmatch(r'.+: Opened pak cache for reading\. \(\d+ MiB\)', message):
        return 'Pak (unspecified)', 'readable'
    return None


def value_for(key, text):
    if key in FLAGS:
        if text not in ('true', 'false'):
            raise ValueError
        return text == 'true'
    if key in COUNTS:
        if not re.fullmatch(r'[0-9]{1,19}', text) or int(text) > 2**63 - 1:
            raise ValueError
        return int(text)
    value = float(text)
    if len(text) > 32 or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError
    return value


def finish(summary, *, closed):
    metrics, diagnostics = summary['metrics'], summary['diagnostics']
    groups = [(*GET_TOTALS, 'TotalGetHitPct', 'GetMissPct'),
              ('TotalPutHits', 'TotalPutMisses', 'TotalPuts', 'TotalPutHitPct', 'PutMissPct'),
              ('LocalGetHits', 'LocalGetMisses', 'LocalGetTotal', 'LocalGetHitPct')]
    groups += [(f'{prefix}GetHits', None, f'{prefix}GetTotal', f'{prefix}GetHitPct')
               for prefix in ('Shared', 'ZenLocal', 'ZenRemote', 'Cloud')]
    for hits, misses, total, *fractions in groups:
        h, m, t = metrics[hits], metrics.get(misses), metrics[total]
        if t is not None and (h is not None and h > t or m is not None and m > t
                              or h is not None and m is not None and h + m != t):
            diagnostics.append(f'inconsistent {total}')
            for key in (hits, misses, total, *fractions):
                if key:
                    metrics[key] = None
        elif t:
            for field, count in zip(fractions, (h, m)):
                fraction = metrics[field]
                if fraction is not None and count is not None and abs(fraction - count / t) > 0.000001:
                    diagnostics.append(f'inconsistent {field}')
                    metrics[field] = None
    if not closed:
        diagnostics.append('summary has no closing boundary')
    summary['status'] = ('incomplete' if diagnostics or any(metrics[key] is None for key in GET_TOTALS) else 'complete')


def parse(lines):
    """@cc [owner:fontanierh,label:correctness] observed-ddc-statistics
    DDC observations MUST NOT certify execution or current configuration. Missing, malformed or conflicting
    statistics MUST remain unknown. Repeated summaries and overlapping backend counters MUST NOT be summed.
    Returned observations MUST exclude raw log text, filesystem paths, URLs, namespaces and launcher arguments.
    """
    result = {'configuration': [], 'summaries': [], 'diagnostics': [], 'coverage': 'complete'}
    nodes, summary, seen = {}, None, set()
    for line_number, line in enumerate(lines, 1):
        if line_number > MAX_LINES or len(line) > MAX_LINE:
            result['diagnostics'].append('log parsing limit reached')
            result['coverage'] = 'partial'
            break
        match = CATEGORY.search(line.rstrip('\r\n'))
        if not match:
            continue
        category, message = match.groups()
        if category == 'LogDerivedDataCache':
            observed = configuration(message)
            if observed:
                node, state = observed
                observations = nodes.setdefault(node, {})
                observations.setdefault(state, line_number)
            continue
        if message == 'DDC Summary Stats':
            if summary is not None:
                finish(summary, closed=False)
            if len(result['summaries']) == MAX_SUMMARIES:
                summary = None
                result['diagnostics'].append('summary limit reached')
                result['coverage'] = 'partial'
                break
            summary = {'line': line_number, 'metrics': dict.fromkeys(sorted(FIELDS)), 'diagnostics': []}
            result['summaries'].append(summary)
            seen = set()
        elif summary is not None:
            if not message.strip() or message == 'DDC Resource Stats':
                finish(summary, closed=True)
                summary = None
                continue
            key, separator, text = message.partition('=')
            key, text = key.strip(), text.strip()
            if not separator:
                finish(summary, closed=False)
                summary = None
                continue
            if key not in FIELDS:
                continue
            try:
                value = value_for(key, text)
                if key in seen and summary['metrics'][key] != value:
                    raise ValueError
            except (ValueError, OverflowError):
                value = None
                diagnostic = f'invalid or conflicting {key}'
                if diagnostic not in summary['diagnostics']:
                    summary['diagnostics'].append(diagnostic)
            seen.add(key)
            summary['metrics'][key] = value
    if summary is not None:
        finish(summary, closed=False)
    result['configuration'] = [
        {'backend': node, 'state': next(iter(states)) if len(states) == 1 else 'mixed',
         'observations': [{'state': state, 'line': line} for state, line in states.items()]}
        for node, states in nodes.items()]
    return result


def read_log(path, budget):
    """Read a bounded prefix of one regular file; live/replaced logs are marked unverified and partial."""
    if budget <= 0:
        return {'coverage': 'unread', 'reason': 'invocation byte limit reached'}, 0
    data = b''
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                return {'coverage': 'unread', 'reason': 'not a regular log'}, 0
            data = stream.read(min(MAX_LOG_BYTES, budget))
            after = os.fstat(stream.fileno())
        current = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return {'coverage': 'unread', 'reason': 'log not found'}, len(data)
    except OSError:
        return {'coverage': 'unread', 'reason': 'log could not be read'}, len(data)
    truncated = len(data) < before.st_size
    text = data.decode('utf-8', errors='replace')
    if truncated:
        text = text[:text.rfind('\n') + 1]  # A cut record must not become an observed value.
    result = parse(io.StringIO(text))
    identity = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    changed = identity(before) != identity(after) or identity(after) != identity(current)
    if truncated or changed:
        result['coverage'] = 'partial'
        result['diagnostics'].append('log changed while reading' if changed else 'log byte limit reached')
    return {**result, 'bytes_read': len(data), 'log_bytes': before.st_size, 'modified_at': before.st_mtime}, len(data)


def inspect(ctx, steps, wanted=()):
    """Read retained logs only. No DDC directory, runtime, stamp or build input is inspected."""
    from .build import UnrealPackage, UnrealScript, order
    reports, remaining = [], MAX_TOTAL_BYTES
    for step in order(steps, list(wanted)):
        if not any(isinstance(command, (UnrealScript, UnrealPackage)) for command in step.commands):
            continue
        guard = ctx.logs / f'{step.name}.guard' / 'stdout.log'
        fallback = ctx.logs / f'{step.name}.log'
        path = guard
        try:
            guard.lstat()
        except FileNotFoundError:
            path = fallback
        except OSError:
            pass  # An unreadable guard log must not silently select another execution's log.
        report, used = read_log(path, remaining)
        remaining -= used
        reports.append({'step': step.name, 'source': '<build>/logs/' + path.relative_to(ctx.logs).as_posix(),
                        'scope': 'last guarded command' if path == guard else 'retained step log', **report})
    return {'schema': 1, 'game': ctx.game, 'historical': True,
            'verification': 'observed logs; execution success and current runtime unverified', 'steps': reports}


def show(game, wanted=(), *, as_json=False, echo=print):
    from . import build
    ctx = build.Context(game, create=False)
    report = inspect(ctx, build.load_recipe(game).steps(ctx), wanted)
    if as_json:
        echo(json.dumps(report, indent=2))
        return 0
    echo('Historical DDC log observations; execution success and current runtime are unverified.')
    echo('Backend counters can overlap. Repeated summaries are separate observations, never summed.')
    for step in report['steps']:
        echo(f"{step['step']:34s} {step['coverage']}; {step['scope']}")
        if 'reason' in step:
            echo('  ' + step['reason'])
            continue
        for node in step['configuration']:
            echo(f"  {node['backend']}: {node['state']}")
        if not step['configuration']:
            echo('  supported cache configuration not recorded')
        if not step['summaries']:
            echo('  DDC get totals not recorded')
        for summary in step['summaries']:
            metrics = summary['metrics']
            show_value = lambda key: 'unknown' if metrics[key] is None else str(metrics[key])
            echo(f"  summary at line {summary['line']} ({summary['status']}): "
                 f"hits {show_value('TotalGetHits')}, misses {show_value('TotalGetMisses')}, gets {show_value('TotalGets')}")
            for diagnostic in summary['diagnostics']:
                echo('    ' + diagnostic)
        for diagnostic in step['diagnostics']:
            echo('  ' + diagnostic)
    return 0
