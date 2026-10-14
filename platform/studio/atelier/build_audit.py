"""Prepare and validate an opt-in Python input audit, separately from the action's outputs."""
from contextlib import contextmanager, ExitStack
import json
import os
from pathlib import Path
import secrets
import select
import shutil
import sysconfig
import tempfile
import threading

from . import paths

WORKER = Path(__file__).with_name('build_audit_worker.py')
SUPPORT = (Path(__file__), WORKER)


def validate(step):
    from .build import Python
    if type(step.audit) is not bool:
        raise ValueError(f'{step.name}: audit must be a boolean')
    if step.audit and (not step.products or len(step.commands) != 1 or type(step.commands[0]) is not Python):
        raise ValueError(f'{step.name}: audit requires named products and exactly one Python command')


def valid_record(record, nonce):
    if not isinstance(record, dict) or record.get('nonce') != nonce:
        return False
    kind = record.get('kind')
    if kind == 'start':
        return set(record) == {'kind', 'nonce'}
    if kind == 'complete':
        return set(record) == {'kind', 'nonce', 'success'} and type(record['success']) is bool
    return (kind == 'access' and set(record) == {'kind', 'nonce', 'operation', 'path', 'violation'}
            and isinstance(record['operation'], str) and bool(record['operation'])
            and (record['path'] is None or isinstance(record['path'], str))
            and (record['violation'] is None or isinstance(record['violation'], str) and bool(record['violation'])))


class Receiver:
    """Drain a private pipe while the normal launcher owns the child and its guard."""
    def __init__(self, fd, nonce):
        self.fd, self.nonce = fd, nonce
        self.records = []
        self.error = None
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self.read, daemon=True, name='atelier-input-audit')

    def read(self):
        buffer = b''
        try:
            while True:
                ready, _, _ = select.select([self.fd], [], [], .1)
                if not ready:
                    if self.stopped.is_set():
                        break
                    continue
                data = os.read(self.fd, 65536)
                if not data:
                    break
                if self.error:
                    continue  # Keep draining: a bad report must not fill the pipe and hang its child.
                buffer += data
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    try:
                        if len(line) > 32768 or len(self.records) >= 20002:
                            raise ValueError('audit report exceeds its limit')
                        record = json.loads(line)
                        if not valid_record(record, self.nonce):
                            raise ValueError('invalid audit record')
                        self.records.append(record)
                    except (ValueError, TypeError) as error:
                        self.error = type(error).__name__
                        buffer = b''
                        break
                if len(buffer) > 32768:
                    self.error, buffer = 'oversized audit record', b''
            if buffer:
                raise ValueError('truncated audit record')
        except (OSError, ValueError, TypeError) as error:
            # Do not copy untrusted record contents or exception text into the report.
            self.error = type(error).__name__

    def finish(self, step):
        self.stopped.set()
        self.thread.join(timeout=2)
        if self.thread.is_alive():
            self.error = 'audit reader did not stop'
        kinds = [r.get('kind') for r in self.records]
        complete = (not self.error and len(kinds) >= 2 and kinds[0] == 'start' and kinds[-1] == 'complete'
                    and all(kind == 'access' for kind in kinds[1:-1]))
        accesses = [r for r in self.records if r.get('kind') == 'access']
        violations = [r for r in accesses if r.get('violation')]
        passed = complete and self.records[-1].get('success') is True and not violations
        return {'schema': 1, 'step': step.name, 'complete': bool(complete), 'passed': bool(passed),
                'error': self.error, 'accesses': accesses, 'violations': violations}


@contextmanager
def prepared(ctx, step, products):
    """@cc [owner:fontanierh,label:correctness] observed-inputs-before-certification
    An audited action MUST provide a fresh, complete successful report without violations before
    certification. Reference products MUST NOT grant read access. Reports MUST stay outside products;
    failed actions and incomplete reports MUST NOT create stamps or publish cache entries.
    """
    from .build import required_inputs
    from .build_cache import atomic_json, roots
    validate(step)
    roots(ctx, step)
    command = step.commands[0]
    inputs = [*required_inputs(step), *(p for name in step.reads for p in products[name].paths)]
    output_roots = [Path(p).resolve() for product in step.products for p in product.paths]
    report_path = ctx.logs / f'{step.name}.audit.json'
    # These paths have one owner, and the executor has already dropped its old stamp. Unlinking
    # leaves (including hard links) preserves their other names; rmtree never follows child links.
    # Starting empty also prevents old output metadata or bytes from becoming undeclared inputs.
    for root in output_roots:
        if root.is_dir():
            shutil.rmtree(root)
        else:
            root.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(dir=ctx.logs, prefix='.audit-') as temporary, ExitStack() as cleanup:
        control = Path(temporary).resolve()
        scratch = control / 'scratch'
        for name in ('home', 'tmp', 'cache', 'bytecode'):
            (scratch / name).mkdir(parents=True)
        read_fd, write_fd = os.pipe()
        reader = cleanup.enter_context(os.fdopen(read_fd, 'rb', buffering=0))
        writer = cleanup.enter_context(os.fdopen(write_fd, 'wb', buffering=0))
        nonce = secrets.token_hex(16)
        receiver = Receiver(read_fd, nonce)
        config = {
            'nonce': nonce, 'fd': write_fd, 'script': str(command.script.resolve()), 'args': list(map(str, command.args)),
            'inputs': [*((str(Path(p).resolve()), Path(p).is_dir()) for p in inputs),
                       *((str(Path(p).resolve()), False) for p in step.optional_inputs)],
            'outputs': list(map(str, output_roots)), 'scratch': str(scratch),
            'runtime': sorted({str(Path(sysconfig.get_path(name)).resolve())
                               for name in ('stdlib', 'platstdlib', 'purelib', 'platlib')}),
            'labels': [(str(scratch), 'scratch'), (str(ctx.out.resolve()), 'build'),
                       (str(paths.REPO.resolve()), 'repo')],
        }
        config['labels'].extend((p, 'runtime') for p in config['runtime'])
        spec = control / 'request.json'
        spec.write_text(json.dumps(config))
        argv = [command.argv(ctx)[0], str(WORKER), str(spec)]
        env = (('HOME', str(scratch / 'home')), ('TMPDIR', str(scratch / 'tmp')),
               ('TMP', str(scratch / 'tmp')), ('TEMP', str(scratch / 'tmp')),
               ('XDG_CACHE_HOME', str(scratch / 'cache')), ('PYTHONPYCACHEPREFIX', str(scratch / 'bytecode')),
               ('PYTHONDONTWRITEBYTECODE', '1'))
        receiver.thread.start()
        try:
            yield argv, env, (write_fd,)
        finally:
            writer.close()
            report = receiver.finish(step)
            reader.close()
            atomic_json(report_path, report)
        if not report['passed']:
            raise RuntimeError(f'{step.name}: input audit incomplete or failed; see {report_path}')
