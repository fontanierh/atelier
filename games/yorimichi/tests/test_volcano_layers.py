"""A volcano look change reimports only the volcano; an export that reruns and writes the same meshes reimports nothing."""
import json
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build

from test_mega_ramp_layers import changed_by

RECIPE = build.load_recipe('yorimichi')
DIGEST = RECIPE.export_digest
LATER = {'data.content', 'data.network', 'unreal.cook', 'unreal.package'}


def records(items, at):
    """Binary FBX 7.4 records starting at file offset `at`: (name, [(kind, bytes)], children)."""
    made = b''
    for name, props, children in items:
        values = b''.join(bytes([ord(kind)]) + value for kind, value in props)
        start = at + len(made) + 13 + len(name) + len(values)
        nested = records(children, start) + (b'\0' * 13 if children else b'')
        made += struct.pack('<IIIB', start + len(nested), len(props), len(values), len(name)) + name + values + nested
    return made


def fbx(year, ids, vertices, link=(1, 0)):
    """A Blender-like export: its time in the header, its object ids from a per-run hash."""
    L = lambda v: ('L', struct.pack('<q', v))
    S = lambda s: ('S', struct.pack('<I', len(s)) + s)
    array = ('d', struct.pack('<III', len(vertices), 0, 8 * len(vertices)) + struct.pack(f'<{len(vertices)}d', *vertices))
    top = [(b'FBXHeaderExtension', [], [(b'CreationTimeStamp', [], [(b'Year', [('I', struct.pack('<i', year))], [])])]),
           (b'Documents', [], [(b'Document', [L(ids[0]), S(b'Scene')], [])]),
           (b'Objects', [], [(b'Geometry', [L(ids[1]), S(b'Geometry'), S(b'Mesh')], [(b'Vertices', [array], [])])]),
           (b'Connections', [], [(b'C', [S(b'OO'), L(ids[link[0]]), L(ids[link[1]])], [])])]
    return DIGEST.MAGIC + b'\x1a\x00' + struct.pack('<I', 7400) + records(top, 27) + b'\0' * 13 + b'footer'


def test_an_fbx_digest_ignores_the_export_time_and_ids_but_not_the_mesh():
    same = DIGEST.fbx(fbx(2025, (11, 22), [0., 1., 2.]))
    assert DIGEST.fbx(fbx(2026, (987654321, 123456789), [0., 1., 2.])) == same
    assert DIGEST.fbx(fbx(2025, (11, 22), [0., 1., 2.5])) != same
    assert DIGEST.fbx(fbx(2025, (11, 22), [0., 1., 2.], link=(0, 1))) != same     # the connection runs the other way


def test_snow_rock_and_mountain_material_reimport_only_the_volcano(tmp_path, monkeypatch):
    for edited in (tmp_path / 'hidamari' / 'north_snow.png', tmp_path / 'hidamari' / 'north_snow.json',
                   RECIPE.ASSETS / 'environment/textures/volcanic-rock.jpg', RECIPE.SCRIPTS / 'mountain_material.py'):
        assert changed_by(edited, tmp_path, monkeypatch) == {'unreal.north'} | LATER, edited


def test_the_world_import_reads_no_volcano_input(tmp_path):
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path, uproject=tmp_path / 'Yorimichi.uproject')
    steps = {s.name: s for s in RECIPE.steps(ctx)}
    world, north = steps['unreal.world'], steps['unreal.north']
    assert 'world.hidamari' not in world.needs and 'world.hidamari.city' in world.needs
    assert not {RECIPE.SCRIPTS / 'mountain_material.py', tmp_path / 'hidamari' / 'north_snow.png'} & set(world.inputs)
    # The world import purges /Game/Japan and makes the textures the volcano's materials use.
    names = list(steps)
    assert 'unreal.world' in north.needs and names.index('unreal.world') < names.index('unreal.north')
    assert north.commands[0].env == (('HIDAMARI_ASSETS', 'HD_North*'),)


def hidamari_export(out, mesh, layout):
    """What world.hidamari writes: city.json, the manifest, a city and a volcano mesh, the snow mask's metadata."""
    folder = out / 'hidamari'
    (folder / 'assets').mkdir(parents=True, exist_ok=True)
    (folder / 'city.json').write_text(json.dumps(layout))
    (folder / 'manifest.json').write_text(json.dumps({'HD_Shop_00': {'triangles': 2}, 'HD_NorthMountains': {'triangles': 2}}))
    (folder / 'north_snow.json').write_text(json.dumps({'south_join_m': 4000.}))
    for name, vertices in (('HD_Shop_00', [0., 1.]), ('HD_NorthMountains', mesh)):
        year, ids = mesh[0] + layout['run'], (layout['run'], 2 * layout['run'] + 1)   # a new time and new ids every run
        (folder / 'assets' / f'{name}.fbx').write_bytes(fbx(int(year), ids, vertices))


