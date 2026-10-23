"""A change to the mini-mega's shape rebuilds the ramp and the map, never the terrain or the world import."""
import hashlib
import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

from atelier import build, build_audit, build_cache, build_deferred, build_inputs, build_products

MEGA = Path(__file__).resolve().parents[1] / 'world' / 'regions' / 'mega'
_BASELINE_CACHE = {}
_BELMONTE_RUNTIME_JSON = None
_BELMONTE_GROUND_JSON = None
_BELMONTE_REPORT_JSON = '{"meshes": [], "materials": {}}'


def _belmonte_runtime_payload():
    global _BELMONTE_RUNTIME_JSON, _BELMONTE_GROUND_JSON
    if _BELMONTE_RUNTIME_JSON is None or _BELMONTE_GROUND_JSON is None:
        library = json.loads((build.paths.game_dir('yorimichi') / 'assets/belmonte/source.json').read_text())
        names = [row['name'] for row in library['meshes'] if row['name'].startswith('SM_BM_BT_Terrain_')]
        names.append('SM_BM_NorthApron')
        transform = {'translation_cm': [0., 0., 0.], 'rotation_xyzw': [0., 0., 0., 1.], 'scale': [1., 1., 1.]}
        _BELMONTE_RUNTIME_JSON = json.dumps({
            'origin_cm': [55000., -450000., 21000.],
            'groups': [{'asset': f'/Game/{name}.{name}', 'transforms': [transform],
                        'plant': False, 'collision': True} for name in names],
        })
        entries = {row['name']: row for row in library['meshes'] if row['name'] in names}
        surfaces = [dict(name=name, path='ground/glb/' + name + '.glb', bounds_m=entries[name]['bounds_m']
                         if name in entries else [[0, 0, 0], [100, 100, 1]]) for name in [*names, 'SM_BM_NorthCountry']]
        _BELMONTE_GROUND_JSON = json.dumps(dict(schema=1, origin_cm=[55000., -450000., 21000.], surfaces=surfaces))
    return _BELMONTE_RUNTIME_JSON, _BELMONTE_GROUND_JSON


def _write_belmonte_fixture(out_dir):
    runtime_json, ground_json = _belmonte_runtime_payload()
    registry = out_dir / 'belmonte/runtime.json'
    if not registry.is_file():
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(runtime_json)
        (registry.parent / 'build-report.json').write_text(_BELMONTE_REPORT_JSON)
    ground = out_dir / 'products/belmonte/ground.json'
    if not ground.is_file():
        ground.parent.mkdir(parents=True, exist_ok=True)
        ground.write_text(ground_json)


def _has_custom_files(tmp_path):
    if not tmp_path.exists():
        return False
    for child in tmp_path.iterdir():
        if child.name not in ('belmonte', 'products'):
            return True
    belmonte = tmp_path / 'belmonte'
    if belmonte.is_dir():
        for child in belmonte.iterdir():
            if child.name not in ('runtime.json', 'build-report.json'):
                return True
    products = tmp_path / 'products'
    if products.is_dir():
        for child in products.rglob('*'):
            if child.is_file() and child.relative_to(products) != Path('belmonte/ground.json'):
                return True
    return False


def _env_signature():
    return (
        os.environ.get('ATELIER_CRATERPARK_EDITOR_PARK', ''),
        os.environ.get('YORIMICHI_MUSIC_CATEGORIES', ''),
        os.environ.get('YORIMICHI_MUSIC_STYLES', ''),
        os.environ.get('YORIMICHI_MUSIC_GROUPS', ''),
        os.environ.get('YORIMICHI_MUSIC_LIMIT', ''),
    )


def _build_state(out_dir):
    _write_belmonte_fixture(out_dir)
    ctx = SimpleNamespace(game='yorimichi', out=out_dir, logs=out_dir / 'logs',
                          stamps=out_dir / 'stamps', uproject=None)
    recipe = build.load_recipe('yorimichi').steps(ctx)
    ordered = build.order(recipe, [step.name for step in recipe])
    controller_names = {step.name for step in ordered if step.controller is not None}
    # This fixture exercises v1 byte-stream fingerprints, not A3 or the Rust backend.
    # Never mint placeholder keys for migrated controllers or hide a content bridge.
    assert not any(controller_names & set(step.needs) for step in ordered if step.controller is None)
    steps = [step for step in ordered if step.controller is None]
    observations = {}
    step_inputs = {}
    provider_cache = {}
    for step in steps:
        build_deferred.validate(step)
        if not step.deferred_inputs:
            obs = build_deferred.observe(step)
        else:
            pkey = tuple((p.name, p.collect, p.settings, p.support) for p in step.deferred_inputs)
            if pkey not in provider_cache:
                provider_cache[pkey] = build_deferred.observe(step)
            cached_obs = provider_cache[pkey]
            obs = build_deferred.InputObservation(
                tuple([*step.inputs, Path(build_deferred.__file__), *cached_obs.paths[len(step.inputs) + 1:]]),
                cached_obs.metadata,
                cached_obs.members,
            )
        observations[step.name] = obs
        req = build.required_inputs(step, observation=obs)
        step_inputs[step.name] = tuple(str(p) for p in (*req, *step.optional_inputs))

    def unedited_hash(digest, path, *args, **kwargs):  # skip/shadow: names stand in for bytes either way
        digest.update(str(path).encode())

    def unedited_inventory(path, **kwargs):
        d = hashlib.sha256()
        d.update(str(path).encode())
        return {'source': d.hexdigest()}

    orig_hp, orig_inv = build._hash_path, build_inputs.inventory
    orig_tc, orig_atc = build_cache.tool_context, build_audit.tool_context
    build._hash_path = unedited_hash
    build_inputs.inventory = unedited_inventory
    build_cache.tool_context = lambda *a, **k: {'fixture': 'unchanged tools'}
    build_audit.tool_context = lambda *a, **k: {'fixture': 'unchanged tools'}
    try:
        before = {}
        for step in steps:
            before[step.name] = build.fingerprint(
                step, before, observation=observations[step.name], _tool_identity='fixture'
            )
            for product in step.products:
                before['product:' + product.name] = build_products.identity((product.name, before[step.name]))
    finally:
        build._hash_path = orig_hp
        build_inputs.inventory = orig_inv
        build_cache.tool_context = orig_tc
        build_audit.tool_context = orig_atc
    return out_dir, steps, observations, step_inputs, before


