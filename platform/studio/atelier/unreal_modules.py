"""Digests of a game's compiled Unreal modules, for steps whose results depend on game code: an import that calls a
module's functions, or saves its classes in assets.

A module has two digests, read from what the compile left in the project's Intermediate folder:

- `code`: every source file in the repository that the compiler read for the module (its .d dependency files), and for
  each game or plugin module it links, by content. Engine sources are left out: the engine is installed at a fixed
  version. An edit in an unrelated module leaves it unchanged.
- `interface`: what assets saved with the module's types depend on. Its reflected declarations, from the files
  UnrealHeaderTool generated for it (classes, structs and enums, with their properties and functions), and each class's
  and struct's defaults: the text of its header and of its constructor and PostInitProperties, and its ancestors' in
  the game's other modules. An asset keeps only the values that differ from its class's defaults, so a changed
  default changes what it holds. Comments and other function bodies are not part of it, so editing them leaves it
  unchanged. Defaults read from config files, or set by a helper the constructor calls or a constant defined in
  another file, are not part of it: a step that depends on them declares the module's code.

`steps()` makes a cutoff step per digest: it reruns after every compile, and its dependents rerun only when the
digest changes. A script that uses game modules lists them in `UnrealScript(modules=...)` and needs their steps;
unreal_script_guard stops it if it uses any other game module, or calls functions of a module it only declares by
interface.
"""
import hashlib, json, os, re
from pathlib import Path

from . import engine, paths
from .build import Call, Step, module_step

PLATFORM, TARGET, CONFIGURATION = 'Mac', 'UnrealEditor', 'Development'
GENERATED = ('.generated.h', '.gen.cpp')
DEPENDENCY = re.compile(r'(?:\\.|[^\s\\])+')   # a path in a .d file, its spaces escaped
# Generated identifiers embed the header's absolute path and line numbers, and reload checksums hash them: neither is
# part of a declaration.
VOLATILE = [(re.compile(r'FID_\w+'), 'FID'), (re.compile(r'(CONSTRUCT_RELOAD_VERSION_INFO\([^\n]*?), \d+U\)'), r'\1)')]


def project_modules(project):
    """The game and plugin modules the editor target built: {module: library file name}."""
    manifest = Path(project) / 'Binaries' / PLATFORM / f'{TARGET}.modules'
    return json.loads(manifest.read_text())['Modules'] if manifest.exists() else {}


def object_dir(project, module):
    """Where the compile put the module's objects: the game's own modules, or plugins from outside the project; the
    most recent architecture's, when an older build left another."""
    for folder in ('Build', 'External/Build'):
        found = list((Path(project) / 'Intermediate' / folder / PLATFORM).glob(f'*/{TARGET}/{CONFIGURATION}/{module}'))
        if found:
            return max(found, key=lambda path: path.stat().st_mtime)
    raise SystemExit(f'{module}: no compiled objects in {project}/Intermediate; compile the editor first')


def dependencies(folder, compiled_in):
    """Every file the compiler read for the module's objects, from their .d files (Makefile syntax: a space in a path
    is escaped, as in the installed engine's 'Epic\\ Games'). Relative paths are from the compiler's working
    directory, `compiled_in`. A .d file whose source is gone is left from an earlier build and is skipped."""
    files = set()
    for depfile in sorted(folder.glob('*.d')):
        listed = []
        for line in depfile.read_text(errors='ignore').replace('\\\n', ' ').splitlines():
            _, _, rest = line.partition(': ')
            listed += [re.sub(r'\\(.)', r'\1', p) if '\\' in p else p for p in DEPENDENCY.findall(rest)]
        source = next((p for p in listed if p.rpartition('/')[2] == depfile.stem), None)   # Tool.cpp.d lists Tool.cpp
        if source is None or os.path.exists(os.path.join(compiled_in, source)):
            files.update(listed)
    return {Path(compiled_in, p) for p in files}


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


# Comments, and string literals so that a '//' inside one is not taken for a comment.
COMMENT = re.compile(r'"(?:\\.|[^"\\\n])*"|//[^\n]*|/\*.*?\*/', re.S)
DECLARED = re.compile(r'\*{5,} Begin (?:Class|ScriptStruct) (\w+) ')


def _text_hash(text):
    return hashlib.sha256(text.encode()).hexdigest()


