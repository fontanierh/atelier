"""Explicit per-asset palette and random context; no sibling constructor replay."""
import json
import math
from pathlib import Path

from atelier.export_manifest import name, real_directory
from random_stream import positioned


def header(path, asset):
    path = Path(path)
    real_directory(path.parent)
    if path.is_symlink() or not path.is_file():
        raise ValueError('City constructor requires its own regular source parameters')
    value = json.loads(path.read_text())
    if (set(value) != {'schema', 'asset', 'seed', 'prefix_words', 'palette_file'}
            or type(value['schema']) is not int or value['schema'] != 1
            or value['asset'] != name(asset) or type(value['seed']) is not int
            or type(value['prefix_words']) is not int or not 0 <= value['prefix_words'] <= 1_000_000
            or not isinstance(value['palette_file'], str)):
        raise ValueError('Invalid city constructor source context')
    relative = value['palette_file']
    if (not relative.startswith('palettes/') or not relative.endswith('.json')
            or relative != 'palettes/' + name(Path(relative).stem) + '.json'):
        raise ValueError('Invalid selected source palette path')
    palette = path.parent / relative
    real_directory(palette.parent)
    if palette.is_symlink() or not palette.is_file():
        raise ValueError('Selected source palette must be regular and unlinked')
    return value, palette


def inputs(path, asset):
    _, palette = header(path, asset)
    return (Path(path), palette)


def read(path, asset):
    value, palette = header(path, asset)
    colours = json.loads(palette.read_text())
    if type(colours) is not dict or not colours:
        raise ValueError('Invalid city source palette')
    for key, colour in colours.items():
        if (not isinstance(key, str) or not key or type(colour) is not list or len(colour) != 3
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in colour)):
            raise ValueError('Invalid city source palette')
    return {key: value[key] for key in ('schema', 'asset', 'seed', 'prefix_words')} | dict(palette=colours)


def apply(value, kernel):
    """@cc [owner:fontanierh,label:correctness] independent-city-constructor-context
    Restore the explicit selected asset's palette and measured random position before
    construction, including in a reused Blender worker. Import its current constructor
    modules first, then restore this context so import-time sibling state cannot affect
    the result. Do not run another constructor or read its export to recover context.
    Palette entries MUST retain tuple semantics used by current surface classification.
    """
    kernel.PALETTE.clear()
    kernel.PALETTE.update({key: tuple(rgb) for key, rgb in value['palette'].items()})
    kernel.R.setstate(positioned(value['seed'], value['prefix_words']).getstate())
