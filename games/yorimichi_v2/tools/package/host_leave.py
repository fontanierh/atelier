"""Host and leave a session in an extracted V2 package, one guarded process, and judge its receipts.

The package runs JapanNetworkQA's `host-leave` role (Dev/JapanNetworkQA.cpp): once the local rider is ready it calls
HostGame(2), the menu's path (content identity, Tailscale address, listen travel to JapanNetwork::Map()), saves a
`connected` receipt on the hosted listen world, calls LeaveGame and saves `complete` back in Solo, then exits. The
receipts go to a folder inside the app's sandbox container, the only place the sandboxed package may write. This
covers the host's own session lifecycle; a second player joining from another machine is not part of it.

    uv run python games/yorimichi_v2/tools/package/host_leave.py run --app APP      # guarded launch, then verify
    uv run python games/yorimichi_v2/tools/package/host_leave.py verify DIR         # re-judge saved receipts and the
                                                                                    # exit code `run` recorded
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cook_config  # noqa: E402

GAME = cook_config.GAME
ROLE = 'host-leave'
# ENetMode values the receipts record.
STANDALONE, LISTEN_SERVER = 0, 2
NETWORK_MODE = '/Script/Yorimichi.JapanNetworkGameMode'
SOLO_MODE = '/Script/Yorimichi.JapanGameMode'
PORT = 7777   # DefaultEngine.ini / JapanIpNetDriver default listen port


def container(bundle_id: str | None = None) -> Path:
    """The package's sandbox data folder, where it may write."""
    return Path.home() / 'Library/Containers' / (bundle_id or cook_config.bundle_identifier(GAME)) / 'Data'


def receipt(folder: Path, stage: str) -> dict | None:
    path = folder / f'{ROLE}-{stage}.json'
    return json.loads(path.read_text()) if path.is_file() else None


def checks(folder: Path, exit_code: int | None = 0) -> dict[str, bool]:
    """@cc [owner:fontanierh,label:correctness] host-leave-receipts
    A pass needs a clean exit, no failed receipt, a `connected` receipt on a listen server with the network game mode,
    a game net driver bound on the session port, a session id and content identity, then a `complete` receipt back
    in Solo: standalone, no net driver, the Solo game mode and one local rider. A missing receipt fails its checks."""
    hosted, solo = receipt(folder, 'connected') or {}, receipt(folder, 'complete') or {}
    result = {
        'exit': exit_code == 0,
        'no_failure': receipt(folder, 'failed') is None,
        'hosted_listen': hosted.get('net_mode') == LISTEN_SERVER and hosted.get('game_mode') == NETWORK_MODE,
        'hosted_driver': hosted.get('has_game_driver') is True and str(hosted.get('bound_endpoint', '')).endswith(f':{PORT}'),
        'hosted_session': bool(hosted.get('session')) and bool(hosted.get('identity')),
        'hosted_rider': hosted.get('local_players') == 1 and hosted.get('player_pawns') == 1,
        'left_to_solo': solo.get('net_mode') == STANDALONE and solo.get('has_game_driver') is False
                        and solo.get('game_mode') == SOLO_MODE,
        'solo_rider': solo.get('local_players') == 1 and solo.get('player_pawns') == 1,
        'same_build': bool(hosted) and hosted.get('compiled_code_digest') == solo.get('compiled_code_digest'),
    }
    return result


def run(app: Path, memory_gib: float) -> int:
    from atelier import playtest
    folder = container() / 'tmp' / datetime.datetime.now().strftime('host-leave-%Y%m%d-%H%M%S')
    folder.mkdir(parents=True)
    code = playtest.play_app('yorimichi_v2', app, ('-networkqa=' + ROLE, '-networkqadir=' + str(folder)),
                             limit_gib=memory_gib)
    return report(folder, code)


def recorded_exit(folder: Path) -> int | None:
    """The guarded process's exit code that `run` saved with its verdict; None (a failed `exit` check) when none was."""
    path = folder / 'checks.json'
    try:
        code = json.loads(path.read_text()).get('exit') if path.is_file() else None
    except ValueError:
        return None
    return code if isinstance(code, int) and not isinstance(code, bool) else None


def report(folder: Path, exit_code: int | None) -> int:
    result = checks(folder, exit_code)
    for name, ok in result.items():
        print(f'{"ok  " if ok else "FAIL"} {name}')
    (folder / 'checks.json').write_text(json.dumps({'passed': all(result.values()), 'exit': exit_code,
                                                    'checks': result}, indent=2) + '\n')
    print(f'evidence: {folder}')
    return 0 if all(result.values()) else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    launch = sub.add_parser('run', help='guarded launch of the package, then verify')
    launch.add_argument('--app', type=Path, required=True)
    launch.add_argument('--memory-gib', type=float, default=16.)
    judge = sub.add_parser('verify', help='judge a saved receipt folder')
    judge.add_argument('folder', type=Path)
    args = parser.parse_args(argv)
    if args.command == 'run':
        return run(args.app, args.memory_gib)
    return report(args.folder, recorded_exit(args.folder))


if __name__ == '__main__':
    sys.exit(main())
