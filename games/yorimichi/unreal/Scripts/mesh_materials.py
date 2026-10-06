"""Assign a static mesh's material slots without building every intermediate assignment."""


def assign_materials(mesh, materials):
    """Keep slot metadata and finish with SetMaterial's normal build and physics refresh.

    SetMaterial rebuilds the mesh, including distance fields, on every call in UE 5.8.
    Its native array setter waits for asynchronous access but does not rebuild. Copy
    the structs first: mutating a live slot wrapper can notify its owning mesh too.
    """
    materials = list(materials)
    slots = [slot.copy() for slot in mesh.static_materials]
    if not slots or len(slots) != len(materials) or any(material is None for material in materials):
        raise ValueError('Expected one valid material for every existing mesh slot')
    names = [(slot.get_editor_property('material_slot_name'),
              slot.get_editor_property('imported_material_slot_name')) for slot in slots]
    # SetMaterial fills missing names. Keep that behavior for an unusual unnamed
    # slot rather than inventing a name or changing its reimport contract.
    if any(str(name) in ('', 'None') for pair in names for name in pair):
        for index, material in enumerate(materials):
            mesh.set_material(index, material)
        return
    for slot, material in zip(slots, materials):
        slot.set_editor_property('material_interface', material)
    # Python exposes the native BlueprintGetter/Setter through this property,
    # not as callable get_static_materials/set_static_materials methods.
    mesh.static_materials = slots
    mesh.set_material(len(slots) - 1, materials[-1])
    final = mesh.static_materials
    assert [slot.get_editor_property('material_interface') for slot in final] == materials
    assert [(slot.get_editor_property('material_slot_name'),
             slot.get_editor_property('imported_material_slot_name')) for slot in final] == names
