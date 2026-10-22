"""Forest import changes keep the independent Belmonte library current."""
from types import SimpleNamespace

import pytest

from atelier import build
from test_mega_ramp_layers import changed_by
from test_volcano_layers import RECIPE


def test_forest_reimport_does_not_reimport_belmonte_but_still_recooks(tmp_path, monkeypatch):
    changed = changed_by(RECIPE.SCRIPTS / 'import_forest.py', tmp_path, monkeypatch)
    assert 'unreal.forest' in changed
    assert 'unreal.belmonte' not in changed
    assert {'data.content', 'data.network', 'unreal.cook', 'unreal.package'} <= changed


@pytest.mark.parametrize('name', ['import_belmonte.py', 'atmosphere.py', 'ground_grain.py'])
def test_belmonte_consumed_code_still_reimports_and_recooks(tmp_path, monkeypatch, name):
    changed = changed_by(RECIPE.SCRIPTS / name, tmp_path, monkeypatch)
    assert {'unreal.belmonte', 'unreal.cook', 'unreal.package'} <= changed


def test_targeted_belmonte_preserves_forest_reachability_and_order(tmp_path):
    steps = RECIPE.steps(SimpleNamespace(out=tmp_path, uproject=None))
    # Order must come from the dependency, even if declarations are presented in reverse.
    selected = build.order(list(reversed(steps)), ['unreal.belmonte'])
    names = [step.name for step in selected]
    assert names.index('unreal.forest') < names.index('unreal.belmonte')
    belmonte = next(step for step in selected if step.name == 'unreal.belmonte')
    assert {'unreal.world',
            *RECIPE.unreal_modules.needs(RECIPE.IMPORT_CODE)} <= set(belmonte.needs)
    assert set(belmonte.reads) == {'belmonte.geometry', 'belmonte.materials'}
