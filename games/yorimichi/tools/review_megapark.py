"""Capture and smoke-test the native Super Ultra Mega Park under the render guard.

Run with project Python after world.megapark and unreal.megapark are built. By default it reviews the standalone level;
--island reviews the park where it sits in the island (docs/MEGAPARK.md, "Placement"), with views of it from around
the island in the game's own look (default settings). The worker owns and quits only the game process it launches.
"""
from pathlib import Path
from contextlib import ExitStack
import argparse,json,subprocess,sys,time
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'world'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'world'/'regions'))
import yori
from megapark import placement
from atelier.build import Context
from atelier.safety import guarded
from atelier.safety.guard import attach as attach_memory_guard, reap
from atelier import live
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
parser.add_argument('--port',type=int,default=8839)
parser.add_argument('--island',action='store_true',help='review the park placed in the island')
args=parser.parse_args()
live.URL=f'http://127.0.0.1:{args.port}'
ctx=Context('yorimichi'); root=yori.REPO; out=yori.OUT/('megapark/island-review' if args.island else 'megapark/play-review'); out.mkdir(parents=True,exist_ok=True)
if not args.worker:
 sys.exit(guarded.run([sys.executable,str(Path(__file__).resolve()),'--worker','--port',str(args.port)]+(['--island'] if args.island else []),out/'guard',timeout=600 if args.island else 240,purpose='Super Ultra Mega Park review',kind='game'))
def to_ue(native):
 """Native (x, y up, z) metres -> Unreal cm where the park is being reviewed."""
 if args.island:return placement.to_unreal(native).tolist()
 x,y,z=native;return [x*100.,z*100.,y*100.]
def island(x,y,z):
 return (x*100.,-y*100.,z*100.)
# name, camera, target (Unreal cm), field of view
SHOTS=[('overview',(62000,-37000,39000),(32500,-65500,10500),65.),('upper',(33000,-73500,14800),(32200,-63500,9100),65.),('lower',(37000,-67000,15000),(35000,-64500,9700),65.)]
if args.island:
 # Island metres. A camera given as ('ground', x, y, h) sits h metres above the highest surface under it.
 top=placement.native_to_island([330,132.006,-710]); deck=island(top[0],top[1],top[2]+1.7)
 park=island(-150,1300,110); summit=island(550,1930,480)
 zone={z['key']:z for z in json.loads((yori.OUT/'map'/'map.json').read_text())['zones']}
 def eye(key):return island(zone[key]['x'],zone[key]['y'],zone[key]['z']+1.7)
 SHOTS=[('overview',island(-560,1120,280),island(-130,1320,105),65.),
        ('overview_east',island(260,1480,300),island(-150,1300,100),65.),
        ('overview_south',island(-120,800,300),island(-150,1300,100),65.),
        ('deck_volcano',deck,summit,70.),
        ('deck_northwest',deck,island(-900,2150,20),70.),
        ('deck_ridge',deck,island(-700,1230,60),70.),
        ('from_west',('ground',-520,1330,25),park,60.),
        ('from_volcano_flank',('ground',140,1560,30),park,60.),
        ('from_south',('ground',-140,860,20),park,60.),
        ('lake_volcano',eye('forest_lake'),summit,70.),
        ('lake_park',eye('forest_lake'),park,45.),
        ('air_station_park',eye('zeppelin_forest'),park,45.),
        ('mini_mega_park',eye('mega'),park,45.),
        ('temple_park',eye('temple'),park,45.),
        ('foothills_park',eye('foothills'),park,45.),
        ('plaza_volcano',eye('plaza'),summit,70.)]
