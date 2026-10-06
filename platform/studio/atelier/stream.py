"""Stream a game to browsers on other devices: `atelier stream <game> start|stop|status|build-web`.

The Mac runs the real Unreal game offscreen; Pixel Streaming sends H.264 video and Opus audio over WebRTC through a
local TURN relay, and the pages come from a loopback web server (platform/web/stream/server.cjs). Two pages:

- `/`       the game's touch page when it has one (game.toml [stream] touch_page): its own controls, sent as messages.
- `/play/`  the plain player: the far device's keyboard, mouse or controller are the game's input (a handheld PC with
            a controller, a friend's computer).

Other devices reach it through Tailscale Serve (HTTPS on :8443, the relay on :3479); `--local` skips that for tests on
this machine. Ports can be moved to run a second stream next to a live one: ATELIER_STREAM_HTTP_PORT,
ATELIER_STREAM_STREAMER_PORT, ATELIER_STREAM_TURN_PORT and ATELIER_STREAM_RELAY_MIN, plus ATELIER_STREAM_OUTPUT (another
folder) in the same checkout; stop and status need the same environment.
"""
import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import time
import tomllib
import urllib.request
from pathlib import Path

from . import paths
from .build import Context
from .safety import memory_guard
from .safety.memory_guard import usage
from .safety.process import spawn_game

WEB = paths.PLATFORM / 'web'
STREAM_WEB = WEB / 'stream'
PAGE_FILES = ('.html', '.css', '.webmanifest', '.png', '.svg', '.ico', '.jpg')


def ports():
    env = os.environ.get
    return {'http': int(env('ATELIER_STREAM_HTTP_PORT', '8080')), 'streamer': int(env('ATELIER_STREAM_STREAMER_PORT', '8888')),
            'turn': int(env('ATELIER_STREAM_TURN_PORT', '3478')), 'relay_min': int(env('ATELIER_STREAM_RELAY_MIN', '54000'))}


class Game:
    def __init__(self, game):
        self.id = game
        self.dir = paths.game_dir(game)
        self.manifest = tomllib.loads((self.dir / 'game.toml').read_text())
        self.config = self.manifest.get('stream', {})
        self.title = self.manifest.get('title', game)
        # ATELIER_STREAM_OUTPUT isolates a second stream in the same checkout (process state, credentials, logs, pages).
        self.out = Path(os.environ.get('ATELIER_STREAM_OUTPUT') or paths.build_dir(game) / 'stream').resolve()
        self.state_file = self.out / 'processes.json'
        self.touch_page = self.dir / self.config['touch_page'] if 'touch_page' in self.config else None

    def routes(self):
        """Extra static folders: {"map": "map"} serves build/<game>/map at /map."""
        return {route: str(paths.build_dir(self.id) / folder) for route, folder in self.config.get('routes', {}).items()}

    def processes(self):
        return json.loads(self.state_file.read_text()) if self.state_file.exists() else {}


def alive(record):
    try:
        command = subprocess.check_output(['ps', '-p', str(record['pid']), '-o', 'command='], text=True).strip()
        return record['marker'] in command and ('started' not in record or usage(record['pid']).started == record['started'])
    except (subprocess.CalledProcessError, ProcessLookupError):
        return False


def stop(g):
    state = g.processes()
    # The memory guard stays up until the game has exited, even if its render thread ignores a graceful shutdown.
    targets = {n: r for n, r in state.items() if n != 'memory_guard'}
    for record in targets.values():
        if alive(record):
            os.kill(record['pid'], signal.SIGTERM)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and any(alive(r) for r in targets.values()):
        time.sleep(.2)
    for record in targets.values():
        if alive(record):
            os.kill(record['pid'], signal.SIGKILL)
    guard = state.get('memory_guard')
    if guard and alive(guard):
        os.kill(guard['pid'], signal.SIGTERM)
    time.sleep(.2)
    remaining = {n: r for n, r in state.items() if alive(r)}
    g.state_file.write_text(json.dumps(remaining, indent=2) + '\n')
    if remaining:
        raise SystemExit('processes still stopping; check `status` before restarting')
    return 0


