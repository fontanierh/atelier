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
        }],
    }


def staged_inputs():
    """Worker-visible paths are explicit and bind through existing A3 ingredients."""
    return {slot: staged for slot, (_, staged) in COURSE_INPUTS.items()}


def targets():
    from atelier.build_v2.controller_recipe import ControllerTarget
    return {name: ControllerTarget(
        unit=name, project='yorimichi', declaration=declaration(),
        staged_inputs={COURSE_TARGET: staged_inputs(), RIM_TARGET: {'far_final': 'inputs/far-final.npz'}},
        content_slots={slot: False for slot in (*COURSE_INPUTS, 'far_final')},
        allowed_install_roots=('games/yorimichi/unreal/Content/Data',
                               'build/yorimichi/brinecove-data'))
        for name in (COURSE_TARGET, RIM_TARGET)}
