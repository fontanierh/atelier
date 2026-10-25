"""Build-v2 Blender job loop: one admitted background Blender, one fresh sandboxed Blender per job.

Started by the controller's launcher as

    Blender --factory-startup -b --threads 3 --python-exit-code 1 --disable-autoexec \\
        -P blender_worker.py -- --request-fd N --response-fd M

so admission sees a literal Blender with three threads. This outer Blender only runs the protocol
loop of `python_worker.py` (hello `atelier-blender-job-1`, `started` then exactly one terminal
response per `run`, cancel, logs off the wire, both protocol descriptors non-inheritable). It does no
Blender work itself.

Each job runs a new Blender from the same installed binary, in the staged job folder:

    Blender --factory-startup -b --threads 3 --python-exit-code 1 --disable-autoexec \\
        --python-use-system-env --python-expr <blender_job.py + python_job.py source>

with the configuration on stdin, the declared environment only, and every Blender user folder
(`BLENDER_USER_*`, and `HOME`) pointed at an initially absent path inside its fresh private
runtime folder, so no existing preferences, add-ons, extensions or caches load. That fixed
job-local scratch is separate from published outputs and never reused between jobs. On macOS
the child runs under the same
deny-default kill-on-deny profile as a Python job, with the Blender application bundle as its
platform: it may read the bundle, the platform files and its job folder, write only `output/`, and
execute only the Blender binary. A clean process per job means no state carries from one job to
the next.

There is no unsandboxed mode on this command line. Portable tests construct `BlenderWorker(...,
sandboxed=False)` from a test-only entry, which announces a different worker version.

Installed Blender and its bundled add-ons are execution platform, not key ingredients.
"""
import argparse
import importlib.util
import os
import stat
from pathlib import Path
import sys

if __package__:
    from . import python_worker
else:  # run by Blender as a script: load the sibling module by path
    _spec = importlib.util.spec_from_file_location('build_v2_python_worker', Path(__file__).with_name('python_worker.py'))
    python_worker = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(python_worker)

WORKER_VERSION = 'atelier-blender-job-1'
TEST_WORKER_VERSION = WORKER_VERSION + '+unsandboxed-test'
THREADS = 3
BOOTSTRAP = Path(__file__).with_name('blender_job.py').read_text(encoding='utf-8')
# Blender flags shared by the loop and every job: no user startup file or preferences, background
# mode, an explicit thread count admission can read, script errors as a non-zero exit, and no
# auto-run of scripts embedded in .blend files.
BLENDER_FLAGS = ('--factory-startup', '-b', '--threads', str(THREADS), '--python-exit-code', '1',
                 '--disable-autoexec')
# A job child also lets its embedded Python read the declared environment, so PYTHONHASHSEED and the
# other JOB_ENVIRONMENT settings apply. The environment holds only declared names (no PYTHONPATH or
# PYTHONHOME), so this adds no ambient input.
JOB_FLAGS = BLENDER_FLAGS + ('--python-use-system-env',)
# Folders Blender would otherwise take from the user's home; each points at a missing job-local path.
# Staged code could occupy that path, so a job whose folder already holds it is refused.
USER_FOLDERS = ('BLENDER_USER_RESOURCES', 'BLENDER_USER_CONFIG', 'BLENDER_USER_SCRIPTS',
                'BLENDER_USER_DATAFILES', 'BLENDER_USER_EXTENSIONS', 'HOME')
RUNTIME_DIRECTORY = '.blender-runtime'
MISSING_USER_FOLDER = RUNTIME_DIRECTORY + '/user'
# Platform files Blender reads at startup beyond the Python job's: ICU data, and the system-wide
# (not per-user) CoreFoundation preferences. Neither is in the home folder.
BLENDER_READ_SUBPATHS = ('/usr/share/icu',)
BLENDER_READ_LITERALS = ('/Library/Preferences/.GlobalPreferences.plist',)
# Further kernel allowances, each needed by Blender itself; none is visible to the Python guard.
# - Blender probes the Metal device during startup even in background mode and crashes without one,
#   so the child may open the GPU's IOKit user clients (no file access).
# - Its temp-folder probe and a system framework's developer-folder probe check that /tmp and
#   /Applications/Xcode.app exist (metadata only; no listing, and writes to /tmp stay denied).
# - The bundled Python's os.urandom reads /dev/urandom, and the bundled extensions add-on calls it at
#   startup. Job code still cannot: the guard refuses os.urandom and opening /dev/urandom.
# - Binding a socket is denied without ending the job: the bundled HTTP library (urllib3, imported by
#   the extensions add-on at startup) probes IPv6 support by binding a local socket. This later rule
#   only replaces the kill with a plain refusal for binds; connections and all other network use
#   still end the job, and job code cannot create sockets at all.
# Background Metal rendering creates a Cocoa GHOST context lazily at the first render.
# AppKit registers this fixed executable with LaunchServices and connects to WindowServer;
# denying those exact SDK endpoints aborts _RegisterApplication before rendering starts.
# AppKit also checks the exact system setup sentinel metadata while registering the app.
# These are native platform services, not an allowance for arbitrary Mach names or job IO.
BLENDER_RENDER_SERVICES = ('com.apple.windowserver.active',
                           'com.apple.coreservices.launchservicesd',
                           'com.apple.lsd.mapdb', 'com.apple.lsd.modifydb')
