"""The board's private web UI on loopback. The server is Rust (platform/web/board/server), built here on demand with an
incremental cargo build; it reads and writes the same SQLite mailbox as the `atelier board` CLI. Session presence stays
in Python beside it, because it reads the agents' own runtimes through the CLI's helpers."""
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

from . import board, board_presence, paths

ASSETS = Path(__file__).with_name('board_web_assets')
SERVER = paths.PLATFORM / 'web' / 'board' / 'server'
BINARY = paths.REPO / 'build' / 'board-server' / 'release' / 'atelier-board-server'
# The board village (platform/web/board-world): its page is committed beside the classic board's assets; the compiled
# scene comes from `platform/web/board-world/build.sh` and is never committed.
WORLD_BUILD = paths.REPO / 'build' / 'board-world' / 'dist'


def cargo():
    """Rust's build tool, from PATH or rustup's default home (launchd jobs start with a short PATH)."""
    found = shutil.which('cargo') or Path.home() / '.cargo' / 'bin' / 'cargo'
    return str(found) if Path(found).is_file() else None


def build():
    """The server binary, rebuilt first when its sources changed. A build that cannot run keeps an existing binary
    serving rather than take the board down, and says so."""
    tool = cargo()
    if tool is None:
        if BINARY.is_file():
            print('cargo not found; serving the board with the last built server', file=sys.stderr)
            return BINARY
        raise RuntimeError('The board server is written in Rust: install it from https://rustup.rs')
    result = subprocess.run([tool, 'build', '--release', '--locked', '--quiet'], cwd=SERVER)
    if result.returncode != 0:
        if BINARY.is_file():
            print('The board server did not build; serving the last built one', file=sys.stderr)
            return BINARY
        raise RuntimeError('The board server did not build')
    return BINARY


def command(binary, args, port=None):
    argv = [str(binary), '--port', str(args.port if port is None else port), '--assets', str(ASSETS),
            '--world-build', str(WORLD_BUILD), '--sender', args.sender, '--parent-pid', str(os.getpid())]
    for origin in args.public_origin:
        argv += ['--public-origin', origin]
    if args.allowed_user:
        argv += ['--allowed-user', args.allowed_user]
    if args.remote_status:
        argv += ['--remote-status', str(args.remote_status)]
    return argv


def serve(args):
    if not 1 <= args.port <= 65535:
        raise ValueError('port must be 1–65535')
    with board.database():
        pass
    binary = build()
    board_presence.Presence().start()
    server = subprocess.Popen(command(binary, args))
    # A restart stops this launcher; the server goes with it, so the port is free for the next one.
    signal.signal(signal.SIGTERM, lambda *_: server.terminate())
    try:
        return server.wait()
    except KeyboardInterrupt:
        server.terminate()
        return server.wait()
