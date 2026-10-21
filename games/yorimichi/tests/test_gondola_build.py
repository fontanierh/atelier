"""Production preparation keeps diagnostic overrides out of shipped kit data."""
from types import SimpleNamespace

from atelier import build
from atelier.build_inputs import validate_imports
from atelier.build_source import environment


def test_normal_kit_preparation_cannot_inherit_partial_or_soft_failure_modes(monkeypatch, tmp_path):
    monkeypatch.setenv('GONDOLA_PIECES','cabin')
    monkeypatch.setenv('GONDOLA_SOFT_FAIL','1')
    monkeypatch.setenv('GONDOLA_PARAMS','diagnostic-parameters.json')
    recipe = build.load_recipe('yorimichi')
    step, = recipe.gondola_steps(SimpleNamespace(out=tmp_path))
    command, = step.commands
    env = environment(command.env)
    assert set(env['GONDOLA_PIECES'].split(',')) == {'cabin','towers','valley','rim','crater'}
    assert not env['GONDOLA_SOFT_FAIL'] and not env['GONDOLA_PARAMS']
    assert step.heavy and command.threads == 3 and command.factory_startup
    products = {p.name:p for p in step.products}
    assert 'gondola.kit' in products and step.cache
    validate_imports(step, step.inputs)
