"""Capture opted-in cinematic shots from the current Unreal build.

Usage: python games/yorimichi/tools/capture.py SESSION [--shots NAME,NAME] [--scout] [--file shots.json]
Fixed 60 Hz simulation, real gameplay movement and unretouched PNG output.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import time
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'world'));import yori  # noqa: E402
ROOT=yori.GAME
PROJECT=ROOT/'unreal'
sys.path.insert(0,str(Path(__file__).resolve().parent))
from benchmark import other_render_processes
from contextlib import ExitStack
from atelier.safety.guard import attach as attach_memory_guard, reap
from atelier.safety.process import spawn_game
from atelier.safety.render_lock import render_lock


def read_telemetry(path, expected):
    """Reject truncated or unquoted state rows before reporting capture results."""
    with path.open(encoding='utf-8-sig', newline='') as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != expected:
        raise RuntimeError(f'Telemetry has {len(rows)} rows; expected {expected}')
    for index, row in enumerate(rows):
        if None in row or None in row.values():
            raise RuntimeError(f'Telemetry row {index} has the wrong number of CSV fields')
        try:
            frame = int(row['frame'])
        except (KeyError, ValueError):
            raise RuntimeError(f'Telemetry row {index} has no valid frame number') from None
        if frame != index:
            raise RuntimeError(f'Telemetry frame {frame} is out of order; expected {index}')
    return rows


def capture(session, name, spec, scout=False, *, allow_visual_overlap=False):
    busy=other_render_processes()
    if busy and not allow_visual_overlap: raise RuntimeError(f'Other render jobs active: {busy}')
    folder=yori.OUT/'captures'/session/name
    folder.mkdir(parents=True,exist_ok=False)
    spec=dict(spec)
    width,height=int(spec.get('width',1920)),int(spec.get('height',1080))
    fps=int(spec.get('capture_fps',60))
    ext=spec.get('format','png')
    if ext not in ('png','jpg'): raise ValueError('Expected png or jpg capture format')
    if fps not in (30,60) or width<640 or height<360 or width>3840 or height>2160:
        raise ValueError('Capture supports 30/60 FPS and resolutions up to native UHD')
    if scout:
        spec['seconds']=2/fps
        spec['move_start']=1000
        spec['events']=[e for e in spec['events'] if e['time']<0]
    config=folder/'shot.json'
    config.write_text(json.dumps(spec,indent=2)+'\n')
    engine=Path(os.environ.get('UE_ROOT','/Users/Shared/Epic Games/UE_5.8'))
    cmd=[str(engine/'Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor'),
         str(PROJECT/'Yorimichi.uproject'),'-game','-RenderOffscreen','-ForceRes',f'-resx={width}',f'-resy={height}',
         '-trailershot='+str(config),'-reviewdir='+str(folder),
         '-UseFixedTimeStep','-FPS=60','-unattended','-nosplash','-stdout',
         # Keep shader compilation inside the memory-guarded process.
         '-noshaderworker',
         # A shot may add preferences (the desktop profile, for instance). The console commands stay
         # a fixed reference unless the shot names its own: a fixed step at 100% internal is what
         # makes two clips comparable.
         '-set=show_fps=0'+(';'+spec['settings'] if spec.get('settings') else ''),
         '-ExecCmds='+spec.get('commands','r.DynamicRes.OperationMode 0,r.ScreenPercentage 100'),
         '-abslog='+str(folder/'game.log')]
    if spec.get('study_renderer'):
        cmd.append('-ini:Engine:[/Script/Engine.RendererSettings]:r.ForwardShading='+('True' if spec['study_renderer']=='forward' else 'False'))
    if spec.get('route'): cmd += ['-reviewroute='+spec['route']]
    if spec.get('rider'): cmd += ['-rider='+spec['rider']]
    saved=(PROJECT/'Saved/settings.txt').read_bytes()
    manifest={'command':cmd,'spec':spec,'git_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'native_binary_sha256':hashlib.sha256((PROJECT/'Binaries/Mac/libUnrealEditor-Yorimichi.dylib').read_bytes()).hexdigest(),
        'settings':saved.decode(),'fixed_step_video':True,'performance_evidence':False,'concurrent_render_processes':busy}
    inputs=[yori.OUT/'world.json',yori.OUT/'hidamari/city.json',PROJECT/'Content/Japan/Terrain.uasset',PROJECT/'Config/DefaultEngine.ini']
    inputs+=sorted((PROJECT/'Content/Japan/Assets').glob('HD_*.uasset'))
    inputs+=sorted((PROJECT/'Content/Japan/Materials').glob('*.uasset'))
    manifest['scene_sha256']={os.path.relpath(p,ROOT):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs if p.exists()}
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('CAPTURING',name,flush=True)
    # One render job at a time, and ownership of the child from the instant it exists: a monitor
    # that fails to start, an exception, an interrupt or the deadline all still reap it.
    with ExitStack() as stack:
        stack.enter_context(render_lock(f'trailer {session}/{name}'))
        log=stack.enter_context((folder/'stdout.log').open('w'))
        shot=spawn_game(cmd,stdout=log,stderr=subprocess.STDOUT)
        stack.callback(reap,shot)
        monitor=stack.enter_context(attach_memory_guard(shot.pid,folder/'memory-health.json',duration=1840))
        started=time.monotonic(); deadline=started+1800; next_progress=started+30
        while shot.poll() is None:
            now=time.monotonic()
            if now>=next_progress:
                saved_frames=sum(1 for _ in folder.glob(f'frame_*.{ext}'))
                print(f'CAPTURE PROGRESS {name}: {now-started:.0f}s elapsed, {saved_frames} frames saved',flush=True)
                next_progress=now+30
            if monitor is not None and monitor.poll() is not None and shot.poll() is None:
                raise RuntimeError('Memory guard exited before the shot finished')
            if time.monotonic()>deadline: raise TimeoutError('Trailer shot exceeded 1800 s')
            try: shot.wait(timeout=1)
            except subprocess.TimeoutExpired: pass
        if shot.returncode: raise subprocess.CalledProcessError(shot.returncode,cmd)
    assert (PROJECT/'Saved/settings.txt').read_bytes()==saved,'Saved settings changed'
    assert 'TRAILER SHOT COMPLETE' in (folder/'game.log').read_text()
    expected=round(spec['seconds']*fps)
    files=sorted(folder.glob(f'frame_*.{ext}'))
    assert len(files)==expected,(len(files),expected)
    for i,path in enumerate(files):
        assert path.name==f'frame_{i:05d}.{ext}'
        if ext=='png':
            with path.open('rb') as f: size=struct.unpack('>II',f.read(24)[16:24])
        else:
            from PIL import Image
            with Image.open(path) as image: size=image.size; image.verify()
        assert size==(width,height),size
    rows=read_telemetry(folder/'telemetry.csv',expected)
    report={'frames':expected,'resolution':[width,height],'fps':fps,'max_speed':max(float(r['speed']) for r in rows),
            'air_frames':sum(int(r['falling']) for r in rows),'clips':sorted(set(r['clip'] for r in rows)),
            'settings_unchanged':True,'actions':sorted(set(r.get('action','') for r in rows)),
            'sailing_frames':sum(int(r.get('sailing',0)) for r in rows),
            'zeppelin_stages':sorted(set(int(r.get('zeppelin_stage',-1)) for r in rows)),
            'passed':True}
    (folder/'checks.json').write_text(json.dumps(report,indent=2)+'\n')
    print('COMPLETE',name,json.dumps(report),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('session');p.add_argument('--shots',default='');p.add_argument('--scout',action='store_true')
    p.add_argument('--file',default=str(Path(__file__).with_name('shots.json')),help='shot list (the September trailer\'s by default)')
    a=p.parse_args()
    shots=json.loads(Path(a.file).read_text())
    for name in a.shots.split(',') if a.shots else shots:
        capture(a.session,name,shots[name],a.scout)
