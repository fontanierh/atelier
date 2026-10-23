"""Publish exact selected ferry constructor programs before Blender or exports run.

The legacy constructor is the authority. Projection retains its original source bytes,
declaration order and complete transitive global closure, without sibling constructors.
"""
import argparse
import ast
import json
from pathlib import Path

from atelier.atomic_files import atomic_json
from atelier.export_manifest import real_directory

BUILD = Path(__file__).resolve().parents[3] / 'assets/vehicles/ferry/build.py'
BUILDERS = dict(FY_Hull='hull', FY_Superstructure='superstructure', FY_Funnel='funnel',
                FY_Lifeboats='lifeboats', FY_Rails='rails', FY_Masts='masts',
                FY_Fittings='fittings', FY_BoardingGate='boarding_gate')


def assigned(node):
    if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
        return {node.name}
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        return {n.id for target in targets for n in ast.walk(target) if isinstance(n, ast.Name)}
    return set()


def program(text, roots):
    """@cc [owner:fontanierh,label:correctness;performance] ferry-constructor-source-closure
    A selected program MUST retain exact original declaration bytes, transitive global
    references and declaration order. Sibling constructors MUST NOT enter its payload
    unless actually referenced. Missing requested declarations and ambiguous rebinding
    MUST refuse before publication. This projection does not claim native equivalence.
    """
    tree = ast.parse(text)
    definitions = {}
    for index, node in enumerate(tree.body):
        for key in assigned(node):
            if key in definitions:
                raise ValueError('Ambiguous ferry source declaration: ' + key)
            definitions[key] = index
    if set(roots) - definitions.keys():
        raise ValueError('Missing selected ferry source declaration')
    selected, pending = set(), list(roots)
    while pending:
        key = pending.pop()
        if key not in definitions or definitions[key] in selected:
            continue
        index = definitions[key]; selected.add(index)
        pending.extend(n.id for n in ast.walk(tree.body[index])
                       if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load))
    selected.update(index for index, node in enumerate(tree.body)
                    if isinstance(node, (ast.Import, ast.ImportFrom)))
    lines = text.splitlines(keepends=True)
    return '\n'.join(''.join(lines[tree.body[index].lineno - 1:tree.body[index].end_lineno])
                     for index in sorted(selected))


def project(text):
    values = {key: dict(schema=1, asset=key, constructor=builder,
                       program=program(text, (builder, 'Mesh', 'check', 'make_materials', 'to_object')))
              for key, builder in BUILDERS.items()}
    values['FY_Collision'] = dict(schema=1, asset='FY_Collision', constructor='collision_proxies',
        program=program(text, ('export_collision',)))
    values['audit'] = dict(schema=1, asset='audit', program=program(text, (
        'Mesh', 'seating_check', 'walk_layout', 'collision_proxies', 'landing_plate', 'RAIL_H')))
    values['FY_Hull']['materials'] = palette(text)
    return values


def palette(text):
    """Read the authored literal palette without importing Blender or running source."""
    constants = {}
    class Names(ast.NodeTransformer):
        def visit_Name(self, node):
            return ast.copy_location(ast.Constant(constants[node.id]), node)
    for node in ast.parse(text).body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, (ast.Tuple, ast.List)) and isinstance(node.value, (ast.Tuple, ast.List)):
            for key, value in zip(target.elts, node.value.elts):
                if isinstance(key, ast.Name) and isinstance(value, ast.Constant):
                    constants[key.id] = value.value
        if isinstance(target, ast.Name) and target.id == 'MATERIALS':
            return ast.literal_eval(Names().visit(node.value))
    raise ValueError('Missing original ferry material palette')


def publish(output, text=None):
    output = real_directory(output, create=True)
    values = project(BUILD.read_text() if text is None else text)
    expected = {key + '.json' for key in values}
    for path in output.iterdir():
        if path.name not in expected or path.is_symlink() or not path.is_file():
            raise ValueError('Foreign ferry constructor source member')
    for key, value in values.items():
        atomic_json(output / (key + '.json'), value)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    publish(args.output)


if __name__ == '__main__': main()
