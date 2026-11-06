"""Hakuba's build for `atelier build hakuba`: the desktop program, and the check that every asset's committed export is
current. Both are cargo commands run in this workspace, so they match `cargo build --release` and
`cargo export --check assets` run by hand."""
from pathlib import Path

from atelier.build import Cargo, Step

GAME = Path(__file__).resolve().parent
CODE = [GAME / 'src', GAME / 'crates', GAME / 'schemas', GAME / 'vendor', GAME / 'Cargo.toml', GAME / 'Cargo.lock',
        GAME / 'rust-toolchain.toml', GAME / '.cargo/config.toml']


def steps(ctx):
    return [
        Step('game.binary', [Cargo(('build', '--release'), workspace=GAME)], inputs=CODE, heavy=True,
             about='the desktop program, target/release/hakuba (cargo keeps its own incremental state in target/)'),
        Step('assets.check', [Cargo(('export', '--check', 'assets'), workspace=GAME)],
             inputs=[GAME / 'tools/export', GAME / 'assets', *CODE], heavy=True,
             about='every asset under assets/ is exported from its current sources, as CI checks'),
    ]