(out/'passed.json').unlink(missing_ok=True)
log=(out/'game.log').open('w')
cmd=[str(ctx.unreal_app),str(ctx.uproject),'/Game/Japan/Maps/Slice' if args.island else '/Game/MegaPark/Maps/SuperUltraMegaPark','-game','-windowed','-resx=1600','-resy=1000','-nosplash','-stdout',f'-liveport={args.port}','-ini:Engine:[HTTPServer.Listeners]:DefaultBindAddress=localhost','-preferencesfile='+str(out/'settings.txt')]+([] if args.island else ['-set=painterly=0;toon=0;outline=0;wind=0;exposure=0;saturation=1'])+['-ExecCmds=t.MaxFPS 60,r.RHISetGPUCaptureOptions 0,DisableAllScreenMessages']
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
 monitor=guards.enter_context(attach_memory_guard(p.pid,out/'memory-health.json',duration=540 if args.island else 240))
 deadline=time.monotonic()+(300 if args.island else 150)
 while time.monotonic()<deadline:
  if p.poll() is not None:raise RuntimeError('Game exited '+str(p.returncode))
  try:
   state=live.request('/state',timeout=1); break
  except OSError:time.sleep(1)
 else:raise RuntimeError('Bridge startup timed out')
 (out/'initial-state.json').write_text(json.dumps(state,indent=2))
 run("import unreal, json, math\nw=unreal.LiveLibrary.game_world()\np=unreal.LiveLibrary.player()\nprint(w.get_name(),p.get_name(),unreal.YorimichiLive.skate_state())\nassert len(unreal.GameplayStatics.get_all_actors_of_class(w,unreal.SuperUltraMegaPark))==1\nprint('one park')"+("" if args.island else "\nassert len(unreal.GameplayStatics.get_all_actors_of_class(w,unreal.MegaParkWorld))==1\nassert len(unreal.GameplayStatics.get_all_actors_of_class(w,unreal.LeafStorm))==0\nprint('level services and no leaf storm passed')"))
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
 expected=[to_ue(r) for r in reference]
 run('traces=[]\nfor x,y,z in '+repr(expected)+":\n point=unreal.LiveLibrary.ground_at(unreal.Vector(x,y,z+1000))\n error=abs(point.z-z)\n traces.append([x,y,z/100,point.z/100,error])\n assert error<.1, traces[-1]\nprint(json.dumps(traces))")
 (out/'traces.json').write_text(run('print(json.dumps(traces))')['output'])
 # Runtime camera, independent of the player camera boom.
 run('unreal.YorimichiLive.film_hud(True)')
 for i,(name,at,target,fov) in enumerate(SHOTS):
  if at[0]=='ground':
   # ground_at searches 20 m above to 60 m below its point: step down until it lands on something.
   _,gx,gy,h=at; x,y=gx*100.,-gy*100.
   z=float(run(f'z=None\nfor s in range(120000,-6000,-7000):\n g=unreal.LiveLibrary.ground_at(unreal.Vector({x},{y},s))\n if g.z!=s:z=g.z;break\nassert z is not None\nprint(z)')['output'].split()[-1])+h*100.
  else:x,y,z=at
  tx,ty,tz=target
  run(f'assert unreal.MegaParkValidation.review_camera(unreal.Vector({x},{y},{z}),unreal.Vector({tx},{ty},{tz}),{fov})')
  # The island streams textures and builds distance fields for a while after loading.
  time.sleep((20 if i==0 else 5) if args.island else 2)
  path=out/(name+'.png'); path.unlink(missing_ok=True); run('unreal.LiveLibrary.screenshot('+repr(str(path))+')')
  for _ in range(300):
   if path.exists():break
   time.sleep(.1)
  assert path.exists(),path
 # Ride along the upper deck. Reaching the descending route requires steering
 # through its original U-turn; a straight input would go over the side.
 start=to_ue([300,132.005,-710])
 run('unreal.MegaParkValidation.restore_player_camera()\nunreal.YorimichiLive.film_hud(False)\nassert unreal.YorimichiLive.skate_place(unreal.Vector(%r,%r,%r),%r)\nunreal.YorimichiLive.skate_input(unreal.Vector2D(),unreal.Vector2D(),True)'%(*start,placement.unreal_transform()['yaw_deg'] if args.island else 0.))
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
 for _ in range(300):
  if path.exists():break
  time.sleep(.1)
 assert path.exists(),path
 (out/'final-state.json').write_text(json.dumps(live.request('/state'),indent=2))
 (out/'passed.json').write_text(json.dumps({'level_loaded':True,'traces':len(reference),'screenshots':len(SHOTS)+1,'ride_samples':len(samples)},indent=2))
finally:
 try:
  if p.poll() is None:live.request('/python',"unreal.SystemLibrary.quit_game(unreal.LiveLibrary.game_world(),None,unreal.QuitPreference.QUIT,False)",timeout=5)
 except Exception:pass
 try:p.wait(timeout=15)
 except subprocess.TimeoutExpired:reap(p)
 guards.close()
 log.close()
