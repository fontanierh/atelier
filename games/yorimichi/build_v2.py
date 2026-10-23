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


def declaration():
    """@cc [owner:fontanierh,label:correctness] course-leaf-declared-closure
    Discovery MUST return a fresh declaration with the complete shared course validator,
    venue scene and checksum-bound geometry, without reading assets or writing state.
    The sole checkout output MUST own the existing runtime path. Source timestamps and
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
        }],
    }


def staged_inputs():
    """Worker-visible paths are explicit and bind through existing A3 ingredients."""
    return {slot: staged for slot, (_, staged) in COURSE_INPUTS.items()}
