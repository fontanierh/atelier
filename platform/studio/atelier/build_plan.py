"""Read-only build decisions. A producer's future output is unknown until it runs."""
import json

from . import build as engine, build_products, paths


def controller_decision(step):
    return {'step': step.name, 'status': 'unknown',
            'reasons': ['readonly controller/cache observation unavailable; no helper bootstrap performed'],
            'previous_seconds': None, 'heavy': False, 'products': [], 'needs': [],
            'after': list(step.after), 'reads': [], 'references': []}


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
    for field, label in (('commands', 'commands'), ('products', 'product declarations'), ('tools', 'tool context'),
                         ('deferred_inputs', 'deferred input selection')):
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
    from .build_cook import validate_force
    validate_force(ctx, force)
    engine.check_modules(steps)
    rebuild_names = engine.touched_targets(ctx, steps, wanted)
    graph = build_products.Graph(steps)
    done, uncertain_steps, uncertain_products, decisions = {}, set(), set(), []
    tool_cache = {}
    selected = graph.select(wanted)
    from .build_cook import validate_selection
    validate_selection(ctx, selected)
    for step in selected:
        if step.controller is not None:
            decisions.append(controller_decision(step))
            # Order evidence only; validate_markers refuses v1 content needs until
            # an explicit output-content bridge exists. This is never an input key.
            done[step.name] = 'controller-order-not-observed'
            uncertain_steps.add(step.name)
            continue
        stamp = read_stamp(ctx.stamps / f'{step.name}.json')
        reasons = []
        try:
            if step.cache or step.audit:
                if step.audit:
                    from .build_audit import roots
                else:
                    from .build_cache import roots
                roots(ctx, step)
            current, state = engine.fingerprint_state(step, done, index=index, tool_cache=tool_cache)
        except (OSError, ValueError, SyntaxError) as error:
            current, state = f'invalid:{step.name}', {}
            reasons.append(f'invalid inputs: {error}')
        reasons.extend(f'required input missing: {path}' for path in engine.missing_product_inputs(step))
        from .build_cook import forced
        if forced(ctx, step, force):
            reasons.append('forced')
        if step.name in rebuild_names and stamp.get('touched'):
            reasons.append('replace touched certificate through a completed build')
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
    report = {'schema': 1, 'game': ctx.game, 'steps': decisions}
    if getattr(ctx, 'cook_mode', engine.CookMode.DEFAULT) is not engine.CookMode.DEFAULT:
        report.update(cook_mode=ctx.cook_mode.value, cook_reason=getattr(ctx, 'cook_reason', None))
    return report


def show(game, wanted=(), *, force=False, explain=False, as_json=False, echo=print, verify=False, cook_mode=None, cook_reason=None,
         rebuild_touched=False, cook_memory_gib=None):
    engine.cook_memory_limit(cook_memory_gib, wanted)
    from .build_v2.controller_entry import exact_selection
    controller = exact_selection(game, wanted)
    if controller is not None:
        from .build_snapshot import require_complete
        require_complete(paths.build_root() / game, game=game)
        if force or verify or rebuild_touched or cook_mode is not None or cook_reason is not None:
            raise ValueError('controller plan does not support legacy force/verify/cook flags')
        decision = controller_decision(controller)
        if as_json:
            echo(json.dumps({'schema': 1, 'game': game, 'steps': [decision]}, indent=2))
        else:
            echo(f"{controller.name:34s} unknown")
            if explain:
                echo('  ' + decision['reasons'][0])
        return 0
    ctx = engine.Context(game, create=False, **({'cook_mode': cook_mode, 'cook_reason': cook_reason} if cook_mode is not None else {}),
                         **({'cook_memory_gib': cook_memory_gib} if cook_memory_gib is not None else {}))
    ctx.rebuild_touched = rebuild_touched
    report = inspect(ctx, engine.load_recipe(game).steps(ctx), wanted, force=force, verify=verify)
    if cook_memory_gib is not None:
        report['cook_memory_gib'] = cook_memory_gib
    if as_json:
        echo(json.dumps(report, indent=2))
        return 0
    for item in report['steps']:
        echo(f"{item['step']:34s} {item['status']}")
        if explain:
            for reason in item['reasons']:
                echo(f'  {reason}')
    return 0
