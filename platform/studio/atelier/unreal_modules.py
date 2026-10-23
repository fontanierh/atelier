"""Digests of a game's compiled Unreal modules, for steps whose results depend on game code: an import that calls a
module's functions, or saves its classes in assets.

A module's digest covers what an editor running it loads (closure): its module and every game or plugin module that
brings in (the libraries it links, by their load commands, and the repository plugins those belong to and depend on,
whole). Each is keyed by its compile inputs, never by library bytes: the module's source folder (code and Build.cs),
the project's target rules, the descriptors that decide what loads, the config files of the project and those plugins
(which set class defaults too), and the installed engine and Xcode toolchain/SDK identity. Library bytes embed the
checkout's absolute source paths, so the same sources compiled in another worktree would otherwise never match. Each
library must still exist (validation, not identity); a prebuilt module without sources keys on its library bytes.
Unreal relinks only the libraries whose code changed, so an edit in a module outside the closure leaves the digest
unchanged: a game keeps what its imports save (data assets, placed actors) in small modules apart from its gameplay.

`steps()` makes a cutoff step per module: it reruns after every compile, and its dependents rerun only when the digest
changes. A script that uses game modules lists them in `UnrealScript(modules=...)` and needs their steps. It runs in
an editor started on `descriptor()`, which loads only their closure and exists only for that run, and
unreal_script_guard fails the step if any other game or plugin library is loaded when the script ends.
"""
import hashlib, json, os, subprocess
from types import SimpleNamespace
from contextlib import contextmanager
from pathlib import Path

from .build import Call, Step, module_step

PLATFORM, TARGET = 'Mac', 'UnrealEditor'


def project_modules(project):
    """The game and plugin modules the editor target built: {module: library file name}."""
    manifest = Path(project) / 'Binaries' / PLATFORM / f'{TARGET}.modules'
    return json.loads(manifest.read_text())['Modules'] if manifest.exists() else {}


def links(library):
    """The file names of the libraries `library` loads, from its load commands (otool -L), without its own."""
    lines = subprocess.check_output(['otool', '-L', str(library)], text=True).splitlines()[1:]
    names = [line.split()[0].rpartition('/')[2] for line in lines if line.strip()]
    return [name for name in names if name != Path(library).name]


def linked(project, module):
    """The game and plugin modules the module's library links (none when it was not built: code() says so)."""
    libraries = project_modules(project)
    library = Path(project) / 'Binaries' / PLATFORM / libraries.get(module, '-')
    names = {file: name for name, file in libraries.items()}
    return {names[name] for name in links(library) if name in names} if library.is_file() else set()


def _file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources(uproject):
    """{module: its source folder}, the folders holding <Module>.Build.cs under the project's and plugins' Source."""
    project = Path(uproject).parent
    roots = [project / 'Source', *(path.parent / 'Source' for path, _, _ in plugins(uproject).values())]
    found = {}
    for root in roots:
        for rules in sorted(root.rglob('*.Build.cs')) if root.is_dir() else []:
            found.setdefault(rules.name[:-len('.Build.cs')], rules.parent)
    return found


def _tree(folder):
    """{relative path: sha256} of a source folder's files, independent of where the checkout lives."""
    return {path.relative_to(folder).as_posix(): _file_hash(path) for path in sorted(folder.rglob('*'))
            if path.is_file() and not any(part.startswith('.') for part in path.relative_to(folder).parts)}


_TOOLS = {}


def tool_identity(engine_root=None):
    """The installed engine build and the selected Xcode toolchain/SDK, which decide what a source compiles to."""
    from . import engine
    from .native_protocol import context
    root = Path(engine_root or engine.unreal_root())
    if root not in _TOOLS:
        value = context(SimpleNamespace(unreal_root=root))
        _TOOLS[root] = {'engine': value['engine'], 'toolchain': value['toolchain'],
                        'system': value['system'], 'machine': value['machine']}
    return _TOOLS[root]


def plugins(uproject):
    """The repository's plugins the project can load (its Plugins folder and AdditionalPluginDirectories):
    {name: (its .uplugin, its module names, names of the plugins it depends on)}."""
    project = Path(uproject).parent
    folders = [project / 'Plugins',
               *(project / d for d in json.loads(Path(uproject).read_text()).get('AdditionalPluginDirectories', []))]
    found = {}
    for folder in folders:
        for path in sorted(folder.rglob('*.uplugin')) if folder.is_dir() else []:
            plugin = json.loads(path.read_text())
            found[path.stem] = (path, [m['Name'] for m in plugin.get('Modules', [])],
                                [d['Name'] for d in plugin.get('Plugins', []) if d.get('Enabled', True)])
    return found


