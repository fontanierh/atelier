"""Normal terminal graph preserves proof reads and independently reusable mesh exports."""
from pathlib import Path
from types import SimpleNamespace
import importlib.util

import pytest
from atelier import build

GAME=Path(__file__).resolve().parents[1]


def test_normal_terminal_graph_keeps_final_source_proofs_and_independent_exports(tmp_path):
    recipe=build.load_recipe('yorimichi')
    ctx=SimpleNamespace(out=tmp_path.resolve(),game='yorimichi',uproject=None)
    steps=recipe.steps(ctx);rows={step.name:step for step in steps}
    required={step.name for step in build.order(steps,['unreal.ferry'])}
    plans=[step for name,step in rows.items() if name.startswith('world.ferry_terminals.geometry.')]
    assert len(plans)==11 and all(step.cache for step in plans)
    assert all(step.commands[0].factory_startup and step.commands[0].threads==3 for step in plans)
    assert all(len(step.reads)==1 and step.reads[0].startswith('ferry_terminals.source.') for step in plans)
    for name in ('world.ferry_terminals.sources','world.ferry_terminals.audit'):
        step=rows[name]
        assert name in required and not step.deferred_inputs and step.cache
        assert 'world.ferry_terminals.proof_inputs' in step.needs
    proof=rows['world.ferry_terminals.proof_inputs']
    assert proof.cutoff and proof.deferred_inputs and not proof.cache and not proof.products and not proof.reads
    assert 'world.hidamari_ferry_cut' in proof.needs
    assert isinstance(rows['world.ferry_terminals'].commands[0],build.Call)
    assert 'ferry.terminals' in rows['unreal.ferry'].reads
    for relative in ('unreal/Scripts/ferry_native.py','ferry_terminal_atomic_products.py',
                     'world/regions/ferry/ship_sources.py'):
        assert GAME/relative in rows['unreal.ferry'].inputs
    assert all(command.script!=GAME/'assets/vehicles/ferry/terminals/build.py'
               for step in steps for command in step.commands if isinstance(command,build.Blender))


def test_terminal_proof_cutoff_binds_complete_bytes_without_checkout_path_keys(tmp_path,monkeypatch):
    spec=importlib.util.spec_from_file_location('terminal_proof_graph_test',GAME/'ferry_terminal_atomic_build.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    out=tmp_path.resolve()/'build';repo=tmp_path.resolve()/'source';out.mkdir();repo.mkdir()
    generated=out/'surface.npz';source=repo/'validator.py'
    generated.write_bytes(b'original source surface');source.write_bytes(b'current exact validator')
    monkeypatch.setattr(module,'proof_paths',lambda *a:[generated,source])
    first=module.proof_snapshot(out,repo)
    assert set(first['files'])=={'generated/surface.npz','source/validator.py'}
    generated.write_bytes(b'changed source surface')
    second=module.proof_snapshot(out,repo)
    assert second['files']['generated/surface.npz']!=first['files']['generated/surface.npz']
    assert second['files']['source/validator.py']==first['files']['source/validator.py']
    linked=out/'linked';linked.symlink_to(source)
    monkeypatch.setattr(module,'proof_paths',lambda *a:[linked])
    with pytest.raises(ValueError,match='regular'):module.proof_snapshot(out,repo)
