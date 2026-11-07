"""A stand-in for the `atelier claims` commands authority.py runs: task scopes and the publish-stage path check."""
import json
import os
import subprocess

REAL_RUN = subprocess.run


class FakeClaims:
    def __init__(self, scopes=(), covers=True):
        self.scopes, self.covers, self.checks = list(scopes), covers, []

    def __call__(self, command, **kwargs):
        if command[:4] != ['uv', 'run', 'atelier', 'claims']:
            return REAL_RUN(command, **kwargs)   # only the claims service is faked
        if command[4:6] == ['task', 'show']:
            claims = [{'state': 'active', 'items': [{'kind': 'scope', 'value': s} for s in self.scopes]}]
            return Result(0, json.dumps({'id': command[6], 'claims': claims}))
        if command[4] == 'check':
            self.checks.append(command)
            return Result(0 if self.covers else 1)
        raise AssertionError(f'unexpected command {command}')


class ClaimService:
    """Several tasks, each held by one agent (ATELIER_AGENT) with scopes and exact locked paths, like the service at
    the publish stage. A coordinator transfer moves a task's claim and locks to another agent's workspace."""

    def __init__(self):
        self.tasks = {}

    def grant(self, task, holder, scopes, paths=()):
        self.tasks[task] = {'holder': holder, 'scopes': list(scopes), 'paths': set(paths)}

    def extend(self, task, paths):
        self.tasks[task]['paths'] |= set(paths)

    def transfer(self, task, holder):
        self.tasks[task]['holder'] = holder

    def __call__(self, command, **kwargs):
        if command[:4] != ['uv', 'run', 'atelier', 'claims']:
            return REAL_RUN(command, **kwargs)
        if command[4:6] == ['task', 'show']:
            task = self.tasks.get(command[6])
            if task is None:
                return Result(1, stderr=f'no task {command[6]}')
            items = [{'kind': 'scope', 'value': s} for s in task['scopes']]
            return Result(0, json.dumps({'id': command[6], 'claims': [
                {'state': 'active', 'holder': task['holder'], 'items': items}]}))
        if command[4] == 'check':
            task = self.tasks.get(command[command.index('--task') + 1])
            paths = set(command[command.index('--paths') + 1:])
            ok = task is not None and task['holder'] == os.environ.get('ATELIER_AGENT') and paths <= task['paths']
            return Result(0 if ok else 1)
        raise AssertionError(f'unexpected command {command}')


class Result:
    def __init__(self, returncode, stdout='', stderr=''):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr
