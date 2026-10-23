"""Independent byte copies for runtime source and assembly actions; no build controllers."""
import ctypes
from functools import cache
import os
import shutil
import sys


@cache
def clone_function():
    clone = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True).clonefile
    clone.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    clone.restype = ctypes.c_int
    return clone


def copy_file(source, destination):
    """An APFS clone when available, otherwise a byte copy. Never a mutable hard/symbolic link."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == 'darwin':
        if clone_function()(os.fsencode(source), os.fsencode(destination), 0) == 0:
            destination.chmod(0o644)
            return
    shutil.copyfile(source, destination)
    destination.chmod(0o644)
