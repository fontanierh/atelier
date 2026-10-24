"""Yorimichi's initial managed declaration profile; tasks remain unsupported.

Only the existing recipe's discovery is entered. The named files below are code
providers, not a certificate that every data.stage prerequisite can execute/repair.
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
    return selected


def run(*, manifest, request, client, custody):
    """Discover read-only, then hold without a new epoch or task/control permission.

    No completion/Finish is issued: selected course ordering, mutation profiles, batch and
    replan/final Graph/repair are not yet implemented. An old epoch is not superseded here.
    """
    from atelier.build_v2.legacy_client import AuthorityRefused
    if request['game'] != 'yorimichi' or set(custody) != {'build', 'content', 'writer'}:
        raise AuthorityRefused('unsupported managed declaration profile')
    if client.record_digest is not None:
        raise AuthorityRefused('existing selection requires qualified ordinary repair')
    checkout = Path(manifest['checkout'])
    output = checkout / 'build/yorimichi'
    if Path(manifest['output']) != output:
        raise AuthorityRefused('discovery supports only the anchored default project output')
    # The host already created the exact output root and writer. Repeating that
    # mkdir is not a genuine mutating task, and cannot justify a whole-output claim.
    # No Prepare/Advance/BeginAttempt or settled/replay credit is fabricated.
    selected = discover(manifest, request)
    print(f'Managed captured recipe discovery: {len(selected)} selected declarations; '
          'HELD Unsupported before Context/task preparation', flush=True)
    raise AuthorityRefused('selected task/control preparation and course obligations remain unsupported')
