"""The executed Python/Blender adapter, separate from build scheduling and native cooking.

Command identity, argv, environment and audited preparation live here. Admission and timing
diagnostics can refuse a run, but do not transform the accepted action's inputs or outputs.
"""
from contextlib import contextmanager
from dataclasses import dataclass, fields
import json
import os
from pathlib import Path
import subprocess
import sys

from . import paths
from atelier.harness.safety import guarded


@dataclass
class Python:
    """A plain Python script, run with this interpreter (or $ATELIER_PYTHON)."""
    script: Path
    args: tuple = ()

    def argv(self, ctx):
        return [os.environ.get('ATELIER_PYTHON') or sys.executable, str(self.script), *map(str, self.args)]


@dataclass
class Blender:
    """A script run by headless Blender; everything after `args` reaches the script after `--`."""
    script: Path
    args: tuple = ()
    threads: int = 6
    factory_startup: bool = False
    env: tuple = ()

    def __repr__(self):
        shown = [f for f in fields(self) if f.name not in ('factory_startup', 'env') or getattr(self, f.name)]
        return f'Blender({", ".join(f"{f.name}={getattr(self, f.name)!r}" for f in shown)})'

    def argv(self, ctx):
        extra = ['--', *map(str, self.args)] if self.args else []
        return [ctx.blender, *(['--factory-startup'] if self.factory_startup else []), '-b', '--threads', str(self.threads), '--python-exit-code', '1',
                '--python', str(self.script), *extra]


def environment(extra=()):
    """Framework environment plus declared command overrides; Context.env overrides do not configure source actions."""
    env = dict(os.environ)
    env['ATELIER_BUILD_ROOT'] = str(paths.build_root())
    env.update(dict(extra))
    return env


@contextmanager
def prepared(ctx, step, command, *, products=None, audit_receipt=None):
    if step.audit:
        from . import build_audit
        with build_audit.prepared(ctx, step, products, receipt=audit_receipt) as action:
            yield action
    else:
        yield command.argv(ctx), getattr(command, 'env', ()), ()


def run(ctx, step, command, log, request=None, slots=None, *, products=None, audit_receipt=None):
    """@cc [owner:fontanierh,label:correctness] executed-source-boundary
    Python/Blender execution MUST use this adapter's argv, environment and preparation code.
    Source tool identity MUST hash this module and the action's audit/bootstrap support;
    unrelated build scheduling and cooking MUST NOT enter that identity. Guarded admission,
    command return codes, completion markers and audit certification MUST remain enforced.
    """
    with prepared(ctx, step, command, products=products, audit_receipt=audit_receipt) as (argv, env, descriptors):
        return run_argv(ctx, step, command, argv, env, log, request, slots, pass_fds=descriptors)


def run_argv(ctx, step, command, argv, env, log, request, slots, *, pass_fds=()):
    env = environment(env)
    log.write(f'$ {" ".join(argv)}\n'); log.flush()
    authority = getattr(ctx, 'legacy_authority', None)
    if step.heavy or authority is not None:
        logical_folder = ctx.logs / f'{step.name}.guard'
        folder = authority.guard_directory if authority is not None else logical_folder
        kind, small_gib = request if step.heavy else ('job', None)
        used = []

        def note(slot, why):
            used.append(slot)
            if slots is not None:
                slots.append(slot)
            why = why or ('no guard report yet' if kind == 'job' and small_gib is None else '')
            log.write(f'render slot: {slot}' + (f' ({why})' if why else '') + '\n'); log.flush()
        inherited = {'pass_fds': pass_fds} if pass_fds else {}
        callback = getattr(command, 'on_poll', None)
        managed = authority.guard_options(argv, env, kind) if authority is not None else {}
        code = guarded.run(argv, folder, purpose=f'atelier build {ctx.game} {step.name}', env=env,
                           small_gib=small_gib, kind=kind, on_slot=note, timeout=(120. if authority is not None else getattr(command, 'timeout', 0.)),
                           watch=getattr(command, 'watch', ()), progress=getattr(command, 'progress', 0.),
                           **inherited, **managed, **({'on_poll': callback} if callback is not None else {}))
        if authority is not None:
            authority.guard_returned(code)
        text = (folder / 'stdout.log').read_text(errors='ignore')
        log.write(text)
        if code and used == ['small']:
            try:
                stopped = json.loads((folder / 'memory-health.json').read_text()).get('state') == 'memory_limit'
            except (OSError, ValueError, AttributeError):
                stopped = False
            if stopped:
                raise RuntimeError(f'{step.name}: stopped at the small render slot\'s memory limit; '
                                   f'its report now sends it to the big slot, run it again')
    else:
        from atelier.harness.safety.process import policy_command
        result = subprocess.run(policy_command(argv), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                                text=True, errors='ignore', **({'pass_fds': pass_fds, 'stdin': subprocess.DEVNULL} if pass_fds else {}))
        code, text = result.returncode, result.stdout
        log.write(text)
    if code:
        raise RuntimeError(f'{step.name}: command exited {code}')
    marker = getattr(command, 'marker', None)
    if marker and marker not in text:
        raise RuntimeError(f'{step.name}: "{marker}" missing from the log')
    from .build_timings import parse_phases
    return parse_phases(text)
