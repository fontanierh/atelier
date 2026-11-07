"""A stand-in for the `atelier claims` commands authority.py runs: task scopes, the publish-stage path check and
`extend ID --lock-path ... --acquire` (binding created files to a claim)."""
import json
import os
import subprocess

REAL_RUN = subprocess.run


def lock_paths(command):
    return [command[i + 1] for i, arg in enumerate(command) if arg == '--lock-path']


class FakeClaims:
    def __init__(self, scopes=(), covers=True):
        self.scopes, self.covers, self.checks, self.extended = list(scopes), covers, [], []

    def __call__(self, command, **kwargs):
        if command[:4] != ['uv', 'run', 'atelier', 'claims']:
            return REAL_RUN(command, **kwargs)   # only the claims service is faked
        if command[4:6] == ['task', 'show']:
            claims = [{'id': 1, 'state': 'active', 'principal': os.environ.get('ATELIER_AGENT'),
                       'items': [{'kind': 'scope', 'value': s} for s in self.scopes]}]
            return Result(0, json.dumps({'id': command[6], 'claims': claims}))
        if command[4] == 'check':
            self.checks.append(command)
            return Result(0 if self.covers else 1)
        if command[4] == 'extend':
            self.extended.append(command)
            return Result(0)
        raise AssertionError(f'unexpected command {command}')


class ClaimService:
    """Several tasks, each held by one agent (ATELIER_AGENT) with scopes and exact locked paths, like the service at
    the publish stage. A coordinator transfer moves a task's claim and locks to another agent's workspace."""

    def __init__(self):
        self.tasks, self.extensions, self.unlocked, self.checks = {}, [], set(), []
        self.failure = None   # 'down' (the service is unavailable) or 'garbled' (its answer does not parse)

    def grant(self, task, holder, scopes, paths=()):
        self.tasks[task] = {'id': len(self.tasks) + 1, 'holder': holder, 'scopes': list(scopes), 'paths': set(paths)}

    def extend(self, task, paths):
        self.tasks[task]['paths'] |= set(paths)

    def transfer(self, task, holder):
        self.tasks[task]['holder'] = holder

    def __call__(self, command, **kwargs):
        if command[:4] != ['uv', 'run', 'atelier', 'claims']:
            return REAL_RUN(command, **kwargs)
        if self.failure == 'down':
            return Result(1, stderr='claim service unavailable')
        if self.failure == 'garbled':
            return Result(0, '<html>bad gateway</html>')
        if command[4:6] == ['task', 'show']:
            task = self.tasks.get(command[6])
            if task is None:
                return Result(1, stderr=f'no task {command[6]}')
            items = [{'kind': 'scope', 'value': s} for s in task['scopes']]
            items += [{'kind': 'path', 'value': p} for p in sorted(task['paths'])]
            return Result(0, json.dumps({'id': command[6], 'claims': [
                {'id': task['id'], 'state': 'active', 'principal': task['holder'], 'items': items}]}))
        if command[4] == 'check':
            task = self.tasks.get(command[command.index('--task') + 1])
            paths = set(command[command.index('--paths') + 1:])
            self.checks.append(command)
            ok = (task is not None and task['holder'] == os.environ.get('ATELIER_AGENT') and paths <= task['paths']
                  and not paths & self.unlocked)   # a listed path whose LFS lock the service cannot verify
            return Result(0 if ok else 1)
        if command[4] == 'extend':   # the service refuses a claim another principal holds (`not_holder`)
            task = next((t for t in self.tasks.values() if str(t['id']) == command[5]), None)
            if task is None or task['holder'] != os.environ.get('ATELIER_AGENT') or '--acquire' not in command:
                return Result(1, stderr=f'claim {command[5]} is not held by {os.environ.get("ATELIER_AGENT")!r}')
            task['paths'] |= set(lock_paths(command))
            self.extensions.append(command)
            return Result(0, json.dumps({'id': task['id']}))
        raise AssertionError(f'unexpected command {command}')


class Result:
    def __init__(self, returncode, stdout='', stderr=''):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr
