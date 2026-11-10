"""The racing master: M_RacingTv, owned by adopted/racing (donor racing_tv_material.py). Imported under MASTERRACING."""
ENGINE_BLACK = '/Engine/EngineResources/Black'

FAMILY = {
    'name': 'racing',
    'adopted': 'adopted/racing',
    'owner': 'shared/racing',
    'license': 'owner-published (docs/DECISIONS.md D05 group 1)',
    'builder': 'racing_masters.py',   # unreal/Scripts/material_masters/, copied into each record's src/
    'donor': 'games/yorimichi/unreal/Scripts/racing_tv_material.py',
    'donor_lines': {'racing_tv': '1-57'},
    # No record references adopted/racing (checked over every asset.toml), so the fallback is never used; it is the family's only
    # master, the one a future referencing record would have to point at.
    'fallback': 'master/racing/tv',
    # `reads` is the engine Black texture (the donor's load of Picture's default), which is allowed and owns nothing. Picture itself
    # is a runtime render target, so it is not a read.
    'masters': [
        {'id': 'master/racing/tv', 'package': '/Game/Racing/M_RacingTv',
         'builder': 'racing_tv', 'reads': [ENGINE_BLACK], 'inputs': [],
         'arguments': {'brightness': 1.0}},
    ],
}
