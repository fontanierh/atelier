"""Pure declarations for Yorimichi's migrated normal-build leaves.

Discovery reads no assets and creates no outputs or cache state. The Rust controller
owns validation, source freezing, keys, reuse, execution and checkout publication.
"""

COURSE_TARGET = 'data.stage.racing_courses'
COURSE_RUNTIME_PATH = 'racing/belmonte_courses.json'
COURSE_SCRIPT = 'games/yorimichi/world/racing/stage_courses.py'
COURSE_CODE = (
    COURSE_SCRIPT,
    'games/yorimichi/world/racing/courses.py',
    'games/yorimichi/world/regions/belmonte/__init__.py',
    'games/yorimichi/world/regions/belmonte/source.py',
    'games/yorimichi/world/regions/belmonte/query_surface.py',
    'games/yorimichi/world/regions/belmonte/terrain_palette.py',
    'platform/studio/atelier/__init__.py',
    'platform/studio/atelier/gltf.py',
)
COURSE_INPUTS = {
    'courses': ('games/yorimichi/world/racing/belmonte_courses.json', 'inputs/courses.json'),
    'venue': ('games/yorimichi/assets/belmonte/source.json', 'inputs/venue/source.json'),
    'surface': ('games/yorimichi/assets/belmonte/meshes/SM_BM_BHip_Course.glb',
                'inputs/venue/meshes/SM_BM_BHip_Course.glb'),
}

RIM_TARGET = 'world.brinecove.rim_data'
RIM_SCRIPT = 'games/yorimichi/world/regions/brinecove/stage_rim_v2.py'
RIM_CODE = (
    RIM_SCRIPT,
    'games/yorimichi/world/regions/brinecove/__init__.py',
    'games/yorimichi/world/regions/brinecove/rim_data.py',
    'games/yorimichi/world/regions/brinecove/boundary.py',
    'games/yorimichi/world/regions/brinecove/region.py',
    'games/yorimichi/world/regions/brinecove/rim_schema.py',
    'games/yorimichi/world/terrain_product.py',
    'platform/studio/atelier/__init__.py',
    'platform/studio/atelier/atomic_files.py',
    'platform/studio/atelier/export_manifest.py',
    'platform/studio/atelier/model_files.py',
)
# Temporary migration input: an independently copied and validated content file,
# not a FarHills result/receipt. The complete graph replaces it with a producer edge.
RIM_INPUT = 'build/v2-migration-inputs/yorimichi/far-final.npz'


CANOPY_NAME = "Tree_Canopy_Maple"
CANOPY_PLAN = "world.treehouse_trees.plan." + CANOPY_NAME
CANOPY_EXPORT = "world.treehouse_trees.export." + CANOPY_NAME
CANOPY_PLAN_SCRIPT = "games/yorimichi/world/regions/treehouse/stage_canopy_v2.py"
CANOPY_EXPORT_SCRIPT = "games/yorimichi/world/stage_mesh_export_v2.py"
CANOPY_PLAN_CODE = ('games/yorimichi/world/asset_mesh.py', 'games/yorimichi/world/material_specs.py', 'games/yorimichi/world/mesh_pieces.py', 'games/yorimichi/world/region_mesh_parts.py', 'games/yorimichi/world/region_plan_files.py', 'games/yorimichi/world/regions/treehouse/__init__.py', 'games/yorimichi/world/regions/treehouse/atomic_parameters.py', 'games/yorimichi/world/regions/treehouse/canopy.py', 'games/yorimichi/world/regions/treehouse/stage_canopy_v2.py', 'games/yorimichi/world/yori.py', 'platform/studio/atelier/__init__.py', 'platform/studio/atelier/atomic_files.py', 'platform/studio/atelier/blender/__init__.py', 'platform/studio/atelier/blender/fbx.py', 'platform/studio/atelier/build_v2/__init__.py', 'platform/studio/atelier/build_v2/blender_geometry.py', 'platform/studio/atelier/build_v2/blender_ops.py', 'platform/studio/atelier/build_v2/blender_validate.py', 'platform/studio/atelier/export_manifest.py', 'platform/studio/atelier/mesh_cells.py', 'platform/studio/atelier/mesh_collision.py', 'platform/studio/atelier/mesh_ir.py', 'platform/studio/atelier/mesh_materials.py', 'platform/studio/atelier/mesh_partition.py', 'platform/studio/atelier/model_files.py', 'platform/studio/atelier/paths.py')
CANOPY_EXPORT_CODE = ('games/yorimichi/world/stage_mesh_export_v2.py', 'platform/studio/atelier/__init__.py', 'platform/studio/atelier/atomic_files.py', 'platform/studio/atelier/blender/__init__.py', 'platform/studio/atelier/blender/fbx.py', 'platform/studio/atelier/build_v2/__init__.py', 'platform/studio/atelier/build_v2/blender_geometry.py', 'platform/studio/atelier/build_v2/blender_ops.py', 'platform/studio/atelier/build_v2/blender_validate.py', 'platform/studio/atelier/export_manifest.py', 'platform/studio/atelier/mesh_collision.py', 'platform/studio/atelier/mesh_ir.py', 'platform/studio/atelier/mesh_materials.py', 'platform/studio/atelier/model_files.py')
CANOPY_INPUTS = {
    'parameters': ('games/yorimichi/assets/treehouse/export-parameters/Tree_Canopy_Maple.json', 'inputs/parameters/Tree_Canopy_Maple.json'),
    'bark': ('build/v2-migration-inputs/yorimichi/textures/T_bark.jpg', 'inputs/textures/T_bark.jpg'),
    'leaf_maple': ('build/v2-migration-inputs/yorimichi/textures/T_leaf_maple.png', 'inputs/textures/T_leaf_maple.png'),
}


def canopy_units():
    limits = dict(max_pieces=16, max_manifest_bytes=1024 * 1024,
                  max_member_bytes=128 * 1024 * 1024, max_total_bytes=512 * 1024 * 1024)
    group = dict(id='geometry', root='geometry', root_param='output_root', manifest='plan.json',
                 adapter_version='d2.mesh-plan/1', parent=CANOPY_NAME, encoding='mesh_ir',
                 **{'class': 'GeometryPayload'}, logical_namespace='/Internal/Treehouse/' + CANOPY_NAME,
                 **limits)
    return [{
        'id': CANOPY_PLAN, 'op': {'kind': 'blender_plan', 'version': '1'},
        'script': CANOPY_PLAN_SCRIPT, 'code': list(CANOPY_PLAN_CODE),
        'params': {'output_root': 'output/geometry', 'parent': CANOPY_NAME, 'plan_limits': limits},
        'inputs': [{'role': 'content', 'name': slot, 'source': {'kind': 'file', 'path': source},
                    'whole': 'The original canopy constructor reads these exact parameters or atlas pixels.'}
                   for slot, (source, _) in CANOPY_INPUTS.items()],
        'outputs': [], 'output_groups': [group],
    }, {
        'id': CANOPY_EXPORT, 'op': {'kind': 'blender_export_piece', 'version': '1'},
        'script': CANOPY_EXPORT_SCRIPT, 'code': list(CANOPY_EXPORT_CODE),
        'params': {'format': 'fbx', 'payload_member': CANOPY_NAME + '.npz',
                   'payload_encoding': 'mesh_ir', 'payload_role': 'geometry',
                   'options': {'path_mode': 'RELATIVE'}},
        'inputs': [{'role': 'content', 'name': 'payload', 'source': {'kind': 'group_member',
                    'unit': CANOPY_PLAN, 'group': 'geometry', 'piece': CANOPY_NAME}}],
        'outputs': [{'id': 'asset', 'logical_path': '/Sources/Treehouse/' + CANOPY_NAME,
                     'class': 'StaticMeshSource', 'destination': 'store', 'files': [
            {'path': CANOPY_NAME + '.fbx'},
            {'path': 'export.json'}]}],
    }]


