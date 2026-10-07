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
import math
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import os
import statistics


def load(path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def host_frame_statistics(folder):
    """Each server world timestamp is one processing frame, even in a move burst."""
    frames = {}
    invalid = 0
    try:
        lines = (folder / 'server.log').read_text(errors='replace').splitlines()
    except FileNotFoundError:
        lines = []
    for line in lines:
        if 'NETWORK defence move ' not in line:
            continue
        fields = dict(re.findall(r'(\w+)=([^\s]+)', line))
        try:
            at, dt = float(fields['now']), float(fields['host_dt'])
            if not math.isfinite(at) or not math.isfinite(dt) or dt <= 0:
                raise ValueError('invalid host frame')
            if at in frames and frames[at] != dt:
                raise ValueError('inconsistent frame duration in a move burst')
            frames[at] = dt
        except (KeyError, ValueError):
            invalid += 1
    values = sorted(frames.values())
    p95 = values[math.ceil(.95 * len(values)) - 1] if values else 0.
    return dict(count=len(values), invalid=invalid, median=statistics.median(values) if values else 0.,
                p95=p95, maximum=max(values, default=0.),
                slow_host_p95=max(0., min(p95, .1) - 1 / 60))


def defence_edge_statistics(folder):
    """Report the actual acceptance window for every remote defensive press."""
    edges, invalid = [], 0
    try:
        lines = (folder / 'server.log').read_text(errors='replace').splitlines()
    except FileNotFoundError:
        lines = []
    for line in lines:
        if 'NETWORK defence edge=' not in line:
            continue
        fields = dict(re.findall(r'(\w+)=([^\s]+)', line))
        if fields.get('button') not in ('guard', 'jump', 'dodge'):
            continue
        try:
            at, press, oldest = (float(fields[k]) for k in ('now', 'press', 'oldest'))
            accepted = int(fields['valid'])
            one_way, spread, step, slow_host = (float(fields[k]) for k in ('one_way', 'spread', 'step', 'slow_host'))
            if (not all(math.isfinite(v) for v in (one_way, spread, step, slow_host)) or
                    not 0 <= one_way <= .15 or not 0 <= spread <= .05 or not 0 <= step <= .1 or
                    not 0 <= slow_host <= .1 - 1/60 + 1e-6):
                raise ValueError('invalid measured allowance')
            expected = min(.2, one_way + spread + .03 + step + slow_host)
            if (not all(math.isfinite(v) for v in (at, press, oldest)) or accepted not in (0, 1)
                    or oldest > at or press > at):
                raise ValueError('invalid defence edge')
            edges.append(dict(edge=int(fields['edge']), button=fields['button'], accepted=bool(accepted),
                              now=at, press=press, oldest=oldest, bound=at-oldest, margin=press-oldest, one_way=one_way, spread=spread,
                              step=step, slow_host=slow_host, expected_bound=expected,
                              formula_matches=abs(at-oldest-expected) <= 5e-6))
        except (KeyError, ValueError):
            invalid += 1
    return dict(edges=edges, invalid=invalid)


def compare_receipts(folder, gameplay=False, listen=False, emulation=None, bound_endpoint=None, combat=False, combat_host_fps=20, enemy=False):
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
            for role, receipt in (('guest', gameplay_client), ('host', gameplay_host)):
                total = receipt.get('interpolated_peer_frames', 0) + receipt.get('held_peer_frames', 0)
                outside = receipt.get('before_buffer_peer_frames', total) + receipt.get('after_buffer_peer_frames', total)
                checks[role + '_interpolated_skating'] = (receipt.get('held_peer_frames', -1) >= 0 and
                    total > 0 and receipt.get('interpolated_peer_frames', 0) / total >= .7)
                checks[role + '_within_pose_buffer'] = total > 0 and outside / total <= .15
                checks[role + '_bounded_timestamp_drops'] = 0 <= receipt.get('peer_timestamp_drops', -1) <= 2
                if not any((emulation or {}).get(key, 0) for key in ('lag_ms', 'variance_ms', 'loss_percent')):
                    checks[role + '_zero_lag_prediction'] = (receipt.get('position_corrections_over_1cm') == 0 and
                        0 <= receipt.get('largest_correction_cm', -1) < 1)
    if combat:
        if combat_host_fps == 60:
            timing = host_frame_statistics(folder)
            checks['combat_fast_host_clock'] = (timing['count'] >= 30 and timing['invalid'] == 0 and
                .015 <= timing['median'] <= .0185 and timing['p95'] <= .022)
            defence = defence_edge_statistics(folder)
            accepted = [edge for edge in defence['edges'] if edge['accepted']]
            checks['combat_fast_defence_edges'] = (defence['invalid'] == 0 and
                {edge['button'] for edge in accepted} == {'guard', 'jump', 'dodge'} and
                all(edge['formula_matches'] and edge['bound'] <= .2 + 1e-6 and
                    edge['slow_host'] <= .002 + 1e-6 and edge['margin'] >= .010 - 1e-6 for edge in accepted))
        # D1 is a latency test, not just a successful local hit.
        expected_lag = dict(lag_ms=60, variance_ms=15, loss_percent=2)
        checks['combat_emulated_defence'] = all(
            all(r.get('emulation', {}).get(k) == v for k, v in expected_lag.items()) for r in (server, client))
        final = read('combat-final').get('cases', [])
        final_by_case = {(r.get('person'), r.get('phase')): r for r in final}
        checks['combat_final_contact_count'] = len(final) == len(final_by_case) == 10
        for person_id, person in enumerate(('host', 'guest')):
            for phase in range(5):
                receipt = read(f'combat-{person}-{phase}-result')
                confirmed = read(f'combat-{person}-{phase}-confirmed')
                expected = (1, 2, 3, 0, 0)[phase]
                health_delta = receipt.get('health_before', -1000) - receipt.get('health_after', 1000)
                checks[f'combat_{person}_{phase}'] = (receipt.get('passed') is True and receipt.get('callbacks') == 1 and
                    receipt.get('host_fps') == combat_host_fps and receipt.get('outcome') == expected and abs(health_delta - (8 if expected == 0 else 0)) < .01 and
                    receipt.get('queued') == person_id and receipt.get('resolved') == person_id and
                    receipt.get('cancelled') == 0 and (phase != 0 or receipt.get('parries') == 1) and
                    (phase != 1 or receipt.get('dodges') == 1))
                final_case = final_by_case.get((person_id, phase), {})
                checks[f'combat_{person}_{phase}_final'] = (final_case.get('callbacks') == 1 and
                    final_case.get('health_before') == receipt.get('health_before') and
                    final_case.get('health_after') == receipt.get('health_after') and
                    abs(confirmed.get('health', -1000) - receipt.get('health_after', 1000)) < .01 and
                    0 <= confirmed.get('health_confirm_delay_ms', -1) <= 1000)
                if phase < 3:
                    checks[f'combat_{person}_{phase}_clean_defence'] = all(receipt.get(key) == 0 for key in
                        ('overflows', 'missing_samples', 'authored_fallbacks', 'rejected_defence_times'))
                if phase < 2:
                    for role, frames, fps in (('host', receipt, combat_host_fps), ('owner', confirmed, combat_host_fps if person_id == 0 else 30)):
                        checks[f'combat_{person}_{phase}_{role}_fps'] = (frames.get('frame_count', 0) >= 2 and
                            frames.get('frame_min', 0) >= (.045 if fps == 20 else .015 if fps == 60 else .030) and
                            frames.get('frame_min', 100) <= frames.get('frame_max', 0) <= (.025 if fps == 60 else .1))
                    checks[f'combat_{person}_{phase}_stimulus_in_window'] = (receipt.get('contact_lateness_ms', -1) >= 0 and
                        receipt.get('window_margin_ms', -1) >= 15)
                if phase == 2:
                    checks[f'combat_{person}_actual_guard'] = (receipt.get('guard_hit') is True and
                        receipt.get('recovering_at_contact') is False)
        pending = read('combat-guest-3-result')
        checks['pending_contact_blocks_optional_activity'] = (pending.get('pending_gate_passed') is True and
            pending.get('pending_skate_refusals') == pending.get('pending_travel_refusals') == 1)
        checks['destroyed_source_contact_resolves'] = (pending.get('source_destroyed_before_resolution') is True and
                                                      pending.get('outcome') == 0 and pending.get('resolved') == 1)
        flushed = read('combat-guest-4-result')
        checks['forced_recovery_resolves_contact_before_epoch'] = (flushed.get('forced_flush_passed') is True and
                                                                   flushed.get('flushed') == 1 and flushed.get('cancelled') == 0)
    if enemy:
        from network_enemy_review import compare_enemy
        checks.update(compare_enemy(folder))
    return checks


def worker(folder, port, gameplay=False, listen=False, lag_ms=0, variance_ms=0, loss_percent=0, tailnet=False, combat=False, combat_host_fps=20, enemy=False, app=None, cook_receipt=None, expected_identity=None, plain_package=False):
    from atelier.build import Context
    from atelier.safety import process_tree
    from atelier.safety.guard import attach, reap
    from atelier.safety.process import spawn_game
    from atelier.safety.render_lock import available_bytes
    from network_review_common import require_clean_source, source_revision, current_native_build
    revision = require_clean_source()
    free = available_bytes()
    # Admission budgets the pair, not one game's current usage before launching another.
    # The independent runtime ceiling below includes both complete owned process trees.
    if free is None or free < 12 * 1024**3:
        raise RuntimeError('The compound smoke needs at least 12 GiB available before either game starts')
    ctx = Context('yorimichi')
    package_source = None
    if app:
        from network_package_target import package_fingerprint, verify_cook_source, packaged_command, runtime_identity_checks, plain_launch_checks, cook_binding_checks
        from atelier import paths
        cook = load(cook_receipt)
        if not cook: raise RuntimeError('Missing cook provenance receipt')
        package_source = verify_cook_source(paths.REPO, cook)
        binary = package_fingerprint(app, expected_identity)
        package_binding = cook_binding_checks(cook, binary, package_source, expected_identity)
        if not all(package_binding.values()):
            raise RuntimeError("Package does not match its cook/source: " + str(package_binding))
    else:
        binary = current_native_build(ctx)
    if tailnet:
        from network_review_common import tailnet_ipv4
        host = tailnet_ipv4()
    else:
        host = '127.0.0.1'
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
                           '-ExecCmds=t.MaxFPS ' + (str(combat_host_fps) if combat and role == 'server' else '30')]
                command.extend([f'-PktLag={lag_ms}', f'-PktLagVariance={variance_ms}', f'-PktLoss={loss_percent}'])
                if not tailnet:
                    command.append('-MULTIHOME=127.0.0.1')
                if combat:
                    command += ['-networkcombat', '-networkcombathostfps=' + str(combat_host_fps)]
                if enemy:
                    command += ['-networkenemy', '-foxhunter']
                if gameplay:
                    command.append('-networkgameplay')
                if listen:
                    command.append('-networklisten')
                if app:
                    if plain_package:
                        command = ['-game', '-nullrhi', '-nosound', '-nosplash', '-nolive', '-unattended',
                                   '-stdout', '-FullStdOutLogOutput', '-seconds=45', '-ExecCmds=t.MaxFPS 30',
                                   '-preferencesfile=' + str(folder / 'plain-preferences.txt')]
                    else:
                        command = command[3:]
                    command = packaged_command(app, destination, role, folder, command)
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

            if plain_package:
                game, game_guard = launch('plain', '/Game/Japan/Maps/Slice')
                wait_for('ordinary packaged Solo deadline', lambda: game.poll() is not None, began + 100,
                         [('plain', game, game_guard)])
            else:
                server, server_guard = launch('server', '/Game/Japan/Maps/Slice?game=/Script/Yorimichi.JapanNetworkGameMode?capacity=2' + ('?listen' if listen else ''))
                wait_for('server world', lambda: load(folder / 'server-world.json'), began + 120,
                         [('server', server, server_guard)])
                client, client_guard = launch('client', f'{host}:{port}')
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
        if plain_package:
            checks = plain_launch_checks(folder, (folder / 'plain.log').read_text(errors='replace'), games[0][1].returncode, package_source['code_digest'])
        else:
            checks = compare_receipts(folder, gameplay, listen, emulation, f'{host}:{port}', combat, combat_host_fps, enemy)
            if app:
                checks.update(runtime_identity_checks(folder, expected_identity, package_source['code_digest']))
        checks['source_unchanged'] = source_revision() == revision
        checks['native_build_unchanged'] = (package_fingerprint(app, expected_identity) if app else current_native_build(ctx)) == binary
        if app:
            checks['package_source_unchanged'] = verify_cook_source(paths.REPO, cook) == package_source
            checks.update(package_binding)
        report = dict(passed=all(checks.values()), checks=checks, aggregate=load(aggregate_report),
                      emulation=emulation, source=revision, native_build=binary,
                      scope=('Same-machine Tailscale listener; ' if tailnet else 'Loopback listener; ') +
                            'NullRHI editor smoke. Packaged, rendered and two-machine acceptance remain separate')
        if app:
            report['packaged_build'] = report.pop('native_build')
            report['package_source'] = package_source
            report['scope'] = ('Ordinary packaged Solo, no network QA flags; ' if plain_package else
                               'Same-machine packaged listen/client; cooked collision and compiled identity; ') + 'NullRHI. Rendered and two-machine acceptance remain separate.'
        if combat:
            report['combat_host_frames'] = host_frame_statistics(folder)
            report['combat_defence_edges'] = defence_edge_statistics(folder)
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
    parser.add_argument('--app', type=Path, help='Independently extracted signed macOS Development app')
    parser.add_argument('--cook-receipt', type=Path, help='Cook receipt on the current clean source commit')
    parser.add_argument('--expected-identity', help='Identity from the accepted native receipt at that cook revision')
    parser.add_argument('--plain-package', action='store_true', help='Ordinary Solo with no network QA flags, bounded by UE seconds')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--port', type=int)
    parser.add_argument('--tailnet', action='store_true', help='Use the verified local Tailscale adapter through the ordinary private-listener path')
    parser.add_argument('--combat-host-fps', type=int, choices=(20, 30, 60), default=20)
    parser.add_argument('--enemy', action='store_true', help='Real shared-hunter attacks, AI claw and replicated death')
    parser.add_argument('--combat', action='store_true', help='Native listen-host 20fps and remote combat probes; same-machine stimulus files, real network inputs')
    parser.add_argument('--gameplay', action='store_true', help='Also exercise predicted walking/jump, five seconds of skating and dismount')
    parser.add_argument('--listen', action='store_true', help='Two local players across listen-host/client processes; validates the observer relay within the same aggregate guard')
    parser.add_argument('--lag-ms', type=int, default=0, help='Emulated one-way packet delay on both processes (0..200 ms)')
    parser.add_argument('--variance-ms', type=int, default=0, help='Packet delay variance (0..50 ms)')
    parser.add_argument('--loss-percent', type=int, default=0, help='Emulated packet loss on both processes (0..10 percent)')
    args = parser.parse_args()
    if not (0 <= args.lag_ms <= 200 and 0 <= args.variance_ms <= 50 and 0 <= args.loss_percent <= 10):
        parser.error('Emulation must stay within the bounded lag/variance/loss ranges')
    if args.enemy and (args.combat or args.gameplay):
        parser.error('--enemy has a separate native route; do not combine it with combat/gameplay')
    if args.enemy:
        if (args.lag_ms, args.variance_ms, args.loss_percent) != (60, 15, 2):
            parser.error('Shared-enemy acceptance requires --lag-ms 60 --variance-ms 15 --loss-percent 2')
        args.listen = True
        args.gameplay = False
    elif args.combat:
        if (args.lag_ms, args.variance_ms, args.loss_percent) != (60, 15, 2):
            parser.error('Combat acceptance requires --lag-ms 60 --variance-ms 15 --loss-percent 2')
        args.listen = True
        args.gameplay = False
    elif args.listen:
        args.gameplay = True
    if args.app:
        if not args.cook_receipt or not args.expected_identity:
            parser.error('--app requires --cook-receipt and --expected-identity')
        if not args.plain_package and not args.listen:
            parser.error('Packaged acceptance currently requires a listen pair')
        if args.plain_package and (args.combat or args.enemy or args.gameplay or args.listen or args.lag_ms or args.variance_ms or args.loss_percent):
            parser.error('Ordinary packaged Solo cannot include network stimuli or emulation')
    elif args.cook_receipt or args.expected_identity or args.plain_package:
        parser.error('Package options require --app')
    from atelier.build import Context
    from atelier.safety import guarded
    ctx = Context('yorimichi')
    if args.app:
        from network_package_target import runtime_directory, package_layout
        import uuid
        folder = args.output or runtime_directory(args.app, time.strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8])
        _, _, _, container = package_layout(args.app)
        if container.resolve() not in folder.resolve().parents:
            raise RuntimeError('All packaged run output must be in its own sandbox container')
        folder.mkdir(parents=True, exist_ok=True)
    else:
        folder = args.output or ctx.out / 'network' / time.strftime('%Y%m%d-%H%M%S')
        folder.mkdir(parents=True, exist_ok=True)
    if args.worker:
        return worker(folder, args.port, args.gameplay, args.listen, args.lag_ms, args.variance_ms, args.loss_percent, args.tailnet, args.combat, args.combat_host_fps, args.enemy, args.app, args.cook_receipt, args.expected_identity, args.plain_package)
    if any(folder.iterdir()):
        raise RuntimeError('Use a fresh evidence directory; old receipts cannot establish a new run')
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(('127.0.0.1', args.port or 0))
        port = sock.getsockname()[1]
    return guarded.run([sys.executable, str(Path(__file__).resolve()), '--worker', '--output', str(folder), '--port', str(port), '--combat-host-fps', str(args.combat_host_fps),
                        '--lag-ms', str(args.lag_ms), '--variance-ms', str(args.variance_ms), '--loss-percent', str(args.loss_percent)] +
                       (['--gameplay'] if args.gameplay else []) + (['--listen'] if args.listen else []) + (['--tailnet'] if args.tailnet else []) + (['--combat'] if args.combat else []) + (['--enemy'] if args.enemy else []) +
                       (['--app', str(args.app.resolve()), '--cook-receipt', str(args.cook_receipt.resolve()), '--expected-identity', args.expected_identity] if args.app else []) +
                       (['--plain-package'] if args.plain_package else []),
                       folder / 'guard', timeout=750 if args.app else 330, purpose='native local network session smoke', kind='game',
                       progress=15, track_tree=True)


if __name__ == '__main__':
    raise SystemExit(main())
