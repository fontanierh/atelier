"""Run the native network serialization and budget tests in one bounded guarded Unreal process.

Compile unreal.compile first. This runs no session or gameplay acceptance test; its
receipt requires every named native test to complete successfully, not merely exit 0.
"""
import json
from pathlib import Path
import re
import time


def main():
    from atelier.build import Context
    from atelier.safety import guarded
    ctx = Context('yorimichi')
    folder = ctx.out / 'network-wire' / time.strftime('%Y%m%d-%H%M%S')
    folder.mkdir(parents=True, exist_ok=False)
    command = [str(ctx.unreal_app), str(ctx.uproject), '/Engine/Maps/Entry?game=/Script/Engine.GameModeBase',
               '-game', '-nullrhi', '-nosound', '-nosplash', '-nolive', '-unattended', '-stdout', '-FullStdOutLogOutput',
               '-ExecCmds=Automation RunTests Yorimichi.Network', '-TestExit=Automation Test Queue Empty',
               '-ReportExportPath=' + str(folder / 'report')]
    (folder / 'command.json').write_text(json.dumps(command, indent=2) + '\n')
    result = guarded.run(command, folder / 'guard', timeout=120, purpose='native network wire tests',
                         kind='game', progress=15, track_tree=True)
    text = (folder / 'guard/stdout.log').read_text(errors='replace')
    outcomes = dict((name, state) for state, name in re.findall(
        r'Test Completed\. Result=\{([^}]+)\} Name=\{[^}]*\} Path=\{([^}]+)\}', text))
    expected = {'Yorimichi.Network.' + name for name in ('JoinEndpoint', 'OrderedInput', 'SkateWire', 'SkateBudget')}
    passed = result == 0 and expected <= outcomes.keys() and all(outcomes[name] == 'Success' for name in expected)
    receipt = dict(passed=passed, process_exit=result, tests=outcomes, missing=sorted(expected - outcomes.keys()))
    (folder / 'checks.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2), flush=True)
    print('Native wire evidence: ' + str(folder), flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
