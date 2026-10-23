"""Selected coastal constructors retain authored bodies and explicit shared state."""
import ast
import builtins
from pathlib import Path
import symtable

from atelier.build_inputs import local_imports

GAME = Path(__file__).resolve().parents[1]
REGIONS = GAME / 'world/regions'
REGION = REGIONS / 'brinecove'


def test_every_extracted_coastal_function_preserves_its_original_complete_ast():
    original = {n.name: ast.dump(n, include_attributes=False)
                for n in ast.parse((REGION / 'modules.py').read_text()).body
                if isinstance(n, ast.FunctionDef)}
    found = {}
    for path in (REGION / 'procedural').glob('*.py'):
        for node in ast.parse(path.read_text()).body:
            if isinstance(node, ast.FunctionDef):
                assert node.name not in found
                assert ast.dump(node, include_attributes=False) == original[node.name], node.name
                found[node.name] = path
    assert len(found) == 34 and found.keys() == original.keys()


def test_selected_coastal_constructor_globals_are_complete():
    for path in (REGION / 'procedural').glob('*.py'):
        table = symtable.symtable(path.read_text(), str(path), 'exec')
        known = set(table.get_identifiers()) | set(dir(builtins))
        pending = list(table.get_children())
        while pending:
            scope = pending.pop()
            for symbol in scope.get_symbols():
                if symbol.is_global() and symbol.is_referenced():
                    assert symbol.get_name() in known, (path.name, scope.get_name(), symbol.get_name())
            pending.extend(scope.get_children())


def test_coastal_constructors_do_not_import_sibling_generators_or_region_exporter():
    names = {'harbor', 'market', 'lower_town', 'upper_town', 'landmarks', 'ships', 'props', 'vegetation'}
    for name in names:
        path = REGION / 'procedural' / (name + '.py')
        sources = set(local_imports(path, (REGIONS, REGIONS.parent)))
        assert REGION / 'modules.py' not in sources
        assert REGION / 'build.py' not in sources
        for other in names - {name}:
            assert REGION / 'procedural' / (other + '.py') not in sources, (name, other)
