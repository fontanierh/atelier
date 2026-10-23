"""One explicit city parent table drives source admission and native runtime routing."""
import importlib.util
from pathlib import Path

import pytest

GAME = Path(__file__).resolve().parents[1]
SCRIPT = GAME / 'world/regions/hidamari/logical_catalogue.py'
spec = importlib.util.spec_from_file_location('city_owner_roster', SCRIPT)
roster = importlib.util.module_from_spec(spec); spec.loader.exec_module(roster)


def test_shared_parent_table_matches_every_committed_constructor_and_parameter_file():
    assert len(roster.ASSETS) == 86
    expected = {p.stem for p in (GAME / 'world/regions/hidamari/logical').glob('*.py') if p.stem != '__init__'}
    assert set(roster.ASSETS) == expected
    assert all((GAME / 'assets/hidamari/export-parameters' / (key + '.json')).is_file() for key in roster.ASSETS)
    cpp = (GAME / 'unreal/Source/Yorimichi/CitySurfacePieces.cpp').read_text()
    assert '#include "CitySurfaceParents.h"' in cpp and 'YORIMICHI_CITY_PARENTS(CITY_PARENT)' in cpp


@pytest.mark.parametrize('mutation', ['alias', 'escape', 'extra-code', 'missing-continuation'])
def test_invalid_shared_roster_refuses_before_graph_admission(tmp_path, mutation):
    text = roster.ROSTER.read_text()
    if mutation == 'alias': text = text.replace('ITEM("HD_Shop_01")', 'ITEM("HD_SHOP_00")')
    if mutation == 'escape': text = text.replace('ITEM("HD_Shop_01")', 'ITEM("../Other")')
    if mutation == 'extra-code': text += 'void unrelated();\n'
    if mutation == 'missing-continuation': text = text.replace('ITEM("HD_Shop_01") \\', 'ITEM("HD_Shop_01")')
    path = tmp_path / 'Parents.h'; path.write_text(text)
    with pytest.raises(ValueError): roster.read(path)
