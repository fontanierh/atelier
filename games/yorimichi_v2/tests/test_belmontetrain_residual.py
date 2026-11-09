"""The seven residual Belmonte train records: their package count and texture coverage, as the inventory classifies them.

They must stay source-less until a verified import closes them (adding sources would make their imports stale)."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'content'))
import records  # noqa: E402

RESIDUAL = ['baggage-van', 'brake-van', 'first-class', 'locomotive', 'restaurant', 'second-class', 'tender']
FOLDER = ROOT / 'assets' / 'adopted' / 'belmontetrain'
GENERATOR = ROOT / 'assets' / 'adopted' / 'belmontetrain' / 'generator' / 'source' / 'world' / 'train' / 'textures.py'


def loaded():
    return {name: records.load_asset(FOLDER / name / 'asset.toml') for name in RESIDUAL}


def test_the_seven_records_hold_473_packages_and_no_source_or_recipe():
    assets = loaded()
    assert sum(len(a.outputs) for a in assets.values()) == 473
    assert all(not a.sources and a.recipe is None for a in assets.values())
    kinds = [o.package.rsplit('/', 1)[1][:4] for a in assets.values() for o in a.outputs]
    assert (kinds.count('SM_B'), kinds.count('M_BT'), kinds.count('T_BT')) == (14, 321, 138)


def test_texture_registry_covers_21_of_the_27_texture_names():
    names = {o.package.rsplit('/', 1)[1] for a in loaded().values() for o in a.outputs
             if o.package.rsplit('/', 1)[1].startswith('T_BT_')}
    registry = set(re.findall(r"'(T_BT_[A-Za-z0-9]+)'", GENERATOR.read_text()))
    assert len(names) == 27
    assert names & registry == names - {'T_BT_BaggageVanInterior', 'T_BT_BrakeVanInterior', 'T_BT_FirstClassInterior',
                                        'T_BT_RestaurantInterior', 'T_BT_SecondClassInterior', 'T_BT_Walnut1'}
    assert len(names & registry) == 21


def test_every_walnut1_sits_beside_the_walnut_it_duplicates():
    # Interchange names the second glTF texture of the one T_BT_Walnut image T_BT_Walnut1; its original is that image.
    packages = {o.package for a in loaded().values() for o in a.outputs}
    twins = sorted(p for p in packages if p.endswith('/T_BT_Walnut1'))
    assert len(twins) == 10
    assert all(p[:-1] in packages and re.search(r'/LOD[01]/', p) for p in twins)