BLENDER_RULES = (
    '(allow iokit-open-user-client (iokit-user-client-class "AGXDeviceUserClient" "IOSurfaceRootUserClient"))',
    '(allow file-read-metadata (literal "/tmp") (literal "/private/tmp") (literal "/Applications/Xcode.app") (literal "/private/var/db/.AppleSetupDone"))',
    '(allow file-read-data (literal "/dev/urandom"))',
    '(allow mach-lookup ' + ' '.join('(global-name ' + python_worker._quote(name) + ')'
                                    for name in BLENDER_RENDER_SERVICES) + ')',
    '(deny network-bind)',
)


def application_bundle(blender):
    """The `.app` bundle that holds this Blender binary, or the binary's folder outside a bundle."""
    real = os.path.realpath(blender)
    path = Path(real)
    for parent in path.parents:
        if parent.suffix == '.app':
            return str(parent)
    return str(path.parent)


class BlenderPlatform(python_worker.Platform):
    """The installed Blender. Its binary is the only executable. Readable and importable: the
    application bundle (bundled Python, `bpy` modules, bundled add-ons) plus the interpreter this loop
    runs in, which inside the admitted Blender is that same bundled Python."""

    def __init__(self, blender):
        self.blender = blender
        self.bundle = application_bundle(blender)

    def executables(self):
        paths = [self.blender, os.path.realpath(self.blender)] + python_worker._links(self.blender)
        return sorted(set(paths))

    def reads(self):
        subpaths, literals = python_worker.platform_reads()
        links = python_worker._links(self.bundle) + python_worker._links(self.blender)
        subpaths = sorted(set(subpaths) | {self.bundle} | set(BLENDER_READ_SUBPATHS))
        return subpaths, literals + [self.blender, *BLENDER_READ_LITERALS] + links

    def extra_rules(self):
        """@cc [owner:fontanierh,label:safety] background-render-sdk-registration
        Background rendering MAY register only the installed Blender bundle for a read-only
        LaunchServices extension and access the fixed native rendering service names. This
        MUST NOT allow arbitrary Mach endpoints, extension targets, file writes or processes.
        Ordinary job code remains subject to the existing Python and filesystem guards.
        """
        registration = []
        if Path(self.bundle).suffix == '.app':
            registration = ['(allow file-issue-extension (require-all '
                '(extension-class "com.apple.app-sandbox.read") '
                '(literal ' + python_worker._quote(self.bundle) + ')))']
        return [*registration, *BLENDER_RULES]

    def import_roots(self):
        return sorted(set(python_worker.interpreter_roots()) | {self.bundle})

    def write_subpaths(self, job_dir):
        return [*super().write_subpaths(job_dir), os.path.join(job_dir, RUNTIME_DIRECTORY)]


class BlenderWorker(python_worker.Worker):
    VERSION = WORKER_VERSION

    def __init__(self, requests, responses, sandboxed, blender):
        super().__init__(requests, responses, sandboxed)
        self.blender = blender
        self.platform = BlenderPlatform(blender)

    def child_command(self):
        expression = f'{BOOTSTRAP}\n_main({python_worker.JOB_SOURCE!r})\n'
        return [self.blender, *JOB_FLAGS, '--python-expr', expression]

    def child_environment(self, job_dir):
        environment = dict(python_worker.JOB_ENVIRONMENT)
        missing = os.path.join(job_dir, MISSING_USER_FOLDER)
        environment.update({name: missing for name in USER_FOLDERS})
        environment['TMPDIR'] = os.path.join(job_dir, RUNTIME_DIRECTORY, 'tmp')
        return environment

    def check_job_folder(self, job_dir):
        # The controller reserves this one empty real directory before sealing the
        # job root. Never chmod that root or adopt preseeded code/user state.
        root = os.path.join(job_dir, RUNTIME_DIRECTORY)
        try:
            info = os.lstat(root)
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_mode & 0o077 or os.listdir(root)):
                raise ValueError('not an empty private directory')
        except (OSError, ValueError):
            raise python_worker.JobRefused(
                'protocol', f'{RUNTIME_DIRECTORY} is not fresh reserved Blender runtime scratch') from None
        os.mkdir(os.path.join(root, 'tmp'), 0o700)


def serve(request_fd, response_fd, sandboxed, blender):
    """Serve one controller over two inherited descriptors, made non-inheritable first."""
    for fd in (request_fd, response_fd):
        os.set_inheritable(fd, False)
    requests = os.fdopen(request_fd, 'rb', buffering=0)
    responses = os.fdopen(response_fd, 'wb', buffering=0)
    BlenderWorker(requests, responses, sandboxed=sandboxed, blender=blender).serve()


def main(argv=None):
    """The production entry, inside the admitted Blender: always sandboxed, no opt-out."""
    if argv is None:
        argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--request-fd', type=int, required=True)
    parser.add_argument('--response-fd', type=int, required=True)
    args = parser.parse_args(argv)
    import bpy  # the jobs use exactly the Blender that was admitted

    serve(args.request_fd, args.response_fd, sandboxed=True, blender=bpy.app.binary_path)


if __name__ == '__main__':
    main()
