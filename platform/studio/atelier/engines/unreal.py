"""Unreal Engine 5.8: the editor binaries (`atelier.engine`), the game's `unreal/*.uproject`, the live bridge and Pixel
Streaming. Its build commands (`UnrealCompile`, `UnrealScript`, `UnrealPackage`, ...) are in `atelier.build`."""
from . import Engine


class Unreal(Engine):
    name = 'unreal'
    live = True
    stream = True
    template = 'sandbox'

    def checks(self, ctx, data):
        from ..setup import mac_checks
        found = [(ctx.unreal_cmd.exists(), f'Unreal Engine at {ctx.unreal_root} (set UE_ROOT to move it)')]
        found += mac_checks()
        found.append((ctx.uproject is not None and ctx.uproject.exists(), f'Unreal project {ctx.uproject}'))
        return found

    def launch(self, ctx, data, profile, spec, folder, settings, extra):
        if ctx.uproject is None:
            raise SystemExit(f'no Unreal project in {ctx.game_dir / "unreal"}')
        args = [a.replace('{run}', str(folder)) for a in spec.get('args', [])]   # {run}: this run's log folder
        command = [str(ctx.unreal_app), str(ctx.uproject), *args, '-stdout', f'-abslog={folder / "game.log"}', *extra]
        if settings:
            command.append(f'-set={settings}')
        return command, ()