def status(g):
    state = {n: {**r, 'running': alive(r)} for n, r in g.processes().items()}
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{ports()["http"]}/health', timeout=3) as r:
            state['connection'] = json.load(r)
    except OSError:
        state['connection'] = 'offline'
    health = g.out / 'memory-health.json'
    if health.exists():
        memory = json.loads(health.read_text())
        game = state.get('game', {})
        memory['current'] = bool(game.get('running') and memory.get('pid') == game.get('pid') and time.time() - memory.get('time', 0) < 5)
        state['memory'] = memory
    print(json.dumps(state, indent=2))
    return 0


def npm_ready(install):
    if (WEB / 'node_modules' / '.bin' / 'esbuild').exists() and not install:
        return
    subprocess.run(['npm', 'ci', '--no-audit', '--no-fund'], cwd=WEB, check=True)


def bundle(entry, outfile):
    subprocess.run([str(WEB / 'node_modules' / '.bin' / 'esbuild'), str(entry), '--bundle', '--format=esm', f'--outfile={outfile}'],
                   cwd=WEB, check=True)


def build_web(g, install=False):
    """Bundle both pages into build/<game>/stream/web (installing platform/web's packages first when missing)."""
    npm_ready(install)
    web = g.out / 'web'
    if web.exists():
        shutil.rmtree(web)
    (web / 'play').mkdir(parents=True)
    bundle(STREAM_WEB / 'player.js', web / 'play' / 'player.js')
    (web / 'play' / 'player.html').write_text((STREAM_WEB / 'player.html').read_text().replace('{{title}}', g.title))
    os.replace(web / 'play' / 'player.html', web / 'play' / 'index.html')
    shutil.copy2(STREAM_WEB / 'player.css', web / 'play' / 'player.css')
    if g.touch_page:
        bundle(g.touch_page / 'client.js', web / 'client.js')
        for f in g.touch_page.iterdir():
            if f.suffix in PAGE_FILES:
                shutil.copy2(f, web / f.name)
    else:
        for f in (web / 'play').iterdir():
            shutil.copy2(f, web / f.name)
    print('pages built in', web)
    return 0


