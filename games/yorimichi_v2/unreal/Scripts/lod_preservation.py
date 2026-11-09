"""LOD-chain preservation for a static-mesh reimport: a mesh that had several LODs keeps the same chain.

No Unreal import here: import_asset.py passes the editor subsystem and the meshes, so the rules are tested with fake
objects (tests/test_lod_preservation.py). A mesh with one LOD gets no LODs added; only a chain that had several is kept.
The chain's count and screen sizes must match within TOLERANCE after the import. If the import dropped the chain, the
recipe's reduction plan (settings `lods`: [[percent, screen], ...], LOD0 first) is applied again and checked again.
"""

TOLERANCE = 1e-3


class LodError(RuntimeError):
    pass


def read(editor, mesh) -> dict:
    """The LOD chain of a mesh: its count, each LOD's screen size and reduction (percent of triangles kept)."""
    count = int(editor.get_lod_count(mesh))
    return {'count': count,
            'screen_sizes': [float(s) for s in editor.get_lod_screen_sizes(mesh)],
            'reductions': [float(editor.get_lod_reduction_settings(mesh, index).get_editor_property('percent_triangles'))
                           for index in range(count)]}


def same_chain(before: dict, after: dict) -> bool:
    return (before['count'] == after['count'] and len(after['screen_sizes']) == after['count']
            and all(abs(a - b) <= TOLERANCE for a, b in zip(before['screen_sizes'], after['screen_sizes'])))


def check_plan(lods, count: int):
    """The recipe's plan must name the chain's levels, LOD0 first, with the chain's own screen sizes."""
    if lods is None:
        return
    if len(lods) != count:
        raise LodError(f'the recipe names {len(lods)} LOD level(s), the chain has {count}')


def preserve(editor, mesh, before, lods, make_options) -> dict:
    """The chain after the import, kept as `before` had it. `before` is None for a new package, and one LOD needs no
    action. `make_options(lods)` builds the editor's reduction options for the recipe's plan."""
    after = read(editor, mesh)
    if before is None or before['count'] <= 1:
        return after
    if same_chain(before, after):
        return after
    check_plan(lods, before['count'])
    if lods is None:
        raise LodError(f'the import dropped the LOD chain ({after["count"]} of {before["count"]} LODs) and the recipe '
                       'names no reduction plan to restore it')
    editor.set_lods(mesh, make_options(lods))
    editor.set_lod_screen_sizes(mesh, [screen for _, screen in lods])
    after = read(editor, mesh)
    if not same_chain(before, after):
        raise LodError(f'the restored LOD chain ({after["count"]} LODs, screens {after["screen_sizes"]}) does not match '
                       f'the chain before the import ({before["count"]}, screens {before["screen_sizes"]})')
    return after


def verify_record(result: dict) -> None:
    """The host-side check of a recorded result: a chain that had several LODs must have the same chain after."""
    before, after = result.get('before'), result.get('after')
    if before is None or before['count'] <= 1:
        return
    if after is None or not same_chain(before, after):
        raise LodError(f'the LOD chain changed: {before["count"]} LODs before, '
                       f'{None if after is None else after["count"]} after')