def function(text, start):
    """The function whose signature starts at `start`, to the end of its body: braces of member initializers (preceded
    by a name) are skipped. The rest of the text when the braces do not match."""
    depth, body = 0, False
    for index in range(start, len(text)):
        char = text[index]
        if char == '{':
            if depth == 0 and not body:
                body = not re.search(r'\w\s*$', text[start:index])
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0 and body:
                return text[start:index + 1]
    return text[start:]


def uht_manifest(project):
    """The editor target's UnrealHeaderTool manifest: each module's reflected headers and generated code folder."""
    found = [(json.loads(path.read_text()), path.stat().st_mtime)
             for path in (Path(project) / 'Intermediate' / 'Build' / PLATFORM).glob('*/*.uhtmanifest')]
    editors = [(manifest, time) for manifest, time in found   # the editor target generates into .../UnrealEditor/Inc
               if any(f'/{PLATFORM}/{TARGET}/Inc/' in m['OutputDirectory'] for m in manifest['Modules'])]
    if not editors:
        raise SystemExit(f'no editor UnrealHeaderTool manifest in {project}/Intermediate; compile the editor first')
    return max(editors, key=lambda pair: pair[1])[0]


class Types:
    """The reflected classes and structs of the game's own modules, with the sources that set their defaults."""
    HEADERS = ('ClassesHeaders', 'PublicHeaders', 'InternalHeaders', 'PrivateHeaders')

    def __init__(self, project, repo):
        self.repo = Path(repo).resolve()
        self.modules = {m['Name']: m for m in uht_manifest(project)['Modules']
                        if Path(m['BaseDirectory']).resolve().is_relative_to(self.repo)}
        self.owner, self.texts, self.cpp = {}, {}, {}
        for module in self.modules:
            for header, generated in self.generated(module, '.generated.h'):
                if generated.is_file():
                    for declared in DECLARED.findall(generated.read_text(errors='ignore')):
                        self.owner.setdefault(declared, (module, header))

    def generated(self, module, suffix):
        """(header, the file UnrealHeaderTool generated from it) for each of the module's reflected headers."""
        manifest = self.modules[module]
        output = Path(manifest['OutputDirectory'])
        return [(Path(header), output / (Path(header).stem + suffix)) for key in self.HEADERS for header in manifest[key]]

    def sources(self, module):
        if module not in self.cpp:
            self.cpp[module] = sorted(Path(self.modules[module]['BaseDirectory']).rglob('*.cpp'))
        return self.cpp[module]

    def text(self, path):
        if path not in self.texts:
            text = COMMENT.sub(lambda m: m.group(0) if m.group(0)[0] == '"' else ' ',
                               path.read_text(errors='ignore')) if path.is_file() else 'missing'
            self.texts[path] = re.sub(r'\s+', ' ', text).strip()   # comments and layout do not change a default
        return self.texts[path]

    def defaults(self, name):
        """{key: sha256} of the sources that set the type's defaults, and its ancestors' in the game."""
        found, seen = {}, set()
        while name in self.owner and name not in seen:
            seen.add(name)
            module, header = self.owner[name]
            text = self.text(header)
            found[header.resolve().relative_to(self.repo).as_posix()] = _text_hash(text)
            for source in self.sources(module):
                code = self.text(source)
                for match in re.finditer(rf'\b{name}::(?:{name}|PostInitProperties)\s*\(', code):
                    found[match.group(0).rstrip('( ')] = _text_hash(function(code, match.start()))
            parent = re.search(rf'(?:class|struct)\s+(?:\w+_API\s+)?{name}\b[^;{{]*?:\s*(?:public\s+)?(\w+)', text)
            name = parent.group(1) if parent else None
        return found


def interface(project, module, repo=None):
    """{name: sha256} of the module's normalized reflection code and of its types' defaults."""
    types = Types(project, repo or paths.REPO)
    if module not in types.modules:
        raise SystemExit(f'{module}: UnrealHeaderTool did not process it; does it declare any UCLASS, USTRUCT or UENUM?')
    files = {}
    for suffix in GENERATED:
        for _, path in types.generated(module, suffix):
            if path.is_file():
                text = path.read_text(errors='ignore')
                for pattern, replacement in VOLATILE:
                    text = pattern.sub(replacement, text)
                files[path.name] = _text_hash(text)
    for name in sorted(t for t, (owner, _) in types.owner.items() if owner == module):
        files.update(types.defaults(name))
    return dict(sorted(files.items()))


def record(project, module, kind, output, unreal_root=None):
    files = code(project, module, unreal_root=unreal_root) if kind == 'code' else interface(project, module)
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
