"""Call one original keyed native factory inside the existing recorded Unreal body."""
import inspect
import math
from pathlib import Path, PurePosixPath
import runpy
import sys


def _module_path(job_dir, relative):
    if (not isinstance(relative, str) or not relative.endswith('.py') or '\\' in relative or '\x00' in relative
            or PurePosixPath(relative).is_absolute()
            or any(part in ('', '.', '..') for part in relative.split('/'))):
        raise ValueError('native author requires one project-relative Python source')
    root = Path(job_dir).resolve()
    source = root / relative
    if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(root):
        raise ValueError('native author source is not a regular staged job file')
    return source


def _package(value):
    return (isinstance(value, str) and value.startswith('/Game/')
            and not value.startswith('/Game/AtelierRaw/') and value != '/Game/AtelierRaw'
            and not any(c in value for c in '.\\:\x00')
            and all(part not in ('', '.', '..') for part in value[1:].split('/')))


def run(context):
    """@cc [owner:fontanierh,label:correctness] keyed-original-native-factory-call
    The body MUST execute only the explicitly keyed staged source module under a
    non-main name, then its named original function with JSON values and exact
    declared singleton native inputs. It MUST NOT invoke main, invent native
    objects, infer package paths or override ambient output roots. Original module
    imports and settings remain inside C3's recorded body and complete keyed code
    closure. Every input, including transitive native dependencies, MUST be staged
    by the declaration. The returned asset MUST match the sole declared output,
    and its final native save MUST succeed before completion. C3 retains authority
    for extra saves, imported dependencies, dirty packages and reset verification.
    """
    import unreal
    if set(context.params) != {'args', 'settings'}:
        raise ValueError('native author parameters require args and separate settings')
    args = context.params['args']
    if set(args) != {'module', 'function', 'arguments', 'keyword_arguments', 'expected_package'}:
        raise ValueError('unsupported native author arguments')
    expected = args['expected_package']
    if not _package(expected) or list(context.outputs) != [expected]:
        raise ValueError('native author must own exactly its expected finished package')
    name = args['function']
    if (not isinstance(name, str) or not name or any(not part.isidentifier() or part in ('main', '__main__')
            or part.startswith('__') for part in name.split('.'))):
        raise ValueError('native author entry must name an original non-main function')
    if (not isinstance(args['arguments'], (list, tuple)) or not isinstance(args['keyword_arguments'], dict)
            or any(not isinstance(key, str) or not key.isidentifier() for key in args['keyword_arguments'])):
        raise ValueError('native author call arguments must be JSON positional/keyword values')
    if set(context.inputs) != set(context.packages):
        raise ValueError('native author input membership differs from staged packages')
    packages = {}
    for slot, value in context.packages.items():
        values = [value] if isinstance(value, str) else value
        if not isinstance(values, (list, tuple)) or len(values) > 1:
            raise ValueError('native author input must be data or one native package')
        if values:
            if not _package(values[0]) or values[0] == expected:
                raise ValueError('native author input must be an independent finished package')
            packages[slot] = values[0]
    loaded = {}
    def resolve(value):
        if isinstance(value, dict):
            if 'native_input' in value:
                if set(value) != {'native_input'} or not isinstance(value['native_input'], str):
                    raise ValueError('native input reference must name exactly one slot')
                slot = value['native_input']
                if slot not in packages:
                    raise ValueError('native input reference is absent, data or not singleton')
                if slot not in loaded:
                    loaded[slot] = unreal.EditorAssetLibrary.load_asset(packages[slot])
                    if loaded[slot] is None:
                        raise ValueError('declared native input failed to load: ' + packages[slot])
                return loaded[slot]
            if any(not isinstance(key, str) for key in value):
                raise ValueError('native author JSON object keys must be strings')
            return {key: resolve(member) for key, member in value.items()}
        if isinstance(value, (list, tuple)):
            return [resolve(member) for member in value]
        if value is None or type(value) in (str, bool, int):
            return value
        if type(value) is float and math.isfinite(value):
            return value
        raise ValueError('native author arguments must contain only finite JSON data/native references')
    source = _module_path(context.job_dir, args['module'])
    positional = resolve(args['arguments'])
    keyword = resolve(args['keyword_arguments'])
    before = list(sys.path)
    try:
        sys.path[:0] = [str(source.parent), str(Path(context.job_dir))]
        namespace = runpy.run_path(str(source), run_name='atelier_native_author_source')
        parts = name.split('.')
        function = namespace.get(parts[0])
        for part in parts[1:]:
            function = getattr(function, part, None)
        actual = function.__func__ if inspect.ismethod(function) else function
        if (not inspect.isfunction(actual) or Path(actual.__code__.co_filename).resolve() != source.resolve()
                or actual.__name__ in ('main', '__main__')):
            raise ValueError('native author entry is not a function from its declared source')
        asset = function(*positional, **keyword)
        if asset is None or asset.get_path_name().split('.', 1)[0] != expected:
            raise ValueError('native author returned another package or no asset')
        if not unreal.EditorAssetLibrary.save_loaded_asset(asset, False):
            raise RuntimeError('native author final save failed: ' + expected)
    finally:
        sys.path[:] = before
