"""Yorimichi's managed declaration and closed hash-index preparation profile.

The existing recipe and finite audited texture tasks are entered. Other game/native
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
    'world/regions/village/atomic_sources.py', 'world/gen_textures.py', 'legacy_texture_profile.py', 'legacy_treehouse_profile.py',
    'world/regions/treehouse/plan_tree.py', 'legacy_treehouse_discovery_profile.py', 'legacy_treehouse_export_profile.py',
    'world/export_region_piece.py', 'legacy_treehouse_data_profile.py',
    'world/regions/treehouse/canopy_data.py', 'legacy_treehouse_assembly_profile.py',
    'legacy_treehouse_recolour_profile.py', 'legacy_treehouse_library_profile.py',
    'world/regions/treehouse/assemble_atomic.py',
    'world/regions/craterpark/v2/editor_generate.py',
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
    for seed in ('build.py', 'build_products.py', 'build_v2/controller_entry.py', 'build_batch_worker.py'):
        for source in scanner.local_imports(checkout / 'platform/studio/atelier' / seed):
            names.add(source.relative_to(checkout).as_posix())
    if len(names) > MAX_NAMED_ISSUER_FILES:
        raise ValueError('Yorimichi declaration code exceeds the bounded issuer capture')
    return tuple(sorted(names))


def discover(manifest, request, *, captured_files=None, consumer=None):
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
        if consumer is not None:
            # Pure declaration mode ends before any qualified normal preparation.
            # The finite captured import scope remains active for execution.
            return consumer(build, graph, steps, selected, files)
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
    """Run the original scheduler through one qualified audited texture task.

    Course order remains independently checked by Rust. Unknown subsequent task
    families stop before mutation; batches, replan and whole-Graph Finish remain
    unsupported. The exact closed texture scope supports ordinary source-fix repair.
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
    # Read-only discovery itself receives no mutation/replay credit. The fixed
    # texture profile records normal preparation and its child before their effects.
    def execute_original(build, graph, steps, ordered, files):
        selected = {'controllers': [s.controller.request(checkout) for s in ordered if s.controller is not None]}
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
        authority = TextureAuthority(manifest, request, client, custody, build, graph, steps, ordered, files)
        ctx = build.Context(request['game'], create=False)
        ctx.fail_fast = request['options']['fail_fast']
        ctx.legacy_authority = authority
        return build._prepared_build(ctx, request['wanted'], force=False, touch=False, echo=print,
                    verify=request['options']['verify'], rebuild_reason=request['options'].get('rebuild_reason'), rebuild_touched=False,
                    record_cook_recovery=False, max_heavy_commands=request['options']['max_heavy_commands'],
                    prepared_steps=steps)
    return discover(manifest, request, consumer=execute_original)



def qualify_texture_aggregate(step, *, build, graph, products):
    """Recognize only the existing no-command read boundary; this grants no permission.

    The original scheduler must still own read-key computation, product observations,
    stamp publication and finalization. No callback, output ownership or task execution
    is inferred from this pure declaration observation.
    """
    from atelier.build_v2.legacy_client import AuthorityRefused
    expected = build.Step('world.textures', [], reads=list(products))
    actual, defaults = vars(step), vars(expected)
    if (type(step) is not build.Step or set(actual) - {'_query_bindings'} != set(defaults) - {'_query_bindings'}
            or any(actual[name] != value for name, value in defaults.items()
                   if name not in {'about', '_query_bindings'})
            or actual.get('_query_bindings')):
        raise AuthorityRefused('texture aggregate is not the original closed no-command read boundary')
    if graph.prerequisites(step) != ['world.textures.' + name.removeprefix('texture.') for name in products]:
        raise AuthorityRefused('texture aggregate dependency order differs from its actual producers')
    return step


def _complete_treehouse_export_roster(steps):
    """Availability only: strict raw-role qualification still precedes any permission."""
    parents = ('Tree_Canopy_Maple', 'Tree_Canopy_Crimson', 'Tree_Canopy_Amber', 'Tree_Canopy_Ginkgo')
    expected = {'world.treehouse_trees.export.' + parent for parent in parents}
    actual = {step.name for step in steps if step.name.startswith('world.treehouse_trees.export.')}
    return actual == expected


