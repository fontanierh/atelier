#!/usr/bin/env python3
"""Paired real-time foliage evidence against an owned, running normal game.

uv run python games/yorimichi/scenarios/foliage_performance.py --port OWN_PORT --take NAME

Uses the persistent settings API, verifies the live renderer state, fixes dynamic
resolution/VSync/frame cap for comparison, then restores preferences/CVars/camera.
ABBA ordering reduces warm-up/thermal bias. Includes a moving aerial pass; never uses
fixed-step capture for timings. GPU timing must be available; NullRHI refuses.
Screenshots and raw samples go only under build/yorimichi/foliage_performance/.
"""
import argparse
from collections import defaultdict
import importlib.util
import json
import math
from pathlib import Path
import statistics
import subprocess
import time

from atelier import paths
import skate as qa

# Island metres, x east / y north. These are review cameras, not player placements.
VIEWS = {
    'village_close': ((-248.3,-100.,10.8),(-200.,-102.3,8.5),(0.,0.,0.)),
    'forest_under': ((-128.5,214.5,81.),(-147.3,249.8,84.),(0.,0.,0.)),
    'treehouse_deck': ((-140.,185.,77.7),(-131.,168.,78.),(0.,0.,0.)),
    'canopy': ((-131.,168.,86.),(-145.,145.,87.),(0.,0.,0.)),
    'city_street': ((1100.,-46.,27.),(1200.,-46.,27.),(0.,0.,0.)),
    'aerial_motion': ((-170.,170.,240.),(-125.,170.,75.),(12.,0.,0.)),
}


def aerial_candidates(data):
    """Choose dense tree neighborhoods from actual placements, then vary height and angle."""
    trees={}
    for region,file in [('momiji','world.json'),('hidamari','hidamari/city.json')]:
        doc=json.loads((data/file).read_text())
        trees[region]=[p[:3] for name,placements in doc['instances'].items()
                       if name.startswith(('Tree_','HD_ArcadeTree','HD_PlazaTree')) for p in placements]
    for region in ('belmonte','brinecove'):
        doc=json.loads((data/region/'runtime.json').read_text());origin=doc['origin_cm']
        trees[region]=[]
        for group in doc['groups']:
            name=group['asset'].rsplit('/',1)[-1]
            if not name.startswith(('Tree_','SM_BC_Plant_Broad','SM_BC_Plant_Emergent','SM_BC_Plant_Small','SM_BC_Plant_Palm')):continue
            for pose in group['transforms']:
                p=pose['translation_cm']
                trees[region].append([(origin[0]+p[0])/100.,-(origin[1]+p[1])/100.,(origin[2]+p[2])/100.])
    views,centers={},{}
    for region,points in trees.items():
        cells=defaultdict(list)
        for point in points:cells[(math.floor(point[0]/128.),math.floor(point[1]/128.))].append(point)
        if not cells:raise ValueError('No tree placements for aerial review: '+region)
        key=min(cells,key=lambda cell:(-len(cells[cell]),cell));selected=cells[key]
        center=[sum(p[i] for p in selected)/len(selected) for i in range(2)]+[max(p[2] for p in selected)]
        centers[region]=dict(center=center,trees_in_128m_cell=len(selected))
        x,y,z=center
        for height in (80.,140.,240.):
            for angle in ('down','oblique'):
                eye=[x,y if angle=='down' else y-height*.65,z+height]
                target=[x,y if angle=='down' else y+height*.6,z+12.]
                views[f'{region}_{int(height)}m_{angle}']=[eye,target,[0.,0.,0.]]
    return views,centers


def camera_file(path):
    doc=json.loads(path.read_text())
    if not isinstance(doc,dict):raise ValueError('Expected a camera object')
    views=doc.get('views',doc)
    if not isinstance(views,dict) or not 1<=len(views)<=64:raise ValueError('Expected 1–64 review cameras')
    for key,pose in views.items():
        if not key or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in key):
            raise ValueError('Camera name must be a simple label')
        if not isinstance(pose,(list,tuple)) or len(pose)!=3 or any(not isinstance(v,(list,tuple)) or len(v)!=3 or
            any(not isinstance(x,(int,float)) or not math.isfinite(x) for x in v) for v in pose):
            raise ValueError('Camera needs finite eye, target and velocity vectors')
        if pose[0]==pose[1]:raise ValueError('Camera eye and target must differ')
    return views


def slowest_views(views):
    gpu=sorted(views,key=lambda key:(-views[key]['passes'][0]['summary']['gpu']['mean_ms'],key))
    pacing=sorted(views,key=lambda key:(-views[key]['passes'][0]['summary']['frame']['p95_ms'],key))
    # Preserve the worst pacing view even when its bottleneck is CPU-side.
    selected=list(dict.fromkeys([pacing[0],*gpu[:3]]))
    return dict(gpu=gpu,frame_p95=pacing),selected


