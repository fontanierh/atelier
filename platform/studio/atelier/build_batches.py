"""Bounded process reuse for independent, explicitly batch-safe build actions.

Graph identities, products and success stamps remain per action. Only a warm tool process is
shared; the existing render admission and memory guard still own its entire lifetime.

plan -> worker START -> receipt -> host validates and stamps -> ACK continue/yield/abort
     -> worker COMPLETE -> host rechecks every completed result
"""
from dataclasses import replace
import json
import math
from pathlib import Path
import shlex
import time
import uuid

from . import build, build_products
from .build_cache import atomic_json
from .build_plan import read_stamp


WORKER = Path(__file__).with_name('build_batch_worker.py')
GiB = 1024 ** 3
LIMIT = 10 * GiB
HEADROOM = GiB


def validate(step):
    if step.batch is None:
        return
    if not step.batch.group or not 0 < step.batch.max_seconds <= 240:
        raise ValueError(f'{step.name}: batches need a name and a wall budget of at most 240 seconds')
    if (not step.heavy or not step.products or step.cutoff or step.pool_roots or len(step.commands) != 1
            or type(step.commands[0]) not in (build.Blender, build.UnrealScript)):
        raise ValueError(f'{step.name}: batching requires one guarded Blender/editor command and named products')
    if step.cache:
        from .build_batch_source import support
        declared = [Path(p).resolve() for p in step.inputs]
        for path in support().values():
            if not any(path.resolve() == p or p.is_dir() and path.resolve().is_relative_to(p) for p in declared):
                raise ValueError(f'{step.name}: cached batch runtime must be a declared input')
    if set(step.batch.runtime_env) & {'PYTHONHASHSEED', 'PYTHONPATH', 'PYTHONHOME', 'PATH',
                                      'ATELIER_BATCH', 'ATELIER_SCRIPT', 'ATELIER_LEFT_OUT'}:
        raise ValueError('A batch may not vary process-start environment settings between scripts')


def compatible(first, other):
    """@cc [owner:fontanierh,label:correctness] batch-environment-isolation
    Shared actions MUST have identical startup overrides and override the same runtime keys.
    An omitted override MUST start a separate process so it cannot inherit a predecessor's value.
    Explicit runtime values may differ; each action's command records them in its own key.
    """
    if (first.audit or other.audit or other.batch != first.batch or other.cache != first.cache
            or type(other.commands[0]) is not type(first.commands[0])):
        return False
    a, b = first.commands[0], other.commands[0]
    # The worker inherits the first action's environment. Every action must explicitly
    # replace the same runtime keys, rather than inherit a predecessor's override.
    runtime = set(first.batch.runtime_env)
    if {k for k, _ in a.env if k in runtime} != {k for k, _ in b.env if k in runtime}:
        return False
    env_a = tuple((k, v) for k, v in a.env if k not in first.batch.runtime_env)
    env_b = tuple((k, v) for k, v in b.env if k not in first.batch.runtime_env)
    if env_a != env_b:
        return False
    if isinstance(a, build.Blender):
        return (a.threads, a.factory_startup) == (b.threads, b.factory_startup)
    return (a.null_rhi, a.args, a.modules) == (b.null_rhi, b.args, b.modules)


def select(ctx, plan, start, done, *, force, index, tool_cache):
    """Consecutive ready actions only; a future reader never runs before its producer commits."""
    first = plan[start]
    if first.batch is None or first.audit:
        return []
    candidates = []
    for step in plan[start:]:
        if not compatible(first, step):
            break
        if (any(n not in done for n in (*step.needs, *step.after)) or
                any('product:' + p not in done for p in step.reads) or build.missing_product_inputs(step)):
            break
        current, inputs = build.fingerprint_state(step, done, index=index, tool_cache=tool_cache)
        # The caller handles current steps normally; keeping them out of the worker also avoids
        # writing a fresh stamp or resaving a package merely because a neighbour changed.
        previous = read_stamp(ctx.stamps / (step.name + '.json'))
        if (not force and previous.get('fingerprint') == current and build.outputs_present(step)
                and build_products.valid_records(step, previous.get('products', {}), hasher=index.digest)):
            continue
        candidates.append((step, current, inputs))
    return candidates


