"""Editing build-controller code never re-keys real game steps; only code a step executes does."""
import collections
import functools
from pathlib import Path
from types import SimpleNamespace

from atelier import build, build_products, engine

PACKAGE = Path(build.__file__).parent
CONTROLLER = ('build.py', 'build_hashes.py', 'build_cache.py', 'build_inputs.py', 'build_products.py',
              'build_checkpoints.py', 'checkpoint_store.py', 'output_inventory.py')


def fake_blender(tmp_path, monkeypatch):
    """A tiny app bundle, so the test needs no installed Blender (CI has none)."""
    binary = tmp_path / 'Blender.app/Contents/MacOS/Blender'
    binary.parent.mkdir(parents=True)
    binary.write_text('fake blender')
    (binary.parent.parent / 'Resources').mkdir()
    (binary.parent.parent / 'Resources/runtime.py').write_text('bundled runtime')
    monkeypatch.setattr(engine, 'blender', lambda: str(binary))


def test_controller_edits_leave_sampled_game_steps_current(tmp_path, monkeypatch):
    fake_blender(tmp_path, monkeypatch)
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


def test_planning_only_hash_index_edits_leave_native_imports_current(tmp_path, monkeypatch):
    """The Unreal adapter executes file_identity, not the planner's hash index."""
    fake_blender(tmp_path, monkeypatch)
    from atelier import build_hashes, file_identity, native_protocol
    ctx = build.Context('yorimichi')
    steps = build.load_recipe('yorimichi').steps(ctx)
    runtime = {path.resolve() for path in native_protocol.runtime_files()}
    native = [s for s in steps if s.name.startswith('unreal.')
              and runtime <= {Path(item).resolve() for item in s.inputs}]
    assert len(native) >= 30
    planner, primitives = Path(build_hashes.__file__), Path(file_identity.__file__)
    assert planner.resolve() not in runtime and primitives.resolve() in runtime
    upstream = collections.defaultdict(lambda: 'upstream result')

    def key(step, edited=None):
        replaced = {edited: edited.read_bytes() + b'\n# edited\n'} if edited else None
        return build.fingerprint(step, upstream, _input_bytes=replaced)

    for step in native[:3]:
        current = key(step)
        assert key(step, planner) == current, step.name
        assert key(step, primitives) != current, step.name
