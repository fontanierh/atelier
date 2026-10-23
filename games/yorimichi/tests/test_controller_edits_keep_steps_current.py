"""Editing build-controller code never re-keys real game steps; only code a step executes does."""
import collections
import functools
from pathlib import Path
from types import SimpleNamespace

from atelier import build, build_products

PACKAGE = Path(build.__file__).parent
CONTROLLER = ('build.py', 'build_hashes.py', 'build_cache.py', 'build_inputs.py', 'build_products.py',
              'build_checkpoints.py', 'checkpoint_store.py', 'store_reuse.py', 'output_inventory.py')


def test_controller_edits_leave_sampled_game_steps_current():
    ctx = build.Context('yorimichi')
    steps = build.load_recipe('yorimichi').steps(ctx)
    tooled = [s for s in steps if s.toolchain and not s.cache][:3]
    cached = [s for s in steps if s.cache][:3]
    sample = tooled + cached
    assert len(sample) == 6
    digest = functools.lru_cache(maxsize=None)(lambda path: build_products.file_digest(path))
    upstream = collections.defaultdict(lambda: 'upstream result')

    def key(step, edited=None):
        def hashed(path):
            path = Path(path)
            return digest(path) + (':edited' if path.parent == PACKAGE and path.name == edited else '')
        return build.fingerprint(step, upstream, index=SimpleNamespace(digest=hashed))

    for step in sample:
        current = key(step)
        assert [name for name in CONTROLLER if key(step, name) != current] == [], step.name
        # The executed adapter still re-keys the step, so the check above is not vacuous.
        assert key(step, 'build_source.py') != current, step.name
