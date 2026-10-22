"""Owner equivalence must prove only the reviewed source-membership handoff."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('city_parent_transition',
    Path(__file__).parents[1]/'unreal/Scripts/city_parent_transition.py')
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)


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
