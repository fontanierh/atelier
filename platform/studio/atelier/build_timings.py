"""Historical build timings. Diagnostics never participate in product certification or cache keys."""
import io
import json
import math
import os
import stat
import uuid

PREFIX = 'ATELIER_PHASE '
MAX_RECORDS = 1000
MAX_PAYLOAD = 8192
MAX_DEPTH = 32
LAUNCH_REPORT = 'execution-timings.json'


def clear_launch_report(folder):
    """Only consume a new invocation's diagnostics; an unreadable old receipt stays unknown."""
    try:
        (folder / LAUNCH_REPORT).unlink(missing_ok=True)
        return True
    except OSError:
        return False


def launch_receipt(folder):
    """Read bounded optional launcher diagnostics, never a certificate or a reason to fail a build."""
    try:
        fd = os.open(folder / LAUNCH_REPORT, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 8192:
                return None
            value = json.loads(stream.read(8193))
        if (not isinstance(value, dict) or set(value) != {'schema', 'invocation_id', 'admission_seconds',
                                                        'child_lifetime_seconds', 'execution_seconds'}
                or type(value['schema']) is not int or value['schema'] != 1
                or uuid.UUID(value['invocation_id']).hex != value['invocation_id']):
            return None
        for name in ('admission_seconds', 'child_lifetime_seconds', 'execution_seconds'):
            if value[name] is not None and not number(value[name]):
                return None
        execution, lifetime = value['execution_seconds'], value['child_lifetime_seconds']
        if execution is not None and (lifetime is None or execution > lifetime):
            return None
        return value
    except (OSError, ValueError, TypeError, AttributeError, OverflowError, RecursionError):
        return None


def number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def label(value):
    return isinstance(value, str) and 0 < len(value) <= 128 and value.isprintable()


def parse_phases(text, *, allow_echo=False):
    """@cc [owner:fontanierh,label:correctness] diagnostic-phase-records
    Malformed phase records MUST remain diagnostics, never build-success or failure signals.
    An unmatched or structurally invalid interval MUST NOT be assigned a guessed duration.

    Read one command's ordered, nested intervals, or None when absent.
    Stop at the first invalid record: retain completed intervals and leave open ones unmeasured.
    Unreal may echo a line with another log prefix; only adjacent identical records are collapsed.
    """
    if PREFIX not in text:
        return None
    phases, active, starts, diagnostics = [], [], {}, []
    previous, latest, count = None, 0., 0
    for line_number, line in enumerate(io.StringIO(text), 1):
        _, separator, payload = line.partition(PREFIX)
        if not separator:
            previous = None
            continue
        count += 1
        try:
            if count > MAX_RECORDS or len(payload) > MAX_PAYLOAD:
                raise ValueError('phase record limit exceeded')
            event = json.loads(payload)
            if not isinstance(event, dict) or not label(event.get('id')) or not number(event.get('at')):
                raise ValueError('phase needs a short id and a finite nonnegative timestamp')
            kind, identity, at = event.get('event'), event['id'], event['at']
            if kind == 'begin':
                if (set(event) - {'event', 'id', 'at', 'name', 'parent'} or not label(event.get('name'))
                        or event.get('parent') is not None and not label(event['parent'])):
                    raise ValueError('invalid phase begin')
            elif kind == 'end':
                if set(event) != {'event', 'id', 'at', 'ok'} or type(event['ok']) is not bool:
                    raise ValueError('invalid phase end')
            else:
                raise ValueError('unknown phase event')
            if allow_echo and event == previous:
                continue
            previous = event
            if at < latest:
                raise ValueError('phase clock moved backwards')
            latest = at
            if kind == 'begin':
                parent = active[-1]['id'] if active else None
                if identity in starts or event.get('parent') != parent or len(active) >= MAX_DEPTH:
                    raise ValueError('duplicate id, incorrect parent or excessive nesting')
                phase = {'id': identity, 'name': event['name'], 'parent': parent,
                         'seconds': None, 'ok': None, 'status': 'incomplete'}
                phases.append(phase)
                starts[identity] = at
                active.append(phase)
            else:
                if not active or active[-1]['id'] != identity:
                    raise ValueError('phase end does not match the current open phase')
                active.pop().update(seconds=round(at - starts[identity], 6), ok=event['ok'], status='complete')
        except (ValueError, TypeError, OverflowError, RecursionError) as error:
            diagnostics.append(f'line {line_number}: {error}')
            break
    if not count:
        return None
    if active:
        diagnostics.append(f'{len(active)} phase(s) have no valid end')
    return {'schema': 1, 'status': 'incomplete' if diagnostics else 'complete',
            'phases': phases, 'diagnostics': diagnostics}


def producer_receipt(stamp):
    """The historical producer, without confusing a restoration or touch with execution.

    Reuse and the legacy pool copy stamps: their producer duration remains useful, but their
    restoration duration was not recorded. Portable restores carry an optional local receipt.
    """
    if stamp.get('touched'):
        return None
    source = stamp.get('producer_receipt') if stamp.get('restored_from') else stamp
    if not isinstance(source, dict) or not number(source.get('seconds')):
        return None
    commands = source.get('commands')
    if not isinstance(commands, list) or len(commands) > MAX_RECORDS:
        return None  # Older stamps without command receipts have unknown execution provenance.
    return {'time': source.get('time'), 'seconds': source['seconds'], 'commands': commands}


def inspect(ctx, steps, wanted=()):
    """@cc [owner:fontanierh,label:correctness] historical-timings-only
    Timing measurements MUST come only from historical stamps; inspection MUST NOT run actions, verify current
    outputs, hash inputs, create directories, restore products or acquire render capacity.
    Missing producer timings MUST remain unknown; restore durations MUST NOT stand in for them.
    """
    from .build import order
    from .build_plan import read_stamp
    result = []
    for step in order(steps, list(wanted)):
        stamp = read_stamp(ctx.stamps / f'{step.name}.json')
        if (ctx.stamps / f'{step.name}.restore.json').exists():
            stamp, kind = {}, 'interrupted restoration'
        elif not stamp:
            kind = 'not recorded'
        elif stamp.get('touched'):
            kind = 'touched'
        elif stamp.get('reused_from') or stamp.get('pooled_from'):
            kind = 'copied stamp'
        elif stamp.get('restored_from'):
            kind = 'cache restore'
        else:
            kind = 'execution' if producer_receipt(stamp) is not None else 'legacy stamp'
        seconds = stamp.get('seconds') if kind in ('execution', 'cache restore') else None
        result.append({'step': step.name, 'last_action': kind, 'time': stamp.get('time'),
                       'seconds': seconds if number(seconds) else None, 'producer': producer_receipt(stamp)})
        if kind == 'cache restore' and stamp.get('restore_source') in ('local', 'https'):
            result[-1]['restore_source'] = stamp['restore_source']
    return {'schema': 1, 'game': ctx.game, 'historical': True, 'steps': result}


def duration(value):
    return f'{value:.3f} s' if number(value) else 'not recorded'


def show(game, wanted=(), *, as_json=False, echo=print):
    from . import build
    ctx = build.Context(game, create=False)
    report = inspect(ctx, build.load_recipe(game).steps(ctx), wanted)
    if as_json:
        echo(json.dumps(report, indent=2))
        return 0
    echo('Historical successful receipts; current inputs and outputs are not checked. Phase times include nested work.')
    for item in report['steps']:
        echo(f"{item['step']:34s} {item['last_action']}: {duration(item['seconds'])}")
        if item['last_action'] == 'cache restore':
            source = {'local': 'local store', 'https': 'HTTPS fetched during this build'}.get(item.get('restore_source'), 'not recorded')
            echo(f'  restore source: {source}')
        producer = item['producer']
        if producer is None:
            echo('  producer timing not recorded')
            continue
        if item['last_action'] != 'execution':
            echo(f"  producer execution: {duration(producer['seconds'])}")
        for command in producer['commands']:
            if not isinstance(command, dict):
                continue
            if command.get('scope') == 'batch action':
                scope = ' (batch action; shared startup/shutdown and host verification excluded)'
            elif command.get('scope') == 'command invocation':
                scope = ' (command invocation)'
            else:
                scope = ' (timing scope not recorded)'
            echo(f"  {command.get('kind', 'command')}: {duration(command.get('seconds'))}{scope}")
            launch = command.get('launcher')
            if isinstance(launch, dict):
                echo(f"    admission and guard setup: {duration(launch.get('admission_seconds'))}")
                echo(f"    child lifetime (includes gated waiting): {duration(launch.get('child_lifetime_seconds'))}")
                echo(f"    command execution: {duration(launch.get('execution_seconds'))}")
            receipt = command.get('phases')
            if not isinstance(receipt, dict) or not isinstance(receipt.get('phases'), list):
                echo('    phases not recorded')
                continue
            cook = receipt.get('cook')
            if isinstance(cook, dict):
                decision = cook.get('decision') if isinstance(cook.get('decision'), dict) else {}
                known = lambda value: 'unknown' if value is None else value
                echo(f"    cook requested {cook.get('requested', 'unknown')}; effective {decision.get('mode', 'unknown')}; "
                     f"modern dependencies {known(cook.get('modern_dependencies'))}; validation {known(cook.get('validated'))}")
                counts = cook.get('counts') if isinstance(cook.get('counts'), dict) else {}
                echo(f"    packages cooked {known(counts.get('cooked'))}; incrementally skipped {known(counts.get('incrementally_skipped'))}")
                uat = cook.get('uat_seconds') if isinstance(cook.get('uat_seconds'), dict) else {}
                echo(f"    cooker session: {duration(cook.get('cooker_seconds'))}")
                for name, seconds in uat.items():
                    echo(f'    UAT {name}: {duration(seconds)}')
                echo('    UAT phase timings overlap nested subprocess metrics; do not add them twice')
            for phase in receipt['phases'][:MAX_RECORDS]:
                if not isinstance(phase, dict):
                    continue
                state = ' (failed phase)' if phase.get('ok') is False else ''
                echo(f"    {phase.get('name', 'phase')}: {duration(phase.get('seconds'))}{state}")
            if receipt.get('status') != 'complete' and not (isinstance(cook, dict) and receipt.get('status') == 'not-recorded'):
                echo('    phase trace incomplete')
                diagnostics = receipt.get('diagnostics', [])
                if isinstance(diagnostics, list):
                    for diagnostic in diagnostics[:20]:
                        if isinstance(diagnostic, str):
                            echo(f'      {diagnostic[:300]}')
    return 0
