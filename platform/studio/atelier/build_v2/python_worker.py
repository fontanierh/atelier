"""Build-v2 Python job loop: one outer worker process, one sandboxed child per job.

Started as `python -I python_worker.py --request-fd N --response-fd M` by the controller's launcher,
which owns admission, guards and deadlines. Frames use only those two inherited descriptors, which
are made non-inheritable at once so no job or descendant can reach the protocol pipe; stdout and
stderr are logs. The loop sends `hello`, then for each `run` sends `started` and exactly one terminal
response; a `cancel` stops that job's child and is answered by a `cancelled` failure.

Each job runs `python -P -s -S -B -c <python_job.py source>` with its configuration on stdin, in the staged job folder with a declared
environment only. On macOS the child runs under a deny-default `sandbox-exec` profile: it may read
only the interpreter's installed roots, a few platform files and its job folder, and write only
`output/`. Any other read, existence check, listing or network use kills the child, which this loop
reports as a `dependency` failure. The child may execute only the interpreter itself. There is no
unsandboxed mode on this command line: elsewhere every job fails. Portable tests of the loop construct
`Worker(..., sandboxed=False)` from a test-only entry, and such a loop announces a different worker
version (`TEST_WORKER_VERSION`), so a controller keyed to `WORKER_VERSION` refuses its session.

The loop reports every regular file the job left under `output/`; the controller decides membership.
Only the standard library is used, so this file also runs by path without the atelier package.
"""
import argparse
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import sysconfig

if __package__:
    from . import protocol
else:  # run by path: load the sibling module without importing the atelier package
    import importlib.util
    _spec = importlib.util.spec_from_file_location('build_v2_protocol', Path(__file__).with_name('protocol.py'))
    protocol = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(protocol)

WORKER_VERSION = 'atelier-python-job-1'
# Announced only by an unsandboxed loop built for portable tests; never a keyed production identity.
TEST_WORKER_VERSION = WORKER_VERSION + '+unsandboxed-test'
JOB_SOURCE = Path(__file__).with_name('python_job.py').read_text(encoding='utf-8')
JOB_ENVIRONMENT = {'LC_ALL': 'C', 'TZ': 'UTC', 'PYTHONHASHSEED': '0', 'PYTHONDONTWRITEBYTECODE': '1',
                   'PYTHONIOENCODING': 'utf-8'}
# -P: no script or working folder on sys.path; -s: no user site; -S: no site-packages .pth hooks;
# -B: no bytecode writes. Not -I/-E, which would drop the declared PYTHONHASHSEED.
CHILD_FLAGS = ('-P', '-s', '-S', '-B')
SANDBOX_EXEC = '/usr/bin/sandbox-exec'
# Platform files the interpreter reads at startup (locale, time zone, user database, dyld/DTrace
# helpers). They are part of the installed execution platform, not project inputs.
PLATFORM_READ_SUBPATHS = ('/System', '/usr/lib', '/usr/share/locale', '/private/var/db/timezone')
PLATFORM_READ_LITERALS = ('/', '/etc', '/var', '/private/etc/passwd', '/private/etc/localtime',
                          '/private/etc/ssl/openssl.cnf', '/dev/dtracehelper', '/dev/null')
SANDBOX_KILLED = 'the sandbox stopped the job: it read, checked, listed or connected to something undeclared'


class JobRefused(Exception):
    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


def interpreter_roots():
    """The installed interpreter and its libraries: the allowed execution platform."""
    paths = sysconfig.get_paths()
    roots = {sys.base_prefix, sys.prefix, os.path.dirname(os.path.realpath(sys.executable))}
    roots.update(paths[name] for name in ('stdlib', 'platstdlib', 'purelib', 'platlib'))
    real = os.path.realpath(sys.base_prefix)
    if real.startswith('/opt/homebrew/'):
        # Homebrew interpreters link shared libraries from other kegs.
        roots.update(('/opt/homebrew/opt', '/opt/homebrew/Cellar'))
    return sorted({os.path.realpath(root) for root in roots} | roots)


def site_libraries():
    """This interpreter's installed-library folders (its venv's, when it runs in one), in order.

    Both scheme folders are always passed, never filtered here: the child refuses, as a `dependency`
    failure naming the folder, any one that is missing, not a folder or outside the platform roots.
    """
    paths = sysconfig.get_paths()
    return list(dict.fromkeys(paths[name] for name in ('purelib', 'platlib')))


