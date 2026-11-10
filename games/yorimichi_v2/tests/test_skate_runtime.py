"""The skate RuntimeData route: the record pins the assembler and the Skate/Data input list, the pure-Python side checks and
stages exactly those inputs, and the editor's Verify report is accepted only when it agrees with the receipt. Nothing here
runs Unreal; the assembly itself is run when the tracked Skate/Data tree is present."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'content'))
sys.path.insert(0, str(ROOT / 'tools' / 'import'))
import records  # noqa: E402
import skate_runtime as sr  # noqa: E402

spec = importlib.util.spec_from_file_location('v2_skate_verify', ROOT / 'unreal/Scripts/skate_verify.py')
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)

spec = importlib.util.spec_from_file_location('v2_import_run_skate', ROOT / 'tools' / 'import' / 'run.py')
run = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = run
spec.loader.exec_module(run)

RECORD = ROOT / 'assets/data/skate/runtime'
GENERATOR = ROOT / 'assets/generator/skate/runtime'
SHA = hashlib.sha256(b'x').hexdigest()
DATA_READY = sr.DATA.is_dir() and (sr.DATA / 'bundle.json').is_file()


def runtime_toml(*, importer='skate-runtime', version=1, settings=f'manifest_sha256 = "{SHA}"\n', sources=None,
                 outputs=('/Game/SkateRuntime/RuntimeData',)):
    if sources is None:
        sources = records.SKATE_RUNTIME_SOURCES
    src = ''.join(f'[[sources]]\npath = "{path}"\nsha256 = "{SHA}"\n' for path in sources)
    outs = ''.join(f'[[outputs]]\npackage = "{package}"\n' for package in outputs)
    return (f'schema = 1\nid = "data/skate/runtime"\nkind = "data"\nauthority = "generated"\nowner = "shared/skateruntime"\n'
            f'{src}[recipe]\nimporter = "{importer}"\nversion = {version}\n[recipe.settings]\n{settings}\n{outs}')


def load_text(tmp_path, text):
    path = tmp_path / 'asset.toml'
    path.write_text(text)
    return records.load_asset(path)


# --- the record --------------------------------------------------------------------------------------------------------

def test_a_well_formed_runtime_record_loads_and_has_its_importer(tmp_path):
    asset = load_text(tmp_path, runtime_toml())
    assert asset.kind == 'data' and run.importer_of(asset) == ('skate-runtime', 1)
    assert run.importer_of(load_text(tmp_path, runtime_toml().replace('"skate-runtime"', '"skate-other"')
                                     .replace('[recipe.settings]\nmanifest_sha256', '[recipe.settings]\nx'))) is None


@pytest.mark.parametrize('kwargs, reason', [
    ({'version': 2}, 'importer "skate-runtime" version 1'),
    ({'sources': records.SKATE_RUNTIME_SOURCES[:3]}, 'pins exactly'),
    ({'sources': list(reversed(records.SKATE_RUNTIME_SOURCES))}, 'pins exactly'),
    ({'settings': 'manifest_sha256 = "abc"\n'}, 'manifest_sha256'),
    ({'settings': f'manifest_sha256 = "{SHA}"\nextra = 1\n'}, 'manifest_sha256'),
    ({'outputs': ('/Game/SkateRuntime/Other',)}, 'RuntimeData'),
])
def test_a_malformed_runtime_record_is_refused(tmp_path, kwargs, reason):
    with pytest.raises(records.RecordError, match=reason):
        load_text(tmp_path, runtime_toml(**kwargs))


def test_the_record_pins_the_same_bytes_as_the_generator_record():
    asset = records.load_asset(RECORD / 'asset.toml')
    generator = {s.path: s.sha256 for s in records.load_asset(GENERATOR / 'asset.toml').sources}
    assert [s.path for s in asset.sources] == records.SKATE_RUNTIME_SOURCES
    for source in asset.sources:
        assert generator[source.path] == source.sha256
        assert records.sha256_file(RECORD / source.path) == source.sha256
    assert asset.references == ['generator/skate/runtime']
    assert asset.recipe['settings']['manifest_sha256'] == sr.PACKAGE_MANIFEST_SHA256
    assert [o.package for o in asset.outputs] == ['/Game/SkateRuntime/RuntimeData']
    sr.verify_record(RECORD)


# --- the input list ----------------------------------------------------------------------------------------------------

def test_the_input_list_is_sorted_unique_and_refuses_bad_lines():
    rows = sr.read_inputs(RECORD)
    assert len(rows) == sr.EXPECTED_READS and sum(sr.CLIP.fullmatch(r) is not None for _, r in rows) == sr.EXPECTED_CLIPS
    for raw in (f'{SHA}  b\n{SHA}  a\n'.encode(), f'{SHA}  a\n{SHA}  a\n'.encode(), f'{SHA}  ../a\n'.encode(),
                f'{SHA} a\n'.encode(), f'{SHA}  a'.encode()):
        with pytest.raises(ValueError):
            sr.parse_inputs(raw)


def test_the_assembler_reads_only_the_runtime_text_motion_and_manifest_files():
    names = ['README.md', 'bundle.json', 'package-manifest.json', 'motion/rig.json', 'motion/metadata/bank-0.json',
             'motion/clips/0/A.json', 'motion/clips/0/deep/B.json', 'runtime/settings.json', 'runtime/other.json']
    assert sr.assembler_reads(names) == ['bundle.json', 'motion/clips/0/A.json', 'motion/metadata/bank-0.json',
                                         'motion/rig.json', 'package-manifest.json', 'runtime/settings.json']


def test_a_tree_with_an_extra_or_changed_input_is_refused(tmp_path):
    data = tmp_path / 'Data'
    (data / 'runtime').mkdir(parents=True)
    (data / 'bundle.json').write_bytes(b'{}')
    rows = [(hashlib.sha256(b'{}').hexdigest(), 'bundle.json')]
    old = sr.EXPECTED_READS
    try:
        sr.EXPECTED_READS = 1
        sr.verify_inputs(rows, data)
        (data / 'runtime' / 'settings.json').write_bytes(b'{}')
        with pytest.raises(ValueError, match='differs from the pinned input list'):
            sr.verify_inputs(rows, data)
        (data / 'runtime' / 'settings.json').unlink()
        (data / 'bundle.json').write_bytes(b'{"x": 1}')
        with pytest.raises(ValueError, match='differs from its pin'):
            sr.verify_inputs(rows, data)
    finally:
        sr.EXPECTED_READS = old


@pytest.mark.skipif(not DATA_READY, reason='the tracked Skate/Data tree is not present')
def test_the_tracked_data_tree_matches_the_pinned_list():
    sr.verify_inputs(sr.read_inputs(RECORD), sr.DATA)


# --- the editor read-back ----------------------------------------------------------------------------------------------

RECEIPT = {'clips': 3324, 'runtime': {'settings.skate': {'bytes': 10, 'sha1': 'a'}, 'action.graph': {'bytes': 5, 'sha1': 'b'}}}
REPORT = {'exact': True, 'negative_control': True, 'runtime_exact': True, 'runtime_negative_control': True,
          'runtime_invalid_record_controls': 3, 'runtime_asset': '/Game/SkateRuntime/RuntimeData.RuntimeData',
          'runtime_files': 2, 'runtime_bytes': 15, 'clips': 3324}


def test_a_verify_report_that_agrees_with_the_receipt_is_accepted():
    assert verify.problems(REPORT, RECEIPT, '/Game/SkateRuntime/RuntimeData') == []


@pytest.mark.parametrize('change, reason', [
    ({'runtime_exact': False}, 'runtime_exact'),
    ({'runtime_negative_control': None}, 'runtime_negative_control'),
    ({'runtime_invalid_record_controls': 2}, 'runtime_invalid_record_controls'),
    ({'runtime_asset': '/Game/Other/RuntimeData.RuntimeData'}, 'names'),
    ({'runtime_files': 7}, 'runtime files'),
    ({'runtime_bytes': 16}, 'runtime bytes'),
    ({'clips': 1}, 'clips'),
])
def test_a_verify_report_that_disagrees_is_refused(change, reason):
    found = verify.problems({**REPORT, **change}, RECEIPT, '/Game/SkateRuntime/RuntimeData')
    assert found and any(reason in p for p in found)


def test_the_importer_imports_then_verifies_and_checks_the_report():
    source = (ROOT / 'unreal/Scripts/import_asset.py').read_text()
    body = source[source.index('def _skate_runtime(plan):'):source.index('def main():')]
    body = body[body.index('"""', body.index('"""') + 3):]   # the code after the docstring
    assert body.index('import_runtime') < body.index('.verify,') < body.index('skate_verify.problems')
    assert "plan['importer'] == 'skate-runtime'" in source
    plan = (ROOT / 'tools/import/run.py').read_text()
    assert "skate_runtime.prepare(asset.folder, build)" in plan
