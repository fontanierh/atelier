"""Static admission checks for the shared production mesh exporter."""
import ast
from functools import lru_cache
from pathlib import Path

from . import paths
from .source_imports import ImportScanner


@lru_cache(maxsize=2048)
def raw_fbx_lines(text):
    # Inspect references as well as calls, so assigning an operator alias cannot
    # accidentally escape the common boundary. Strings/comments are not code.
    if not any(name in text for name in ('export_scene', 'getattr', 'io_scene_fbx')):
        return ()
    tree = ast.parse(text)
    nodes = list(ast.walk(tree))
    namespaces = {alias.asname or alias.name for node in nodes
                  if isinstance(node, ast.ImportFrom) and node.module == 'bpy.ops'
                  for alias in node.names if alias.name == 'export_scene'}
    def namespace(node):
        return (isinstance(node, ast.Attribute) and node.attr == 'export_scene'
                or isinstance(node, ast.Name) and node.id in namespaces)
    # Follow ordinary local aliases to a fixed point, including nested functions.
    while True:
        aliases = {target.id for node in nodes if isinstance(node, ast.Assign) and namespace(node.value)
                   for target in node.targets if isinstance(target, ast.Name)}
        if aliases <= namespaces:
            break
        namespaces.update(aliases)
    return tuple(sorted({node.lineno for node in ast.walk(tree)
                 if (isinstance(node, ast.Attribute) and node.attr == 'fbx' and namespace(node.value))
                 or (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                     and node.func.id == 'getattr' and len(node.args) >= 2 and namespace(node.args[0])
                     and isinstance(node.args[1], ast.Constant) and node.args[1].value == 'fbx')
                 or (isinstance(node, ast.ImportFrom) and ((node.module or '').split('.')[0] == 'io_scene_fbx'
                     or node.module == 'bpy.ops.export_scene' and any(a.name == 'fbx' for a in node.names)))
                 or (isinstance(node, ast.Import) and any(alias.name.split('.')[0] == 'io_scene_fbx' for alias in node.names))}))



def violations(source, text):
    helper = paths.STUDIO / 'atelier' / 'blender' / 'fbx.py'
    if Path(source).resolve() == helper.resolve():
        return []
    return [f'{source}:{line}: raw FBX export; use atelier.blender.fbx.export_fbx'
            for line in raw_fbx_lines(text)]


def check_steps(steps, blender_type):
    """@cc [owner:fontanierh,label:correctness] enforced-mesh-export-boundary
    Blender action admission MUST reject raw FBX operators in its local imported
    source closure. Actions using the common exporter MUST declare its bytes as
    inputs. This preflight MUST NOT rewrite fingerprints, inputs or saved outputs.
    """
    scanner = ImportScanner()
    checked = set()
    helper = (paths.STUDIO / 'atelier' / 'blender' / 'fbx.py').resolve()
    for step in steps:
        for command in step.commands:
            if not isinstance(command, blender_type) or not Path(command.script).is_file():
                continue
            closure = scanner.local_imports(command.script)
            for source in closure:
                if source not in checked:
                    problems = violations(source, source.read_text())
                    if problems:
                        raise ValueError('\n'.join(problems))
                    checked.add(source)
            if helper in closure and not any(helper == Path(p).resolve()
                    or Path(p).is_dir() and helper.is_relative_to(Path(p).resolve()) for p in step.inputs):
                raise ValueError(f'{step.name}: shared FBX exporter must be a declared input')