def _quote(path):
    return '"' + path.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _ancestors(path):
    found = []
    while True:
        parent = os.path.dirname(path)
        if parent == path:
            return found
        found.append(parent)
        path = parent


def _links(path):
    """Every symbolic link met while resolving `path`; exec and import follow them."""
    found, pending, seen = [], path, set()
    while pending not in seen:
        seen.add(pending)
        parts, current = pending.split('/')[1:], '/'
        for index, part in enumerate(parts):
            current = os.path.join(current, part)
            if os.path.islink(current):
                found.append(current)
                target = os.path.join(os.path.dirname(current), os.readlink(current))
                pending = os.path.normpath(os.path.join(target, *parts[index + 1:]))
                break
        else:
            return found
    return found


def platform_reads():
    """(subpaths, literals) of the installed platform every job may read, links included."""
    subpaths = list(PLATFORM_READ_SUBPATHS) + interpreter_roots()
    links = [link for path in subpaths + [sys.executable] for link in _links(path)]
    return subpaths, list(PLATFORM_READ_LITERALS) + [sys.executable] + links


def interpreter_executables():
    """The interpreter binaries a job child may execute: the launched path, its links and target,
    and a framework build's re-executed application binary."""
    paths = [sys.executable, os.path.realpath(sys.executable)] + _links(sys.executable)
    app = os.path.join(sys.base_prefix, 'Resources', 'Python.app', 'Contents', 'MacOS', 'Python')
    if os.path.isfile(app):
        paths += [app, os.path.realpath(app)] + _links(app)
    return sorted(set(paths))


class Platform:
    """The installed execution platform one kind of job may use: what it may execute and read, and
    where platform modules import from. The default is this Python interpreter."""

    def executables(self):
        return interpreter_executables()

    def reads(self):
        """(subpaths, literals) of platform files every job may read."""
        return platform_reads()

    def import_roots(self):
        return interpreter_roots()

    def site_libraries(self):
        """The installed-library folders a job imports from: this loop's own purelib and platlib.

        The child runs with -P -s -S, so it never derives them itself and never runs a .pth file.
        """
        return site_libraries()

    def extra_rules(self):
        """Further sandbox allowances this platform needs, each a reviewed profile rule; none here."""
        return []


def sandbox_profile(job_dir, platform=None):
    """@cc [owner:fontanierh,label:safety] exact-platform-openssl-config
    The installed OpenSSL config MUST be an exact canonical read literal, never a directory
    allowance or an environment override. Neighboring certs/hosts MUST remain outside data-read
    grants. All other file/network, Mach, write and process rules MUST remain unchanged.
    It is installed platform context, not a new game input. See the profile-only portable
    test_openssl_platform_config_literal_never_grants_neighbor_data_reads; actual sandbox
    execution is separate guarded evidence, not a claim made by that profile inspection.
    """
    platform = platform or Platform()
    subpaths, literals = platform.reads()
    reads = subpaths + [job_dir] + _links(job_dir)
    metadata = sorted({ancestor for path in reads + literals for ancestor in _ancestors(path)})
    literals = literals + _links(job_dir)
    subpaths = ' '.join(f'(subpath {_quote(path)})' for path in reads)
    return '\n'.join([
        '(version 1)',
        '(deny default)',
        # Listed first so that every later allow takes precedence; what remains kills the job.
        '(deny file-read* network* (with send-signal SIGKILL))',
        f'(allow process-exec {" ".join(f"(literal {_quote(path)})" for path in platform.executables())})',
        f'(allow file-read* {subpaths} {" ".join(f"(literal {_quote(path)})" for path in literals)})',
        f'(allow file-read-metadata {" ".join(f"(literal {_quote(path)})" for path in metadata)})',
        f'(allow file-write* (subpath {_quote(os.path.join(job_dir, "output"))}) (literal "/dev/null"))',
        '(allow file-ioctl (literal "/dev/dtracehelper"))',
        '(allow sysctl-read)',
        *platform.extra_rules(),
    ])


def _job_relative(path, label):
    parts = path.split('/')
    if not path or path.startswith('/') or '\\' in path or '\0' in path or any(part in ('', '.', '..') for part in parts):
        raise JobRefused('protocol', f'{label} is not a job-relative path: {path!r}')
    return path


