"""Publish only declarations reachable from one original railway constructor."""
import argparse
import ast
import json
from pathlib import Path

MODULES = {name: Path(__file__).with_name(name.rsplit('.', 1)[1] + '.py')
           for name in ('train.track', 'train.station', 'train.station_site', 'train.overbridge')}


def project(request):
    """@cc [owner:fontanierh,label:performance] selected-track-source-declarations
    Selected source MUST execute projected original constructor declarations. Discovery,
    layout and export-driver changes MUST NOT enter a selected key unless their consumed
    declaration or explicit argument bytes change. External query imports remain declared.
    """
    parsed = {}
    selected = {name: set() for name in MODULES}
    external = set()
    for module, path in MODULES.items():
        text = path.read_text(); declarations = {}; imports = {}
        for node in ast.parse(text).body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                declarations[node.name] = node
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    for part in ast.walk(target):
                        if isinstance(part, ast.Name): declarations[part.id] = node
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    key = alias.asname or alias.name.split('.')[0]
                    full = alias.name if isinstance(node, ast.Import) else f'{node.module}.{alias.name}'
                    imports[key] = (full, node)
        parsed[module] = text, declarations, imports

    def include(module, key):
        if key in selected[module]: return
        text, declarations, imports = parsed[module]
        if key in imports:
            full, _ = imports[key]
            if full not in MODULES: external.add(full)
            selected[module].add(key)
            return
        if key not in declarations: return  # a local variable or Python builtin
        selected[module].add(key)
        node = declarations[key]
        for part in ast.walk(node):
            if isinstance(part, ast.Name) and isinstance(part.ctx, ast.Load): include(module, part.id)
            if isinstance(part, ast.Attribute) and isinstance(part.value, ast.Name):
                alias = imports.get(part.value.id)
                if alias and alias[0] in MODULES: include(alias[0], part.attr)
            # Function-local imports execute unchanged and are real query dependencies.
            if isinstance(part, ast.ImportFrom):
                for alias in part.names: external.add(f'{part.module}.{alias.name}')
            elif isinstance(part, ast.Import):
                external.update(alias.name for alias in part.names)

    def arguments(value):
        if not isinstance(value, dict): return
        if value.get('kind') == 'request':
            include(value['module'], value['function'])
            for arg in value['arguments']: arguments(arg)
        elif value.get('kind') == 'site': include('train.station_site', 'Site')
        elif value.get('kind') == 'line': include('train.track', 'Line')
        elif value.get('kind') in ('tuple', 'list'):
            for arg in value['values']: arguments(arg)
    arguments(request)
    result = {}
    for module, keys in selected.items():
        if not keys: continue
        text, declarations, imports = parsed[module]
        nodes = {id(declarations[key]): declarations[key] for key in keys if key in declarations}
        bindings = {key: imports[key][0] for key in sorted(keys) if key in imports}
        snippets = []
        for node in sorted(nodes.values(), key=lambda n: n.lineno):
            start = min([node.lineno, *(d.lineno for d in getattr(node, 'decorator_list', ()))])
            snippets.append('\n'.join(text.splitlines()[start - 1:node.end_lineno]))
        result[module] = dict(bindings=bindings, declarations=snippets)
    return result, sorted(external)


def descriptor(asset, level, value):
    from atelier.export_manifest import name
    name(asset)
    if (value.get('schema') != 1 or asset not in value['meshes'] or type(level) is not int
            or not 0 <= level < value['meshes'][asset]['levels']):
        raise ValueError('Unknown railway request projection')
    request = value['meshes'][asset]['requests'][level]
    code, support = project(request)
    factory = Path(__file__).with_name('track_build.py').read_text()
    functions = {node.name: node for node in ast.parse(factory).body if isinstance(node, ast.FunctionDef)}
    track = MODULES['train.track'].read_text()
    palette = next(ast.literal_eval(node.value) for node in ast.parse(track).body
                   if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'MATERIALS'
                                                         for target in node.targets))
    material_names = json.dumps([code, request])
    return dict(schema=1, asset=f'{asset}_LOD{level}', logical=asset, level=level, request=request,
                code=code, support=support, palette={key: color for key, color in palette.items() if key in material_names},
                factory={out: ast.get_source_segment(factory, functions[source]) for out, source in
                         [('to_object', 'to_object'), ('material_factory', 'materials'), ('export_glb', 'export_glb')]})


def main():
    from atelier.atomic_files import atomic_json
    from atelier.export_manifest import real_directory
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset', required=True); parser.add_argument('--level', type=int, required=True)
    parser.add_argument('--inventory', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); real_directory(args.inventory.parent)
    if args.inventory.is_symlink() or not args.inventory.is_file(): raise ValueError('Linked railway inventory')
    atomic_json(args.output, descriptor(args.asset, args.level, json.loads(args.inventory.read_text())))
    print('RAILWAY REQUEST PROJECTION COMPLETE', args.asset, args.level, flush=True)


if __name__ == '__main__': main()
