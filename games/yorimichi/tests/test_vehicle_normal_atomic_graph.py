"""Normal vehicle builds select every independent part before their native consumer."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from atelier import build

GAME=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('family,count',[('sailboat',5),('kei',4),('kart',4)])
def test_actual_vehicle_build_orders_each_selected_source_before_native_import(tmp_path,family,count):
    recipe=build.load_recipe('yorimichi')
    ctx=SimpleNamespace(out=tmp_path.resolve(),game='yorimichi',uproject=None)
    steps=recipe.steps(ctx);by_name={step.name:step for step in steps}
    assert len([name for name in by_name if name.startswith('world.vehicle_'+family+'.geometry.')])==count
    assert isinstance(by_name['world.'+family].commands[0],build.Call)
    assert all(command.script!=GAME/'assets/vehicles'/family/'build.py'
        for step in steps for command in step.commands if isinstance(command,build.Blender))
    required={step.name for step in build.order(steps,['unreal.world' if family=='sailboat' else 'unreal.'+family])}
    assert {'world.'+family+'.sources','world.'+family}<=required
