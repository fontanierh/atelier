"""Digests of a game's compiled Unreal modules, for steps whose results depend on game code: an import that calls a
module's functions, or saves its classes in assets.

A module's digest covers what an editor running it loads (closure): its library and every game or plugin library that
brings in (the libraries it links, by their load commands, and the repository plugins those belong to and depend on,
whole), by content, with the descriptors that decide what loads and the config files of the project and those plugins,
which set class defaults too. A library holds all the module's compiled code, whatever its sources, generated code or compiler
options; engine libraries are left out, as the engine is installed at a fixed version. Unreal relinks only the
libraries whose code changed, so an edit in a module outside the closure leaves the digest unchanged: a game keeps
what its imports save (data assets, placed actors) in small modules apart from its gameplay.

`steps()` makes a cutoff step per module: it reruns after every compile, and its dependents rerun only when the digest
changes. A script that uses game modules lists them in `UnrealScript(modules=...)` and needs their steps. It runs in
an editor started on `descriptor()`, which loads only their closure and exists only for that run, and
unreal_script_guard fails the step if any other game or plugin library is loaded when the script ends.
"""
import hashlib, json, os, subprocess
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


def code(uproject, module):
    """{file: sha256} of the libraries of the module and everything an editor running it loads (closure), and of the
    descriptors and config files (the project's and its enabled plugins') that decide what loads and the classes'
    defaults."""
    project = Path(uproject).parent
    libraries, binaries = project_modules(project), project / 'Binaries' / PLATFORM
    loaded = closure(uproject, [module])
    files = {f'<config>/{path.relative_to(project).as_posix()}': _file_hash(path) for path in project.glob('Config/**/*.ini')}
    files[Path(uproject).name] = _file_hash(Path(uproject))
    for path, names, _ in plugins(uproject).values():
        if set(names) & loaded:       # an enabled plugin's config is merged into the project's
            files[path.name] = _file_hash(path)
            files.update({f'<{path.stem}>/{c.relative_to(path.parent).as_posix()}': _file_hash(c)
                          for c in path.parent.glob('Config/**/*.ini')})
    for name in loaded:
        library = binaries / libraries.get(name, '-')
        if not library.is_file():
            raise SystemExit(f'{name}: the editor target did not build it; compile the editor first')
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


def record(uproject, module, output):
    files = code(uproject, module)
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
            log.write(f'{module} code digest {record(ctx.uproject, module, output)}\n')
        made.append(Step(module_step(module), [Call(f'unreal module digest {module}', write)], inputs=[Path(__file__)],
                         needs=[compile], outputs=[output], cutoff=True, about=f'the code digest of the compiled {module} module'))
    return made


def needs(modules):
    """The module steps a step whose script declares `modules` needs."""
    return [module_step(m) for m in dict.fromkeys(modules)]
