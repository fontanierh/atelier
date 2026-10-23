"""Owner equivalence must prove only the reviewed source-membership handoff."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('city_parent_transition',
    Path(__file__).parents[1]/'unreal/Scripts/city_parent_transition.py')
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)


def historical_current(member):
    fixture=json.loads((Path(__file__).parent/'fixtures/atomic-predecessor-native-policies.json').read_text())
    expected='283329c07' if member==P.SETUP else 'a66794fa20c57f3b0fa30883596625ab9c5b1966'
    assert fixture['source_revision'][member].startswith(expected)
    value=fixture['sources'][member]
    assert hashlib.sha256(value.encode()).hexdigest()==fixture['source_sha256'][member]
    return value


def sources():
    old_import = "for name,entry in manifest.items():\n    if only and name not in only: continue\n    import_mesh(name)\n"
    old_catalog = 'def independently_owned(package):\n    "owned packages"\n    return package in shared_packages()\n'
    importer = old_import.replace('    import_mesh(name)',
        "    if name in ('HD_Terrain', 'HD_Streets', 'HD_Square'):\n        continue\n    import_mesh(name)")
    catalog = old_catalog.replace('    return package',
        "    if package in {'/Game/Japan/Assets/'+name for name in ('HD_Terrain', 'HD_Streets', 'HD_Square')}:\n"
        "        return True\n    return package")
    old_setup = ('def purge(): delete_owned_namespace()\ndef main():\n    \"world owner\"\n'
                 '    if retired: raise RuntimeError()\n    import json\n'
                 '    W = json.load(open(os.path.join(OUT, \"world.json\")))\n    purge()\n    import_world()\n')
    setup = old_setup.replace('    purge()\n', '')
    return ({P.IMPORTER:old_import,P.CATALOG:old_catalog,P.SETUP:old_setup,'unrelated.py':'def finish(): return 1\n'},
            {P.IMPORTER:importer,P.CATALOG:catalog,P.SETUP:setup,'unrelated.py':'def finish(): return 1\n'})


def test_only_the_three_delegated_parent_packages_are_excluded():
    old,current = sources()
    assert P.excluded_packages(old,current) == tuple('/Game/Japan/Assets/'+name for name in P.PARENTS)
    # Other owners may consume only the catalogue, not the Hidamari importer.
    assert P.excluded_packages({P.CATALOG:old[P.CATALOG]}, {P.CATALOG:current[P.CATALOG]})


def test_importer_and_world_handoff_preserves_the_shared_generator_catalogue():
    old, current = sources()
    # The unused purge catalogue is shared by forest and foliage source generators.
    # Parent delegation belongs to native importer dispatch and explicit retirement.
    current[P.CATALOG] = old[P.CATALOG]
    assert P.excluded_packages(old, current) == tuple('/Game/Japan/Assets/'+name for name in P.PARENTS)


@pytest.mark.parametrize('change', ['geometry','selection','extra_skip','wrong_target','wrong_position',
                                  'foreign_member','missing_member','syntax','unchanged','reversed'])
def test_any_other_owner_or_membership_change_refuses(change):
    old,current = sources()
    if change=='geometry': current[P.IMPORTER] = current[P.IMPORTER].replace('import_mesh(name)','modify_mesh(name)')
    if change=='selection': current[P.IMPORTER] = current[P.IMPORTER].replace('if only and','if not only and')
    if change=='extra_skip': current[P.IMPORTER] += 'if other: delete_mesh()\n'
    if change=='wrong_target': current[P.IMPORTER] = current[P.IMPORTER].replace('HD_Square','HD_Park')
    if change=='wrong_position': current[P.IMPORTER] = current[P.IMPORTER].replace('    import_mesh(name)',
        '    other_finish()\n    import_mesh(name)')
    if change=='foreign_member': current['new.py'] = 'pass\n'
    if change=='missing_member': del current['unrelated.py']
    if change=='syntax': old[P.CATALOG] = 'def broken('
    if change=='unchanged': old = dict(current)
    if change=='reversed': old,current = current,old
    assert P.excluded_packages(old,current) is None


@pytest.mark.parametrize('change', ['import', 'purge_body', 'extra_call', 'wrong_location'])
def test_removed_upfront_purge_never_hides_other_world_changes(change):
    old, current = sources()
    if change == 'import': current[P.SETUP] = current[P.SETUP].replace('import_world()', 'import_other_world()')
    if change == 'purge_body': current[P.SETUP] = current[P.SETUP].replace('delete_owned_namespace()', 'other_deletion()')
    if change == 'extra_call': old[P.SETUP] = old[P.SETUP].replace('    purge()', '    purge()\n    purge()')
    if change == 'wrong_location': old[P.SETUP] = old[P.SETUP].replace('    purge()\n    import_world()', '    import_world()\n    purge()')
    assert P.excluded_packages(old, current) is None


def product_sources():
    current = historical_current(P.PRODUCTS)
    history = json.loads((Path(__file__).parent/'fixtures/city_five_family_policy.json').read_text())
    previous = history['sources'][P.PRODUCTS]
    assert previous != current
    return {P.PRODUCTS: previous}, {P.PRODUCTS: current}


def test_literal_six_family_extension_preserves_other_product_logic():
    old, current = product_sources()
    assert P.excluded_packages(old, current) == tuple('/Game/Japan/Assets/'+name for name in P.PARENTS)
    assert P.excluded_packages(current, old) is None


@pytest.mark.parametrize('bad', ['finishing', 'limit', 'destination', 'import', 'extra_source', 'diagnostic'])
def test_family_extension_cannot_hide_changed_finishing_or_membership(bad):
    old, current = product_sources()
    text = current[P.PRODUCTS]
    if bad == 'finishing': text = text.replace("slug == 'road'", "slug == 'paving'")
    if bad == 'limit': text = text.replace('TRIANGLE_LIMIT = 32768', 'TRIANGLE_LIMIT = 65536')
    if bad == 'destination': text = text.replace('v1_128m', 'v2_128m')
    if bad == 'import': text += '\nimport unexpected_owner\n'
    if bad == 'extra_source': text = text.replace("'HD_Harbor')", "'HD_Harbor', 'HD_PlazaFloor')")
    if bad == 'diagnostic': text = text.replace('all six production', 'some production')
    current[P.PRODUCTS] = text
    assert P.excluded_packages(old, current) is None


@pytest.mark.parametrize('previous_count', [0, 3])
def test_original_and_three_family_importer_can_delegate_exactly_six(previous_count):
    old, current = sources()
    current[P.CATALOG] = old[P.CATALOG]
    current[P.IMPORTER] = current[P.IMPORTER].replace(repr(P.ORIGINAL_PARENTS), repr(P.PARENTS))
    if previous_count == 3:
        old[P.IMPORTER] = current[P.IMPORTER].replace(repr(P.PARENTS), repr(P.ORIGINAL_PARENTS))
    assert P.excluded_packages(old, current)
    assert P.excluded_packages(current, old) is None


@pytest.mark.parametrize('member', [P.PIECE_IMPORTER, P.FERRY_SOURCE])
def test_exact_harbor_binding_and_ownership_doc_transition(member):
    history = json.loads((Path(__file__).parent/'fixtures/city_five_family_policy.json').read_text())
    current = (Path(__file__).parents[3]/member).read_text()
    old = {member: history['sources'][member]}
    if member == P.PIECE_IMPORTER:
        # Preserve the exact historical Harbor-only positive proof separately
        # from today's additional, intentionally incompatible collision finish.
        assert P.excluded_packages(old, {member: current}) is None
        assert old[member].count('material_paths') == 2
        current = old[member].replace('material_paths', 'piece_material_paths')
        previous_call = "piece_material_paths(source['source_material_slots'])"
        assert current.count(previous_call) == 1
        current = current.replace(previous_call, "piece_material_paths(name, source['source_material_slots'])")
    else:
        assert P.excluded_packages(old,{member:current}) is None
        current=historical_current(member)
    assert P.excluded_packages(old, {member: current})
    assert P.excluded_packages({member: current}, old) is None
    if member == P.PIECE_IMPORTER:
        changed = current.replace("piece_material_paths(name, source['source_material_slots'])",
                                  "piece_material_paths('HD_Harbor', source['source_material_slots'])")
    else:
        changed = current.replace("cut.get('failures') != []", "False")
    assert changed != current
    assert P.excluded_packages(old, {member: changed}) is None


def test_harbor_wrapper_cannot_certify_a_different_material_binding():
    old, current = product_sources()
    current[P.PRODUCTS] = current[P.PRODUCTS].replace('/Game/Japan/Materials/M_Harbor', '/Game/Foreign/M_Other')
    assert P.excluded_packages(old, current) is None


def test_actual_world_dispatch_is_not_mistaken_for_static_finisher_coverage():
    from atelier import source_imports
    game = Path(__file__).parents[1]
    script = game/'unreal/Scripts/setup_project.py'
    members = source_imports.local_imports(script, (game/'world', game/'world/regions'))
    assert script in members
    assert game/'unreal/Scripts/import_hidamari.py' not in members
    assert any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
               and isinstance(node.func.value, ast.Name) and node.func.value.id == 'runpy'
               and node.func.attr == 'run_path' and 'import_hidamari.py' in ast.unparse(node)
               for node in ast.walk(ast.parse(script.read_text())))


def map_sources(local=False):
    import hashlib
    import json
    name = 'world_map_local_startup_policy.json' if local else 'world_map_startup_policy.json'
    fixture = json.loads((Path(__file__).parent/'fixtures'/name).read_text())
    assert hashlib.sha256(fixture['sources'][P.SETUP].encode()).hexdigest() == fixture['source_sha256'][P.SETUP]
    current = historical_current(P.SETUP)
    return {P.SETUP:fixture['sources'][P.SETUP]}, {P.SETUP:current}


@pytest.mark.parametrize('local', [False, True])
def test_exact_map_startup_transition_preserves_the_complete_remaining_world_owner(local):
    old,current = map_sources(local)
    assert P.excluded_packages(old,current)
    assert P.excluded_packages(current,old) is None


@pytest.mark.parametrize('member',[P.SETUP,P.PRODUCTS,P.FERRY_SOURCE])
def test_atomic_source_and_map_ownership_changes_are_not_historical_policy_exemptions(member):
    previous=historical_current(member)
    current=(Path(__file__).parents[3]/member).read_text()
    assert previous!=current
    assert P.excluded_packages({member:previous},{member:current}) is None


@pytest.mark.parametrize('change', ['map','partition','blank_failure','actor','material','save','save_failure',
                                  'import','extra_statement','old_creation','old_world'])
@pytest.mark.parametrize('local', [False, True])
def test_map_startup_transition_cannot_hide_any_other_world_change(change, local):
    old,current = map_sources(local)
    text = current[P.SETUP]
    if change == 'map': text = text.replace('/Game/Japan/Maps/Slice','/Game/Foreign/Map')
    if change == 'partition': text = text.replace('new_blank_map(False)','new_blank_map(True)')
    if change == 'blank_failure': text = text.replace('if world is None:', 'if False:')
    if change == 'actor': text = text.replace('L.set_intensity(7.0)','L.set_intensity(3.0)')
    if change == 'material': text = text.replace('MI["_painterly"]','MI["other"]')
    if change == 'save': text = text.replace('save_map(world, map_path)','save_map(world, other_path)')
    if change == 'save_failure': text = text.replace('if not ok:', 'if False:')
    if change == 'import': text = text.replace('import os, glob, sys, unreal','import os, glob, sys, unreal, other')
    if change == 'extra_statement': text = text.replace('if True:', 'other_mutation()\n    if True:',1)
    if change == 'old_creation':
        old[P.SETUP] = old[P.SETUP].replace('new_blank_map(False)', 'new_blank_map(True)') if local else old[P.SETUP].replace('les.new_level(map_path)','les.new_level(other_path)')
    if change == 'old_world': old[P.SETUP] = old[P.SETUP].replace('unreal.EditorLevelLibrary.get_editor_world()','other_world()')
    current[P.SETUP] = text
    assert P.excluded_packages(old,current) is None
