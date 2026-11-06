"""Bevy, in Rust: a Cargo workspace built with `cargo` (the `Cargo` build command, `atelier.build_cargo`), played by
running the binary a profile names. It has no live bridge or browser streaming.

The game's manifest says where its workspace is and how each profile runs:

    engine = "bevy"

    [bevy]
    workspace = "."                      # the folder holding Cargo.toml, from the game's folder (default ".")

    [play.play]
    binary = "target/release/my_game"    # from the workspace; built by a step in build.py
    args = ["--windowed"]                # {run} is this run's log folder, {workspace} the workspace's
    env = { BEVY_ASSET_ROOT = "{workspace}", MY_GAME_LOG = "{run}/game.log" }
    settings_env = "MY_GAME_SET"         # optional: `atelier play --set` reaches the game in this variable
"""
import shutil

from . import Engine


def workspace(ctx, data):
    """The game's Cargo workspace folder."""
    return (ctx.game_dir / data.get('bevy', {}).get('workspace', '.')).resolve()


class Bevy(Engine):
    name = 'bevy'
    template = 'bevy'

    def checks(self, ctx, data):
        root = workspace(ctx, data)
        found = [(bool(shutil.which('cargo')), 'cargo on PATH (install Rust with rustup)'),
                 ((root / 'Cargo.toml').is_file(), f'Cargo workspace {root / "Cargo.toml"}')]
        toolchain = root / 'rust-toolchain.toml'
        if toolchain.is_file():
            found.append((bool(shutil.which('rustup')), f'rustup on PATH, for the toolchain {toolchain.name} picks'))
        return found

    def launch(self, ctx, data, profile, spec, folder, settings, extra):
        if 'binary' not in spec:
            raise SystemExit(f'play profile {profile!r} names no binary (or script) to run')
        root = workspace(ctx, data)
        binary = root / spec['binary']
        if not binary.is_file():
            raise SystemExit(f'{binary} is not built: run `atelier build {ctx.game}` first')
        fill = lambda text: str(text).replace('{run}', str(folder)).replace('{workspace}', str(root))
        env = [(key, fill(value)) for key, value in spec.get('env', {}).items()]
        if settings:
            if 'settings_env' not in spec:
                raise SystemExit(f'play profile {profile!r} takes no --set (it names no settings_env)')
            env.append((spec['settings_env'], settings))
        return [str(binary), *(fill(a) for a in spec.get('args', [])), *extra], tuple(env)

