"""One guarded, bounded local server/client lifecycle smoke test (no editor Python or live bridge).

    nice -n 10 uv run python games/yorimichi/tools/review_network_session.py

Compile and stage data.network first. Uses one big render turn, one independent 10 GiB
aggregate guard from before either game starts, and the normal per-game guards. NullRHI
editor processes prove session/collision diagnostics only, never a packaged server cook,
rendered remote poses, or clean-machine/Tailscale acceptance.
"""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import os


def load(path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def compare_receipts(folder, gameplay=False, listen=False, emulation=None, bound_endpoint=None):
    def read(name):
        value = load(folder / (name + '.json'))
        if not value or value.get('error'):
            raise RuntimeError(f'Native receipt missing or failed: {name}: {value}')
        return value

    server, client = read('server-connected'), read('client-connected')
    server_end, client_end = read('server-complete'), read('client-complete')
    checks = {}
    if bound_endpoint is not None:
        checks['private_listener'] = (server.get('bound_endpoint') == bound_endpoint and
                                       server.get('driver_class') == '/Script/Yorimichi.JapanIpNetDriver')
    if emulation is not None:
        expected = dict(order=0, duplicate_percent=0, lag_min_ms=0, lag_max_ms=0,
                        incoming_lag_min_ms=0, incoming_lag_max_ms=0, incoming_loss_percent=0,
                        jitter_ms=0) | emulation
        for role, receipt in (('server', server), ('client', client)):
            checks[role + '_actual_emulation'] = receipt.get('emulation') == expected
    checks['same_session'] = bool(server.get('session')) and server['session'] == client.get('session')
    checks['same_identity'] = bool(server.get('identity')) and server['identity'] == client.get('identity')
    checks['server_role'] = server.get('local_players') == int(listen) and server.get('net_mode') == (2 if listen else 1)
    players = 2 if listen else 1
    checks['admitted_player'] = (server.get('players') == client.get('players') == players and
                                server.get('player_pawns') == client.get('player_pawns') == players)
    people_a, people_b = [sorted(r.get('people', []), key=lambda p: p.get('id', '')) for r in (server, client)]
    checks['player_identity'] = (people_a == people_b and len(people_a) == players and
                                len({p.get('id') for p in people_a}) == players and
                                all(p.get('id') and p.get('ready') is True for p in people_a))
    checks['world_ready'] = server.get('world_ready') is True and client.get('world_ready') is True
    checks['same_instances'] = server.get('instances', 0) > 0 and server['instances'] == client.get('instances')
    checks['same_rails'] = (server.get('rails', 0) > 0 and server['rails'] == client.get('rails') and
                            bool(server.get('rail_digest')) and server['rail_digest'] == client.get('rail_digest'))
    a, b = server.get('collision_probes', []), client.get('collision_probes', [])
    checks['collision_samples'] = len(a) >= 40 and len(a) == len(b)
    for index, (left, right) in enumerate(zip(a, b)):
        checks[f'ground_{index}'] = (left.get('key') == right.get('key') and
                                     left.get('complex') == right.get('complex') and
                                     left.get('hit') is True and right.get('hit') is True and
                                     abs(left['z'] - right['z']) <= .1 and
                                     abs(left['normal_z'] - right['normal_z']) <= .001)
    checks['server_teardown'] = (server_end.get('players') == server_end.get('player_pawns') == int(listen) and
                                 server_end.get('local_players') == int(listen) and server_end.get('net_mode') == (2 if listen else 1))
    checks['client_returned_to_solo'] = (client_end.get('net_mode') == 0 and
                                        client_end.get('local_players') == client_end.get('player_pawns') == client_end.get('players') == 1)
    if gameplay:
        gameplay_server, gameplay_client = read('server-gameplay'), read('client-gameplay')
        checks['native_gameplay'] = gameplay_server.get('passed') is True and gameplay_client.get('passed') is True
        checks['host_received_sustained_skating'] = gameplay_server.get('accepted_pose_frames', 0) >= 60
        checks['host_applied_jump_and_release'] = (gameplay_server.get('jump_cm', 0) >= 25 and
                                                   gameplay_server.get('processed_edges', 0) >= 2)
        checks['client_applied_valid_checkpoints'] = (gameplay_client.get('checkpoints_applied', 0) > 0 and
                                                       gameplay_client.get('checkpoints_rejected', -1) == 0)
        checks['owner_skated_without_saved_moves'] = (gameplay_client.get('skate_seconds', 0) >= 5 and
                                                     gameplay_client.get('maximum_saved_skate_moves') == 0)
        if listen:
            gameplay_host = read('host/client-gameplay')
            checks['both_peers_received_skating'] = (gameplay_client.get('received_peer_frames', 0) >= 60 and
                                                      gameplay_host.get('received_peer_frames', 0) >= 60)
            checks['both_peers_applied_skating'] = (gameplay_client.get('applied_peer_frames', 0) >= 60 and
                                                     gameplay_host.get('applied_peer_frames', 0) >= 60)
            checks['listen_host_drove'] = gameplay_host.get('passed') is True and gameplay_host.get('skate_seconds', 0) >= 5
            checks['both_peers_interpolated_skating'] = (gameplay_client.get('interpolated_peer_frames', 0) > 0 and
                                                         gameplay_host.get('interpolated_peer_frames', 0) > 0)
    return checks


def worker(folder, port, gameplay=False, listen=False, lag_ms=0, variance_ms=0, loss_percent=0):
    from atelier.build import Context
    from atelier.safety import process_tree
    from atelier.safety.guard import attach, reap
    from atelier.safety.process import spawn_game
    from atelier.safety.render_lock import available_bytes
    free = available_bytes()
    # Admission budgets the pair, not one game's current usage before launching another.
    # The independent runtime ceiling below includes both complete owned process trees.
    if free is None or free < 12 * 1024**3:
        raise RuntimeError('The compound smoke needs at least 12 GiB available before either game starts')
    ctx = Context('yorimichi')
    pid, started = os.getpid(), process_tree.started(os.getpid())
    aggregate_report, stop = folder / 'aggregate-memory.json', folder / 'aggregate-stop'
    monitor = subprocess.Popen([sys.executable, '-m', 'atelier.safety.tree_guard', '--pid', str(pid),
                                '--expected-start', str(started), '--report', str(aggregate_report),
                                '--stop-file', str(stop), '--duration', '315'])
    games = []
    began, spoken = time.monotonic(), 0.
    try:
        ready = time.monotonic() + 10
        while time.monotonic() < ready:
            health = load(aggregate_report)
            if monitor.poll() is not None:
                raise RuntimeError('Aggregate monitor exited before startup')
            if health and health.get('owner_started') == started and health.get('state') == 'running':
                break
            time.sleep(.1)
        else:
            raise RuntimeError('Aggregate monitor did not certify startup within 10 seconds')
        with ExitStack() as guards:
            def launch(role, destination):
                log = guards.enter_context((folder / (role + '.log')).open('w'))
                command = [str(ctx.unreal_app), str(ctx.uproject), destination,
                           '-server' if role == 'server' and not listen else '-game', '-nullrhi', '-nosound', '-nosplash', '-nolive',
                           '-unattended', '-stdout', '-FullStdOutLogOutput',
                           f'-port={port}', '-networkqa=' + role, '-networkqadir=' + str(folder),
                           '-preferencesfile=' + str(folder / (role + '-preferences.txt')),
                           '-ExecCmds=t.MaxFPS 30']
                command.extend([f'-PktLag={lag_ms}', f'-PktLagVariance={variance_ms}', f'-PktLoss={loss_percent}'])
                command.append('-MULTIHOME=127.0.0.1')
                if gameplay:
                    command.append('-networkgameplay')
                if listen:
                    command.append('-networklisten')
                (folder / (role + '-command.json')).write_text(json.dumps(command, indent=2) + '\n')
                game = spawn_game(command, stdout=log, stderr=subprocess.STDOUT)
                games.append((role, game))
                guards.callback(reap, game)
                guard = guards.enter_context(attach(game.pid, folder / (role + '-memory.json'), duration=300))
                if guard is None:
                    raise RuntimeError(f'Could not attach the {role} actual-child guard')
                print(f'{role} started as owned pid {game.pid}; aggregate plus individual guards active', flush=True)
                return game, guard

            def wait_for(stage, condition, deadline, running):
                nonlocal spoken
                while time.monotonic() < deadline:
                    health = load(aggregate_report)
                    if monitor.poll() is not None or not health or health.get('state') != 'running':
                        raise RuntimeError('Aggregate monitor lost: ' + str(health))
                    if time.time() - health.get('time', 0) > 3:
                        raise RuntimeError('Aggregate monitor heartbeat is stale')
                    for role, game, guard in running:
                        if game.poll() is None and guard.poll() is not None:
                            raise RuntimeError(role + ' lost its actual-child guard')
                        failed = load(folder / (role + '-failed.json'))
                        if failed:
                            raise RuntimeError(str(failed))
                    if condition():
                        print(f'{stage}: complete, {time.monotonic() - began:.1f}s elapsed', flush=True)
                        return
                    for role, game, _ in running:
                        if game.poll() is not None and (game.returncode != 0 or not load(folder / (role + '-complete.json'))):
                            raise RuntimeError(f'{role} exited {game.returncode} before {stage}')
                    now = time.monotonic()
                    if now - spoken >= 15:
                        spoken = now
                        print(f'{stage}: waiting for native receipt; {now - began:.1f}s elapsed; '
                              f'aggregate {health["footprint_bytes"] / 1024**3:.2f}/10 GiB', flush=True)
                    time.sleep(.25)
                raise RuntimeError(stage + ' deadline expired')

            server, server_guard = launch('server', '/Game/Japan/Maps/Slice?game=/Script/Yorimichi.JapanNetworkGameMode?capacity=2' + ('?listen' if listen else ''))
            wait_for('server world', lambda: load(folder / 'server-world.json'), began + 120,
                     [('server', server, server_guard)])
            client, client_guard = launch('client', f'127.0.0.1:{port}')
            running = [('server', server, server_guard), ('client', client, client_guard)]
            wait_for('admission and clean disconnect',
                     lambda: all(load(folder / (role + '-complete.json')) for role in ('server', 'client')),
                     began + 290, running)
            for role, game in games:
                try:
                    code = game.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    raise RuntimeError(role + ' did not exit after its native completion receipt')
                if code != 0:
                    raise RuntimeError(f'{role} exited {code}')
        # Actual-child guards have reaped their recorded SDK helpers before this stop request.
        stop.touch()
        if monitor.wait(timeout=5) != 0:
            raise RuntimeError('Aggregate monitor rejected teardown')
        emulation = dict(lag_ms=lag_ms, variance_ms=variance_ms, loss_percent=loss_percent)
        checks = compare_receipts(folder, gameplay, listen, emulation, f'127.0.0.1:{port}')
        report = dict(passed=all(checks.values()), checks=checks, aggregate=load(aggregate_report),
                      emulation=emulation,
                      scope='Local NullRHI editor session smoke; packaged/rendered/network acceptance remains separate')
        (folder / 'checks.json').write_text(json.dumps(report, indent=2) + '\n')
        for name, ok in checks.items():
            print(('PASS ' if ok else 'FAIL ') + name, flush=True)
        return 0 if report['passed'] else 1
    finally:
        for _, game in games:
            reap(game)
        # On failure leave the aggregate guard alive until this pinned worker exits; it
        # will reap remaining recorded descendants. The outer guard also tracks ownership.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--port', type=int)
    parser.add_argument('--gameplay', action='store_true', help='Also exercise predicted walking/jump, five seconds of skating and dismount')
    parser.add_argument('--listen', action='store_true', help='Two local players across listen-host/client processes; validates the observer relay within the same aggregate guard')
    parser.add_argument('--lag-ms', type=int, default=0, help='Emulated one-way packet delay on both processes (0..200 ms)')
    parser.add_argument('--variance-ms', type=int, default=0, help='Packet delay variance (0..50 ms)')
    parser.add_argument('--loss-percent', type=int, default=0, help='Emulated packet loss on both processes (0..10 percent)')
    args = parser.parse_args()
    if not (0 <= args.lag_ms <= 200 and 0 <= args.variance_ms <= 50 and 0 <= args.loss_percent <= 10):
        parser.error('Emulation must stay within the bounded lag/variance/loss ranges')
    if args.listen:
        args.gameplay = True
    from atelier.build import Context
    from atelier.safety import guarded
    ctx = Context('yorimichi')
    folder = args.output or ctx.out / 'network' / time.strftime('%Y%m%d-%H%M%S')
    folder.mkdir(parents=True, exist_ok=True)
    if args.worker:
        return worker(folder, args.port, args.gameplay, args.listen, args.lag_ms, args.variance_ms, args.loss_percent)
    if any(folder.iterdir()):
        raise RuntimeError('Use a fresh evidence directory; old receipts cannot establish a new run')
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(('127.0.0.1', args.port or 0))
        port = sock.getsockname()[1]
    return guarded.run([sys.executable, str(Path(__file__).resolve()), '--worker', '--output', str(folder), '--port', str(port),
                        '--lag-ms', str(args.lag_ms), '--variance-ms', str(args.variance_ms), '--loss-percent', str(args.loss_percent)] +
                       (['--gameplay'] if args.gameplay else []) + (['--listen'] if args.listen else []),
                       folder / 'guard', timeout=330, purpose='native local network session smoke', kind='game',
                       progress=15, track_tree=True)


if __name__ == '__main__':
    raise SystemExit(main())
