"""Exact owned-music inventory used by the optional Unreal music import."""


def stale_assets(existing, expected):
    """Existing package paths under /Game/Audio/Music that the current selection does not own."""
    return tuple(sorted(str(asset).split('.')[0] for asset in existing
                        if str(asset).split('.')[0].startswith('/Game/Audio/Music/')
                        and str(asset).split('.')[0] not in expected))