class TextureAuthority:
    """@cc [owner:fontanierh,label:correctness;safety] original-closed-texture-task
    Only the finite qualified texture scripts/arguments/spec/products and complete scheduler
    metadata scope MAY qualify. Every preparation/launch MUST first pass the live Rust
    authority; this object/metadata alone MUST NOT grant permission. Original scheduler,
    fingerprint, cache, audit, stamp and final output checks MUST remain the certifiers.
    Source fixes MUST preserve old claims/positive cleanup/counters via Supersede. Warm
    metadata work MUST use explicit permission, never a fabricated zero-work claim.
    Settle MUST follow final certificate revalidation; unknown subsequent families MUST
    stop before mutation without Finish. See finite profile/source/queue regressions and
    the separately retained real cold/failure/repair/current observations.
    """
    def __init__(self, manifest, request, client, custody, build, graph, steps, selected, files):
        import hashlib
        from atelier.build_v2.legacy_client import AuthorityRefused
        self.manifest, self.request, self.client = manifest, request, client
        self.custody, self.build, self.files = custody, build, files
        self.checkout = Path(manifest['checkout'])
        self.nonce = manifest['nonce']
        from legacy_texture_profile import qualify_texture_step, ROSTER
        from atelier.build_audit import _bind_captured_runtime
        # Qualify each RAW declaration before attaching its private runtime descriptor.
        names = {'world.textures.' + name for name in ROSTER}
        self.profiles, self.steps, self.runtimes = {}, {}, {}
        for step in selected:
            if step.name not in names:
                continue
            profile = qualify_texture_step(step, checkout=self.checkout,
                                           output_root=self.checkout / 'build/yorimichi')
            if graph.prerequisites(step):
                raise AuthorityRefused('texture has unqualified prerequisite effects')
            self.profiles[step.name], self.steps[step.name] = profile, step
            self.runtimes[step.name] = _bind_captured_runtime(
                step, checkout=self.checkout, issuer_files=manifest['issuer_files'])
        self.texture_steps = dict(self.steps)
        self.generated_inputs = set()
        self.output_paths = {name: (profile.output,) for name, profile in self.profiles.items()}
        self.native_steps, self.native_profiles, self.native_runtimes = {}, {}, {}
        from legacy_treehouse_profile import qualify_treehouse_planner
        from atelier.build_v2.legacy_native_action import _bind_native_runtime
        parents = ('Tree_Canopy_Maple', 'Tree_Canopy_Crimson', 'Tree_Canopy_Amber', 'Tree_Canopy_Ginkgo')
        native_names = {'world.treehouse_trees.geometry.' + parent for parent in parents}
        for step in selected:
            if step.name not in native_names:
                continue
            profile = qualify_treehouse_planner(step, checkout=self.checkout,
                                               output_root=self.checkout / 'build/yorimichi')
            self.native_steps[step.name], self.native_profiles[step.name] = step, profile
            self.output_paths[step.name] = tuple(path for _, roots in profile.products for path in roots)
            self.generated_inputs.update(profile.produced_inputs)
        from legacy_treehouse_export_profile import qualify_treehouse_export
        export_names = {'world.treehouse_trees.export.' + parent for parent in parents}
        exports_ready = _complete_treehouse_export_roster(selected)
        for step in selected:
            if not exports_ready or step.name not in export_names:
                continue
            profile = qualify_treehouse_export(step, checkout=self.checkout,
                                              output_root=self.checkout / 'build/yorimichi')
            self.native_steps[step.name], self.native_profiles[step.name] = step, profile
            self.output_paths[step.name] = tuple(path for _, roots in profile.products for path in roots)
            self.generated_inputs.update(profile.produced_inputs)
        from legacy_treehouse_recolour_profile import qualify_treehouse_recolour
        self.single_native = {}
        for step in selected:
            if not exports_ready or step.name != 'world.treehouse_trees.recolour':
                continue
            profile = qualify_treehouse_recolour(step, checkout=self.checkout,
                                                output_root=self.checkout / 'build/yorimichi')
            self.single_native[step.name] = profile
            self.native_steps[step.name], self.native_profiles[step.name] = step, profile
            self.output_paths[step.name] = tuple(path for _, roots in profile.products for path in roots)
            self.generated_inputs.update(profile.produced_inputs)
        self.steps.update(self.native_steps)
        from legacy_treehouse_discovery_profile import qualify_treehouse_discovery
        from atelier.build_v2.legacy_call import bind_captured_call
        self.discovery = next((step for step in selected if step.name == 'world.treehouse_trees.geometry'), None)
        self.discovery_profile = None
        self.call_steps, self.call_profiles, self.call_runtimes = {}, {}, {}
        if self.discovery is not None:
            profile = qualify_treehouse_discovery(self.discovery, checkout=self.checkout,
                                                 output_root=self.checkout / 'build/yorimichi')
            self.discovery_profile = profile
            self.call_steps[self.discovery.name], self.call_profiles[self.discovery.name] = self.discovery, profile
        from legacy_treehouse_assembly_profile import qualify_treehouse_assembly
        self.assembly = (next((step for step in selected if step.name == 'world.treehouse_trees.assembled'), None)
                         if exports_ready else None)
        if self.assembly is not None:
            profile = qualify_treehouse_assembly(self.assembly, checkout=self.checkout,
                                                output_root=self.checkout / 'build/yorimichi')
            self.call_steps[self.assembly.name], self.call_profiles[self.assembly.name] = self.assembly, profile
        for name, step in self.call_steps.items():
            profile = self.call_profiles[name]
            bind_captured_call(step, checkout=self.checkout,
                               issuer_files=manifest['issuer_files'], code_inputs=profile.code_inputs)
            self.call_runtimes[name] = vars(step)['_captured_call_runtime']
            self.steps[name] = step
            self.output_paths[name] = tuple(path for _, roots in profile.products for path in roots)
            self.generated_inputs.update(profile.produced_inputs)
        # All pure declaration/callback qualification precedes the private native
        # descriptors: closures keep the actual original child Step identities.
        for name, step in self.native_steps.items():
            self.native_runtimes[name] = _bind_native_runtime(
                step, checkout=self.checkout, issuer_files=manifest['issuer_files'],
                verifier=getattr(self.native_profiles[name], 'verifier', None))
        from legacy_treehouse_data_profile import qualify_treehouse_data
        from legacy_treehouse_library_profile import qualify_treehouse_library
        self.data_steps, self.python_qualifiers = {}, {}
        for step in selected:
            qualifier = (qualify_treehouse_data if step.name == 'world.treehouse_trees.data'
                         else qualify_treehouse_library if step.name in
                         {'world.treehouse_trees', 'world.treehouse_props', 'world.treehouse'} else None)
            if not exports_ready or qualifier is None:
                continue
            # The ordinary Graph remains the product/owner authority. Future
            # roles without a complete qualified producer roster receive no task.
            if any(name not in self.steps for name in graph.prerequisites(step)):
                continue
            profile = qualifier(step, checkout=self.checkout,
                                output_root=self.checkout / 'build/yorimichi')
            self.python_qualifiers[step.name] = qualifier
            self.data_steps[step.name] = (step, profile)
            self.steps[step.name] = step
            self.runtimes[step.name] = _bind_captured_runtime(
                step, checkout=self.checkout, issuer_files=manifest['issuer_files'])
            self.output_paths[step.name] = tuple(path for _, roots in profile.products for path in roots)
            self.generated_inputs.update(profile.produced_inputs)
        self.dones = {}
        self.native_launch = None
        first = next((step for step in selected if step.controller is None), None)
        if first is None or first.name not in self.steps:
            raise AuthorityRefused('first actual selected task is outside the closed texture family')
        self.controllers = {step.name: step.controller.request(self.checkout)
                            for step in selected if step.controller is not None}
        following = next((step.name for step in selected
                          if step.controller is None and step.name not in self.steps), None)
        next_family = next((step.name for step in selected
                            if step.controller is None and step.name not in self.steps
                            and step.name != 'world.textures'), None)
        print(f'Managed texture group declarations: {len(self.texture_steps)}; next actual boundary: {following}; '
              f'first nontexture task: {next_family}', flush=True)
        self.aggregate = next((step for step in selected if step.name == 'world.textures'), None)
        if self.aggregate is not None:
            qualify_texture_aggregate(self.aggregate, build=build, graph=graph,
                                      products=['texture.' + name for name in ROSTER])
        self.aggregate_done = None
        self.metadata = 'control.textures.scheduler'
        self.attempt = 'prepare-' + self.nonce
        self.preparation_attempt = self.attempt
        self.completed = {}
        self.begun = False
        self.hashlib = hashlib
        self.step = first
        self.runtime = self.runtimes.get(first.name)
        self.returned = None
        self.launch_context = None

    def witness(self, name):
        import os
        import stat
        from atelier.build_v2.controller_client import _read_at, MAX_SOURCE_TOTAL_BYTES
        try:
            info = os.lstat(self.checkout / name)
        except FileNotFoundError:
            return [{'path': name, 'fact': {'kind': 'absent'}}]
        if stat.S_ISDIR(info.st_mode):
            result = [{'path': name, 'fact': {'kind': 'directory', 'device': info.st_dev, 'inode': info.st_ino}}]
            for path in sorted((self.checkout / name).iterdir()):
                result.extend(self.witness(path.relative_to(self.checkout).as_posix()))
                if len(result) > 2048:
                    raise ValueError('texture operational output inventory exceeds its finite bound')
            return result
        raw = _read_at(self.checkout, name, MAX_SOURCE_TOTAL_BYTES)
        return [{'path': name, 'fact': {'kind': 'file', 'digest': self.hashlib.sha256(raw).hexdigest(),
                                      'size': len(raw), 'mode': stat.S_IMODE(info.st_mode)}}]

    def before_prepare(self, ctx, steps, wanted, *, expanded=False):
        import os
        from atelier.build_v2.legacy_client import AuthorityRefused
        from atelier.build_hashes import HashIndex
        self.keys = {name: self.build.fingerprint_state(step, {}, index=HashIndex(verify=True),
                                                       tool_cache={})[0]
                     for name, step in self.texture_steps.items()}
        # Historical broad purge and interrupted checkpoint replacement need their
        # separately reviewed recovery profiles; no generic metadata grant covers them.
        journal = ctx.out / '.checkpoint-in-progress.json'
        if journal.exists() or journal.is_symlink():
            raise AuthorityRefused('pending checkpoint restore needs its separately qualified recovery family')
        info = os.lstat(ctx.out)
        anchor = {'path': 'build/yorimichi', 'device': info.st_dev, 'inode': info.st_ino}
        self.paths = ['build/yorimichi/.state', 'build/yorimichi/logs', 'build/yorimichi/stamps',
                      'build/yorimichi/.checkpoint-in-progress.json']
        def claims(paths):
            return [{'path': name, 'canonical': name, 'anchor': anchor} for name in paths]
        # Subdivide the SAME complete claim union, not its observations. Each
        # root settles in one bounded message after ALL original finalization;
        # every actual attempt retains all four metadata members.
        self.metadata_scopes = dict(zip(
            (self.metadata, self.metadata + '.logs', self.metadata + '.stamps', self.metadata + '.journal'),
            ([path] for path in self.paths)))
        tasks = [{'id': name, 'replay': 'closed_replay', 'writes': claims(paths)}
                 for name, paths in self.metadata_scopes.items()]
        for name, paths in self.output_paths.items():
            tasks.append({'id': name, 'replay': 'closed_replay',
                          'writes': claims([path.relative_to(self.checkout).as_posix() for path in paths])})
        inputs = []
        for step in self.steps.values():
            for path in self.build.required_inputs(step):
                # Produced texture bytes are observed by the ORIGINAL fingerprint at
                # native dispatch, not frozen as absent cold raw-source inputs.
                if Path(path) not in self.generated_inputs:
                    inputs.extend(self.witness(Path(path).relative_to(self.checkout).as_posix()))
        inputs.extend(self.witness('games/yorimichi/game.toml'))
        inputs.extend(self.witness('uv.lock'))
        # Operational witnesses are unique paths, not another task fingerprint.
        inputs = list({item['path']: item for item in inputs}.values())
        frame = {'profile': 'named_assembly', 'topology': self.manifest['issuer_digest'],
                 'inputs': inputs, 'tasks': tasks}
        observation = {'project': self.request['game'], 'selector': self.request['wanted'],
                       'source_plan': self.manifest['issuer_digest'],
                       'request_digest': self.manifest['scheduler_request']['digest'],
                       'issuer': self.manifest['issuer_digest'], 'controller_source': self.manifest['source_digest'],
                       'roots': ['build/yorimichi'],
                       'sources': self.witness('games/yorimichi/legacy_qualification.py')}
        old = _prior_record(self.client)
        if old is not None:
            previous_frame = old.get('frame')
            scope = None if previous_frame is None else previous_frame['scope']
            allowed = {'control.hash-index.prepare', *self.metadata_scopes, *self.steps}
            if scope is not None and any(task['id'] not in allowed for task in scope['tasks']):
                raise AuthorityRefused('old epoch includes an unqualified game-family repair scope')
            same = all(old['binding'].get(key) == value for key, value in observation.items() if key != 'sources')
            if same and scope == frame:
                if not expanded:
                    self.client.request({'type': 'prepare_selection', 'observation': observation})
                settled = [item['task'] for item in old['frame']['settled']]
                if settled:
                    # Resume all actual members under new permission. Pending failed
                    # members remain pending; no settled credit grants another launch.
                    self.client.request({'type': 'requeue', 'members': settled})
            elif same and previous_frame is not None and not previous_frame['pending']:
                if not expanded:
                    self.client.request({'type': 'prepare_selection', 'observation': observation})
                self.client.request({'type': 'advance', 'observation': frame})
            else:
                if expanded:
                    raise AuthorityRefused('live expansion changed a scope with unfinished tasks; no Supersede or new permission')
                self.client.request({'type': 'supersede', 'observation': observation, 'initial_frame': frame})
        else:
            self.client.request({'type': 'prepare_selection', 'observation': observation})
            self.client.request({'type': 'advance', 'observation': frame})
        if expanded:
            # A same-frame replay retains all old attempts. Bind a fresh id to
            # this exact live protocol sequence; no counter/frame reset.
            sequence = self.client.sequence
            if type(sequence) is not int or sequence <= 0:
                raise AuthorityRefused('live preparation lacks its exact protocol sequence')
            self.attempt = self.preparation_attempt = 'prepare-' + self.nonce + '-' + str(sequence)
        self.client.request({'type': 'begin_attempt', 'attempt': {'id': self.attempt,
                             'members': [*self.metadata_scopes, *self.steps], 'execution': {'kind': 'in_process'}, 'guard': None}})
        self.begun = True

    def expanded(self, ctx, steps, wanted):
        from atelier import build_products
        self.build.check_declarations(steps)
        graph = build_products.Graph(steps)
        selected = graph.select(wanted)
        # Same authority/guards/channel; only the freshly qualified current frame
        # changes. No old settled credit grants newly discovered tasks permission.
        self.__init__(self.manifest, self.request, self.client, self.custody,
                      self.build, graph, steps, selected, self.files)
        self.before_prepare(ctx, steps, wanted, expanded=True)

    def writer(self, output):
        """Borrow only the host's same-OFD writer; never acquire/unlock another lock."""
        from contextlib import contextmanager
        import os
        import stat
        @contextmanager
        def borrowed():
            fd = self.custody['writer']
            info = os.fstat(fd)
            named = os.lstat(output / '.state/retention/writer.lock')
            if (not stat.S_ISREG(info.st_mode) or os.get_inheritable(fd)
                    or (info.st_dev, info.st_ino) != (named.st_dev, named.st_ino)):
                raise ValueError('host checkpoint writer does not match its current original path')
            yield
        return borrowed()

    def current_controller(self, step):
        if step.controller.request(self.checkout) != self.controllers.get(step.name):
            raise ValueError('selected controller changed within the original scheduling graph')
        # Every permission request was independently gated by fresh Rust Current.

    def before_task(self, ctx, step, *, done=None):
        from atelier.build_v2.legacy_client import AuthorityRefused
        if step is self.aggregate:
            if not set(self.texture_steps) <= set(self.completed):
                raise AuthorityRefused('texture aggregate reached before its complete successful product set')
            self.step, self.runtime = step, None
            self.attempt, self.returned = self.preparation_attempt, None
            self.launch_context = None
            return
        if self.steps.get(step.name) is not step:
            raise AuthorityRefused('next actual selected family is not yet qualified; completed tasks retained')
        self.step = step
        if done is not None:
            self.dones[step.name] = dict(done)
        if step.name in self.native_steps or step.name in self.data_steps or step.name in self.call_steps:
            if done is None:
                raise AuthorityRefused('native dispatch lacks original scheduler input observations')
            self.keys[step.name] = self.build.fingerprint(step, done, index=ctx.build_hash_index,
                                                        tool_cache=ctx.build_tool_cache)
        if step.name in self.single_native:
            from dataclasses import replace
            from legacy_treehouse_recolour_profile import qualify_treehouse_recolour
            actual = qualify_treehouse_recolour(replace(step), checkout=self.checkout,
                                                output_root=self.checkout / 'build/yorimichi')
            if actual != self.single_native[step.name]:
                raise AuthorityRefused('standalone native declaration changed before permission')
        if step.name in self.data_steps:
            from dataclasses import replace
            actual = self.python_qualifiers[step.name](replace(step), checkout=self.checkout,
                                                       output_root=self.checkout / 'build/yorimichi')
            if actual != self.data_steps[step.name][1]:
                raise AuthorityRefused('plain Python source/arguments/owned products changed before permission')
        self.step_key = self.keys[step.name]
        self.runtime = self.runtimes.get(step.name)
        self.native_launch = None
        token = self.hashlib.sha256(step.name.encode()).hexdigest()[:20]
        self.guard_relative = 'build/build-v2/legacy-host/' + self.nonce + '/guards/' + token
        self.guard_directory = self.checkout / self.guard_relative
        self.audit_root = self.guard_directory / 'audit'
        self.invocation = self.hashlib.sha256((self.nonce + ':' + step.name).encode()).hexdigest()[:32]
        self.attempt = self.preparation_attempt
        self.returned = None
        self.launch_context = None
        if step.name in self.call_steps:
            self.validate_call(step, step.commands[0])
            self.attempt = 'call-' + self.nonce + '-' + token + '-' + str(self.client.sequence)
            self.client.request({'type': 'begin_attempt', 'attempt': {
                'id': self.attempt, 'members': [*self.metadata_scopes, step.name],
                'execution': {'kind': 'in_process'}, 'guard': None}})

    def call_scope(self, ctx, step, command):
        self.validate_call(step, command)
        from atelier.atomic_files import managed_temporaries
        return managed_temporaries(ctx.out / '.state/batches' / self.attempt / 'atomic-tmp')

    def raw_native_members(self):
        """Private descriptor-only view for pure child-role revalidation.

        Original child objects/fields/unknown attributes remain intact. Only this
        issuer's exact already-checked runtime object is temporarily absent while
        the pure qualifier runs; it is restored even when qualification refuses.
        This view neither executes callbacks nor requests any task permission.
        """
        from contextlib import contextmanager
        from atelier.build_v2.legacy_client import AuthorityRefused
        from atelier.build_v2.legacy_native_action import captured_native_inputs
        @contextmanager
        def original():
            removed = []
            try:
                for name, member in self.native_steps.items():
                    expected = self.native_runtimes[name]
                    if vars(member).get('_captured_native_runtime') is not expected:
                        raise AuthorityRefused('original child runtime descriptor changed before pure revalidation')
                    captured_native_inputs(member)  # Private type/origin, not raw attribute trust.
                    del member._captured_native_runtime
                    removed.append((member, expected))
                yield
            finally:
                for member, expected in removed:
                    member._captured_native_runtime = expected
        return original()

    def validate_call(self, step, command):
        from dataclasses import fields, replace
        from legacy_treehouse_discovery_profile import qualify_treehouse_discovery
        from legacy_treehouse_assembly_profile import qualify_treehouse_assembly
        from atelier.build_v2.legacy_call import captured_call_inputs
        from atelier.build_v2.legacy_client import AuthorityRefused
        if (self.call_steps.get(step.name) is not step or command is not step.commands[0]
                or vars(step).get('_captured_call_runtime') is not self.call_runtimes[step.name]
                or set(vars(step)) != {field.name for field in fields(step) if field.init} | {'_captured_call_runtime'}):
            raise AuthorityRefused('in-process callback differs from its exact original role/runtime')
        captured_call_inputs(step)
        qualifier = qualify_treehouse_discovery if step is self.discovery else qualify_treehouse_assembly
        with self.raw_native_members():
            actual = qualifier(replace(step), checkout=self.checkout,
                               output_root=self.checkout / 'build/yorimichi')
        if actual != self.call_profiles[step.name]:
            raise AuthorityRefused('callback source, helper or original child closure changed before execution')

    def after_task(self, ctx, step, code, *, done=None):
        from atelier.build_v2.legacy_client import AuthorityRefused
        if (code is not None and not (step is getattr(self, 'discovery', None) and code == 76)) or self.returned not in (None, 0):
            raise AuthorityRefused('qualified task failed; original outputs/certificates remain fenced')
        if step is self.aggregate:
            if done is None:
                raise AuthorityRefused('aggregate lacks the original scheduler product observations')
            self.aggregate_done = dict(done)
            self.aggregate_key = self.build.fingerprint(step, done, index=ctx.build_hash_index,
                                                         tool_cache=ctx.build_tool_cache)
            self._check_aggregate(ctx)
            print('Managed texture aggregate observed: zero commands; original read identity/stamp', flush=True)
            return
        if done is not None:
            self.dones[step.name] = dict(done)
        self._check_certificate(ctx, step)
        self.completed[step.name] = self.attempt

    def _check_certificate(self, ctx, step):
        from atelier.build_plan import read_stamp
        from atelier import build_products
        index = ctx.build_hash_index
        key = self.build.fingerprint(step, self.dones.get(step.name, {}), index=index, tool_cache=ctx.build_tool_cache)
        stamp = read_stamp(ctx.stamps / (step.name + '.json'))
        if (key != self.keys[step.name] or stamp.get('fingerprint') != key
                or not self.build.outputs_present(step)
                or not build_products.valid_records(step, stamp.get('products', {}), hasher=index.digest)):
            raise ValueError('original texture completion is no longer current: ' + step.name)
        return key

    def _check_aggregate(self, ctx):
        if self.aggregate_done is None:
            return
        from atelier import build_products
        from atelier.build_plan import read_stamp
        # Reuse the ORIGINAL product inventory/identity and fingerprint encoders,
        # replacing observations from every actual producer with fresh facts.
        fresh = dict(self.aggregate_done)
        for step in self.texture_steps.values():
            build_products.feed_results(fresh, build_products.records(step, hasher=ctx.build_hash_index.digest))
        key = self.build.fingerprint(self.aggregate, fresh, index=ctx.build_hash_index,
                                     tool_cache=ctx.build_tool_cache)
        stamp = read_stamp(ctx.stamps / (self.aggregate.name + '.json'))
        if key != self.aggregate_key or stamp.get('fingerprint') != key:
            raise ValueError('original aggregate read identity/stamp changed before metadata settlement')

    def checkpoint_complete(self, ctx, invalid):
        self.final_invalid = invalid
        self.finalized = True

    def before_collection(self, ctx):
        from atelier.build_v2.legacy_client import AuthorityRefused
        raise AuthorityRefused('global retention collection needs its separately qualified finalization scope')

    def after_index(self, ctx):
        if getattr(self, 'finalized', False):
            self.after_checkpoint(ctx, self.final_invalid)
            self.finalized = False

    def after_checkpoint(self, ctx, invalid):
        if invalid:
            raise ValueError('original final output checkpoint invalidated texture certificates')
        # Original finalization and HashIndex.close precede ANY member settlement.
        # Validate the complete successful prefix first, then retain its exact products.
        keys = {name: self._check_certificate(ctx, self.steps[name]) for name in self.completed}
        self._check_aggregate(ctx)
        for name, attempt in self.completed.items():
            outputs = []
            for path in self.output_paths[name]:
                outputs.extend(self.witness(path.relative_to(self.checkout).as_posix()))
            self.client.request({'type': 'settle', 'observation': {'task': name, 'attempt': attempt,
                                 'inputs': keys[name], 'outputs': outputs}})
            print('Managed original game task settled: ' + name, flush=True)
        for task, paths in self.metadata_scopes.items():
            outputs = []
            for name in paths:
                outputs.extend(self.witness(name))
            self.client.request({'type': 'settle', 'observation': {'task': task,
                                 'attempt': self.preparation_attempt,
                                 'inputs': self.manifest['issuer_digest'], 'outputs': outputs}})
        print('Managed original scheduler metadata settled', flush=True)

    def runtime_roots(self):
        import sysconfig
        context = self.manifest['python_context']
        return sorted(set([*context['platform_roots'], context['purelib'], context['platlib'],
                           sysconfig.get_path('stdlib'), sysconfig.get_path('platstdlib')]))

    def audit_argv(self, specification):
        from atelier.build_v2.legacy_action import worker_argv
        return worker_argv(self.manifest, specification, self.files)

    def action_environment(self, extra):
        from atelier.build_source import environment
        actual = environment(extra)
        if self.launch_context is None:
            return actual
        if actual != self.base_environment:
            raise ValueError('audit scratch environment changed after launch preparation')
        return dict(self.launch_context.environment)

    def audit_directory(self):
        from contextlib import contextmanager
        from atelier.build_v2.legacy_client import authority_now_ns
        import os
        from atelier.harness.capacity_protocol import boot_id
        from atelier.harness.capacity_protocol import process_start
        @contextmanager
        def owned():
            from atelier.harness import capacity_runtime
            settings = capacity_runtime.read_configuration(capacity_runtime.DEFAULT_CONFIG)
            if settings.get('schema') != 2 or 'ATELIER_CAPACITY_CLIENT' in os.environ:
                raise ValueError('texture provider requires fresh automatic full-capacity mode')
            spec = self.audit_root / 'request.json'
            scratch = self.audit_root / 'scratch'
            extras = tuple((name, str(scratch / member)) for name, member in (
                ('HOME', 'home'), ('TMPDIR', 'tmp'), ('TMP', 'tmp'), ('TEMP', 'tmp'),
                ('XDG_CACHE_HOME', 'cache'), ('PYTHONPYCACHEPREFIX', 'bytecode')))
            extras += (('PYTHONDONTWRITEBYTECODE', '1'), ('ATELIER_ACTION_INPUTS', str(self.audit_root / 'action-inputs.json')))
            self.expected_argv = self.audit_argv(spec)
            from atelier.harness.safety.launch_ownership import prepare
            self.base_environment = self.action_environment(extras)
            self.launch_context = prepare(self.base_environment)
            self.expected_environment = dict(self.launch_context.environment)
            now = authority_now_ns()
            execution_ns = 120 * 1_000_000_000
            queue_ns = min(now + 1800 * 1_000_000_000,
                           self.manifest['work_deadline_ns'] - execution_ns)
            if queue_ns <= now:
                raise ValueError('texture guard queue/work does not fit the original authority deadline')
            self.queue_deadline_ns = queue_ns
            self.attempt = 'texture-' + self.nonce + '-' + self.hashlib.sha256(self.step.name.encode()).hexdigest()[:20]
            launch = {'scheduler': {'pid': os.getpid(), 'boot': boot_id(), 'started': str(process_start(os.getpid()))},
                      'program': self.expected_argv[0], 'args': self.expected_argv[1:],
                      'environment_digest': self.hashlib.sha256(__import__('json').dumps(self.expected_environment,
                                             sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                      'kind': 'job', 'threads': 1, 'memory_bytes': 10 * 1024**3,
                      'execution_ns': execution_ns, 'queue_deadline_ns': queue_ns}
            self.client.request({'type': 'begin_attempt', 'attempt': {'id': self.attempt,
                'members': [*self.metadata_scopes, self.step.name], 'execution': {'kind': 'guarded', 'directory': self.guard_relative,
                 'invocation': self.invocation, 'launch': launch}, 'guard': None}})
            self.audit_root.mkdir(parents=True, mode=0o700)
            yield self.audit_root
        return owned()

    def before_native_batch(self, ctx, session):
        """@cc [owner:fontanierh,label:correctness;safety] complete-original-native-batch-members
        Every actual candidate MUST be an original qualified Step before write_plan
        invalidates stamps. Complete member preparation/launch intents MUST precede
        effects. Member observations MUST follow original guard closure, verify_completed
        and applicable mesh finalization; final publication/index close MUST precede
        epoch settlement. Failed native attempts MUST NOT receive normal member credit.
        See test_build_batches shared Session ordering and retained runtime evidence.
        """
        from atelier.build_v2.legacy_client import AuthorityRefused
        from atelier.build_v2.legacy_native_launch import NativeBatchLaunch
        for step, key, _ in session.candidates:
            if self.native_steps.get(step.name) is not step:
                raise AuthorityRefused('original batch includes an unqualified native member')
            self.keys[step.name] = key
            self.dones[step.name] = dict(session.done)
        launch = NativeBatchLaunch(self, session, self.native_runtimes)
        # Explicit complete member scope BEFORE write_plan unlinks any stamp.
        self.client.request({'type': 'begin_attempt', 'attempt': {
            'id': 'native-prepare-' + self.nonce + '-' + session.nonce,
            'members': [*self.metadata_scopes, *launch.members],
            'execution': {'kind': 'in_process'}, 'guard': None}})
        self.native_launch = launch

    def native_batch_observed(self, ctx, session, completed, code):
        from atelier.build_v2.legacy_client import AuthorityRefused
        launch = self.native_launch
        if launch is None or launch.session is not session:
            raise AuthorityRefused('native batch result has no original shared launch binding')
        if self.returned != 0:
            # Preserve original completed stamps/facts, but never certify a member
            # under a failed native attempt in this named-assembly frame.
            self.native_partial = {name: self.keys[name] for name in completed}
            return
        for name in completed:
            if name not in launch.members:
                raise AuthorityRefused('original native completion has a foreign member')
            self.dones[name] = dict(session.done)
            self._check_certificate(ctx, self.native_steps[name])
            self.completed[name] = self.attempt

    def command_timeout(self):
        native = getattr(self, 'native_launch', None)
        return native.work_seconds if native is not None else 120.

    def prepare_native_command(self, ctx, step, command):
        from atelier.build_v2.legacy_client import AuthorityRefused
        native = getattr(self, 'native_launch', None)
        if native is None and step.name in self.single_native and self.native_steps.get(step.name) is step:
            from atelier.build_v2.legacy_native_launch import NativeSingleLaunch
            native = NativeSingleLaunch(self, ctx, step, command, self.native_runtimes[step.name])
            self.native_launch = native
        if native is None:
            raise AuthorityRefused('native command has no qualified original launch intent')
        return native.prepared(ctx, command)

    def guard_options(self, argv, environment, kind):
        from atelier.build_v2.legacy_client import authority_now_ns
        native = getattr(self, 'native_launch', None)
        if native is not None:
            return native.guard_options(argv, environment, kind)
        if list(argv) != self.expected_argv or environment != self.expected_environment or kind != 'job':
            raise ValueError('original audit command/environment differs from persisted launch intent')
        remaining = (self.queue_deadline_ns - authority_now_ns()) / 1e9
        if remaining <= 0:
            raise ValueError('persisted texture queue deadline expired before normal admission')
        return {'custody_fds': tuple(self.custody.values()), 'aggregate_tree': True,
                'launch_context': self.launch_context,
                'invocation_id': self.invocation, 'logical_folder': self.checkout / 'build/yorimichi/logs' / (self.step.name + '.guard'),
                'queue_seconds': remaining}

    def guard_returned(self, code):
        import json
        from atelier.build_v2.controller_client import _read_at
        from atelier.harness.capacity_protocol import boot_id
        # This attests the observed OUTER normal return of the fixed automatic
        # full-capacity call, not rc0 or a self-generated cleanup receipt.
        raw_process = _read_at(self.checkout, self.guard_relative + '/memory-health.json', 2 * 1024 * 1024)
        raw_tree = _read_at(self.checkout, self.guard_relative + '/memory-health-tree.json', 2 * 1024 * 1024)
        process, tree = json.loads(raw_process), json.loads(raw_tree)
        monitor = tree['monitor']
        observation = {'directory': self.guard_relative, 'invocation': self.invocation,
                       'child': {'pid': process['pid'], 'started': str(process['process_start']), 'boot': boot_id()},
                       'monitor': {'pid': monitor[0], 'started': str(monitor[1]), 'boot': boot_id()},
                       'controller_source': self.manifest['source_digest'], 'issuer_source': self.manifest['issuer_digest'],
                       'request_digest': self.manifest['scheduler_request']['digest'], 'returncode': code,
                       'process_digest': self.hashlib.sha256(raw_process).hexdigest(),
                       'tree_digest': self.hashlib.sha256(raw_tree).hexdigest()}
        self.client.request({'type': 'guard_returned', 'attempt': self.attempt, 'observation': observation})
        self.returned = code