def closure(uproject, modules):
    """The game and plugin modules an editor running `modules` loads: those, the modules their libraries link, and the
    plugins those belong to and depend on, whole (an enabled plugin loads every module the editor target built for
    it), until nothing is added."""
    project = Path(uproject).parent
    available, built = plugins(uproject), project_modules(project)
    owner = {module: name for name, (_, names, _) in available.items() for module in names}
    found, pending = set(), list(modules)
    while pending:
        name = pending.pop()
        if name in found:
            continue
        found.add(name)
        pending += linked(project, name)
        if name in owner:
            plugin = owner[name]
            pending += [m for p in (plugin, *available[plugin][2]) for m in available.get(p, (None, (), ()))[1] if m in built]
    return found


def code(uproject, module, *, tools=None):
    """{file: sha256} of the compile inputs of the module and everything an editor running it loads (closure): their
    sources, the target rules, the descriptors and config files (the project's and its enabled plugins') that decide
    what loads and the classes' defaults, and the engine/toolchain identity. Every library must have been built."""
    project = Path(uproject).parent
    libraries, binaries = project_modules(project), project / 'Binaries' / PLATFORM
    loaded = closure(uproject, [module])
    files = {f'<config>/{path.relative_to(project).as_posix()}': _file_hash(path) for path in project.glob('Config/**/*.ini')}
    files.update({f'<targets>/{path.name}': _file_hash(path) for path in sorted((project / 'Source').glob('*.Target.cs'))})
    tools = tool_identity() if tools is None else tools
    files['<tools>'] = hashlib.sha256(json.dumps(tools, sort_keys=True).encode()).hexdigest()
    folders = sources(uproject)
    files[Path(uproject).name] = _file_hash(Path(uproject))
    for path, names, _ in plugins(uproject).values():
        if set(names) & loaded:       # an enabled plugin's config is merged into the project's
            files[path.name] = _file_hash(path)
            files.update({f'<{path.stem}>/{c.relative_to(path.parent).as_posix()}': _file_hash(c)
                          for c in path.parent.glob('Config/**/*.ini')})
    for name in loaded:
        library = binaries / libraries.get(name, '-')
        if not library.is_file() or library.stat().st_size == 0:
            raise SystemExit(f'{name}: the editor target did not build it; compile the editor first')
        if name in folders:
            files.update({f'<{name}>/{relative}': digest for relative, digest in _tree(folders[name]).items()})
        else:  # A prebuilt module without sources: its library is its only identity.
            files[library.name] = _file_hash(library)
    return dict(sorted(files.items()))


@contextmanager
def descriptor(uproject, modules):
    """A project descriptor that loads only `modules` and what they need (closure): the other game modules are left
    out and the repository's other plugins disabled. It sits beside `uproject`, as Unreal takes the project's Content,
    Config and Saved from the descriptor's folder, and exists only inside this block, which removes it however it ends.
    Its name follows its contents, so the editor's project name (and its log) is the same on every run.
    Yields (its path, the libraries it leaves out)."""
    uproject = Path(uproject)
    project, allowed = uproject.parent, closure(uproject, modules)
    original = json.loads(uproject.read_text())
    contents = dict(original, Modules=[m for m in original.get('Modules', []) if m['Name'] in allowed])
    disabled = sorted(name for name, (_, names, _) in plugins(uproject).items() if not set(names) & allowed)
    contents['Plugins'] = [p for p in original.get('Plugins', []) if p['Name'] not in disabled]
    contents['Plugins'] += [{'Name': name, 'Enabled': False} for name in disabled]
    text = json.dumps(contents, indent=1) + '\n'
    path = uproject.with_name(f'{uproject.stem}_{hashlib.sha256(text.encode()).hexdigest()[:8]}.uproject')
    binaries = (project / 'Binaries' / PLATFORM).resolve()
    left_out = sorted(str(binaries / library) for module, library in project_modules(project).items() if module not in allowed)
    temporary = path.with_suffix(f'.{os.getpid()}')
    try:
        temporary.write_text(text)
        temporary.replace(path)
        yield path, left_out
    finally:
        temporary.unlink(missing_ok=True)
        path.unlink(missing_ok=True)


def record(uproject, module, output, *, tools=None):
    files = code(uproject, module, tools=tools)
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({'module': module, 'digest': digest, 'files': files}, indent=1) + '\n')
    return digest


def steps(ctx, modules, compile='unreal.compile'):
    """A cutoff step per module recording its digest after `compile`. This file is an input: a change to how the
    digest is taken reruns them."""
    made = []
    for module in dict.fromkeys(modules):
        output = ctx.out / 'unreal-modules' / f'{module}.json'

        def write(ctx, log, module=module, output=output):
            tools = tool_identity(getattr(ctx, 'unreal_root', None))
            log.write(f'{module} code digest {record(ctx.uproject, module, output, tools=tools)}\n')
        made.append(Step(module_step(module), [Call(f'unreal module digest {module}', write)], inputs=[Path(__file__)],
                         needs=[compile], outputs=[output], cutoff=True, about=f'the code digest of the compiled {module} module'))
    return made


def needs(modules):
    """The module steps a step whose script declares `modules` needs."""
    return [module_step(m) for m in dict.fromkeys(modules)]
