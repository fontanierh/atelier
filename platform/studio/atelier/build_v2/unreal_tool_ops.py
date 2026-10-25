"""Pure command and output adapters for Rust-owned guarded Unreal tool units.

These functions never launch, admit, certify Current, or write result records.
The caller freezes all source/parameters and retains normal actual-child guards,
capacity admission, nice 10, deadlines and positive cleanup before publication.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat


_TARGET = re.compile(r'[A-Za-z][A-Za-z0-9_]*\Z')


def _absolute(value):
    path = Path(value)
    if not path.is_absolute():
        raise ValueError('Tool execution paths must be absolute')
    return Path(os.path.normpath(path))


def _target(value):
    if not isinstance(value, str) or not _TARGET.fullmatch(value):
        raise ValueError('Invalid Unreal target name')
    return value


def compile_argv(engine_root, project, target, *, kind='editor', configuration='Development'):
    """The existing Build.sh route, explicitly capped at three compile actions."""
    engine, project = _absolute(engine_root), _absolute(project)
    _target(target)
    if kind not in ('editor', 'game') or configuration not in ('Development', 'Shipping'):
        raise ValueError('Unsupported native compile target configuration')
    if kind == 'editor' and configuration != 'Development':
        raise ValueError('Editor compilation requires Development configuration')
    if project.suffix != '.uproject':
        raise ValueError('Expected an Unreal project descriptor')
    return [str(engine / 'Engine/Build/BatchFiles/Mac/Build.sh'), target, 'Mac', configuration,
            f'-project={project}', '-WaitMutex', '-MaxParallelActions=3']


def _inside(path, roots):
    return any((path == root or path.is_relative_to(root))
               and (path.resolve() == root.resolve() or path.resolve().is_relative_to(root.resolve()))
               for root in roots)


def _receipt_path(text, *, project, engine, receipt):
    if not isinstance(text, str) or not text or '\0' in text:
        raise ValueError('Invalid UBT receipt path')
    text = text.replace('$(ProjectDir)', str(project)).replace('$(EngineDir)', str(engine))
    if '$(' in text:
        raise ValueError('Unsupported UBT receipt path variable')
    path = Path(text)
    return _absolute(path if path.is_absolute() else receipt.parent / path)


def _regular_files(path, *, allow_empty=False):
    """An exact file inventory; unsupported links fail rather than vanish from output proof."""
    metadata = path.lstat()
    if stat.S_ISREG(metadata.st_mode):
        return [path]
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError('UBT output contains a link or unsupported file')
    files = []
    for child in sorted(path.iterdir()):
        files.extend(_regular_files(child, allow_empty=allow_empty))
    if not files and not allow_empty:
        raise ValueError('UBT output directory is empty')
    return files


def compile_products(engine_root, project, target, *, owned_roots, kind='editor', configuration='Development'):
    """@cc [owner:fontanierh,label:correctness] v2-complete-ubt-product-inventory
    The adapter MUST require the actual target/platform/configuration receipt, every
    receipt-listed produced file and runtime dependency, and the editor module map
    when compiling an editor. Installed engine entries MUST be verified as present
    but MUST NOT become produced project outputs. A non-engine product outside the
    explicit owned roots, missing product, unknown variable, link or empty directory
    MUST refuse. This proves an observed output inventory only, never guard cleanup,
    source identity, portable receipt bytes, CAS success or Current.
    """
    # Reuse command validation so inventory and command cannot disagree on target roles.
    compile_argv(engine_root, project, target, kind=kind, configuration=configuration)
    project = _absolute(project).parent
    engine = _absolute(engine_root) / 'Engine'
    roots = tuple(_absolute(path) for path in owned_roots)
    if not roots:
        raise ValueError('Explicit compile output ownership is required')
    receipt = project / 'Binaries/Mac' / f'{target}.target'
    if not _inside(receipt, roots):
        raise ValueError('Compile receipt is outside the owned output roots')
    _regular_files(receipt)
    value = json.loads(receipt.read_bytes())
    if (value.get('TargetName') != target or value.get('Platform') != 'Mac'
            or value.get('Configuration') != configuration):
        raise ValueError('UBT receipt target/platform/configuration differs')
    entries = value.get('BuildProducts')
    if not isinstance(entries, list) or not entries:
        raise ValueError('UBT receipt has no complete BuildProducts inventory')
    files, products, dependencies = {receipt}, [], []
    for item in entries:
        if not isinstance(item, dict) or 'Path' not in item:
            raise ValueError('Malformed UBT BuildProducts entry')
        path = _receipt_path(item['Path'], project=project, engine=engine, receipt=receipt)
        if _inside(path, (engine,)):
            if not path.exists():
                raise ValueError('Installed engine product is missing')
            continue
        if not _inside(path, roots):
            raise ValueError('UBT product is outside the owned output roots')
        observed = _regular_files(path)
        products.append(path)
        files.update(observed)
    runtime = value.get('RuntimeDependencies', [])
    if not isinstance(runtime, list):
        raise ValueError('Malformed UBT RuntimeDependencies inventory')
    for item in runtime:
        text = item.get('Path') if isinstance(item, dict) else item
        path = _receipt_path(text, project=project, engine=engine, receipt=receipt)
        if not _inside(path, (engine, *roots)):
            raise ValueError('UBT runtime dependency is outside declared project/platform roots')
        if _inside(path, (engine,)):
            if not path.exists():
                raise ValueError('Installed engine runtime dependency is missing')
        else:
            _regular_files(path)
        dependencies.append(path)
    if kind == 'editor':
        modules = project / 'Binaries/Mac/UnrealEditor.modules'
        _regular_files(modules)
        data = json.loads(modules.read_bytes())
        if not isinstance(data.get('Modules'), dict) or not data['Modules'] or not data.get('BuildId'):
            raise ValueError('Missing editor module identities')
        files.add(modules)
        for name in data['Modules'].values():
            if not isinstance(name, str) or Path(name).name != name:
                raise ValueError('Invalid editor module binary path')
            binary = modules.parent / name
            if binary not in files:
                raise ValueError('Editor module binary is absent from BuildProducts')
    if not products:
        raise ValueError('UBT receipt contains no project products')
    return {'receipt': receipt, 'products': tuple(products), 'files': tuple(sorted(files)),
            'runtime_dependencies': tuple(dependencies)}


def verify_cooked_files(cooked_root, files):
    """Verify every cooked file; empty stock-cooker directories carry no file bytes.

    Links and special entries still refuse, and no unlisted regular file may pass.
    This observes the controller inventory and does not certify cooking.
    """
    root = _absolute(cooked_root)
    if not isinstance(files, dict) or not files:
        raise ValueError('Packaging requires a nonempty independently completed cooked inventory')
    expected = set()
    for name, digest in files.items():
        if (not isinstance(name, str) or not name or '\\' in name or name.startswith('/')
                or any(part in ('', '.', '..') for part in name.split('/'))
                or not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest)):
            raise ValueError('Invalid upstream cooked file identity')
        path = root / name
        if _regular_files(path) != [path]:
            raise ValueError('Cooked inventory members must be regular files')
        with path.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != digest:
            raise ValueError('Cooked input differs from its upstream identity')
        expected.add(path)
    if set(_regular_files(root, allow_empty=True)) != expected:
        raise ValueError('Cooked folder differs from its complete upstream inventory')
    return tuple(sorted(expected))


def package_argv(engine_root, project, target, archive, *, cooked_root, cooked_files,
                 configuration='Development'):
    """Stage/package an independently completed cooked set; never run a cook or compile."""
    engine, project, archive = map(_absolute, (engine_root, project, archive))
    _target(target)
    if configuration not in ('Development', 'Shipping') or project.suffix != '.uproject':
        raise ValueError('Unsupported package target configuration')
    cooked_root = _absolute(cooked_root)
    # The standard UAT skipcook route reads this project-local cook location. There
    # is no advertised arbitrary Zen locator injection or per-package cook hook.
    if cooked_root != project.parent / 'Saved/Cooked/Mac':
        raise ValueError('Standard UAT packaging requires the project Saved/Cooked/Mac set')
    verify_cooked_files(cooked_root, cooked_files)
    return [str(engine / 'Engine/Build/BatchFiles/RunUAT.sh'), 'BuildCookRun', f'-project={project}',
            f'-target={target}', '-platform=Mac', f'-clientconfig={configuration}', '-skipbuild', '-skipcook',
            '-ubtargs=-MaxParallelActions=3', '-stage', '-pak', '-package', '-archive',
            f'-archivedirectory={archive}', '-nocompileeditor', '-noP4', '-unattended', '-utf8output']


def package_lifecycle(folder, engine_root, environment):
    """Use existing bounded Zen sponsorship callbacks on the actual admitted UAT PID."""
    from atelier.build_zen import Lifecycle
    return Lifecycle(folder, engine_root, environment)


def cook_observer(folder, mode):
    """Existing cook observations, for an actual cook unit, never a package-only unit."""
    from atelier.build_cook import Observer
    return Observer(folder, mode)


def package_environment(engine_root, environment):
    """Match UnrealPackage's existing headless UAT toolchain repair without launching it."""
    result = dict(environment)
    if not result.get('UE_HEADLESS_USER_DIR'):
        from atelier.setup import headless_user_dir
        folder = headless_user_dir(_absolute(engine_root))
        if folder is not None:
            result['UE_HEADLESS_USER_DIR'] = str(folder)
    return result
