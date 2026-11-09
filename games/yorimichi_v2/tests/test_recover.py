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


def test_city_surfaces_recover_every_piece_with_its_collision(tmp_path):
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
    record(game, 'adopted/japan/road', '''schema = 1
id = "adopted/japan/road"
kind = "adopted"
authority = "editor"
owner = "shared/japan/road"
provenance = "test"
license = "test"

[[outputs]]
package = "/Game/Japan/Materials/MI_Road"
''')
    fbx = {'HD_Street_0': b'street fbx', 'HD_Arcade_0': b'arcade fbx', 'HD_Sea': b'sea fbx'}
    for name, data in fbx.items():
        write(donor / name.rsplit('_', 1)[0].replace('HD_Sea', 'HD_Sea') / f'{name}.fbx', data)
    tile = lambda name, hulls=0: {'name': name, 'sha256': sha(fbx[name]), 'triangles': 12, 'collision_hulls': hulls}
    write(donor / 'manifest.json', json.dumps({'sources': {
        'HD_Street': {'source_collision_hulls': 0, 'tiles': [tile('HD_Street_0')]},
        'HD_Arcade': {'source_collision_hulls': 2, 'tiles': [tile('HD_Arcade_0', 2)],
                      'source_material_slots': ['HDS_asphalt', 'HDS_road']},
        'HD_Sea': {'source_collision_hulls': 0, 'tiles': [tile('HD_Sea')]}}}))
    bind = lambda name: [{'name': name, 'triangles': 12, 'asset': f'{dest}/{name}.{name}',
                          'material': '/Game/Japan/Hidamari/Materials/MI_HD_asphalt.MI_HD_asphalt'}]
    write(donor / 'import-report.json', json.dumps({'HD_Street': bind('HD_Street_0'), 'HD_Arcade': bind('HD_Arcade_0'),
                                                    'HD_Sea': bind('HD_Sea')}))
    plan = recover.build_plan(game, 'experiments/citysurfaces', donor)
    street, arcade = sorted(plan.generated, key=lambda g: g.id, reverse=True)
    assert street.id == 'prop/citysurfaces/street-0' and street.package == f'{dest}/HD_Street_0'
    assert street.settings == {'slot_materials': ['/Game/Japan/Hidamari/Materials/MI_HD_asphalt'], 'triangles': 12,
                               'collision': 'complex', 'full_precision_uvs': True}
    assert street.references == ['adopted/japan/materials']
    # A hull source's pieces import their UCX hulls, each with its own count; a piece no record holds is reported.
    assert arcade.id == 'prop/citysurfaces/arcade-0'
    assert (arcade.settings['collision'], arcade.settings['hulls']) == ('simple_and_complex', 2)
    # A source with several authored slots binds each by name (the donor's material_paths), never the report's one.
    assert arcade.settings['slot_map'] == {'HDS_asphalt': '/Game/Japan/Hidamari/Materials/MI_HD_asphalt',
                                           'HDS_road': '/Game/Japan/Materials/MI_Road'}
    assert 'slot_materials' not in arcade.settings
    assert arcade.references == ['adopted/japan/materials', 'adopted/japan/road']
    assert any('HD_Sea' in u for u in plan.unmapped_outputs)
    assert plan.kept['adopted/experiments/citysurfaces/v1-128m/street'] == []
    recover.apply(game, plan, donor)
    loaded = records.load_asset(game / 'assets/prop/citysurfaces/arcade-0/asset.toml')
    assert loaded.recipe['settings']['slot_map']['HDS_road'] == '/Game/Japan/Materials/MI_Road'


