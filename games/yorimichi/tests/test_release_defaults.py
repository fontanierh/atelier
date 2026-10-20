"""The release defaults (JapanPreferences.cpp JapanReleaseDefaults) are the operator's preset, exactly."""
from pathlib import Path
import re

GAME = Path(__file__).resolve().parents[1]
PREFERENCES = GAME / 'unreal/Source/Yorimichi/JapanPreferences.cpp'
PRESET = Path(__file__).resolve().parent / 'fixtures/operator393-defaults.txt'
# Preset keys that are not preferences: kept by their own code at the preset's value, or retired settings.
KEPT_ELSEWHERE = {'soundbank': 0.0, 'light_version': 3.0}
RETIRED = {'cairo_botw', 'moveset', 'shield'}


def preset():
    return {k: float(v) for k, v in (line.split('=', 1) for line in PRESET.read_text().split() if '=' in line)}


def source():
    return PREFERENCES.read_text(encoding='utf-8')


def release_defaults():
    block = re.search(r'JapanReleaseDefaults\(\)\n\{.*?Preset = \{(.*?)\n    \};', source(), re.S).group(1)
    pairs = re.findall(r'\{TEXT\("(\w+)"\), (-?\d*\.\d*)f\}', block)
    assert len(pairs) == block.count('TEXT('), 'every entry parses'
    return {k: float(v) for k, v in pairs}


def preferences():
    """Key -> (built-in default or None for a Skate feel knob, minimum, maximum)."""
    text, out, num = source(), {}, r'(-?[\d.]+)f?'
    for m in re.finditer(r'\{TEXT\("(\w+)"\),\s*TEXT\("[^"]*"\),\s*' + num + r',\s*' + num + r',\s*' + num, text):
        out[m[1]] = (float(m[2]), float(m[3]), float(m[4]))
    for m in re.finditer(r'\{TEXT\("(skate_\w+)"\),\s*TEXT\("[^"]*"\),\s*TEXT\("(?:[^"\\]|\\.)*"\),\s*' + num + r',\s*' + num, text):
        out[m[1]] = (None, float(m[2]), float(m[3]))
    return out


def test_release_defaults_are_the_operator_preset_exactly():
    given, table = preset(), release_defaults()
    supported = {k: v for k, v in given.items() if k not in KEPT_ELSEWHERE and k not in RETIRED}
    assert table == supported
    assert set(given) == set(supported) | set(KEPT_ELSEWHERE) | RETIRED


def test_every_release_default_is_a_preference_within_its_range():
    prefs = preferences()
    for key, value in release_defaults().items():
        assert key in prefs, key
        _, low, high = prefs[key]
        assert low <= value <= high, (key, value, low, high)
    # The preset covers every saved preference; desktop is a launch flag, never saved.
    assert set(prefs) - set(release_defaults()) == {'desktop'}


def test_retired_and_separately_kept_keys_are_not_preferences():
    prefs = preferences()
    assert not (RETIRED | set(KEPT_ELSEWHERE)) & set(prefs)
    text = source()
    assert 'static constexpr int32 LightVersion = 3;' in text
    assert 'Saved(TEXT("soundbank"),0.f)' in text


def test_saved_values_win_and_resets_return_to_the_release_defaults():
    text = source()
    init = text[text.index('void UJapanPreferences::Initialize'):]
    # defaults first, then the saved file over them
    assert init.index('Values = JapanDefaultPreferences(nullptr);') < init.index('DefaultValues.Add(V.Key,V.Value)') < init.index('SavedValues=ReadSaved();')
    for function in ('void UJapanPreferences::ResetSkate', 'bool UJapanPreferences::IsSkateCustomStock', 'void UJapanPreferences::ResetLight'):
        body = text[text.index(function):]
        body = body[:body.index('\n}\n')]
        assert 'DefaultValues.FindRef(' in body and 'SkateDefault(' not in body, function
