"""One owned cleanup for the kart scenarios: keys, stick, camera and fixed timestep.

A scenario that raises must not leave the player holding throttle or steering, the review camera detached, or the
game at a fixed step. Every kart scenario calls cleanup() on success and on error; it is idempotent, so a second
call is harmless.
"""
KEYS = ('W', 'A', 'S', 'D', 'SpaceBar')


def cleanup(live, restore_camera=None):
    for key in KEYS:
        try:
            live.L.input_key(key, 'release', 0.0)
        except Exception:
            pass
    try:
        live.drive(0.0, 0.0)
    except Exception:
        pass
    if restore_camera is not None:
        try:
            restore_camera()
        except Exception:
            pass
    try:
        live.L.fixed_step(0)
    except Exception:
        pass

