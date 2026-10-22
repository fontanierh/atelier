"""Complete Brinecove output inventories repair missing nonrepresentative packages."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from atelier import build, build_checkpoints, build_products


def test_real_recipe_declares_complete_native_outputs_without_portable_caching(tmp_path):
    recipe = build.load_recipe('yorimichi')
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path, uproject=None)
    graph = build_products.Graph(recipe.steps(ctx))
    step = graph.by_name['unreal.brinecove']
    products = {product.name: product for product in step.products}
    content = recipe.GAME / 'unreal/Content/Brinecove'
    assert products['brinecove.native_meshes'].paths == (content / 'Meshes',)
    assert products['brinecove.native_materials'].paths == (content / 'Materials', content / 'Textures')
    assert products['brinecove.native_report'].paths == (tmp_path / 'brinecove/import-report.json',)
    assert set(step.reads) == {'brinecove.geometry', 'brinecove.materials'}
    assert not step.cache and not step.audit
    # Shared declarations preserve the complete prior Belmonte ownership too.
    belmonte = {product.name: product for product in graph.by_name['unreal.belmonte'].products}
    assert set(belmonte) == {'belmonte.native_meshes', 'belmonte.native_materials',
                              'belmonte.native_tv', 'belmonte.native_report'}


@pytest.mark.parametrize('member', ['Meshes/Secondary.uasset', 'Meshes/Secondary.uexp',
    'Meshes/Secondary.ubulk', 'Meshes/Secondary.uptnl', 'Meshes/Secondary.m.ubulk',
    'Meshes/Secondary.upayload', 'Materials/Current.uasset', 'Textures/Paint.uasset'])
def test_real_inventory_repairs_missing_secondary_native_members(tmp_path, monkeypatch, member):
    recipe = build.load_recipe('yorimichi')
    original_game = recipe.GAME
    out = tmp_path / 'out'
    ctx = SimpleNamespace(game='fixture', out=out, logs=out/'logs', stamps=out/'stamps', uproject=None)
    actual = next(step for step in recipe.brinecove_steps(out) if step.name == 'unreal.brinecove')
    monkeypatch.setattr(recipe, 'GAME', tmp_path / 'game')
    content = recipe.GAME / 'unreal/Content/Brinecove'
    expected = ['Meshes/SM_BC_Ground_0_0.uasset', 'Meshes/Secondary.uasset', 'Materials/Current.uasset',
                'Textures/Paint.uasset', *('Meshes/Secondary'+suffix for suffix in
                    ('.uexp', '.ubulk', '.uptnl', '.m.ubulk', '.upayload'))]
    ran = []
    def receive(ctx, log):
        # Native tools are replaced only here; actual production product roots,
        # build certification and subsequent missing-member checks stay real.
        ran.append('receive')
        for name in expected:
            path = content / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(('fixture native bytes '+name).encode())
        report = out / 'brinecove/import-report.json'
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text('{"native_owner_fixture":true}\n')
    step = replace(actual, commands=[build.Call('native receiving fixture', receive)],
                   needs=[], after=[], reads=[], heavy=False,
                   products=recipe.region_native_products(out, 'brinecove'),
                   outputs=[recipe.GAME / path.relative_to(original_game) if path.is_relative_to(original_game)
                            else path for path in actual.outputs])
    monkeypatch.setattr(build, 'Context', lambda *a, **k: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda _: SimpleNamespace(steps=lambda _: [step]))
    monkeypatch.setattr(build_checkpoints, 'configured', lambda _: None)
    monkeypatch.setenv('ATELIER_CACHE', str(tmp_path / 'cache'))
    def run():
        logs = []
        assert build.build('fixture', [step.name], echo=logs.append) == 0, '\n'.join(logs)
    run()
    run()
    assert ran == ['receive']
    # The legacy representative output remains intact while a different member goes missing.
    (content/member).unlink()
    assert (content/'Meshes/SM_BC_Ground_0_0.uasset').is_file()
    run()
    assert ran == ['receive', 'receive'] and (content/member).is_file()
