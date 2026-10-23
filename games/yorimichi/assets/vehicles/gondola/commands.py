"""Lossless primitive-command boundary between source plans and selected geometry.

Recording evaluates authored dimensions and frames without running a mesh primitive.
Replay invokes only the selected mesh's original primitive calls, in original order.
"""
from contextlib import contextmanager
import math
import sys

CONTEXTS = frozenset(('at', 'mirrored', 'frame', 'wall', 'tagged', 'grained'))
PRIMITIVES = frozenset(('part', 'box', 'prism', 'ring_prism', 'loft', 'band',
                        'beam', 'tube', 'lathe', 'cylinder', 'sphere', 'cone', 'rock'))


def data(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value): raise ValueError('Nonfinite Gondola source command')
        return value
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value): raise ValueError('Invalid command mapping')
        return {key: data(item) for key, item in value.items()}
    if hasattr(value, '__iter__') or (hasattr(value, '__len__') and hasattr(value, '__getitem__')):
        return [data(item) for item in value]
    raise ValueError('Unsupported Gondola command argument: ' + type(value).__name__)


class Recorder:
    """@cc [owner:fontanierh,label:correctness;performance] gondola-source-commands
    Source recording MUST NOT construct any mesh geometry. Every primitive and nested
    frame/tag/grain call MUST retain its exact arguments and order. Unknown operations,
    nonfinite values and unbalanced contexts MUST refuse. Replay MUST construct only
    the explicitly selected command stream using the unchanged authored primitives.
    """
    def __init__(self, name):
        self.name = name
        self.commands = []
        self.depth = 0

    def __getattr__(self, name):
        if name in CONTEXTS:
            @contextmanager
            def context(*args, **kwargs):
                self.commands.append(['enter', name, data(args), data(kwargs)])
                self.depth += 1
                try: yield
                finally:
                    self.depth -= 1
                    self.commands.append(['exit', name])
            return context
        if name in PRIMITIVES:
            def primitive(*args, **kwargs):
                args, kwargs = freeze_prism(name, args, kwargs)
                frame = sys._getframe(1)
                origin = frame.f_code.co_filename.rsplit('/', 1)[-1] + ':' + str(frame.f_lineno)
                self.commands.append(['primitive', name, data(args), data(kwargs), origin])
            return primitive
        raise AttributeError('Unsupported Gondola source operation: ' + name)


def replay(value, mesh_type):
    if value.get('schema') != 1 or not isinstance(value.get('asset'), str) or not value.get('commands'):
        raise ValueError('Incomplete selected Gondola commands')
    commands = data(value['commands'])
    depth = []
    # Validate the full stream before the first primitive mutates geometry.
    for row in commands:
        if not isinstance(row, list) or not row: raise ValueError('Invalid Gondola command')
        if (row[0] == 'enter' and len(row) == 4 and row[1] in CONTEXTS
                and isinstance(row[2], list) and isinstance(row[3], dict)):
            depth.append(row[1])
        elif row[0] == 'exit' and len(row) == 2 and depth and depth.pop() == row[1]:
            pass
        elif (row[0] == 'primitive' and len(row) == 5 and row[1] in PRIMITIVES
                and isinstance(row[2], list) and isinstance(row[3], dict) and isinstance(row[4], str)):
            pass
        else: raise ValueError('Invalid or unbalanced Gondola command')
    if depth: raise ValueError('Unclosed Gondola command context')
    mesh = mesh_type(value['asset'])
    managers = []
    try:
        for row in commands:
            if row[0] == 'enter':
                manager = getattr(mesh, row[1])(*row[2], **row[3])
                manager.__enter__(); managers.append(manager)
            elif row[0] == 'exit':
                managers.pop().__exit__(None, None, None)
            else:
                start = len(mesh.parts)
                args = [thaw(value) for value in row[2]]
                kwargs = {key: thaw(value) for key, value in row[3].items()}
                getattr(mesh, row[1])(*args, **kwargs)
                mesh.origins[start:] = [row[4]] * (len(mesh.parts) - start)
    finally:
        while managers: managers.pop().__exit__(None, None, None)
    return mesh


def freeze_prism(name, args, kwargs):
    if name != 'prism' or not any(callable(value) for value in (*args, *kwargs.values())):
        return args, kwargs
    # The source's callable boardwalk heights are exact finite spatial queries.
    # Capture every point the unchanged primitive will evaluate, never fit a plane.
    import solid
    args, kwargs = list(args), dict(kwargs)
    points = [tuple(point) for point in args[0]]
    if kwargs.get('step'): points = solid.resample(points, kwargs['step'])
    samples = list(points)
    if kwargs.get('bevel', 0) > 0: samples.extend(solid.offset_loop(points, -kwargs['bevel']))
    for index, key in ((1, 'z0'), (2, 'z1')):
        value = args[index] if len(args) > index else kwargs[key]
        if callable(value):
            frozen = dict(height_samples=[[x, y, value(x, y)] for x, y in samples])
            if len(args) > index: args[index] = frozen
            else: kwargs[key] = frozen
    return args, kwargs


def thaw(value):
    if not isinstance(value, dict) or set(value) != {'height_samples'}: return value
    samples = {(x, y): z for x, y, z in value['height_samples']}
    def height(x, y):
        if (x, y) not in samples: raise ValueError('Gondola primitive queried an unpublished height')
        return samples[x, y]
    return height
