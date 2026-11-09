"""Source recovery plans and applies a donor family's records once, and refuses whatever the donor report disagrees with."""
import hashlib
import importlib
import json
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS / 'content'))
sys.path.insert(0, str(TOOLS / 'migrate'))
import records  # noqa: E402
import recover  # noqa: E402


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode() if isinstance(data, str) else data)
    return path


def record(game: Path, folder: str, text: str):
    write(game / 'assets' / folder / 'asset.toml', text)


def verified(game: Path, folder: str, files: dict):
    body = {'schema': 1, 'kind': 'editor-saved', 'asset': folder, 'engine': '5.8.2-test', 'dependencies': {},
            'files': {rel: sha(rel.encode()) for rel in files}}
    write(game / 'assets' / folder / 'verified.json', json.dumps(body, indent=2, sort_keys=True) + '\n')


@pytest.fixture
def world(tmp_path):
    """A small game with three adopted hippodrome records, and a donor output folder with two surfaces and one
    painted structure, one texture."""
    game = tmp_path / 'game'
    record(game, 'adopted/hippodrome/loose_files', '''schema = 1
id = "adopted/hippodrome/loose_files"
kind = "adopted"
authority = "editor"
owner = "shared/hippodrome/loose_files"
provenance = "test"
license = "test"

[[outputs]]
package = "/Game/Hippodrome/SM_HD_Ground"

[[outputs]]
package = "/Game/Hippodrome/SM_HD_FinishPost"
''')
    verified(game, 'adopted/hippodrome/loose_files', ['unreal/Content/Hippodrome/SM_HD_Ground.uasset',
                                                      'unreal/Content/Hippodrome/SM_HD_Ground.ubulk',
                                                      'unreal/Content/Hippodrome/SM_HD_FinishPost.uasset'])
    record(game, 'adopted/hippodrome/textures', '''schema = 1
id = "adopted/hippodrome/textures"
kind = "adopted"
authority = "editor"
owner = "shared/hippodrome/textures"
provenance = "test"
license = "test"

[[outputs]]
package = "/Game/Hippodrome/Textures/T_Dirt"
''')
    verified(game, 'adopted/hippodrome/textures', ['unreal/Content/Hippodrome/Textures/T_Dirt.uasset'])
    record(game, 'adopted/hippodrome/materials', '''schema = 1
id = "adopted/hippodrome/materials"
kind = "adopted"
authority = "editor"
owner = "shared/hippodrome/materials"
provenance = "test"
license = "test"

[[outputs]]
package = "/Game/Hippodrome/Materials/M_HD_Grass"
''')
    verified(game, 'adopted/hippodrome/materials', ['unreal/Content/Hippodrome/Materials/M_HD_Grass.uasset'])

    donor = tmp_path / 'donor'
    glb = {'SM_HD_Ground': b'ground glb', 'SM_HD_FinishPost': b'finish glb'}
    for name, data in glb.items():
        write(donor / 'glb' / f'{name}.glb', data)
    write(donor / 'textures' / 'T_HD_Dirt.png', b'dirt png')
    write(donor / 'hippodrome.json', json.dumps({
        'textures': {'HD_Dirt': 'T_HD_Dirt.png'},
        'meshes': [{'name': 'SM_HD_Ground'}, {'name': 'SM_HD_FinishPost'}]}))
    write(donor / 'build-report.json', json.dumps({'meshes': {
        'SM_HD_Ground': {'material': 'HD_Grass', 'triangles': 1188, 'sha256': sha(glb['SM_HD_Ground'])},
        'SM_HD_FinishPost': {'material': 'HD_FinishPost', 'triangles': 5006, 'sha256': sha(glb['SM_HD_FinishPost'])}}}))
    return game, donor