def test_train_vehicles_recover_their_lod_chain_slots_and_boxes(tmp_path, monkeypatch):
    game, donor = tmp_path / 'game', tmp_path / 'donor'
    root = '/Game/BelmonteTrain'
    mat0, mat1 = f'{root}/Source/SM_BT_Tender/LOD0/M_BT_Brass', f'{root}/Source/SM_BT_Tender/LOD1/M_BT_Brass'
    record(game, 'adopted/belmontetrain/tender', f'''schema = 1
id = "adopted/belmontetrain/tender"
kind = "adopted"
authority = "editor"
owner = "shared/belmontetrain/tender"
provenance = "test"
license = "test"

[[outputs]]
package = "{root}/SM_BT_Tender"

[[outputs]]
package = "{root}/Doors/SM_BTD_Tender_side_l"

[[outputs]]
package = "{mat0}"

[[outputs]]
package = "{mat1}"
''')
    glb = {'service/glb/SM_BT_Tender_LOD0.glb': b'lod0', 'tender/SM_BT_Tender_LOD1.glb': b'lod1',
           'service/glb/doors/SM_BTD_Tender_side_l.glb': b'door'}
    for rel, data in glb.items():
        write(donor / rel, data)
    box = [-10.0, -5.0, 0.0, 10.0, 5.0, 4.0]
    leaf = {'mesh': f'{root}/Doors/SM_BTD_Tender_side_l.SM_BTD_Tender_side_l',
            'glb': 'service/glb/doors/SM_BTD_Tender_side_l.glb'}
    vehicle = {'name': 'SM_BT_Tender', 'mesh': f'{root}/SM_BT_Tender.SM_BT_Tender', 'collision': [box],
               'levels': ['service/glb/SM_BT_Tender_LOD0.glb', 'tender/SM_BT_Tender_LOD1.glb'],
               'doors': [{'leaves': [leaf, {'mesh': 'unmodelled'}]}]}
    write(donor / 'service/service.json', json.dumps({'consist': {'vehicles': [vehicle]}, 'furniture': {}}))
    write(donor / 'service/import-report.json', json.dumps({'vehicles': {'SM_BT_Tender': {'sources': {
        'SM_BT_Tender_LOD0.glb': sha(b'lod0'), 'SM_BT_Tender_LOD1.glb': sha(b'lod1')}}}}))
    saved = {f'{root}/SM_BT_Tender': {'slots': [['M_BT_Brass', mat0], ['M_BT_Brass_2', mat1]],
                                      'lods': [[1.0, 12, [0]], [0.6, 4, [1]]], 'boxes': [[0, 0, 2, 20, 10, 4]]},
             f'{root}/Doors/SM_BTD_Tender_side_l': {'slots': [['M_BT_Brass', mat1]], 'lods': [[2.0, 2, [0]]],
                                                    'boxes': []}}
    monkeypatch.setattr(recover, 'TRAIN_SAVED', write(tmp_path / 'saved.json', json.dumps({'meshes': saved})))
    plan = recover.build_plan(game, 'belmontetrain', donor)
    tender, door = sorted(plan.generated, key=lambda g: g.id)
    assert (tender.id, door.id) == ('prop/belmontetrain/tender', 'prop/belmontetrain/tender-door-side-l')
    assert tender.owner == door.owner == 'shared/belmontetrain/tender'
    # The chain names each level's own source, so the LOD order is in the recipe (and its fingerprint).
    assert tender.settings == {'lod_chain': [['src/SM_BT_Tender_LOD0.glb', 1.0, 12, [0]],
                                             ['src/SM_BT_Tender_LOD1.glb', 0.6, 4, [1]]],
                               'slots': saved[f'{root}/SM_BT_Tender']['slots'], 'collision': 'boxes', 'boxes': [box]}
    assert door.settings['boxes'] == [] and door.references == ['adopted/belmontetrain/tender']
    assert plan.kept['adopted/belmontetrain/tender'] == [mat0, mat1]
    recover.apply(game, plan, donor)
    asset = records.load_asset(game / 'assets/prop/belmontetrain/tender/asset.toml')
    assert [s.path for s in asset.sources] == ['src/SM_BT_Tender_LOD0.glb', 'src/SM_BT_Tender_LOD1.glb']
    assert asset.recipe['settings']['lod_chain'][1] == ['src/SM_BT_Tender_LOD1.glb', 0.6, 4, [1]]
    assert asset.recipe['settings']['boxes'] == [box]
    assert (game / 'assets/prop/belmontetrain/tender/src/SM_BT_Tender_LOD1.glb').read_bytes() == b'lod1'
    again = recover.apply(game, recover.build_plan(game, 'belmontetrain', donor), donor)
    assert again['created'] == [] and again['shrunk'] == []
    # A donor box that is not the saved one stops the plan: the recipe would move the collision.
    vehicle['collision'] = [[-10.0, -5.0, 0.0, 10.0, 5.0, 9.0]]
    write(donor / 'service/service.json', json.dumps({'consist': {'vehicles': [vehicle]}, 'furniture': {}}))
    with pytest.raises(recover.RecoverError, match='collision boxes'):
        recover.build_plan(game, 'belmontetrain', donor)


# --- Small source-less families: skatepark, megapark seam, swordcamp, fx, villageatomic ---------------------------------
def adopted(game: Path, folder: str, packages: list[str], refs: str = ''):
    outputs = ''.join(f'\n[[outputs]]\npackage = "{p}"\n' for p in packages)
    record(game, f'adopted/{folder}', f'''schema = 1
id = "adopted/{folder}"
kind = "adopted"
authority = "editor"
owner = "shared/{folder}"
provenance = "test"
license = "test"
{refs}{outputs}''')


