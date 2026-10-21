"""Native inputs retain geometry without duplicating unused LODs or giant strings."""
import ast
from copy import deepcopy
import io
import json
from pathlib import Path


def writer():
    script = Path(__file__).resolve().parents[1] / 'unreal/Scripts/build_foliage_system.py'
    function = next(node for node in ast.parse(script.read_text()).body
                    if isinstance(node, ast.FunctionDef) and node.name == 'write_representations')
    namespace = {'json': json}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(script), 'exec'), namespace)
    return namespace['write_representations']


def product():
    level = dict(vertices=[dict(p=point, n=[0., 0., 1.], c=[1., .5, 0., 1.],
                               uv=[.25, .75], uvs=[[.25, .75], [3., .375]])
                           for point in ([1.25, -2., 3.], [2., -2., 3.], [1.25, -1., 3.])],
                 faces=[dict(v=[0, 1, 2], s=4)])
    return dict(source='/Game/Test.Plant', screens=[1., .24, .07, .018],
                levels=[deepcopy(level) for _ in range(4)], shadow=deepcopy(level),
                patch=deepcopy(level), coverage=[{'canopy': [1., 2., 3.]}])


def test_native_documents_preserve_all_geometry_and_only_required_fields(tmp_path):
    prepared = product()
    before = deepcopy(prepared)
    path = tmp_path / 'mesh.json'
    shadow, patch = writer()(prepared, path)
    visual = json.loads(path.read_text())
    assert visual == {key: prepared[key] for key in ('source', 'screens', 'levels')}
    assert json.loads(shadow.read_text()) == dict(source=prepared['source'], shadow=prepared['shadow'])
    assert json.loads(patch.read_text()) == dict(source=prepared['source'], shadow=prepared['patch'])
    assert prepared == before


def test_large_documents_use_bounded_writes_instead_of_a_document_string():
    class Sink(io.StringIO):
        largest_write = 0

        def write(self, value):
            self.largest_write = max(self.largest_write, len(value))
            return super().write(value)

        def close(self):
            pass  # Inspect the completed in-memory test document after its context exits.

    class Destination:
        def __init__(self):
            self.handles = {}

        def with_suffix(self, suffix):
            return self.handles.setdefault(suffix, Destination())

        def open(self, *args, **kwargs):
            self.sink = Sink()
            return self.sink

    prepared = product()
    prepared['levels'][0]['vertices'] *= 1000
    destination = Destination()
    writer()(prepared, destination)
    assert len(destination.sink.getvalue()) > 100000
    assert destination.sink.largest_write < 1024
    assert json.loads(destination.sink.getvalue())['levels'] == prepared['levels']
