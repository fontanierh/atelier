"""Selected house constructors retain their exact authored bodies and source isolation."""
import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace

from atelier.build_inputs import local_imports

GAME = Path(__file__).resolve().parents[1]
REGION = GAME / 'world/regions/houses'


def definitions(path):
    return {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(path.read_text()).body
            if isinstance(n, (ast.FunctionDef, ast.ClassDef))}


def test_selected_house_definitions_preserve_all_original_geometry_statements():
    original = definitions(REGION / 'build.py')
    found = {}
    for name in ('geometry_mesh', 'construction', 'house_a', 'house_b', 'house_c', 'lots'):
        for key, value in definitions(REGION / (name + '.py')).items():
            assert key not in found
            assert original[key] == value, key
            found[key] = value
    assert len(found) == 34
    assert {'Mesh', 'Ground', 'lot_mesh', 'house_a', 'house_b', 'house_c', 'house_shade'} <= found.keys()


def test_each_house_constructor_excludes_its_siblings_and_export_orchestration():
    for name in ('house_a', 'house_b', 'house_c'):
        sources = set(local_imports(REGION / (name + '.py'), (GAME / 'world', GAME / 'world/regions')))
        assert REGION / 'build.py' not in sources
        assert REGION / 'lots.py' not in sources
        for other in {'house_a', 'house_b', 'house_c'} - {name}:
            assert REGION / (other + '.py') not in sources


def test_production_models_and_lots_have_independent_source_and_data_owners(tmp_path):
    spec = importlib.util.spec_from_file_location('houses_atomic_recipe', GAME / 'houses_build.py')
    recipe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(recipe)
    steps = {step.name: step for step in recipe.steps(SimpleNamespace(out=tmp_path.resolve()))}
    for key, builder in [('House_A', 'house_a'), ('House_B', 'house_b'), ('House_C', 'house_c')]:
        step = steps['world.houses.geometry.' + key]
        assert not step.reads and not step.needs
        assert REGION / (builder + '.py') in step.inputs
        assert REGION / 'lot_data.py' not in step.inputs
        assert tmp_path / 'heightmap.npy' not in step.inputs
        for other in {'house_a', 'house_b', 'house_c'} - {builder}:
            assert REGION / (other + '.py') not in step.inputs
    for index in range(1, 6):
        key = f'HouseLot_{index}'
        step = steps['world.houses.geometry.' + key]
        assert step.reads == ['houses.data.' + key]
        assert steps['world.houses.data.' + key].needs == ['world.layout']
        assert REGION / 'lot_data.py' in step.inputs
        assert REGION / 'house_a.py' not in step.inputs