def test_skatepark_binds_slots_by_name_and_reuses_the_steel_maps_for_painted(tmp_path):
    game, donor = tmp_path / 'game', tmp_path / 'donor'
    root = '/Game/SkatePark'
    adopted(game, 'skatepark/materials', [f'{root}/Materials/M_Pier_concrete', f'{root}/Materials/M_Pier_steel'])
    adopted(game, 'skatepark/textures', [f'{root}/Textures/T_Pier_steel_albedo', f'{root}/Textures/T_Pier_steel_normal',
                                         f'{root}/Textures/T_Pier_painted_albedo', f'{root}/Textures/T_Pier_painted_normal'])
    adopted(game, 'skatepark/loose_files', [f'{root}/SM_SkatePath', f'{root}/SM_SkateParkPlanting'])
    adopted(game, 'skatepark/board', [f'{root}/Board/SM_SkateDeck', f'{root}/Board/M_BoardDissolve'])
    adopted(game, 'japan/materials/base-materials', ['/Game/Japan/Materials/M_Village'])
    files = {'assets/SM_SkatePath.fbx': b'path', 'assets/SM_SkateParkPlanting.fbx': b'planting', 'board/SM_SkateDeck.fbx': b'deck',
             'textures/steel-albedo.png': b'sa', 'textures/steel-normal.png': b'sn'}
    for rel, data in files.items():
        write(donor / rel, data)
    write(donor / 'textures/textures.json', json.dumps({'steel': {'maps': {'albedo': 'steel-albedo.png', 'normal': 'steel-normal.png'},
        'sha256': {'albedo': sha(b'sa'), 'normal': sha(b'sn')}}}))
    write(donor / 'runtime-park.json', json.dumps({'meshes': [{'name': 'SM_SkatePath', 'blocks': True},
                                                              {'name': 'SM_SkateParkPlanting', 'blocks': False}]}))
    write(donor / 'build-report.json', json.dumps({
        'identity': {'exports': {rel: sha(files[rel]) for rel in files if rel.endswith('.fbx')}},
        'material_slots': {'SM_SkatePath': ['Pier_concrete', 'Pier_steel'], 'SM_SkateParkPlanting': ['Pier_concrete']},
        'meshes': {'SM_SkatePath': {'triangles': 10}, 'SM_SkateParkPlanting': {'triangles': 4}, 'SM_SkateDeck': {'triangles': 6}}}))
    plan = recover.build_plan(game, 'skatepark', donor)
    by_id = {g.id: g for g in plan.generated}
    assert len(by_id) == 7
    path, planting, deck = (by_id[f'prop/skatepark/{n}'] for n in ('skate-path', 'skate-park-planting', 'skate-deck'))
    assert path.settings == {'slot_map': {'Pier_concrete': f'{root}/Materials/M_Pier_concrete',
                                          'Pier_steel': f'{root}/Materials/M_Pier_steel'}, 'triangles': 10, 'collision': 'complex',
                                          'allow_cpu_access': True, 'double_sided': False}
    assert planting.settings['collision'] == 'none'                      # a floor paint piece has no shapes
    assert deck.settings == {'slot_materials': ['/Game/Japan/Materials/M_Village'], 'triangles': 6, 'collision': 'none'}     # no cpu access
    assert deck.references == ['adopted/japan/materials/base-materials']
    # The donor's 'painted' surface is the steel maps under the painted names; colour maps are sRGB, normals are not.
    painted = by_id['texture/skatepark/pier-painted-normal']
    assert painted.package == f'{root}/Textures/T_Pier_painted_normal' and painted.source.name == 'steel-normal.png'
    assert painted.settings == {'srgb': False, 'compression': 'TC_NORMALMAP'}
    assert by_id['texture/skatepark/pier-steel-albedo'].settings == {'srgb': True, 'compression': 'TC_DEFAULT'}
    assert plan.kept['adopted/skatepark/loose_files'] == [] and plan.kept['adopted/skatepark/board'] == [f'{root}/Board/M_BoardDissolve']
    assert plan.kept['adopted/skatepark/materials'] == [f'{root}/Materials/M_Pier_concrete', f'{root}/Materials/M_Pier_steel']
    # A material no record owns leaves the piece open, reported.
    (game / 'assets/adopted/skatepark/materials/asset.toml').unlink()
    open_plan = recover.build_plan(game, 'skatepark', donor)
    assert any('SM_SkatePath' in u and 'M_Pier_concrete' in u for u in open_plan.unmapped_outputs)
    assert 'prop/skatepark/skate-path' not in {g.id for g in open_plan.generated}


def test_megapark_seam_recovers_both_seam_meshes_and_ignores_the_sections(tmp_path):
    game, donor = tmp_path / 'game', tmp_path / 'donor'
    root = '/Game/MegaPark'
    adopted(game, 'megapark/seam', [f'{root}/Materials/MI_aa_Seam', f'{root}/Meshes/SM_MP_Seam', f'{root}/Meshes/UC_MP_Seam'])
    adopted(game, 'megapark/cell-x150-zm450', [f'{root}/Meshes/SM_MP_0123'])
    export = lambda name, slots: {'asset': name, 'primary': f'{name}.fbx', 'sha256': sha(name.encode()), 'triangles': 8,
                                  'metadata': {'slots': slots, 'collision_hulls': 0}}
    write(donor / 'fbx/manifest.json', json.dumps({'exports': [
        export('SM_MP_Seam', ['M_aa_Seam']), export('UC_MP_Seam', ['M_Collision']), export('SM_MP_0123', ['M_bb'])]}))
    for name in ('SM_MP_Seam', 'UC_MP_Seam', 'SM_MP_0123'):
        write(donor / f'fbx/{name}.fbx', name)
    plan = recover.build_plan(game, 'megapark', donor)
    render, collision = sorted(plan.generated, key=lambda g: g.id)
    assert (render.id, collision.id) == ('prop/megapark/seam', 'prop/megapark/seam-collision')
    assert render.settings == {'slot_map': {'M_aa_Seam': f'{root}/Materials/MI_aa_Seam'}, 'triangles': 8,
                               'collision': 'complex', 'full_precision_uvs': True, 'allow_cpu_access': True,
                               'double_sided': False}
    assert collision.settings['double_sided'] is False and 'slot_map' not in collision.settings and collision.references == []
    assert plan.kept['adopted/megapark/seam'] == [f'{root}/Materials/MI_aa_Seam']     # the material instance stays editor-owned
    assert plan.kept['adopted/megapark/cell-x150-zm450'] == [f'{root}/Meshes/SM_MP_0123']