def test_plan_maps_surfaces_and_texture_and_keeps_the_structure_open(world):
    game, donor = world
    plan = recover.build_plan(game, 'hippodrome', donor)
    ids = sorted(g.id for g in plan.generated)
    assert ids == ['prop/hippodrome/ground', 'texture/hippodrome/dirt']
    ground = next(g for g in plan.generated if g.id == 'prop/hippodrome/ground')
    assert ground.package == '/Game/Hippodrome/SM_HD_Ground'
    assert ground.settings['slot_materials'] == ['/Game/Hippodrome/Materials/M_HD_Grass']
    assert ground.settings['triangles'] == 1188
    assert ground.origin == 'adopted/hippodrome/loose_files'
    assert any('SM_HD_FinishPost' in item for item in plan.unmapped_outputs)
    assert plan.kept['adopted/hippodrome/textures'] == []
    assert plan.kept['adopted/hippodrome/loose_files'] == ['/Game/Hippodrome/SM_HD_FinishPost']


def test_apply_writes_pinned_sources_and_shrinks_the_adopted_records(world):
    game, donor = world
    plan = recover.build_plan(game, 'hippodrome', donor)
    changed = recover.apply(game, plan, donor)
    assert sorted(changed['created']) == ['prop/hippodrome/ground', 'texture/hippodrome/dirt']
    src = game / 'assets/prop/hippodrome/ground/src/SM_HD_Ground.glb'
    assert src.read_bytes() == b'ground glb'
    loaded = records.load_asset(game / 'assets/prop/hippodrome/ground/asset.toml')
    assert loaded.authority == 'generated' and loaded.kind == 'static-mesh'
    assert loaded.sources[0].sha256 == sha(b'ground glb')
    assert [o.package for o in loaded.outputs] == ['/Game/Hippodrome/SM_HD_Ground']
    assert loaded.recipe['importer'] == 'static-mesh' and loaded.recipe['settings']['collision'] == 'complex'
    texture = records.load_asset(game / 'assets/texture/hippodrome/dirt/asset.toml')
    assert texture.recipe['settings'] == {'srgb': True, 'compression': 'TC_DEFAULT', 'address': 'wrap'}
    # The adopted loose-files record keeps the structure and loses the surface and its companion file.
    left = records.load_asset(game / 'assets/adopted/hippodrome/loose_files/asset.toml')
    assert [o.package for o in left.outputs] == ['/Game/Hippodrome/SM_HD_FinishPost']
    verified_left = json.loads((game / 'assets/adopted/hippodrome/loose_files/verified.json').read_text())
    assert sorted(verified_left['files']) == ['unreal/Content/Hippodrome/SM_HD_FinishPost.uasset']
    # The textures record had only generated packages, so it is gone; the materials record is untouched.
    assert not (game / 'assets/adopted/hippodrome/textures').exists()
    assert [o.package for o in records.load_asset(game / 'assets/adopted/hippodrome/materials/asset.toml').outputs] \
        == ['/Game/Hippodrome/Materials/M_HD_Grass']


def test_second_apply_changes_nothing(world):
    game, donor = world
    recover.apply(game, recover.build_plan(game, 'hippodrome', donor), donor)
    before = {p: p.read_bytes() for p in game.rglob('*') if p.is_file()}
    plan = recover.build_plan(game, 'hippodrome', donor)
    assert all(g.origin == 'applied' for g in plan.generated)
    changed = recover.apply(game, plan, donor)
    assert changed == {'created': [], 'shrunk': [], 'deleted': [], 'retargeted': []}
    assert {p: p.read_bytes() for p in game.rglob('*') if p.is_file()} == before


