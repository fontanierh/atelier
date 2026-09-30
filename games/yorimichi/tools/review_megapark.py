"""Capture and smoke-test the native Super Ultra Mega Park under the render guard.

Run with project Python after world.megapark and unreal.megapark are built.
The worker owns and quits only the game process it launches.
"""
from pathlib import Path
from contextlib import ExitStack
import argparse,json,subprocess,sys,time
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'world'))
import yori
from atelier.build import Context
from atelier.safety import guarded
from atelier.safety.guard import attach as attach_memory_guard, reap
from atelier import live
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
parser.add_argument('--port',type=int,default=8839)
args=parser.parse_args()
live.URL=f'http://127.0.0.1:{args.port}'
ctx=Context('yorimichi'); root=yori.REPO; out=yori.OUT/'megapark/play-review'; out.mkdir(parents=True,exist_ok=True)
if not args.worker:
 sys.exit(guarded.run([sys.executable,str(Path(__file__).resolve()),'--worker','--port',str(args.port)],out/'guard',timeout=240,purpose='Super Ultra Mega Park review',kind='game'))
(out/'passed.json').unlink(missing_ok=True)
log=(out/'game.log').open('w')
cmd=[str(ctx.unreal_app),str(ctx.uproject),'/Game/MegaPark/Maps/SuperUltraMegaPark','-game','-windowed','-resx=1600','-resy=1000','-nosplash','-stdout',f'-liveport={args.port}','-ini:Engine:[HTTPServer.Listeners]:DefaultBindAddress=localhost','-preferencesfile='+str(out/'settings.txt'),'-set=painterly=0;toon=0;outline=0;wind=0;exposure=0;saturation=1','-ExecCmds=t.MaxFPS 60,r.RHISetGPUCaptureOptions 0']
p=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT)
guards=ExitStack()
monitor=None
def run(code):
 if monitor is not None and monitor.poll() is not None and p.poll() is None:
  raise RuntimeError('Memory monitor exited before the game')
 r=live.request('/python',code,timeout=30)
 if not r.get('ok'):raise RuntimeError(r)
 print(r.get('output','').strip(),flush=True)
 return r
