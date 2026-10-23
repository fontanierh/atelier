"""Selected ferry programs retain exact authority and isolate sibling geometry edits."""
import ast
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('ferry_ship_sources',
    Path(__file__).resolve().parents[1] / 'world/regions/ferry/ship_sources.py')
sources = importlib.util.module_from_spec(spec); spec.loader.exec_module(sources)


def declarations(text):
    tree = ast.parse(text)
    return {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}


def test_each_selected_constructor_has_exact_original_declarations_and_no_siblings():
    text = sources.BUILD.read_text()
    original = ast.parse(text)
    spans = {node.name: ast.get_source_segment(text, node) for node in original.body
             if isinstance(node, ast.FunctionDef)}
    for key, row in sources.project(text).items():
        compile(row['program'], 'selected', 'exec')
        if key not in sources.BUILDERS:
            continue
        present = declarations(row['program'])
        assert present & set(sources.BUILDERS.values()) == {sources.BUILDERS[key]}
        assert {'Mesh', 'check', 'make_materials', 'to_object'} <= present
        for node in ast.parse(row['program']).body:
            if isinstance(node, ast.FunctionDef):
                assert ast.get_source_segment(row['program'], node) == spans[node.name]


def test_unrelated_ship_edit_does_not_change_selected_payloads():
    text = sources.BUILD.read_text()
    before = sources.project(text)
    after = sources.project(text.replace('width = GATES[0][1] - .2', 'width = GATES[0][1] - .21'))
    assert before['FY_BoardingGate'] != after['FY_BoardingGate']
    assert {key for key in before if before[key] != after[key]} == {'FY_BoardingGate'}


def test_shared_deck_parameter_reaches_actual_consumers():
    text = sources.BUILD.read_text()
    before = sources.project(text)
    after = sources.project(text.replace('ZL = 1.0', 'ZL = 1.01'))
    changed = {key for key in before if before[key] != after[key]}
    assert {'FY_Hull', 'FY_Superstructure', 'audit'} <= changed
    assert 'FY_BoardingGate' not in changed
    assert 'FY_Collision' not in changed  # it reads the independently projected actual proxies


def test_projection_refuses_ambiguous_or_missing_definitions():
    with pytest.raises(ValueError, match='Missing'):
        sources.program('a = 1\n', ('absent',))
    with pytest.raises(ValueError, match='Ambiguous'):
        sources.program('a = 1\na = 2\n', ('a',))


def test_source_publication_validates_complete_exclusive_membership(tmp_path):
    sources.publish(tmp_path)
    assert {p.stem for p in tmp_path.iterdir()} == {*sources.BUILDERS, 'FY_Collision', 'audit'}
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    sources.publish(tmp_path)
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert json.loads((tmp_path / 'FY_Hull.json').read_text())['asset'] == 'FY_Hull'
    (tmp_path / 'foreign.json').write_text('{}')
    with pytest.raises(ValueError, match='Foreign'):
        sources.publish(tmp_path)
    assert all((tmp_path / key).read_bytes() == value for key, value in before.items())
