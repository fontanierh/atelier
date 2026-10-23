"""City logical constructors keep their original authored bodies and narrow source closures."""
import ast
from pathlib import Path

from atelier.build_inputs import local_imports

GAME = Path(__file__).resolve().parents[1]
REGIONS = GAME / 'world/regions'
REGION = REGIONS / 'hidamari'
MODULES = ('construction', 'lettering_mesh', 'sheet_mesh', 'temple_mesh', 'pavilion_mesh',
           'playground_mesh', 'props_mesh', 'boat_mesh', 'lighthouse_mesh', 'terrain_mesh',
           'streets_mesh', 'harbor_mesh', 'square_mesh', 'park_mesh', 'water_mesh', 'gate_rock_mesh')


def definitions(path):
    return {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(path.read_text()).body
            if isinstance(n, (ast.FunctionDef, ast.ClassDef))}


def test_selected_city_geometry_keeps_complete_original_authored_definitions():
    original = definitions(REGION / 'build.py')
    found = {}
    for name in MODULES:
        for key, body in definitions(REGION / (name + '.py')).items():
            assert key not in found
            assert body == original[key], key
            found[key] = body
    assert len(found) == 22
    assert {'harbor', 'surface', 'city_terrain_surfaces', 'streets', 'park', 'SheetMesh'} <= found.keys()


def test_selected_city_sources_do_not_load_the_whole_or_sibling_builders():
    for name, excluded in [('boat_mesh', ('terrain_mesh', 'park_mesh', 'streets_mesh', 'harbor_mesh')),
                           ('harbor_mesh', ('terrain_mesh', 'park_mesh', 'streets_mesh')),
                           ('terrain_mesh', ('park_mesh', 'streets_mesh', 'harbor_mesh')),
                           ('lighthouse_mesh', ('terrain_mesh', 'park_mesh', 'streets_mesh', 'harbor_mesh'))]:
        sources = set(local_imports(REGION / (name + '.py'), (REGIONS, REGIONS.parent)))
        assert REGION / 'build.py' not in sources
        for other in excluded:
            assert REGION / (other + '.py') not in sources


def test_selected_constructor_global_names_are_explicitly_bound():
    import builtins
    import symtable
    paths = [REGION / (name + '.py') for name in (*MODULES, 'sea_mesh', 'wire_mesh', 'lane_edge_mesh', 'arcade_mesh')]
    paths.extend((REGION / 'logical').glob('*.py'))
    for path in paths:
        name = path.stem
        table = symtable.symtable(path.read_text(), str(path), 'exec')
        available = set(table.get_identifiers()) | set(dir(builtins))
        pending = list(table.get_children())
        while pending:
            scope = pending.pop()
            for symbol in scope.get_symbols():
                if symbol.is_global() and symbol.is_referenced():
                    assert symbol.get_name() in available, (name, scope.get_name(), symbol.get_name())
            pending.extend(scope.get_children())


def test_all_logical_city_entry_points_exclude_sibling_entry_points_and_original_exporter():
    import runpy
    names = runpy.run_path(str(REGION / 'logical_catalogue.py'))['ASSETS']
    assert len(names) == 86 and len(set(names)) == 86
    for name in names:
        path = REGION / 'logical' / (name + '.py')
        sources = set(local_imports(path, (REGIONS, REGIONS.parent)))
        assert REGION / 'build.py' not in sources
        assert {p.name for p in sources if p.parent == REGION / 'logical'} == {path.name}
    lighthouse = set(local_imports(REGION / 'logical/HD_Lighthouse.py', (REGIONS, REGIONS.parent)))
    assert REGION / 'layout.py' not in lighthouse
    assert REGION / 'harbor_mesh.py' not in lighthouse
