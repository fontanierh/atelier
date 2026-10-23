"""Unreal imports with owned Content folders publish like source actions; the folders never overlap."""
from atelier import build, checkpoint_actions, paths


def test_owned_content_imports_declare_disjoint_complete_outputs(monkeypatch):
    # The installed engine and toolchain identity, without an installed engine.
    monkeypatch.setattr(checkpoint_actions, 'context', lambda _: dict(system='Darwin', machine='arm64', engine='installed'))
    ctx = build.Context('yorimichi')
    steps = build.load_recipe('yorimichi').steps(ctx)
    recipe = build.load_recipe('yorimichi')
    by_name = {s.name: s for s in steps}
    assert set(recipe.OWNED_CONTENT) <= set(by_name)
    content = paths.GAMES / 'yorimichi/unreal/Content'
    for name, folders in recipe.OWNED_CONTENT.items():
        step = by_name[name]
        assert all(content / folder in step.checkpoint_outputs for folder in folders), name
        assert all(output in step.checkpoint_outputs or any(root in output.parents for root in step.checkpoint_outputs)
                   for output in step.outputs), name
        assert checkpoint_actions.key(ctx, step, 'fingerprint') is not None, name
    checkpoint_actions.validate_ownership(ctx, steps)  # Raises on any overlapping output scope.
    # Imports sharing Japan/* or a character's root are deliberately left unpublished.
    assert not by_name['unreal.kei'].checkpoint_outputs and not by_name['unreal.world'].checkpoint_outputs
