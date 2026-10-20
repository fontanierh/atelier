"""Performance evidence must retain slow frames and reject unavailable GPU timestamps."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def metrics(monkeypatch):
    folder=Path(__file__).resolve().parents[1]/'scenarios'
    monkeypatch.syspath_prepend(str(folder))
    spec=importlib.util.spec_from_file_location('foliage_performance',folder/'foliage_performance.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_slow_frames_are_retained_in_pacing_and_gpu_percentiles(metrics):
    clock=100.;rows=[]
    for i in range(100):
        clock+=.250 if i==90 else .010
        rows.append([clock,100. if i==90 else 5.])
    stats=metrics.summarize(rows)
    assert stats['frames']==99
    assert stats['frame']['max_ms']==pytest.approx(250.)
    assert stats['frame']['p99_ms']==pytest.approx(250.)
    assert stats['gpu']['max_ms']==100. and stats['gpu']['mean_ms']==pytest.approx(5.95)
    assert stats['wall_seconds']==pytest.approx(1.23)


@pytest.mark.parametrize('rows', [[],[[i/60,0.] for i in range(100)],[[0.,5.]]*100,
                                [[i/60,float('nan')] for i in range(100)]])
def test_insufficient_nonmonotonic_or_nullrhi_samples_refuse(metrics,rows):
    with pytest.raises(ValueError):metrics.summarize(rows)


@pytest.mark.parametrize('save_succeeds',[True,False])
def test_restores_actual_active_preferences_instead_of_default_file(metrics,monkeypatch,tmp_path,save_succeeds):
    default=tmp_path/'Saved/settings.txt';default.parent.mkdir();default.write_text('foliage_optimization=1.0\n')
    custom=tmp_path/'session-preferences.txt';custom.write_text('foliage_optimization=0.0\n')
    state=dict(code='compiled',ready=True,fixed_step=False,fixed_frame_rate=False,enabled=False,
               film_hud=True,preferences={'foliage_optimization':0.})
    values={'t.MaxFPS':60.};effects=[]
    def set_preference(key,value):
        custom.write_text(f'{key}={value}\n');return True
    live=SimpleNamespace(L=SimpleNamespace(foliage_review_state=lambda:json.dumps(state),
        set_preference=set_preference,game_world=lambda:None,film_hud=lambda value:effects.append(value)),
        stop=lambda name:None)
    unreal=SimpleNamespace(SystemLibrary=SimpleNamespace(execute_console_command=lambda world,code:effects.append(code)),
        MegaParkValidation=SimpleNamespace(restore_player_camera=lambda:effects.append('camera')))
    def bridge(code):
        if 'print(json.dumps(' in code:return json.dumps(json.loads(live.L.foliage_review_state()))
        exec(code,{'live':live,'unreal':unreal})
        return ''
    monkeypatch.setattr(metrics.qa,'py',bridge)
    active=metrics.active_state('compiled')
    set_preference('foliage_optimization',1.)
    if save_succeeds:metrics.restore(active,values)
    else:
        live.L.set_preference=lambda key,value:False
        with pytest.raises(AssertionError,match='Restoring settings failed'):metrics.restore(active,values)
    assert custom.read_text()==('foliage_optimization=0.0\n' if save_succeeds else 'foliage_optimization=1.0\n')
    assert default.read_text()=='foliage_optimization=1.0\n'
    assert effects==['t.MaxFPS 60.0','camera',True]


@pytest.mark.parametrize('change',[{'fixed_step':True},{'fixed_frame_rate':True},
    {'code':'stale'},{'ready':False},{'enabled':False}])
def test_review_preflight_refuses_invalid_evidence_without_mutation(metrics,monkeypatch,change):
    state=dict(code='compiled',ready=True,fixed_step=False,fixed_frame_rate=False,enabled=True,
               film_hud=False,preferences={'foliage_optimization':1.})
    state.update(change)
    monkeypatch.setattr(metrics,'read_json',lambda code:state)
    monkeypatch.setattr(metrics.qa,'py',lambda code:pytest.fail('Must refuse before any live mutation'))
    with pytest.raises(RuntimeError):metrics.active_state('compiled')
