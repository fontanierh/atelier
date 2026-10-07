"""Prove private UDP bind failure and normal Solo recovery without changing Tailscale.

Uses a real exclusive blocker on the verified Tailscale adapter at game port 7777.
One guarded turn, serial owned games, no live bridge or editor Python, no fake address.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time


def port_owners(address, port):
    result = subprocess.run(['lsof', '-nP', '-iUDP@' + address + ':' + str(port), '-Fpn'],
                            capture_output=True, text=True, timeout=3, check=False)
    if result.returncode not in (0, 1):
        raise RuntimeError('Could not certify UDP port ownership')
    owners = {int(line[1:]) for line in result.stdout.splitlines() if line.startswith('p')}
    return dict(owners=sorted(owners), lsof=result.stdout)


def process_udp(pid, port):
    result = subprocess.run(['lsof', '-nP', '-a', '-p', str(pid), '-iUDP', '-Fpn'],
                            capture_output=True, text=True, timeout=3, check=False)
    if result.returncode not in (0, 1):
        raise RuntimeError('Could not inspect the live game UDP sockets')
    local = [line[1:].split('->', 1)[0] for line in result.stdout.splitlines() if line.startswith('n')]
    return dict(no_game_port=all(name.rsplit(':', 1)[-1] != str(port) for name in local), lsof=result.stdout)


def load(path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def bind_checks(code, dedicated, text, owners, blocker_pid, receipt=None, live=None):
    checks = dict(exit_code=code == int(dedicated),
                  real_bind_failed='Private listener initialization failed:' in text,
                  sole_blocker=owners == [blocker_pid])
    if dedicated:
        checks['dedicated_error'] = 'Private dedicated listener failed:' in text
        checks['clean_shutdown'] = 'LogExit: Exiting.' in text
    else:
        receipt = receipt or {}
        live = live or {}
        checks.update(native_receipt=bool(receipt) and not receipt.get('error'),
                      live_socket_check=all(live.get(key) is True for key in
                          ('game_alive_before', 'game_alive_after', 'no_game_port', 'sole_blocker')),
                      failure_seen=receipt.get('listen_failure_seen') is True,
                      solo=receipt.get('net_mode') == 0 and receipt.get('game_mode') == '/Script/Yorimichi.JapanGameMode',
                      no_driver=receipt.get('has_game_driver') is False,
                      one_local_player=receipt.get('local_players') == receipt.get('players') == receipt.get('player_pawns') == 1,
                      visible_notice=receipt.get('friends_menu_open') is True and
                          'Could not open game port' in receipt.get('session_status', ''))
    return checks


def worker(folder):
    from atelier.build import Context
    from atelier.safety.guard import attach, reap
    from atelier.safety.process import spawn_game
    from network_review_common import tailnet_ipv4, require_clean_source, source_revision, current_native_build
    ctx = Context('yorimichi')
    revision = require_clean_source()
    binary = current_native_build(ctx)
    address, port = tailnet_ipv4(), 7777
    proof = dict(passed=False, endpoint=f'{address}:{port}', blocker_pid=os.getpid(), runs=[], source=revision, native_build=binary)
    games = []
    try:
        # Deliberately no SO_REUSEADDR or SO_REUSEPORT. Refuse if anything already owns it.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as blocker:
            blocker.bind((address, port))
            proof['before'] = port_owners(address, port)
            if proof['before']['owners'] != [os.getpid()]:
                raise RuntimeError('The occupied-port fixture is not the sole UDP port owner')
            for dedicated in (False, True):
                role = 'dedicated' if dedicated else 'host'
                destination = '/Game/Japan/Maps/Slice'
                if dedicated:
                    destination += '?game=/Script/Yorimichi.JapanNetworkGameMode?capacity=2'
                command = [str(ctx.unreal_app), str(ctx.uproject), destination,
                           '-server' if dedicated else '-game', '-nullrhi', '-nosound', '-nosplash',
                           '-nolive', '-unattended', '-stdout', '-FullStdOutLogOutput', f'-port={port}',
                           '-preferencesfile=' + str(folder / (role + '-preferences.txt')), '-ExecCmds=t.MaxFPS 30']
                if not dedicated:
                    command += ['-networkqa=bind-failure', '-networkqadir=' + str(folder)]
                (folder / (role + '-command.json')).write_text(json.dumps(command, indent=2) + '\n')
                with (folder / (role + '.log')).open('w') as log:
                    game = spawn_game(command, stdout=log, stderr=subprocess.STDOUT)
                    games.append(game)
                    print(f'{role}: owned pid {game.pid}; actual private listener against exclusive blocker', flush=True)
                    live = None
                    with attach(game.pid, folder / (role + '-memory.json'), duration=100) as guard:
                        if guard is None:
                            raise RuntimeError('Actual-child guard could not attach')
                        began, spoken = time.monotonic(), 0.
                        while game.poll() is None:
                            if guard.poll() is not None:
                                raise RuntimeError(role + ' lost its actual-child guard')
                            now = time.monotonic()
                            if now - began > 95:
                                raise RuntimeError(role + ' bind-failure proof exceeded its deadline')
                            if not dedicated and live is None and load(folder / 'bind-failure-complete.json'):
                                before = game.poll() is None
                                sockets = process_udp(game.pid, port)
                                blocker_now = port_owners(address, port)
                                live = dict(game_alive_before=before, game_alive_after=game.poll() is None,
                                            no_game_port=sockets['no_game_port'], sole_blocker=blocker_now['owners'] == [os.getpid()],
                                            game_udp=sockets['lsof'], blocker_udp=blocker_now['lsof'])
                                (folder / 'host-live-sockets.json').write_text(json.dumps(live, indent=2) + '\n')
                                if not all(live[k] for k in ('game_alive_before', 'game_alive_after', 'no_game_port', 'sole_blocker')):
                                    raise RuntimeError('Recovered host failed its live UDP socket inspection')
                                (folder / 'bind-release').touch()
                                print('host: live recovered process has no game-port socket on any address; release certified', flush=True)
                            if now - spoken >= 15:
                                spoken = now
                                print(f'{role}: waiting for native bind-failure/exit proof, {now-began:.1f}s elapsed', flush=True)
                            time.sleep(.1)
                reap(game)
                owners = port_owners(address, port)
                text = (folder / (role + '.log')).read_text(errors='replace')
                checks = bind_checks(game.returncode, dedicated, text, owners['owners'], os.getpid(),
                                     load(folder / 'bind-failure-complete.json'), live)
                proof['runs'].append(dict(role=role, exit=game.returncode, checks=checks, port=owners, live=live))
                print(role + ': ' + json.dumps(checks), flush=True)
                if not all(checks.values()):
                    raise RuntimeError(role + ' failed its actual bind/recovery acceptance checks')
            proof['source_unchanged'] = source_revision() == revision
            proof['native_build_unchanged'] = current_native_build(ctx) == binary
            if not proof['source_unchanged'] or not proof['native_build_unchanged']:
                raise RuntimeError('Source or compiled files changed during native bind acceptance')
            proof['passed'] = True
        return 0
    finally:
        for game in games:
            reap(game)
        (folder / 'checks.json').write_text(json.dumps(proof, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    from atelier.build import Context
    from atelier.safety import guarded
    ctx = Context('yorimichi')
    folder = args.output or ctx.out / 'network-bind' / time.strftime('%Y%m%d-%H%M%S')
    folder.mkdir(parents=True, exist_ok=True)
    if args.worker:
        return worker(folder)
    if any(folder.iterdir()):
        raise RuntimeError('A fresh evidence directory is required')
    return guarded.run([sys.executable, str(Path(__file__).resolve()), '--worker', '--output', str(folder)],
                       folder / 'guard', timeout=225, purpose='native private UDP bind failures',
                       kind='game', progress=15, track_tree=True)


if __name__ == '__main__':
    raise SystemExit(main())
