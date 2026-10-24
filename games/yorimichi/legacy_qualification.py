"""Yorimichi's managed declaration and closed hash-index preparation profile.

The existing recipe and one normal operational metadata task are entered. Game/native
tasks remain unsupported. The named files below are code providers, not a certificate
that every data.stage prerequisite can execute or repair.
"""
from pathlib import Path

# Computed spec_from_file_location sites in the current normal recipe need explicit
# seeds in addition to ordinary static imports. Unknown paths still refuse pre-exec.
CODE_SEEDS = (
    'build.py', 'build_v2.py', 'legacy_qualification.py', 'runtime_data.py',
    'assets/characters/pipeline/definition.py', 'assets/characters/adventure/library.py',
    'tools/kart_grip_editor/source_identity.py', 'foliage_build.py', 'compile_inputs.py',
    'skatepark_build.py', 'treehouse_pieces.py', 'export_digest.py', 'city_inputs.py',
    'city_tile_products.py', 'city_harbor_inputs.py', 'tools/racing_assets.py',
    'tools/package_cook.py', 'tools/game_binary.py', 'world/source_registry.py',
    'world/yori.py', 'world/texture_catalog.py', 'world/train/bake_manifest.py',
    'world/regions/brinecove/foliage_names.py', 'world/regions/craterpark/v2/v4_config.py',
    'world/regions/craterpark/v2/trees.py', 'unreal/Scripts/horse_data.py',
    'craterpark_atomic_build.py', 'forest_atomic_build.py', 'props_atomic_build.py',
    'treehouse_atomic_build.py', 'hidamari_build.py', 'hidamari_prop_build.py',
    'belmonte_atomic_build.py', 'belmonte_north_build.py', 'belmonte_scene_build.py',
    'brinecove_atomic_build.py', 'stable_atomic_build.py', 'houses_build.py',
    'southwest_atomic_build.py', 'mega_build.py', 'swordcamp_build.py',
    'megapark_atomic_build.py', 'lake_atomic_build.py', 'skatepark_atomic_build.py',
    'vehicle_atomic_build.py', 'train_carriage_build.py', 'train_atomic_build.py',
    'hidamari_tree_build.py', 'island_native_policy.py', 'city_atomic_products.py',
    'gondola_atomic_build.py', 'ferry_ship_atomic_build.py', 'ferry_terminal_atomic_build.py',
    'network_identity.py', 'content_policy.py', 'region_exports.py',
    'terrain_atomic_build.py', 'village_atomic_build.py', 'region_texture_inputs.py',
    'assets/vehicles/gondola/params.py', 'world/gondola/inputs.py',
    'world/gondola/validation.py', 'world/gondola/structures.py',
    'world/asset_catalog.py', 'world/material_specs.py', 'world/train/budgets.py',
    'world/regions/hidamari/prop_roster.py', 'world/regions/belmonte/ground_names.py',
    'southwest_atomic_products.py', 'world/racing/courses.py',
    'world/forest_parameters.py', 'world/prop_sources.py', 'world/vehicle_sources.py',
    'world/regions/brinecove/logical_catalogue.py',
    'world/regions/hidamari/source_context.py', 'world/regions/hidamari/tree_policy.py',
    'hidamari_metadata.py', 'world/regions/hidamari_stable/query_inputs.py',
    'world/regions/swordcamp/catalogue.py', 'world/regions/houses/catalogue.py',
    'world/regions/houses/layout.py', 'world/regions/ferry/ship_sources.py',
    'world/regions/ferry/site_inputs.py',
    'world/regions/belmonte/model_sources.py', 'world/regions/zeppelin/atomic.py',
    'world/regions/hippodrome/atomic.py', 'world/regions/hidamari_stable/catalogue.py',
    'world/regions/hidamari/logical_catalogue.py',
    # Direct-spec seeds still execute in their original real package hierarchy.
    # These initializers are code inputs even when static imports never name them.
    'world/train/__init__.py', 'world/regions/brinecove/__init__.py',
    'world/regions/ferry/__init__.py', 'world/regions/hidamari_stable/__init__.py',
    'world/regions/swordcamp/__init__.py',
    'world/regions/belmonte/source.py',
    'world/regions/village/atomic_sources.py',
)


