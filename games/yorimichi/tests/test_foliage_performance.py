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


def test_partial_or_failed_sampler_cannot_look_like_a_complete_pass(metrics):
    rows=[[i/1000,5.] for i in range(100)]
    with pytest.raises(ValueError,match='requested interval'):metrics.summarize(rows,10.)
    rows=[[i/60,5.] for i in range(600)]
    assert metrics.summarize(rows,10.)['wall_seconds']>9.9
    with pytest.raises(ValueError,match='callback failed'):metrics.summarize(rows,10.,['RuntimeError: failed'])


def test_sampler_rejects_camera_failures_and_records_callback_exceptions(metrics):
    live=SimpleNamespace(L=SimpleNamespace(game_world=lambda:None),behave=lambda *args:None)
    unreal=SimpleNamespace(SubsystemBlueprintLibrary=SimpleNamespace(get_world_subsystem=lambda *args:object()),
        YorimichiFoliageSubsystem=object(),Vector=lambda *v:v,
        MegaParkValidation=SimpleNamespace(review_camera=lambda *args:False))
    owner=dict(live=live,unreal=unreal)
    exec(metrics.SAMPLER,owner)
    with pytest.raises(AssertionError,match='Review camera failed'):
        owner['start']([0,0,1],[0,0,0],[0,0,0])
    unreal.MegaParkValidation.review_camera=lambda *args:True
    unreal.LiveLibrary=SimpleNamespace(gpu_frame_ms=lambda:(_ for _ in ()).throw(RuntimeError('GPU read failed')))
    owner['start']([0,0,1],[0,0,0],[0,0,0])
    with pytest.raises(RuntimeError,match='GPU read failed'):owner['sample'](.01)
    assert owner['errors']==['RuntimeError: GPU read failed'] and owner['rows']==[]


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


def test_aerial_sweep_uses_dense_real_placements_and_converts_regional_coordinates(metrics,tmp_path):
    for region in ('hidamari','belmonte','brinecove'):(tmp_path/region).mkdir()
    for name in ('world.json','hidamari/city.json'):
        (tmp_path/name).write_text(json.dumps(dict(instances={'Tree_A':[[1,2,3],[3,4,9],[999,999,0]],
                                                            'House_TreeDecoration':[[900,900,999]]*10})))
    for region,asset in [('belmonte','Tree_Tuscan_Oak'),('brinecove','SM_BC_Plant_Broad0')]:
        doc=dict(origin_cm=[1000,-2000,3000],groups=[dict(asset='/Game/'+asset,transforms=[
            dict(translation_cm=[100,-200,300]),dict(translation_cm=[200,-300,400])])])
        (tmp_path/region/'runtime.json').write_text(json.dumps(doc))
    views,centers=metrics.aerial_candidates(tmp_path)
    assert len(views)==24
    assert centers['momiji']==dict(center=[2.,3.,9],trees_in_128m_cell=2)
    assert centers['belmonte']==dict(center=[11.5,22.5,34.],trees_in_128m_cell=2)
    assert views['momiji_80m_down']==[[2.,3.,89.],[2.,3.,21.],[0.,0.,0.]]
    assert views['momiji_240m_oblique'][0][1]<3<views['momiji_240m_oblique'][1][1]


def test_scout_selection_keeps_cpu_pacing_outlier_and_slowest_gpu_views(metrics):
    def view(gpu,p95):return dict(passes=[dict(summary=dict(gpu=dict(mean_ms=gpu),frame=dict(p95_ms=p95)))])
    ranking,selected=metrics.slowest_views(dict(cpu=view(1,200),gpu1=view(40,50),gpu2=view(30,40),gpu3=view(20,30),fast=view(2,3)))
    assert selected==['cpu','gpu1','gpu2','gpu3']
    assert ranking['gpu'][0]=='gpu1' and ranking['frame_p95'][0]=='cpu'


@pytest.mark.parametrize('camera', [[],{'../unsafe':[[0,0,1],[0,0,0],[0,0,0]]},
    {'bad':[[0,0,float('nan')],[0,0,0],[0,0,0]]},{'bad':None},{'bad':[[0,0,0]]*3}])
def test_camera_manifest_refuses_invalid_capture_paths_and_nonfinite_poses(metrics,tmp_path,camera):
    file=tmp_path/'cameras.json';file.write_text(json.dumps(camera))
    with pytest.raises(ValueError):metrics.camera_file(file)


def test_scout_camera_output_roundtrips_for_exact_abba_replay(metrics,tmp_path):
    views={'forest':[[10,20,180],[10,20,30],[0,0,0]]}
    path=tmp_path/'slow_views.json';path.write_text(json.dumps(dict(views=views)))
    assert metrics.camera_file(path)==views
