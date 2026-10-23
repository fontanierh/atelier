"""Declare independent cached single-mesh exporters using runtime-only manifest validation."""
from dataclasses import dataclass
from pathlib import Path
import re

from .export_manifest import NAME, PRIMARY, TRIANGLE_LIMIT, name, real_directory, sha, validate, publish_receipt

@dataclass(frozen=True)
class Asset:
    """One complete planned piece; its payload is the exporter's consumed geometry."""
    key: str
    source: Path
    suffix: str = '.fbx'

    def __post_init__(self):
        name(self.key)
        if self.suffix not in PRIMARY or not isinstance(self.source, Path):
            raise ValueError('An export requires a mesh format and a declared geometry payload')


def steps(ctx, *, prefix, assets, script, inputs=(), reads=(), after=()):
    """@cc [owner:fontanierh,label:correctness;performance] independent-atomic-export-task
    Each selected asset MUST have a separate ordinary cached source action, complete inputs,
    a single primary mesh and an exclusive product root. Assembly MUST consume the individual
    products rather than conceal a whole-region geometry callback inside a small-export name.
    """
    from .build import Batch, Blender, Product, Step
    from .build_inputs import local_imports
    from .build_batch_source import support as batch_support
    if not isinstance(prefix, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z][A-Za-z0-9_-]*)*', prefix):
        raise ValueError('Atomic export prefix must be a canonical task namespace')
    source_inputs = local_imports(script) if Path(script).is_file() else [script]
    assets = tuple(assets)
    if len({a.key.casefold() for a in assets}) != len(assets):
        raise ValueError('Export asset identities must be case-fold unique')
    result = []
    for asset in assets:
        folder = ctx.out / 'exports' / prefix / asset.key
        args = ('--input', str(asset.source), '--output', str(folder), '--format', asset.suffix)
        result.append(Step(
            prefix + '.' + asset.key,
            [Blender(script, args, threads=3, factory_startup=True,
                     env=(('PYTHONHASHSEED', '0'),))],
            inputs=[*source_inputs, *batch_support().values(), *inputs, asset.source], reads=list(reads), after=list(after),
            products=[Product(prefix + '.' + asset.key, (folder,))],
            cache=True, toolchain=True, batch=Batch(prefix + ' atomic exports'), heavy=True,
            verify=lambda folder=folder, key=asset.key: present(folder, key=key),
            about='independent bounded export ' + asset.key))
    return result


def present(root, *, key):
    try:
        validate(root, key=key)
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False
