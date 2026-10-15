"""Read-only build decisions. A producer's future output is unknown until it runs."""
import json

from . import build as engine, build_products


def read_stamp(path):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def changed_inputs(previous, current):
    """Explain stored input identities without reading the inputs a second time."""
    if not previous:
        return ['recipe or inputs changed (the old stamp has no input detail)']
    reasons = []
    for field, label in (('commands', 'commands'), ('products', 'product declarations'), ('tools', 'tool context')):
        if previous.get(field) != current.get(field):
            reasons.append(f'{label} changed')
    for field, label in (('inputs', 'input'), ('needs', 'dependency'), ('reads', 'product'),
                         ('queries', 'spatial query'), ('spatial_outputs', 'spatial bounds')):
        before, after = previous.get(field, {}), current.get(field, {})
        for name in sorted(before.keys() | after.keys()):
            if before.get(name) != after.get(name):
                reasons.append(f'{label} changed: {name}')
    before, after = previous.get('optional_inputs', {}), current.get('optional_inputs', {})
    for name in sorted(before.keys() | after.keys()):
        old, new = before.get(name), after.get(name)
        if old == new:
            continue
        change = 'declared' if old is None else 'declaration removed' if new is None else 'changed'
        if isinstance(old, dict) and isinstance(new, dict) and old.get('present') != new.get('present'):
            change = 'appeared' if new.get('present') else 'removed'
        reasons.append(f'optional input {change}: {name}')
    return reasons or ['fingerprint changed']


def inspect(ctx, steps, wanted=(), *, force=False, verify=False):
    """@cc [owner:fontanierh,label:correctness] plan-without-execution
    Planning MUST NOT run commands, create output directories, write stamps or acquire capacity.
    A changed producer's unobserved product MUST remain conditional in downstream decisions.
    """
    from .build_hashes import HashIndex
    with HashIndex(ctx.out / '.state' / 'file-hashes.sqlite3', read_only=True, verify=verify) as index:
        return _inspect(ctx, steps, wanted, force=force, index=index)


def _inspect(ctx, steps, wanted, *, force, index):
    engine.check_modules(steps)
    graph = build_products.Graph(steps)
    done, uncertain_steps, uncertain_products, decisions = {}, set(), set(), []
    tool_cache = {}
    for step in graph.select(wanted):
        stamp = read_stamp(ctx.stamps / f'{step.name}.json')
        reasons = []
        try:
            if step.cache or step.audit:
                from .build_cache import roots
                roots(ctx, step)
            current, state = engine.fingerprint_state(step, done, index=index, tool_cache=tool_cache)
        except (OSError, ValueError, SyntaxError) as error:
            current, state = f'invalid:{step.name}', {}
            reasons.append(f'invalid inputs: {error}')
        reasons.extend(f'required input missing: {path}' for path in engine.missing_product_inputs(step))
        if force:
            reasons.append('forced')
        if (ctx.stamps / f'{step.name}.restore.json').exists():
            reasons.append('interrupted product restoration')
        if not stamp:
            reasons.append('no successful stamp')
        elif stamp.get('fingerprint') != current:
            reasons.extend(changed_inputs(stamp.get('input_state'), state))
        if not engine.outputs_present(step):
            reasons.append('required outputs missing or verification failed')
        if step.products and not build_products.valid_records(step, stamp.get('products', {}), hasher=index.digest):
            reasons.append('product inventory missing, changed or incomplete')
        pending = sorted(set(step.needs) & uncertain_steps)
        pending += sorted(set(step.reads) & uncertain_products)
        # Existing bytes are useful for explanations, but cannot predict a generator's next result.
        status = 'run' if reasons else 'check-after-build' if pending else 'current'
        if pending:
            reasons.append('recheck after producer finishes: ' + ', '.join(pending))
        decisions.append({'step': step.name, 'status': status, 'reasons': reasons,
                          'previous_seconds': stamp.get('seconds'), 'heavy': step.heavy,
                          'products': [p.name for p in step.products], 'needs': step.needs, 'after': step.after,
                          'reads': step.reads, 'references': step.references})
        if step.queries:
            from .build_spatial import manifest
            decisions[-1]['queries'] = manifest(step)['queries']
        done[step.name] = (stamp['result'] if step.cutoff and status != 'current' and stamp.get('result')
                           else engine.result(step, current, stamp))
        build_products.feed_results(done, stamp.get('products', {}))
        if status != 'current':
            if step.cutoff or pending:
                uncertain_steps.add(step.name)
            uncertain_products.update(p.name for p in step.products)
    return {'schema': 1, 'game': ctx.game, 'steps': decisions}


def show(game, wanted=(), *, force=False, explain=False, as_json=False, echo=print, verify=False):
    ctx = engine.Context(game, create=False)
    report = inspect(ctx, engine.load_recipe(game).steps(ctx), wanted, force=force, verify=verify)
    if as_json:
        echo(json.dumps(report, indent=2))
        return 0
    for item in report['steps']:
        echo(f"{item['step']:34s} {item['status']}")
        if explain:
            for reason in item['reasons']:
                echo(f'  {reason}')
    return 0
