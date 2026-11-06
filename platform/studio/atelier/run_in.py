"""`python -m atelier.run_in FOLDER COMMAND [ARG ...]`: run COMMAND in FOLDER, in this very process.

For a build command that must start in its own folder. It replaces itself with COMMAND (exec), so the process the
guard launched, watches and ends is COMMAND itself. Standard library only.
"""
import os
import sys


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    folder, command = argv[0], argv[1:]
    os.chdir(folder)
    os.execvp(command[0], command)


if __name__ == '__main__':
    sys.exit(main())