def job_config(job, job_dir, result_fd, platform=None):
    """The child's configuration: declared names only, no job ID, folder or source locator."""
    platform = platform or Platform()
    inputs = {}
    for item in job['inputs']:
        path = _job_relative(item['path'], 'input')
        present = item['identity']['state'] != 'absent'
        if present != os.path.lexists(os.path.join(job_dir, path)):
            raise JobRefused('protocol', f'input {item["name"]!r} does not match its staged presence')
        inputs[item['name']] = path if present else None
    for path in job['code']:
        _job_relative(path, 'code file')
    if job['script'] not in job['code']:
        raise JobRefused('protocol', 'the entry script is outside the declared code')
    return {'script': job['script'], 'code': job['code'], 'inputs': inputs,
            'outputs': [_job_relative(item['path'], 'output') for item in job['outputs']],
            'params': job['params'], 'platform_roots': platform.import_roots(),
            'site_libraries': platform.site_libraries(), 'read_subpaths': platform.reads()[0],
            'read_literals': platform.reads()[1], 'result_fd': result_fd}


def output_files(job_dir):
    """Every regular file under `output/`, declared or not; links and other types fail the job.

    The loop reports the complete actual set (fixed outputs and group members alike) and leaves
    membership to the controller, which holds the exact fixed and group output contracts.
    """
    root = os.path.join(job_dir, 'output')
    found = []
    for directory, subdirectories, files in os.walk(root):
        for name in subdirectories + files:
            path = os.path.join(directory, name)
            if os.path.islink(path) or not (os.path.isdir(path) or os.path.isfile(path)):
                raise JobRefused('job', f'output {os.path.relpath(path, root)!r} is not a regular file')
        found.extend(os.path.relpath(os.path.join(directory, name), root) for name in files)
    return sorted(found)


def forward_log(chunk):
    sys.stderr.buffer.write(chunk)
    sys.stderr.buffer.flush()


def drain(logs):
    """Forward what an exited child left in its log pipe, without waiting on any descendant."""
    os.set_blocking(logs.fileno(), False)
    while True:
        try:
            chunk = os.read(logs.fileno(), 65536)
        except BlockingIOError:
            return
        if not chunk:
            return
        forward_log(chunk)


