"""The revision a running game was proven to start from: the `revision` of the parity and route receipts.

A receipt must name the commit its game runs, not the checkout's HEAD at the end of the run: a checkout that moved
after the launch is refused. `launch_revision` reads a live session's recorded launch commit after verifying the
running process; tools for a game without a session record prove its launch another way and pass `how`.
"""
import subprocess
from pathlib import Path


def git(checkout: Path, *argv) -> str:
    return subprocess.run(['git', '-C', str(checkout), *argv], capture_output=True, text=True, check=True).stdout


def revision(checkout: Path, launched: str, how: str) -> dict:
    """The checkout's commit and dirty state, refused unless it is `launched`, the commit the running game was proven
    to start from (`how`: its live session record, or the process start check for a game without one)."""
    commit = git(checkout, 'rev-parse', 'HEAD').strip()
    if launched != commit:
        raise ValueError(f'the game was launched at {launched[:10] or "an unknown revision"}, but {checkout} is now at '
                         f'{commit[:10]}: relaunch the game from this checkout')
    return {'commit': commit, 'dirty': bool(git(checkout, 'status', '--porcelain').strip()), 'launch': how}


def launch_revision(session: str, checkout: Path) -> str:
    """The revision recorded when this live session was launched; the session must have started from `checkout`."""
    from atelier import live_sessions
    record = live_sessions.select(session, checkout=checkout)
    live_sessions.verify(record)
    return record.get('revision') or ''