def test_apply_points_consumers_at_the_records_now_owning_the_packages_they_use(world):
    game, donor = world

    def placement(name, refs, uses):
        record(game, f'object/hippodrome/{name}', f'''schema = 1
id = "object/hippodrome/{name}"
kind = "placement"
authority = "editor"
owner = "region/hippodrome"
references = [{', '.join(f'"{r}"' for r in refs)}]

[[outputs]]
package = "/Game/__ExternalActors__/V2/{name}"
''')
        write(game / f'unreal/Content/__ExternalActors__/V2/{name}.uasset', ''.join(f'{u}\0' for u in uses))
        verified(game, f'object/hippodrome/{name}', [f'unreal/Content/__ExternalActors__/V2/{name}.uasset'])
        body = json.loads((game / f'assets/object/hippodrome/{name}/verified.json').read_text())
        body['dependencies'] = {r: 'old' for r in refs}
        write(game / f'assets/object/hippodrome/{name}/verified.json', json.dumps(body))

    placement('ground', ['adopted/hippodrome/loose_files'], ['/Game/Hippodrome/SM_HD_Ground'])
    placement('both', ['adopted/hippodrome/loose_files'], ['/Game/Hippodrome/SM_HD_Ground',
                                                         '/Game/Hippodrome/SM_HD_FinishPost'])
    placement('post', ['adopted/hippodrome/loose_files'], ['/Game/Hippodrome/SM_HD_FinishPost'])
    placement('dirt', ['adopted/hippodrome/textures', 'adopted/hippodrome/materials'],
              ['/Game/Hippodrome/Textures/T_Dirt', '/Game/Hippodrome/Materials/M_HD_Grass'])
    # A record's copied donor sources may carry their own asset.toml: a source file, never read as a record.
    write(game / 'assets/object/hippodrome/ground/source/asset.toml', 'not a record')
    changed = recover.apply(game, recover.build_plan(game, 'hippodrome', donor), donor)
    refs = {n: records.load_asset(game / f'assets/object/hippodrome/{n}/asset.toml').references
            for n in ('ground', 'both', 'post', 'dirt')}
    # A shrunk record stays only while the consumer still uses what it kept; a deleted one is always replaced.
    assert refs == {'ground': ['prop/hippodrome/ground'],
                    'both': ['adopted/hippodrome/loose_files', 'prop/hippodrome/ground'],
                    'post': ['adopted/hippodrome/loose_files'],
                    'dirt': ['texture/hippodrome/dirt', 'adopted/hippodrome/materials']}
    assert sorted(changed['retargeted']) == ['object/hippodrome/both', 'object/hippodrome/dirt',
                                             'object/hippodrome/ground']
    # Not imported yet: the new owners record their state on import; untouched links keep theirs.
    deps = json.loads((game / 'assets/object/hippodrome/dirt/verified.json').read_text())['dependencies']
    assert deps == {'adopted/hippodrome/materials': 'old'}


def test_donor_bytes_that_differ_from_the_report_refuse_the_plan(world):
    game, donor = world
    write(donor / 'glb' / 'SM_HD_Ground.glb', b'rebuilt glb')
    with pytest.raises(recover.RecoverError, match='differs from the donor report'):
        recover.build_plan(game, 'hippodrome', donor)
    assert not (game / 'assets/prop').exists()


def test_a_package_in_no_adopted_record_is_reported_not_guessed(world):
    game, donor = world
    record(game, 'adopted/hippodrome/loose_files', '''schema = 1
id = "adopted/hippodrome/loose_files"
kind = "adopted"
authority = "editor"
owner = "shared/hippodrome/loose_files"
provenance = "test"
license = "test"

[[outputs]]
package = "/Game/Hippodrome/SM_HD_FinishPost"
''')
    with pytest.raises(recover.RecoverError, match='SM_HD_Ground is in no adopted'):
        recover.build_plan(game, 'hippodrome', donor)


def test_unknown_family_is_refused(world):
    game, donor = world
    with pytest.raises(recover.RecoverError, match='unknown family'):
        recover.build_plan(game, 'nope', donor)


def test_drop_outputs_keeps_the_other_lines_byte_for_byte():
    text = ('# head\nschema = 1\n\n[[outputs]]\npackage = "/Game/A/X"\n\n[[outputs]]\npackage = "/Game/A/Y"\n')
    assert recover._drop_outputs(text, {'/Game/A/X'}) == '# head\nschema = 1\n\n[[outputs]]\npackage = "/Game/A/Y"\n'


