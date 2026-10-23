"""Select one plain railway constructor and publish its complete pre-export mesh data.

Inventory discovery evaluates the original placement/query arithmetic, but no mesh
constructor. A selected data action then evaluates just its requested constructor;
Blender and bounded exports consume only that action's published corner source.
"""
import argparse
import ast
import json
from dataclasses import dataclass
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json
from atelier.export_manifest import name, real_directory
from train import track as T


@dataclass
class Request:
    builder: object
    arguments: tuple
    item: int | None = None

    def evaluate(self):
        args = tuple(value.evaluate() if isinstance(value, Request) else value for value in self.arguments)
        result = self.builder(*args)
        return result if self.item is None else result[self.item]


def encode_argument(value):
    if isinstance(value, Request):
        return dict(kind='request', module=value.builder.__module__, function=value.builder.__name__,
                    arguments=[encode_argument(arg) for arg in value.arguments], item=value.item)
    if isinstance(value, T.Line): return dict(kind='line')
    from train.station_site import Site
    if isinstance(value, Site):
        return dict(kind='site', fields={key: encode_argument(item) for key, item in vars(value).items()})
    if isinstance(value, np.ndarray):
        return dict(kind='array', dtype=value.dtype.str, shape=list(value.shape), values=value.tolist())
    if isinstance(value, np.generic): return value.item()
    if value is None or type(value) in (str, int, float, bool): return value
    if isinstance(value, (tuple, list)):
        return dict(kind='tuple' if isinstance(value, tuple) else 'list', values=[encode_argument(item) for item in value])
    raise ValueError('Unsupported complete railway constructor argument: ' + type(value).__name__)


def decode_argument(value, line_factory):
    if not isinstance(value, dict):
        if value is None or type(value) in (str, int, float, bool): return value
        raise ValueError('Invalid railway scalar argument')
    kind = value.get('kind')
    if kind == 'line': return line_factory()
    if kind == 'array':
        result = np.asarray(value['values'], dtype=value['dtype'])
        if list(result.shape) != value['shape'] or result.dtype.kind not in 'fiu' or not np.isfinite(result).all():
            raise ValueError('Invalid exact railway argument array')
        return result
    if kind in ('tuple', 'list'):
        result = [decode_argument(item, line_factory) for item in value['values']]
        return tuple(result) if kind == 'tuple' else result
    if kind == 'site':
        from train.station_site import Site
        if set(value['fields']) != {'origin', 't', 'n', 'rail', 'heading'}: raise ValueError('Incomplete station frame')
        site = object.__new__(Site)
        vars(site).update({key: decode_argument(item, line_factory) for key, item in value['fields'].items()})
        return site
    if kind == 'request':
        import importlib
        allowed = {
            'train.track': {'chunk_mesh', 'loop_mesh', 'lining_mesh', 'portal_mesh', 'bank_mesh', 'lamp_mesh',
                            'viaduct_mesh', 'sleeper_mesh', 'buffer_stop_mesh', 'stop_board_mesh', 'turnout_mesh', 'marker_mesh'},
            'train.station': {'to_world', 'headhouse', 'sheds', 'coaches', 'forecourt'},
            'train.overbridge': {'overbridge'},
        }
        if value['module'] not in allowed or value['function'] not in allowed[value['module']]:
            raise ValueError('Foreign railway constructor module/function')
        module = importlib.import_module(value['module'])
        function = value['function']
        if not isinstance(function, str) or function.startswith('_') or not function.isidentifier():
            raise ValueError('Foreign railway constructor name')
        builder = getattr(module, function)
        return Request(builder, tuple(decode_argument(arg, line_factory) for arg in value['arguments']), value['item'])
    raise ValueError('Unsupported railway argument kind')


def descriptor(asset, level, value):
    from train.track_projection import descriptor as project_descriptor
    return project_descriptor(asset, level, value)


def from_descriptor(value, *, line_factory=None):
    from train.construct_track import construct
    return construct(value, line_factory=line_factory)


def requests(line=None):
    """@cc [owner:fontanierh,label:correctness;performance] railway-query-before-selected-construction
    Inventory discovery MUST execute original placement arithmetic without constructing
    any mesh. Each selected request MUST call only its own original constructor closure;
    nested coordinate conversion is retained. The overbridge's origin and chainage MUST
    come from its original bridge query, not an exported mesh or guessed frame.
    """
    def defer(builder, *args):
        request = Request(builder, args)
        if builder.__module__ == 'train.overbridge' and builder.__name__ == 'overbridge':
            from train.overbridge import bridge
            _, origin, chainage = bridge(args[0])
            return Request(builder, args, 0), origin, chainage
        return request
    meshes, doc = T.layout(line, make=defer)
    if not meshes or any(not isinstance(value, Request) for rows in meshes.values() for value in rows):
        raise ValueError('Track layout escaped explicit constructor discovery')
    return meshes, doc


def inventory(line=None):
    meshes, doc = requests(line)
    doc['mesh_order'] = list(meshes)
    doc['meshes'] = {key: dict(levels=len(rows), requests=[encode_argument(row) for row in rows])
                     for key, rows in meshes.items()}
    return doc


def selected(asset, level, line=None):
    name(asset)
    meshes, _ = requests(line)
    if asset not in meshes or type(level) is not int or not 0 <= level < len(meshes[asset]):
        raise ValueError('Unknown selected railway mesh/LOD')
    return packet(asset, level, meshes[asset][level].evaluate())


def packet(asset, level, mesh):
    if not isinstance(mesh, T.Mesh) or not mesh.faces or len(mesh.faces) != len(mesh.mats):
        raise ValueError('Incomplete original railway constructor output')
    slots = list(dict.fromkeys(mesh.mats))
    # Keep the original conversion function verbatim; the planner never imports
    # track_build or reaches another source/route/constructor from this payload.
    factory = Path(__file__).with_name('track_build.py').read_text()
    functions = {node.name: node for node in ast.parse(factory).body if isinstance(node, ast.FunctionDef)}
    return dict(schema=1, asset=f'{asset}_LOD{level}', logical=asset, level=level,
                vertices=mesh.verts, faces=mesh.faces, materials=mesh.mats,
                palette={key: T.MATERIALS[key] for key in slots},
                to_object=ast.get_source_segment(factory, functions['to_object']),
                material_factory=ast.get_source_segment(factory, functions['materials']),
                export_glb=ast.get_source_segment(factory, functions['export_glb']), triangles=mesh.triangles)


def read(path, asset=None):
    path = Path(path); real_directory(path.parent)
    if path.is_symlink() or not path.is_file(): raise ValueError('Railway data must be a regular file')
    value = json.loads(path.read_text())
    if value.get('schema') != 1 or (asset is not None and value.get('asset') != asset):
        raise ValueError('Foreign railway constructor data')
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset')
    parser.add_argument('--level', type=int)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--inventory', type=Path)
    parser.add_argument('--descriptor', type=Path)
    args = parser.parse_args(argv)
    if (args.asset is None) != (args.level is None): raise ValueError('Select both asset and authored LOD')
    if args.inventory and args.descriptor: raise ValueError('Choose one railway source stage')
    if args.inventory:
        value = descriptor(args.asset, args.level, read(args.inventory))
    elif args.descriptor:
        value = from_descriptor(read(args.descriptor, f'{args.asset}_LOD{args.level}'))
    elif args.asset is None:
        value = inventory(); value['schema'] = 1
    else:
        raise ValueError('Normal selected construction requires its explicit descriptor')
    atomic_json(args.output, value)
    print('RAILWAY SOURCE DATA COMPLETE', args.asset or 'inventory', flush=True)


if __name__ == '__main__': main()