def test_swordcamp_solid_props_keep_their_hull_and_the_atlas_is_srgb(tmp_path):
    game, donor = tmp_path / 'game', tmp_path / 'donor'
    adopted(game, 'swordcamp/assets', ['/Game/SwordCamp/Assets/SM_CampBales', '/Game/SwordCamp/Assets/SM_RoninKatana'])
    adopted(game, 'swordcamp/materials', ['/Game/SwordCamp/Materials/M_SwordCamp'])
    adopted(game, 'swordcamp/textures', ['/Game/SwordCamp/Textures/T_SwordCampAtlas'])
    write(donor / 'swordcamp_atlas.jpg', 'atlas')
    export = lambda name, hulls: {'asset': name, 'primary': f'{name}.fbx', 'sha256': sha(name.encode()), 'triangles': 20,
                                  'metadata': {'slots': ['M_SwordCamp'], 'collision_hulls': hulls}}
    write(donor / 'fbx/manifest.json', json.dumps({'exports': [export('SM_CampBales', 1), export('SM_RoninKatana', 0)]}))
    for name in ('SM_CampBales', 'SM_RoninKatana'):
        write(donor / f'fbx/{name}.fbx', name)
    plan = recover.build_plan(game, 'swordcamp', donor)
    by_id = {g.id: g for g in plan.generated}
    assert by_id['texture/swordcamp/atlas'].settings == {'srgb': True, 'max_texture_size': 2048,
                                                              'lod_group': 'TEXTUREGROUP_WORLD'}
    assert by_id['prop/swordcamp/camp-bales'].settings == {'slot_materials': ['/Game/SwordCamp/Materials/M_SwordCamp'],
                                                           'triangles': 20, 'collision': 'simple_and_complex', 'hulls': 1}
    assert by_id['prop/swordcamp/ronin-katana'].settings['collision'] == 'none'
    assert plan.kept['adopted/swordcamp/materials'] == ['/Game/SwordCamp/Materials/M_SwordCamp']
    # A hull count that contradicts the donor's solid-prop list stops the plan: the collision would change.
    write(donor / 'fbx/manifest.json', json.dumps({'exports': [export('SM_CampBales', 0), export('SM_RoninKatana', 0)]}))
    with pytest.raises(recover.RecoverError, match='collision policy'):
        recover.build_plan(game, 'swordcamp', donor)


def test_fx_recovers_the_sprite_textures_only(tmp_path):
    game, donor = tmp_path / 'game', tmp_path / 'donor'
    adopted(game, 'fx/textures', ['/Game/FX/Textures/T_FX_Glow'])
    adopted(game, 'fx/loose_files', ['/Game/FX/M_FX_Additive'])
    write(donor / 'T_FX_Glow.png', 'glow')
    write(donor / 'unreal_import.json', json.dumps({'textures': ['/Game/FX/Textures/T_FX_Glow.T_FX_Glow',
                                                                 '/Game/FX/Textures/T_FX_Gone.T_FX_Gone']}))
    plan = recover.build_plan(game, 'fx', donor)
    (glow,) = plan.generated
    assert (glow.id, glow.kind, glow.settings) == ('texture/fx/glow', 'texture', {'srgb': False, 'lod_group': 'TEXTUREGROUP_EFFECTS'})
    assert any('T_FX_Gone' in u for u in plan.unmapped_outputs)
    assert plan.kept == {'adopted/fx/textures': [], 'adopted/fx/loose_files': ['/Game/FX/M_FX_Additive']}


def test_villageatomic_follows_the_parent_collision_policy_in_a_one_record_family(tmp_path):
    game = tmp_path / 'game'
    donor = tmp_path / 'build' / 'atomic_regions' / 'village'
    dest = '/Game/Experiments/VillageAtomic/v1_atomic'
    adopted(game, 'experiments/villageatomic', [f'{dest}/Village_Sign', f'{dest}/Village_Ground', f'{dest}/Village_Planting_cell_0_0'])
    adopted(game, 'japan/materials/base-materials', ['/Game/Japan/Materials/M_Village'])
    names = {'Village_Sign': 1, 'Village_Ground': 0, 'Village_Planting_cell_0_0': 0}
    export = lambda name, hulls: {'asset': name, 'primary': f'{name}.fbx', 'sha256': sha(name.encode()), 'triangles': 30,
                                  'metadata': {'slots': ['VillagePalette'], 'collision_hulls': hulls}}
    write(donor / 'assets/manifest.json', json.dumps({'exports': [export(n, h) for n, h in names.items()]}))
    for name in names:
        write(donor / f'assets/{name}.fbx', name)
    write(tmp_path / 'build' / 'village' / 'atomic-manifest.json', json.dumps({'parents': {
        'Village_Sign': {'collision': 'simple_and_complex', 'pieces': [{'name': 'Village_Sign', 'native_triangles': 30}]},
        'Village_Ground': {'collision': 'complex_as_simple', 'pieces': [{'name': 'Village_Ground', 'native_triangles': 29}]},
        'Village_Planting': {'collision': 'simple_and_complex', 'pieces': [{'name': 'Village_Planting_cell_0_0', 'native_triangles': 30}]}}}))
    plan = recover.build_plan(game, 'experiments/villageatomic', donor)
    by_id = {g.id: g for g in plan.generated}
    assert by_id['prop/villageatomic/sign'].settings == {'slot_materials': ['/Game/Japan/Materials/M_Village'], 'triangles': 30,
                                                         'collision': 'simple_and_complex', 'hulls': 1}
    # The ground's one degenerate triangle goes in the donor's legacy import (native 29 of 30), single-sided as the old package.
    assert by_id['prop/villageatomic/ground'].settings == {
        'slot_materials': ['/Game/Japan/Materials/M_Village'], 'triangles': 29, 'collision': 'complex', 'legacy_fbx': True,
        'double_sided': False}
    assert by_id['prop/villageatomic/planting-cell-0-0'].settings['hulls'] == 0       # a render-only leaf keeps no shapes
    assert plan.kept == {'adopted/experiments/villageatomic': []}
    changed = recover.apply(game, plan, donor)
    assert len(changed['created']) == 3 and changed['deleted'] == ['adopted/experiments/villageatomic']
    again = recover.apply(game, recover.build_plan(game, 'experiments/villageatomic', donor), donor)
    assert again['created'] == []