def test_belmonte_pieces_bind_their_owned_ground_material_and_skip_the_rest(tmp_path):
    """The belmonte donor report lists meshes as rows; a piece is recovered only when its one material is owned."""
    game = tmp_path / 'game'
    record(game, 'adopted/belmonte/generator', '''schema = 1
id = "adopted/belmonte/generator"
kind = "adopted"
authority = "editor"
owner = "shared/belmonte/generator"
provenance = "test"
license = "test"

[[outputs]]
package = "/Game/Belmonte/Materials/MI_BM_Ground"
''')
    record(game, 'adopted/belmonte/north-country', '''schema = 1
id = "adopted/belmonte/north-country"
kind = "adopted"
authority = "editor"
owner = "shared/belmonte/north-country"
provenance = "test"
license = "test"
references = ["adopted/belmonte/generator"]

[[outputs]]
package = "/Game/Belmonte/Meshes/SM_BM_NorthCountry_Piece000"

[[outputs]]
package = "/Game/Belmonte/Meshes/SM_BM_NorthCountry_Piece001"
''')
    verified(game, 'adopted/belmonte/north-country', ['unreal/Content/Belmonte/Meshes/SM_BM_NorthCountry_Piece000.uasset',
                                                      'unreal/Content/Belmonte/Meshes/SM_BM_NorthCountry_Piece001.uasset'])
    donor = tmp_path / 'build' / 'belmonte'
    write(donor / 'glb' / 'SM_BM_NorthCountry_Piece000.glb', b'piece zero')
    write(donor / 'glb' / 'SM_BM_NorthCountry_Piece001.glb', b'piece one')
    write(donor / 'build-report.json', json.dumps({'meshes': [
        {'name': 'SM_BM_NorthCountry_Piece000', 'path': 'glb/SM_BM_NorthCountry_Piece000.glb', 'triangles': 13393,
         'sha256': sha(b'piece zero'), 'slots': ['Ground']},
        {'name': 'SM_BM_NorthCountry_Piece001', 'path': 'glb/SM_BM_NorthCountry_Piece001.glb', 'triangles': 900,
         'sha256': sha(b'piece one'), 'slots': ['Ground']}]}))
    write(donor.parent / 'products' / 'belmonte' / 'materials.json', json.dumps({'bindings': {
        'SM_BM_NorthCountry_Piece000': ['/Game/Belmonte/Materials/MI_BM_Ground.MI_BM_Ground'],
        'SM_BM_NorthCountry_Piece001': ['/Game/Belmonte/Materials/MI_BM_Other.MI_BM_Other']}}))
    plan = recover.build_plan(game, 'belmonte', donor)
    assert [g.id for g in plan.generated] == ['prop/belmonte/north-country-piece000']
    gen = plan.generated[0]
    assert gen.settings == {'slot_materials': ['/Game/Belmonte/Materials/MI_BM_Ground'], 'triangles': 13393}
    assert gen.references == ['adopted/belmonte/generator']
    assert plan.unmapped_outputs == ['glb/SM_BM_NorthCountry_Piece001.glb (its material [\'/Game/Belmonte/Materials/MI_BM_Other\'] is owned by no adopted record)']
    recover.apply(game, plan, donor)
    left = records.load_asset(game / 'assets/adopted/belmonte/north-country/asset.toml')
    assert [o.package for o in left.outputs] == ['/Game/Belmonte/Meshes/SM_BM_NorthCountry_Piece001']
    assert records.load_asset(game / 'assets/prop/belmonte/north-country-piece000/asset.toml').authority == 'generated'


def test_repartition_check_stays_clean_on_the_real_game():
    """Recovery leaves nothing for adoption's repartition to rewrite: no record file would change, nothing deleted.
    Source copies are reported too, since a checkout without hydrated LFS bytes differs from its donor copies; they
    are not record files, so they are not part of this check."""
    adopt = importlib.import_module('adopt')
    report = adopt.repartition(recover.GAME, check_only=True)
    record_writes = [p for p in report['write'] if p.endswith(('asset.toml', 'verified.json'))]
    assert record_writes == []
    assert report['delete'] == []


