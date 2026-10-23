"""Coastal geometry/export keys exclude sibling construction and exported query prerequisites."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

from atelier.build import check_modules

GAME = Path(__file__).resolve().parents[1]
REGION = GAME / 'world/regions/brinecove'


def test_coastal_component_planners_are_separate_and_ground_requires_complete_paving(tmp_path):
    spec = importlib.util.spec_from_file_location('brinecove_atomic_recipe', GAME / 'brinecove_atomic_build.py')
    recipe = importlib.util.module_from_spec(spec); spec.loader.exec_module(recipe)
    steps = recipe.steps(SimpleNamespace(out=tmp_path.resolve()))
    check_modules(steps)
    planners = {s.name.rsplit('.', 1)[-1]: s for s in steps if '.geometry.' in s.name}
    assert len(planners) == 13
    for key, step in planners.items():
        query = tmp_path.resolve() / 'brinecove/query-data' / (key + '.npz')
        assert next(p for p in step.products if p.name == 'brinecove.query.' + key).paths == (query,)
        assert '--query-output' in step.commands[0].args or '--surface-output' in step.commands[0].args
    for key, function in recipe.COMPONENTS:
        step = planners['SM_BC_' + key]
        assert step.cache and step.commands[0].factory_startup and step.commands[0].threads == 3
        assert step.reads == ['brinecove.rim_data'] and not step.needs
        assert REGION / 'procedural' / (function + '.py') in step.inputs
        assert REGION / 'build.py' not in step.inputs and REGION / 'modules.py' not in step.inputs
        assert REGION / 'ground.py' not in step.inputs
        assert all(p.suffix not in ('.fbx', '.glb') or p.is_relative_to(GAME / 'assets') for p in step.inputs)
        assert step.products[-1].name == 'brinecove.paving.' + key
        for other, other_function in recipe.COMPONENTS:
            if other != key:
                assert REGION / 'procedural' / (other_function + '.py') not in step.inputs
                assert GAME / 'assets/brinecove/export-parameters' / (other + '.json') not in step.inputs
    ground = planners['SM_BC_Ground']
    assert set(ground.reads) == {'brinecove.rim_data', *('brinecove.paving.' + k for k, _ in recipe.COMPONENTS)}
    assert ground.products[-1].name == 'terrain.Brinecove.final'
    assert all(REGION / 'procedural' / (function + '.py') not in ground.inputs for _, function in recipe.COMPONENTS)
    for slug in recipe.HEROES:
        key = 'SM_BC_Hero_' + ''.join(part.title() for part in slug.split('-'))
        step = planners[key]
        assert not step.reads and not step.needs
        assert GAME / 'assets/brinecove/models' / (slug + '.glb') in step.inputs
        assert REGION / 'hero_assets.py' not in step.inputs
        assert REGION / 'hero_placements.py' not in step.inputs
        assert REGION / 'layout.py' not in step.inputs
        assert REGION / 'kit.py' not in step.inputs
        assert step.products[-1].name == 'brinecove.hero_materials.' + slug
    assembly = recipe.assembly_step(tmp_path.resolve(), plant_products=['plant.fixture'])
    assert assembly.cache and not assembly.heavy
    assert 'plant.fixture' in assembly.reads and 'brinecove.atomic' in assembly.reads
    assert assembly.commands[0].script == REGION / 'assemble.py'
    assert REGION / 'build.py' not in assembly.inputs
