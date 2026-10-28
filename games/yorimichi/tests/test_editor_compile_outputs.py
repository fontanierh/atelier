"""Complete editor compile output claims, without UBT or whole-game discovery."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from atelier import build_deferred
from atelier.build_v2 import native_tool_worker
from test_volcano_layers import RECIPE


def compile_step(tmp_path):
    # Evaluate only the actual compile Step declaration, avoiding unrelated graph
    # factories while retaining its original input/deferred/command expressions.
    tree = ast.parse(Path(RECIPE.__file__).read_text())
    method = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'unreal_steps')
    expression = next(node for node in ast.walk(method) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name) and node.func.id == 'Step' and node.args
        and isinstance(node.args[0], ast.Constant) and node.args[0].value == 'unreal.compile')
    context = SimpleNamespace(uproject=RECIPE.GAME / 'unreal/Yorimichi.uproject', out=tmp_path)
    return eval(compile(ast.Expression(expression), str(RECIPE.__file__), 'eval'), {**vars(RECIPE), 'ctx': context}), context


def test_complete_editor_roots_bind_explicit_source_and_validate_with_named_products(tmp_path):
    step, ctx = compile_step(tmp_path)
    assert step.outputs == [RECIPE.GAME / 'unreal/Binaries/Mac']
    products = {product.name: product for product in step.products}
    assert products['unreal.compile.HorseRacing'].paths == (RECIPE.GAME / 'unreal/Plugins/HorseRacing/Binaries/Mac',)
    assert products['unreal.compile.HorseRacing'].optional_paths == ()
    # Real receipt roster: shared AdditionalPluginDirectories modules live in the project Binaries/Mac output.
    assert set(products) == {'unreal.compile.' + p.stem for p in (RECIPE.GAME / 'unreal/Plugins').rglob('*.uplugin')}
    assert set(products) == {'unreal.compile.HorseRacing'}
    shared = {p.stem for p in RECIPE.paths.ENGINE_PLUGINS.rglob('*.uplugin')}
    assert 'AtelierCore' in shared and not shared & {name.removeprefix('unreal.compile.') for name in products}
    assert step.inputs == [ctx.uproject, *RECIPE.compile_inputs.files(RECIPE.native_source_inputs().settings[0])]
    assert not step.deferred_inputs
    build_deferred.validate(step)
    assert step.needs == ['skate.runtime'] and step.heavy
    assert len(step.commands) == 1 and step.commands[0].target == 'YorimichiEditor'


def test_actual_receipt_consumer_requires_both_project_plugin_products(tmp_path):
    step, _ = compile_step(tmp_path)
    view = tmp_path / 'view'; project = view / 'games/yorimichi/unreal/Yorimichi.uproject'
    project.parent.mkdir(parents=True); project.write_text('{}')
    engine = tmp_path / 'engine'; engine.mkdir()
    binaries = project.parent / 'Binaries/Mac'; binaries.mkdir(parents=True)
    horse = project.parent / 'Plugins/HorseRacing/Binaries/Mac'; horse.mkdir(parents=True)
    files = [binaries / 'libUnrealEditor-Yorimichi.dylib', horse / 'libUnrealEditor-AtelierHorseRacing.dylib']
    for path in files: path.write_bytes(b'compile-product-transport')
    (binaries / 'UnrealEditor.modules').write_text(json.dumps({'BuildId': 'fixture', 'Modules': {'Yorimichi': files[0].name}}))
    (horse / 'UnrealEditor.modules').write_text(json.dumps({'BuildId': 'fixture', 'Modules': {'AtelierHorseRacing': files[1].name}}))
    (binaries / 'YorimichiEditor.target').write_text(json.dumps({'TargetName': 'YorimichiEditor', 'Platform': 'Mac',
        'Configuration': 'Development', 'BuildProducts': [{'Path': str(path)} for path in [*files, horse / 'UnrealEditor.modules']]}))
    observed = native_tool_worker.receipt_files(engine, project, 'YorimichiEditor', 'Development', 'editor', owned_root=view)
    with pytest.raises(ValueError): native_tool_worker._covers([binaries], observed)
    checkout = RECIPE.GAME.parents[1]
    roots = [view / root.relative_to(checkout) for root in step.outputs]
    roots += [view / root.relative_to(checkout) for product in step.products for root in product.roots()]
    native_tool_worker._covers(roots, observed)
    assert horse / 'UnrealEditor.modules' in observed and files[1] in observed


def test_real_recipe_graph_accepts_complete_editor_product_roots(tmp_path):
    from atelier.build_products import Graph
    context = SimpleNamespace(uproject=RECIPE.GAME / 'unreal/Yorimichi.uproject', out=tmp_path)
    graph = Graph(RECIPE.steps(context))
    assert graph.owners['unreal.compile.HorseRacing'] == 'unreal.compile'
    assert any(step.name == 'unreal.compile' for step in graph.select(('unreal.compile',)))
