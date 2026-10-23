"""Ordered extraction/storage checks; full production parity is a separate gate."""
import json
from pathlib import Path
import sys
import zipfile

import numpy as np
import pytest

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME/'world'))
import yori  # noqa: E402,F401
from terrain_product import Mesh, load, save  # noqa: E402
import farhills_surface  # noqa: E402


def test_products_round_trip_every_frozen_ordered_fixture(tmp_path):
    cases = json.loads(Path(__file__).with_name('fixtures').joinpath('terrain-r8.json').read_text())['cases']
    for name, case in cases.items():
        mesh = Mesh.from_polygons(case['vertices'], case['triangles'])
        a, b = tmp_path/(name+'.npz'), tmp_path/(name+'-again.npz')
        save(a, mesh, owner='FarHills', stage='final', city=True)
        save(b, mesh, owner='FarHills', stage='final', city=True)
        assert a.read_bytes() == b.read_bytes()
        with zipfile.ZipFile(a) as archive:
            assert all(member.date_time == (1980, 1, 1, 0, 0, 0) for member in archive.infolist())
        restored = load(a, owner='FarHills', stage='final', city=True)
        np.testing.assert_array_equal(restored.vertices, case['vertices'])
        np.testing.assert_array_equal(restored.triangles(), case['triangles'])
        assert restored.polygons() == case['triangles']
        assert not restored.vertices.flags.writeable and not restored.indices.flags.writeable


def test_natural_polygon_fan_and_empty_mesh_stay_explicit(tmp_path):
    v = np.array([[0., 0., 0.], [2., 0., 1.], [2., 3., 2.], [0., 3., 3.]])
    mesh = Mesh.from_polygons(v, [[0, 1, 2, 3]])
    v[0, 2] = 7.  # The product owns an independent copy.
    assert mesh.vertices[0, 2] == 0.
    assert mesh.polygons() == [[0, 1, 2, 3]]
    np.testing.assert_array_equal(mesh.triangles(), [[0, 1, 2], [0, 2, 3]])
    path = tmp_path/'natural.npz'
    save(path, mesh, owner='FarHills', stage='natural', city=False)
    assert load(path, owner='FarHills', stage='natural', city=False).polygons() == mesh.polygons()
    empty = Mesh.from_polygons([], [])
    assert empty.triangles().shape == (0, 3)


@pytest.mark.parametrize('change', [
    {'indices': np.array([0., 1., 2.])},
    {'indices': np.array([0, 1, 9])},
    {'offsets': np.array([0, 2])},
    {'offsets': np.array([0, 3, 2], dtype='u8')},
    {'vertices': np.array([[0., 0., np.nan], [1., 0., 0.], [0., 1., 0.]])},
])
def test_mesh_rejects_invalid_geometry(change):
    values = dict(vertices=[[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]], indices=[0, 1, 2], offsets=[0, 3])
    values.update(change)
    with pytest.raises(ValueError):
        Mesh(**values)


def test_loader_fails_on_missing_corrupt_or_mismatched_products(tmp_path):
    path = tmp_path/'surface.npz'
    identity = dict(owner='FarHills', stage='final', city=True)
    with pytest.raises(FileNotFoundError):
        load(path, **identity)
    mesh = Mesh.from_polygons([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]], [[0, 1, 2]])
    save(path, mesh, **identity)
    for wrong in [dict(owner='city'), dict(stage='natural'), dict(city=False), dict(city=1)]:
        with pytest.raises(ValueError):
            load(path, **(identity | wrong))
    with np.load(path, allow_pickle=False) as source:
        arrays = dict(source)
    for bad in [arrays | {'triangles': np.array([[1, 0, 2]])},
                arrays | {'indices': arrays['indices'].astype('f8')},
                arrays | {'unexpected': np.array(1)}]:
        np.savez(path, **bad)
        with pytest.raises(ValueError):
            load(path, **identity)


