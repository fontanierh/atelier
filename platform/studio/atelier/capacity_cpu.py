"""Read-only CPU observations of the pinned processes in one live aggregate guard report."""
import ctypes
import json
import math
import os
from pathlib import Path
import stat
import sys
import time

MAX_REPORT_BYTES = 4 * 1024 * 1024
MAX_PROCESSES = 4096
MAX_AGE = 3.
SCOPE = ('Sampled owned identities only; first observations, exit tails and between-poll helpers '
         'may be missed. Shared services excluded by the guard. Not a peak bound or admission authority.')


class _Timebase(ctypes.Structure):
    _fields_ = [('numer', ctypes.c_uint32), ('denom', ctypes.c_uint32)]


def timebase():
    lib = ctypes.CDLL('/usr/lib/libSystem.B.dylib')
    lib.mach_timebase_info.argtypes = [ctypes.POINTER(_Timebase)]
    lib.mach_timebase_info.restype = ctypes.c_int
    value = _Timebase()
    if lib.mach_timebase_info(ctypes.byref(value)) or not value.numer or not value.denom:
        raise OSError('Cannot read the Darwin CPU timebase')
    return value.numer, value.denom


def integer(value):
    return type(value) is int and 0 < value <= 2**64 - 1


def read_report(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_REPORT_BYTES:
            raise ValueError('CPU observation requires a bounded regular guard report')
        raw = stream.read(MAX_REPORT_BYTES + 1)
    if len(raw) > MAX_REPORT_BYTES:
        raise ValueError('Guard report exceeds the CPU observation bound')
    value = json.loads(raw)
    if (not isinstance(value, dict) or not integer(value.get('owner')) or not integer(value.get('owner_started'))
            or not isinstance(value.get('state'), str) or not isinstance(value.get('processes'), list)
            or len(value['processes']) > MAX_PROCESSES):
        raise ValueError('CPU observation requires an aggregate guard identity and process roster')
    seen = set()
    for item in value['processes']:
        if not isinstance(item, dict) or not integer(item.get('pid')) or not integer(item.get('started')):
            raise ValueError('Guard process identity is invalid')
        pin = item['pid'], item['started']
        if pin in seen:
            raise ValueError('Guard process identity is duplicated')
        seen.add(pin)
    return value


def age(report, now, wall):
    stamp = report.get('observed_monotonic')
    current = now
    if stamp is None:
        stamp, current = report.get('time'), wall
    if type(stamp) not in (int, float) or not math.isfinite(stamp):
        raise ValueError('Guard observation time is missing or invalid')
    return current - stamp


class Counters:
    def __init__(self, scale):
        self.scale, self.previous, self.at = scale, {}, None

    def sample(self, report, usage, now):
        interval = None if self.at is None else now - self.at
        if interval is not None and interval <= 0:
            raise ValueError('CPU observation clock did not advance')
        current, processes, unavailable, new, reset = {}, [], [], [], []
        delta, paired = 0., 0
        for item in report['processes']:
            pin = item['pid'], item['started']
            try:
                value = usage(pin[0])
            except OSError:
                unavailable.append(dict(pid=pin[0], started=pin[1], reason='usage unavailable'))
                continue
            if value.started != pin[1]:
                unavailable.append(dict(pid=pin[0], started=pin[1], reason='identity changed'))
                continue
            ticks = value.user + value.system
            if type(ticks) is not int or ticks < 0:
                unavailable.append(dict(pid=pin[0], started=pin[1], reason='invalid CPU counter'))
                continue
            current[pin] = ticks
            seconds = None
            if pin not in self.previous:
                new.append(list(pin))
            elif ticks < self.previous[pin]:
                reset.append(list(pin))
            else:
                seconds = (ticks - self.previous[pin]) * self.scale
                delta += seconds
                paired += 1
            processes.append(dict(pid=pin[0], started=pin[1], cpu_ticks=ticks, interval_cpu_seconds=seconds))
        departed = [list(pin) for pin in self.previous if pin not in current]
        self.previous, self.at = current, now
        return dict(interval_seconds=interval, observed_cpu_units=delta / interval if interval and paired else None,
                    interval_cpu_seconds=delta if paired else None, paired_identities=paired, processes=processes,
                    new_identities=new, unavailable=unavailable, counter_resets=reset,
                    departed_with_unobserved_tail=departed)


def observe(report, output, *, usage, numer, denom, seconds=60., interval=1.,
            clock=time.monotonic, wall=time.time, sleep=time.sleep, echo=print):
    """@cc [owner:fontanierh,label:correctness] owned-cpu-observation
    Measurements MUST remain bound to one guard root and each PID's birth identity. CPU deltas
    MUST use the host timebase and only paired matching identities; unavailable data MUST NOT
    become zero usage. Coverage gaps MUST remain explicit. This diagnostic MUST NOT launch or
    signal jobs, alter admission/guards, certify completion or establish a hard profile bound.
    """
    if (not all(type(v) in (int, float) and math.isfinite(v) for v in (seconds, interval))
            or not .25 <= interval <= 5 or not 2 * interval <= seconds <= 900):
        raise ValueError('CPU observation needs 0.25–5s intervals and a duration of 2 intervals to 900s')
    if not integer(numer) or not integer(denom):
        raise ValueError('CPU observation needs a positive Darwin timebase')
    report = Path(report)
    initial = read_report(report)
    root = initial['owner'], initial['owner_started']
    initial_age = age(initial, clock(), wall())
    if initial['state'] != 'running' or not 0 <= initial_age <= MAX_AGE:
        raise ValueError('CPU observation requires a fresh running aggregate guard')
    if root not in {(item['pid'], item['started']) for item in initial['processes']}:
        raise ValueError('Running aggregate guard does not include its pinned root')
    owner = usage(root[0])
    if owner.started != root[1] or owner.exited:
        raise ValueError('Guard root is no longer the pinned process')
    output = Path(output)
    output.mkdir(parents=True, mode=0o700)  # Existing evidence is never overwritten.
    counter = Counters(numer / denom / 1e9)
    began, spoken = clock(), None
    rows, cpu, span, maximum = 0, 0., 0., None
    gaps = dict(new_identities=0, unavailable=0, counter_resets=0, departed_with_unobserved_tail=0)
    ending, terminal, error = 'duration', None, None
    try:
        with (output / 'samples.jsonl').open('x') as stream:
            while True:
                current = read_report(report)
                now = clock()  # The guard may atomically publish a newer report during our read.
                if (current['owner'], current['owner_started']) != root:
                    raise ValueError('Guard invocation changed; CPU observation stopped')
                report_age = age(current, now, wall())
                if not 0 <= report_age <= MAX_AGE:
                    raise ValueError('Guard report became stale; CPU observation stopped')
                row = counter.sample(current, usage, now)
                row.update(time=wall(), elapsed_seconds=now-began, guard_state=current['state'], guard_age_seconds=report_age)
                stream.write(json.dumps(row) + '\n');stream.flush()
                rows += 1
                for key in gaps:
                    gaps[key] += len(row[key])
                units = row['observed_cpu_units']
                if units is not None:
                    maximum = max(maximum or 0, units)
                    cpu += row['interval_cpu_seconds']
                    span += row['interval_seconds']
                if spoken is None or now - spoken >= 30:
                    observed = 'unavailable' if units is None else f'{units:.2f}'
                    echo(f'CPU observation: {rows} samples, {now-began:.1f}/{seconds:g}s, '
                         f'{observed} observed CPU units, {len(row["unavailable"])} unavailable identities')
                    spoken = now
                if current['state'] != 'running':
                    ending, terminal = 'guard_terminal', current['state']
                    break
                if clock() - began >= seconds:
                    break
                sleep(min(interval, max(0, seconds - (clock() - began))))
    except BaseException as failure:
        ending, error = 'observation_error', type(failure).__name__
        raise
    finally:
        summary = dict(schema=1, root=dict(pid=root[0], started=root[1]), mach_timebase=dict(numer=numer, denom=denom),
                       requested_seconds=seconds, elapsed_seconds=clock()-began, samples=rows,
                       ending=ending, terminal_state=terminal, error=error, observed_cpu_seconds=cpu if span else None,
                       paired_span_seconds=span, max_observed_cpu_units=maximum,
                       mean_observed_cpu_units=cpu/span if span else None, gaps=gaps,
                       coverage_complete=False, scope=SCOPE)
        (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    return summary


def main(folder, output, *, seconds=60., interval=1., as_json=False):
    if sys.platform != 'darwin':
        raise ValueError('Live CPU observation currently supports macOS only')
    from .safety.process_tree import usage
    numer, denom = timebase()
    result = observe(Path(folder) / 'memory-health-tree.json', output, usage=usage,
                     numer=numer, denom=denom, seconds=seconds, interval=interval,
                     echo=lambda text: print(text, file=sys.stderr, flush=True))
    if as_json:
        print(json.dumps(result, indent=2))
    else:
        maximum = result['max_observed_cpu_units']
        shown = 'unavailable' if maximum is None else f'{maximum:.2f}'
        print(f'{result["samples"]} samples; maximum observed {shown} CPU units; {result["ending"]}. '
              f'Incomplete coverage; evidence: {output}')
    return 0