def source_names(checkout):
    """Use the existing static local-import resolver, never execute a recipe to capture it."""
    from atelier.source_imports import ImportScanner
    from atelier.build_v2.controller_client import MAX_NAMED_ISSUER_FILES
    checkout = Path(checkout)
    game = checkout / 'games/yorimichi'
    scanner = ImportScanner()
    names = set()
    for seed in CODE_SEEDS:
        for source in scanner.local_imports(game / seed,
                                           (game, game / 'world', game / 'world/regions',
                                            checkout / 'platform/studio')):
            names.add(source.relative_to(checkout).as_posix())
    # Capture the actual scheduler/declaration code even when a recipe imports only a
    # subset of its names; no helper implementation is inferred from a Git revision.
    for seed in ('build.py', 'build_products.py', 'build_v2/controller_entry.py'):
        for source in scanner.local_imports(checkout / 'platform/studio/atelier' / seed):
            names.add(source.relative_to(checkout).as_posix())
    if len(names) > MAX_NAMED_ISSUER_FILES:
        raise ValueError('Yorimichi declaration code exceeds the bounded issuer capture')
    return tuple(sorted(names))


def discover(manifest, request, *, captured_files=None):
    """Enter actual load_recipe/steps/Graph over the exact named captured providers."""
    from atelier.build_v2.controller_client import _read_at, _captured_source
    from atelier.build_v2.legacy_qualification import (
        CapturedCode, IdentityBinding, captured_recipe_imports, verify_callable, diagnostic_phase,
    )
    import importlib
    checkout = Path(manifest['checkout'])
    with diagnostic_phase('discovery.bytes'):
        files = (list(captured_files) if captured_files is not None else
                 [(name, _read_at(manifest['issuer_root'], name, 8 * 1024 * 1024))
                  for name in manifest['issuer_files']])
        if _captured_source(files).digest != manifest['issuer_digest']:
            raise ValueError('captured recipe issuer changed')
        sources = [CapturedCode(str(checkout / name), raw) for name, raw in files if name.endswith('.py')]
    with captured_recipe_imports(sources, checkout=checkout,
                                 platform_roots=manifest['python_context']['platform_roots']):
        from atelier import build, build_products, paths
        from atelier.build_snapshot import require_complete
        from atelier.build_v2.controller_entry import declaration_context
        # Also check the fresh loader's callable/environment at the original
        # filename; no preloaded module or pycache timestamp supplies its origin.
        recipe_loader = next(source for source in sources
                             if source.filename == str(checkout / 'platform/studio/atelier/build.py'))
        verify_callable(build.load_recipe, recipe_loader, qualname='load_recipe',
                        namespace=build.__dict__, globals_={
                            'paths': IdentityBinding(paths), 'importlib': IdentityBinding(importlib)})
        with paths.captured_declaration('yorimichi'):
            require_complete(paths.build_root() / 'yorimichi', game='yorimichi')
            with diagnostic_phase('discovery.load'):
                recipe = build.load_recipe('yorimichi')
            with diagnostic_phase('discovery.steps'):
                steps = recipe.steps(declaration_context('yorimichi'))
            with diagnostic_phase('discovery.graph'):
                build.check_declarations(steps)
                graph = build_products.Graph(steps)
            with diagnostic_phase('discovery.select'):
                selected = graph.select(request['wanted'])
            controllers = [step.controller.request(checkout) for step in selected
                           if step.controller is not None]
            names = [step.name for step in selected]
            # Diagnostic scheduling labels/family names only, never permission,
            # source identity, arbitrary repr or raw command/input values.
            first = next((step for step in selected if step.controller is None), None)
            blocker = None if first is None else {
                'unit': first.name, 'heavy': first.heavy, 'replan': first.replan,
                'commands': [type(command).__name__ for command in first.commands],
                'calls': [getattr(command.fn, '__module__', '') + '.' + getattr(command.fn, '__qualname__', '')
                          for command in first.commands if type(command).__name__ == 'Call'],
            }
            if (first is not None and first.name == 'world.textures.leaf_broad'
                    and not graph.prerequisites(first) and not first.references
                    and blocker['commands'] == ['Python']):
                from atelier.build_hashes import HashIndex
                from atelier.build_cache import Store
                # The actual existing fingerprint API and an in-memory verification
                # index: no new encoder, persistent index write or cache authority.
                key, _ = build.fingerprint_state(first, {}, index=HashIndex(verify=True), tool_cache={})
                candidate = Store().action(key)
                blocker.update(fingerprint=key, candidate_present=candidate.is_file() and not candidate.is_symlink())
    return {'selected': names, 'controllers': controllers, 'first_legacy': blocker}


def _prior_record(client):
    """Bounded correlated observations only; the Rust host validates/resumes authority."""
    import hashlib
    from atelier.build_v2.controller_client import _json
    if client.record_digest is None:
        return None
    raw = bytearray()
    while True:
        page = client.request({'type': 'observe', 'witnesses': [], 'record_offset': len(raw)})['record_page']
        raw.extend(bytes.fromhex(page['hex']))
        if len(raw) == page['total']:
            break
    if hashlib.sha256(raw).hexdigest() != client.record_digest:
        raise ValueError('prior selection observation changed')
    return _json(bytes(raw))


