"""The game binary is its own cached step; the cook restores it instead of rebuilding C++."""
import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

from atelier import build as B
from atelier import checkpoint_actions, checkpoint_store, paths
from atelier.build import UnrealGame, UnrealPackage

GAME = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def recipe():
    module = B.load_recipe('yorimichi')
    ctx = B.Context('yorimichi', create=False)
    return ctx, {step.name: step for step in module.steps(ctx)}


def test_the_game_target_has_its_own_step(recipe):
    ctx, steps = recipe
    step = steps['unreal.game_binary']
    game = step.commands[0]
    assert isinstance(game, UnrealGame) and game.target == 'Yorimichi'
    assert step.heavy and step.checkpoint_restore is not None
    assert not step.explicit, 'a normal build must run it'


def test_the_step_declares_the_receipt_products(recipe):
    ctx, steps = recipe
    game = steps['unreal.game_binary'].commands[0]
    project = Path(ctx.uproject).parent
    declared = checkpoint_actions.game_outputs(ctx, game)
    binaries = project / 'Binaries/Mac'
    for expected in ('Yorimichi', 'Yorimichi.app', 'Yorimichi.target', 'libtbb.12.dylib'):
        assert binaries / expected in declared
    assert project / 'Samples/PixelStreaming2/WebServers/get_ps_servers.sh' in declared
    # Every product must sit under a root the checkpoint store can publish and restore by label.
    bases = [root for root, _ in checkpoint_store.roots(ctx).values()]
    for path in declared:
        assert any(path == base or base in path.parents for base in bases), path


def test_the_cook_restores_the_binary_and_does_not_build(recipe):
    ctx, steps = recipe
    cook = steps['unreal.cook']
    assert 'unreal.game_binary' in cook.needs
    package = [c for c in cook.commands if isinstance(c, UnrealPackage)]
    assert len(package) == 1 and package[0].skip_build
    argv = package[0].argv(ctx)
    assert '-skipbuild' in argv and '-build' not in argv


def test_the_key_covers_the_native_sources_and_the_engine(recipe):
    ctx, steps = recipe
    step = steps['unreal.game_binary']
    assert Path(ctx.uproject) in step.inputs
    assert Path(ctx.unreal_root) / 'Engine/Build/Build.version' in step.inputs
    assert step.deferred_inputs and step.deferred_inputs[0].name == 'native-source-files'


def test_a_restored_receipt_relocates_donor_repository_paths(tmp_path):
    spec = spec_from_file_location('game_binary_test', GAME / 'tools/game_binary.py')
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    project = tmp_path / 'unreal'
    (project / 'Binaries/Mac').mkdir(parents=True)
    (project / 'Binaries/Mac/Yorimichi').write_bytes(b'binary')
    receipt = project / 'Binaries/Mac/Yorimichi.target'
    receipt.write_text(json.dumps(dict(
        BuildProducts=[dict(Path='$(ProjectDir)/Binaries/Mac/Yorimichi', Type='Executable')],
        RuntimeDependencies=[dict(Path='/donor/checkout/platform/engine/Plugins/Activities/Skate/Skate.uplugin',
                                  Type='UFS')])))
    ctx = type('Ctx', (), dict(uproject=project / 'Yorimichi.uproject', unreal_root=tmp_path))

    class Log:
        text = ''

        def write(self, value):
            self.text += value

    log = Log()
    module.relocate(ctx, log)
    data = json.loads(receipt.read_text())
    wanted = (paths.REPO / 'platform/engine/Plugins/Activities/Skate/Skate.uplugin').as_posix()
    assert data['RuntimeDependencies'][0]['Path'] == wanted
    assert 'products' in log.text