def japan_adopted(game: Path, record_id: str, *packages: str):
    """A source-less adopted record owning the given packages."""
    outputs = ''.join(f'\n[[outputs]]\npackage = "{p}"\n' for p in packages)
    record(game, record_id, f'''schema = 1
id = "{record_id}"
kind = "adopted"
authority = "editor"
owner = "shared/{record_id}"
provenance = "test"
license = "test"
{outputs}''')


def atomic(donor: Path, step: str, pieces: dict, **per_piece):
    """A donor atomic step: assets/manifest.json plus one FBX per piece (pieces: name -> triangles, slots)."""
    exports = []
    for name, (triangles, slots) in pieces.items():
        data = f'{name} fbx'.encode()
        write(donor / 'atomic_regions' / step / 'assets' / f'{name}.fbx', data)
        exports.append({'asset': name, 'primary': f'{name}.fbx', 'sha256': sha(data), 'triangles': triangles,
                        'metadata': {'collision_hulls': 0, 'slots': slots,
                                     'uv_channels': ['UVMap', 'Piece1', 'Piece2', 'Piece3', 'Piece4']
                                     if per_piece.get('bake') else ['UVMap']}})
    write(donor / 'atomic_regions' / step / 'assets' / 'manifest.json',
          json.dumps({'schema': 1, 'complete': True, 'exports': exports}))


def japan_donor(tmp_path):
    """Every atomic step the Japan planners read, empty unless a test fills it."""
    donor = tmp_path / 'donor'
    for step in ('vehicle_bike', 'vehicle_sailboat', 'zeppelin', 'mega', 'treehouse_surfaces', 'southwest', 'lake'):
        atomic(donor, step, {})
    write(donor / 'bike/import-report.json', json.dumps({'parts': {}}))
    return donor


def test_lake_binds_water_to_its_own_material_and_a_one_record_family_is_recovered(tmp_path):
    game, donor = tmp_path / 'game', japan_donor(tmp_path)
    japan_adopted(game, 'adopted/japan/lake', '/Game/Japan/Lake/Pieces/Lake_Cabin', '/Game/Japan/Lake/Pieces/Lake_Water')
    japan_adopted(game, 'adopted/japan/materials/base-materials', '/Game/Japan/Materials/M_Village',
            '/Game/Japan/Materials/M_ForestLakeWater')
    atomic(donor, 'lake', {'Lake_Cabin': (20910, ['LakePalette']), 'Lake_Water': (160, ['LakePalette'])})
    plan = recover.build_plan(game, 'japan/lake', donor)
    cabin, water = sorted(plan.generated, key=lambda g: g.id)
    assert (cabin.id, water.id) == ('prop/lake/cabin', 'prop/lake/water')
    assert cabin.settings == {'slot_materials': ['/Game/Japan/Materials/M_Village'], 'triangles': 20910, 'double_sided': False,
                              'collision': 'complex'}
    assert water.settings['slot_materials'] == ['/Game/Japan/Materials/M_ForestLakeWater']
    assert cabin.references == ['adopted/japan/materials/base-materials'] and cabin.origin == 'adopted/japan/lake'
    assert plan.kept['adopted/japan/lake'] == []
    changed = recover.apply(game, plan, donor)
    assert sorted(changed['created']) == ['prop/lake/cabin', 'prop/lake/water'] and changed['deleted'] == ['adopted/japan/lake']
    assert (game / 'assets/prop/lake/water/src/Lake_Water.fbx').read_bytes() == b'Lake_Water fbx'