def test_partition_honours_a_units_map_below_a_folder_with_few_packages():
    """A `[[units]]` folder below a folder with one package still puts that package in its mapped unit."""
    adopt = importlib.import_module('adopt')
    units = adopt.Units({'/Game/Experiments/IslandTerrain/v1_atomic/Sea': 'generator'},
                        {'generator': {'about': 'generator'}})
    rules = {'/Game/Experiments/IslandTerrain/v1_atomic': units}
    found = adopt.partition(['/Game/Experiments/IslandTerrain/v1_atomic/Sea'], 'Experiments', groups=rules)
    assert list(found) == ['adopted/experiments/islandterrain/v1-atomic/generator']


def test_city_surfaces_recover_pieces_of_hull_free_sources_only(tmp_path):
    game, donor = tmp_path / 'game', tmp_path / 'donor'
    dest = '/Game/Experiments/CitySurfaces/v1_128m'
    record(game, 'adopted/experiments/citysurfaces/v1-128m/street', f'''schema = 1
id = "adopted/experiments/citysurfaces/v1-128m/street"
kind = "adopted"
authority = "editor"
owner = "shared/citysurfaces/street"
provenance = "test"
license = "test"

[[outputs]]
package = "{dest}/HD_Street_0"

[[outputs]]
package = "{dest}/HD_Arcade_0"
''')
    record(game, 'adopted/japan/materials', '''schema = 1
id = "adopted/japan/materials"
kind = "adopted"
authority = "editor"
owner = "shared/japan/materials"
provenance = "test"
license = "test"

[[outputs]]
package = "/Game/Japan/Hidamari/Materials/MI_HD_asphalt"
''')
    fbx = {'HD_Street_0': b'street fbx', 'HD_Arcade_0': b'arcade fbx', 'HD_Sea': b'sea fbx'}
    for name, data in fbx.items():
        write(donor / name.rsplit('_', 1)[0].replace('HD_Sea', 'HD_Sea') / f'{name}.fbx', data)
    tile = lambda name, hulls=0: {'name': name, 'sha256': sha(fbx[name]), 'triangles': 12, 'collision_hulls': hulls}
    write(donor / 'manifest.json', json.dumps({'sources': {
        'HD_Street': {'source_collision_hulls': 0, 'tiles': [tile('HD_Street_0')]},
        'HD_Arcade': {'source_collision_hulls': 2, 'tiles': [tile('HD_Arcade_0', 2)]},
        'HD_Sea': {'source_collision_hulls': 0, 'tiles': [tile('HD_Sea')]}}}))
    bind = lambda name: [{'name': name, 'triangles': 12, 'asset': f'{dest}/{name}.{name}',
                          'material': '/Game/Japan/Hidamari/Materials/MI_HD_asphalt.MI_HD_asphalt'}]
    write(donor / 'import-report.json', json.dumps({'HD_Street': bind('HD_Street_0'), 'HD_Arcade': bind('HD_Arcade_0'),
                                                    'HD_Sea': bind('HD_Sea')}))
    plan = recover.build_plan(game, 'experiments/citysurfaces', donor)
    (street,) = plan.generated
    assert street.id == 'prop/citysurfaces/street-0' and street.package == f'{dest}/HD_Street_0'
    assert street.settings == {'slot_materials': ['/Game/Japan/Hidamari/Materials/MI_HD_asphalt'], 'triangles': 12,
                               'collision': 'complex', 'full_precision_uvs': True}
    assert street.references == ['adopted/japan/materials']
    # A hull source stays open (no V2 UCX import); a piece no adopted record holds is reported, not guessed.
    assert any('HD_Arcade_0' in u and 'UCX' in u for u in plan.unmapped_outputs)
    assert any('HD_Sea' in u for u in plan.unmapped_outputs)
    assert plan.kept['adopted/experiments/citysurfaces/v1-128m/street'] == [f'{dest}/HD_Arcade_0']
