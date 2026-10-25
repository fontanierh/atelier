"""Build-v2 Unreal job loop: one editor per admitted session, one job at a time.

Started by the controller (`platform/build-v2/src/unreal.rs`) as

    UnrealEditor-Cmd <scratch>/Atelier.uproject -run=pythonscript -script=<session>/worker/unreal_worker.py \\
        -unattended -nop4 -nosplash -stdout -AllowStdOutLogVerbosity -NullRHI -nocrashreports \\
        -UserDir=<session>/user -nowrite -NoZenAutoLaunch \\
        -DDC=(InstalledEnginePak,V2Local=(Type=FileSystem,Path=<store>/unreal-ddc/<BuildId>)) \\
        [declared -ini:/-ForceDPCVars=] --request-fd N --response-fd M

The script is the session's frozen, read-only copy of this file, beside a frozen `protocol.py` it loads by
path; the source tree is never run. It speaks protocol version 1 (`protocol.py`) on the two inherited pipes, made close-on-exec at once
so no helper process the editor starts inherits them. Stdout and stderr are the editor's logs.

**Unreal is not sandboxed.** Per-job isolation is detection only:
- each job's input packages are copied into the session's empty `/Game` at their logical paths,
  read-only, and removed afterwards;
- the packages saved during the job must be exactly the declared output packages (a package saved
  twice to one file counts once), nothing may be left dirty, no input may change, and no ensure may
  fail (with -nocrashreports an ensure starts no crash reporter and fails the job instead);
- every collected file must hold exactly the bytes its package's last save wrote (the plugin hashes
  a save's files after flushing its writes), every required output must exist, nothing may be written
  into `output/` directly, and each saved package's import evidence comes from its file's own import
  table (an unreadable table fails the job);
- after every job, every package it touched is unloaded, garbage is collected synchronously through
  the plugin, and each package must be gone by `find_object` (neither the unload call's result nor
  `SystemLibrary.collect_garbage`, which only schedules a collection, is trusted); no `/Game`
  package may stay loaded, `/Game` and the asset registry must be empty, the Python state is
  restored, every console variable that existed before the job must keep its value, and one
  registered during the job must still be at its default.

A job whose reset fails still gets its terminal reply; the worker then exits instead of serving
another job, so the controller ends the session (a clean exit after a terminal reply is never crash
evidence for that job). Once per session, before `hello`, the worker recomputes each declared engine
plugin's identity from the folder the editor loaded it from and reads every declared `-ForceDPCVars=`
and `-ini:` setting back from the editor. It then writes the session evidence file
`unreal-context.json` (what it actually loaded, and the editor's effective cache graph read from the
editor, never from the command line) and refuses to start if the context differs from
`Atelier/expected-context.json` or the graph breaks its DDC policy: file-system nodes only inside the
persistent v2 DDC folder, the installed engine pak only at its own path, path-less memory nodes, and
nothing else (no Zen, shared or remote node, no fallback), with at least one node in the v2 folder.
The DDC is acceleration only; nothing here reads it as evidence. Each job's import tables go to `evidence/imports.json` beside, never
inside, `output/`.

The editor surface is `Editor`: the `unreal` module plus the editor-only `AtelierBuildWorker`
plugin library, whose functions this file defines by use (the T0 stand-in implements the same).
"""
from contextlib import contextmanager
from decimal import Decimal
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import stat
import sys

if __package__:
    from . import protocol
else:  # run by the editor as a script: load the sibling module by path
    _spec = importlib.util.spec_from_file_location('build_v2_protocol', Path(__file__).with_name('protocol.py'))
    protocol = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(protocol)

