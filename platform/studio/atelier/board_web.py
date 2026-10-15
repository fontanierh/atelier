"""The board's private web UI on loopback. The server is Rust (platform/web/board/server), built here on demand with an
incremental cargo build; it reads and writes the same SQLite mailbox as the `atelier board` CLI. Session presence stays
in Python beside it, because it reads the agents' own runtimes through the CLI's helpers."""
import hashlib
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
from pathlib import Path

from . import board, board_presence, paths

ASSETS = Path(__file__).with_name('board_web_assets')
SERVER = paths.PLATFORM / 'web' / 'board' / 'server'
BINARY = paths.REPO / 'build' / 'board-server' / 'release' / 'atelier-board-server'
MAX_PREBUILT_BYTES = 256 * 1024**2
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


def prebuilt(binary, expected):
    """@cc [owner:fontanierh,label:correctness] verified-prebuilt-board-server
    An explicit prebuilt server MUST be an absolute, owned regular executable without symbolic links,
    bounded in size and freshly verified against the expected SHA256 before launch. A malformed pair,
    changed file or failed verification MUST refuse startup without invoking cargo or falling back.
    """
    if binary is None or type(expected) is not str or not re.fullmatch('[0-9a-fA-F]{64}', expected):
        raise ValueError('Prebuilt board startup requires both --prebuilt-server and a valid --prebuilt-sha256')
    binary = Path(binary)
    if not binary.is_absolute():
        raise ValueError('Prebuilt board server path must be absolute')

    def checked():
        if any(path.is_symlink() for path in (binary, *binary.parents)):
            raise ValueError('Prebuilt board server path cannot contain symbolic links')
        info = binary.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or not info.st_mode & stat.S_IXUSR or not 0 < info.st_size <= MAX_PREBUILT_BYTES):
            raise ValueError('Prebuilt board server must be an owned regular executable within its size bound')
        return info

    def identity(info):
        return (info.st_dev, info.st_ino, info.st_uid, info.st_mode, info.st_size,
                info.st_mtime_ns, info.st_ctime_ns)

    try:
        before = identity(checked())
        descriptor = os.open(binary, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(descriptor, 'rb') as stream:
            if identity(os.fstat(stream.fileno())) != before:
                raise ValueError('Prebuilt board server changed before verification')
            digest, size = hashlib.sha256(), 0
            while chunk := stream.read(min(1024**2, MAX_PREBUILT_BYTES + 1 - size)):
                size += len(chunk)
                if size > MAX_PREBUILT_BYTES:
                    raise ValueError('Prebuilt board server grew beyond its size bound')
                digest.update(chunk)
            if identity(os.fstat(stream.fileno())) != before or identity(checked()) != before:
                raise ValueError('Prebuilt board server changed during verification')
        if digest.hexdigest() != expected.lower():
            raise ValueError('Prebuilt board server SHA256 does not match')
    except OSError:
        raise ValueError('Prebuilt board server could not be verified') from None
    return binary


def serve(args):
    if not 1 <= args.port <= 65535:
        raise ValueError('port must be 1–65535')
    binary, digest = getattr(args, 'prebuilt_server', None), getattr(args, 'prebuilt_sha256', None)
    selected = prebuilt(binary, digest) if binary is not None or digest is not None else None
    with board.database():
        pass
    binary = build() if selected is None else selected
    board_presence.Presence().start()
    server = subprocess.Popen(command(binary, args))
    # A restart stops this launcher; the server goes with it, so the port is free for the next one.
    signal.signal(signal.SIGTERM, lambda *_: server.terminate())
    try:
        return server.wait()
    except KeyboardInterrupt:
        server.terminate()
        return server.wait()
