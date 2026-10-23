"""Each factory action must bootstrap imports even when yori is already cached."""
import ast
from pathlib import Path
import sys
from types import ModuleType

import pytest

REGIONS=Path(__file__).resolve().parents[1]/'world/regions'
SCRIPTS=('hidamari/plan_asset.py','hidamari/plan_tree_lod.py','hidamari/plan_harbor.py',
         'hidamari/layout_data.py','hidamari/north_masks.py','brinecove/plan_component.py',
         'brinecove/plan_ground.py','brinecove/plan_hero.py','houses/plan_asset.py',
         'mega/plan_asset.py','swordcamp/plan_asset.py')


@pytest.mark.parametrize('relative',SCRIPTS)
def test_reset_worker_path_with_cached_yori_keeps_both_canonical_source_roots(monkeypatch,relative):
    script=REGIONS/relative
    # build_batch_worker restores its base path before every action but keeps
    # module objects: importing an already cached yori cannot rerun its setup.
    monkeypatch.setattr(sys,'path',[p for p in sys.path if p not in {str(REGIONS),str(REGIONS.parent)}])
    monkeypatch.setitem(sys.modules,'yori',ModuleType('yori'))
    prefix=[]
    for node in ast.parse(script.read_text()).body:
        prefix.append(node)
        if isinstance(node,ast.Import) and any(alias.name=='yori' for alias in node.names):break
    else:raise AssertionError('Factory action must bootstrap before importing yori')
    exec(compile(ast.Module(body=prefix,type_ignores=[]),str(script),'exec'),{'__file__':str(script)})
    assert sys.path[:2]==[str(REGIONS.parent),str(REGIONS)]