def test_a_lake_piece_with_other_slots_or_a_missing_material_is_reported_not_guessed(tmp_path):
    game, donor = tmp_path / 'game', japan_donor(tmp_path)
    japan_adopted(game, 'adopted/japan/lake', '/Game/Japan/Lake/Pieces/Lake_Cabin', '/Game/Japan/Lake/Pieces/Lake_Water')
    japan_adopted(game, 'adopted/japan/materials/base-materials', '/Game/Japan/Materials/M_Village')
    atomic(donor, 'lake', {'Lake_Cabin': (20910, ['Other']), 'Lake_Water': (160, ['LakePalette'])})
    plan = recover.build_plan(game, 'japan/lake', donor)
    assert plan.generated == []
    assert any('Lake_Cabin' in u and 'slots differ' in u for u in plan.unmapped_outputs)
    assert any('Lake_Water' in u and 'M_ForestLakeWater' in u for u in plan.unmapped_outputs)
    assert plan.kept['adopted/japan/lake'] == ['/Game/Japan/Lake/Pieces/Lake_Cabin', '/Game/Japan/Lake/Pieces/Lake_Water']


def test_vehicle_and_kit_meshes_bind_the_materials_of_the_donor_imports(tmp_path):
    game, donor = tmp_path / 'game', japan_donor(tmp_path)
    assets = '/Game/Japan/Assets'
    japan_adopted(game, 'adopted/japan/assets/bike', f'{assets}/BK_Frame', f'{assets}/BK_WheelFront')
    japan_adopted(game, 'adopted/japan/assets/sailboat', f'{assets}/SB_Sail', f'{assets}/SB_Hull')
    japan_adopted(game, 'adopted/japan/assets/zeppelin', f'{assets}/ZP_Airship', f'{assets}/ZP_Gate')
    japan_adopted(game, 'adopted/japan/assets/mega-park-pieces', f'{assets}/Mega_Ramp', f'{assets}/Mega_Trim')
    japan_adopted(game, 'adopted/japan/assets/treehouse', f'{assets}/TH_P_bell')
    japan_adopted(game, 'adopted/japan/assets/rock', f'{assets}/Rock_A')
    japan_adopted(game, 'adopted/japan/materials/base-materials', *(f'/Game/Japan/Materials/{m}' for m in (
        'M_Village', 'M_Bike', 'M_SailboatCloth', 'M_SailboatWake', 'M_ZeppelinFabric')))
    atomic(donor, 'vehicle_bike', {'BK_Frame': (25666, ['BikePalette']), 'BK_WheelFront': (26060, ['BikePalette'])})
    # Unreal drops duplicate points of a vehicle part: the report's count is the one the import keeps.
    write(donor / 'bike/import-report.json', json.dumps({'parts': {'BK_Frame': {'source_triangles': 25666, 'triangles': 25094},
                                                                   'BK_WheelFront': {'source_triangles': 26060, 'triangles': 26060}}}))
    atomic(donor, 'vehicle_sailboat', {'SB_Sail': (324, ['SailboatPalette']), 'SB_Hull': (1028, ['SailboatPalette'])})
    atomic(donor, 'zeppelin', {'ZP_Airship': (13688, ['ZeppelinPalette', 'ZeppelinFabric']), 'ZP_Gate': (528, ['ZeppelinPalette'])})
    atomic(donor, 'mega', {'Mega_Ramp': (22462, ['MegaPalette']), 'Mega_Trim': (44, ['MegaPalette'])})
    plan = recover.build_plan(game, 'japan/assets', donor)
    by_id = {g.id: g for g in plan.generated}
    assert sorted(by_id) == ['prop/bike/frame', 'prop/mega/ramp', 'prop/mega/trim', 'prop/sailboat/hull',
                             'prop/sailboat/sail', 'prop/zeppelin/airship', 'prop/zeppelin/gate']
    assert by_id['prop/bike/frame'].settings == {'slot_materials': ['/Game/Japan/Materials/M_Bike'], 'triangles': 25094}
    assert by_id['prop/sailboat/sail'].settings['slot_materials'] == ['/Game/Japan/Materials/M_SailboatCloth']
    assert by_id['prop/sailboat/hull'].settings['slot_materials'] == ['/Game/Japan/Materials/M_Village']
    assert by_id['prop/zeppelin/airship'].settings['slot_map'] == {
        'ZeppelinPalette': '/Game/Japan/Materials/M_Village', 'ZeppelinFabric': '/Game/Japan/Materials/M_ZeppelinFabric'}
    assert by_id['prop/zeppelin/gate'].settings['collision'] == 'complex'
    # The look-only trim keeps no physics shape; the ramp is complex-as-simple.
    assert (by_id['prop/mega/trim'].settings['collision'], by_id['prop/mega/trim'].settings['boxes']) == ('boxes', [])
    assert by_id['prop/mega/ramp'].settings['collision'] == 'complex'
    reasons = ' '.join(plan.unmapped_outputs)
    assert 'BK_WheelFront' in reasons and 'allow_cpu_access' in reasons      # the importer cannot set CPU access
    assert 'TH_P_bell' in reasons and 'report_meshes' in reasons and 'Rock_A' in reasons
    assert plan.kept['adopted/japan/assets/sailboat'] == []
    assert plan.kept['adopted/japan/assets/bike'] == [f'{assets}/BK_WheelFront']