def test_extraction_passes_original_polygons_to_one_carve(monkeypatch):
    import shorelines
    import farhills_grid
    from hidamari import layout, mountains
    from train import earthworks
    grid = np.array([2000., 2010.]), np.array([2000., 2014.]), np.array([[1., 2.], [3., 8.]])
    calls = []
    monkeypatch.setattr(farhills_grid, 'mesh_grid', lambda n, *, city: grid)
    monkeypatch.setattr(farhills_grid, 'source_grid', lambda *, city: grid)
    monkeypatch.setattr(farhills_grid, 'rail_refinement', lambda *, city: {})
    monkeypatch.setattr(layout, 'coastal_backdrop_height', lambda x, y, z: z)
    monkeypatch.setattr(shorelines, 'field', lambda x, y: (np.zeros_like(x), np.zeros_like(x)))
    monkeypatch.setattr(shorelines, 'reach', lambda x, y: np.full_like(x, 1000.))
    def carve(vertices, faces, step, *, hidden, conform_neighbors):
        assert step == 4. and hidden is mountains.contains and conform_neighbors
        assert any(len(face) == 4 for face in faces)  # Never fan before the planner.
        calls.append((np.array(vertices), [list(face) for face in faces]))
        return np.asarray(vertices)+[0., 0., 1.], faces, {'refined': 0}
    monkeypatch.setattr(earthworks, 'polygons', carve)
    natural, final, report = farhills_surface.generate(301, city=True)
    assert len(calls) == 1 and report == {'refined': 0}
    np.testing.assert_array_equal(natural.vertices, calls[0][0])
    assert natural.polygons() == calls[0][1] == final.polygons()
    np.testing.assert_array_equal(final.vertices, natural.vertices+[0., 0., 1.])