def changed_by(edited, tmp_path, monkeypatch, *, stable_products=()):
    """Legacy v1 steps whose fingerprint changes; migrated controller identities are tested through A3 separately.
    Inputs hash by name, and an input that is or contains
    edited hashes differently afterwards, so the test reads the recipe's dependencies and needs no built files."""
    tmp_path = Path(tmp_path)
    edited = Path(edited)
    stable_set = frozenset(stable_products)
    custom = _has_custom_files(tmp_path)
    _write_belmonte_fixture(tmp_path)

    if not custom:
        key = _env_signature()
        if key not in _BASELINE_CACHE:
            base_out = Path(tempfile.mkdtemp(prefix='atelier-changed-by-')).resolve()
            _BASELINE_CACHE[key] = _build_state(base_out)
        base_out, steps, observations, step_inputs, before = _BASELINE_CACHE[key]
        if edited == tmp_path or tmp_path in edited.parents:
            target = base_out / edited.relative_to(tmp_path)
        else:
            target = edited
    else:
        _, steps, observations, step_inputs, before = _build_state(tmp_path)
        target = edited

    target_str = str(target)

    def stand_in(digest, path, *args, **kwargs):
        s = str(path)
        inside = s == target_str or target_str.startswith(f'{s}/')
        digest.update(s.encode() + (b'edited' if inside else b''))

    def inventory(path, **kwargs):
        digest = hashlib.sha256()
        stand_in(digest, path)
        return {'source': digest.hexdigest()}

    monkeypatch.setattr(build, '_hash_path', stand_in)
    monkeypatch.setattr(build_inputs, 'inventory', inventory)
    monkeypatch.setattr(build_cache, 'tool_context', lambda *a, **k: {'fixture': 'unchanged tools'})
    monkeypatch.setattr(build_audit, 'tool_context', lambda *a, **k: {'fixture': 'unchanged tools'})

    after = {}
    for step in steps:
        inputs_changed = any(p == target_str or target_str.startswith(f'{p}/') for p in step_inputs[step.name])
        needs_changed = any(after[n] != before[n] for n in step.needs if n in after and n in before)
        reads_changed = any(
            after['product:' + r] != before['product:' + r]
            for r in step.reads if ('product:' + r) in after and ('product:' + r) in before
        )
        if inputs_changed or needs_changed or reads_changed:
            after[step.name] = build.fingerprint(
                step, after, observation=observations[step.name], _tool_identity='fixture'
            )
        else:
            after[step.name] = before[step.name]
        for product in step.products:
            if product.name in stable_set:
                after['product:' + product.name] = before['product:' + product.name]
            elif after[step.name] == before[step.name]:
                after['product:' + product.name] = before['product:' + product.name]
            else:
                after['product:' + product.name] = build_products.identity((product.name, after[step.name]))
    return {name for name in before if not name.startswith('product:') and before[name] != after[name]}


def test_ramp_shape_rebuilds_only_the_ramp_and_the_map(tmp_path, monkeypatch):
    # The package certifies and cooks every changed import before assembling its download.
    assert changed_by(MEGA/'ramp.py', tmp_path, monkeypatch) == {'world.mega', 'world.map', 'unreal.mega', 'data.stage',
                                                             'world.mega.geometry.Mega_Ramp', 'world.mega.geometry.Mega_Trim',
                                                             'world.mega.geometry', 'world.mega.assembled',
                                                             'data.content', 'data.network', 'unreal.cook', 'unreal.package'}


def test_ramp_place_still_reshapes_the_terrain(tmp_path, monkeypatch):
    changed = changed_by(MEGA/'layout.py', tmp_path, monkeypatch)
    assert {'world.layout', 'world.terrain', 'world.mega', 'world.map', 'unreal.world', 'unreal.mega'} <= changed
