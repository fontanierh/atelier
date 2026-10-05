"""macOS login and crash supervision for board transports, independently of agents."""
import fcntl
import os
import plistlib
import subprocess
import sys
import time
from pathlib import Path

from . import board, paths


def label(agent):
    return 'com.atelier.board.' + board.agent_name(agent)


def configuration(args):
    board.notify_command(args.notify)
    folder = board.root() / 'board-subscribers'
    folder.mkdir(exist_ok=True)
    argv = [sys.executable, '-m', 'atelier.cli', 'board', 'subscribe', '--agent', args.agent,
            '--notify', args.notify, '--checkout', str(Path(args.checkout).resolve()), '--managed']
    if args.addressed_only:
        argv.append('--addressed-only')
    return {'Label': label(args.agent), 'ProgramArguments': argv, 'WorkingDirectory': str(paths.REPO),
            'EnvironmentVariables': {'PYTHONPATH': str(paths.STUDIO), 'ATELIER_CACHE': str(board.root()),
                                     'PATH': os.environ.get('PATH', '/usr/bin:/bin')}, 'RunAtLoad': True,
            'KeepAlive': True, 'ThrottleInterval': 5,
            'StandardOutPath': str(folder / f'{args.agent}.log'),
            'StandardErrorPath': str(folder / f'{args.agent}.log')}


def command(argv):
    return subprocess.run(argv, capture_output=True, text=True, timeout=8)


def install(args):
    if sys.platform != 'darwin':
        raise ValueError('board supervise currently uses macOS launchd; use your service manager on Linux')
    config = configuration(args)
    path = Path.home() / 'Library/LaunchAgents' / (config['Label'] + '.plist')
    domain = f'gui/{os.getuid()}'
    current = command(['launchctl', 'print', domain + '/' + config['Label']])
    if current.returncode == 0:
        if not path.exists() or plistlib.loads(path.read_bytes()) != config:
            raise ValueError('Listener service configuration differs; retire that listener before replacing it')
        print('Listener is already supervised by ' + config['Label'])
        return 0
    # Cooperatively replace a legacy one-shot wait, preserving its cursor/history.
    with board.database() as db:
        db.execute('INSERT INTO subscribers (agent,supervised,stop) VALUES (?,?,1) '
                   'ON CONFLICT(agent) DO UPDATE SET supervised=excluded.supervised,stop=1',
                   (args.agent, config['Label']))
    deadline = time.monotonic() + 10
    while True:
        with board.database() as db:
            row = db.execute('SELECT pid FROM subscribers WHERE agent=?', (args.agent,)).fetchone()
        if not row or not row['pid']:
            break
        # A crashed fallback can leave a stale PID. Only a free owner lock proves
        # it is absent; never signal a PID or confuse PID reuse with a listener.
        with (board.root() / 'board-subscribers' / f'{args.agent}.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                pass
            else:
                with board.database() as db:
                    db.execute('UPDATE subscribers SET pid=NULL WHERE agent=?', (args.agent,))
                break
        if time.monotonic() >= deadline:
            raise ValueError('Existing listener has not stopped yet; retry after its bounded delivery finishes')
        time.sleep(.1)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.plist.tmp')
    temporary.write_bytes(plistlib.dumps(config)); temporary.chmod(0o600); temporary.replace(path)
    with board.database() as db:
        db.execute('INSERT INTO subscribers (agent,supervised,stop) VALUES (?,?,0) '
                   'ON CONFLICT(agent) DO UPDATE SET supervised=excluded.supervised,stop=0',
                   (args.agent, config['Label']))
    result = command(['launchctl', 'bootstrap', domain, str(path)])
    if result.returncode:
        raise ValueError('Could not start the listener service: ' + result.stderr.strip())
    print('Persistent listener installed: ' + config['Label'])
    return 0


def retire(agent):
    if sys.platform != 'darwin':
        raise ValueError('board retire currently uses macOS launchd')
    name = label(agent)
    result = command(['launchctl', 'bootout', f'gui/{os.getuid()}/{name}'])
    if result.returncode and command(['launchctl', 'print', f'gui/{os.getuid()}/{name}']).returncode == 0:
        raise ValueError('Listener service could not be retired')
    (Path.home() / 'Library/LaunchAgents' / (name + '.plist')).unlink(missing_ok=True)
    with board.database() as db:
        db.execute('UPDATE subscribers SET supervised=NULL,stop=1,pid=NULL WHERE agent=?', (agent,))
    print('Listener retired; message history retained')
    return 0
