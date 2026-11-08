"""Publish selected terminal programs, exact scalar plans and consumed ground queries."""
import argparse
import ast
import copy
import importlib.util
import json
import math
from pathlib import Path
import sys
from collections import Counter
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json
from atelier.export_manifest import real_directory
import region_query
from regions.ferry.ship_sources import BUILD, assigned, program

GAME = Path(__file__).resolve().parents[3]
KIT = GAME / 'assets/vehicles/ferry/terminals'
OWNERS = ('hidamari', 'brinecove')
PRIMITIVES = ('col', 'col_box', 'col_seg', 'collision_objects', 'export_collision', 'COL', 'BROW_COL')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def closure(text, roots):
    """Keep exact transitive terminal declarations; the caller supplies F/FS/SILL explicitly."""
    tree = ast.parse(text); definitions = {}
    for index, node in enumerate(tree.body):
        keys = assigned(node)
        if isinstance(node, ast.Import): keys = {row.asname or row.name.split('.')[0] for row in node.names}
        if isinstance(node, ast.ImportFrom): keys = {row.asname or row.name for row in node.names}
        for key in keys: definitions.setdefault(key, []).append(index)
    selected = set(); pending = list(roots)
    while pending:
        key = pending.pop()
        if key in ('F', 'FS', 'SILL', 'GATE_W', 'SITE', 'OUT', 'HERE', '__file__') or key not in definitions: continue
        indices = definitions[key]
        if len(indices) != 1: raise ValueError('Ambiguous selected terminal declaration: ' + key)
        index, = indices
        if index in selected: continue
        selected.add(index)
        pending.extend(node.id for node in ast.walk(tree.body[index]) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load))
    if any(key not in definitions for key in roots): raise ValueError('Missing selected terminal primitive')
    lines = text.splitlines(keepends=True)
    return '\n'.join(''.join(lines[tree.body[index].lineno-1:tree.body[index].end_lineno]) for index in sorted(selected))


def queries_only(function):
    """@cc [owner:fontanierh,label:correctness] complete-terminal-query-expression-projection
    Every original ground-query expression MUST survive exactly once with its ordered
    loops/conditions and arithmetic. Unsupported query placement MUST refuse before
    source publication. No mesh constructor or rendered sibling export may supply it.
    """
    def statements(nodes):
        result = []
        for node in nodes:
            if isinstance(node, ast.Assign):
                if any(isinstance(part, ast.Call) and ast.unparse(part.func) == 'kit.F.Mesh' for part in ast.walk(node)): continue
                result.append(copy.deepcopy(node))
            elif isinstance(node, ast.Expr):
                result.extend(ast.Expr(value=copy.deepcopy(part)) for part in ast.walk(node)
                    if isinstance(part, ast.Call) and ast.unparse(part.func) == 'kit.ground_under')
            elif isinstance(node, (ast.For, ast.If)):
                body = statements(node.body); other = statements(node.orelse)
                if body or other:
                    new = copy.deepcopy(node); new.body = body or [ast.Pass()]; new.orelse = other; result.append(new)
        return result
    selected = copy.deepcopy(function); selected.body = statements(function.body)
    def calls(node):
        return Counter(ast.dump(part) for part in ast.walk(node) if isinstance(part, ast.Call)
            and ast.unparse(part.func) == 'kit.ground_under')
    if calls(selected) != calls(function): raise ValueError('Unsupported or incomplete terminal ground query projection')
    return ast.fix_missing_locations(ast.Module(body=[selected], type_ignores=[]))


def berth_fields(function):
    return {node.slice.value for node in ast.walk(function) if isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name) and node.value.id == 'b' and isinstance(node.slice, ast.Constant)}


