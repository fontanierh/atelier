"""Native policies remain attached to logical owners after city subdivision."""
import ast
from pathlib import Path

GAME = Path(__file__).resolve().parents[1]


def test_distance_lods_are_the_actual_existing_native_finisher():
    previous = GAME / 'unreal/Scripts/import_hidamari.py'
    current = GAME / 'unreal/Scripts/city_distance_lods.py'
    def body(path):
        node = next(n for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == 'distance_lods')
        return ast.dump(node, include_attributes=False)
    assert body(current) == body(previous)