try:
 # The outer guard owns the worker/lock; monitor the actual Unreal process too.
 monitor=guards.enter_context(attach_memory_guard(p.pid,out/'memory-health.json',duration=240))
 deadline=time.monotonic()+150
 while time.monotonic()<deadline:
  if p.poll() is not None:raise RuntimeError('Game exited '+str(p.returncode))
  try:
   state=live.request('/state',timeout=1); break
  except OSError:time.sleep(1)
 else:raise RuntimeError('Bridge startup timed out')
 (out/'initial-state.json').write_text(json.dumps(state,indent=2))
 run("import unreal, json, math\nw=unreal.LiveLibrary.game_world()\np=unreal.LiveLibrary.player()\nprint(w.get_name(),p.get_name(),unreal.YorimichiLive.skate_state())\nassert len(unreal.GameplayStatics.get_all_actors_of_class(w,unreal.SuperUltraMegaPark))==1\nassert len(unreal.GameplayStatics.get_all_actors_of_class(w,unreal.MegaParkWorld))==1\nassert len(unreal.GameplayStatics.get_all_actors_of_class(w,unreal.LeafStorm))==0\nprint('level services and no leaf storm passed')")
 source=json.loads((yori.ASSETS/'megapark/map.json').read_text())
 triangles=np.concatenate([np.load(yori.ASSETS/'megapark'/m['npz'],allow_pickle=False)['triangles'] for m in source['collision']]).astype('f8')
 a,b,c=triangles[:,0],triangles[:,1],triangles[:,2]
 denominator=(b[:,2]-c[:,2])*(a[:,0]-c[:,0])+(c[:,0]-b[:,0])*(a[:,2]-c[:,2])
 reference=[]
 for x,z in [(330,-710),(322,-700),(320,-690),(320,-675),(318,-650),(305,-630),(310,-610),(320,-590),(300,-560),(340,-550),(375,-655)]:
  with np.errstate(divide='ignore',invalid='ignore'):
   u=((b[:,2]-c[:,2])*(x-c[:,0])+(c[:,0]-b[:,0])*(z-c[:,2]))/denominator
   v=((c[:,2]-a[:,2])*(x-c[:,0])+(a[:,0]-c[:,0])*(z-c[:,2]))/denominator
   s=1-u-v; heights=u*a[:,1]+v*b[:,1]+s*c[:,1]
   inside=(u>=-1e-8)&(v>=-1e-8)&(s>=-1e-8)&np.isfinite(heights)
   assert inside.any(),(x,z)
   reference.append([x,float(heights[inside].max()),z])
 run('traces=[]\nfor x,y,z in '+repr(reference)+":\n point=unreal.LiveLibrary.ground_at(unreal.Vector(x*100,z*100,(y+10)*100))\n error=abs(point.z-y*100)\n traces.append([x,z,y,point.z/100,error])\n assert error<.1, traces[-1]\nprint(json.dumps(traces))")
 (out/'traces.json').write_text(run('print(json.dumps(traces))')['output'])
 # Runtime camera, independent of the player camera boom.
 run('unreal.YorimichiLive.film_hud(True)')
 for name,at,target in [('overview',(620,-370,390),(325,-655,105)),('upper',(330,-735,148),(322,-635,91)),('lower',(370,-670,150),(350,-645,97))]:
  x,y,z=at; tx,ty,tz=target
  run(f'assert unreal.MegaParkValidation.review_camera(unreal.Vector({x*100},{y*100},{z*100}),unreal.Vector({tx*100},{ty*100},{tz*100}),65.)')
  time.sleep(2)
  path=out/(name+'.png'); path.unlink(missing_ok=True); run('unreal.LiveLibrary.screenshot('+repr(str(path))+')')
  for _ in range(50):
   if path.exists():break
   time.sleep(.1)
  assert path.exists(),path
 # Ride along the upper deck. Reaching the descending route requires steering
 # through its original U-turn; a straight input would go over the side.
 run('unreal.MegaParkValidation.restore_player_camera()\nunreal.YorimichiLive.film_hud(False)\nassert unreal.YorimichiLive.skate_place(unreal.Vector(30000,-71000,13200.5),0.)\nunreal.YorimichiLive.skate_input(unreal.Vector2D(),unreal.Vector2D(),True)')
 run('ride_start=p.get_actor_location()')
 samples=[]
 for _ in range(6):
  time.sleep(1); samples.append(run('print(unreal.YorimichiLive.skate_state())')['output'])
 assert 'bails=0' in samples[-1], samples[-1]
 assert 'retail=PhysicsGround' in samples[-1], samples[-1]
 (out/'ride.txt').write_text('\n'.join(samples))
 run('ride_end=p.get_actor_location()\ntravel=unreal.Vector2D(ride_end.x-ride_start.x,ride_end.y-ride_start.y).length()\nassert travel>500.,travel\nprint(\"ride displacement cm\",travel)')
 run('unreal.YorimichiLive.skate_input(unreal.Vector2D(),unreal.Vector2D(),False,True)')
 time.sleep(1)
 path=out/'riding.png'; path.unlink(missing_ok=True)
 run('unreal.LiveLibrary.screenshot('+repr(str(path))+')')
 for _ in range(50):
  if path.exists():break
  time.sleep(.1)
 assert path.exists(),path
 (out/'final-state.json').write_text(json.dumps(live.request('/state'),indent=2))
 (out/'passed.json').write_text(json.dumps({'level_loaded':True,'traces':len(reference),'screenshots':4,'ride_samples':len(samples)},indent=2))
finally:
 try:
  if p.poll() is None:live.request('/python',"unreal.SystemLibrary.quit_game(unreal.LiveLibrary.game_world(),None,unreal.QuitPreference.QUIT,False)",timeout=5)
 except Exception:pass
 try:p.wait(timeout=15)
 except subprocess.TimeoutExpired:reap(p)
 guards.close()
 log.close()
