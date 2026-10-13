"""The native contact validator's Python binding: receipt on success, None on failure."""


def validate_contact_data(library, mesh, required, context='Native skin-morph contact'):
    # Unreal suppresses a bool return when a UFUNCTION also has output parameters.
    # ValidateSkinMorphContacts therefore yields its FString receipt, or None.
    receipt = library.validate_skin_morph_contacts(mesh, required)
    if receipt is None:
        raise RuntimeError(context + ' validation failed')
    if not isinstance(receipt, str):
        raise TypeError('Unexpected native skin-morph contact validation result: ' + repr(receipt))
    return receipt
