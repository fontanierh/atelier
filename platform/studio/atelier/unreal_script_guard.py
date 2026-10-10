"""Runs an editor script (ATELIER_SCRIPT) in an editor started on a descriptor that loads only the game modules its
build step declares (atelier.unreal_modules.descriptor), then checks that it stayed that way.

The other game and plugin modules are not loaded, so their classes, defaults and assets are not there to use. A script
can still load one (unreal.load_module, a console command), so when it ends, the guard lists the libraries the process
has loaded; if any is one the descriptor left out (ATELIER_LEFT_OUT), it ends the editor with an error and the step
fails. Runs inside the editor's Python: standard library only.
"""
import ctypes, json, os, runpy, sys


def loaded_libraries():
    """The paths of the libraries this process has loaded (macOS dyld)."""
    dyld = ctypes.CDLL(None)
    dyld._dyld_get_image_name.restype = ctypes.c_char_p
    return [dyld._dyld_get_image_name(index).decode() for index in range(dyld._dyld_image_count())]


def undeclared(loaded, left_out):
    """The left-out libraries among those loaded."""
    left_out = {os.path.realpath(path) for path in left_out}
    return sorted({os.path.realpath(path) for path in loaded} & left_out)


def check(script, left_out, stop):
    found = undeclared(loaded_libraries(), left_out)
    if found:
        stop(f'{script} loaded {", ".join(os.path.basename(p) for p in found)}, from game or plugin modules its build step '
             f'does not declare (UnrealScript modules)')


def stop(message):
    print(f'ATELIER SCRIPT GUARD: {message}', flush=True)
    sys.stderr.flush()
    os._exit(3)   # an exception could be caught by the script; the step must fail


def main():
    script, left_out = os.environ['ATELIER_SCRIPT'], json.loads(os.environ['ATELIER_LEFT_OUT'])
    check(script, left_out, lambda message: stop('before the script ran, ' + message))
    sys.argv = [script]
    sys.path.insert(0, os.path.dirname(script))
    try:
        runpy.run_path(script, run_name='__main__')
    finally:
        check(script, left_out, stop)


if __name__ == '__main__':
    main()
