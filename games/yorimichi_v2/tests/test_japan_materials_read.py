"""The Japan material instances as read from the saved packages (docs/inventory/japan-materials-read.json, the output of
unreal/Scripts/report_materials.py) against what the donor generators set.

EXPECTED is transcribed from the donor scripts, not from the read: `instance(name, parent, tex, tint)` in
material_assets.py sets the parent, Tex and Tint; see_through.py adds CutScale to MI_Paint; forest_ground.py sets
NearGround on MI_Coast; mountain_material.py sets Caps on MI_NorthRockCaps; import_southwest.py sets MI_Sand's tint.
Overrides not in the read: enable_bark_lod_blend (foliage_material.py) and mask_instance (see_through.py) set
base_property_overrides, which the parameter read does not cover; those 13 rows are pinned as UNREAD_BASE."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
READ = ROOT / 'docs' / 'inventory' / 'japan-materials-read.json'
EXCEPTIONS = ROOT / 'docs' / 'inventory' / 'exceptions.md'

ONE = 1.0


def tint(r, g, b):
    return [r, g, b, ONE]


# name: (parent, Tex name or None, vector overrides, scalar overrides)
EXPECTED = {
    # shared_materials.py build_materials
    'MI_Bark': ('M_Painted', 'T_bark', {}, {}),
    'MI_BarkOlive': ('M_Painted', 'T_bark_olive', {}, {}),
    'MI_BarkTuscan': ('M_Painted', 'T_bark_olive', {'Tint': tint(.65, .55, .4)}, {}),
    'MI_Concrete': ('M_Painted', 'T_concrete', {}, {}),
    'MI_Ground': ('M_Painted', 'T_ground', {}, {}),
    'MI_Road': ('M_Painted', 'T_road', {'Tint': tint(.34, .33, .33)}, {}),
    'MI_Water': ('M_Painted', 'T_water', {}, {}),
    'MI_Sky': ('M_Sky', None, {'Tint': tint(1.35, 1.35, 1.35)}, {}),
    'MI_Flower': ('M_Foliage', 'T_flower', {}, {}),
    'MI_Grass': ('M_Grass', 'T_grass', {}, {}),
    'MI_Litter': ('M_Foliage', 'T_litter', {}, {}),
    'MI_LeafBroad': ('M_Foliage', 'T_leaf_broad', {}, {}),
    'MI_LeafCedar': ('M_Foliage', 'T_leaf_cedar', {}, {}),
    'MI_LeafPine': ('M_Foliage', 'T_leaf_pine', {}, {}),
    'MI_LeafOchre': ('M_Foliage', 'T_leaf_ochre', {}, {}),
    'MI_LeafMaple': ('M_Foliage', 'T_leaf_maple', {}, {}),
    'MI_LeafGinkgo': ('M_Foliage', 'T_leaf_ginkgo', {'Tint': tint(1., .72, .42)}, {}),
    'MI_LeafSmall': ('M_Foliage', 'T_leaf_small', {}, {}),
    'MI_LeafOchreSmall': ('M_Foliage', 'T_leaf_ochre_small', {}, {}),
    'MI_RoofTile': ('M_Painted', 'T_rooftile', {'Tint': tint(.40, .42, .48)}, {}),
    'MI_Paint': ('M_Painted', 'T_white', {'Tint': tint(.85, .85, .82), 'CutScale': [1., .25, 1., ONE]}, {}),
    'MI_Stone': ('M_Painted', 'T_white', {'Tint': tint(.50, .50, .47)}, {}),
    'MI_Vermilion': ('M_Painted', 'T_white', {'Tint': tint(.62, .12, .06)}, {}),
    'MI_Plaster': ('M_Painted', 'T_white', {'Tint': tint(.80, .74, .62)}, {}),
    'MI_Tile': ('M_Painted', 'T_white', {'Tint': tint(.16, .17, .20)}, {}),
    'MI_Wood': ('M_Painted', 'T_white', {'Tint': tint(.18, .11, .07)}, {}),
    'MI_Feather': ('M_Painted', 'T_white', {'Tint': tint(.92, .92, .90)}, {}),
    'MI_FeatherDark': ('M_Painted', 'T_white', {'Tint': tint(.10, .10, .12)}, {}),
    'MI_Metal': ('M_Painted', 'T_white', {'Tint': tint(.08, .08, .09)}, {}),
    'MI_Rock': ('M_Painted', 'T_white', {'Tint': tint(.30, .27, .24)}, {}),
    'MI_Lattice': ('M_Painted', 'T_white', {'Tint': tint(.14, .10, .08)}, {}),
    'MI_Moss': ('M_Painted', 'T_white', {'Tint': tint(.30, .38, .16)}, {}),
    # forest_ground.py, import_island_world.py, mountain_material.py, import_southwest.py
    'MI_Coast': ('M_ForestGround', None, {}, {'NearGround': 1.}),
    'MI_CoastRock': ('M_CoastRock', None, {}, {}),
    'MI_FarForest': ('M_ForestGround', None, {}, {}),
    'MI_NorthRockCaps': ('M_NorthMountains', None, {}, {'Caps': 1.}),
    'MI_Sand': ('M_Painted', 'T_white', {'Tint': tint(.24, .185, .10)}, {}),
    # import_forest.py: parent M_Foliage and Tex only
    'MI_LeafOak': ('M_Foliage', 'T_LeafOak', {}, {}),
    'MI_LeafOlive': ('M_Foliage', 'T_LeafOlive', {}, {}),
    'MI_LeafCypress': ('M_Foliage', 'T_LeafCypress', {}, {}),
    'MI_LeafStonePine': ('M_Foliage', 'T_LeafStonePine', {}, {}),
}

# Used leaves: a recipe recorded from the read, no donor builder (see the doc table).
LEAVES = {
    'MI_LeafAmber': ('M_Foliage', 'T_leaf_amber'),
    'MI_LeafCrimson': ('M_Foliage', 'T_leaf_crimson'),
}

# Rows whose base-property overrides the read does not cover (enable_bark_lod_blend, mask_instance).
UNREAD_BASE = {'MI_Bark', 'MI_BarkOlive', 'MI_BarkTuscan', 'MI_RoofTile', 'MI_Tile', 'MI_Plaster', 'MI_Wood',
               'MI_Lattice', 'MI_Vermilion', 'MI_Paint', 'MI_Metal', 'MI_Stone', 'MI_Concrete'}


def read_rows():
    return json.loads(READ.read_text())


def short(path):
    """'/Game/Japan/Textures/T_bark.T_bark' -> 'T_bark'; None stays None."""
    return None if path is None else path.rsplit('/', 1)[1].split('.')[0]


def same_vector(a, b):
    return len(a) == len(b) == 4 and all(abs(x - y) < 1e-6 for x, y in zip(a, b))


def overrides_of(row):
    o = row['overrides']
    return ({k: [round(x, 6) for x in v] for k, v in o['vector'].items()}, o['scalar'],
            {k: short(v) for k, v in o['texture'].items()})


def test_the_read_covers_the_43_packages_without_errors():
    rows = read_rows()
    assert len(rows) == 43
    assert all('error' not in r for r in rows.values())
    assert set(EXPECTED) | set(LEAVES) == {k.rsplit('/', 1)[1] for k in rows}


def test_every_generator_row_matches_its_donor_script_on_parent_and_parameters():
    rows = read_rows()
    mismatches = []
    for name, (parent, tex, vectors, scalars) in EXPECTED.items():
        row = rows[f'/Game/Japan/Materials/{name}']
        vec, sca, tx = overrides_of(row)
        want_tex = {'Tex': tex} if tex else {}
        if short(row['parent']) != parent:
            mismatches.append((name, 'parent', short(row['parent']), parent))
        if tx != want_tex:
            mismatches.append((name, 'Tex', tx, want_tex))
        if set(vec) != set(vectors) or not all(same_vector(vec[k], vectors[k]) for k in vectors):
            mismatches.append((name, 'vector', vec, vectors))
        if sca != scalars:
            mismatches.append((name, 'scalar', sca, scalars))
    assert mismatches == []
    assert len(EXPECTED) == 41


def test_the_two_used_leaves_are_parent_and_tex_only_and_their_effective_values_are_the_parent_defaults():
    rows = read_rows()
    for name, (parent, tex) in LEAVES.items():
        row = rows[f'/Game/Japan/Materials/{name}']
        vec, sca, tx = overrides_of(row)
        assert short(row['parent']) == parent
        assert (vec, sca, tx) == ({}, {}, {'Tex': tex})
        eff = row['effective']
        assert eff['scalar'] == {'FadeMode': 0.0}
        assert {k: [round(x, 6) for x in v] for k, v in eff['vector'].items()} == {
            'CutScale': [1., 1., 2., 1.], 'Tint': [1., 1., 1., 1.]}
        assert {k: short(v) for k, v in eff['texture'].items()} == {'Tex': tex}


def test_the_base_property_rows_are_the_13_the_read_cannot_confirm():
    assert len(UNREAD_BASE) == 13
    assert UNREAD_BASE <= set(EXPECTED)


def test_the_doc_statuses_pin_41_read_confirmed_2_recipe_recorded_and_no_blocked():
    text = EXCEPTIONS.read_text()
    rows = re.findall(r'^\| `(MI_[A-Za-z0-9]+)` \| `[^`]+` \| ([^|]+?) \|', text, re.M)
    status = dict(rows)
    assert len(rows) == 43 and len(status) == 43
    assert sorted(n for n, s in status.items() if s == 'Prepared, read-confirmed') == sorted(EXPECTED)
    assert sorted(n for n, s in status.items() if s == 'Prepared, recipe recorded') == sorted(LEAVES)
    assert 'Blocked' not in status.values()
