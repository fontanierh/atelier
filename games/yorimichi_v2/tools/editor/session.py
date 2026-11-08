"""Feed a batch of claimed editor jobs, in order, to one warm editor this checkout owns (owner steering #31137).

    uv run python games/yorimichi_v2/tools/editor/session.py JOBS.json

JOBS.json is {"jobs": [...]}; each job is one of
    {"kind": "objects", "regions": ["region/w16-belmonte"], "environment": "region/w00-island", "claim": "TASK",
     "only": ["object/belmonte/fountain"]}                    tools/migrate/objects.py's migration, these objects only
    {"kind": "script", "script": "move_actor.py", "claim": "TASK", "paths": [...], "scopes": [...], "env": {"V2_..."}}
                                                               one named unreal/Scripts editor script, like editor.run
Other agents prepare jobs and their inputs in their own checkouts; only this controller writes this checkout and
drives its editor. The explicit build step `editor.session` (unreal/Scripts/job_queue.py) supplies the one guarded,
admitted editor; the build's lock and memory guard own its whole life. The controller authorizes each job just before
it runs, with the same code as the job's own cold step (build.py's _authorize_migration / _authorize_editor, which
name that job's save lists), waits for its receipt, then checks it with that step's code (_check_migration_writes /
_check_editor_writes) and records what it wrote before the next job starts. A job needs a claim. The editor scripts
and code are fixed for the batch: a changed unreal/Scripts or unreal/Source ends the session before the next job.
The first failure ends the session. OUT/summary.json keeps the editor start time and each job's run and check time,
the figures to compare with one cold editor per job.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parents[1]
REPO = GAME.parents[1]
sys.path.insert(0, str(GAME / 'tools/content'))
sys.path.insert(0, str(GAME / 'tools/migrate'))
import authority  # noqa: E402

LOG = REPO / 'build/yorimichi_v2/logs/editor.session.guard/stdout.log'   # the guarded editor's output
OUT = REPO / 'build/yorimichi_v2/editor-session'
BEAT_SECONDS = 10.


class SessionError(RuntimeError):
    pass


def code_digest(game: Path = GAME) -> str:
    """The editor scripts and C++ the session loaded: a change ends the batch before its next job."""
    digest = hashlib.sha256()
    for root in (game / 'unreal/Scripts', game / 'unreal/Source'):
        for path in sorted(p for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts):
            digest.update(path.relative_to(game).as_posix().encode() + b'\0' + path.read_bytes() + b'\0')
    return digest.hexdigest()


def load_build():
    """The game's build recipe, for its authorize and check functions (one module: their snapshots are shared)."""
    spec = importlib.util.spec_from_file_location('yorimichi_v2_build_recipe', GAME / 'build.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def launch_step(folder: Path) -> subprocess.Popen:
    env = {**os.environ, 'V2_JOBS': str(folder)}
    LOG.unlink(missing_ok=True)
    return subprocess.Popen(['nice', '-n', '10', 'uv', 'run', 'atelier', 'build', 'yorimichi_v2', 'editor.session'],
                            cwd=REPO, env=env)


class JobContext:
    """What the authorize/check calls read of a build context: where to put this job's save lists."""
    def __init__(self, out: Path):
        self.out = out


class Session:
    def __init__(self, game: Path = GAME, *, out: Path = OUT, launch=launch_step, log: Path = LOG, echo=print,
                 open_seconds: float = 3 * 3600):
        self.game, self.launch, self.log_path, self.echo = game, launch, log, echo
        self.nonce = uuid.uuid4().hex
        self.folder = out / self.nonce
        self.open_seconds = open_seconds
        self.process = None
        self.seq = 0
        self.code = None
        self.offset = 0
        self.text = ''
        self.summary = {'nonce': self.nonce, 'jobs': []}
        self.checked: list[str] = []
        self.beating = threading.Event()
        self.build = None

    # -- the editor ------------------------------------------------------------------------------------------------
    def _beat(self):
        while not self.beating.wait(BEAT_SECONDS):
            (self.folder / 'heartbeat').touch()

    def _write(self, name, value):
        temporary = self.folder / (name + '.tmp')
        temporary.write_text(json.dumps(value) + '\n')
        temporary.replace(self.folder / name)

    def _read(self, name):
        try:
            return json.loads((self.folder / name).read_text())
        except (FileNotFoundError, ValueError):
            return None

    def _wait(self, what, ready, seconds):
        deadline = time.monotonic() + seconds
        while True:
            found = ready()
            if found:
                return found
            if self.process.poll() is not None:
                raise SessionError(f'the editor session ended (exit {self.process.returncode}) while waiting for '
                                   f'{what}; see {self.log_path}')
            if time.monotonic() > deadline:
                raise SessionError(f'no {what} within {seconds:g} s')
            time.sleep(.2)

    def _log(self) -> str:
        try:
            with self.log_path.open(errors='replace') as log:
                log.seek(self.offset)
                self.text += log.read()
                self.offset = log.tell()
        except FileNotFoundError:
            pass
        return self.text

    def open(self):
        self.folder.mkdir(parents=True)
        self.code = code_digest(self.game)
        self._write('session.json', {'nonce': self.nonce, 'code': self.code})
        (self.folder / 'heartbeat').touch()
        threading.Thread(target=self._beat, daemon=True).start()
        started = time.monotonic()
        self.process = self.launch(self.folder)
        self._wait('editor start', lambda: (self._read('ready.json') or {}).get('nonce') == self.nonce,
                   self.open_seconds)
        self.summary['startup_seconds'] = round(time.monotonic() - started, 1)
        self.echo(f'editor session {self.nonce[:8]} ready after {self.summary["startup_seconds"]} s')
        self.build = load_build()
        return self

    def close(self) -> int:
        if self.process is None:
            return 0
        try:
            if self.process.poll() is None:
                self._write('next.json', {'nonce': self.nonce, 'seq': self.seq + 1, 'close': True})
            code = self.process.wait()
        finally:
            self.beating.set()
            self.folder.mkdir(parents=True, exist_ok=True)
            self.summary['exit'] = self.process.returncode
            self._write('summary.json', self.summary)
        self.echo(f'editor session {self.nonce[:8]} closed (exit {code}); summary {self.folder / "summary.json"}')
        return code

    def __enter__(self):
        return self.open()

    def __exit__(self, *_):
        self.close()

    def run(self, name: str, script: str, env: dict, *, seconds: float = 1800) -> str:
        """One job's editor part: its script with its environment; returns its section of the editor log."""
        if code_digest(self.game) != self.code:
            raise SessionError('unreal/Scripts or unreal/Source changed since the editor started; '
                               'start a new session for the changed code')
        self.seq += 1
        seq = self.seq
        self._write('next.json', {'nonce': self.nonce, 'seq': seq, 'name': name, 'script': script, 'env': env})
        receipt = self._wait(f'job {seq} {name}', lambda: (r := self._read(f'{seq}.receipt.json')) and
                             r.get('nonce') == self.nonce and r, seconds)
        end = f'V2 JOB END {seq} '
        # The receipt can reach the disk before Unreal flushes its log; the job's log section ends with its marker.
        try:
            self._wait(f'job {seq} log', lambda: end in self._log(), 30)
        except SessionError:
            if receipt.get('error') is None:
                raise
        text = self.text.split(f'V2 JOB START {seq} ', 1)[-1].split(end, 1)[0]
        if receipt.get('error'):
            raise SessionError(f'job {seq} {name}: {receipt["error"]}')
        self.summary['jobs'].append({'seq': seq, 'name': name, 'seconds': receipt['seconds']})
        return text

    # -- jobs --------------------------------------------------------------------------------------------------------
    def _checked(self, before):
        written = sorted('games/yorimichi_v2/' + rel
                         for rel in authority.written(before, authority.content_snapshot(self.game)))
        self.checked += written
        self._write('checked.json', sorted(set(self.checked)))
        return written

    def _job_env(self, keys):
        return {k: os.environ.get(k) for k in keys}

    def objects(self, regions, environment, claim, only=None):
        """tools/migrate/objects.py's migration of these objects, its editor part a session job."""
        import objects
        if not claim:
            raise SessionError('a session job needs a claim')
        timing = {}

        def editor(plan_file: Path) -> str:
            os.environ['V2_MIGRATE_PLAN'] = str(plan_file)
            context, log = JobContext(self.folder / f'job-{self.seq + 1}'), _Log()
            self.build._authorize_migration(context, log)
            before = dict(self.build.MIGRATE_BEFORE) or authority.content_snapshot(self.game)
            env = self._job_env(['V2_MIGRATE_PLAN', 'V2_SAVE_DENY']) | {'V2_SAVE_ALLOW': None}
            try:
                text = self.run(f'objects {" ".join(only or regions)}', 'migrate_objects.py', env)
            finally:
                os.environ.pop('V2_MIGRATE_PLAN', None)
            started = time.monotonic()
            os.environ['V2_MIGRATE_PLAN'] = str(plan_file)
            try:
                self.build._check_migration_writes(context, log)
            finally:
                os.environ.pop('V2_MIGRATE_PLAN', None)
            self._checked(before)
            timing['check'] = time.monotonic() - started
            return text

        started = time.monotonic()
        made = objects.migrate(self.game, list(regions), environment, claim, only=only, editor=editor,
                               out=self.folder / f'job-{self.seq + 1}', echo=self.echo)
        self.summary['jobs'][-1].update(objects=sorted(made), total_seconds=round(time.monotonic() - started, 1),
                                        check_seconds=round(timing.get('check', 0), 1))
        return made

    def script(self, script, claim, paths, scopes=(), env=None):
        """One named unreal/Scripts editor script under a claim, like editor.run but in this editor."""
        extra = dict(env or {})
        if not claim:
            raise SessionError('a session job needs a claim')
        if any(not k.startswith('V2_') or k.startswith(('V2_SAVE_', 'V2_JOBS', 'V2_EDITOR_')) for k in extra):
            raise SessionError(f'a script job sets only its own V2_ inputs, not {sorted(extra)}')
        names = {'V2_EDITOR_SCRIPT': str(self.game / 'unreal/Scripts' / script), 'V2_EDITOR_CLAIM': claim,
                 'V2_EDITOR_PATHS': ' '.join(paths), 'V2_EDITOR_SCOPES': ' '.join(scopes)}
        started = time.monotonic()
        saved = {k: os.environ.get(k) for k in names}
        os.environ.update(names)
        try:
            context, log = JobContext(self.folder / f'job-{self.seq + 1}'), _Log()
            self.build._authorize_editor(context, log)
            before = dict(self.build.EDITOR_BEFORE)
            job_env = self._job_env(['V2_SAVE_ALLOW', 'V2_SAVE_DENY']) | names | extra
            text = self.run(f'script {script}', script, job_env)
            checking = time.monotonic()
            self.build._check_editor_writes(context, log)
            written = self._checked(before)
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        self.summary['jobs'][-1].update(written=written, total_seconds=round(time.monotonic() - started, 1),
                                        check_seconds=round(time.monotonic() - checking, 1))
        return text


class _Log:
    """The authorize/check calls' log: kept for the job's summary line."""
    def __init__(self):
        self.lines = []

    def write(self, text):
        self.lines.append(text)


def run_jobs(jobs: list[dict], session: Session) -> None:
    with session:
        for job in jobs:
            kind = job.get('kind')
            if kind == 'objects':
                session.objects(job['regions'], job['environment'], job.get('claim'), job.get('only'))
            elif kind == 'script':
                session.script(job['script'], job.get('claim'), job.get('paths', []), job.get('scopes', ()),
                               job.get('env'))
            else:
                raise SessionError(f'unknown job kind {kind!r}')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('jobs', type=Path, help='JSON file {"jobs": [...]}')
    args = parser.parse_args(argv)
    import objects
    import records
    import save_validate
    jobs = json.loads(args.jobs.read_text())['jobs']
    session = Session()
    try:
        run_jobs(jobs, session)
    except (SessionError, objects.ObjectError, authority.Unauthorized, save_validate.ValidationError,
            records.RecordError, RuntimeError) as error:
        print(f'editor session failed: {error}', file=sys.stderr)
        return 1
    finally:
        done = session.summary['jobs']
        print(f'{len(done)} of {len(jobs)} job(s) done; editor start {session.summary.get("startup_seconds")} s; '
              + ', '.join(f'{j["name"]} {j["seconds"]:.0f}+{j.get("check_seconds", 0):.0f} s' for j in done))
    return 0


if __name__ == '__main__':
    sys.exit(main())