def test_a_bike_report_that_disagrees_with_the_export_stops_the_plan(tmp_path):
    game, donor = tmp_path / 'game', japan_donor(tmp_path)
    japan_adopted(game, 'adopted/japan/assets/bike', '/Game/Japan/Assets/BK_Frame')
    japan_adopted(game, 'adopted/japan/materials/base-materials', '/Game/Japan/Materials/M_Bike')
    atomic(donor, 'vehicle_bike', {'BK_Frame': (25666, ['BikePalette'])})
    write(donor / 'bike/import-report.json', json.dumps({'parts': {'BK_Frame': {'source_triangles': 100, 'triangles': 90}}}))
    with pytest.raises(recover.RecoverError, match='disagree'):
        recover.build_plan(game, 'japan/assets', donor)


def test_treehouse_surfaces_bind_each_slot_and_keep_the_bake_and_collision_of_their_parent(tmp_path):
    game, donor = tmp_path / 'game', japan_donor(tmp_path)
    mats = '/Game/Japan/Treehouse/Materials'
    japan_adopted(game, 'adopted/japan/treehouse/dressing-m2-2', '/Game/Japan/Treehouse/Pieces/TH_Dressing_cell_-2_2_Piece0')
    japan_adopted(game, 'adopted/japan/treehouse/structure-m1-1', '/Game/Japan/Treehouse/StructurePieces/TH_Structure_cell_-1_1')
    japan_adopted(game, 'adopted/japan/assets/treehouse', '/Game/Japan/Assets/TH_Trunks', '/Game/Japan/Assets/TH_Frame')
    japan_adopted(game, 'adopted/japan/treehouse/surface-flat', f'{mats}/MI_TH_flat', '/Game/Japan/Treehouse/Textures/T_TH_flat')
    japan_adopted(game, 'adopted/japan/treehouse/surfaces', *(f'{mats}/MI_TH_{s}' for s in ('rope', 'wood_plank', 'trunk')))
    atomic(donor, 'treehouse_surfaces', {
        'TH_Dressing_cell_-2_2_Piece0': (14226, ['TH_flat', 'TH_rope']),
        'TH_Structure_cell_-1_1': (9638, ['TH_wood_plank']),
        'TH_Frame': (30584, ['TH_rope', 'TH_wood_plank']),
        'TH_Trunks': (7140, ['TH_bark'])}, bake=True)
    # Only the dressing and the frame carry the five-channel bake, so give the others one channel.
    manifest = donor / 'atomic_regions/treehouse_surfaces/assets/manifest.json'
    data = json.loads(manifest.read_text())
    for row in data['exports']:
        if not row['asset'].startswith(('TH_Dressing', 'TH_Frame')):
            row['metadata']['uv_channels'] = ['UVMap']
    manifest.write_text(json.dumps(data))
    # The trunks' bark binds MI_TH_trunk (not MI_TH_bark), as the donor's import_surfaces does.
    japan_adopted(game, 'adopted/japan/treehouse/surface-trunk', f'{mats}/MI_TH_trunk')
    treehouse = {g.id: g for g in recover.build_plan(game, 'japan/treehouse', donor).generated}
    assert sorted(treehouse) == ['prop/treehouse/dressing-cell-m2-2-piece0', 'prop/treehouse/structure-cell-m1-1']
    dressing = treehouse['prop/treehouse/dressing-cell-m2-2-piece0']
    assert dressing.package == '/Game/Japan/Treehouse/Pieces/TH_Dressing_cell_-2_2_Piece0'
    assert dressing.settings['slot_map'] == {'TH_flat': f'{mats}/MI_TH_flat', 'TH_rope': f'{mats}/MI_TH_rope'}
    assert dressing.settings['full_precision_uvs'] is True and dressing.settings['boxes'] == []
    structure = treehouse['prop/treehouse/structure-cell-m1-1']
    assert 'full_precision_uvs' not in structure.settings and structure.settings['collision'] == 'complex'
    plan = recover.build_plan(game, 'japan/assets', donor)
    kit = {g.id: g for g in plan.generated}
    assert sorted(kit) == ['prop/treehouse/frame', 'prop/treehouse/trunks']
    assert kit['prop/treehouse/trunks'].settings['slot_map'] == {'TH_bark': f'{mats}/MI_TH_trunk'}
    assert kit['prop/treehouse/frame'].settings['full_precision_uvs'] is True


def test_world_textures_import_with_the_factory_defaults_and_the_region_textures_stay_open(tmp_path):
    game, donor = tmp_path / 'game', tmp_path / 'donor'
    japan_adopted(game, 'adopted/japan/textures/sky-water', '/Game/Japan/Textures/T_water', '/Game/Japan/Textures/T_white')
    japan_adopted(game, 'adopted/japan/textures/plaza-harbor', '/Game/Japan/Textures/T_Harbor_timber')
    write(donor / 'textures/T_water.jpg', b'water jpg')
    write(donor / 'textures/T_white.png', b'white png')
    plan = recover.build_plan(game, 'japan/textures', donor)
    assert sorted((g.id, g.source.name, g.settings) for g in plan.generated) == [
        ('texture/japan/water', 'T_water.jpg', {}), ('texture/japan/white', 'T_white.png', {})]
    assert any('T_Harbor_timber' in u for u in plan.unmapped_outputs)
    assert plan.kept['adopted/japan/textures/plaza-harbor'] == ['/Game/Japan/Textures/T_Harbor_timber']
    recover.apply(game, plan, donor)
    loaded = records.load_asset(game / 'assets/texture/japan/water/asset.toml')
    assert loaded.recipe['importer'] == 'texture' and loaded.sources[0].path == 'src/T_water.jpg'


