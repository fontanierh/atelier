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
    from network_review_common import require_clean_source, source_revision, current_native_build
    ctx = Context('yorimichi')
    revision = require_clean_source()
    binary = current_native_build(ctx)
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
    rows = re.findall(r'Test Completed\. Result=\{([^}]+)\} Name=\{[^}]*\} Path=\{([^}]+)\}', text)
    outcomes = {name: state for state, name in rows}
    names = [name for _, name in rows if name.startswith('Yorimichi.Network.')]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    expected = {'Yorimichi.Network.' + name for name in ('JoinEndpoint', 'OrderedInput', 'TraversalCheckpoint', 'SkateWire', 'SkateBudget', 'DefenceTimeline', 'PlayerCollision', 'MoveClock', 'BikeCheckpoint', 'SailCheckpoint', 'FixedCollision', 'BikeSupport')}
    unchanged = source_revision() == revision and current_native_build(ctx) == binary
    passed = not duplicates and unchanged and result == 0 and expected <= outcomes.keys() and all(state == 'Success' for name, state in outcomes.items() if name.startswith('Yorimichi.Network.'))
    receipt = dict(passed=passed, process_exit=result, tests=outcomes, duplicates=duplicates, missing=sorted(expected - outcomes.keys()),
                   source=revision, native_build=binary, source_and_build_unchanged=unchanged)
    (folder / 'checks.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2), flush=True)
    print('Native wire evidence: ' + str(folder), flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
