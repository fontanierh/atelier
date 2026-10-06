"""Scenarios and the in-game code they send must at least parse, and every in-game file a scenario reads must exist:
a typo here otherwise costs a whole game launch to find."""
import ast
import re
from pathlib import Path

SCENARIOS = Path(__file__).resolve().parents[1] / 'scenarios'


def test_every_scenario_and_ingame_file_parses():
    files = sorted(SCENARIOS.glob('*.py')) + sorted((SCENARIOS / 'ingame').rglob('*.py'))
    assert len(files) > 40
    for path in files:
        ast.parse(path.read_text(), filename=str(path))


def test_every_ingame_file_a_scenario_reads_exists():
    for path in SCENARIOS.glob('*.py'):
        for folder, name in re.findall(r"INGAME / '([\w-]+)' / '([\w-]+\.py)'", path.read_text()):
            assert (SCENARIOS / 'ingame' / folder / name).is_file(), f'{path.name} reads a missing {folder}/{name}'
