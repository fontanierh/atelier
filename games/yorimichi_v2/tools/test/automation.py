"""Run V2's native automation tests in one bounded, guarded editor process (-game, no rendering).

    ATELIER_AGENT=OWNER nice -n 10 uv run python games/yorimichi_v2/tools/test/automation.py [FILTER ...]

FILTER defaults to `Yorimichi.V2`. Compile `unreal.compile` first. Passing needs every test the filter names to
complete with Success, at least one test, and the process to exit 0: an empty run or a crash is a failure, never
a pass. The receipt (checks.json) and the guard's log go to build/yorimichi_v2/automation/<time>/.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time

RESULT = re.compile(r'Test Completed\. Result=\{([^}]+)\} Name=\{[^}]*\} Path=\{([^}]+)\}')


def parse(text: str, filters: list[str]) -> dict[str, str]:
    return {path: state for state, path in RESULT.findall(text) if any(path.startswith(f) for f in filters)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('filters', nargs='*', default=['Yorimichi.V2'])
    parser.add_argument('--timeout', type=int, default=600)
    args = parser.parse_args(argv)
    from atelier.build import Context
    from atelier.harness.safety import guarded
    ctx = Context('yorimichi_v2')
    folder = ctx.out / 'automation' / time.strftime('%Y%m%d-%H%M%S')
    folder.mkdir(parents=True, exist_ok=False)
    command = [str(ctx.unreal_app), str(ctx.uproject), '/Engine/Maps/Entry?game=/Script/Engine.GameModeBase',
               '-game', '-nullrhi', '-nosound', '-nosplash', '-nolive', '-unattended', '-stdout', '-FullStdOutLogOutput',
               '-ExecCmds=Automation RunTests ' + '+'.join(args.filters), '-TestExit=Automation Test Queue Empty',
               '-ReportExportPath=' + str(folder / 'report')]
    (folder / 'command.json').write_text(json.dumps(command, indent=2) + '\n')
    exit_code = guarded.run(command, folder / 'guard', timeout=args.timeout, purpose='V2 native automation tests',
                            kind='game', progress=15, track_tree=True)
    outcomes = parse((folder / 'guard/stdout.log').read_text(errors='replace'), args.filters)
    passed = exit_code == 0 and bool(outcomes) and all(state == 'Success' for state in outcomes.values())
    receipt = {'passed': passed, 'process_exit': exit_code, 'filters': args.filters, 'tests': outcomes}
    (folder / 'checks.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))
    print(f'evidence: {folder}')
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
