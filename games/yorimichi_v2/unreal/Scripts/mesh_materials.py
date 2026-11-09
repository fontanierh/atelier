"""Assign a static mesh's materials with one final rebuild (ported from the donor's helper)."""


def assign_materials(mesh, materials):
    """@cc [owner:fontanierh,label:correctness] imported-material-batch
    A full assignment MUST preserve slot order, names and UV metadata and bind every requested material. A nonempty
    assignment MUST finish through native SetMaterial. Named slots MUST notify/rebuild the mesh only once. Unnamed slots MUST retain
    SetMaterial's native name generation. Invalid lengths or missing materials MUST fail before any mesh write.
    """
    materials = list(materials)
    slots = [slot.copy() for slot in mesh.static_materials]
    if len(slots) != len(materials) or any(material is None for material in materials):
        raise ValueError('Expected one valid material for every existing mesh slot')
    if not slots:
        return
    names = [(slot.get_editor_property('material_slot_name'),
              slot.get_editor_property('imported_material_slot_name')) for slot in slots]
    # Native SetMaterial fills missing names; preserve that behavior on unusual unnamed imports.
    if any(str(name) in ('', 'None') for pair in names for name in pair):
        for index, material in enumerate(materials):
            mesh.set_material(index, material)
        return
    for slot, material in zip(slots, materials):
        slot.set_editor_property('material_interface', material)
    # This property calls the native BlueprintSetter, which waits for async access without rebuilding.
    # Detached slot copies also avoid notifying the mesh for each intermediate struct edit. Using
    # set_editor_property on the array would add another rebuild. Finish with the normal native refresh.
    mesh.static_materials = slots
    mesh.set_material(len(slots) - 1, materials[-1])
    final = mesh.static_materials
    if [slot.get_editor_property('material_interface') for slot in final] != materials:
        raise RuntimeError('The imported mesh did not retain its assigned materials')
    if [(slot.get_editor_property('material_slot_name'),
         slot.get_editor_property('imported_material_slot_name')) for slot in final] != names:
        raise RuntimeError('The imported mesh changed its material slot names')
