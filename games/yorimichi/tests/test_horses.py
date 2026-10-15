"""The horse library (assets/horses), its coat provenance, the GLB uprighting and roster contract of the Unreal import
(Scripts/horse_data.py) and the horse build steps: fresh-checkout data, no Blender or Unreal."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from atelier import build, build_inputs, paths
from atelier.gltf import glb_parts

GAME = Path(__file__).resolve().parents[1]
ASSETS = GAME / 'assets'
HORSES = ASSETS / 'horses'
VARIANTS = HORSES / 'coats' / 'variants'
SCRIPTS = GAME / 'unreal' / 'Scripts'
LIBRARY = json.loads((HORSES / 'manifest.json').read_text())
VARIANT_LIST = json.loads((VARIANTS / 'manifest.json').read_text())['variants']
_spec = importlib.util.spec_from_file_location('horse_data_under_test', SCRIPTS / 'horse_data.py')
horse_data = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(horse_data)
RECIPE = build.load_recipe('yorimichi')
PARTS = ('Saddle', 'Reins')
# What world.horses samples (assets/horses/build.py SAMPLED) and import_horses.py restyles by name.
BONES = {'Saddle_Root', 'Spine_1', 'Spine_2', 'Neck_1', 'Head', 'Bit', 'Stirrup_2_L', 'Stirrup_2_R', 'Reins_5_L', 'Reins_5_R',
         'Reins_C'}
SLOTS = {'Coat', 'Mane', 'Tail'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def glbs():
    return {rel: glb_parts((HORSES / rel).read_bytes()) for rel in LIBRARY['glbs']}


@pytest.fixture(scope='module')
def parsed():
    return glbs()


def accessor(doc, binary, index):
    a = doc['accessors'][index]
    view = doc['bufferViews'][a['bufferView']]
    dtype = {5121: np.uint8, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}[a['componentType']]
    width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[a['type']]
    start = view.get('byteOffset', 0) + a.get('byteOffset', 0)
    return np.frombuffer(binary, dtype, a['count'] * width, start).reshape(a['count'], width)


def test_the_manifest_declares_the_library_once_and_matches_disk_and_source_library():
    breeds, tack, clips = list(LIBRARY['breeds']), LIBRARY['tack_sets'], list(LIBRARY['clips'])
    assert LIBRARY['reference_breed'] in breeds and len(set(breeds)) == len(breeds) == 6
    assert len(set(tack)) == len(tack) == 7 and len(set(clips)) == len(clips) == 11
    assert set(LIBRARY) == {'reference_breed', 'breeds', 'tack_sets', 'clips', 'coat_masks', 'hair_colors',
                            'hair_patterns', 'tints', 'glbs'}
    for slug, breed in LIBRARY['breeds'].items():
        assert set(breed) == {'name', 'hair_colour'} and breed['name'] == slug.capitalize()
        assert len(breed['hair_colour']) == 3 and all(0 <= c <= 1 for c in breed['hair_colour'])
    assert all(set(c) == {'loop'} and isinstance(c['loop'], bool) for c in LIBRARY['clips'].values())
    expected = {f'{slug}/horse.glb' for slug in breeds} | {f'{slug}/tack/{part}_{sid}.glb' for slug in breeds
                                                             for sid in tack for part in PARTS}
    assert set(LIBRARY['glbs']) == expected == {p.relative_to(HORSES).as_posix() for p in HORSES.rglob('*.glb')}
    library = json.loads((ASSETS / 'source-library.json').read_text())['files']
    for rel, entry in LIBRARY['glbs'].items():
        data = (HORSES / rel).read_bytes()
        assert entry == {'bytes': len(data), 'sha256': sha(data)} == library['horses/' + rel], rel
    # Only the declared sources remain: no loose texture copies, coat JPEGs, breed.json or prompt batches.
    sources = {p.relative_to(HORSES).as_posix() for p in HORSES.rglob('*') if p.is_file() and p.name != '.DS_Store' and '__pycache__' not in p.parts}
    declared = (expected | {'manifest.json', 'build.py', 'rider.py', 'coats/variants/manifest.json'}
                | {f'coats/T_Coat_{mask}_Mask.png' for mask in LIBRARY['coat_masks']}
                | {f'coats/variants/{v[key]}' for v in VARIANT_LIST for key in ('file', 'provenance')})
    assert sources == declared
    assert {k for k in library if k.startswith('horses/')} == {'horses/' + s for s in declared if s.endswith(('.glb', '.png'))}


def test_palettes_have_one_shape_each():
    assert all(set(c) == {'id', 'label', 'primary', 'secondary'} for c in LIBRARY['hair_colors'])
    assert all(set(p) == {'id', 'label', 'mix'} and 0 <= p['mix'] <= 1 for p in LIBRARY['hair_patterns'])
    assert all(set(t) == {'id', 'label', 'rgb'} and len(t['rgb']) == 3 for t in LIBRARY['tints'])
    for palette in ('hair_colors', 'hair_patterns', 'tints'):
        ids = [entry['id'] for entry in LIBRARY[palette]]
        assert len(ids) == len(set(ids)), palette
    for name in ('build.py', 'rider.py'):   # read from the manifest, never restated
        assert 'HAIR_COLORS' not in (HORSES / name).read_text() and "'#171516'" not in (HORSES / name).read_text()


def test_coat_variants_match_their_provenance_and_files():
    assert len(VARIANT_LIST) == 16 and len({v['id'] for v in VARIANT_LIST}) == 16
    for v in VARIANT_LIST:
        assert set(v) == {'id', 'name', 'swatch', 'file', 'sha256', 'provenance'}
        png = (VARIANTS / v['file']).read_bytes()
        record = json.loads((VARIANTS / v['provenance']).read_text())
        assert v['file'].endswith('.png') and png.startswith(b'\x89PNG')
        assert v['sha256'] == sha(png) == record['output_sha256'], v['id']
        assert record['prompt_sha256'] == sha(record['prompt'].encode()), v['id']
        assert record['id'] == v['id'] and record['output'] == Path(v['file']).name and record['status'] == 'done'
        assert record['requested_model'] and record['prompt']
    on_disk = {p.relative_to(VARIANTS).as_posix() for p in VARIANTS.rglob('*') if p.is_file()} - {'manifest.json'}
    assert on_disk == {v[key] for v in VARIANT_LIST for key in ('file', 'provenance')}
    masks = {p.name for p in (HORSES / 'coats').glob('*.png')}
    assert masks == {f'T_Coat_{mask}_Mask.png' for mask in LIBRARY['coat_masks']} and 'Solid' in LIBRARY['coat_masks']


def test_glbs_are_slim_self_contained_and_skinned_within_range(parsed):
    for rel, (doc, binary) in parsed.items():
        assert len(doc['buffers']) == 1 and 'uri' not in doc['buffers'][0], rel
        assert all(v.get('byteOffset', 0) + v['byteLength'] <= len(binary) for v in doc['bufferViews']), rel
        base = set()
        for material in doc['materials']:
            pbr = material.get('pbrMetallicRoughness', {})
            assert 'baseColorTexture' in pbr, (rel, material.get('name'))
            assert not {'normalTexture', 'emissiveTexture', 'occlusionTexture', 'extras'} & set(material), rel
            assert 'metallicRoughnessTexture' not in pbr, rel
            base.add(doc['textures'][pbr['baseColorTexture']['index']]['source'])
        # Every image is embedded and is a base colour: the only texture copies, which Interchange imports.
        assert base == set(range(len(doc['images']))), rel
        assert all('bufferView' in image and 'uri' not in image for image in doc['images']), rel
        for i, node in enumerate(doc['nodes']):
            if 'mesh' not in node:
                continue
            joints = len(doc['skins'][node['skin']]['joints'])
            for prim in doc['meshes'][node['mesh']]['primitives']:
                assert 'indices' in prim and '__LEG_ID' not in prim['attributes'], rel
                assert accessor(doc, binary, prim['attributes']['JOINTS_0']).max() < joints, (rel, i)
                count = doc['accessors'][prim['attributes']['POSITION']]['count']
                assert accessor(doc, binary, prim['indices']).max() < count, (rel, i)
        names = {n.get('name') for n in doc['nodes']}
        if rel.endswith('horse.glb'):
            assert [a['name'] for a in doc['animations']] == list(LIBRARY['clips']), rel
            assert BONES <= names and SLOTS <= {m['name'] for m in doc['materials']}, rel
        else:
            assert not doc.get('animations'), rel
        if rel.endswith('Saddle_00.glb'):   # what world.horses measures the seat and stirrup treads on
            assert 'Saddle_00_Model__Mt_Saddle' in names and {'Stirrup_2_L', 'Stirrup_2_R'} <= names, rel


def test_upright_glb_turns_rotated_meshes_into_glTF_y_up(parsed):
    rotated = next(rel for rel, (doc, _) in parsed.items() if 'tack' in rel and any(
        'rotation' in n for n in doc['nodes'] if 'mesh' in n))
    plain = next((rel for rel, (doc, _) in parsed.items() if not any('rotation' in n for n in doc['nodes'] if 'mesh' in n)), None)
    for rel in filter(None, (rotated, plain)):
        doc, binary = parsed[rel]
        new_doc, new_binary = glb_parts(horse_data.upright_glb((HORSES / rel).read_bytes()))
        turned = rel == rotated
        for node in new_doc['nodes']:
            if node.get('name') in ('Horse', 'Root') or 'mesh' in node or 'skin' in node:
                assert node['rotation'] == [0., 0., 0., 1.], rel
        root = [(a, b) for a, b in zip(doc['nodes'], new_doc['nodes']) if a.get('name') == 'Root' and 'translation' in a]
        for a, b in root:
            assert b['translation'] == [a['translation'][0], a['translation'][2], -a['translation'][1]]
        for mesh in doc['meshes']:
            for prim in mesh['primitives']:
                for attribute in ('POSITION', 'NORMAL'):
                    index = prim['attributes'][attribute]
                    old, new = accessor(doc, binary, index), accessor(new_doc, new_binary, index)
                    want = np.stack([old[:, 0], old[:, 2], -old[:, 1]], 1) if turned else old
                    np.testing.assert_array_equal(new, want)
                    if attribute == 'POSITION':
                        np.testing.assert_allclose(new_doc['accessors'][index]['min'], new.min(0))
                        np.testing.assert_allclose(new_doc['accessors'][index]['max'], new.max(0))
                joints = accessor(doc, binary, prim['attributes']['JOINTS_0'])
                np.testing.assert_array_equal(accessor(new_doc, new_binary, prim['attributes']['JOINTS_0']), joints)
        for skin in doc['skins']:
            old = accessor(doc, binary, skin['inverseBindMatrices']).reshape(-1, 4, 4)   # [matrix, column, row]
            new = accessor(new_doc, new_binary, skin['inverseBindMatrices']).reshape(-1, 4, 4)
            want = np.stack([old[:, 0], old[:, 2], -old[:, 1], old[:, 3]], 1) if turned else old
            np.testing.assert_array_equal(new, want)


def test_upright_glb_drops_the_channels_of_the_nodes_it_resets():
    doc, _ = glb_parts((HORSES / LIBRARY['reference_breed'] / 'horse.glb').read_bytes())
    new_doc, _ = glb_parts(horse_data.upright_glb((HORSES / LIBRARY['reference_breed'] / 'horse.glb').read_bytes()))
    reset = {i for i, n in enumerate(doc['nodes']) if n.get('name') in ('Horse', 'Root') or 'mesh' in n or 'skin' in n}
    for old, new in zip(doc['animations'], new_doc['animations']):
        assert new['channels'] == [c for c in old['channels'] if c['target'].get('node') not in reset]
        assert any(c['target']['node'] == next(i for i, n in enumerate(doc['nodes']) if n.get('name') == 'Reins_C')
                   for c in new['channels'])


def imported():
    """What import_horses.py would hand horse_data.roster, as plain paths."""
    lib = LIBRARY
    masters = {k: f'/Game/Horses/M_{k}.M_{k}' for k in horse_data.MASTERS}
    masks = {m: f'/Game/Horses/Coats/Masks/T_Coat_{m}_Mask.T_Coat_{m}_Mask' for m in lib['coat_masks']}
    variants = [{**v, 'texture': f"/Game/Horses/Coats/Variants/T_{v['id']}.T_{v['id']}"} for v in VARIANT_LIST]
    breeds = {}
    for slug, breed in lib['breeds'].items():
        folder = f"/Game/Horses/{breed['name']}"
        breeds[slug] = {
            'mesh': f"{folder}/SK_Horse_{breed['name']}.SK_Horse_{breed['name']}",
            'skeleton': f"{folder}/SKEL_Horse_{breed['name']}.SKEL_Horse_{breed['name']}",
            'clips': {c: {'path': f'{folder}/A_{c}.A_{c}', 'length': 1.5, 'loop': spec['loop']} for c, spec in lib['clips'].items()},
            'saddles': {sid: f'{folder}/Tack/Saddle_{sid}/S.S' for sid in lib['tack_sets']},
            'reins': {sid: f'{folder}/Tack/Reins_{sid}/R.R' for sid in lib['tack_sets']},
        }
    contacts = {'saddle_root': [0.04, 0., 1.6], 'seat_z': 1.37, 'seat_offset_z': -0.23, 'scale_ratio': 1.0,
                'stirrup_L': [0., .3, .8], 'stirrup_R': [0., -.3, .8], 'grip_L': [.42, .13, 1.57], 'grip_R': [.42, -.13, 1.57]}
    built = {'reference_breed': lib['reference_breed'], 'fps': 60,
             'breeds': {slug: {'name': b['name'], 'contacts': contacts} for slug, b in lib['breeds'].items()}, 'clips': {}}
    return built, masters, masks, variants, breeds


def test_roster_contract():
    built, masters, masks, variants, breeds = imported()
    roster = horse_data.roster(LIBRARY, built, masters, masks, variants, breeds)
    roster = json.loads(json.dumps(roster))   # as written to roster.json
    assert horse_data.roster_problems(roster) == []
    assert roster['breed_order'] == list(LIBRARY['breeds']) and roster['fps'] == 60
    assert roster['tack_sets'] == LIBRARY['tack_sets'] and list(roster['coat_masks']) == LIBRARY['coat_masks']
    assert [v['id'] for v in roster['coat_variants']] == [v['id'] for v in VARIANT_LIST]
    for slug, b in roster['breeds'].items():
        assert set(b['contacts']) == {'saddle_root', 'seat_z', 'scale_ratio', 'stirrup_L', 'stirrup_R', 'grip_L', 'grip_R'}
        assert b['mesh_yaw'] == -90. and list(b['clips']) == list(LIBRARY['clips'])
    assert 'seconds' not in json.dumps(roster) and 'textures' not in roster['breeds'][LIBRARY['reference_breed']]
    assert len(list(horse_data.asset_paths(roster))) == 4 + 5 + 16 + 6 * (2 + 11 + 2 * 7)
    for broken in (lambda r: r.pop('tints'), lambda r: r['breeds']['arabian']['contacts'].pop('grip_L'),
                   lambda r: r['breeds']['quarter']['clips'].pop('Walk'), lambda r: r.update(fps=60.0),
                   lambda r: r['breeds']['friesian']['saddles'].pop('03'), lambda r: r.update(seconds=3)):
        copy = json.loads(json.dumps(roster))
        broken(copy)
        assert horse_data.roster_problems(copy), broken


def test_import_verification_checks_the_roster_and_its_saved_assets(tmp_path, monkeypatch):
    built, masters, masks, variants, breeds = imported()
    roster = horse_data.roster(LIBRARY, built, masters, masks, variants, breeds)
    meshes = list(horse_data.meshes(roster))
    assert len(meshes) == len(set(meshes)) == 6 * (1 + 2 * 7)
    folder = lambda mesh: mesh.rsplit('/', 1)[0]
    materials = {m: {f'{folder(m)}/Coat': f'{folder(m)}/T_Coat.T_Coat'} for m in meshes}
    monkeypatch.setattr(RECIPE, 'GAME', tmp_path)
    out = tmp_path / 'build'
    content = tmp_path / 'unreal' / 'Content'
    report = out / 'horses' / 'unreal_import.json'
    assert not RECIPE.horses_imported_present(out)
    for path, data in ((content / 'Data' / 'horses' / 'roster.json', roster), (report, {**roster, 'materials': materials})):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
    assert not RECIPE.horses_imported_present(out)   # no assets saved yet
    uasset = lambda p: content / f"{p.split('.')[0].removeprefix('/Game/')}.uasset"
    named = [uasset(p) for p in horse_data.asset_paths(roster)]
    dependencies = [uasset(p) for used in materials.values() for pair in used.items() for p in pair]
    for path in named + dependencies:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'')
    assert RECIPE.horses_imported_present(out)
    for path in (named[-1], dependencies[0], dependencies[-1]):   # a clip or mesh, a material instance, a texture
        path.unlink()
        assert not RECIPE.horses_imported_present(out), path
        path.write_bytes(b'')
    for data in ({**roster, 'materials': materials, 'fps': 30}, roster,
                 {**roster, 'materials': {**materials, meshes[0]: {}}},
                 {**roster, 'materials': {m: used for m, used in materials.items() if m != meshes[-1]}}):
        report.write_text(json.dumps(data))
        assert not RECIPE.horses_imported_present(out)


def test_the_rider_and_recipe_take_their_clip_lists_from_the_manifest():
    tree = ast.parse((HORSES / 'rider.py').read_text())
    specs = next(n.value for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', '') == 'MOUNTED_SPECS')
    rides = {key.value: next(k.value.value for k in call.keywords if k.arg == 'horse_clip') for key, call in zip(specs.keys, specs.values)}
    assert rides == {f'Horse{clip}': clip for clip in LIBRARY['clips']}
    assert all(k.arg != 'loop' for call in specs.values for k in call.keywords)   # the loop is the horse clip's
    # Getting on and off are transition_keys' clips, whose last statement returns {clip: (duration, keys)}.
    keys = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'transition_keys')
    transitions = tuple(k.value for k in keys.body[-1].value.keys)
    assert transitions == ('HorseMount', 'HorseDismount')
    assert RECIPE.HORSE_RIDER_CLIPS == (*rides, *transitions)
    # export.json keeps only what the clip import and the fit gate read.
    exported = next(n.value for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', '') == 'EXPORTED')
    assert {e.value for e in exported.elts} == {'frames', 'duration', 'loop', 'reach_error_cm'}
    assert RECIPE.HORSE_LIBRARY == LIBRARY
    source = (HORSES / 'build.py').read_text()
    assert 'prepare_library' not in source and 'HORSES_MODELS_DIR' not in source and 'breed_contact=None' not in source


def test_the_riders_share_only_what_rider_common_defines_and_the_bike_export_keeps_its_keys():
    """The shared rider module is not a behaviour change for the bike: both riders import only names rider_common
    defines, and the bike's export.json (read by UBikeComponent, the clip import and the fit gate) keeps its keys."""
    common = ast.parse(RECIPE.RIDE_COMMON.read_text())
    defined = {n.name for n in common.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    defined |= {t.id for n in common.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
    bike = ASSETS / 'vehicles' / 'bike' / 'rider.py'
    for rider in (HORSES / 'rider.py', bike):
        tree = ast.parse(rider.read_text())
        imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == 'rider_common' for a in n.names}
        assert imported and imported <= defined, (rider, imported - defined)
    tree = ast.parse(bike.read_text())
    function = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    report = next(n.value for n in ast.walk(function['main']) if isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', '') == 'report')
    assert {k.value for k in report.keys} == {'source_sha256', 'fps', 'clips'}
    clip = next(n.value.elts[1] for n in ast.walk(function['bake']) if isinstance(n, ast.Return))
    assert {k.value for k in clip.keys} == {'frames', 'duration', 'loop', 'contacts', 'bike_channels', 'bike', 'end_offset',
                                           'reach_error_cm'}


def steps(tmp_path):
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path, uproject=tmp_path / 'Yorimichi.uproject')
    return {s.name: s for s in RECIPE.steps(ctx)}


def covers(step, path):
    return any(path == i or i in path.parents for i in step.inputs)


def script_reads(script, *roots):
    """The modules a script imports, found by reading its source (build_inputs.local_imports, with the folders it puts
    on sys.path as roots), less the path plumbing every yori.py step shares: yori.py imports atelier.paths only for
    where the build goes, not for what it makes."""
    plumbing = set(build_inputs.local_imports(RECIPE.YORI)) - {RECIPE.YORI.resolve()}
    return [p for p in build_inputs.local_imports(script, roots) if p not in plumbing]


def test_horse_steps_hash_exactly_what_their_scripts_read(tmp_path):
    s = steps(tmp_path)
    world = s['world.horses']
    assert world.cutoff and world.verify is None and world.outputs == [tmp_path / 'horses' / 'manifest.json']
    assert all(covers(world, p) for p in (HORSES / 'build.py', HORSES / 'manifest.json', RECIPE.YORI,
                                           *(HORSES / rel for rel in LIBRARY['glbs'])))
    assert not any(covers(world, p) for p in (HORSES / 'coats' / 'variants' / 'manifest.json', HORSES / 'rider.py'))

    horses = s['unreal.horses']
    modules = script_reads(SCRIPTS / 'import_horses.py', RECIPE.WORLD)
    assert {SCRIPTS / 'horse_data.py', RECIPE.YORI, paths.STUDIO / 'atelier' / 'gltf.py'} <= set(modules)
    reads = [*modules, HORSES / 'manifest.json', VARIANTS / 'manifest.json', *(HORSES / rel for rel in LIBRARY['glbs']),
             *(HORSES / 'coats' / f'T_Coat_{m}_Mask.png' for m in LIBRARY['coat_masks']),
             *(VARIANTS / v['file'] for v in VARIANT_LIST)]
    assert [p for p in reads if not covers(horses, p)] == []
    assert not any(covers(horses, VARIANTS / v['provenance']) for v in VARIANT_LIST)   # provenance only
    assert horses.needs == ['world.horses'] and horses.verify is not None

    for character in RECIPE.definition.movers():
        if not character.playable:
            continue
        k = RECIPE.key(character)
        rider, bike = s[f'characters.{k}_horse'], s[f'characters.{k}_bike']
        rider_reads = script_reads(HORSES / 'rider.py', RECIPE.WORLD, ASSETS / 'vehicles', RECIPE.PIPELINE)
        assert {RECIPE.RIDE_COMMON, RECIPE.YORI, RECIPE.PIPELINE / 'rig.py'} <= set(rider_reads)
        assert [p for p in rider_reads if not covers(rider, p)] == []
        assert covers(bike, RECIPE.RIDE_COMMON) and rider.needs == ['world.horses']
        clip_reads = script_reads(SCRIPTS / 'import_ride_clips.py', RECIPE.WORLD, RECIPE.PIPELINE)
        assert RECIPE.YORI in clip_reads
        for kind in ('bike', 'horse'):
            ride = s[f'unreal.{k}_{kind}']
            assert ride.commands[0].script == SCRIPTS / 'import_ride_clips.py' and [p for p in clip_reads if not covers(ride, p)] == []
            assert ride.commands[0].env == (('RIDE', kind), ('RIDE_CHARACTER', character.id))
            assert ride.commands[0].marker == f'{character.id.upper()} {kind.upper()} IMPORT COMPLETE'
        pawn = s[f'unreal.{k}_pawn']
        assert f'unreal.{k}_horse' in pawn.after and not any('horse' in n for n in pawn.needs)
        assert f'characters.{k}_horse' in s[f'characters.{k}_fit'].needs
    assert not (SCRIPTS / 'import_bike_clips.py').exists() and not (SCRIPTS / 'import_horse_clips.py').exists()
    staged = RECIPE.staged(tmp_path)
    assert 'horses/manifest.json' not in staged and 'world.horses' not in s['data.stage'].needs
    # The game reads no rider horse report, so none is staged and data.stage waits on no horse export.
    assert not any(rel.endswith('horse/export.json') for rel in staged)
    assert not any(n.startswith('characters.') and n.endswith('_horse') for n in s['data.stage'].needs)
