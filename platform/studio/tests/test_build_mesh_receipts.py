"""Host receipt publication follows native exit, marker and guard cleanup; no native launched."""
import io
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, checkpoint_store as cp, mesh_reuse


@pytest.mark.parametrize('failure', [None, 'exit', 'marker'])
def test_standalone_receipt_is_bound_to_successful_invocation(tmp_path, monkeypatch, failure):
    out = tmp_path / 'out'
    old = dict(fingerprint='a' * 64, input_state=dict(inputs={'source': 'b' * 64}))
    ctx = SimpleNamespace(game='fixture', out=out, logs=out / 'logs',
                          native_previous_stamps={'import.mesh': old}, env=lambda extra: dict(os.environ, **dict(extra)))
    step = build.Step('import.mesh', [], heavy=True)
    command = build.UnrealScript(tmp_path / 'import.py', 'IMPORT_OK')
    events, invocations = [], []
    def guard(argv, folder, **kwargs):
        env = kwargs['env']; invocations.append(env)
        packet = cp.read_json(Path(env['ATELIER_BUILD_PRIOR_STAMP']))
        assert packet == dict(schema=1, task=step.name, nonce=env['ATELIER_MESH_REUSE_NONCE'], stamp=old, observed_context=None)
        assert env['ATELIER_BUILD_SCRIPT'] == str(command.script)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'stdout.log').write_text('no marker' if failure == 'marker' else 'IMPORT_OK')
        events.append('guard closed')
        return 9 if failure == 'exit' else 0
    def finalize(ctx, task, nonce):
        assert events == ['guard closed']
        assert nonce == invocations[-1]['ATELIER_MESH_REUSE_NONCE'] and task == step.name
        events.append('receipts')
    monkeypatch.setattr(build.guarded, 'run', guard)
    monkeypatch.setattr(mesh_reuse, 'finalize_pending', finalize)
    def run():
        build.run_argv(ctx, step, command, ['stand-in'], (), io.StringIO(), ('job', None), [])
    if failure:
        with pytest.raises(RuntimeError):
            run()
        assert events == ['guard closed']
    else:
        run()
        first = invocations[-1]['ATELIER_MESH_REUSE_NONCE']
        assert len(first) == 24 and events == ['guard closed', 'receipts']
        events.clear(); run()
        assert invocations[-1]['ATELIER_MESH_REUSE_NONCE'] != first