def summarize(rows, expected_seconds=None, errors=()):
    if errors:raise ValueError('Sampling callback failed: '+repr(errors))
    if len(rows)<30:raise ValueError('Too few real frames for a pacing comparison')
    frame=[(b[0]-a[0])*1000 for a,b in zip(rows,rows[1:])]
    gpu=[row[1] for row in rows]
    if not all(math.isfinite(x) and x>0 for x in frame+gpu):
        raise ValueError('Invalid real-time samples or unavailable GPU timestamps')
    def stats(values):
        ordered=sorted(values)
        return dict(mean_ms=statistics.fmean(values),median_ms=statistics.median(values),
                    p95_ms=ordered[math.ceil(len(ordered)*.95)-1],
                    p99_ms=ordered[math.ceil(len(ordered)*.99)-1],max_ms=max(values))
    span=rows[-1][0]-rows[0][0]
    if expected_seconds is not None and span+max(.1,2*statistics.median(frame)/1000)<expected_seconds:
        raise ValueError('Sampling ended before the requested interval')
    return dict(frames=len(frame),wall_seconds=span,frame=stats(frame),gpu=stats(gpu))


# Runs in its own namespace in the game's Python interpreter.
SAMPLER = '''
import time
world=live.L.game_world()
system=unreal.SubsystemBlueprintLibrary.get_world_subsystem(world,unreal.YorimichiFoliageSubsystem)
assert system, 'Foliage subsystem unavailable'
def vector(point):return unreal.Vector(point[0]*100.,-point[1]*100.,point[2]*100.)
def aim(eye,target):
    assert unreal.MegaParkValidation.review_camera(vector(eye),vector(target),60.), 'Review camera failed'
def sample(dt):
    try:
        elapsed=time.perf_counter()-started
        offset=[speed[i]*elapsed for i in range(3)]
        if any(speed):aim([eye[i]+offset[i] for i in range(3)],[target[i]+offset[i] for i in range(3)])
        rows.append([time.perf_counter(),float(unreal.LiveLibrary.gpu_frame_ms())])
    except BaseException as error:
        errors.append(type(error).__name__+': '+str(error))
        raise
def start(e,t,s):
    global eye,target,speed,rows,errors,started
    eye,target,speed=e,t,s
    rows=[];errors=[];started=time.perf_counter();aim(eye,target)
    live.behave('foliage_performance',sample)
'''


def read_json(code):
    return json.loads(qa.py('import json;print(json.dumps('+code+'))').strip().splitlines()[-1])


def active_state(code_identity):
    state=read_json('json.loads(live.L.foliage_review_state())')
    if state['code']!=code_identity:raise RuntimeError('Running native code is stale for this checkout')
    if not state['ready']:raise RuntimeError('World has not reached gameplay readiness')
    if state['fixed_step'] or state['fixed_frame_rate']:
        raise RuntimeError('Real-time comparison requires both fixed-clock modes off')
    original=state['preferences']['foliage_optimization']
    if original not in (0.,1.) or state['enabled']!=bool(original):
        raise RuntimeError('Renderer must match the active saved foliage preference')
    return state


