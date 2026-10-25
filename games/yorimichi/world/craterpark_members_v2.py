"""Select actual CraterPark source packets and restyled pixels for keyed FileSet children."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
from types import SimpleNamespace

NAME = re.compile(r'[A-Za-z][A-Za-z0-9_]*\Z')


def read_json(path):
    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise ValueError('Duplicate CraterPark source field')
            result[key] = value
        return result
    return json.loads(Path(path).read_bytes(), object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite CraterPark source')))


def _file(root, member):
    path = Path(root) / member
    if (not isinstance(member, str) or Path(member).is_absolute() or '..' in Path(member).parts
            or path.resolve() != path or path.is_symlink() or not path.is_file()):
        raise ValueError('CraterPark source member is not an exact regular file')
    return path


def _root(source, scratch):
    from atelier.build_v2.recipe_job import inventory, unpack_root
    source = Path(source)
    if source.is_dir() and not source.is_symlink():
        inventory(source)
        return source
    if source.is_symlink() or not source.is_file():
        raise ValueError('Expected a declared CraterPark ROOT archive')
    unpack_root(source, scratch)
    if not scratch.is_dir():
        raise ValueError('CraterPark source ROOT must be a directory')
    return scratch


def project(source=None, output=None, kind=None):
    """Validate the whole frozen source before emitting one declared finite FileSet role."""
    import numpy as np
    output = Path(output)
    if kind not in ('render', 'collision', 'seed', 'textures') or output.exists():
        raise ValueError('Unexpected CraterPark projection role or existing output')
    output.mkdir(parents=True)
    scratch = output / '.source'
    try:
        root = _root(source, scratch)
        chosen = {}
        if kind == 'textures':
            report = read_json(root / 'textures.json')
            entries = list(report['textures'].values()) + list(report.get('world_aligned', {}).values())
            for entry in entries:
                path = _file(root, entry['png'])
                piece = path.stem
                if (path.suffix != '.png' or not NAME.fullmatch(piece)
                        or hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']):
                    raise ValueError('CraterPark restyle pixels differ from their receipt')
                if piece in chosen and chosen[piece] != path:
                    raise ValueError('Aliased CraterPark restyle texture name')
                chosen[piece] = path
        else:
            report = read_json(root / 'inputs.json')
            if set(report) != {'schema', 'complete', 'assets'} or report['schema'] != 1 or report['complete'] is not True:
                raise ValueError('Incomplete canonical CraterPark inventory')
            seen = set()
            for row in report['assets']:
                piece = row['name']
                if (set(row) != {'name', 'packet', 'sha256', 'kind'} or not NAME.fullmatch(piece)
                        or piece.casefold() in seen or row['packet'] != piece + '.npz'
                        or row['kind'] not in ('render', 'collision', 'seed')
                        or (row['kind'] == 'seed' and piece != 'SM_CP_ImportSeed')
                        or not piece.startswith({'render': 'SM_CP_', 'collision': 'UC_CP_', 'seed': 'SM_CP_ImportSeed'}[row['kind']])):
                    raise ValueError('Foreign canonical CraterPark owner')
                seen.add(piece.casefold())
                path = _file(root, row['packet'])
                if hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
                    raise ValueError('Changed canonical CraterPark packet')
                with np.load(path, allow_pickle=False) as packet:
                    spec = json.loads(str(packet['spec']))
                    if spec['name'] != piece or spec['kind'] != row['kind']:
                        raise ValueError('CraterPark packet identity differs from its inventory')
                if row['kind'] == kind:
                    chosen[piece] = path
            expected = {'inputs.json', 'metadata.npz', *(row['packet'] for row in report['assets'])}
            if {p.name for p in root.iterdir()} != expected or not seen:
                raise ValueError('CraterPark source inventory has missing or extra members')
            _file(root, 'metadata.npz')
        if not chosen:
            raise ValueError('CraterPark selected FileSet role is empty')
        for piece, path in chosen.items():
            shutil.copyfile(path, output / (piece + path.suffix))
    finally:
        if scratch.exists():
            shutil.rmtree(scratch)


def select_texture(source=None, output=None, piece=None):
    source, output = Path(source), Path(output)
    if not NAME.fullmatch(piece) or {p.name for p in source.iterdir()} != {piece + '.png'} or output.exists():
        raise ValueError('Expected exactly the selected CraterPark texture')
    path = _file(source, piece + '.png')
    output.mkdir(parents=True)
    shutil.copyfile(path, output / path.name)


def export_packet(source=None, output=None, payload=None, metadata=None, piece=None, planner=None):
    """Run the original selected-packet planner, then the fixed validated FBX exporter."""
    from atelier.build_v2.blender_ops import run_export_piece, verify_plan
    from v2_geometry_templates import LIMITS
    source, output, payload, metadata = map(Path, (source, output, payload, metadata))
    if not NAME.fullmatch(piece) or {p.name for p in source.iterdir()} != {piece + '.npz'}:
        raise ValueError('Expected exactly one selected canonical CraterPark packet')
    _file(source, piece + '.npz')
    if any(path.exists() for path in (output, payload, metadata)):
        raise ValueError('CraterPark export roots must be fresh')
    output.mkdir(parents=True); payload.mkdir(parents=True); metadata.mkdir(parents=True)
    work = metadata / '.plan'
    spec = importlib.util.spec_from_file_location('craterpark_selected_plan', planner)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    module.main(['--input', str(source / (piece + '.npz')), '--output', str(work),
                 '--metadata', str(metadata / (piece + '.json'))])
    checked = verify_plan(work, parent=piece, limits=LIMITS, output_format='fbx')
    if len(checked['pieces']) != 1 or checked['pieces'][0]['name'] != piece:
        raise ValueError('Canonical CraterPark packet unexpectedly split')
    (metadata / 'plan.json').write_text(json.dumps(checked, sort_keys=True, allow_nan=False) + '\n')
    member = checked['pieces'][0]['payload']
    shutil.copyfile(_file(work, member), payload / (piece + '.npz'))
    context = SimpleNamespace(params={'format': 'fbx', 'payload_encoding': 'mesh_ir', 'payload_role': 'geometry',
                                     'payload_member': piece + '.npz', 'options': {}},
                              inputs={'payload': payload}, outputs=(piece + '.fbx', 'export.json'),
                              output=lambda name: output / name)
    run_export_piece(context)
    shutil.rmtree(work)


def native_summary(build_archive=None, render=(), collision=(), output=None):
    """Require the original assembled source library and every selected native report before the alias completes."""
    output = Path(output)
    if output.exists():
        raise ValueError('CraterPark native summary must be fresh')
    output.mkdir(parents=True)
    build_file = Path(build_archive)
    if build_file.is_symlink() or not build_file.is_file():
        raise ValueError('CraterPark requires its decoded original build.json ROOT')
    build = read_json(build_file)
    observed = []
    for kind, values in (('render', render), ('collision', collision)):
        expected = {entry['name']: entry for entry in build[kind]}
        if len(expected) != len(build[kind]) or len(values) != len(expected):
            raise ValueError('CraterPark native membership differs from assembled runtime source')
        seen = set()
        for child, piece in values:
            if piece in seen or piece not in expected:
                raise ValueError('CraterPark native report has a foreign or duplicate owner')
            seen.add(piece)
            report = read_json(_file(child.products[0].paths[0], 'data/reports/' + piece + '.json'))
            if (report['name'] != piece or report['triangles'] != expected[piece]['triangles']
                    or report['collision'] is not (kind == 'collision')
                    or not 0 <= report['bounds_error_cm'] < .05):
                raise ValueError('CraterPark native report differs from assembled source')
            observed.append(report)
    (output / 'native.json').write_text(json.dumps({'meshes': observed}, sort_keys=True, allow_nan=False) + '\n')
