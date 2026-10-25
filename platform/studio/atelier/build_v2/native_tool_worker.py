"""Fixed native TOOL routes under the controller's existing whole-tree guard.

No admission, scheduler, arbitrary argv or result authority lives here. Frozen
recipe roots are copied with recipe_job; the controller validates and publishes
only after its normal guard has positively completed cleanup.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import selectors
import stat
import subprocess
import sys
import time


def _sibling(name):
    spec = importlib.util.spec_from_file_location('atelier_native_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


protocol = _sibling('protocol')
recipe_job = _sibling('recipe_job')
ops = _sibling('unreal_tool_ops')
WORKER_VERSION = 'atelier-native-tool-job-1'
KINDS = frozenset(('unreal.compile', 'unreal.game', 'unreal.cook.produce', 'unreal.package', 'package.archive'))


class Refused(ValueError):
    pass


def _path(view, name):
    return view / recipe_job.relative(name)


def _digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _tree(root):
    """Nofollow complete product inventory, retaining only internal app symlinks."""
    rows = []
    def visit(path):
        info = path.lstat()
        name = path.relative_to(root).as_posix()
        if stat.S_ISLNK(info.st_mode):
            target = os.readlink(path)
            if Path(target).is_absolute() or not path.resolve(strict=True).is_relative_to(root.resolve()):
                raise Refused('native product link escapes its owned root')
            rows.append((name, 'link', target))
        elif stat.S_ISDIR(info.st_mode):
            rows.append((name, 'directory', None))
            for child in sorted(path.iterdir()):
                visit(child)
        elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
            rows.append((name, 'file', _digest(path)))
        else:
            raise Refused('native product contains a special file or hard link')
    visit(root)
    return rows


def receipt_files(engine, project, target, configuration, kind):
    if kind == 'editor':
        return ops.compile_products(engine, project, target, owned_roots=[project.parent],
                                    kind=kind, configuration=configuration)['files']
    receipt = project.parent / 'Binaries/Mac' / (target + '.target')
    value = json.loads(receipt.read_bytes())
    if (value.get('TargetName'), value.get('Platform'), value.get('Configuration')) != (target, 'Mac', configuration):
        raise Refused('game receipt target/platform/configuration differs')
    files = {receipt}
    products = value.get('BuildProducts')
    if not isinstance(products, list) or not products:
        raise Refused('game receipt lacks complete products')
    for row in [*products, *value.get('RuntimeDependencies', [])]:
        path = ops._receipt_path(row['Path'], project=project.parent, engine=engine / 'Engine', receipt=receipt)
        if ops._inside(path, (engine / 'Engine',)):
            if not path.exists():
                raise Refused('installed runtime product is absent')
            continue
        if not ops._inside(path, (project.parent,)):
            raise Refused('game receipt product is outside the owned project')
        _tree(path)
        if row in products:
            files.add(path)
    return tuple(sorted(files))


def _covers(roots, paths):
    if any(not any(path == root or path.is_relative_to(root) for root in roots) for path in paths):
        raise Refused('declared outputs omit receipt-listed project products')


def zip_argv(root, destination):
    return ['/usr/bin/ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', str(root), str(destination)]


def export_outputs(recipe, view, output, run):
    """Use ROOT for ordinary roots, regular ditto ZIP payloads for explicit mac-zip roots."""
    for row in recipe['outputs']:
        root, destination = _path(view, row['path']), _path(output, row['file'])
        if row.get('encoding', 'root') == 'root':
            recipe_job.pack_root(root, destination, required=row.get('required', True))
        elif row['encoding'] == 'mac-zip':
            if not root.exists():
                raise Refused('required native archive root is absent')
            before = _tree(root)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                raise Refused('native archive destination exists')
            run(zip_argv(root, destination), cwd=view)
            if _tree(root) != before or not destination.is_file() or not destination.stat().st_size:
                raise Refused('native product changed during archive')
        else:
            raise Refused('unsupported native output encoding')


def dispatch(job, job_dir, engine, run):
    """@cc [owner:fontanierh,label:correctness;safety] fixed-native-tool-routes
    Only the five fixed version-1 operations MAY dispatch. SDK/interpreter locators
    MUST remain execution context. Compilation MUST use the private frozen project,
    three actions, complete real receipts and declared output coverage. Package MUST
    verify an independently completed exact cooked set and skip build/cook. Unknown
    cook production MUST refuse until the fixed source producer/export hook exists.
    This worker MUST NOT issue source-currentness certificates or CAS records.
    """
    kind = job['op']['kind']
    if kind not in KINDS or job['op']['version'] != '1':
        raise Refused('unsupported native tool operation')
    params, output = job['params'], job_dir / 'output'
    recipe = params['recipe']
    if recipe['version'] != 1 or output.is_symlink() or not output.is_dir() or any(output.iterdir()):
        raise Refused('native job needs an empty staged output and recipe version 1')
    view, protected, writes = recipe_job.prepare_view(job, job_dir)
    frozen_inputs = {name: recipe_job.inventory(name) for name in protected}
    # Runtime modules are loaded only from the same explicitly frozen source view.
    sys.path[:0] = [str(view / 'platform/studio'), str(view / 'platform/harness'), str(view)]
    project = _path(view, params['project']) if kind != 'package.archive' else None
    target = params.get('target')
    configuration = params.get('configuration', 'Development')
    environment = dict(os.environ)
    environment['TMPDIR'] = str(job_dir / recipe_job.RUNTIME / 'tmp')
    roots = [_path(view, row['path']) for row in recipe['outputs']]
    if kind in ('unreal.compile', 'unreal.game'):
        role = 'editor' if kind == 'unreal.compile' else 'game'
        run(ops.compile_argv(engine, project, target, kind=role, configuration=configuration),
            cwd=view, env=environment)
        _covers(roots, receipt_files(engine, project, target, configuration, role))
    elif kind == 'unreal.package':
        # Inventory comes from the controller's frozen upstream item, not a writer report.
        inventory = params.get('cooked_files')
        cooked = project.parent / 'Saved/Cooked/Mac'
        archive = _path(view, params['archive'])
        argv = ops.package_argv(engine, project, target, archive, cooked_root=cooked,
                                cooked_files=inventory, configuration=configuration)
        environment = ops.package_environment(engine, environment)
        lifecycle = ops.package_lifecycle(job_dir, engine, environment)
        try:
            run(argv, cwd=view, env=environment, lifecycle=lifecycle)
        finally:
            lifecycle.close()
        ops.verify_cooked_files(cooked, inventory)
    elif kind == 'package.archive':
        # The original archive script/arguments are frozen in the original declaration.
        commands = recipe['commands']
        if len(commands) != 1 or commands[0]['kind'] != 'python':
            raise Refused('package archive requires one declared Python script')
        command = commands[0]
        script = _path(view, command['script'])
        if script.name != 'package_archive.py' or command.get('env'):
            raise Refused('unknown package archive producer')
        if command['script'] not in job['code']:
            raise Refused('archive producer is outside frozen code')
        args = recipe_job._value(command['args'], view)
        run([sys.executable, '-I', '-B', str(script), *map(str, args)], cwd=view, env=environment)
    else:
        raise Refused('stock source-cook and native export hook is not yet installed')
    if recipe.get('verify') is not None:
        previous = Path.cwd()
        try:
            os.chdir(view)
            if not recipe_job.bind(recipe['verify'], view)():
                raise Refused('original native producer verification refused outputs')
        finally:
            os.chdir(previous)
    if any(recipe_job.inventory(name) != rows for name, rows in frozen_inputs.items()):
        raise Refused('native producer changed frozen input bytes or modes')
    export_outputs(recipe, view, output, run)
    return sorted(str(path.relative_to(output)) for path in output.rglob('*') if path.is_file())


class Worker:
    def __init__(self, requests, responses, engine_root):
        self.requests, self.responses = requests, responses
        self.engine = Path(engine_root)
        if not self.engine.is_absolute():
            raise Refused('engine locator must be absolute')
        self.active = None
        self.stop = False

    def send(self, value):
        protocol.write_frame(self.responses, protocol.RESPONSE, value)

    def command(self, argv, *, cwd, env=None, lifecycle=None):
        # No new session/group: all descendants remain owned by the C5 outer guard.
        child = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        started, spoken, buffered = time.monotonic(), time.monotonic(), b''
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout, selectors.EVENT_READ)
                selector.register(self.requests, selectors.EVENT_READ)
                logs_open = True
                while child.poll() is None or logs_open:
                    for key, _ in selector.select(timeout=1):
                        if key.fileobj is self.requests:
                            request = protocol.read_frame(self.requests, protocol.REQUEST)
                            if request is not None and request['type'] == 'cancel' and request['job_id'] != self.active:
                                continue
                            self.stop = True
                            raise Refused('cancelled by controller' if request else 'controller pipe closed')
                        chunk = os.read(child.stdout.fileno(), 65536)
                        if not chunk:
                            selector.unregister(child.stdout)
                            logs_open = False
                            continue
                        sys.stderr.buffer.write(chunk)
                        sys.stderr.buffer.flush()
                        if lifecycle:
                            buffered += chunk
                            lines = buffered.split(b'\n')
                            buffered = lines.pop()
                            for line in lines:
                                lifecycle.line(line.decode('utf-8', errors='replace'))
                    if lifecycle:
                        lifecycle.poll(child.pid)
                    if time.monotonic() - spoken >= 25:
                        print(f'native tool running: elapsed={time.monotonic()-started:.0f}s; awaiting tool completion',
                              file=sys.stderr, flush=True)
                        spoken = time.monotonic()
            if child.wait() != 0:
                raise Refused(f'native tool exited {child.returncode}')
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
            child.stdout.close()

    def serve(self):
        self.send({'type': 'hello', 'worker_version': WORKER_VERSION})
        while not self.stop:
            request = protocol.read_frame(self.requests, protocol.REQUEST)
            if request is None:
                return
            if request['type'] == 'shutdown':
                self.send({'type': 'stopped'})
                return
            if request['type'] != 'run':
                continue
            job = request['job']
            self.active = job['job_id']
            self.send({'type': 'started', 'job_id': self.active})
            try:
                directory = Path(job['job_dir'])
                if not directory.is_absolute() or directory.is_symlink():
                    raise Refused('job directory must be owned absolute staging')
                files = dispatch(job, directory, self.engine, self.command)
                self.send({'type': 'completed', 'job_id': self.active, 'outputs': {'files': files}})
            except (ValueError, OSError, KeyError, TypeError, RuntimeError) as error:
                self.send({'type': 'failed', 'job_id': self.active,
                           'failure': {'kind': 'cancelled' if self.stop else 'dependency', 'message': str(error)}})
            self.active = None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request-fd', type=int, required=True)
    parser.add_argument('--response-fd', type=int, required=True)
    parser.add_argument('--engine-root', required=True)
    args = parser.parse_args(argv)
    for fd in (args.request_fd, args.response_fd):
        os.set_inheritable(fd, False)
    with os.fdopen(args.request_fd, 'rb', buffering=0) as requests, os.fdopen(args.response_fd, 'wb', buffering=0) as responses:
        Worker(requests, responses, args.engine_root).serve()


if __name__ == '__main__':
    main()
