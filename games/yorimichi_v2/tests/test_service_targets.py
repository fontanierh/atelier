"""The included services still find their world: the saved transport and park objects cover exactly the meshes the runtime
used to spawn, the saved units keep the climbing exemptions their service actors had, the racing save lives outside the
content tree, and the excluded phone and kart features are gone from the code and config.

Data files are read from unreal/Content/Data; a checkout without the LFS data (a pointer file) skips those checks."""
import json
import re
import tomllib
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'unreal/Source/Yorimichi'
DATA = ROOT / 'unreal/Content/Data'
REGIONS = ROOT / 'world/regions'


def data(rel):
    """The parsed JSON of a committed data file, or a skip when only its LFS pointer is here."""
    path = DATA / rel
    text = path.read_text(encoding='utf-8', errors='replace') if path.exists() else ''
    if not text or text.startswith('version https://git-lfs'):
        pytest.skip(f'{rel} is an LFS pointer in this checkout (git lfs checkout games/yorimichi_v2/unreal/Content/Data)')
    return json.loads(text)


def objects_of(tag):
    """Every saved object of the regions whose objects.toml tag is `tag`, as {region id: [route names]}."""
    found = {}
    for path in sorted(REGIONS.glob('*/objects.toml')):
        spec = tomllib.loads(path.read_text())
        if spec.get('tag') == tag:
            found[path.parent.name] = [route for item in spec.get('objects', []) for route in item['route']]
    return found


def region_tags():
    return {path.parent.name: tomllib.loads(path.read_text()).get('tag') for path in REGIONS.glob('*/objects.toml')}


def mesh_name(asset):
    """'/Game/BelmonteTrack/SM_TK_Sleeper.SM_TK_Sleeper' is 'SM_TK_Sleeper' (BelmonteTrack.cpp MeshName)."""
    return asset.rsplit('/', 1)[-1].split('.', 1)[0]


def read_source(rel):
    return (SRC / rel).read_text()


def test_zeppelin_four_stations_each_have_one_saved_station_building():
    """The zeppelin's four stations (world.json zeppelin) are the four saved ZP_ station buildings, one per region."""
    stations = data('world.json')['zeppelin']['stations']
    assert len(stations) == 4
    keys = {'ZP_Woodland', 'ZP_City', 'ZP_MegaPark', 'ZP_Belmonte'}
    seen = Counter()
    for path in REGIONS.glob('*/patches.json'):
        for key in re.findall(r'"key": "(ZP_\w+)"', path.read_text()):
            if key in keys:
                seen[key] += 1
    assert seen == Counter({key: 1 for key in keys})


def test_ferry_terminals_are_one_saved_object_each():
    """Both ferry terminals in service.json are saved, once each, and nothing else is listed."""
    keys = [t['key'] for t in data('ferry/service/service.json')['terminals']]
    saved = [route for routes in objects_of('ferry').values() for route in routes]
    assert sorted(saved) == sorted(keys) == ['brinecove', 'hidamari']


def test_gondola_statics_are_each_saved_exactly_once():
    """Every fixed static row of gondola/runtime.json is held by one saved object, so the runtime skips it and no more."""
    names = [s['name'] for s in data('gondola/runtime.json')['static']]
    saved = [route for routes in objects_of('gondola').values() for route in routes]
    assert Counter(saved) == Counter(names), (set(names) - set(saved), set(saved) - set(names))


def test_railway_pieces_and_groups_are_each_saved_exactly_once():
    """Each track.json piece (by name) and instanced group (mesh#key) is held by one railway object, and nothing else."""
    track = data('belmonte_track/track.json')
    names = [p['name'] for p in track['pieces']]
    names += [f"{mesh_name(g['mesh'])}#{g['key']}" for g in track['instances']]
    saved = [route for routes in objects_of('railway').values() for route in routes]
    # A group split into its rows ("mesh#key@i", from the retired railway_fittings.py) is held once all of its rows are, and never also whole.
    sizes = {f"{mesh_name(g['mesh'])}#{g['key']}": len(g['instances']) for g in track['instances']}
    rows = Counter(route.rsplit('@', 1)[0] for route in saved if '@' in route)
    assert all(n == sizes.get(group) and group not in saved for group, n in rows.items()), rows
    saved = [route for route in saved if '@' not in route] + list(rows)
    assert Counter(saved) == Counter(names), (set(names) - set(saved), set(saved) - set(names))