def start(g, local=False):
    if any(alive(r) for r in g.processes().values()):
        raise SystemExit('the stream is already running; `status` or `stop` first')
    running = subprocess.check_output(['ps', '-axo', 'pid=,command='], text=True)
    if any('UnrealEditor.app/Contents/MacOS/UnrealEditor' in line and '-game' in line for line in running.splitlines()):
        raise SystemExit('another Unreal game is running; stop it before streaming')
    if not (g.out / 'web' / 'play' / 'player.js').exists():
        build_web(g)
    turn = shutil.which('turnserver')
    if not turn:
        raise SystemExit('the TURN relay is missing: brew install coturn')
    p = ports()
    ctx = Context(g.id)
    credential = secrets.token_hex(24)
    relay_host = '127.0.0.1' if local else subprocess.check_output(['tailscale', 'ip', '-4'], text=True).strip()
    peer = {'iceServers': [{'urls': [f'turn:{relay_host}:3479?transport=tcp'], 'username': 'atelier', 'credential': credential}],
            'iceTransportPolicy': 'relay'}
    (g.out / 'peer-options.json').write_text(json.dumps(peer)); os.chmod(g.out / 'peer-options.json', 0o600)
    config = g.out / 'turn.conf'
    config.write_text(f'''listening-ip=127.0.0.1
relay-ip=127.0.0.1
relay-threads=2
allow-loopback-peers
denied-peer-ip=0.0.0.0-255.255.255.255
allowed-peer-ip=127.0.0.1
listening-port={p["turn"]}
min-port={p["relay_min"]}
max-port={p["relay_min"] + 100}
realm=atelier
lt-cred-mech
user=atelier:{credential}
fingerprint
no-tls
no-dtls
no-cli
no-multicast-peers
no-tcp-relay
no-stun-backward-compatibility
log-file={g.out}/turn-detail.log
pidfile={g.out}/turn.pid
''')
    os.chmod(config, 0o600)
    state = {}

    def spawn(name, args, marker, env=None):
        with (g.out / f'{name}.log').open('ab') as log:
            launch = spawn_game if name == 'game' else subprocess.Popen
            proc = launch(args, cwd=paths.REPO, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                          start_new_session=True, env=env)
        state[name] = {'pid': proc.pid, 'marker': marker, 'started': usage(proc.pid).started}
        g.state_file.write_text(json.dumps(state, indent=2) + '\n')
        return proc

    relay = spawn('turn', [turn, '-c', str(config)], str(config))
    time.sleep(.5)
    if relay.poll() is not None:
        raise SystemExit('the TURN relay failed; see turn.log')
    server_js = STREAM_WEB / 'server.cjs'
    env = {**os.environ, 'ATELIER_STREAM_OUTPUT': str(g.out), 'ATELIER_STREAM_HTTP_PORT': str(p['http']),
           'ATELIER_STREAM_STREAMER_PORT': str(p['streamer']), 'ATELIER_STREAM_TURN_PORT': str(p['turn']),
           'ATELIER_STREAM_ROUTES': json.dumps(g.routes())}
    server = spawn('signalling', [shutil.which('node'), str(server_js)], str(server_js), env=env)
    time.sleep(.5)
    if server.poll() is not None:
        raise SystemExit('the stream server failed; see signalling.log')
    video = g.config.get('video', {})
    width, height, fps = video.get('width', 1280), video.get('height', 720), video.get('fps', 60)
    args = [str(ctx.unreal_app), str(ctx.uproject), '-game', '-RenderOffscreen', '-ForceRes', f'-ResX={width}', f'-ResY={height}',
            '-AtelierStream', f'-PixelStreamingConnectionURL=ws://127.0.0.1:{p["streamer"]}', '-PixelStreamingEncoderCodec=H264',
            '-PixelStreamingUseMediaCapture=false', '-PixelStreamingEncoderKeyframeInterval=120',
            f'-PixelStreamingWebRTCFps={fps}', '-PixelStreamingWebRTCStartBitrate=3000000',
            '-PixelStreamingWebRTCMinBitrate=500000', '-PixelStreamingWebRTCMaxBitrate=8000000',
            '-PixelStreamingWebRTCDisableReceiveAudio', '-PixelStreamingWebRTCDisableReceiveVideo',
            # Metal's per-frame GPU-capture labels accumulate in a development build over a long stream.
            '-AudioMixer', '-Unattended', '-NoSplash', '-stdout',
            f'-ExecCmds=t.MaxFPS {fps},r.RHISetGPUCaptureOptions 0', f'-abslog={g.out}/game.log', *g.config.get('args', [])]
    game = spawn('game', args, '-AtelierStream', env=ctx.env())
    guard = spawn('memory_guard', [sys.executable, memory_guard.__file__, '--pid', str(game.pid), '--expected-start',
                                   str(state['game']['started']), '--limit-gib', '10', '--report', str(g.out / 'memory-health.json')],
                  memory_guard.__file__)
    time.sleep(.3)
    if guard.poll() is not None:
        game.kill()
        raise SystemExit('memory protection did not start; the game was stopped')
    spawn('awake', ['/usr/bin/caffeinate', '-di', '-w', str(game.pid)], f'-w {game.pid}')
    if not local:
        subprocess.run(['tailscale', 'serve', '--bg', '--yes', '--tcp=3479', f'tcp://127.0.0.1:{p["turn"]}'], check=True, timeout=30)
        subprocess.run(['tailscale', 'serve', '--bg', '--yes', '--https=8443', f'http://127.0.0.1:{p["http"]}'], check=True, timeout=30)
    where = f'http://127.0.0.1:{p["http"]}' if local else 'https://<this Mac>.<tailnet>.ts.net:8443'
    print(f'starting {g.title}; `atelier stream {g.id} status` shows when it is ready. Pages: {where}/ and {where}/play/. Logs: {g.out}')
    return 0


def main(game, action, local=False, install=False):
    g = Game(game)
    g.out.mkdir(parents=True, exist_ok=True)
    if action == 'start':
        return start(g, local)
    if action == 'stop':
        return stop(g)
    if action == 'build-web':
        return build_web(g, install)
    return status(g)
