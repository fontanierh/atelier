"""Execute one selected terminal program against explicit original primitive/query data."""
import math
from types import SimpleNamespace


def kit(primitives, source):
    if primitives.get('schema') != 1 or primitives.get('asset') != 'primitives':
        raise ValueError('Foreign terminal shared construction data')
    ferry = dict(__file__=__file__, __name__='selected_ferry_shared_primitives')
    exec(compile(primitives['ferry'], '<ferry shared primitives>', 'exec'), ferry)
    ferry.setdefault('MATERIALS', {})
    namespace = dict(F=SimpleNamespace(**ferry), SILL=source.get('sill'), math=math,
        __file__=__file__, __name__='selected_terminal_shared_primitives')
    exec(compile(primitives['terminal'], '<terminal shared primitives>', 'exec'), namespace)
    if 'MATERIALS' in namespace: namespace['F'].MATERIALS.update(namespace['MATERIALS'])
    pending = iter(source.get('ground', ())); consumed = []
    def ground(world, *rectangle):
        if world != source.get('owner'): raise ValueError('Foreign terminal ground owner')
        row = next(pending, None)
        if row is None or row['rectangle'] != list(rectangle):
            raise ValueError('Terminal constructor made an undeclared ground query')
        consumed.append(row)
        return row['height']
    namespace['ground_under'] = ground
    namespace['FS'] = SimpleNamespace(FENDER=source.get('fender'), load_world=lambda owner: owner if owner == source.get('owner')
        else (_ for _ in ()).throw(ValueError('Foreign terminal ground owner')))
    result = SimpleNamespace(**namespace)
    result._globals = namespace
    def complete():
        if len(consumed) != len(source.get('ground', ())):
            raise ValueError('Terminal constructor did not consume its complete selected query set')
    return result, complete


def construct(source, primitives):
    if (source.get('schema') != 1 or not isinstance(source.get('asset'), str)
            or not source['asset'].startswith(('FT_HD_', 'FT_BC_'))):
        raise ValueError('Foreign terminal constructor data')
    context, complete = kit(primitives, source)
    namespace = dict(math=math)
    exec(compile(source['program'], '<selected terminal constructor>', 'exec'), namespace)
    mesh, metadata = namespace[source['constructor']](context, source['parameters'])
    complete()
    if mesh.name != source['asset']: raise ValueError('Terminal constructor returned another mesh owner')
    return context, mesh, metadata
