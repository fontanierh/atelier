#!/usr/bin/env python3
"""Private phone play: python games/yorimichi/streaming/run.py start|stop|status|build-web."""
import argparse,json,os,shutil,signal,subprocess,time,urllib.request,secrets,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(ROOT/'world'));import yori  # noqa: E402
from atelier.safety.memory_guard import usage  # noqa: E402
import atelier.safety.memory_guard as _guard  # noqa: E402
OUT=Path(os.environ.get('YORIMICHI_STREAM_OUTPUT',str(yori.OUT/'pixel-streaming'))).resolve()
STATE=OUT/'processes.json'
PROJECT=ROOT/'unreal/Yorimichi.uproject'
ENGINE=Path(os.environ.get('UE_ROOT','/Users/Shared/Epic Games/UE_5.8'))
# Local ports; override them (and pass the same environment to server.cjs) to run a second, private test stream.
HTTP_PORT=int(os.environ.get('YORIMICHI_HTTP_PORT','8080'));STREAMER_PORT=int(os.environ.get('YORIMICHI_STREAMER_PORT','8888'))
TURN_PORT=int(os.environ.get('YORIMICHI_TURN_PORT','3478'));RELAY_MIN=int(os.environ.get('YORIMICHI_RELAY_MIN','54000'))

def processes():
    return json.loads(STATE.read_text()) if STATE.exists() else {}

def alive(record):
    try:
        command=subprocess.check_output(['ps','-p',str(record['pid']),'-o','command='],text=True).strip()
        return record['marker'] in command and ('started' not in record or usage(record['pid']).started==record['started'])
    except (subprocess.CalledProcessError,ProcessLookupError):return False

def stop():
    state=processes()
    # Keep the independent guard alive until the game has exited, even if its
    # render thread ignores graceful shutdown.
    targets={n:r for n,r in state.items() if n!='memory_guard'}
    for record in targets.values():
        if alive(record):os.kill(record['pid'],signal.SIGTERM)
    deadline=time.monotonic()+5
    while time.monotonic()<deadline and any(alive(r) for r in targets.values()):time.sleep(.2)
    for record in targets.values():
        if alive(record):os.kill(record['pid'],signal.SIGKILL)
    guard=state.get('memory_guard')
    if guard and alive(guard):os.kill(guard['pid'],signal.SIGTERM)
    time.sleep(.2)
    remaining={n:r for n,r in state.items() if alive(r)}
    STATE.write_text(json.dumps(remaining,indent=2)+'\n')
    if remaining:raise RuntimeError('Processes still stopping; inspect status before restarting')

def status():
    state={n:{**r,'running':alive(r)} for n,r in processes().items()}
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{HTTP_PORT}/health',timeout=3) as r:state['connection']=json.load(r)
    except OSError:state['connection']='offline'
    health=OUT/'memory-health.json'
    if health.exists():
        memory=json.loads(health.read_text())
        game=state.get('game',{})
        memory['current']=bool(game.get('running') and memory.get('pid')==game.get('pid') and time.time()-memory.get('time',0)<5)
        state['memory']=memory
    print(json.dumps(state,indent=2))

def build_web():
    subprocess.run(['npm','ci','--no-audit','--no-fund'],cwd=HERE,check=True)
    subprocess.run(['npm','run','build','--',f'--outfile={OUT}/web/client.js'],cwd=HERE,check=True)
    for name in ['index.html','style.css','manifest.webmanifest','icon-192.png','icon-512.png']:shutil.copy2(HERE/name,OUT/'web'/name)

