"""An interrupted build stops its light children's whole process group."""
import os
import signal
import sys
import threading
import time

import pytest

from atelier import build
from atelier.harness.safety.cancellation import termination_cleanup


def test_termination_stops_the_light_command_process_group(tmp_path):
    marker = tmp_path / 'grandchild.pid'
    script = ('import os, subprocess, sys, time; '
              f'child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"]); '
              f'open({str(marker)!r}, "w").write(str(child.pid)); time.sleep(60)')
    timer = threading.Timer(1.0, os.kill, (os.getpid(), signal.SIGTERM))
    timer.start()
    started = time.monotonic()
    with pytest.raises(SystemExit):
        with termination_cleanup():
            build.run_light([sys.executable, '-c', script], dict(os.environ), {})
    timer.cancel()
    assert time.monotonic() - started < 20
    grandchild = int(marker.read_text())
    for _ in range(50):
        try:
            os.kill(grandchild, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        pytest.fail('grandchild survived the interrupted build')
