"""Keep original parent runtime policy outside independently consumed mesh packets."""
FIELDS={'parent_bounds_m','parent_material_slots'}


def metadata(entry,slots,collides):
    assembly={key:value for key,value in entry.items() if key in FIELDS}
    leaf={key:value for key,value in entry.items() if key not in FIELDS}
    return dict(metadata=dict(entry=leaf,slots=slots,collision=collides),assembly_metadata=assembly)


def entry(piece,metadata):
    assembly=piece.get('assembly_metadata',{})
    if not isinstance(assembly,dict) or set(assembly)-FIELDS:
        raise ValueError('Foreign Belmonte parent runtime metadata')
    if set(assembly)&set(metadata['entry']):raise ValueError('Ambiguous Belmonte runtime metadata')
    return dict(metadata['entry'],**assembly)
