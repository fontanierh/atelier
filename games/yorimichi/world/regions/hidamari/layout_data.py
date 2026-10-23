"""Publish city placement/query data without constructing or exporting any mesh."""
import argparse
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv if argv is not None else (
        sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else None))
    real_directory(args.output.parent)
    from hidamari import layout
    done = threading.Event()
    started = time.monotonic()
    def heartbeat():
        while not done.wait(25):
            print(f'City layout generating after {time.monotonic()-started:.0f}s; no completed data product yet', flush=True)
    thread = threading.Thread(target=heartbeat, daemon=True)
    print('City layout generation started; no geometry or exports', flush=True)
    thread.start()
    try:
        value = layout.generate()
    finally:
        done.set(); thread.join(timeout=1)
    atomic_json(args.output, value)
    print('HIDAMARI LAYOUT DATA COMPLETE', len(value['buildings']), 'buildings', flush=True)


if __name__ == '__main__':
    main()
