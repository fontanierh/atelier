"""Pinned process identities for walking a launcher's descendants on macOS.

A pid alone is not an identity: it can be reused the moment its process exits. Every relation here is checked against
start times. A parent is the same process before and after its children are listed, and a child has the same start on
both sides of a second listing. So a reused pid, the parent's or a child's, never brings in another process's children.
(The same rule as the memory guard's helper record.)
"""
import ctypes

from atelier.harness.safety.memory_guard import children, name, usage

PROC_PPID_ONLY = 6


def started(pid):
    try:
        return usage(pid).started
    except ProcessLookupError:
        return None


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
