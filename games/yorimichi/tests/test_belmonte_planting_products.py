"""Planting follows explicit final query surfaces without rebuilding or reading mesh exports."""
import importlib
import json
from pathlib import Path

import numpy as np
import pytest

GAME=Path(__file__).resolve().parents[1]


@pytest.fixture
def module(monkeypatch):
    monkeypatch.syspath_prepend(str(GAME/'world'))
    monkeypatch.syspath_prepend(str(GAME/'world/regions'))
    return importlib.import_module('belmonte.prepare_planting')


def query(module,path,owner,height,stage='final'):
    faces=np.array([[[-2,-2,height],[2,-2,height],[2,2,height]],
                    [[-2,-2,height],[2,2,height],[-2,2,height]]],float)
    module.query_arrays.write(path,faces,owner=owner,stage=stage)


def test_planting_uses_selected_final_heights_and_preserves_helper_results(tmp_path,module,monkeypatch):
    data=dict(planting=[],meshes=[],placements=[])
    inputs=tmp_path/'inputs/planting.json';inputs.parent.mkdir()
    inputs.write_text(json.dumps(dict(schema=1,view='planting',data=data)))
    valley=tmp_path/'BelmonteValley-final.npz';apron=tmp_path/'SM_BM_NorthApron-final.npz'
    query(module,valley,'BelmonteValley',8.);query(module,apron,'SM_BM_NorthApron',9.)
    seen=[]
    def authored(value,height):
        assert value==data and float(height(0,0))==8.;seen.append('authored')
        return {'Tree':[dict(authored=True)]},dict(original_report=True)
    def woodland(surface):
        assert float(surface.height(0,0))==9.;seen.append('woodland')
        return {'Tree':[dict(woodland=True)]}
    def corridor(plants):
        assert plants=={'Tree':[dict(authored=True),dict(woodland=True)]};seen.append('corridor')
        return dict(Tree=3)
    monkeypatch.setattr(module.planting,'replacements',authored)
    monkeypatch.setattr(module.planting,'woodland',woodland)
    monkeypatch.setattr(module.runtime_layout,'clear_railway',corridor)
    output=tmp_path/'result/planting.json';value=module.prepare(inputs,valley,apron,output)
    assert seen==['authored','woodland','corridor']
    assert value['report']['original_report'] is True and value['report']['connecting_woodland']==1
    assert value['report']['railway_corridor_removed']==dict(Tree=3)
    assert value['plants']=={'Tree':[dict(authored=True),dict(woodland=True)]}
    assert json.loads(output.read_text())==value


def test_natural_query_is_not_a_final_planting_fallback(tmp_path,module,monkeypatch):
    inputs=tmp_path/'inputs/planting.json';inputs.parent.mkdir()
    inputs.write_text(json.dumps(dict(schema=1,view='planting',data=dict(planting=[],meshes=[],placements=[]))))
    valley=tmp_path/'BelmonteValley-natural.npz';apron=tmp_path/'SM_BM_NorthApron-final.npz'
    query(module,valley,'BelmonteValley',8.,stage='natural');query(module,apron,'SM_BM_NorthApron',9.)
    monkeypatch.setattr(module.planting,'replacements',lambda *args:pytest.fail('No placement work after invalid query'))
    output=tmp_path/'result/planting.json'
    with pytest.raises(ValueError):module.prepare(inputs,valley,apron,output)
    assert not output.exists()
