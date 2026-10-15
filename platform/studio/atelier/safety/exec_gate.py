"""Wait for an owned tree monitor before replacing this process with its actual command."""
import os
import sys


def main():
    descriptor = int(sys.argv[1])
    try:
        ready = os.read(descriptor, 1) == b'1'
    finally:
        os.close(descriptor)
    if not ready:
        return 1
    os.execvpe(sys.argv[2], sys.argv[2:], os.environ)


if __name__ == '__main__':
    raise SystemExit(main())
