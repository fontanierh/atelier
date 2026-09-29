"""Native views and collision probes of the lake, cabin and jetty."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / 'world')); import yori  # noqa: E402
import json,math,sys,subprocess
from pathlib import Path
ROOT = yori.GAME
def transform(x,y,z):
    a=math.radians(-135)
    return [-56+x*math.cos(a)-y*math.sin(a),215+x*math.sin(a)+y*math.cos(a),75.65+z]
def main():
    folder=yori.OUT/'forest_lake'/sys.argv[1];folder.mkdir(parents=True,exist_ok=False)
    shots=[dict(id=n,camera_position=p,camera_target=t,fov=f) for n,p,t,f in [
      ('hero',[-45,195,96],[-85,232,76.5],60),
      ('overview',[-110,222,83],[-76,233,76],72),
      ('cabin-front',transform(1,-11,2.0),transform(0,-1,1.9),72),
      ('cabin-rear',transform(1,11,2.0),transform(0,1,1.8),72),
      ('wood-store',transform(10,0,2.0),transform(3.0,0,1.3),72),
      ('cabin-side',transform(-9,0,2.0),transform(-2,0,1.4),72),
      ('jetty',transform(-8,-18,3.4),transform(0,-9,.4),75),
      ('boat-interior',transform(-5.5,-18,1.9),transform(-3.4,-15.5,-.25),70),
      ('rock-islet',[-111,238,78],[-109,246,76.5],68),
      ('shore',[-102,211,77.6],[-88,250,76.],75),
      ('trail',[15,229,73],[-12,235,74],75),
      ('aerial',[-93,221,129],[-90,235,75],75),
    ]]
    if len(sys.argv)>2:shots=[s for s in shots if s["id"] in sys.argv[2:]]
    probes=[]
    for i,(x,y,z) in enumerate([(-2,-4.65,.24),(0,-3.5,.43),(0,-5,.37),(0,-8,.37),(0,-11,.37),(-.5,-14,.37),(1,-14,.37)]):
        p=transform(x,y,z);probes.append(dict(id='deck-'+str(i),kind='entry_tread_top' if i==0 else 'walkable_landing',position=p,expected_z=p[2],tolerance_cm=4))
    spec=folder/'shots.json';spec.write_text(json.dumps(dict(shots=shots,probes=probes,settle_frames=90,initial_settle_frames=180),indent=2))
    engine=str(yori.REPO) and __import__('atelier.build',fromlist=['Context']).Context('yorimichi').unreal_app.as_posix()
    command=[engine,str(ROOT/'unreal/Yorimichi.uproject'),'-game','-RenderOffscreen','-ForceRes','-resx=1920','-resy=1080','-buildingreview='+str(spec),'-reviewdir='+str(folder),'-unattended','-nosplash','-stdout','-abslog='+str(folder/'game.log'),'-ExecCmds=r.DynamicRes.OperationMode 0,r.ScreenPercentage 100']
    subprocess.run([sys.executable,'-m','atelier.safety.guarded','--report',str(folder),'--',*command],check=True,env={**__import__('os').environ,'PYTHONPATH':str(yori.REPO/'platform/studio')})
    result=json.loads((folder/'completed.json').read_text());print(result);assert result['passed']
if __name__=='__main__':main()