def test_normal_export_requires_matching_product_and_never_regenerates(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('normal export must not regenerate geometry')
    monkeypatch.setattr(farhills_surface, 'generate', forbidden)
    with pytest.raises(FileNotFoundError):
        farhills_surface.export_mesh(301, tmp_path, city=True)
    mesh = Mesh.from_polygons([[0., 0., 0.], [1., 0., 2.], [0., 1., 3.]], [[0, 1, 2]])
    save(tmp_path/'final.npz', mesh, owner='FarHills', stage='final', city=False)
    with pytest.raises(ValueError, match='mode mismatch'):
        farhills_surface.export_mesh(301, tmp_path, city=True)
    save(tmp_path/'final.npz', mesh, owner='FarHills', stage='final', city=True)
    result = farhills_surface.export_mesh(301, tmp_path, city=True)
    np.testing.assert_array_equal(result.vertices, mesh.vertices)
    np.testing.assert_array_equal(result.indices, mesh.indices)


def test_explicit_no_city_export_preserves_its_own_construction(tmp_path, monkeypatch):
    mesh = Mesh.from_polygons([[0., 0., 0.], [1., 0., 2.], [0., 1., 3.]], [[0, 1, 2]])
    calls = []
    def generate(count, *, city):
        calls.append((count, city))
        return mesh, mesh, {'refined': 0}
    monkeypatch.setattr(farhills_surface, 'generate', generate)
    assert farhills_surface.export_mesh(301, tmp_path, city=False) is mesh
    assert calls == [(301, False)]
    restored = load(tmp_path/'final.npz', owner='FarHills', stage='final', city=False)
    np.testing.assert_array_equal(restored.vertices, mesh.vertices)


def test_products_have_one_early_guarded_owner_and_export_reads_final(tmp_path):
    from types import SimpleNamespace
    from atelier import build, build_products
    recipe = build.load_recipe('yorimichi')
    graph = build_products.Graph(recipe.steps(SimpleNamespace(game='yorimichi', out=tmp_path, uproject=None)))
    producer, export = graph.by_name['world.farhills'], graph.by_name['world.island.geometry.FarHills']
    assert producer.heavy and producer.commands[0].threads == 3
    assert 'world.layout' in producer.needs and 'world.hidamari' not in producer.needs
    assert not any(path.name == 'city.json' for path in producer.inputs)
    assert {p.name for p in producer.products} == {f'terrain.FarHills.{stage}' for stage in ('natural', 'final', 'provenance')}
    assert all(graph.owners[p.name] == producer.name for p in producer.products)
    assert 'terrain.FarHills.final' in export.reads and export.products
    assert graph.by_name['world.terrain'].reads == ['island.atomic', 'island.receiving', 'island.source_inventory']
    names = [step.name for step in graph.select(['world.terrain'])]
    assert names.index('world.farhills') < names.index(export.name) < names.index('world.terrain')
    assert recipe.WORLD/'build_terrain.py' not in producer.inputs
    # The city layout's conservative import closure still includes appearance
    # definitions. Narrow those modules separately; never hide reachable reads.


@pytest.mark.parametrize('city', [True, False])
def test_geometry_entrypoint_publishes_explicit_mode_without_city_scenery(tmp_path, monkeypatch, city):
    import yori
    monkeypatch.setattr(yori, 'OUT', tmp_path)
    (tmp_path/'world.json').write_text(json.dumps({'n': 301}))
    mesh = Mesh.from_polygons([[0., 0., 0.], [1., 0., 2.], [0., 1., 3.]], [[0, 1, 2]])
    calls = []
    def generate(count, *, city, progress):
        calls.append((count, city))
        progress('fixture complete')
        return mesh, mesh, {'refined': 0}
    monkeypatch.setattr(farhills_surface, 'generate', generate)
    farhills_surface.main([] if city else ['--no-city'])
    assert calls == [(301, city)]
    assert not (tmp_path/'hidamari/city.json').exists()
    result = load(tmp_path/'terrain/FarHills/final.npz', owner='FarHills', stage='final', city=city)
    np.testing.assert_array_equal(result.vertices, mesh.vertices)


def test_failed_geometry_entrypoint_does_not_publish_products(tmp_path, monkeypatch):
    import yori
    monkeypatch.setattr(yori, 'OUT', tmp_path)
    (tmp_path/'world.json').write_text(json.dumps({'n': 301}))
    def fail(*args, **kwargs):
        raise RuntimeError('fixture generation failure')
    monkeypatch.setattr(farhills_surface, 'generate', fail)
    with pytest.raises(RuntimeError, match='generation failure'):
        farhills_surface.main([])
    assert not (tmp_path/'terrain/FarHills').exists()


def test_forest_compatibility_names_use_the_authoritative_grid():
    import farhills_grid
    from hidamari import forest_backdrop
    for name in ('source_grid', 'mesh_grid', 'rail_refinement'):
        assert getattr(forest_backdrop, name) is getattr(farhills_grid, name)


def test_export_adapter_edit_does_not_rebuild_geometry_products(tmp_path, monkeypatch):
    from test_mega_ramp_layers import changed_by
    changed = changed_by(GAME/'world/build_terrain.py', tmp_path, monkeypatch)
    assert 'world.terrain' in changed
    assert 'world.farhills' not in changed


@pytest.mark.parametrize('arguments', [(), ('--no-city',)])
def test_blender_action_entrypoint_bootstraps_and_ignores_engine_arguments(tmp_path, arguments):
    import os
    import subprocess
    from types import SimpleNamespace
    from atelier.build_source import Blender
    # Match the actual action argv, from an isolated process with no world path
    # or preloaded modules. Stop at the missing required input before any heavy
    # generation; import/argparse failures must not mask that input failure.
    command = Blender(GAME/'world/farhills_surface.py', args=arguments, threads=3).argv(
        SimpleNamespace(blender='Blender'))
    driver = ("import json,runpy,sys; sys.argv=json.loads(sys.argv[1]); "
              "runpy.run_path(sys.argv[sys.argv.index('--python')+1],run_name='__main__')")
    result = subprocess.run([sys.executable, '-I', '-c', driver, json.dumps(command)],
                            cwd=tmp_path, env=dict(os.environ, ATELIER_BUILD_ROOT=str(tmp_path)),
                            text=True, capture_output=True, timeout=15)
    assert result.returncode == 1
    assert 'FileNotFoundError' in result.stderr and 'world.json' in result.stderr
    assert 'ModuleNotFoundError' not in result.stderr and 'unrecognized arguments' not in result.stderr
