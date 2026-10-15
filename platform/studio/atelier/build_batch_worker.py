"""Cooperative worker inside a guarded Blender/editor process. Standard library only.

Each completed script waits for the host to verify its products and persist its stamp before
the next action can start. A host that disappears cannot leave an unbounded worker behind.
"""
import importlib.util
import json
import os
from pathlib import Path
import runpy
import sys
import time


ACK_SECONDS = 60.


def write(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value) + '\n')
    temporary.replace(path)


def read(path):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return None


def check_modules(script):
    if 'ATELIER_LEFT_OUT' not in os.environ:
        return
    path = Path(__file__).with_name('unreal_script_guard.py')
    spec = importlib.util.spec_from_file_location('atelier_batch_module_guard', path)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    guard.check(script, json.loads(os.environ['ATELIER_LEFT_OUT']), guard.stop)


def set_environment(values):
    """Restore script changes without briefly emptying the native process's environment."""
    for key in os.environ.keys() - values.keys():
        del os.environ[key]
    for key, value in values.items():
        if os.environ.get(key) != value:
            os.environ[key] = value


def main():
    folder = Path(os.environ['ATELIER_BATCH'])
    plan = read(folder / 'plan.json')
    base_env, base_path, base_args = dict(os.environ), list(sys.path), list(sys.argv)
    for action in plan['actions']:
        name, script = action['name'], action['script']
        set_environment(base_env | action['env'])
        sys.path[:] = [str(Path(script).parent), *base_path]
        sys.argv = [script, '--', *action['args']] if plan['kind'] == 'Blender' else [script]
        check_modules(script)
        started = time.monotonic()
        print(f'ATELIER ACTION START {name}', flush=True)
        write(folder / 'active.json', {'name': name, 'pid': os.getpid()})
        try:
            runpy.run_path(script, run_name='__main__')
        finally:
            check_modules(script)
        receipt = {'name': name, 'nonce': plan['nonce'], 'seconds': time.monotonic() - started}
        sys.stdout.flush()
        write(folder / (name + '.receipt.json'), receipt)
        deadline, spoken = time.monotonic() + ACK_SECONDS, time.monotonic()
        while True:
            ack = read(folder / (name + '.ack.json'))
            if ack and ack.get('nonce') == plan['nonce']:
                if ack['decision'] == 'abort':
                    raise RuntimeError('Host refused action certification: ' + ack['reason'])
                if ack['decision'] == 'yield':
                    print('ATELIER BATCH YIELD ' + ack['reason'], flush=True)
                    write(folder / 'result.json', {'status': 'yield', 'reason': ack['reason']})
                    print('ATELIER BATCH COMPLETE ' + plan['nonce'], flush=True)
                    return
                break
            now = time.monotonic()
            if now >= deadline:
                raise RuntimeError('Host did not acknowledge completed action within 60 seconds')
            if now - spoken >= 25:
                print(f'{name}: script finished; waiting for host verification, no new action started', flush=True)
                spoken = now
            time.sleep(.05)
    set_environment(base_env)
    sys.path[:], sys.argv = base_path, base_args
    write(folder / 'result.json', {'status': 'complete'})
    print('ATELIER BATCH COMPLETE ' + plan['nonce'], flush=True)


if __name__ == '__main__':
    main()
