"""Digests of a game's compiled Unreal modules, for steps whose results depend on game code: an import that calls a
module's functions, or saves its classes in assets.

A module has two digests, read from what the compile left in the project's Intermediate folder:

- `code`: every source file in the repository that the compiler read for the module (its .d dependency files), and for
  each game or plugin module it links, by content. Engine sources are left out: the engine is installed at a fixed
  version. An edit in an unrelated module leaves it unchanged.
- `interface`: the module's reflected declarations, from the files UnrealHeaderTool generated for it: its classes,
  structs and enums, with their properties and functions. Function bodies and the defaults constructors set are not
  part of it, so editing them leaves it unchanged; assets keep only values that differ from a class's defaults.

`steps()` makes a cutoff step per digest: it reruns after every compile, and its dependents rerun only when the
digest changes. A script that uses game modules lists them in `UnrealScript(modules=...)` and needs their steps;
unreal_script_guard stops it if it uses any other game module, or calls functions of a module it only declares by
interface.
"""
import hashlib, json, re
from pathlib import Path

from . import engine, paths
from .build import Call, Step, module_step

PLATFORM, TARGET, CONFIGURATION = 'Mac', 'UnrealEditor', 'Development'
GENERATED = ('.generated.h', '.gen.cpp')
# Generated identifiers embed the header's absolute path and line numbers, and reload checksums hash them: neither is
# part of a declaration.
DEPENDENCY = re.compile(r'(?:\\.|[^\s\\])+')
VOLATILE = [(re.compile(r'FID_\w+'), 'FID'), (re.compile(r'(CONSTRUCT_RELOAD_VERSION_INFO\([^\n]*?), \d+U\)'), r'\1)')]


def project_modules(project):
    """The game and plugin modules the editor target built: {module: library file name}."""
    manifest = Path(project) / 'Binaries' / PLATFORM / f'{TARGET}.modules'
    return json.loads(manifest.read_text())['Modules'] if manifest.exists() else {}


def object_dir(project, module):
    """Where the compile put the module's objects: the game's own modules, or plugins from outside the project."""
    for folder in ('Build', 'External/Build'):
        for found in sorted((Path(project) / 'Intermediate' / folder / PLATFORM).glob(f'*/{TARGET}/{CONFIGURATION}/{module}')):
            return found
    raise SystemExit(f'{module}: no compiled objects in {project}/Intermediate; compile the editor first')


def dependencies(folder, compiled_in):
    """Every file the compiler read for the module's objects, from their .d files (Makefile syntax: a space in a path
    is escaped, as in the installed engine's 'Epic\\ Games'). Relative paths are from the compiler's working
    directory, `compiled_in`."""
    files = set()
    for depfile in sorted(folder.glob('*.d')):
        text = depfile.read_text(errors='ignore').replace('\\\n', ' ')
        for line in text.splitlines():
            _, _, listed = line.partition(': ')
            files.update(Path(compiled_in, re.sub(r'\\(.)', r'\1', p)) for p in DEPENDENCY.findall(listed))
    return files


def linked(project, folder):
    """The game and plugin modules the module's library links."""
    names = {library: module for module, library in project_modules(project).items()}
    binaries = (Path(project) / 'Binaries' / PLATFORM).resolve()
    found = set()
    for response in folder.glob('*.dylib.rsp'):
        for quoted in re.findall(r'"([^"]+\.dylib)"', response.read_text(errors='ignore')):
            path = Path(quoted)
            if path.is_absolute() and path.resolve().parent == binaries and path.name in names:
                found.add(names[path.name])
    return found


def _file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else 'missing'


def compiled_in(unreal_root=None):
    """Where Unreal's build tool runs the compiler: the engine's Source folder."""
    return Path(unreal_root or engine.unreal_root()) / 'Engine' / 'Source'


def code(project, module, repo=None, unreal_root=None):
    """{repo-relative path: sha256} of every repository source the module and the modules it links were built from."""
    repo, source = Path(repo or paths.REPO).resolve(), compiled_in(unreal_root)
    files, seen, pending = {}, set(), [module]
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        folder = object_dir(project, name)
        definitions = folder / f'Definitions.{name}.h'   # what the module's build rules define
        if definitions.exists():
            files[f'<{name}>/{definitions.name}'] = _file_hash(definitions)
        for path in dependencies(folder, source):
            resolved = path.resolve()
            if not resolved.is_relative_to(repo):
                continue
            relative = resolved.relative_to(repo)
            if {'Intermediate', 'Binaries'} & set(relative.parts):
                continue
            files[relative.as_posix()] = _file_hash(resolved)
        pending.extend(linked(project, folder) - seen)
    return dict(sorted(files.items()))


def interface(project, module, unreal_root=None):
    """{generated file name: sha256 of its normalized text} of the module's reflection code."""
    files = {}
    for path in dependencies(object_dir(project, module), compiled_in(unreal_root)):
        if path.name.endswith(GENERATED) and path.parent.name == 'UHT' and path.parent.parent.name == module:
            text = path.read_text(errors='ignore') if path.is_file() else 'missing'
            for pattern, replacement in VOLATILE:
                text = pattern.sub(replacement, text)
            files[path.name] = hashlib.sha256(text.encode()).hexdigest()
    if not files:
        raise SystemExit(f'{module}: no generated reflection code found; does it declare any UCLASS, USTRUCT or UENUM?')
    return dict(sorted(files.items()))


def record(project, module, kind, output, unreal_root=None):
    files = (code if kind == 'code' else interface)(project, module, unreal_root=unreal_root)
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({'module': module, 'kind': kind, 'digest': digest, 'files': files}, indent=1) + '\n')
    return digest


def steps(ctx, modules, compile='unreal.compile'):
    """A cutoff step per (module, kind) recording that digest after `compile`."""
    made = []
    for module, kind in dict.fromkeys(modules):
        if kind not in ('code', 'interface'):
            raise ValueError(f'{module}: kind must be code or interface, not {kind!r}')
        output = ctx.out / 'unreal-modules' / f'{module}.{kind}.json'

        def write(ctx, log, module=module, kind=kind, output=output):
            log.write(f'{module} {kind} digest {record(ctx.uproject.parent, module, kind, output, ctx.unreal_root)}\n')
        made.append(Step(module_step(module, kind), [Call(f'unreal module {kind} digest {module}', write)], needs=[compile],
                         outputs=[output], cutoff=True, about=f'the {kind} digest of the compiled {module} module'))
    return made


def needs(modules):
    """The module steps a step whose script declares `modules` needs."""
    return [module_step(*m) for m in dict.fromkeys(modules)]
