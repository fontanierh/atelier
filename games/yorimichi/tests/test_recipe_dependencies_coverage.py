from types import SimpleNamespace

from atelier import build, paths
from atelier.build_v2 import recipe_dependencies as rd


def test_real_recipe_extracts_every_static_step_purely(tmp_path):
    out = paths.build_root() / 'yorimichi'
    existed = out.exists()
    recipe = build.load_recipe('yorimichi')
    ctx = SimpleNamespace(game='yorimichi', out=out, uproject=paths.REPO / 'games/yorimichi/unreal/Yorimichi.uproject')
    steps = recipe.steps(ctx)
    game = paths.REPO / 'games/yorimichi'
    roots = (game / 'world', game / 'world/regions', paths.REPO / 'platform/studio')
    report = rd.coverage(steps, checkout=paths.REPO, build_root=paths.build_root(), import_roots=roots)
    assert report['refused'] == 0, report['examples']
    rows = rd.extract(steps, checkout=paths.REPO, build_root=paths.build_root(), import_roots=roots)
    assert len(rows) == len(steps) and all(tuple(row) == rd.ROW_KEYS for row in rows)
    assert len({row['id'] for row in rows}) == len(rows)
    assert all(not path.startswith('/') for row in rows for path in row['code'])
    assert set(report['external_sources']) <= {'blender:5.2', 'atelier-cache:sonniss', 'atelier-cache:yorimichi'}
    assert out.exists() == existed  # extraction creates no build output
