"""__Title__'s build: the game program, compiled by cargo."""
from pathlib import Path

from atelier.build import Cargo, Step

GAME = Path(__file__).resolve().parent


def steps(ctx):
    return [
        Step('game.binary', [Cargo(('build', '--release'), workspace=GAME)],
             inputs=[GAME / 'src', GAME / 'Cargo.toml'], optional_inputs=[GAME / 'Cargo.lock'], heavy=True,
             about='the game program (target/release), with cargo keeping its own incremental state'),
    ]