def projections(site, worlds):
    text = (KIT / 'build.py').read_text()
    definitions = {node.name: node for node in ast.parse(text).body if isinstance(node, ast.FunctionDef)}
    pure = {}
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign) and assigned(node) & {'TREAD', 'DOOR_RISER'}:
            exec(compile(ast.Module(body=[node], type_ignores=[]), str(KIT / 'build.py'), 'exec'), pure)
    exec(compile(ast.Module(body=[definitions['stair_run']], type_ignores=[]), str(KIT / 'build.py'), 'exec'), pure)
    kit = SimpleNamespace(SITE=site, SILL=site['ship']['sill_z'], TREAD=pure['TREAD'], stair_run=pure['stair_run'])
    # The site reader's own plain-Python loader supplies its established bpy stubs.
    fs = load('ferry_terminal_source_queries', KIT / 'site.py')
    ground_namespace = dict(FS=fs, np=np)
    exec(compile(ast.Module(body=[definitions['ground_under']], type_ignores=[]), str(KIT / 'build.py'), 'exec'), ground_namespace)
    values = {}; primitive_roots = set(PRIMITIVES)
    ferry_text = BUILD.read_text()
    ferry_definitions = {key for node in ast.parse(ferry_text).body for key in assigned(node)}
    for owner in OWNERS:
        path = GAME / 'world/regions' / owner / 'ferry_terminal.py'
        module = load('terminal_data_' + owner, path)
        source = path.read_text(); functions = {node.name: node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)}
        data = module.construction_plan(kit)
        for key, function in module.CONSTRUCTORS.items():
            node = functions[function]
            selected_roots = {part.attr for part in ast.walk(node) if isinstance(part, ast.Attribute)
                and isinstance(part.value, ast.Name) and part.value.id == 'kit'}
            parameters = {field: data[field] for field in module.CONSTRUCTION_FIELDS[key]}
            if 'b' in parameters: parameters['b'] = {field: data['b'][field] for field in berth_fields(node)}
            ground = []
            if any(isinstance(part, ast.Call) and ast.unparse(part.func) == 'kit.ground_under' for part in ast.walk(node)):
                def query(world, *rectangle):
                    value = ground_namespace['ground_under'](world, *rectangle)
                    ground.append(dict(rectangle=list(rectangle), height=value))
                    return value
                query_kit = SimpleNamespace(FS=SimpleNamespace(load_world=lambda selected: worlds[selected]),
                    ground_under=query, DOOR_RISER=pure['DOOR_RISER'])
                namespace = dict(math=math)
                exec(compile(queries_only(node), str(path), 'exec'), namespace)
                namespace[function](query_kit, parameters)
            code = ast.get_source_segment(source, node)
            values[key] = dict(schema=1, asset=key, owner=owner, constructor=function, program=code,
                parameters=parameters, ground=ground,
                anchor=[data['gx'], data['face'], 0.] if owner == 'hidamari' else [data['face'], data['gy'], 0.],
                **({'fender': fs.FENDER} if 'kit.FS.FENDER' in code else {}),
                **({'sill': site['ship']['sill_z']} if 'kit.SILL' in code else {}))
            selected_roots.update(('COL', 'BROW_COL', 'MATERIALS'))
            if key.endswith('_Brow'): selected_roots.add('collision_objects')
            terminal_program = closure(text, sorted(selected_roots))
            ferry_roots = {'Mesh', 'check', 'make_materials', 'to_object'}
            for part in ast.walk(ast.parse(terminal_program)):
                if (isinstance(part, ast.Attribute) and isinstance(part.value, ast.Name)
                        and part.value.id == 'F' and part.attr in ferry_definitions): ferry_roots.add(part.attr)
            values[key]['primitives'] = dict(schema=1, asset='primitives',
                ferry=program(ferry_text, sorted(ferry_roots)), terminal=terminal_program)
        for key, function in (('collision', 'fixed_collision'), ('walk', 'walk_plan')):
            node = functions[function]
            values[owner + '_' + key] = dict(schema=1, asset=owner + '_' + key, owner=owner,
                program=ast.get_source_segment(source, node), parameters={field: data[field] for field in module.CONSTRUCTION_FIELDS[key]},
                sill=site['ship']['sill_z'])
    values['primitives'] = dict(schema=1, asset='primitives',
        ferry='',
        terminal=closure(text, sorted(primitive_roots)))
    return values


def final_world(world, harbor):
    """Replace the declared raw Harbor owner with its complete final query surface."""
    meta = world['meta'] if isinstance(world['meta'], dict) else json.loads(str(world['meta']))
    labels = meta['labels']
    if labels.count('HD_Harbor') != 1 or world['solid_label'].shape != (len(world['solid']),):
        raise ValueError('Ferry world query has no unique Harbor owner')
    result = dict(world)
    # Preserve the original probe's float32 storage followed by load_world's
    # astype(float) query evaluation; a direct high-precision query is different.
    final = np.asarray(region_query.triangles(harbor), dtype=np.float32).astype(world['solid'].dtype)
    index = labels.index('HD_Harbor'); keep = world['solid_label'] != index
    result['solid'] = np.concatenate([world['solid'][keep], final])
    result['solid_label'] = np.concatenate([world['solid_label'][keep], np.full(len(final), index, dtype=world['solid_label'].dtype)])
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', type=Path, required=True)
    parser.add_argument('--world-hidamari', type=Path, required=True)
    parser.add_argument('--world-brinecove', type=Path, required=True)
    parser.add_argument('--harbor-query', type=Path, required=True)
    parser.add_argument('--proof', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    from atelier.export_manifest import sha
    for path in (args.site, args.world_hidamari, args.world_brinecove, args.harbor_query):
        real_directory(path.parent)
        if path.is_symlink() or not path.is_file(): raise ValueError('Terminal query sources must be regular files')
    site = json.loads(args.site.read_text())
    if site.get('pass') is not True: raise ValueError('Failed terminal source site')
    from regions.hidamari.ferry_source import validated_atomic_harbor
    validated_atomic_harbor(yori.OUT, yori.REPO)
    if (sha(args.site) != sha(yori.OUT / 'ferry/terminals/site.json')
            or sha(args.harbor_query) != sha(yori.OUT / 'hidamari/query-data/HD_Harbor.npz')
            or any(sha(getattr(args, 'world_' + owner)) != site['inputs']['world_probes'][owner] for owner in OWNERS)):
        raise ValueError('Terminal source inputs differ from complete current owner proof')
    fs = load('current_ferry_terminal_site_proof', KIT / 'site.py')
    stale = fs.stale_inputs(site)
    if stale: raise ValueError('Stale terminal source site: ' + str(stale))
    if any(getattr(args, 'world_' + owner).name != 'world_' + owner + '.npz' for owner in OWNERS):
        raise ValueError('Terminal source probe identity differs from its original named owner')
    worlds = {owner: fs.load_world(owner, out=getattr(args, 'world_' + owner).parent) for owner in OWNERS}
    original = projections(site, worlds)
    final = dict(worlds, hidamari=final_world(worlds['hidamari'], region_query.load(args.harbor_query, owner='HD_Harbor', stage='final')))
    values = projections(site, final)
    if values != original: raise ValueError('Final Harbor source changes a consumed original terminal ground query')
    root = real_directory(args.output, create=True)
    if any(path.name not in {key + '.json' for key in values} or path.is_symlink() or not path.is_file() for path in root.iterdir()):
        raise ValueError('Foreign terminal source product member')
    for key, value in values.items(): atomic_json(root / (key + '.json'), value)
    atomic_json(args.proof, dict(schema=1, complete=True, original_queries_equal_final=True,
        inputs={path.name: sha(path) for path in (args.site, args.world_hidamari, args.world_brinecove, args.harbor_query)}))


if __name__ == '__main__': main()
