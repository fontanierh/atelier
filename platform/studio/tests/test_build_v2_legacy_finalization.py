"""Actual shared orchestration ordering; mocked effects confer no production authority."""
from contextlib import contextmanager
from types import SimpleNamespace
import pytest

from atelier import build, build_checkpoints, build_hashes, checkpoint_manifest, checkpoint_store, store_retention


@pytest.mark.parametrize('failure', [None, 'held', 'discard', 'finish', 'collect', 'close', 'scope'])
def test_managed_settlement_is_after_all_finalizers_and_positive_index_close(tmp_path, monkeypatch, failure):
    events = []
    sentinel = RuntimeError('original-' + str(failure))
    def effect(name):
        events.append(name)
        if failure == name:
            raise sentinel
    class Authority:
        ready = False
        def before_prepare(self, *args): effect('prepare')
        @contextmanager
        def writer(self, output):
            yield
        def checkpoint_complete(self, ctx, invalid):
            effect('checkpoint-ready')
            self.ready = True
        def before_collection(self, ctx):
            effect('scope')
        def after_index(self, ctx):
            if self.ready:
                effect('settle')
    class Index:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self):
            effect('open')
            return self
        def __exit__(self, *args):
            effect('close')
    ctx = SimpleNamespace(game='fixture', out=tmp_path, stamps=tmp_path / 'stamps', legacy_authority=Authority())
    def execute(ctx, *args, checkpoint, **kwargs):
        checkpoint.update(steps=[], plan=[], done={})
        effect('execute')
        if failure == 'held':
            raise sentinel
        return 0
    monkeypatch.setattr(build, '_execute_build', execute)
    monkeypatch.setattr(build, '_discard_changed_certificates', lambda *a, **k: effect('discard') or [])
    monkeypatch.setattr(checkpoint_manifest, 'finish', lambda *a: effect('finish'))
    monkeypatch.setattr(store_retention, 'maybe_collect', lambda *a, **k: effect('collect'))
    monkeypatch.setattr(checkpoint_store, 'Store', lambda *a: object())
    monkeypatch.setattr(build_checkpoints, 'configured', lambda ctx: {'rebuild_budget_seconds': 600})
    monkeypatch.setattr(build_checkpoints, 'prepare', lambda *a, **k: effect('checkpoint-prepare'))
    monkeypatch.setattr(build_hashes, 'HashIndex', Index)
    def run():
        return build._prepared_build(ctx, [], force=False, touch=False, echo=lambda *a: None,
                verify=False, rebuild_reason=None, rebuild_touched=False, record_cook_recovery=False,
                max_heavy_commands=None, prepared_steps=[])
    if failure is None:
        assert run() == 0
        assert events.index('finish') < events.index('collect') < events.index('close') < events.index('settle')
    else:
        with pytest.raises(RuntimeError) as result:
            run()
        assert result.value is sentinel
        if failure == 'held':
            assert 'finish' not in events and 'collect' not in events
            assert events.index('discard') < events.index('close') < events.index('settle')
        else:
            assert 'settle' not in events
