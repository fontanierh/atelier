"""Calls receive only frozen staged paths and a write-only progress sink."""
import dataclasses
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier.build_v2 import recipe_compiler as compiler, recipe_dependencies as dependencies, recipe_job as job


def load(path):
    spec = importlib.util.spec_from_file_location('call_binding_fixture', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def context(out='build/game'):
    return {'game': 'game', 'out': {'path': out}, 'game_dir': {'path': 'games/game'},
            'uproject': {'path': 'games/game/unreal/Game.uproject'}, 'unreal_root': None}


def test_actual_region_assembly_binds_required_arguments_and_derived_items(tmp_path, capsys):
    source = tmp_path / 'games/game/region_exports.py'
    source.parent.mkdir(parents=True)
    source.write_bytes((Path(__file__).resolve().parents[1] / 'region_exports.py').read_bytes())
    script = source.parent / 'planner.py'
    script.write_text('')
    graph = load(source)
    out = tmp_path / 'build/game'
    steps = graph.steps(SimpleNamespace(out=out), region='fixture',
                        assets=[graph.LogicalAsset('One', script)])
    fn = steps[-1].commands[0].fn
    binding = dependencies._callable(fn, dependencies._Paths(tmp_path, tmp_path / 'build'),
                                     step='assembly', what='Call')
    assert binding['required_parameters'] == [{'name': 'ctx', 'kind': 'POSITIONAL_OR_KEYWORD'},
                                               {'name': 'log', 'kind': 'POSITIONAL_OR_KEYWORD'}]
    index = fn.__code__.co_freevars.index('children')
    binding['closure'][index] = {'derived_items': {'root': 'build/derived', 'members': [
        {'root': 'build/derived/One', 'piece': 'One'}]}}
    plan = out / 'planned_exports/fixture/One'
    plan.mkdir(parents=True)
    (plan / 'plan.json').write_text(json.dumps(dict(schema=1, parent='One', complete=True,
        triangle_limit=32768, source_triangles=12, source_polygons=12, source_collision_hulls=0,
        slots=['Surface'], matrix=[], pieces=[dict(name='One', payload='One.npz', triangles=12,
        polygons=12, collision_hulls=0, min=[0, 0, 0], max=[1, 1, 1])])) )
    exported = tmp_path / 'build/derived/One'
    exported.mkdir(parents=True)
    (exported / 'One.fbx').write_bytes(b'owned primary bytes')
    from atelier.export_tasks import publish_receipt
    publish_receipt(exported, key='One', primary='One.fbx', triangles=12,
                    bounds=[[0, 0, 0], [1, 1, 1]])
    command = compiler._command({'kind': 'call', 'fn': binding}, call_context=context())
    assert set(command) == {'kind', 'call'}
    job.bind(command['call'], tmp_path)()
    destination = out / 'atomic_regions/fixture'
    assert (destination / 'assets/One.fbx').read_bytes() == b'owned primary bytes'
    assert json.loads((destination / 'logical-pieces.json').read_text())['exports'] == ['One']
    assert 'Assembled 1 independently cached fixture exports' in capsys.readouterr().out


def test_unknown_required_arguments_and_noncall_required_verify_refuse(tmp_path):
    source = tmp_path / 'callbacks.py'
    source.write_text('def unsupported(secret): pass\ndef required(ctx, log): pass\ndef plain(value=3): return value\n')
    module = load(source)
    ps = dependencies._Paths(tmp_path, tmp_path / 'build')
    binding = lambda fn: dependencies._callable(fn, ps, step='step', what='Call')
    with pytest.raises(compiler.Unsupported, match='unsupported arguments'):
        compiler._command({'kind': 'call', 'fn': binding(module.unsupported)}, call_context=context())
    with pytest.raises(compiler.Unsupported, match='unsupported arguments'):
        compiler._binding(binding(module.required))
    plain = compiler._binding(binding(module.plain))
    assert plain['defaults'] == [3]
    assert job.bind(plain, tmp_path)() == 3


def test_context_is_immutable_staged_paths_and_does_not_grant_io(tmp_path):
    from atelier.build_v2.python_job import PathGuard
    descriptor = context('custom-output/game')
    ctx = job._value({'recipe_context': descriptor}, tmp_path)
    assert ctx.out == tmp_path / 'custom-output/game'
    assert ctx.game_dir == tmp_path / 'games/game'
    assert ctx.uproject == tmp_path / 'games/game/unreal/Game.uproject'
    assert ctx.unreal_root is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.out = tmp_path
    assert not hasattr(ctx, 'stamps') and not hasattr(ctx, 'launch')
    guard = PathGuard(str(tmp_path), [], [], lambda _: None, [str(ctx.out / 'declared.json')])
    assert guard.allowed('write', str(ctx.out / 'declared.json'))
    assert not guard.allowed('write', str(ctx.out / 'unknown.json'))
    assert not guard.allowed('read', str(tmp_path.parent / 'ambient-project.uproject'))
    logger = job._value({'recipe_stdout': True}, tmp_path)
    assert not hasattr(logger, 'read') and not hasattr(logger, 'fileno')
    with pytest.raises(TypeError): logger.write(b'bytes')


def test_compile_rows_binds_custom_output_root_without_host_paths(tmp_path):
    source = tmp_path / 'callbacks.py'
    source.write_text('def action(ctx, log, value=7): return ctx.out, value\n')
    module = load(source)
    binding = dependencies._callable(module.action, dependencies._Paths(tmp_path, tmp_path / 'custom'),
                                     step='action', what='Call')
    row = {'id': 'action', 'commands': [{'kind': 'call', 'fn': binding}], 'code': ['callbacks.py'],
           'inputs': [], 'reads': [], 'needs': [], 'after': [], 'products': [],
           'outputs': ['custom/game/result.json'], 'verify': None, 'replan': False}
    request = compiler.compile_rows([row], project='game', targets=['action'], checkout=tmp_path,
                                    callback_out='custom/game').request(tmp_path)
    call = request['declaration']['units'][0]['params']['recipe']['commands'][0]['call']
    assert call['defaults'][0]['recipe_context']['out'] == {'path': 'custom/game'}
    assert call['defaults'][-1] == 7
    assert job.bind(call, tmp_path)() == (tmp_path / 'custom/game', 7)
    with pytest.raises(compiler.Unsupported, match='noncanonical'):
        compiler.compile_rows([row], project='game', targets=['action'], checkout=tmp_path,
                              callback_out='../ambient')