def restore(state,cvars):
    original=state['preferences']['foliage_optimization']
    qa.py('live.stop("foliage_performance")\n'
          f'try:\n assert live.L.set_preference("foliage_optimization",{original}), "Restoring settings failed"\n'
          'finally:\n for key,value in '+repr(cvars)+'.items():unreal.SystemLibrary.execute_console_command(live.L.game_world(),key+" "+str(value))\n'
          f' unreal.MegaParkValidation.restore_player_camera();live.L.film_hud({state["film_hud"]!r})')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,required=True)
    parser.add_argument('--take',required=True)
    parser.add_argument('--seconds',type=float,default=10.)
    parser.add_argument('--settle',type=float,default=8.)
    parser.add_argument('--views',nargs='+')
    parser.add_argument('--camera-file',type=Path)
    parser.add_argument('--aerial-scout',action='store_true',help='rank original-mode aerial views over the densest tree placements')
    args=parser.parse_args()
    if args.aerial_scout and args.camera_file:parser.error('aerial-scout generates its own placement-based cameras')
    views,centers=aerial_candidates(paths.build_root()/'yorimichi') if args.aerial_scout else (camera_file(args.camera_file) if args.camera_file else VIEWS,{})
    chosen=args.views or list(views)
    if any(name not in views for name in chosen):parser.error('unknown camera in --views')
    if not args.take or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in args.take):
        parser.error('take must be a simple unique name')
    if args.seconds<2 or args.seconds>30 or args.settle<2 or args.settle>30:parser.error('sample/settle must be 2–30 seconds')
    qa.bridge.URL=f'http://127.0.0.1:{args.port}'
    project=read_json('str(unreal.Paths.project_dir())')
    if Path(project).resolve()!=(qa.GAME/'unreal').resolve():raise RuntimeError('Live game belongs to another checkout')
    repo=qa.GAME.parents[1]
    if subprocess.check_output(['git','status','--porcelain'],cwd=repo,text=True).strip():
        raise RuntimeError('Revision-bound evidence requires a clean source checkout')
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    spec=importlib.util.spec_from_file_location('foliage_network_identity',qa.GAME/'network_identity.py')
    identity=importlib.util.module_from_spec(spec);spec.loader.exec_module(identity)
    state=active_state(identity.code_identity(repo))
    saved=state['preferences'];original=saved['foliage_optimization']
    out=paths.build_root()/'yorimichi/foliage_performance'/args.take
    out.mkdir(parents=True,exist_ok=False)
    settings=['t.MaxFPS','r.VSync','r.DynamicRes.OperationMode','r.ProfileGPU.ShowUI','t.IdleWhenNotForeground']
    cvars=read_json('{key:unreal.SystemLibrary.get_console_variable_float_value(key) for key in '+repr(settings)+'}')
    graphics=('renderer','performance','render_scale','forest_detail','tree_sway','tree_shadow','laptop',
              'tree_optimization','tree_lod_mode','tree_lod_distance','leaf_motion','painterly','fog')
    report=dict(revision=revision,code=state['code'],settings={key:saved[key] for key in graphics if key in saved},
                original_enabled=original,original_cvars=cvars,views={},errors=[],
                mode='original_aerial_scout' if args.aerial_scout else 'abba',tree_centers=centers)
    # A viewport size alone does not establish internal pixel count or lighting.
    # Record actual renderer controls as well as the saved player preferences.
    renderer_cvars=['r.ScreenPercentage','r.SecondaryScreenPercentage.GameViewport','r.ForwardShading',
                    'r.DynamicGlobalIlluminationMethod','r.ReflectionMethod','r.AntiAliasingMethod','sg.ShadowQuality']
    report['renderer_cvars']=read_json('{key:unreal.SystemLibrary.get_console_variable_float_value(key) for key in '+repr(renderer_cvars)+'}')
    report['viewport']=read_json('list(unreal.GameplayStatics.get_player_controller(live.L.game_world(),0).get_viewport_size())')
    if min(report['viewport'])<=0:raise RuntimeError('A real viewport is required for a resolution-bound comparison')
    try:
        qa.py('live.FOLIAGE_QA=dict(live=live,unreal=unreal)\nexec('+repr(SAMPLER)+',live.FOLIAGE_QA)')
        qa.py('live.L.film_hud(True)')
        for name in chosen:
            eye,target,speed=views[name];results=[]
            passes=(False,) if args.aerial_scout else (False,True,True,False)
            for index,enabled in enumerate(passes):
                print(f'{name} pass {index+1}/{len(passes)}: optimization={enabled}; settling {args.settle:g}s then sampling {args.seconds:g}s',flush=True)
                qa.py(f'assert live.L.set_preference("foliage_optimization",{int(enabled)}), "Settings switch refused"\n'
                      f'assert live.FOLIAGE_QA["system"].is_enabled()=={enabled}, "Renderer did not switch"\n'
                      'for key in '+repr(settings)+':unreal.SystemLibrary.execute_console_command(live.L.game_world(),key+" 0")\n'
                      f'live.FOLIAGE_QA["aim"]({eye!r},{target!r})')
                time.sleep(args.settle)
                qa.py(f'live.FOLIAGE_QA["start"]({eye!r},{target!r},{speed!r})')
                time.sleep(args.seconds)
                capture=read_json('(live.stop("foliage_performance"),dict(rows=live.FOLIAGE_QA["rows"],errors=live.FOLIAGE_QA["errors"]))[1]')
                (out/f'{name}_{index}_samples.json').write_text(json.dumps(capture)+'\n')
                rows=capture['rows']
                result=dict(enabled=enabled,samples=rows,summary=summarize(rows,args.seconds,capture['errors']))
                results.append(result)
                shot=out/f'{name}_{index}_{"on" if enabled else "off"}.png'
                qa.py(f'live.L.screenshot({str(shot)!r})')
                # Detailed GPU event breakdown stays in the owned game's stdout log.
                qa.py('unreal.SystemLibrary.execute_console_command(live.L.game_world(),"ProfileGPU")')
                print(f'{name} pass {index+1}: '+json.dumps(result['summary']),flush=True)
            report['views'][name]=dict(eye=eye,target=target,velocity_m_s=speed,passes=results)
            if not args.aerial_scout:report['views'][name].update(
                gpu_mean_speedup=statistics.fmean(p['summary']['gpu']['mean_ms'] for p in results if not p['enabled'])/
                                 statistics.fmean(p['summary']['gpu']['mean_ms'] for p in results if p['enabled']),
                frame_p95_speedup=statistics.fmean(p['summary']['frame']['p95_ms'] for p in results if not p['enabled'])/
                                  statistics.fmean(p['summary']['frame']['p95_ms'] for p in results if p['enabled']))
            (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        if args.aerial_scout:
            report['rankings'],selected=slowest_views(report['views'])
            (out/'slow_views.json').write_text(json.dumps(dict(views={key:views[key] for key in selected}),indent=2)+'\n')
            print('Slowest aerial review cameras: '+', '.join(selected),flush=True)
    except BaseException as error:
        report['errors'].append(type(error).__name__+': '+str(error))
        raise
    finally:
        try:
            restore(state,cvars)
        except Exception as error:
            report['errors'].append('Restore: '+str(error))
            raise
        finally:(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Foliage comparison complete: '+str(out),flush=True)


if __name__=='__main__':main()