def start(local=False):
    if any(alive(r) for r in processes().values()):raise RuntimeError('Stream already running; use status or stop first')
    running=subprocess.check_output(['ps','-axo','pid=,command='],text=True)
    if any('UnrealEditor.app/Contents/MacOS/UnrealEditor' in line and '-game' in line for line in running.splitlines()):
        raise RuntimeError('Another Unreal game is running; stop it before launching a stream')
    if not (OUT/'web/client.js').exists():build_web()
    turn=shutil.which('turnserver')
    if not turn:raise RuntimeError('Install coturn first: brew install coturn')
    tail_ip=subprocess.check_output(['tailscale','ip','-4'],text=True).strip()
    credential=secrets.token_hex(24)
    peer={'iceServers':[{'urls':[f'turn:{tail_ip}:3479?transport=tcp'],'username':'yorimichi','credential':credential}],'iceTransportPolicy':'relay'}
    (OUT/'peer-options.json').write_text(json.dumps(peer));os.chmod(OUT/'peer-options.json',0o600)
    config=OUT/'turn.conf'
    config.write_text(f'''listening-ip=127.0.0.1
relay-ip=127.0.0.1
relay-threads=2
allow-loopback-peers
denied-peer-ip=0.0.0.0-255.255.255.255
allowed-peer-ip=127.0.0.1
listening-port={TURN_PORT}
min-port={RELAY_MIN}
max-port={RELAY_MIN+100}
realm=yorimichi
lt-cred-mech
user=yorimichi:{credential}
fingerprint
no-tls
no-dtls
no-cli
no-multicast-peers
no-tcp-relay
no-stun-backward-compatibility
log-file={OUT}/turn-detail.log
pidfile={OUT}/turn.pid
''')
    os.chmod(config,0o600)
    state={}
    def spawn(name,args,marker):
        with (OUT/f'{name}.log').open('ab') as log:
            p=subprocess.Popen(args,cwd=yori.REPO,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        state[name]={'pid':p.pid,'marker':marker,'started':usage(p.pid).started};STATE.write_text(json.dumps(state,indent=2)+'\n');return p
    relay=spawn('turn',[turn,'-c',str(config)],str(config))
    time.sleep(.5)
    if relay.poll() is not None:raise RuntimeError('TURN failed; inspect turn.log')
    server=spawn('signalling',[shutil.which('node'),str(HERE/'server.cjs')],str(HERE/'server.cjs'))
    time.sleep(.5)
    if server.poll() is not None:raise RuntimeError('Signalling failed; inspect signalling.log')
    args=[str(ENGINE/'Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor'),str(PROJECT),
          '-game','-RenderOffscreen','-ForceRes','-ResX=1280','-ResY=720','-phonestreaming',
          f'-PixelStreamingConnectionURL=ws://127.0.0.1:{STREAMER_PORT}','-PixelStreamingEncoderCodec=H264',
          '-PixelStreamingUseMediaCapture=false','-PixelStreamingEncoderKeyframeInterval=120',
          '-PixelStreamingWebRTCFps=60','-PixelStreamingWebRTCStartBitrate=3000000',
          '-PixelStreamingWebRTCMinBitrate=500000','-PixelStreamingWebRTCMaxBitrate=8000000',
          '-PixelStreamingWebRTCDisableReceiveAudio','-PixelStreamingWebRTCDisableReceiveVideo',
          # Metal's per-frame diagnostic encoder labels accumulate in this UE
          # development build. Disable GPU-capture labels for the long-lived
          # phone stream; lighting, resolution and frame timing are unchanged.
          '-AudioMixer','-Unattended','-NoSplash','-stdout',
          '-ExecCmds=t.MaxFPS 60,r.RHISetGPUCaptureOptions 0',f'-abslog={OUT}/game.log']
    game=spawn('game',args,'-phonestreaming')
    guard=spawn('memory_guard',[sys.executable,_guard.__file__,'--pid',str(game.pid),
          '--expected-start',str(state['game']['started']),'--limit-gib','10','--report',str(OUT/'memory-health.json')],_guard.__file__)
    time.sleep(.3)
    if guard.poll() is not None:
        game.kill()
        raise RuntimeError('Memory protection did not start; game stopped')
    spawn('awake',['/usr/bin/caffeinate','-di','-w',str(game.pid)],f'-w {game.pid}')
    if not local:
        subprocess.run(['tailscale','serve','--bg','--yes','--tcp=3479',f'tcp://127.0.0.1:{TURN_PORT}'],check=True,timeout=30)
        subprocess.run(['tailscale','serve','--bg','--yes','--https=8443',f'http://127.0.0.1:{HTTP_PORT}'],check=True,timeout=30)
    print('Starting the game; use status to check readiness. Logs:',OUT)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['start','stop','status','build-web']);p.add_argument('--local',action='store_true');a=p.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    if a.action=='start':start(a.local)
    elif a.action=='stop':stop()
    elif a.action=='build-web':build_web()
    else:status()
