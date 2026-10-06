"""Repeatable, uncapped GPU captures. Outputs are local to build/yorimichi/perf60.

python games/yorimichi/tools/benchmark.py NAME --commands 'sg.GlobalIlluminationQuality 2'
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import math
import statistics
import struct
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'world')); import yori  # noqa: E402
from contextlib import ExitStack
from atelier.safety.guard import attach as attach_memory_guard, reap
from atelier.safety.process import spawn_game
from atelier.safety.render_lock import render_lock
from atelier.safety.provenance import profile_from_log

ROOT = yori.GAME
PROJECT = ROOT / 'unreal'
ENGINE = Path(os.environ.get('UE_ROOT', '/Users/Shared/Epic Games/UE_5.8'))


def other_render_processes(ignore_pid=None):
    """Reject overlapping game/editor/art jobs instead of reporting their slowdown."""
    processes = subprocess.check_output(['ps','-axo','pid=,comm='],text=True)
    busy = []
    for line in processes.splitlines():
        fields = line.strip().split(None,1)
        if len(fields) != 2: continue
        pid, command = int(fields[0]), fields[1]
        if pid != ignore_pid and Path(command).name in (
                'UnrealEditor','UnrealEditor-Cmd','ShaderCompileWorker','blender','Blender'):
            busy.append({'pid':pid,'command':command})
    return busy


def summarize(path, warmup=300, phase=None):
    csv.field_size_limit(16_000_000)
    with path.open() as handle:
        rows = [r for r in csv.DictReader(handle)
                if (r.get('FrameTime') or '').replace('.', '', 1).isdigit()]
    rows = rows[warmup:]
    rows = [r for r in rows if float(r.get('JapanBenchmark/Measured') or 1) > .5
            and (phase is None or int(float(r.get('JapanBenchmark/Phase') or -1)) == phase)]
    if len(rows) < 100:
        raise RuntimeError('Capture contains too few measured frames')
    times = sorted(float(r['FrameTime']) for r in rows)
    def percentile(q):
        return times[min(len(times)-1, round((len(times)-1)*q))]
    medians = {}
    for key in rows[0]:
        if key and (key.startswith(('GPU/', 'DrawCall/', 'RHI/', 'JapanBenchmark/'))
                    or key in ('GameThreadTime', 'RenderThreadTime', 'FrameTime')):
            try:
                medians[key] = statistics.median(float(r[key]) for r in rows)
            except (ValueError, TypeError):
                pass
    return dict(frames=len(rows), median_ms=statistics.median(times), p95_ms=percentile(.95),
                p99_ms=percentile(.99), median_fps=1000/statistics.median(times),
                average_fps=1000/statistics.mean(times),
                percent_within_16_67_ms=100*sum(t <= 1000/60 for t in times)/len(times),
                medians=medians)


# Views that only move the camera, and views where the harness drives the character. A claim about
# traversal is only allowed for the second group, and only if the telemetry shows it happened.
STATIC_VIEWS = ('spawn', 'portrait', 'forest', 'coast', 'village', 'north_overview', 'park',
                'station', 'lake', 'harbor', 'arcade', 'plaza', 'city', 'custom')
MOVING_VIEWS = ('traverse', 'road_walk')
# 0.3 m/s. The scripted traverse deliberately stages walk, jog and run, and its walk is 85 cm/s, so
# a 1 m/s threshold failed a view that was moving exactly as intended. The idle soak that prompted
# all of this drifted below 1 cm/s, so this still separates travel from standing still.
MOVING_SPEED_CM_S = 30.
STALL_SECONDS = 2.


def route_report(path, view, warmup=300, threshold=MOVING_SPEED_CM_S):
    """What the character actually did, so `--seconds 600` cannot describe an idle camera.

    A ten-minute soak of this harness once reported a held 60 FPS while the rider had stopped after
    eleven seconds: the route was a 39 m stub and steering parked on its last waypoint. Distance,
    moving fraction, stalls and waypoint progress are now recorded, and a moving view whose rider
    stopped fails the run instead of publishing the timing.
    """
    csv.field_size_limit(16_000_000)
    with Path(path).open() as handle:
        rows = [r for r in csv.DictReader(handle)
                if (r.get('FrameTime') or '').replace('.', '', 1).isdigit()][warmup:]
    def series(key):
        out = []
        for row in rows:
            try: out.append(float(row.get(key, '')))
            except (TypeError, ValueError): out.append(None)
        return out
    seconds = series('JapanBenchmark/Seconds')
    speed = series('JapanBenchmark/Speed')
    x, y = series('JapanBenchmark/PlayerX'), series('JapanBenchmark/PlayerY')
    index, turns = series('JapanBenchmark/RoadIndex'), series('JapanBenchmark/RoadTurns')
    recoveries = series('JapanBenchmark/RoadRecoveries')
    samples = series('JapanBenchmark/RoadSamples')
    frames = [(t, v) for t, v in zip(seconds, speed) if t is not None and v is not None]
    distance = 0.
    cells = set()
    last = None
    for px, py in zip(x, y):
        if px is None or py is None:
            continue
        if last is not None:
            distance += math.dist((px, py), last)
        last = (px, py)
        cells.add((round(px/1000), round(py/1000)))     # 10 m cells visited
    moving = [1 for _, v in frames if v >= threshold]
    stalls, longest, run_start = [], 0., None
    for t, v in frames:
        if v < threshold:
            if run_start is None: run_start = t
        elif run_start is not None:
            length = t-run_start
            longest = max(longest, length)
            if length >= STALL_SECONDS: stalls.append([round(run_start, 2), round(length, 2)])
            run_start = None
    if run_start is not None and frames:
        length = frames[-1][0]-run_start
        longest = max(longest, length)
        if length >= STALL_SECONDS: stalls.append([round(run_start, 2), round(length, 2)])
    last_movement = max((t for t, v in frames if v >= threshold), default=None)
    report = dict(view=view,
                  classification='moving' if view in MOVING_VIEWS else 'static',
                  threshold_cm_s=threshold, frames=len(frames),
                  measured_seconds=round(frames[-1][0]-frames[0][0], 2) if frames else 0,
                  distance_m=round(distance/100, 1),
                  mean_speed_cm_s=round(sum(v for _, v in frames)/len(frames), 1) if frames else 0,
                  moving_fraction=round(len(moving)/len(frames), 4) if frames else 0,
                  last_movement_s=round(last_movement, 2) if last_movement is not None else None,
                  longest_stall_s=round(longest, 2), stalls_over_2s=stalls[:20],
                  stall_count=len(stalls),
                  cells_10m_visited=len(cells),
                  first_position=[round(x[0], 1), round(y[0], 1)] if x and x[0] is not None else None,
                  last_position=[round(last[0], 1), round(last[1], 1)] if last else None,
                  road_samples=int(max((v for v in samples if v is not None), default=0)),
                  road_index_range=[int(min((v for v in index if v is not None), default=0)),
                                    int(max((v for v in index if v is not None), default=0))],
                  road_turns=int(max((v for v in turns if v is not None), default=0)),
                  road_recoveries=int(max((v for v in recoveries if v is not None), default=0)))
    problems = []
    if report['classification'] == 'moving':
        if report['moving_fraction'] < .9:
            problems.append(f"the rider moved for only {report['moving_fraction']*100:.1f}% of the "
                            f"measured window; a traversal needs at least 90%")
        if stalls:
            problems.append(f'{len(stalls)} stall(s) longer than {STALL_SECONDS:g} s, '
                            f'longest {longest:.1f} s')
        if report['distance_m'] < 10:
            problems.append(f"only {report['distance_m']} m travelled")
        # A recovery is an annotated transfer, not travel. A couple over a long run is a rough
        # route; one every half minute means the route is unusable and the timing is not traversal.
        allowed = max(1, int(report['measured_seconds']//30))
        if report['road_recoveries'] > allowed:
            problems.append(f"{report['road_recoveries']} stall recoveries in "
                            f"{report['measured_seconds']:.0f} s: the route is not traversable")
    report['problems'] = problems
    report['passed'] = not problems
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('name')
    p.add_argument('--commands', default='')
    p.add_argument('--settings', default='')
    p.add_argument('--ini', action='append', default=[])
    p.add_argument('--launch-arg', action='append', default=[], help='Extra native startup argument')
    p.add_argument('--compare-before', default='', help='Runtime console commands for A in an ABABAB static-view test')
    p.add_argument('--compare-after', default='', help='Runtime console commands for B; 8s settling and screenshots are excluded')
    p.add_argument('--route',choices=('village','village_loop','mega','hidamari','arcade','plaza','harbor','harbor_pier','north'),default='village')
    p.add_argument('--view', choices=STATIC_VIEWS+MOVING_VIEWS, default='spawn')
    p.add_argument('--camera', type=float, nargs=6, metavar=('X','Y','Z','PITCH','YAW','FOV'),
                   help='With --view custom: fixed diagnostic camera in UE centimetres/degrees; player hidden')
    p.add_argument('--hide-hud', action='store_true', help='Clean review still; frame timings remain in CSV')
    p.add_argument('--wait-renderer', type=float, default=0,
                   help='Wait up to this many seconds for the shared render slot; default refuses immediately')
    p.add_argument('--seconds', type=float, default=25)
    p.add_argument('--road-index',type=int,default=0,help='Starting route sample for the road walk')
    p.add_argument('--boot', action='store_true', help='Use the original 900-frame boot capture')
    p.add_argument('--width', type=int, default=1920)
    p.add_argument('--height', type=int, default=1080)
    p.add_argument('--capped', action='store_true')
    p.add_argument('--desktop-fullscreen', action='store_true',
                   help='Measure the visible native 1440-high desktop viewport; width must match display aspect')
    args = p.parse_args()
    if args.desktop_fullscreen and (args.height != 1440 or args.boot):
        p.error('--desktop-fullscreen requires --height 1440 and a scene benchmark')
    if (args.view == 'custom') != (args.camera is not None):
        p.error('--view custom and --camera must be supplied together')
    if args.camera and args.boot:
        p.error('--camera requires the scene benchmark, not --boot')
    if args.camera and (not all(math.isfinite(v) for v in args.camera) or not 5 <= args.camera[5] <= 170):
        p.error('--camera values must be finite and FOV must be between 5 and 170 degrees')
    if not math.isfinite(args.wait_renderer) or not 0 <= args.wait_renderer <= 1800:
        p.error('--wait-renderer must be between 0 and 1800 seconds')
    if not 10 <= args.seconds <= 1800:
        p.error('--seconds must be between 10 and 1800, matching the native capture limits')
    if args.compare_after and args.view not in STATIC_VIEWS:
        p.error('paired comparisons require the same static camera; validate traversal separately')
    if args.compare_after and (args.boot or not args.compare_before):
        p.error('paired comparisons require explicit before commands and cannot use --boot')
    slot_deadline = time.monotonic()+args.wait_renderer
    busy = other_render_processes()
    if busy and args.wait_renderer:
        print('Waiting for the shared render slot; no Unreal process started.',flush=True)
    while busy and time.monotonic()<slot_deadline:
        time.sleep(min(1.,max(0.,slot_deadline-time.monotonic())))
        busy=other_render_processes()
    if busy: raise RuntimeError(f'Wait for other rendering jobs before benchmarking: {busy}')
    folder = yori.OUT / 'perf60' / args.name
    folder.mkdir(parents=True, exist_ok=False)
    cmd = [str(ENGINE/'Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor'),
           # macOS can clamp a window to the logical desktop size even when -resx/-resy
           # request 1440p. Offscreen uses the exact backbuffer size, independent of
           # Retina scaling or a remote display. The PNG check below remains mandatory.
           str(PROJECT/'Yorimichi.uproject'), '-game',
           '-fullscreen' if args.desktop_fullscreen else '-RenderOffscreen', '-ForceRes',
           f'-resx={args.width}', f'-resy={args.height}', '-fixedview',
           '-csvGpuStats', '-csvCompression=0', '-ExitAfterCsvProfiling', '-unattended',
           '-nosplash', '-stdout', '-abslog='+str(folder/'game.log')]
    if args.desktop_fullscreen:
        cmd += ['-desktopnative1440',
                '-ini:Engine:[/Script/Engine.Engine]:GameViewportClientClassName=/Script/Yorimichi.DesktopPreviewViewportClient']
    commands = ('t.MaxFPS 60' if args.capped else 't.MaxFPS 0')+',r.VSync 0'
    if args.desktop_fullscreen: commands += ',japan.PreviewInfo'
    if args.commands: commands += ','+args.commands
    cmd += ['-ExecCmds='+commands]
    if args.hide_hud: cmd += ['-benchmarkhidehud']
    if args.view == 'road_walk': cmd += ['-reviewroute='+args.route,'-benchmarkroadindex='+str(args.road_index)]
    if args.settings: cmd += ['-set='+args.settings]
    cmd += ['-ini:Engine:'+v for v in args.ini]
    cmd += args.launch_arg
    if args.camera:
        cmd += ['-benchmarkcamera='+','.join(str(v) for v in args.camera)]
    if args.compare_after:
        cmd += ['-benchmarkbefore='+args.compare_before,'-benchmarkafter='+args.compare_after]
    if args.boot:
        cmd += ['-csvCaptureFrames=900']
    else:
        cmd += ['-benchmarkview='+args.view, f'-benchmarkseconds={args.seconds}',
                '-benchmarkdir='+str(folder)]
    manifest = dict(command=cmd, commit=subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip(),
                    dirty=subprocess.check_output(['git','status','--porcelain'], text=True),
                    settings=(PROJECT/'Saved/settings.txt').read_text(),
                    engine_config=(PROJECT/'Config/DefaultEngine.ini').read_text(),
                    binary_sha256=hashlib.sha256((PROJECT/'Binaries/Mac/libUnrealEditor-Yorimichi.dylib').read_bytes()).hexdigest())
    inputs=[yori.OUT/'world.json',PROJECT/'Content/Japan/Materials/M_Foliage.uasset',
            PROJECT/'Content/Japan/Materials/MI_Bark.uasset',
            PROJECT/'Content/Japan/Materials/M_Painterly.uasset',
            PROJECT/'Content/Japan/Materials/M_Painted.uasset',
            PROJECT/'Content/Japan/Materials/M_ForestLakeWater.uasset',
            PROJECT/'Content/Japan/Materials/MI_Grass.uasset',
            PROJECT/'Content/Japan/Textures/T_grass.uasset',
            PROJECT/'Content/Japan/Maps/Slice.umap',
            PROJECT/'Content/Japan/Animation/CharacterCompression.uasset']
    inputs += sorted((PROJECT/'Content/Japan/Assets').glob('Village_*.uasset'))
    city=yori.OUT/'hidamari/city.json'
    if city.exists():
        inputs.append(city)
        inputs.append(PROJECT/'Content/Japan/Terrain.uasset')
        inputs+=sorted((PROJECT/'Content/Japan/Assets').glob('HD_*.uasset'))
    arcade_material=PROJECT/'Content/Japan/Materials/M_Arcade.uasset'
    if arcade_material.exists(): inputs.append(arcade_material)
    for name in ['M_ArcadePaving','M_PlazaPaving','M_PlazaWater','M_PondWater','M_Harbor','M_HarborWater','M_NorthMountains']:
        material=PROJECT/'Content/Japan/Materials'/f'{name}.uasset'
        if material.exists(): inputs.append(material)
    inputs+=sorted((PROJECT/'Content/Japan/Textures').glob('T_Arcade_*.uasset'))
    inputs+=sorted((PROJECT/'Content/Japan/Textures').glob('T_Harbor_*.uasset'))
    village_material=PROJECT/'Content/Japan/Materials/M_Village.uasset'
    if village_material.exists(): inputs.append(village_material)
    resident_material=PROJECT/'Content/Japan/Materials/M_VillageResident.uasset'
    if resident_material.exists(): inputs.append(resident_material)
    grass_material=PROJECT/'Content/Japan/Materials/M_Grass.uasset'
    if grass_material.exists(): inputs.append(grass_material)
    lod_manifest=yori.OUT/'foliage_lods/manifest.json'
    if lod_manifest.exists():
        inputs.append(lod_manifest)
        inputs += [PROJECT/'Content/Japan/Assets'/(name+'.uasset') for name in json.loads(lod_manifest.read_text())]
    inputs.extend(sorted((PROJECT/'Content/Experiments').rglob('*.uasset')))
    inputs.extend(sorted((PROJECT/'Content/Japan/FoliageCoverage').rglob('*.uasset')))
    inputs.extend(sorted((yori.OUT/'foliage_coverage').glob('*/manifest.json')))
    manifest['asset_sha256']={os.path.relpath(path, ROOT):hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
    (folder/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    overlap = {}
    # One render job at a time on this machine, and ownership of the child from the instant it
    # exists: anything that fails afterwards (the monitor, the deadline, an interrupt) still reaps it.
    with ExitStack() as stack:
        stack.enter_context(render_lock(f'benchmark {args.name} {args.view}',
                                       wait=max(0.,slot_deadline-time.monotonic())))
        log = stack.enter_context((folder/'stdout.log').open('w'))
        process = spawn_game(cmd, stdout=log, stderr=subprocess.STDOUT)
        stack.callback(reap, process)
        duration=args.seconds*6+40 if args.compare_after else args.seconds
        deadline = time.monotonic()+duration+300
        # The independent 10 GiB guard watches this exact child; losing its telemetry aborts the run.
        monitor = stack.enter_context(attach_memory_guard(process.pid, folder/'memory-health.json',
                                                          duration=duration+340))
        while process.poll() is None:
            for job in other_render_processes(process.pid): overlap[job['pid']] = job
            # The guard exits on its own the moment the child is gone, and it polls on a
            # one-second tick, so a dead monitor only means trouble while the child lives.
            if monitor is not None and monitor.poll() is not None and process.poll() is None:
                raise RuntimeError('Memory guard exited before the benchmark finished')
            if time.monotonic() >= deadline:
                raise RuntimeError('Benchmark timed out')
            try: process.wait(timeout=1)
            except subprocess.TimeoutExpired: pass
        if process.returncode: raise subprocess.CalledProcessError(process.returncode,cmd)
    if overlap:
        (folder/'overlapping-jobs.json').write_text(json.dumps(list(overlap.values()),indent=2)+'\n')
        raise RuntimeError('Other rendering jobs overlapped this run; capture is not a valid performance measurement')
    text = (folder/'game.log').read_text()
    if not args.boot:
        if 'BENCHMARK COMPLETE' not in text: raise RuntimeError('Benchmark did not complete')
        size=struct.unpack('>II',(folder/'view.png').read_bytes()[16:24])
        if size != (args.width,args.height): raise RuntimeError(f'Unexpected output resolution: {size}')
        if args.desktop_fullscreen and 'DESKTOP PREVIEW separate_scene_target=1' not in text:
            raise RuntimeError('Fullscreen scene target was not verified')
    match = re.search(r'Writing CSV to file : .*?([^/\n]+\.csv)', text)
    if not match: raise RuntimeError('Unreal did not finish a CSV capture')
    saved = (Path.home()/'Library/Application Support/Epic/UnrealEngine/5.8/Saved'
             if args.boot else PROJECT/'Saved')
    source = saved/'Profiling/CSV'/match[1]
    shutil.copyfile(source, folder/'frames.csv')
    warmup = 300 if args.boot else 3
    result = summarize(folder/'frames.csv', warmup)
    route = route_report(folder/'frames.csv', args.view, warmup)
    (folder/'route.json').write_text(json.dumps(route, indent=2)+'\n')
    result['route'] = {k: v for k, v in route.items() if k != 'stalls_over_2s'}
    result['profile'] = profile_from_log(folder/'game.log')
    result['output'] = [args.width, args.height]
    if args.compare_after:
        for phase in range(1,6):
            image=folder/f'phase_{phase}.png'
            if not image.exists() or struct.unpack('>II',image.read_bytes()[16:24]) != (args.width,args.height):
                raise RuntimeError(f'Comparison phase {phase} lacks a valid matching-resolution screenshot')
        phases=[summarize(folder/'frames.csv',warmup,phase=i) for i in range(6)]
        result['comparison']={
            'before':args.compare_before,'after':args.compare_after,
            'phase_median_ms':[p['median_ms'] for p in phases],
            'phase_p95_ms':[p['p95_ms'] for p in phases],
            'paired_savings_ms':[phases[i]['median_ms']-phases[i+1]['median_ms'] for i in (0,2,4)],
            'phase_scopes':[p['medians'] for p in phases]}
    (folder/'results.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('medians','profile')}, indent=2), flush=True)
    for key, value in sorted(result['medians'].items(), key=lambda item:-item[1]):
        if key.startswith('GPU/') and value > .1: print(f'{key}: {value:.2f} ms')
    if not route['passed']:
        raise RuntimeError('The run did not perform its intended movement: '+'; '.join(route['problems'])
                           +f". See {folder/'route.json'}")


if __name__ == '__main__':
    main()
