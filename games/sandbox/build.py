"""How the sandbox is built: `atelier build sandbox`. The C++ module, then one editor script that makes the test
ground (materials and the level); nothing else to generate."""
from pathlib import Path

from atelier.build import Step, UnrealScript, UnrealCompile

GAME = Path(__file__).resolve().parent
SCRIPTS = GAME / 'unreal' / 'Scripts'


def steps(ctx):
    from atelier import paths
    return [
        Step('unreal.compile', [UnrealCompile('SandboxEditor')],
             inputs=[GAME / 'unreal' / 'Source', ctx.uproject, paths.ENGINE_PLUGINS], heavy=True,
             about='the Sandbox C++ module (editor target) and the platform plugins it enables'),
        Step('unreal.level', [UnrealScript(SCRIPTS / 'make_level.py', 'SANDBOX LEVEL SAVED')],
             inputs=[SCRIPTS / 'make_level.py'], after=['unreal.compile'], heavy=True,
             about='the prop material and the test ground (/Game/Sandbox)'),
    ]
