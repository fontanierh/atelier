"""Validate actual cold and discovered batch declarations before any tool starts."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, build_batches, build_cache

GAME = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('discovered', [False, True])
def test_complete_recipe_validates_cached_batches_before_and_after_discovery(tmp_path, discovered):
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path.resolve(), uproject=None)
    if discovered:
        # Discovery reads only task membership. No geometry or successful build
        # evidence is fabricated, and no payload or native tool is executed.
        import importlib.util
        spec = importlib.util.spec_from_file_location('batch_test_skate_sources', GAME / 'skatepark_atomic_build.py')
        skate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(skate)
        for region, names in (('skatepark', skate.PARK), ('skatepark_board', skate.BOARD)):
            for name in names:
                root = ctx.out / 'planned_exports' / region / name
                root.mkdir(parents=True)
                (root / 'plan.json').write_text(json.dumps(dict(schema=1, parent=name, complete=True,
                    triangle_limit=32768, source_triangles=1,
                    pieces=[dict(name=name, payload=name + '.npz', triangles=1)])))
    steps = build.load_recipe('yorimichi').steps(ctx)
    plan = build.order(steps, [step.name for step in steps if not step.explicit])
    build.check_modules(plan)
    for step in plan:
        build_batches.validate(step)
        if step.cache:
            assert build_cache.roots(ctx, step), step.name
    names = {step.name for step in plan}
    assert len([name for name in names if name.startswith('world.forest.impostor.')]) == 8
    assert 'world.megapark.letters_data' in names
    roundtrips = [step for step in plan if step.name.startswith('world.skatepark.roundtrip.')]
    assert len(roundtrips) == (10 if discovered else 0)
    repaired = [step for step in plan if step.name.startswith('world.forest.impostor.')
                or step.name == 'world.megapark.letters_data'] + roundtrips
    assert all(step.cache and step.batch is not None for step in repaired)
