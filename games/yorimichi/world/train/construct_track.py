"""Execute one published railway source declaration closure, without layout discovery."""
import argparse
import importlib
import json
from pathlib import Path
import sys
from types import ModuleType

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json
from atelier.export_manifest import real_directory


def modules(projection):
    allowed = {'train.track', 'train.station', 'train.station_site', 'train.overbridge'}
    if not projection or set(projection) - allowed: raise ValueError('Foreign railway source projection')
    result = {key: ModuleType('_selected_' + key.replace('.', '_')) for key in projection}
    for module in result.values(): sys.modules[module.__name__] = module
    pending = set(result)
    def populate(key):
        if key not in pending: return
        pending.remove(key)
        module = result[key]
        for alias, full in projection[key]['bindings'].items():
            if full in result:
                populate(full); value = result[full]
            else:
                try: value = importlib.import_module(full)
                except ModuleNotFoundError as error:
                    parent, _, member = full.rpartition('.')
                    if not parent or error.name != full: raise
                    value = getattr(importlib.import_module(parent), member)
            vars(module)[alias] = value
        for declaration in projection[key]['declarations']:
            exec(compile(declaration, '<published railway declaration>', 'exec'), vars(module))
    for key in result: populate(key)
    return result


def construct(value, *, line_factory=None):
    if value.get('schema') != 1 or value.get('asset') != f"{value.get('logical')}_LOD{value.get('level')}":
        raise ValueError('Foreign selected railway request')
    projected = modules(value['code'])
    allowed = {
        'train.track': {'chunk_mesh', 'loop_mesh', 'lining_mesh', 'portal_mesh', 'bank_mesh', 'lamp_mesh',
                        'viaduct_mesh', 'sleeper_mesh', 'buffer_stop_mesh', 'stop_board_mesh', 'turnout_mesh', 'marker_mesh'},
        'train.station': {'to_world', 'headhouse', 'sheds', 'coaches', 'forecourt'},
        'train.overbridge': {'overbridge'},
    }
    def decode(arg):
        if not isinstance(arg, dict): return arg
        kind = arg['kind']
        if kind == 'line': return line_factory() if line_factory else projected['train.track'].Line()
        if kind == 'site':
            if set(arg['fields']) != {'origin', 't', 'n', 'rail', 'heading'}: raise ValueError('Incomplete station frame')
            site = object.__new__(projected['train.station_site'].Site)
            vars(site).update({key: decode(item) for key, item in arg['fields'].items()}); return site
        if kind == 'array':
            data = np.asarray(arg['values'], dtype=arg['dtype'])
            if list(data.shape) != arg['shape'] or data.dtype.kind not in 'fiu' or not np.isfinite(data).all():
                raise ValueError('Invalid exact railway argument array')
            return data
        if kind in ('tuple', 'list'):
            data = [decode(item) for item in arg['values']]; return tuple(data) if kind == 'tuple' else data
        if kind == 'request':
            if arg['module'] not in allowed or arg['function'] not in allowed[arg['module']]:
                raise ValueError('Foreign railway constructor module/function')
            data = getattr(projected[arg['module']], arg['function'])(*[decode(item) for item in arg['arguments']])
            return data if arg['item'] is None else data[arg['item']]
        raise ValueError('Unsupported railway argument kind')
    mesh = decode(value['request'])
    if not mesh.faces or len(mesh.faces) != len(mesh.mats): raise ValueError('Incomplete railway constructor output')
    return dict(schema=1, asset=value['asset'], logical=value['logical'], level=value['level'],
        vertices=mesh.verts, faces=mesh.faces, materials=mesh.mats,
        palette={key: value['palette'][key] for key in dict.fromkeys(mesh.mats)},
        **value['factory'], triangles=mesh.triangles)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset', required=True); parser.add_argument('--level', type=int, required=True)
    parser.add_argument('--descriptor', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); real_directory(args.descriptor.parent)
    if args.descriptor.is_symlink() or not args.descriptor.is_file(): raise ValueError('Linked railway request')
    value = json.loads(args.descriptor.read_text())
    if value['asset'] != f'{args.asset}_LOD{args.level}': raise ValueError('Foreign railway request identity')
    atomic_json(args.output, construct(value))
    print('RAILWAY SELECTED SOURCE COMPLETE', value['asset'], flush=True)


if __name__ == '__main__': main()
