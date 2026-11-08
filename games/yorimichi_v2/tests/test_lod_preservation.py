"""LOD-chain preservation: a mesh with several LODs keeps its chain through a reimport; one LOD gets none added."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'unreal' / 'Scripts'
sys.path.insert(0, str(SCRIPTS))
import lod_preservation as lp  # noqa: E402

spec = importlib.util.spec_from_file_location('v2_import_run_lods', ROOT / 'tools' / 'import' / 'run.py')
run = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = run
spec.loader.exec_module(run)

PLAN = [(1.0, 1.0), (0.45, 0.3), (0.2, 0.12), (0.08, 0.04)]


class Mesh:
    def __init__(self, chain):
        self.chain = list(chain)            # [(percent, screen)], LOD0 first


class Reduction:
    def __init__(self, percent):
        self.percent = percent

    def get_editor_property(self, name):
        assert name == 'percent_triangles'
        return self.percent


class Options:
    def __init__(self, levels):
        self.levels = levels


class FakeMeshEditor:
    """The StaticMeshEditorSubsystem calls preserve.py uses, on a fake chain. `keeps_screens=False` ignores the screen
    sizes the import sets, to model a reapply that does not take."""

    def __init__(self, keeps_screens=True):
        self.keeps_screens = keeps_screens
        self.set_lods_calls = 0

    def get_lod_count(self, mesh):
        return len(mesh.chain)

    def get_lod_screen_sizes(self, mesh):
        return [screen for _, screen in mesh.chain]

    def get_lod_reduction_settings(self, mesh, index):
        return Reduction(mesh.chain[index][0])

    def set_lods(self, mesh, options):
        self.set_lods_calls += 1
        mesh.chain = [(level.percent, level.screen if self.keeps_screens else 1.0) for level in options.levels]

    def set_lod_screen_sizes(self, mesh, screens):
        if self.keeps_screens:
            mesh.chain = [(percent, screen) for (percent, _), screen in zip(mesh.chain, screens)]


def options(levels):
    return Options([type('Level', (), {'percent': p, 'screen': s})() for p, s in levels])


def test_read_gives_the_count_screen_sizes_and_reductions():
    editor, mesh = FakeMeshEditor(), Mesh(PLAN)
    assert lp.read(editor, mesh) == {'count': 4, 'screen_sizes': [1.0, 0.3, 0.12, 0.04],
                                     'reductions': [1.0, 0.45, 0.2, 0.08]}


def test_screen_sizes_are_the_same_within_one_thousandth_and_no_further():
    before = {'count': 2, 'screen_sizes': [1.0, 0.3], 'reductions': [1.0, .5]}
    assert lp.same_chain(before, {'count': 2, 'screen_sizes': [1.0009, 0.3], 'reductions': [1.0, .5]})
    assert not lp.same_chain(before, {'count': 2, 'screen_sizes': [1.002, 0.3], 'reductions': [1.0, .5]})
    assert not lp.same_chain(before, {'count': 1, 'screen_sizes': [1.0], 'reductions': [1.0]})


def test_a_new_package_has_no_chain_to_keep():
    editor, mesh = FakeMeshEditor(), Mesh([(1.0, 1.0)])
    after = lp.preserve(editor, mesh, None, None, options)
    assert after['count'] == 1 and editor.set_lods_calls == 0


def test_a_mesh_with_one_lod_gets_no_lods_added_even_when_the_recipe_names_a_plan():
    editor, mesh = FakeMeshEditor(), Mesh([(1.0, 1.0)])
    before = lp.read(editor, mesh)
    after = lp.preserve(editor, mesh, before, PLAN, options)
    assert after['count'] == 1 and editor.set_lods_calls == 0 and mesh.chain == [(1.0, 1.0)]


def test_a_chain_the_import_kept_is_not_touched():
    editor, mesh = FakeMeshEditor(), Mesh(PLAN)
    before = lp.read(editor, mesh)
    lp.preserve(editor, mesh, before, PLAN, options)
    assert editor.set_lods_calls == 0


def test_a_dropped_chain_is_reapplied_from_the_recipe_and_checked_again():
    editor, mesh = FakeMeshEditor(), Mesh(PLAN)
    before = lp.read(editor, mesh)
    mesh.chain = [(1.0, 1.0)]                                   # the reimport dropped the editor's LODs
    after = lp.preserve(editor, mesh, before, PLAN, options)
    assert editor.set_lods_calls == 1 and after['count'] == 4
    assert after['screen_sizes'] == before['screen_sizes']


def test_a_dropped_chain_with_no_recipe_plan_fails():
    editor, mesh = FakeMeshEditor(), Mesh(PLAN)
    before = lp.read(editor, mesh)
    mesh.chain = [(1.0, 1.0)]
    with pytest.raises(lp.LodError, match='names no reduction plan'):
        lp.preserve(editor, mesh, before, None, options)


def test_a_recipe_plan_with_the_wrong_number_of_levels_fails():
    editor, mesh = FakeMeshEditor(), Mesh(PLAN)
    before = lp.read(editor, mesh)
    mesh.chain = [(1.0, 1.0)]
    with pytest.raises(lp.LodError, match='names 2 LOD level'):
        lp.preserve(editor, mesh, before, [(1.0, 1.0), (.5, .3)], options)


def test_a_reapply_that_does_not_take_the_screen_sizes_fails():
    editor, mesh = FakeMeshEditor(keeps_screens=False), Mesh(PLAN)
    before = lp.read(editor, mesh)
    mesh.chain = [(1.0, 1.0)]
    with pytest.raises(lp.LodError, match='does not match'):
        lp.preserve(editor, mesh, before, PLAN, options)


def test_the_host_check_rejects_a_recorded_chain_that_changed():
    one = {'count': 1, 'screen_sizes': [1.0], 'reductions': [1.0]}
    four = {'count': 4, 'screen_sizes': [1.0, .3, .12, .04], 'reductions': [1., .45, .2, .08]}
    lp.verify_record({'before': one, 'after': one})
    lp.verify_record({'before': None, 'after': four})
    lp.verify_record({'before': four, 'after': four})
    with pytest.raises(lp.LodError, match='changed: 4 LODs before, 1 after'):
        lp.verify_record({'before': four, 'after': one})