def yield_reason(policy, elapsed, footprint, next_delta, growth):
    """Use conservative additional headroom, not a count of meshes. The guard remains final."""
    if elapsed >= policy.max_seconds:
        return 'wall-time budget reached; recheck waiting work before resuming'
    if footprint is None:
        return 'fresh memory telemetry unavailable'
    reserve = max(LIMIT / 2 if next_delta is None else next_delta, max(0, growth) * 2, GiB / 4)
    if footprint + reserve >= LIMIT - HEADROOM:
        return 'next action would exceed the session memory budget'
    return None


def expected_growth(ctx, step):
    """A batch delta excludes editor startup; standalone peaks remain a conservative fallback."""
    folder = ctx.logs / (step.name + '.guard')
    delta = read_stamp(folder / 'batch-profile.json').get('batch_delta_bytes')
    if isinstance(delta, (int, float)) and math.isfinite(delta) and delta >= 0:
        return delta
    peak = build.expected_peak_gib(folder)
    return peak * GiB if peak else None


class Session:
    def __init__(self, ctx, candidates, done, index, tool_cache, echo, products):
        self.ctx, self.candidates, self.done = ctx, candidates, done
        self.products = products
        self.index, self.tool_cache, self.echo = index, tool_cache, echo
        self.nonce = uuid.uuid4().hex
        self.mesh_nonces = {step.name: uuid.uuid4().hex[:24] for step, _, _ in candidates}
        self.folder = ctx.out / '.state/batches' / self.nonce
        # Never let a session's cumulative report replace an individual action's standalone peak.
        self.guard = ctx.logs / ('batch.' + self.nonce + '.guard')
        self.started = None
        self.completed, self.error = {}, None
        self.memory, self.last_memory, self.action_peak, self.growth = None, None, 0, 0
        self.log = ''
        self.log_offset = 0
        # write_plan invalidates old certificates before execution. Retain their historical
        # inventories now so each new receipt can describe a real before/after comparison.
        self.previous = {step.name: read_stamp(ctx.stamps / (step.name + '.json'))
                         for step, _, _ in candidates}

    def write_plan(self):
        actions = []
        for step, key, _ in self.candidates:
            command = step.commands[0]
            from .checkpoint_candidates import save_prior
            prior = save_prior(self.ctx, step.name, self.mesh_nonces[step.name], self.previous[step.name])
            from .build_batch_source import action
            actions.append(action(command, name=step.name, game=self.ctx.game,
                                  nonce=self.mesh_nonces[step.name], prior=prior,
                                  blender=isinstance(command, build.Blender)))
            # An action about to run cannot keep a successful stamp from an older invocation.
            (self.ctx.stamps / (step.name + '.json')).unlink(missing_ok=True)
        atomic_json(self.folder / 'plan.json', {'nonce': self.nonce, 'actions': actions,
                                               'kind': type(self.candidates[0][0].commands[0]).__name__})

    def observe(self, pid):
        report = read_stamp(self.guard / 'memory-health.json')
        if report.get('pid') == pid and time.time() - report.get('time', 0) < 5:
            self.memory = report.get('footprint_bytes')
            if self.memory is not None:
                self.action_peak = max(self.action_peak, self.memory)
        else:
            self.memory = None
        try:
            with (self.guard / 'stdout.log').open(errors='replace') as log:
                log.seek(self.log_offset)
                self.log += log.read()
                self.log_offset = log.tell()
        except FileNotFoundError:
            pass

    def poll(self, pid):
        """@cc [owner:fontanierh,label:correctness] batch-active-time-budget
        The between-action clock MUST start on the first guarded child observation, after admission,
        never at session construction. Queued time MUST NOT consume it; later polls MUST NOT reset it.
        The independent guard's memory and child-duration limits remain authoritative.
        """
        if self.started is None:
            self.started = time.monotonic()
        self.observe(pid)
        if self.error:
            return
        for position, (step, key, inputs) in enumerate(self.candidates):
            if step.name in self.completed:
                continue
            path = self.folder / (step.name + '.receipt.json')
            receipt = read_stamp(path)
            if not receipt:
                break
            if receipt.get('nonce') != self.nonce or receipt.get('name') != step.name:
                raise ValueError('Batch receipt does not belong to this invocation')
            marker = getattr(step.commands[0], 'marker', None)
            start = 'ATELIER ACTION START ' + step.name
            if start not in self.log:
                break
            section = self.log.rsplit(start, 1)[-1]
            if marker and marker not in section:
                # The receipt can reach disk before Unreal flushes its stdout. A bounded worker
                # acknowledgement deadline covers a marker that never arrives.
                break
            try:
                self.certify(step, key, inputs, receipt, section)
            except (OSError, ValueError, RuntimeError) as error:
                self.error = str(error)
                atomic_json(self.folder / (step.name + '.ack.json'),
                            {'nonce': self.nonce, 'decision': 'abort', 'reason': self.error})
                return
            self.growth = max(0, self.memory - self.last_memory) if self.memory is not None and self.last_memory is not None else 0
            self.last_memory = self.memory
            self.action_peak = self.memory or 0
            self.log = ''
            reason = None
            if position + 1 < len(self.candidates):
                next_step = self.candidates[position + 1][0]
                reason = yield_reason(step.batch, time.monotonic() - self.started, self.memory,
                                      expected_growth(self.ctx, next_step), self.growth)
            atomic_json(self.folder / (step.name + '.ack.json'),
                        {'nonce': self.nonce, 'decision': 'yield' if reason else 'continue', 'reason': reason})

    def certify(self, step, key, inputs, receipt, log):
        build_products.verify_reads(step, self.products, self.done)
        if (not build.outputs_present(step) or build.missing_product_inputs(step) or
                build.fingerprint(step, self.done, index=self.index, tool_cache=self.tool_cache) != key):
            raise RuntimeError(f'{step.name}: inputs changed or required outputs missing during batch')
        products = build_products.records(step)
        seconds = round(receipt['seconds'], 3)
        command = step.commands[0]
        timing = {'kind': type(command).__name__, 'seconds': seconds, 'scope': 'batch action'}
        from . import build_changes
        from .build_timings import parse_phases
        phases = parse_phases(log, allow_echo=isinstance(command, build.UnrealScript))
        if phases is not None:
            timing['phases'] = phases
        roots, optional = build_changes.root_labels(self.ctx, step), build_changes.optional_roots(step)
        record = {'fingerprint': key, 'products': products, 'input_state': inputs, 'time': time.time(),
                  'seconds': seconds, 'commands': [timing], 'product_roots': roots,
                  'output_changes': build_changes.compare(self.previous[step.name], products, roots, optional=optional),
                  'batch': self.nonce}
        if optional:
            record['product_optional_roots'] = optional
        atomic_json(self.ctx.stamps / (step.name + '.json'), record)
        (self.ctx.stamps / (step.name + '.restore.json')).unlink(missing_ok=True)
        # The first action has no measured pre-action baseline. Do not invent a growth estimate.
        if self.last_memory is not None and self.memory is not None:
            atomic_json(self.ctx.logs / (step.name + '.guard/batch-profile.json'),
                        {'batch_delta_bytes': max(0, self.action_peak - self.last_memory),
                         'batch': self.nonce, 'time': time.time()})
        (self.ctx.logs / (step.name + '.log')).write_text(log)
        self.completed[step.name] = record
        self.done[step.name] = key
        build_products.feed_results(self.done, products)
        self.echo(f'{step.name:34s} done in {seconds:.1f} s (shared process; result saved)')

    def verify_completed(self):
        """@cc [owner:fontanierh,label:correctness] independent-batch-results
        Every completed action MUST be checked again after the worker exits, even on failure.
        Changed inputs or products MUST lose their stamp; an interrupted later action MUST NOT
        erase valid earlier results or certify actions that never completed.
        """
        for step, key, _ in self.candidates:
            record = self.completed.get(step.name)
            if record is None:
                continue
            try:
                build_products.verify_reads(step, self.products, self.done)
                valid = (not build.missing_product_inputs(step) and build.outputs_present(step)
                         and build.fingerprint(step, self.done, index=self.index, tool_cache=self.tool_cache) == key
                         and build_products.valid_records(step, record['products']))
            except (OSError, ValueError):
                valid = False
            if not valid:
                (self.ctx.stamps / (step.name + '.json')).unlink(missing_ok=True)
                self.completed.pop(step.name)
                self.done.pop(step.name, None)
                for product in step.products:
                    self.done.pop('product:' + product.name, None)
                self.error = f'{step.name}: inputs/products changed during the batch; result not certified'


