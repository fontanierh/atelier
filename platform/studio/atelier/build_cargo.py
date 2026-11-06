"""`Cargo`: a build step's command that runs `cargo` in a Rust workspace, for games on the Bevy engine.

It runs in the workspace's folder, so the workspace's own `.cargo/config.toml` (aliases, target flags) and its
`rust-toolchain.toml` apply, and it asks admission for the compile slot, as an Unreal compile does: rustc fans out
over every core, so `CARGO_BUILD_JOBS` caps its workers (aliases included) as the Unreal build tool's are capped.
Cargo keeps its own incremental state in the workspace's `target/`; the step's inputs decide when the command runs.

    Step('game.binary', [Cargo(('build', '--release'), workspace=GAME)], inputs=[GAME / 'src', GAME / 'Cargo.lock'],
         heavy=True)
"""
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

# The compiler workers a build may use, as for Unreal's (`UnrealPackage.workers`).
JOBS = 3


@dataclass
class Cargo:
    """`cargo <args>` in `workspace` (a folder holding Cargo.toml), with at most `jobs` compiler workers."""
    args: tuple
    workspace: Path
    jobs: int = JOBS
    timeout: float = 2 * 3600
    progress: float = 25.               # quiet compiles still print at least every 30 s
    admission_kind: ClassVar[str] = 'compile'

    @property
    def env(self):
        return (('CARGO_BUILD_JOBS', str(self.jobs)),)

    def argv(self, ctx):
        return [sys.executable, '-m', 'atelier.run_in', str(self.workspace), 'cargo', *self.args]
