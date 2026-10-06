"""Pinned process identities for walking a launcher's descendants on macOS.

A pid alone is not an identity: it can be reused the moment its process exits. Every relation here is checked against
start times. A parent is the same process before and after its children are listed, and a child has the same start on
both sides of a second listing. So a reused pid, the parent's or a child's, never brings in another process's children.
(The same rule as the memory guard's helper record.)
"""
import ctypes

from .memory_guard import LIB, usage

PROC_PPID_ONLY = 6
LIB.proc_listpids.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_int]
LIB.proc_name.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]


def started(pid):
    try:
        return usage(pid).started
    except ProcessLookupError:
        return None


def children(pid):
    """The live children of pid; one born during the call is caught on the next poll."""
    size = ctypes.sizeof(ctypes.c_int)
    count = LIB.proc_listpids(PROC_PPID_ONLY, pid, None, 0)
    if count <= 0:
        return []
    buf = (ctypes.c_int * (count // size + 64))()
    count = LIB.proc_listpids(PROC_PPID_ONLY, pid, buf, ctypes.sizeof(buf))
    return [p for p in buf[:max(count, 0) // size] if p > 0]


def name(pid):
    """The executable's current name ('UnrealEditor-Cmd', 'dotnet'); it changes when the process execs. '' once gone."""
    buf = ctypes.create_string_buffer(256)
    return buf.value.decode(errors='replace') if LIB.proc_name(pid, buf, 256) > 0 else ''


def owned_children(parent, parent_start):
    """(pid, start) of each child of this exact parent."""
    if started(parent) != parent_start:
        return []
    first = children(parent)
    starts = {child: started(child) for child in first}
    again = set(children(parent))
    if started(parent) != parent_start:
        return []
    return [(child, start) for child, start in starts.items()
            if start is not None and child in again and started(child) == start]