class Worker:
    """The job loop. Subclasses (another tool's loop) override the version, platform and child command."""

    VERSION = WORKER_VERSION

    def __init__(self, requests, responses, sandboxed):
        self.requests = requests
        self.responses = responses
        self.sandboxed = sandboxed
        self.version = self.VERSION if sandboxed else self.VERSION + '+unsandboxed-test'
        self.platform = Platform()

    def child_command(self):
        """The job child's command before sandbox wrapping; its configuration arrives on stdin."""
        return [sys.executable, *CHILD_FLAGS, '-c', JOB_SOURCE]

    def child_environment(self, job_dir):
        return dict(JOB_ENVIRONMENT)

    def check_job_folder(self, job_dir):
        """Refuse a staged folder this loop's child cannot use; a Python job needs nothing further."""

    def send(self, message):
        protocol.write_frame(self.responses, protocol.RESPONSE, message)

    def fail(self, job_id, kind, message):
        self.send({'type': 'failed', 'job_id': job_id, 'failure': {'kind': kind, 'message': message}})

    def serve(self):
        self.send({'type': 'hello', 'worker_version': self.version})
        while True:
            request = protocol.read_frame(self.requests, protocol.REQUEST)
            if request is None:
                return
            if request['type'] == 'shutdown':
                self.send({'type': 'stopped'})
                return
            if request['type'] == 'run':
                self.run(request['job'])
            # A cancel for a job that already finished gets no reply.

    def run(self, job):
        job_id = job['job_id']
        self.send({'type': 'started', 'job_id': job_id})
        try:
            files = self.execute(job)
        except JobRefused as refusal:
            return self.fail(job_id, refusal.kind, str(refusal))
        except OSError as error:
            # Whatever happens to the job's process or folder, the controller gets its one terminal reply.
            return self.fail(job_id, 'dependency', f'the job loop could not run the job: {error}')
        if files is not None:
            self.send({'type': 'completed', 'job_id': job_id, 'outputs': {'files': files}})

    def execute(self, job):
        job_id = job['job_id']
        job_dir = os.path.realpath(job['job_dir'])
        if not os.path.isabs(job['job_dir']) or not os.path.isdir(os.path.join(job_dir, 'output')):
            raise JobRefused('protocol', 'the job folder is not a staged absolute folder with output/')
        if os.listdir(os.path.join(job_dir, 'output')):
            raise JobRefused('protocol', 'output/ is not empty before the job')
        self.check_job_folder(job_dir)
        if self.sandboxed and not os.access(SANDBOX_EXEC, os.X_OK):
            raise JobRefused('dependency', 'no supported job sandbox on this platform')
        command = self.child_command()
        if self.sandboxed:
            command = [SANDBOX_EXEC, '-p', sandbox_profile(job_dir, self.platform)] + command
        result_read, result_write = os.pipe()
        try:
            # The configuration travels on the child's stdin, never argv, so no valid request can hit
            # argument limits. The child gets its own log pipe: inherited stdout/stderr files would be
            # undeclared paths to the sandbox; the loop forwards those logs to its own stderr. It stays
            # in the loop's process group, so a guard that stops the worker stops the job too.
            config = json.dumps(job_config(job, job_dir, result_write, self.platform)).encode('utf-8')
            child = subprocess.Popen(command, cwd=job_dir, env=self.child_environment(job_dir), stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, pass_fds=(result_write,))
        except OSError as error:
            os.close(result_read)
            raise JobRefused('dependency', f'cannot start the job process: {error.strerror or error}') from None
        finally:
            os.close(result_write)
        try:
            child.stdin.write(config)
        except BrokenPipeError:
            pass  # the child ended before reading; its exit status decides the failure below
        finally:
            try:
                child.stdin.close()
            except BrokenPipeError:
                pass
        with os.fdopen(result_read, 'rb') as results, child.stdout as logs, \
                selectors.DefaultSelector() as selector:
            for stream in (results, logs, self.requests):
                selector.register(stream, selectors.EVENT_READ)
            report = b''
            while True:
                for key, _ in selector.select():
                    if key.fileobj is logs:
                        chunk = os.read(logs.fileno(), 65536)
                        if chunk:
                            forward_log(chunk)
                        else:
                            selector.unregister(logs)
                        continue
                    if key.fileobj is results:
                        chunk = os.read(results.fileno(), 65536)
                        if chunk:
                            report += chunk
                            continue
                        selector.unregister(results)
                        status = child.wait()
                        drain(logs)
                        return self.finish(job, job_dir, status, report)
                    request = protocol.read_frame(self.requests, protocol.REQUEST)
                    if request is not None and request['type'] == 'cancel' and request['job_id'] != job_id:
                        continue  # a late cancel for an earlier job gets no reply
                    child.kill()
                    child.wait()
                    drain(logs)
                    if request == {'type': 'cancel', 'job_id': job_id}:
                        self.fail(job_id, 'cancelled', 'cancelled by the controller')
                        return None
                    if request is None:
                        raise SystemExit(0)  # the controller closed the pipe
                    raise JobRefused('protocol', f'unexpected {request["type"]} while job {job_id} runs')

    def finish(self, job, job_dir, status, report):
        if status == -signal.SIGKILL and self.sandboxed:
            raise JobRefused('dependency', SANDBOX_KILLED)
        if status < 0:
            raise JobRefused('job', f'the job process ended by signal {-status}')
        try:
            result = json.loads(report.decode('utf-8'))
        except ValueError:
            raise JobRefused('job', f'the job process exited with status {status} and no result') from None
        if result.get('status') != 'ok':
            raise JobRefused(result.get('kind', 'job'), result.get('message', 'the job failed'))
        if status != 0:
            raise JobRefused('job', f'the job process exited with status {status}')
        return output_files(job_dir)


def serve(request_fd, response_fd, sandboxed):
    """Serve one controller over two inherited descriptors, made non-inheritable first."""
    for fd in (request_fd, response_fd):
        os.set_inheritable(fd, False)
    requests = os.fdopen(request_fd, 'rb', buffering=0)
    responses = os.fdopen(response_fd, 'wb', buffering=0)
    Worker(requests, responses, sandboxed=sandboxed).serve()


def main(argv=None):
    """The production entry: always sandboxed, with no option to turn isolation off."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--request-fd', type=int, required=True)
    parser.add_argument('--response-fd', type=int, required=True)
    args = parser.parse_args(argv)
    serve(args.request_fd, args.response_fd, sandboxed=True)


if __name__ == '__main__':
    main()