def declaration():
    """@cc [owner:fontanierh,label:correctness] course-leaf-declared-closure
    Discovery MUST return fresh explicit declarations with the complete shared course
    validator and coastal projection closures, without reading assets or writing state.
    Checkout outputs MUST own their existing runtime paths. Source timestamps and
    installed Python/NumPy identities MUST NOT be semantic parameters. See
    test_course_declaration_is_pure_complete_and_independent in test_racing_courses.py.
    """
    return {
        'schema_version': 2,
        'cache_version': 'v2-1',
        'units': [{
            'id': COURSE_TARGET,
            'op': {'kind': 'py_data', 'version': '1'},
            'script': COURSE_SCRIPT,
            'code': list(COURSE_CODE),
            'params': {},
            'inputs': [
                {'role': 'content', 'name': slot, 'source': {'kind': 'file', 'path': source},
                 'whole': 'Complete bytes are copied or checksum-validated by the course preflight.'}
                for slot, (source, _) in COURSE_INPUTS.items()
            ],
            'outputs': [{
                'id': 'courses',
                'logical_path': '/Game/Data/racing/belmonte_courses.json',
                'class': 'JsonData',
                'destination': 'checkout',
                'files': [{'path': 'belmonte_courses.json',
                           'install_path': 'games/yorimichi/unreal/Content/Data/' + COURSE_RUNTIME_PATH}],
            }],
        }, {
            'id': RIM_TARGET,
            'op': {'kind': 'py_data', 'version': '1'},
            'script': RIM_SCRIPT,
            'code': list(RIM_CODE),
            'params': {},
            'inputs': [{'role': 'content', 'name': 'far_final',
                        'source': {'kind': 'file', 'path': RIM_INPUT},
                        'whole': 'The original projection validates and consumes the complete terrain product.'}],
            'outputs': [{
                'id': 'rim', 'logical_path': '/Game/Data/brinecove/final-rim.json',
                'class': 'JsonData', 'destination': 'checkout',
                'files': [{'path': 'final-rim.json',
                           'install_path': 'build/yorimichi/brinecove-data/final-rim.json'}],
            }],
        }, *canopy_units()],
    }


def staged_inputs():
    """Worker-visible paths are explicit and bind through existing A3 ingredients."""
    return {slot: staged for slot, (_, staged) in COURSE_INPUTS.items()}


def targets():
    from atelier.build_v2.controller_recipe import ControllerTarget
    return {name: ControllerTarget(
        unit=name, project='yorimichi', declaration=declaration(),
        staged_inputs={COURSE_TARGET: staged_inputs(), RIM_TARGET: {'far_final': 'inputs/far-final.npz'},
                       CANOPY_PLAN: {slot: staged for slot, (_, staged) in CANOPY_INPUTS.items()},
                       CANOPY_EXPORT: {'payload': 'inputs/payload'}},
        content_slots={slot: False for slot in (*COURSE_INPUTS, 'far_final', *CANOPY_INPUTS)},
        allowed_install_roots=('games/yorimichi/unreal/Content/Data',
                               'build/yorimichi/brinecove-data', 'build/yorimichi/treehouse/trees'))
        for name in (COURSE_TARGET, RIM_TARGET, CANOPY_PLAN, CANOPY_EXPORT)}


def compile_target(name):
    """Compile the actual authored closure into v2 declarations, never run the old build loop."""
    from atelier import paths
    from atelier.build_v2.recipe_compiler import compile_game, compile_source_prerequisites
    if name == 'world.source-prerequisites':
        return compile_source_prerequisites('yorimichi', checkout=paths.REPO, build_root=paths.build_root())
    return compile_game('yorimichi', checkout=paths.REPO, build_root=paths.build_root(), targets=(name,))