def test_a_rerun_export_reimports_only_what_its_meshes_changed(tmp_path, monkeypatch):
    out = tmp_path / 'build'
    ctx = SimpleNamespace(game='yorimichi', out=out, logs=out / 'logs', stamps=out / 'stamps', uproject=None)
    state, imported = {'mesh': [5., 6.], 'layout': {'run': 1}}, []

    def export(ctx, log):
        state['layout']['run'] += 1
        hidamari_export(out, state['mesh'], state['layout'])
    source = tmp_path / 'layout.py'
    source.write_text('1')
    steps = [build.Step('world.hidamari', [build.Call('export', export)], inputs=[source]),
             RECIPE.digest_step(out, 'world.hidamari', 'city', '', north=False),
             RECIPE.digest_step(out, 'world.hidamari', 'north', '', north=True),
             *[build.Step(name, [build.Call(name, lambda ctx, log, name=name: imported.append(name))], needs=[need])
               for name, need in (('unreal.world', 'world.hidamari.city'), ('unreal.north', 'world.hidamari.north'))]]
    monkeypatch.setattr(build, 'Context', lambda game: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda game: SimpleNamespace(steps=lambda context: steps))
    assert build.build('yorimichi', echo=lambda line: None) == 0 and imported == ['unreal.world', 'unreal.north']

    imported.clear()
    state['layout']['trees'] = 3          # a layout change: city.json only, every FBX written again
    source.write_text('2')
    assert build.build('yorimichi', echo=lambda line: None) == 0 and imported == []

    state['mesh'] = [5., 7.]              # the volcano's mesh
    source.write_text('3')
    assert build.build('yorimichi', echo=lambda line: None) == 0 and imported == ['unreal.north']


@pytest.fixture
def props_build(tmp_path, monkeypatch):
    """Run the recipe's real cutoff with a deterministic stand-in for Blender and native world import."""
    out = tmp_path / 'build'
    folder = out / 'hidamari/props'
    source = tmp_path / 'props.py'
    state = {'revision': 0, 'run': 0, 'review': b'first review',
             'manifest': {f'HD_P_{name}': {'gain': .07, 'boxes': 1} for name in ('first', 'middle', 'last')},
             'vertices': {}, 'png': {}}
    imported, messages = [], []
    ctx = SimpleNamespace(game='yorimichi', out=out, logs=out / 'logs', stamps=out / 'stamps', uproject=None)

    def export(ctx, log):
        state['run'] += 1
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'props.json').write_text(json.dumps(state['manifest']))
        for i, name in enumerate(state['manifest']):
            (folder / f'{name}.fbx').write_bytes(fbx(2025 + state['run'], (state['run'] * 100 + i, 20 + i),
                                                  state['vertices'].get(name, [0., 1., 2.])))
            (folder / f'{name}.png').write_bytes(state['png'].get(name, b'prop texture ' + name.encode()))
        (folder / 'review.png').write_bytes(state['review'])

    recipe = {s.name: s for s in RECIPE.steps(ctx)}
    needs = [n for n in recipe['unreal.world'].needs if n.startswith('world.hidamari_props')]
    assert needs == ['world.hidamari_props.import']
    steps = [build.Step('world.hidamari_props', [build.Call('export', export)], inputs=[source]),
             recipe['world.hidamari_props.import'],
             build.Step('unreal.world', [build.Call('import', lambda ctx, log: imported.append('world'))], needs=needs)]
    monkeypatch.setattr(build, 'Context', lambda game: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda game: SimpleNamespace(steps=lambda context: steps))

    def run(*, edited=True):
        if edited:
            state['revision'] += 1
            source.write_text(str(state['revision']))
        return build.build('yorimichi', echo=messages.append)

    assert run() == 0 and imported == ['world']
    imported.clear()
    return state, imported, run, out, messages


def test_identical_hidamari_prop_exports_leave_world_current_after_producer_edit(props_build):
    state, imported, run, out, _ = props_build
    digest = out / 'digests/world.hidamari_props.import.json'
    before = digest.read_bytes()
    assert run() == 0 and state['run'] == 2 and imported == []
    assert digest.read_bytes() == before  # the FBX time and object IDs changed, its geometry did not


@pytest.mark.parametrize('changed', ['geometry', 'png', 'metadata', 'receipt', 'add', 'remove'])
def test_every_consumed_hidamari_prop_export_invalidates_world(props_build, changed):
    state, imported, run, _, _ = props_build
    # Change the last entry: an inventory of a representative first prop would miss this.
    name = 'HD_P_last'
    if changed == 'geometry':
        state['vertices'][name] = [0., 1., 3.]
    elif changed == 'png':
        state['png'][name] = b'changed texture'
    elif changed == 'metadata':
        state['manifest'][name]['gain'] = .12
    elif changed == 'receipt':
        state['manifest'][name]['source_sha256'] = 'changed manifest receipt'
    elif changed == 'add':
        state['manifest']['HD_P_added'] = {'gain': .09, 'boxes': 2}
    else:
        del state['manifest'][name]  # stale exports remain on disk but cease to be consumed
    assert run() == 0 and imported == ['world']


