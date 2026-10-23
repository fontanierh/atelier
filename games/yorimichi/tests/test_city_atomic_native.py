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


def test_native_city_manifest_api_does_not_require_numpy():
    import subprocess
    import sys
    code = '''import sys
sys.modules['numpy'] = None
sys.path[:0] = [sys.argv[1], sys.argv[1] + '/world']
import city_atomic_products
assert len(city_atomic_products.SOURCES) == 86
assert city_atomic_products.piece_material_paths('HD_Boat', ['Palette']) == {'Palette': '/Game/Japan/Materials/M_Harbor'}
'''
    result = subprocess.run([sys.executable, '-c', code, str(GAME)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
