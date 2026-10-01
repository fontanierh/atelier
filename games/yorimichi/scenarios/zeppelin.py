"""Fresh native station captures and actual pawn collision probes."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / 'world')); import yori  # noqa: E402
import sys,json,subprocess
from pathlib import Path
ROOT = yori.GAME
from zeppelin.layout import STATIONS
def main():
    folder=yori.OUT/'zeppelin'/sys.argv[1];folder.mkdir(parents=True,exist_ok=False)
    index=int(sys.argv[2]) if len(sys.argv)>2 else 0;s=STATIONS[index];ox,oy,oz=s['origin']
    def p(x,y,z):return [ox+x,oy+y,oz+z]
    shots=[]
    for name,eye,aim,fov in [
      ('hero',(-19,-20,11),(1,1,6),68),
      ('approach',(-3,-14,2.2),(-3,-1,2.8),74),
      ('hut-front',(-6,-10,2.1),(-6,-2,1.6),65),
      ('hut-rear',(-6,7,3),(-6,0,1.8),72),
      ('hut-west',(-15,-1,2.2),(-7,-1,1.5),75),
      ('hut-east',(0,-7,3),(-3,-1,1.8),75),
      ('stairs',(8,-10,2.6),(6,-3,1.4),70),
      ('pier',(4,-2,3.7),(6,3.5,2.5),76),
      ('ship-side',(6,-8,7.3),(6,4,6.7),84),
      ('rotors-front',(23,4,8),(8,4,7.8),64),
      ('deck',(10,1.8,4.7),(5,4,2.5),80),
      ('supports',(12,-6,1.4),(6,-1,.9),75),
      ('backdrop',(17,15,10),(0,0,3.8),76)]:shots.append(dict(id=name,camera_position=p(*eye),camera_target=p(*aim),fov=fov))
    probes=[]
    for k in range(10):
        z=oz+(k+1)*.165;probes.append(dict(id=f'step-{k}',kind='entry_tread_top',position=p(6,-7.9+k*.49,(k+1)*.165),expected_z=z,tolerance_cm=4))
    for x,y,z in [(6,-3.15,1.65),(6,-2,1.65),(6,.55,1.65),(6,1.7,1.65),(-6,-4.9,.11),(6,-8.6,.03)]:probes.append(dict(id=f'landing-{len(probes)}',kind='walkable_landing',position=p(x,y,z),expected_z=oz+z,tolerance_cm=4))
    if '--visual' in sys.argv:shots=[s for s in shots if s['id'] in ('hero','rotors-front','backdrop')];probes=[]
    spec=folder/'shots.json';spec.write_text(json.dumps(dict(shots=shots,probes=probes,settle_frames=90,initial_settle_frames=180),indent=2))
    commands='r.DynamicRes.OperationMode 0,r.ScreenPercentage 100'
    if '--unlit' in sys.argv:commands+=',viewmode unlit'
    if '--cvars' in sys.argv:commands+=','+sys.argv[sys.argv.index('--cvars')+1]
    cmd=[str(yori.REPO) and __import__('atelier.build',fromlist=['Context']).Context('yorimichi').unreal_app.as_posix(),str(ROOT/'unreal/Yorimichi.uproject'),'-game','-RenderOffscreen','-ForceRes','-resx=1920','-resy=1080',f'-zeppelindock={index}','-buildingreview='+str(spec),'-reviewdir='+str(folder),'-unattended','-nosplash','-stdout','-abslog='+str(folder/'game.log'),'-ExecCmds='+commands]
    subprocess.run([sys.executable,'-m','atelier.safety.guarded','--report',str(folder),'--',*cmd],check=True,env={**__import__('os').environ,'PYTHONPATH':str(yori.REPO/'platform/studio')})
    result=json.loads((folder/'completed.json').read_text());print('PASS',result['passed'],result['errors']);assert result['passed']
    log=(folder/'game.log').read_text()
    assert 'Failed to compile Material' not in log, 'A material fell back to the checkerboard shader'
    assert 'ZEPPELIN ready=1' in log, 'Zeppelin service did not load'
if __name__=='__main__':main()
