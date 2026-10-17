"""Let ordinary termination unwind owned cleanup before restoring caller signal handlers."""
from contextlib import contextmanager
import signal
import threading


@contextmanager
def termination_cleanup():
    """@cc [owner:fontanierh,label:safety] guarded-termination-unwind
    On the main thread, TERM/HUP MUST unwind the guarded lifecycle with a nonzero result.
    After accepting a termination signal, repeated TERM/HUP MUST NOT interrupt the remaining cleanup.
    A first signal during an ordinary unwind can interrupt that callback; independent guards remain active.
    Previous signal handlers MUST be restored afterwards. SIGKILL cannot be caught.
    """
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    previous = {}
    cancelling = False
    def stop(number, frame):
        nonlocal cancelling
        if not cancelling:
            cancelling = True
            raise SystemExit(128 + number)
    for number in (signal.SIGTERM, signal.SIGHUP):
        previous[number] = signal.signal(number, stop)
    try:
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)
