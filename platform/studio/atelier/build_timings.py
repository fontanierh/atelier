"""Historical build timings. Diagnostics never participate in product certification or cache keys."""
import io
import json
import math

PREFIX = 'ATELIER_PHASE '
MAX_RECORDS = 1000
MAX_PAYLOAD = 8192
MAX_DEPTH = 32


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
        producer = item['producer']
        if producer is None:
            echo('  producer timing not recorded')
            continue
        if item['last_action'] != 'execution':
            echo(f"  producer execution: {duration(producer['seconds'])}")
        for command in producer['commands']:
            if not isinstance(command, dict):
                continue
            echo(f"  {command.get('kind', 'command')}: {duration(command.get('seconds'))}")
            receipt = command.get('phases')
            if not isinstance(receipt, dict) or not isinstance(receipt.get('phases'), list):
                echo('    phases not recorded')
                continue
            for phase in receipt['phases'][:MAX_RECORDS]:
                if not isinstance(phase, dict):
                    continue
                state = ' (failed phase)' if phase.get('ok') is False else ''
                echo(f"    {phase.get('name', 'phase')}: {duration(phase.get('seconds'))}{state}")
            if receipt.get('status') != 'complete':
                echo('    phase trace incomplete')
                diagnostics = receipt.get('diagnostics', [])
                if isinstance(diagnostics, list):
                    for diagnostic in diagnostics[:20]:
                        if isinstance(diagnostic, str):
                            echo(f'      {diagnostic[:300]}')
    return 0
