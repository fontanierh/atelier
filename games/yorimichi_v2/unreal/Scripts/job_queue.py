"""Run a batch of authorized editor jobs in one warm editor (build step `editor.session`, tools/editor/session.py).

The controller (tools/editor/session.py) owns this editor and its checkout. It authorizes one job at a time and
writes it to V2_JOBS/next.json: a sequence number, the session nonce, the V2 script and the job's environment,
which names the job's own V2_SAVE_ALLOW/V2_SAVE_DENY lists (V2SaveGuard reads them per save). Between jobs the
session's environment names an empty allow list, so nothing may be saved. Each job runs once; a job that raises,
or leaves a package unsaved, ends the session, so no later job saves what an earlier one left dirty. The controller
touches V2_JOBS/heartbeat while it authorizes and checks; one that stops cannot leave this editor waiting: after
IDLE_SECONDS without a heartbeat it exits with an error.
"""
import json
import os
import runpy
import sys
import time
from pathlib import Path

import unreal as U

MARKER = 'V2 JOBS DONE'
IDLE_SECONDS = 120.
SCRIPTS = Path(__file__).resolve().parent


def write(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value) + '\n')
    temporary.replace(path)


def read(path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        return None


def set_environment(values):
    """Exactly `values`, without briefly emptying the editor's environment (V2SaveGuard reads it per save)."""
    for key in os.environ.keys() - values.keys():
        del os.environ[key]
    for key, value in values.items():
        if os.environ.get(key) != value:
            os.environ[key] = value


def dirty_packages():
    utils = U.EditorLoadingAndSavingUtils
    return sorted(p.get_name() for p in [*utils.get_dirty_content_packages(), *utils.get_dirty_map_packages()])


def job_script(name):
    script = (SCRIPTS / name).resolve()
    if script.parent != SCRIPTS or not script.is_file() or script.name in ('job_queue.py', 'import_asset.py'):
        raise RuntimeError(f'{name} is not a V2 editor script a session job may run')
    return script


def main():
    folder = Path(os.environ['V2_JOBS'])
    session = read(folder / 'session.json')
    if not session or not os.environ.get('V2_SAVE_ALLOW') or not U.V2SaveGuard.is_active():
        raise RuntimeError('a job session needs its session.json and an active V2 save guard (editor.session)')
    nonce, base_env, base_path = session['nonce'], dict(os.environ), list(sys.path)
    write(folder / 'ready.json', {'nonce': nonce, 'pid': os.getpid()})
    U.log(f'V2 JOBS READY {nonce}')
    expected = 1
    while True:
        job = read(folder / 'next.json')
        if not job or job.get('nonce') != nonce or job.get('seq') != expected:
            beat = folder / 'heartbeat'
            if not beat.is_file() or time.time() - beat.stat().st_mtime > IDLE_SECONDS:
                raise RuntimeError(f'the controller has not answered for {IDLE_SECONDS:g} s')
            time.sleep(.1)
            continue
        if job.get('close'):
            break
        script = job_script(job['script'])
        set_environment(base_env | {k: v for k, v in job['env'].items() if v is not None})
        for key in [k for k, v in job['env'].items() if v is None]:
            os.environ.pop(key, None)
        sys.path[:] = [str(SCRIPTS), *base_path]
        U.log(f'V2 JOB START {expected} {job["name"]}')
        started, error = time.monotonic(), None
        try:
            runpy.run_path(str(script), run_name='__main__')
        except Exception as raised:   # reported to the controller, then the session ends
            error = f'{type(raised).__name__}: {raised}'
        finally:
            set_environment(base_env)
            sys.path[:] = base_path
        left = dirty_packages()
        if left and not error:
            error = f'{len(left)} package(s) left unsaved, e.g. {left[0]}'
        U.log(f'V2 JOB END {expected} {job["name"]} {"ok" if not error else "failed"}')
        write(folder / f'{expected}.receipt.json', {'nonce': nonce, 'seq': expected, 'error': error,
                                                    'seconds': round(time.monotonic() - started, 3)})
        if error:
            raise RuntimeError(f'job {expected} {job["name"]} failed: {error}')
        expected += 1
    U.log(f'{MARKER} {nonce} jobs={expected - 1}')


main()