def run(ctx, candidates, done, *, index, tool_cache, echo, products, wanted=()):
    # PEP 578 hooks cannot be removed, and warm imports/callbacks carry action state. An audited
    # batch declaration falls back through select() to ordinary fresh-process execution.
    if any(step.audit for step, _, _ in candidates):
        raise ValueError('Audited batch actions require separate fresh native processes')
    session = Session(ctx, candidates, done, index, tool_cache, echo, products)
    first = candidates[0][0]
    authority = getattr(ctx, 'legacy_authority', None)
    if authority is not None:
        authority.before_native_batch(ctx, session)
    session.write_plan()
    command = replace(first.commands[0], script=WORKER,
                      env=(*first.commands[0].env, ('ATELIER_BATCH', str(session.folder))))
    if isinstance(command, build.Blender):
        command.args = ()
    command.marker = 'ATELIER BATCH COMPLETE ' + session.nonce
    command.on_poll, command.progress = session.poll, 25.
    slots = []
    echo(f'{first.batch.group}: up to {len(candidates)} independent actions in one guarded process; '
         f'{first.batch.max_seconds:g} s between-action budget')
    try:
        with (ctx.logs / ('batch.' + session.nonce + '.log')).open('w') as log:
            # A warm session may grow beyond any single action's old peak. Keep the BIG request;
            # the shared 10 GiB actual-child guard is never lifted or replaced by the predictor.
            build.run_command(ctx, replace(first, name='batch.' + session.nonce), command, log, ('job', None), slots)
    except (Exception, SystemExit) as error:
        session.error = session.error or str(error)
    finally:
        session.verify_completed()
    outcome = read_stamp(session.folder / 'result.json')
    if not session.error:
        for step, _, _ in candidates:
            if step.name in session.completed and isinstance(step.commands[0], build.UnrealScript):
                try:
                    from .mesh_reuse import finalize_pending
                    finalize_pending(ctx, step.name, session.mesh_nonces[step.name])
                except Exception as error:
                    (ctx.stamps / (step.name + '.json')).unlink(missing_ok=True)
                    session.completed.pop(step.name, None)
                    session.done.pop(step.name, None)
                    for product in step.products:
                        session.done.pop('product:' + product.name, None)
                    session.error = str(error)
                    break
    if session.error:
        echo('Batch failed: ' + session.error)
        code = 1
    elif outcome.get('status') == 'yield':
        echo('Batch yielded: ' + outcome['reason'] + '. Completed results are saved.')
        resume = shlex.join(['atelier', 'build', ctx.game, *wanted])
        echo(f'BATCH YIELDED: {len(session.completed)} of {len(candidates)} actions done; '
             f'recheck Waiting, then resume with {resume}')
        code = 75
    elif len(session.completed) != len(candidates):
        echo('Batch ended without a receipt for every action')
        code = 1
    else:
        code = 0
    completed = set(session.completed)
    if authority is not None:
        authority.native_batch_observed(ctx, session, completed, code)
    return completed, code
