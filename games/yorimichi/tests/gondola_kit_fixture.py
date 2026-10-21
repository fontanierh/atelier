"""Load the gondola kit's modules for a test without Blender, and leave no trace in sys.modules or sys.path.

The kit's modules have short names (rope, checks, walk, cabin, ...) and some import bpy and mathutils. A test loads
them inside gondola_modules(): sys.modules is patched for the duration (patch.dict restores it afterwards, dropping
everything imported inside, so no stub or kit module leaks into other tests), and the kit directory is on sys.path
only while importing. The loaded module objects stay usable after the block.

pure=True blocks bpy and mathutils (an import of either raises ImportError), proving the module needs no Blender;
pure=False stubs both with MagicMock for the modules that only use them inside functions.
"""
import importlib
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy  # noqa: F401  (imported once out here: walk.py needs it, and numpy must not be reloaded inside the patch)

KIT = Path(__file__).resolve().parents[1] / 'assets' / 'vehicles' / 'gondola'
KIT_MODULES = {p.stem for p in KIT.glob('*.py')}


@contextmanager
def gondola_modules(*names, pure=True):
    stubs = {'bpy': None, 'mathutils': None} if pure else {'bpy': MagicMock(name='bpy'), 'mathutils': MagicMock(name='mathutils')}
    saved_path = list(sys.path)
    with patch.dict(sys.modules, stubs):
        for name in (KIT_MODULES | {'solid_mesh'}) & set(sys.modules):
            del sys.modules[name]                      # a same-named module from elsewhere must not stand in
        sys.path.insert(0, str(KIT))
        sys.path.insert(0, str(KIT.parents[2] / 'world'))
        try:
            yield SimpleNamespace(**{n: importlib.import_module(n) for n in names})
        finally:
            sys.path[:] = saved_path


def load(*names, pure=True):
    with gondola_modules(*names, pure=pure) as kit:
        return kit
