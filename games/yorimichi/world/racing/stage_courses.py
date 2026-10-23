"""Exact-byte racing data body for the normal build-v2 course leaf.

The controller stages the whole declared venue scene and its checksum-bound GLB beside
each other. This body uses the existing course preflight, including actual surface support;
JsonData validation alone is not the game-specific validity proof.
"""
import importlib.util
from pathlib import Path
import sys


# The declared code closure is staged at these project-relative names. Only the
# private job copy is visible here; the worker's finder still checks each import.
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'platform/studio'))
_spec = importlib.util.spec_from_file_location('racing_courses', Path(__file__).with_name('courses.py'))
courses = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(courses)


def run(context):
    """@cc [owner:fontanierh,label:correctness] racing-course-exact-copy
    The course leaf MUST run the complete shared course preflight before requesting any
    output path, then emit exactly the validated input bytes. It MUST NOT reserialize JSON
    or promise ambient source timestamps. See test_course_leaf_preserves_original_bytes
    and test_invalid_course_leaf_never_requests_output in test_racing_courses.py.
    """
    raw = context.input('courses').read_bytes()
    scene = context.input('venue')
    if courses.venue(scene)[2] != context.input('surface'):
        raise ValueError('Racing scene geometry must match the declared surface slot')
    courses.load_bytes(raw, scene)
    context.output('belmonte_courses.json').write_bytes(raw)