def test_service_group_tags_match_the_runtime_checks():
    """Each service's saved objects carry the tag its runtime skip looks up (CoversGroup), in the same spelling."""
    literals = {
        'ferry': ('Travel/FerryService.cpp', 'FName(TEXT("ferry"))'),
        'gondola': ('Travel/GondolaService.cpp', 'FName(TEXT("gondola"))'),
        'railway': ('Travel/BelmonteTrack.cpp', 'RailwayTag(TEXT("railway"))'),
    }
    for tag, (rel, literal) in literals.items():
        assert literal in read_source(rel), rel
        assert objects_of(tag), f'no saved objects with tag {tag}'


def test_saved_units_keep_the_climbing_exemption_of_the_actor_they_replaced():
    """AdventureMoveSet::Climbable refused the service actors (NoClimb), the ramps and the parks. Every saved unit of those
    systems must still be refused: ClimbExempt names its tag or source key, and the rule is reached from Climbable."""
    exempt = read_source('World/V2ScenePatch.cpp')
    body = exempt[exempt.index('bool AV2ScenePatch::ClimbExempt'):]
    body = body[:body.index('\n}\n')]
    for tag in ('railway', 'ferry', 'gondola'):
        assert f'SourceKey.StartsWith(TEXT("{tag}:"))' in body, tag
    assert 'SourceKey == TEXT("mega:ramp")' in body
    assert 'SourceKey == TEXT("SkatePark")' in body
    # Every park unit (trees, props, ramps, rails) replaced the SkatePark-tagged park: the whole tag is exempt.
    for tag in ('megapark', 'craterpark'):
        assert f'SourceKey.StartsWith(TEXT("{tag}:"))' in body, tag
    # The saved keys are built from the region tags, so the tags in the objects and the exemptions must agree.
    tags = region_tags()
    assert 'railway' in tags.values() and 'ferry' in tags.values() and 'gondola' in tags.values()
    assert 'mega' in tags.values() and 'megapark' in tags.values() and 'craterpark' in tags.values()
    move = read_source('Player/AdventureMoveSet.cpp')
    assert 'Patch->ClimbExempt()' in move and 'A->ActorHasTag(TEXT("NoClimb"))' in move


def test_racing_saves_live_under_the_project_saved_dir_not_the_content_tree():
    """The racing save is Saved/racing/world.json, so a static-world conversion of Content/Data/world.json cannot touch it,
    and no migration or content tool names the racing files."""
    racing = read_source('Racing/RacingService.cpp')
    assert 'FPaths::ProjectSavedDir() / TEXT("racing") / TEXT("world.json")' in racing
    for path in (ROOT / 'tools').rglob('*.py'):
        assert 'racing' not in path.read_text().lower(), path.relative_to(ROOT)


def test_racing_and_tv_targets_are_still_spawned_by_the_world():
    """The racing service, the TVs and the hippodrome find ABelmonteRegion and AHippodrome; JapanWorld still spawns both."""
    world = read_source('World/JapanWorld.cpp')
    assert 'ABelmonteRegion::Spawn(this, AtelierDataPath(TEXT("belmonte/runtime.json")))' in world
    assert 'AHippodrome::Spawn(GetWorld(), HippodromePath)' in world
    assert 'TActorIterator<ABelmonteRegion>' in read_source('Racing/RacingBroadcast.cpp')
    assert 'AHippodrome::Find(this)' in read_source('Racing/RacingService.cpp')


EXCLUDED = ('PixelStreaming', 'AtelierStream', 'YorimichiPhone', 'kart', 'CarRide', 'DrivingComponent', '/Game/Audio/Driving')


def test_phone_and_kart_exclusions_are_gone_from_code_and_config():
    """X01/X02 have no runtime references and their plugins are disabled; the package checker names forbidden roots."""
    project = json.loads((ROOT / 'unreal/YorimichiV2.uproject').read_text())
    plugins = {p['Name']: p.get('Enabled') for p in project['Plugins']}
    for name in ('Driving', 'AtelierStream', 'PixelStreaming2'):
        assert plugins.get(name) is False, name
    scanned = [p for p in (ROOT / 'unreal/Source').rglob('*') if p.suffix in ('.cpp', '.h', '.inl', '.cs')]
    scanned += list((ROOT / 'unreal/Config').rglob('*.ini')) + list((ROOT / 'tools').rglob('*.py'))
    scanned += [ROOT / 'build.py', ROOT / 'game.toml']
    hits = []
    for path in scanned:
        if 'tests' in path.parts or path == ROOT / 'tools/package/cook_config.py':
            # The packaging check must name these features to reject their content (test_package_config covers it).
            continue
        text = path.read_text(errors='replace')
        hits += [f'{path.relative_to(ROOT)}: {word}' for word in EXCLUDED if word in text]
    assert hits == []