def test_hidamari_prop_review_images_do_not_invalidate_world(props_build):
    state, imported, run, _, _ = props_build
    state['review'] = b'new review image'
    assert run() == 0 and imported == []


@pytest.mark.parametrize('missing', ['props.json', 'HD_P_last.fbx', 'HD_P_last.png'])
def test_missing_hidamari_prop_export_fails_even_after_successful_cutoff(props_build, missing):
    _, imported, run, out, messages = props_build
    (out / 'hidamari/props' / missing).unlink()
    assert run(edited=False) == 1 and imported == []
    assert not (out / 'stamps/world.hidamari_props.import.json').exists()
    assert any('FAILED' in message for message in messages)


def reruns(edited, changed, out):
    """Steps that rerun when `edited` changes: an input is or holds it, or a need reran; a cutoff need only when its
    outputs changed (`changed`: the cutoff steps whose files differ). World exports are taken to write the same files
    except where `changed` says otherwise."""
    ctx = SimpleNamespace(game='yorimichi', out=out, uproject=out / 'Yorimichi.uproject')
    steps = build.order(RECIPE.steps(ctx), ['unreal.package'])
    cutoff = {s.name for s in steps if s.cutoff}
    ran = set()
    for step in steps:
        inside = any(str(edited) == str(i) or str(edited).startswith(f'{i}/') for i in step.inputs)
        if inside or any(n in ran and (n not in cutoff or n in changed) for n in step.needs):
            ran.add(step.name)
    return ran


# What follows any re-export of the city: the digests, the exports that need world.hidamari, staging and packaging.
CITY = {'world.hidamari', 'world.hidamari.city', 'world.hidamari.north', 'world.zeppelin', 'world.zeppelin.meshes',
        'world.terrain', 'world.terrain.meshes', 'world.map', 'world.city_tiles', 'world.city_tiles.meshes',
        'world.city_trees', 'world.city_trees.meshes', 'data.stage'} | LATER
# The regions that also read mountains.py and hidamari/layout.py, and the layout itself (a cutoff step).
NORTHERN = {'world.layout', 'world.belmonte', 'world.belmonte.meshes', 'world.hippodrome', 'world.hippodrome.meshes'}


def test_volcano_snow_or_colours_reimport_only_the_volcano(tmp_path):
    ran = reruns(RECIPE.REGIONS / 'hidamari' / 'mountains.py', {'world.hidamari.north'}, tmp_path)
    assert ran == CITY | NORTHERN | {'unreal.north'}


def test_caldera_dressing_reimports_nothing(tmp_path):
    ran = reruns(RECIPE.REGIONS / 'hidamari' / 'layout.py', set(), tmp_path)
    assert ran == CITY | NORTHERN
    # Unless the volcano's meshes change with it.
    assert reruns(RECIPE.REGIONS / 'hidamari' / 'layout.py', {'world.hidamari.north'}, tmp_path) == CITY | NORTHERN | {'unreal.north'}


def test_layout_dependents_list_the_layout_sources_they_import(tmp_path):
    """world.layout is a cutoff step: a dependent no longer sees its sources through its fingerprint."""
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path, uproject=tmp_path / 'Yorimichi.uproject')
    steps = {s.name: s for s in RECIPE.steps(ctx)}
    assert steps['world.layout'].cutoff
    covers = lambda step, files: all(any(f == i or i in f.parents for i in step.inputs) for f in files)
    for name in ('world.village', 'world.houses', 'world.southwest', 'world.mega', 'world.lake', 'world.skatepark',
                 'world.treehouse', 'world.hidamari', 'world.belmonte', 'world.hippodrome'):
        assert covers(steps[name], RECIPE.VILLAGE_LAYOUT), name
    for name in ('world.treehouse', 'world.hidamari', 'world.belmonte', 'world.hippodrome'):   # import treehouse/layout.py
        assert covers(steps[name], RECIPE.TREEHOUSE_LAYOUT) and 'world.treehouse_trees' in steps[name].needs, name


def test_layout_dependents_hash_every_module_their_scripts_import(tmp_path):
    """Each step on the cutoff hashes every module its world scripts import, read from their source: the volcano's
    layout reads Belmonte's terrain, which reads the Hippodrome's build, so editing either reruns them."""
    regions = RECIPE.REGIONS
    assert {regions / 'belmonte' / 'layout.py', regions / 'belmonte' / 'terrain.py', regions / 'belmonte' / 'source.py',
            regions / 'hippodrome' / 'build.py'} <= set(RECIPE.local_imports(regions / 'hidamari' / 'layout.py'))
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path, uproject=tmp_path / 'Yorimichi.uproject')
    steps = RECIPE.steps(ctx)
    checked = 0
    for step in steps:
        if step.name != 'world.layout' and 'world.layout' not in step.needs:
            continue
        for command in step.commands:
            script = getattr(command, 'script', None)
            if script is None or RECIPE.WORLD not in Path(script).parents:
                continue
            missing = [f for f in RECIPE.local_imports(script) if not any(f == i or i in f.parents for i in step.inputs)]
            assert not missing, (step.name, missing)
            checked += 1
    assert checked >= 12
