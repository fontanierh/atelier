"""The map a multiplayer host or leave opens (JapanNetwork::Map, used by JapanSession) is the V2 game map."""
import re
from pathlib import Path

GAME = Path(__file__).resolve().parents[1]
SOURCE = GAME / 'unreal/Source/Yorimichi/Network/JapanNetwork.cpp'
ENGINE = GAME / 'unreal/Config/DefaultEngine.ini'


def test_the_session_map_is_the_game_default_map_and_has_a_record():
    """@cc [owner:fontanierh,label:correctness] network-session-map
    Hosting and leaving open JapanNetwork::Map(). It must be the configured GameDefaultMap, a package the map record
    owns; the donor's /Game/Japan/Maps/Slice does not exist in V2, so opening it would fail."""
    found = re.findall(r'const TCHAR\* Map\(\) \{ return TEXT\("([^"]+)"\); \}', SOURCE.read_text())
    assert len(found) == 1
    default = re.search(r'^GameDefaultMap=(\S+)$', ENGINE.read_text(), re.M).group(1)
    assert default.split('.')[0] == found[0] == '/Game/V2/Maps/Slice'
    assert f'package = "{found[0]}"' in (GAME / 'assets/map/slice/asset.toml').read_text()
