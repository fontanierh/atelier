"""Replay the real city owner's old header through the shared native adapter."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from atelier import mesh_reuse, paths, source_imports, unreal_mesh_reuse as native

REPO = Path(__file__).resolve().parents[3]
GAME = REPO/'games/yorimichi'
OWNER = 'games/yorimichi/unreal/Scripts/import_city_surface_tiles.py'
RAW = 'games/yorimichi/unreal/Scripts/mesh_import.py'
SUPPORT = 'games/yorimichi/unreal/Scripts/city_parent_transition.py'
PRODUCTS = 'games/yorimichi/city_tile_products.py'

# Reuse the shared adapter's fake Unreal/disk fixture, while exercising the real
# game owner, raw policy, validator roots and full static owner projection.
_spec = importlib.util.spec_from_file_location('city_receipt_adapter_fixtures',
    REPO/'platform/studio/tests/test_unreal_mesh_reuse.py')
_fixtures = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixtures)
scene = _fixtures.scene


@pytest.fixture
def family_history(scene, monkeypatch):
    with monkeypatch.context() as scan:
        scan.setattr(paths, 'REPO', REPO)
        originals = source_imports.local_imports(REPO/OWNER, (GAME/'world', GAME/'world/regions'))
    files = set(originals) | {REPO/RAW, REPO/SUPPORT}
    texts = {str(p.relative_to(REPO)):p.read_text() for p in files if p.is_relative_to(REPO)}
    # These exact source bytes predate the five-family implementation. In
    # particular the old transition helper must not be synthesized from today's
    # helper: that would test the wrong historical receipt policy.
    history = json.loads((GAME/'tests/fixtures/city_three_family_policy.json').read_text())
    assert history['revision'] == 'c24eba4c087c6bce02a2e3740a0c7d3eb7823c94'
    assert history['sha256'] == {'games/yorimichi/city_tile_products.py': '2ed86b94d2fd495b525218f0329bff7889a10113568c7c67b579357c21249f21', 'games/yorimichi/unreal/Scripts/city_parent_transition.py': '77ac41c5904f4cd1d08a9bf523cee6383a03fbf56e3ec51032953e0a736488d4'}
    for name, text in history['sources'].items():
        assert hashlib.sha256(text.encode()).hexdigest() == history['sha256'][name]
        texts[name] = text
    repo = paths.REPO
    for name, text in texts.items():
        file = repo/name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text)
    # Resolve the copied actual import closure inside the private repository.
    monkeypatch.setattr(source_imports, '__file__', str(repo/'platform/studio/atelier/source_imports.py'))
    monkeypatch.setattr(native, 'observed_environment', lambda *a: True)
    recorded = {name:hashlib.sha256((Path(name).name+text).encode()).hexdigest() for name,text in texts.items()}
    monkeypatch.setattr(mesh_reuse, 'prior_stamp', lambda *a: dict(fingerprint='f'*64,time=1.,
        input_state={'inputs':{'<repo>/'+name:value for name,value in recorded.items()}}))
    monkeypatch.setattr(mesh_reuse, 'saved_source', lambda repo,name,key:
        texts.get(name) if key == recorded.get(name) else None)
    for member, file in scene.staged.items():
        if member.startswith('content/'):
            target = scene.content/member.removeprefix('content/')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(file.read_bytes())

    def make():
        spec = importlib.util.spec_from_file_location('recorded_city_transition', repo/SUPPORT)
        support = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(support)
        return native.MeshReuse(scene.ctx, 'unreal.desktop', repo/RAW, ('_source_mesh',),
            owner_script=repo/OWNER, owner_roots=(repo/'games/yorimichi/world', repo/'games/yorimichi/world/regions'),
            validation_script=repo/RAW, validation_functions=('legacy_options_match',),
            owner_transition=support.excluded_packages)

    first = make()
    assert PRODUCTS in first.owner_texts and OWNER in first.owner_texts
    assert RAW not in first.owner_texts and SUPPORT not in first.owner_texts
    # Establish an actual saved original receipt using the current adapter's
    # ordinary successful acquisition/validation/finalization protocol.
    assert first.enabled
    _fixtures.acquire(scene, first, validator=lambda mesh: True)
    first.imported('Mesh')  # fixture packages stand in for the successful original import
    first.validated('Mesh')
    mesh_reuse.finalize_pending(scene.ctx, 'unreal.desktop', 'e'*24)
    (repo/PRODUCTS).write_text((REPO/PRODUCTS).read_text())
    (repo/SUPPORT).write_text((REPO/SUPPORT).read_text())
    return scene, make, first, repo


def test_recorded_three_family_header_revalidates_unchanged_piece_without_import(family_history):
    scene, make, first, repo = family_history
    saved = first.receipts.path.read_bytes()
    current = make()
    assert current.previous_owner_transition and current.local_compatible
    assert first.receipts.header['policy'] in current.previous_receipt_policies
    assert current.receipts.header['policy'] != first.receipts.header['policy']
    checks = []
    assert _fixtures.acquire(scene, current, validator=lambda mesh: checks.append(mesh) or True)
    assert len(checks) == 1 and current.counts == dict(reused_local=1,reused_candidate=0,imported=0)
    assert current.receipts.path.read_bytes() == saved  # publication remains deferred
    current.validated('Mesh')
    mesh_reuse.finalize_pending(scene.ctx, 'unreal.desktop', 'e'*24)
    assert json.loads(current.receipts.path.read_text())['policy'] == current.receipts.header['policy']


@pytest.mark.parametrize('bad', ['no_receipt', 'source', 'source_bytes', 'sidecar', 'validator', 'finishing', 'closure', 'new_piece'])
def test_family_history_never_certifies_changed_or_unrecorded_outputs(family_history, bad):
    scene, make, first, repo = family_history
    if bad == 'no_receipt': first.receipts.path.unlink()
    if bad == 'source': scene.tags[scene.package] = None
    if bad == 'source_bytes':
        package, source, digest = scene.sources[0]
        source.write_bytes(b'changed actual FBX')
        scene.sources[0] = (package, source, mesh_reuse.digest(source))
    if bad == 'sidecar': (scene.content/'Region/Mesh.uexp').write_bytes(b'changed bytes')
    if bad == 'finishing':
        p = repo/OWNER
        p.write_text(p.read_text()+'\nFINISHING_CHANGED = True\n')
    if bad == 'closure':
        p = repo/OWNER
        p.write_text(p.read_text()+'\nimport newly_added_owner\n')
        (repo/'games/yorimichi/unreal/Scripts/newly_added_owner.py').write_text('OWNED = True\n')
    current = make()
    if bad == 'new_piece':
        result = current.acquire('NewPiece', scene.package, geometry={'source':'same'},
                                 sources=scene.sources, donor_geometry={'source':'same'}, validator=lambda mesh: True)
    else:
        result = _fixtures.acquire(scene, current, validator=lambda mesh: bad != 'validator')
    assert result is None
    assert current.counts['reused_local'] == current.counts['reused_candidate'] == 0
