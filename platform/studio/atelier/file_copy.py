"""Independent byte copies for runtime source and assembly actions; no build controllers."""
import ctypes
from functools import cache
import os
import shutil
import sys

from .atomic_files import _MANAGED_TEMPORARY


@cache
def clone_function():
    clone = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True).clonefile
    clone.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    clone.restype = ctypes.c_int
    return clone


def copy_file(source, destination):
    """@cc [owner:fontanierh,label:correctness;safety] managed-observable-independent-copy
    Managed scratch execution MUST use the existing Python copy fallback without
    granting ctypes access. Default unmanaged clone/fallback selection MUST remain
    unchanged. Both paths MUST preserve independent exact bytes and mode0644;
    private scope MUST NOT grant access to undeclared sources or destinations.
    See test_file_copy and the original-observer managed-copy regression.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Managed bodies use the existing observable Python copy path. No ctypes
    # load/symbol access is granted by private scratch or product ownership.
    if sys.platform == 'darwin' and _MANAGED_TEMPORARY.get() is None:
        if clone_function()(os.fsencode(source), os.fsencode(destination), 0) == 0:
            destination.chmod(0o644)
            return
    shutil.copyfile(source, destination)
    destination.chmod(0o644)