def test_southwest_pieces_use_the_village_material_and_complex_collision(tmp_path):
    game, donor = tmp_path / 'game', japan_donor(tmp_path)
    japan_adopted(game, 'adopted/japan/southwest', '/Game/Japan/Southwest/Pieces/SW_Boat', '/Game/Japan/Southwest/Pieces/Tree_PineLean_A')
    japan_adopted(game, 'adopted/japan/materials/base-materials', '/Game/Japan/Materials/M_Village')
    atomic(donor, 'southwest', {'SW_Boat': (692, ['Southwest_Palette']), 'Tree_PineLean_A': (300, ['Southwest_Palette']),
                                'SW_Gone': (10, ['Southwest_Palette'])})
    plan = recover.build_plan(game, 'japan/southwest', donor)
    assert sorted(g.id for g in plan.generated) == ['prop/southwest/boat', 'prop/southwest/tree-pine-lean-a']
    assert all(g.settings['collision'] == 'complex' for g in plan.generated)
    assert any('SW_Gone' in u for u in plan.unmapped_outputs)       # a piece no record holds is reported


def test_japan_props_take_the_saved_collision_and_stop_on_a_donor_disagreement(tmp_path, monkeypatch):
    game, donor = tmp_path / 'game', tmp_path / 'donor'
    assets = '/Game/Japan/Assets'
    adopted(game, 'japan/assets/hd-p-bus-stop', [f'{assets}/HD_P_bus_stop'])
    adopted(game, 'japan/assets/treehouse', [f'{assets}/TH_P_bell', f'{assets}/TH_P_globe'])
    adopted(game, 'japan/hidamari/prop-bus-stop', ['/Game/Japan/Hidamari/Materials/MI_HD_P_bus_stop'])
    adopted(game, 'japan/treehouse/prop-bell', ['/Game/Japan/Treehouse/Materials/MI_TH_P_bell',
                                              '/Game/Japan/Treehouse/Materials/MI_TH_P_globe'])
    saved = tmp_path / 'saved.json'
    mesh = lambda slot, material, trace, hulls, triangles: {'slot': slot, 'material': material, 'triangles': triangles,
                                                           'trace': trace, 'hulls': hulls}
    saved.write_text(json.dumps({'meshes': {
        f'{assets}/HD_P_bus_stop': mesh('HD_P_bus_stop', '/Game/Japan/Hidamari/Materials/MI_HD_P_bus_stop',
                                        'CTF_USE_DEFAULT', 1, 9842),
        f'{assets}/TH_P_bell': mesh('TH_P_bell', '/Game/Japan/Treehouse/Materials/MI_TH_P_bell',
                                    'CTF_USE_SIMPLE_AS_COMPLEX', 0, 9130),
        f'{assets}/TH_P_globe': mesh('TH_P_globe', '/Game/Japan/Treehouse/Materials/MI_TH_P_globe',
                                     'CTF_USE_SIMPLE_AS_COMPLEX', 0, 100)}}))
    monkeypatch.setattr(recover, 'PROPS_SAVED', saved)
    atomic(donor, 'hidamari_props', {'HD_P_bus_stop': (9855, ['HD_P_bus_stop']), 'Tree_Caldera_A': (5, ['x'])})
    atomic(donor, 'treehouse_props', {'TH_P_bell': (9130, ['TH_P_bell']), 'TH_P_globe': (100, ['TH_P_globe'])})
    manifest = donor / 'atomic_regions/hidamari_props/assets/manifest.json'
    data = json.loads(manifest.read_text())
    data['exports'][0]['metadata']['collision_hulls'] = 1
    manifest.write_text(json.dumps(data))
    plan = recover.build_plan(game, 'japan/props', donor)
    by_id = {g.id: g for g in plan.generated}
    assert sorted(by_id) == ['prop/hidamari-props/bus-stop', 'prop/treehouse-props/bell', 'prop/treehouse-props/globe']
    assert by_id['prop/hidamari-props/bus-stop'].settings == {
        'slot_materials': ['/Game/Japan/Hidamari/Materials/MI_HD_P_bus_stop'], 'triangles': 9855,
        'collision': 'simple_and_complex', 'hulls': 1, 'collision_trace': 'CTF_USE_DEFAULT'}
    assert by_id['prop/treehouse-props/bell'].settings['collision_trace'] == 'CTF_USE_SIMPLE_AS_COMPLEX'
    assert by_id['prop/treehouse-props/bell'].settings['boxes'] == []        # a look-only prop keeps no shape
    assert plan.kept['adopted/japan/assets/treehouse'] == []
    # A donor hull count that is not the saved one would move the collision.
    data['exports'][0]['metadata']['collision_hulls'] = 2
    manifest.write_text(json.dumps(data))
    with pytest.raises(recover.RecoverError, match='disagree'):
        recover.build_plan(game, 'japan/props', donor)