def _bundle_module(name):
    spec = importlib.util.spec_from_file_location('atelier_c3_' + name,
                                                Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def declared_python(job_dir, code, reads, platform_roots):
    """Reuse C2's path/import checks for the project Python body inside C3.

    A caught refusal remains sticky. The audit hook is inactive outside this scope;
    all wrapped process functions and import hooks are restored before reset.
    """
    helper = _bundle_module('python_job')
    class Guard(helper.PathGuard):
        failed = None
        def violation(self, access, path):
            self.failed = f'undeclared Python {access}: {path}'
            raise JobRefused('dependency', self.failed)
    root = str(job_dir)
    guard = Guard(root, [str(p) for p in platform_roots],
                  {str(p) for p in reads}, lambda _: None)
    # Staged job bytes are already immutable. Scratch content contains only this
    # job's staged inputs and native saves; Python itself cannot write there.
    guard.reads += [str(p) for p in reads if Path(p).is_dir()]
    finder = helper.DeclaredCodeFinder(root, set(code), [str(p) for p in platform_roots])
    originals = {name: getattr(os, name) for name in guard.DESCRIPTOR_CALLS if hasattr(os, name)}
    meta, hooks = list(sys.meta_path), list(sys.path_hooks)
    active = [True]
    guard.original_readlink = os.readlink
    sys.addaudithook(lambda event, args: guard.audit(event, args) if active[0] else None)
    try:
        for name, function in originals.items():
            setattr(os, name, guard.wrap(name, function, guard.DESCRIPTOR_CALLS[name]))
        sys.meta_path.insert(0, finder)
        yield
        if guard.failed:
            raise JobRefused('dependency', guard.failed)
    finally:
        active[0] = False
        for name, function in originals.items():
            setattr(os, name, function)
        sys.meta_path[:] = meta
        sys.path_hooks[:] = hooks


WORKER_VERSION = 'atelier-unreal-job-1'
EXPECTED_CONTEXT = 'Atelier/expected-context.json'
CONTEXT_REPORT = 'unreal-context.json'
IMPORT_EVIDENCE = 'evidence/imports.json'
READ_EVIDENCE = 'evidence/reads.json'
EVIDENCE_VERSION = 1
GAME = '/Game/'
INPUT_CONTENT = 'in/content/Game/'
OUTPUT_CONTENT = 'content/Game/'
PACKAGE_FILES = ('.uasset', '.umap', '.uexp', '.m.ubulk', '.ubulk', '.uptnl', '.upayload')
PRIMARY_FILES = ('.uasset', '.umap')
INI_SETTING = re.compile(r'-ini:([^:\[\]]+):\[([^\]]+)\]:([^=]+)=(.*)')


class JobRefused(Exception):
    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


class StartRefused(Exception):
    """The editor's native context or cache graph is not the declared one: no `hello`."""


def plugin_identity(folder, name):
    """The controller's `tree_identity` of a plugin folder: its descriptor and `Binaries/`, by relative path."""
    folder = Path(folder)
    binaries = folder / 'Binaries'
    found = sorted((path.relative_to(folder) for path in binaries.rglob('*') if path.is_file()), key=lambda p: p.parts)
    try:
        manifest = ''.join(f'{relative}\0{sha256(folder / relative)}\n'
                           for relative in [Path(f'{name}.uplugin'), *found])
    except OSError as error:
        return f'unreadable: {error}'
    return hashlib.sha256(manifest.encode()).hexdigest()


def worker_identity():
    """The controller's `UnrealWorkerBundle` digest of the files actually running: this script and the protocol
    module, which must be its sibling in the session's frozen bundle, never a source-tree copy."""
    script, module = Path(__file__).resolve(), Path(protocol.__file__).resolve()
    if module.parent != script.parent:
        return f'protocol loaded from outside the bundle: {module}'
    digests = {name: sha256(script.with_name(name)) for name in
               ('protocol.py', 'python_job.py', 'recipe_job.py', 'unreal_inputs.py', 'unreal_worker.py')}
    canonical = json.dumps({'domain': 'atelier-unreal-worker', 'version': 1, 'files': digests},
                           sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()


DECIMAL = re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?')


def same_value(declared, actual, numeric):
    """Whether the editor holds a declared setting value: `actual` is its readback, None when unset.

    Ini values compare as exact text. A console variable may also print a number its own way
    (`1` as `1.000000`), so with `numeric` two finite decimal texts of the same exact value match;
    nothing is rounded through a binary float, so distinct values never alias.
    """
    if actual is None:
        return False
    if declared == actual:
        return True
    if not numeric or not (DECIMAL.fullmatch(declared) and DECIMAL.fullmatch(actual)):
        return False
    return Decimal(declared) == Decimal(actual)


def ddc_problem(policy, nodes):
    """Why the effective cache graph `nodes` ([{kind, path}], full paths) breaks `policy`, or None."""
    folder = Path(policy['dir'])
    local = False
    for node in nodes:
        path = node['path']
        if node['kind'] == 'File System':
            allowed = bool(path) and Path(path).is_absolute() and Path(path).is_relative_to(folder)
            local = local or allowed
        elif node['kind'] == 'Pak File':
            allowed = path == policy['engine_pak']
        elif node['kind'] in ('Memory', 'Async'):
            allowed = not path
        else:
            allowed = False
        if not allowed:
            return f'a {node["kind"]} node at {path!r} is outside the v2 DDC folder'
    return None if local else 'no cache node is inside the v2 DDC folder'


def validate_read_report(report, declared, platform_roots=(), generated=()):
    """@cc [owner:fontanierh,label:correctness] unreal-observed-input-closure
    Observed unknown reads MUST fail before Completed. Generated files MUST be attested
    outputs of this job. This best-effort report MUST NOT certify unobserved native IO.
    """
    if (not isinstance(report, dict) or set(report) != {'version', 'best_effort', 'files'}
            or type(report['version']) is not int or report['version'] != 1
            or report['best_effort'] is not True or not isinstance(report['files'], list)):
        raise JobRefused('dependency', 'missing or malformed native read report')
    allowed = {Path(path).resolve() for path in (*declared, *generated)}
    roots = tuple(Path(path).resolve() for path in platform_roots)
    unknown = []
    for item in report['files']:
        if not isinstance(item, str) or not Path(item).is_absolute():
            raise JobRefused('dependency', 'native read report contains a non-absolute path')
        path = Path(item).resolve()
        if path not in allowed and not any(path.is_relative_to(root) for root in roots):
            unknown.append(item)
    if unknown:
        raise JobRefused('dependency', f'opened undeclared files: {sorted(set(unknown))}')


def generated_save_reads(report, saved, folder, before):
    """UE SavePackage uses Saved/<package-leaf[:32]><FGuid Digits>.tmp.

    Only a new direct temporary for an actually attested package save is generated state.
    Preexisting names, aliases, other roots and other names remain undeclared reads.
    """
    folder = Path(folder)
    if folder.resolve() != folder or folder.is_symlink():
        return []
    prefixes = {item['package'].rsplit('/', 1)[-1][:32] for item in saved}
    result = []
    for raw in report.get('files', ()):
        path = Path(raw)
        if path.parent == folder and path.name not in before and any(
                re.fullmatch(re.escape(prefix) + r'[0-9A-F]{32}\.tmp', path.name)
                for prefix in prefixes):
            if path.is_symlink():
                continue
            result.append(path)
    return result


def content_has_files(root):
    """Empty editor-created folder scaffolding is not package content; links are never empty."""
    with os.scandir(root) as entries:
        for entry in entries:
            if not entry.is_dir(follow_symlinks=False) or content_has_files(entry.path):
                return True
    return False


def log(message):
    print(f'atelier-unreal-worker: {message}', file=sys.stderr, flush=True)


def sha1(path):
    """Integrity only (a file still holds what its save wrote); never a key ingredient."""
    digest = hashlib.sha1()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 16), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    with open(temporary, 'w', encoding='utf-8') as stream:
        json.dump(value, stream, sort_keys=True, indent=1)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def protocol_fds(command_line):
    """`--request-fd N --response-fd M` from the engine command line (`-script` arguments aside)."""
    tokens = command_line.split()
    found = {}
    for flag in ('--request-fd', '--response-fd'):
        if tokens.count(flag) != 1 or tokens.index(flag) + 1 >= len(tokens):
            raise StartRefused(f'the command line must carry exactly one {flag}')
        value = tokens[tokens.index(flag) + 1]
        if not value.isdigit():
            raise StartRefused(f'{flag} is not a descriptor number')
        found[flag] = int(value)
    request, response = found['--request-fd'], found['--response-fd']
    for fd in (request, response):
        if not stat.S_ISFIFO(os.fstat(fd).st_mode):
            raise StartRefused(f'descriptor {fd} is not a pipe')
        os.set_inheritable(fd, False)
    return request, response


def package_of(relative, root):
    """`/Game/A/B` for `root/A/B.uasset`; None for a non-primary package file."""
    if not relative.startswith(root):
        return None
    rest = relative[len(root):]
    for suffix in PRIMARY_FILES:
        if rest.endswith(suffix):
            return GAME + rest[:-len(suffix)]
    return None


def package_owning(relative, root):
    """`/Game/A/B` for any package file `root/A/B.<package suffix>` (companions included), else None."""
    if not relative.startswith(root):
        return None
    rest = relative[len(root):]
    for suffix in PACKAGE_FILES:
        if rest.endswith(suffix):
            return GAME + rest[:-len(suffix)]
    return None


def _job_relative(path, label):
    parts = path.split('/')
    if not path or path.startswith('/') or '\\' in path or '\0' in path or any(p in ('', '.', '..') for p in parts):
        raise JobRefused('protocol', f'{label} is not a job-relative path: {path!r}')
    return path


class Editor:
    """Everything the loop asks of the editor."""

    def __init__(self, unreal):
        self.unreal = unreal
        self.library = unreal.AtelierBuildWorkerLibrary

    def command_line(self):
        return self.unreal.SystemLibrary.get_command_line()

    def project_dir(self):
        paths = self.unreal.Paths
        return Path(paths.convert_relative_path_to_full(paths.project_dir())).resolve()

    def engine_dir(self):
        paths = self.unreal.Paths
        return Path(paths.convert_relative_path_to_full(paths.engine_dir())).resolve()

    def native_context(self):
        """{build_id, modules, plugins: {name: folder}, libraries: [path], rhi} from the plugin."""
        return json.loads(self.library.native_context())

    def config_value(self, file, section, key):
        """The effective value of an ini key, or None when it is not set."""
        result = json.loads(self.library.config_value(file, section, key))
        return result['value'] if result['found'] else None

    def ddc_graph(self):
        """{graph, nodes: [{kind, path}]}: the editor's effective cache stores, from the plugin."""
        graph = json.loads(self.library.ddc_graph())
        nodes = [{'kind': node['kind'], 'path': str(Path(node['path']).resolve()) if node['path'] else ''}
                 for node in graph['nodes']]
        return {'graph': graph['graph'], 'nodes': nodes}

    def begin_job(self):
        if not self.library.begin_read_recording():
            raise JobRefused('dependency', 'native read recording is unavailable')
        self.library.begin_ensure_count()
        self.library.begin_save_recording()

    def read_report(self):
        return json.loads(self.library.end_read_recording())

    def ensures(self):
        """Failed ensures since `begin_job` (the editor runs with -nocrashreports, so none is reported elsewhere)."""
        return self.library.ensure_count()

    def saved_packages(self):
        """[{package, filename, files: {path: sha1}}] saved since `begin_job`; each save's files are hashed after
        its writes were flushed, so later plain file writes show as a mismatch."""
        return json.loads(self.library.end_save_recording())

    def finish_background_work(self):
        self.library.finish_background_work()

    def dirty_packages(self):
        return list(self.library.dirty_package_names())

    def loaded_game_packages(self):
        return sorted(self.library.loaded_package_names(GAME))

    def imports(self, filename):
        """[[path, class]] from the saved file's own import table, in table order; None when unreadable."""
        text = self.library.package_imports(str(filename))
        return [list(item) for item in json.loads(text)] if text else None

    def settings(self):
        """{console variable: [value, set by]}; set by "Constructor" means still at its default."""
        return json.loads(self.library.settings_snapshot())

    def scan(self, files):
        registry = self.unreal.AssetRegistryHelpers.get_asset_registry()
        registry.scan_files_synchronous([str(path) for path in files], True)

    def forget(self, files):
        """Drop deleted files from the asset registry (a commandlet watches no folders)."""
        self.library.forget_files([str(path) for path in files])

    def registry_game_assets(self):
        registry = self.unreal.AssetRegistryHelpers.get_asset_registry()
        return len(registry.get_assets_by_path('/Game', True))

    def unload(self, packages, passes=3):
        """Unload `packages` with a synchronous garbage collection, and say which are still in memory.

        One pass is not enough after an import: while the import task still holds its assets the first
        unload leaves them standalone (it frees nothing), and only a second unload after the collection
        drops them. Up to `passes` passes run until nothing is left. The unload call's own result ("any",
        not "all") is never trusted.
        """
        remaining = list(packages)
        for _ in range(passes):
            objects = [self.unreal.find_object(None, name) for name in remaining]
            objects = [value for value in objects if value is not None]
            if objects:
                self.unreal.EditorLoadingAndSavingUtils.unload_packages(objects)
            del objects
            # SystemLibrary.collect_garbage only schedules a collection for the next engine tick, which a
            # commandlet script never reaches; the plugin collects now.
            self.library.collect_garbage_now()
            remaining = [name for name in remaining if self.unreal.find_object(None, name) is not None]
            if not remaining:
                break
        return remaining


class Context:
    """What an op sees: its params, staged inputs and declared outputs; no repository paths."""

    def __init__(self, job_dir, inputs, packages, params, outputs, content_dir):
        self.job_dir = Path(job_dir)
        self.inputs = inputs  # name -> logical package (staged) or job-folder path
        self.packages = packages  # name -> logical package, for staged package inputs
        self.params = params
        self.outputs = outputs  # declared output packages
        self.content_dir = Path(content_dir)


class Worker:
    def __init__(self, editor, requests, responses):
        self.editor = editor
        self.requests = requests
        self.responses = responses
        self.project = editor.project_dir()
        self.content = self.project / 'Content'
        self.read_platform_roots = ()

    def send(self, message):
        protocol.write_frame(self.responses, protocol.RESPONSE, message)

    def start(self):
        """Report the loaded context as session evidence, then refuse a mismatch before `hello`."""
        expected = json.loads((self.project / EXPECTED_CONTEXT).read_text(encoding='utf-8'))
        native = self.editor.native_context()
        declared = set(expected['plugins'])
        plugins = {name for name, folder in native['plugins'].items()
                   if name in declared or Path(folder).resolve().is_relative_to(self.project)}
        libraries = {}
        for library in native['libraries']:
            path = Path(library).resolve()
            if path.is_relative_to(self.project):
                libraries[str(path.relative_to(self.project))] = sha256(path)
            elif not path.is_relative_to(self.editor.engine_dir()):
                libraries[str(path)] = sha256(path)  # neither project nor engine: always a mismatch
        # Once per session: the declared engine plugins' bytes, and the declared settings as the editor holds them.
        engine_plugins = {name: plugin_identity(native['plugins'][name], name) if name in native['plugins'] else 'not loaded'
                          for name in expected['engine_plugins']}
        cvars, reads = self.editor.settings(), []
        loaded = {'worker_version': WORKER_VERSION, 'profile': expected['profile'], 'build_id': native['build_id'],
                  'modules': sorted(native['modules']), 'plugins': sorted(plugins), 'libraries': libraries,
                  'engine_plugins': engine_plugins, 'worker': worker_identity(),
                  'settings': [self.observed_setting(token, cvars, reads) for token in expected['settings']],
                  'rhi': native['rhi'], 'ddc': expected['ddc']}
        graph = self.editor.ddc_graph()
        write_atomic(self.project.parent / CONTEXT_REPORT,
                     {'version': EVIDENCE_VERSION, 'loaded': loaded, 'ddc_graph': graph, 'settings_read': reads,
                      **({'native_worker_source_digest': native['worker_source_digest']}
                         if 'worker_source_digest' in native else {})})
        if loaded != {**expected, 'modules': sorted(expected['modules']), 'plugins': sorted(expected['plugins'])}:
            raise StartRefused('the editor loaded a different native context than the session declared')
        problem = ddc_problem(expected['ddc'], graph['nodes'])
        if problem:
            raise StartRefused(f"the editor's cache graph is not the v2 graph: {problem}")
        self.read_platform_roots = (self.editor.engine_dir(), Path(expected['ddc']['dir']))
        if content_has_files(self.content) or self.editor.registry_game_assets():
            raise StartRefused('/Game is not empty at startup')

    def observed_setting(self, token, cvars, reads):
        """A declared setting rebuilt from the editor's own values: equal to `token` only if the editor applied it.

        Each raw readback is appended to `reads`. A value the editor does not hold at all never
        rebuilds a token, whatever the declared text.
        """
        if token.startswith('-ForceDPCVars='):
            pairs = []
            for pair in token[len('-ForceDPCVars='):].split(','):
                name, _, value = pair.partition('=')
                actual = cvars[name][0] if name in cvars else None
                reads.append({'setting': token, 'name': name, 'actual': actual})
                if actual is None:
                    return f'missing {name} in {token}'
                pairs.append(f'{name}={value if same_value(value, actual, numeric=True) else actual}')
            return '-ForceDPCVars=' + ','.join(pairs)
        match = INI_SETTING.fullmatch(token)
        if match:
            file, section, key, value = match.groups()
            actual = self.editor.config_value(file, section, key)
            reads.append({'setting': token, 'name': f'{file}:[{section}]:{key}', 'actual': actual})
            if actual is None:
                return f'missing {file}:[{section}]:{key} in {token}'
            return f'-ini:{file}:[{section}]:{key}={value if same_value(value, actual, numeric=False) else actual}'
        reads.append({'setting': token, 'name': '', 'actual': None})
        return f'unreadable {token}'

    def serve(self):
        """Serve jobs until `shutdown`, the end of the request stream, or a failed reset."""
        self.send({'type': 'hello', 'worker_version': WORKER_VERSION})
        while True:
            request = protocol.read_frame(self.requests, protocol.REQUEST)
            if request is None:
                return 'requests ended'
            if request['type'] == 'shutdown':
                self.send({'type': 'stopped'})
                return 'shutdown'
            if request['type'] == 'run':
                reset_problem = self.run(request['job'])
                if reset_problem:
                    log(f'retiring after a terminal reply: {reset_problem}')
                    return 'retired'
            # A cancel can only be read between jobs, so it always names a finished job: no reply.

    def run(self, job):
        """Run one job; returns why the editor may not serve another, or None."""
        job_id = job['job_id']
        self.send({'type': 'started', 'job_id': job_id})
        state = _PythonState()
        touched, moved = set(), []
        try:
            files = self.execute(job, touched, moved)
        except JobRefused as refusal:
            reply = {'type': 'failed', 'job_id': job_id, 'failure': {'kind': refusal.kind, 'message': str(refusal)}}
        except Exception as error:  # the op's own failure
            reply = {'type': 'failed', 'job_id': job_id,
                     'failure': {'kind': 'job', 'message': f'{type(error).__name__}: {error}'}}
        else:
            reply = {'type': 'completed', 'job_id': job_id, 'outputs': {'files': files}}
        try:
            problem = self.reset(job, touched, moved, state)
        except Exception as error:  # the editor is in an unknown state: reply, then retire
            problem = f'reset raised {type(error).__name__}: {error}'
        self.send(reply)
        return problem

    def execute(self, job, touched, moved):
        job_dir = Path(job['job_dir'])
        if not job_dir.is_absolute() or not (job_dir / 'output').is_dir():
            raise JobRefused('protocol', 'the job folder is not a staged absolute folder with output/')
        if any((job_dir / 'output').iterdir()):
            raise JobRefused('protocol', 'output/ is not empty before the job')
        if content_has_files(self.content):
            raise JobRefused('dependency', '/Game is not empty before the job')
        declared, required = {}, set()
        for item in job['outputs']:
            path = _job_relative(item['path'], 'output')
            if not path.startswith(OUTPUT_CONTENT) or not path.endswith(PACKAGE_FILES):
                raise JobRefused('protocol', f'output {path!r} is not a package file under {OUTPUT_CONTENT}')
            declared[path] = item['required']
        packages = {package_of(path, OUTPUT_CONTENT) for path in declared} - {None}
        required = {package_of(path, OUTPUT_CONTENT) for path, need in declared.items() if need} - {None}
        if job['script'] not in job['code']:
            raise JobRefused('protocol', 'the entry script is outside the declared code')
        helper = _bundle_module('unreal_inputs')
        try:
            prepared = helper.stage_inputs(job_dir, job['inputs'], self.content,
                runtime_dir=job_dir / '.unreal-runtime', output_packages=packages,
                root_bindings=job['params'].get('input_roots', {}))
        except (OSError, ValueError) as error:
            raise JobRefused('dependency', str(error)) from error
        staged, inputs, input_packages = (prepared['staged_files'], prepared['inputs'], prepared['packages'])
        for values in input_packages.values():
            touched.update(values)
        if staged:
            self.editor.scan(staged)
        self.settings = self.editor.settings()
        save_folder = self.project.parent / 'user' / 'Saved'
        save_before = set(os.listdir(save_folder)) if save_folder.is_dir() else set()
        self.editor.begin_job()
        recording = True
        try:
            with declared_python(job_dir, job['code'],
                    [*prepared['declared_reads'], self.content],
                    [*self.read_platform_roots, Path(sys.base_prefix), Path(sys.prefix)]):
                entry = runpy.run_path(str(job_dir / job['script']), run_name='atelier_unreal_job')
                if not callable(entry.get('run')):
                    raise JobRefused('protocol', 'the entry script defines no run(context)')
                entry['run'](Context(job_dir, inputs, input_packages, job['params'], sorted(packages), self.content))
            self.editor.finish_background_work()
            saved = self.editor.saved_packages()
            read_report = self.editor.read_report()
            recording = False
        finally:
            if recording:
                touched.update(item['package'] for item in self.editor.saved_packages())
                self.editor.read_report()
        # Every file a save attested, with the package that saved it: in save order, so a file's
        # latest attestation wins, and a later save that leaves a companion alone keeps its hash.
        files_of, attested, shared = {}, {}, set()
        for item in saved:  # a rename saves the same package twice to the same file: one save
            files_of.setdefault(item['package'], set()).add(item['filename'])
            for path, digest in item['files'].items():
                resolved = str(Path(path).resolve())
                owner = attested.get(resolved, (item['package'], None))[0]
                if owner != item['package']:
                    shared.add(resolved)
                attested[resolved] = (item['package'], digest)
        write_atomic(job_dir / READ_EVIDENCE, read_report)
        declared_reads = [job_dir / path for path in job['code']]
        declared_reads += prepared['declared_reads']
        declared_reads += list(staged)
        generated = [*attested, *generated_save_reads(read_report, saved, save_folder, save_before)]
        validate_read_report(read_report, declared_reads, self.read_platform_roots, generated)
        # The registry forgets every saved file at reset, even one the op deleted afterwards.
        moved.extend(Path(filename) for filenames in files_of.values() for filename in filenames)
        names = set(files_of)
        touched.update(names | packages)
        split = sorted(name for name, files in files_of.items() if len(files) > 1)
        if split:
            raise JobRefused('dependency', f'saved packages to more than one file: {split}')
        if shared:
            raise JobRefused('dependency', f'more than one package saved the same file: {sorted(shared)}')
        ensures = self.editor.ensures()
        if ensures:
            raise JobRefused('job', f'the editor reported {ensures} failed ensure(s) during the job')
        if names - packages:
            raise JobRefused('dependency', f'saved undeclared packages: {sorted(names - packages)}')
        if any((job_dir / 'output').iterdir()):
            raise JobRefused('dependency', 'the job wrote into output/ directly; only package saves produce outputs')
        if required - names:
            raise JobRefused('job', f'did not save declared packages: {sorted(required - names)}')
        dirty = sorted(name for name in self.editor.dirty_packages() if name.startswith(GAME))
        if dirty:
            raise JobRefused('job', f'left unsaved changes in {dirty}')
        for target, digest in staged.items():
            if not target.is_file() or sha256(target) != digest:
                raise JobRefused('dependency', f'input {target.relative_to(self.content)} changed')
        files = {}
        for directory, _, names_here in os.walk(self.content):
            for name in names_here:
                path = Path(directory, name)
                if path in staged:
                    continue
                relative = OUTPUT_CONTENT + str(path.relative_to(self.content))
                if relative not in declared:
                    raise JobRefused('dependency', f'wrote undeclared file {relative}')
                package = package_owning(relative, OUTPUT_CONTENT)
                if package not in names:
                    # Only the editor's package saves produce outputs, never plain file writes.
                    raise JobRefused('dependency', f'{relative} was written without saving its package')
                owner, digest = attested.get(str(path.resolve()), (None, None))
                if owner is None:
                    # A file already there that the save left alone: a plain write, not a save.
                    raise JobRefused('dependency', f'{relative} was not written by its package save')
                if owner != package:
                    raise JobRefused('dependency', f'{relative} was saved by {owner}, not by {package}')
                if digest != sha1(path):
                    raise JobRefused('dependency', f'{relative} does not hold the bytes its package save wrote')
                files[relative] = path
        missing = sorted(path for path, need in declared.items() if need and path not in files)
        if missing:
            raise JobRefused('job', f'required outputs are missing after the job: {missing}')
        imports = {}
        for name in sorted(names):
            (filename,) = files_of[name]
            imports[name] = self.editor.imports(filename)
            if imports[name] is None:
                raise JobRefused('job', f'could not read the import table of {name}')
        for relative, path in files.items():
            target = job_dir / 'output' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            moved.append(path)
            shutil.move(path, target)
        write_atomic(job_dir / IMPORT_EVIDENCE, {'version': EVIDENCE_VERSION, 'packages': [
            {'package': name, 'imports': imports[name]} for name in sorted(names)]})
        return sorted(files)

    def reset(self, job, touched, moved, state):
        """Return the editor to its between-jobs state; returns the first problem, or None."""
        problems = []
        state.restore(Path(job['job_dir']))
        removed = list(moved)  # outputs moved to the job folder left /Game as well
        for directory, folders, names in os.walk(self.content, topdown=False):
            for name in names:
                path = Path(directory, name)
                os.chmod(path, 0o644)
                path.unlink()
                removed.append(path)
            for name in folders:
                Path(directory, name).rmdir()
        if removed:
            self.editor.forget(removed)
        remaining = self.editor.unload(sorted(touched | set(self.editor.loaded_game_packages())))
        if remaining:
            problems.append(f'packages still loaded after unload: {remaining}')
        if self.editor.loaded_game_packages():
            problems.append(f'/Game packages still loaded: {self.editor.loaded_game_packages()}')
        if self.editor.registry_game_assets():
            problems.append('the asset registry still lists /Game assets')
        before = getattr(self, 'settings', None)
        if before is not None:
            after = self.editor.settings()
            changed = sorted(name for name, value in before.items() if after.get(name) != value)
            # A variable registered during the job (a module loaded on demand) may stay only at its default.
            moved = sorted(name for name, value in after.items() if name not in before and value[1] != 'Constructor')
            if changed or moved:
                problems.append(f'the job changed editor settings: {(changed + moved)[:8]}')
        self.settings = None
        return '; '.join(problems) or None


class _PythonState:
    """sys.path, argv, environment, cwd and the module table, as they were before the job."""

    def __init__(self):
        self.path = list(sys.path)
        self.argv = list(sys.argv)
        self.environ = dict(os.environ)
        self.cwd = os.getcwd()
        self.modules = set(sys.modules)

    def restore(self, job_dir):
        sys.path[:] = self.path
        sys.argv[:] = self.argv
        os.environ.clear()
        os.environ.update(self.environ)
        os.chdir(self.cwd)
        for name in set(sys.modules) - self.modules:
            module = sys.modules.get(name)
            location = getattr(module, '__file__', None) or ''
            # Modules the job brought in from its own folder never outlive it.
            if location and Path(location).resolve().is_relative_to(job_dir.resolve()):
                del sys.modules[name]


def main():
    import unreal  # inside the editor

    editor = Editor(unreal)
    try:
        request_fd, response_fd = protocol_fds(editor.command_line())
        requests = os.fdopen(request_fd, 'rb', buffering=0)
        responses = os.fdopen(response_fd, 'wb', buffering=0)
        worker = Worker(editor, requests, responses)
        worker.start()
    except StartRefused as refusal:
        log(f'refusing to start: {refusal}')
        raise SystemExit(3)
    log(f'stopping: {worker.serve()}')


if __name__ == '__main__':
    main()
