"""Restore a reused tree base's authored material table before its shared palette is bound."""


def restore_authored_slots(mesh, name):
    """A far crown level (world/far_crown.py) appends its own <name>_Crown slot after the authored ones, and a saved
    base reused by native admission keeps it. Drop those trailing slots, and the assembled levels that use them, so
    the shared palette binds and the LOD chain re-adds the crown's slot. Returns whether anything was dropped."""
    slots = list(mesh.get_editor_property('static_materials'))
    keys = [str(slot.get_editor_property('imported_material_slot_name')).split('.')[0] for slot in slots]
    authored = len(keys)
    while authored and keys[authored - 1] == name + '_Crown':
        authored -= 1
    if name + '_Crown' in keys[:authored]:
        raise RuntimeError('Crown slot is not after the authored slots: ' + name)
    if authored == len(slots):
        return False
    mesh.set_num_source_models(1)
    mesh.set_editor_property('static_materials', slots[:authored])
    return True
