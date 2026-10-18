"""Recheck the original audio pins after GO, then exec the unchanged literal tool command."""
import json
import os
import sys

from atelier.harness.ffmpeg_audio import Command, worker_environment


def main():
    payload = json.loads(sys.argv[1])
    command = Command(**payload)
    command.verify()
    os.execve(command.executable, list(command), worker_environment())


if __name__ == '__main__':
    main()