def _control_index(manifest, request, client):
    """@cc [owner:fontanierh,label:correctness;safety] closed-normal-hash-index-preparation
    The existing HashIndex constructor/close MUST run only after its exact four SQLite
    claims receive permission, and settlement MUST observe every file/absence after close.
    The disposable hint's memory fallback MUST remain valid without certifying cache
    availability. Same-source continuation MUST revalidate old outputs; source changes
    MUST use Supersede with complete ClosedReplay and no counter reset/old settled credit.
    Unknown prior scopes MUST refuse. No game/native/restore or Graph Finish permission
    is granted. See test_legacy_qualification.py control-index regressions.
    """
    import hashlib
    import os
    import stat
    import sqlite3
    import _sqlite3
    import types
    from atelier.build_v2.controller_client import _read_at, MAX_SOURCE_TOTAL_BYTES
    from atelier.build_v2.legacy_client import AuthorityRefused
    from atelier.build_v2.legacy_qualification import CapturedCode, IdentityBinding, captured_recipe_imports, verify_callable
    checkout = Path(manifest['checkout'])
    base = 'build/yorimichi'
    paths = tuple(base + '/.state/file-hashes.sqlite3' + suffix for suffix in ('', '-journal', '-wal', '-shm'))
    task = 'control.hash-index.prepare'
    files = [(name, _read_at(manifest['issuer_root'], name, 8 * 1024 * 1024)) for name in manifest['issuer_files']]

    def witness(name):
        try:
            raw = _read_at(checkout, name, MAX_SOURCE_TOTAL_BYTES)
        except FileNotFoundError:
            return {'path': name, 'fact': {'kind': 'absent'}}
        mode = stat.S_IMODE(os.lstat(checkout / name).st_mode)
        return {'path': name, 'fact': {'kind': 'file', 'digest': hashlib.sha256(raw).hexdigest(),
                                     'size': len(raw), 'mode': mode}}

    anchor = os.lstat(checkout / base)
    if not stat.S_ISDIR(anchor.st_mode):
        raise AuthorityRefused('control preparation output anchor is not a real directory')
    anchor = {'path': base, 'device': anchor.st_dev, 'inode': anchor.st_ino}
    claims = [{'path': name, 'canonical': name, 'anchor': anchor} for name in paths]
    source = f'games/{request["game"]}/legacy_qualification.py'
    observation = {'project': request['game'], 'selector': request['wanted'],
                   'source_plan': manifest['issuer_digest'],
                   'request_digest': manifest['scheduler_request']['digest'],
                   'issuer': manifest['issuer_digest'], 'controller_source': manifest['source_digest'],
                   'roots': [base + '/.state'], 'sources': [witness(source)]}
    frame = {'profile': 'control_preparation', 'topology': manifest['issuer_digest'], 'inputs': [],
             'tasks': [{'id': task, 'replay': 'closed_replay', 'writes': claims}]}
    old = _prior_record(client)
    if old is not None:
        previous = old.get('frame')
        if previous is not None:
            scope = previous['scope']
            if (scope['profile'] != 'control_preparation' or len(scope['tasks']) != 1
                    or scope['tasks'][0]['id'] != task
                    or scope['tasks'][0]['replay'] != 'closed_replay'
                    or [item['path'] for item in scope['tasks'][0]['writes']] != list(paths)):
                raise AuthorityRefused('existing epoch is outside the exact hash-index repair family')
        same = all(old['binding'].get(key) == observation[key] for key in observation if key != 'sources')
        expected_sources = {name: witness(name) for name, _ in files}
        same = same and {item['path']: item for item in old['binding']['sources']} == expected_sources
        if not same:
            client.request({'type': 'supersede', 'observation': observation, 'initial_frame': frame})
            previous = None  # No old settled credit; the same complete claims replay.
        else:
            client.request({'type': 'prepare_selection', 'observation': observation})
            if previous is not None and not previous['pending']:
                settled = previous['settled']
                if len(settled) != 1 or settled[0]['task'] != task:
                    raise AuthorityRefused('existing control settlement is incomplete')
                client.request({'type': 'observe', 'witnesses': settled[0]['outputs'], 'record_offset': None})
                print('Managed hash-index preparation: prior settlement revalidated; no replay', flush=True)
                return
    else:
        client.request({'type': 'prepare_selection', 'observation': observation})
        previous = None
    if client.frame is None:
        client.request({'type': 'advance', 'observation': frame})
    attempt = 'index-' + manifest['nonce']
    # Every possible SQLite sidecar is checked before the closed replay permission.
    for name in paths:
        witness(name)
    client.request({'type': 'begin_attempt', 'attempt': {
        'id': attempt, 'members': [task], 'execution': {'kind': 'in_process'}, 'guard': None}})
    sources = [CapturedCode(str(checkout / name), raw) for name, raw in files if name.endswith('.py')]
    with captured_recipe_imports(sources, checkout=checkout,
                                 platform_roots=manifest['python_context']['platform_roots']):
        from atelier import build_hashes
        code = next(item for item in sources if item.filename == str(checkout / 'platform/studio/atelier/build_hashes.py'))
        if (sqlite3.connect is not _sqlite3.connect or sqlite3.Connection is not _sqlite3.Connection
                or type(sqlite3.connect) is not types.BuiltinFunctionType):
            raise AuthorityRefused('installed SQLite entry differs from the checked platform provider')
        verify_callable(build_hashes.HashIndex.__init__, code, qualname='HashIndex.__init__',
                        namespace=build_hashes.__dict__, defaults=(None,),
                        keyword_defaults={'read_only': False, 'verify': False},
                        globals_={'Path': IdentityBinding(Path), 'sqlite3': IdentityBinding(sqlite3)},
                        builtins_={'OSError': IdentityBinding(OSError)})
        verify_callable(build_hashes.HashIndex.close, code, qualname='HashIndex.close',
                        namespace=build_hashes.__dict__, globals_={'sqlite3': IdentityBinding(sqlite3)})
        for method in ('__enter__', '__exit__'):
            verify_callable(getattr(build_hashes.HashIndex, method), code,
                            qualname='HashIndex.' + method, namespace=build_hashes.__dict__)
        # Execute the actual normal implementation, not a second index/cache.
        with build_hashes.HashIndex(checkout / paths[0], verify=request['options']['verify']) as index:
            usable = index.connection is not None
    if usable:
        try:
            with sqlite3.connect((checkout / paths[0]).as_uri() + '?mode=ro', uri=True, timeout=.1) as database:
                names = {row[0] for row in database.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                usable = (database.execute('PRAGMA quick_check').fetchall() == [('ok',)]
                          and names == {'hashes_v1', 'memos_v1'})
        except sqlite3.Error:
            usable = False
    # This is a disposable hint, not an output/cache authority. Preserve the
    # actual constructor's memory fallback and every existing byte on failure.
    # Settlement certifies complete bounded effects, never a usable cached digest.
    outputs = [witness(name) for name in paths]
    client.request({'type': 'settle', 'observation': {
        'task': task, 'attempt': attempt, 'inputs': manifest['issuer_digest'], 'outputs': outputs}})
    print('Managed hash-index preparation: actual normal implementation settled; '
          f'hint={"usable" if usable else "unavailable"}; no game task permission', flush=True)


def run(*, manifest, request, client, custody):
    """Discover, fulfill controller order, and prepare/repair one real metadata task.

    No target completion/Finish is issued: game/native mutation, batch, replan and final
    Graph validation remain unsupported. Only exact hash-index claims may replay.
    """
    from atelier.build_v2.legacy_client import AuthorityRefused
    if request['game'] != 'yorimichi' or set(custody) != {'build', 'content', 'writer'}:
        raise AuthorityRefused('unsupported managed declaration profile')
    checkout = Path(manifest['checkout'])
    output = checkout / 'build/yorimichi'
    if Path(manifest['output']) != output:
        raise AuthorityRefused('discovery supports only the anchored default project output')
    # The host already created the exact output root and writer. Repeating that
    # mkdir is not a genuine mutating task, and cannot justify a whole-output claim.
    # Read-only discovery itself receives no mutation/replay credit. The separate
    # closed hash-index task below uses real original operations and permissions.
    selected = discover(manifest, request)
    obligations = manifest['controller_obligations']
    if len(obligations) != len(selected['controllers']):
        raise AuthorityRefused('selected controller obligations do not match the actual Graph')
    import json
    from atelier.build_v2.controller_client import _read_at
    for index, (binding, original) in enumerate(zip(obligations, selected['controllers'])):
        if binding['unit'] != original['targets'][0]:
            raise AuthorityRefused('selected controller ordering differs from original Graph')
        bound = json.loads(_read_at(checkout, binding['request']['path'], 2 * 1024 * 1024))
        if bound != original:
            raise AuthorityRefused('selected controller declaration changed after fulfillment')
    _control_index(manifest, request, client)
    print('Managed next unsupported selected task: ' + json.dumps(selected['first_legacy'], sort_keys=True)[:768], flush=True)
    print(f'Managed captured recipe discovery: {len(selected["selected"])} selected declarations; '
          'HELD Unsupported before game-task dispatch', flush=True)
    raise AuthorityRefused('selected game-task execution, repair and final Graph completion remain unsupported')
