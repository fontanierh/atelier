"""``atelier claims ...``: run the service, or act on it as one principal."""
import json
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_URL = 'http://127.0.0.1:8840'


def configure(sub):
    p = sub.add_parser('claims', help='global task/scope claims bound to Git LFS locks')
    p.add_argument('--url', default=os.environ.get('ATELIER_CLAIMS_URL', DEFAULT_URL), help='claims service URL')
    p.add_argument('--actor', default=os.environ.get('ATELIER_CLAIMS_ACTOR') or os.environ.get('ATELIER_AGENT'),
                   help='registered principal acting (default: ATELIER_CLAIMS_ACTOR or ATELIER_AGENT)')
    p.add_argument('--token-file', help='private bearer token file (default: ATELIER_CLAIMS_TOKEN[_FILE] or '
                   '~/.config/atelier/claims.token)')
    p.add_argument('--repo', default='.', help='checkout used for git and git-lfs (default: current directory)')
    p.add_argument('--lfs-remote', help='git remote whose LFS server holds the locks (default: git-lfs choice)')
    a = p.add_subparsers(dest='claims_action', required=True)

    s = a.add_parser('serve', help='run the service (the only process that opens its database)')
    s.add_argument('--db', required=True, help='SQLite database on this host (never a shared folder)')
    s.add_argument('--git-repo', required=True, help='service-host clone of the shared repository')
    s.add_argument('--git-remote', default='origin')
    lfs = s.add_mutually_exclusive_group(required=True)
    lfs.add_argument('--lfs-url', help='LFS locking API base URL (verifier uses ATELIER_CLAIMS_LFS_AUTH as Authorization)')
    lfs.add_argument('--lfs-repo', help='verify with `git lfs locks --json` in this checkout')
    s.add_argument('--bind', default='127.0.0.1', help='listen address (default: loopback; use a private-network address)')
    s.add_argument('--port', type=int, default=8840)
    s.add_argument('--coordinator', action='append', default=[], help='principal allowed to recover/resolve (repeatable)')
    s.add_argument('--heartbeat-timeout', type=float, default=300.0)
    s.add_argument('--uncertain-settle', type=float, default=3600.0,
                   help='seconds an unseen lock with an unknown request outcome stays reserved before reconcile '
                   'settles it as abandoned; must exceed the lock timeout plus any server delay (default 3600)')

    s = a.add_parser('register-principal'); s.add_argument('name'); s.add_argument('--kind', choices=['agent', 'human'], required=True)
    s.add_argument('--git-account', help='LFS lock owner name of this principal')
    s = a.add_parser('register-machine'); s.add_argument('id', help='opaque machine ID (no hostnames)')
    s = a.add_parser('register-workspace'); s.add_argument('id'); s.add_argument('--machine', required=True)
    s = a.add_parser('heartbeat'); s.add_argument('workspace')

    s = a.add_parser('task', help='create, show or update tasks; record pushes, merges and cancellations')
    t = s.add_subparsers(dest='task_action', required=True)
    c = t.add_parser('create'); c.add_argument('id'); c.add_argument('--title', required=True)
    c.add_argument('--workspace', required=True); c.add_argument('--target', default='main')
    c.add_argument('--branch'); c.add_argument('--base', help='base revision (full commit ID)')
    c.add_argument('--depends-on', action='append', default=[]); c.add_argument('--reads', action='append', default=[],
                                                                                help='read dependency path or prefix/ pinned at base')
    c = t.add_parser('show'); c.add_argument('id')
    c = t.add_parser('update'); c.add_argument('id'); c.add_argument('--status', choices=['open', 'in_progress', 'review'])
    c.add_argument('--branch'); c.add_argument('--base'); c.add_argument('--note')
    c = t.add_parser('push'); c.add_argument('id'); c.add_argument('--revision', required=True)
    c.add_argument('--failed', action='store_true'); c.add_argument('--detail')
    c = t.add_parser('merged', help='record the merge, then unlock released locks'); c.add_argument('id')
    c.add_argument('--revision', required=True)
    c = t.add_parser('cancel'); c.add_argument('id'); c.add_argument('--disposition', choices=['preserved', 'discarded'], required=True)
    c.add_argument('--note')

    s = a.add_parser('request', help='reserve scopes/paths (pending); --acquire also locks and activates')
    s.add_argument('--task', required=True); s.add_argument('--workspace', required=True)
    s.add_argument('--scope', action='append', default=[]); s.add_argument('--lock-path', action='append', default=[])
    s.add_argument('--path', action='append', default=[]); s.add_argument('--prefix', action='append', default=[])
    s.add_argument('--base'); s.add_argument('--acquire', action='store_true')
    s = a.add_parser('extend'); s.add_argument('claim', type=int)
    s.add_argument('--lock-path', action='append', default=[]); s.add_argument('--path', action='append', default=[])
    s.add_argument('--acquire', action='store_true')
    s = a.add_parser('acquire', help='lock needed LFS paths with your own credentials, then activate'); s.add_argument('claim', type=int)
    s = a.add_parser('show'); s.add_argument('claim', type=int)
    s = a.add_parser('cancel'); s.add_argument('claim', type=int)
    s.add_argument('--disposition', choices=['preserved', 'discarded'], required=True); s.add_argument('--note')
    s = a.add_parser('unlock', help='retry unlocking locks the service marked releasing'); s.add_argument('claim', type=int)
    s = a.add_parser('recover', help='coordinator: transfer/release a claim or resolve one lock')
    s.add_argument('claim', type=int); s.add_argument('--action', choices=['transfer', 'release', 'resolve'], required=True)
    s.add_argument('--reason', required=True); s.add_argument('--old-writer-stopped', action='store_true')
    s.add_argument('--preserved', help='where the old writer\'s work was preserved (branch, commit or archive)')
    s.add_argument('--to-workspace'); s.add_argument('--path'); s.add_argument('--decision', choices=['adopt', 'foreign'])
    s.add_argument('--lock-id')
    a.add_parser('reconcile', help='compare recorded locks with the remote; required after every service start')
    s = a.add_parser('events'); s.add_argument('--after', type=int, default=0); s.add_argument('--limit', type=int, default=100)
    a.add_parser('status')

    for name, text in (('check', 'fail-closed check that protected changes are covered by the task\'s active claim'),
                       ('premerge', 'final pre-merge check of the whole branch against the target, with live lock verification')):
        s = a.add_parser(name, help=text)
        s.add_argument('--task', help='task ID (default: ATELIER_CLAIMS_TASK or `claims use-task`)')
        s.add_argument('--protect', action='append', default=[], help='extra protected glob (also git config atelier.claims.protect)')
        if name == 'check':
            mode = s.add_mutually_exclusive_group(required=True)
            mode.add_argument('--paths', nargs='+'); mode.add_argument('--staged', action='store_true')
            mode.add_argument('--range', help='git diff range such as origin/main...HEAD')
            s.add_argument('--stage', choices=['commit', 'publish'], default='commit')
        else:
            s.add_argument('--remote', default='origin'); s.add_argument('--head', default='HEAD')
    s = a.add_parser('use-task', help='set the task the cooperative pre-commit/pre-push hooks check in this checkout')
    g = s.add_mutually_exclusive_group(required=True); g.add_argument('task', nargs='?'); g.add_argument('--clear', action='store_true')


def _token(args):
    from .service import read_token
    return read_token(args.token_file)


def _client(args):
    from .client import Client
    if not args.actor:
        raise SystemExit('claims: set --actor, ATELIER_CLAIMS_ACTOR or ATELIER_AGENT')
    return Client(args.url, _token(args), args.actor)


class _Offline:
    def __init__(self, reason):
        self.reason = reason

    def call(self, method, path, body=None):
        from .client import Unreachable
        raise Unreachable(self.reason)


def _locker(args):
    from .remote import client_locker
    return client_locker(_toplevel(args.repo), args.lfs_remote)


def _toplevel(repo):
    return subprocess.run(['git', '-C', repo, 'rev-parse', '--show-toplevel'], capture_output=True, text=True,
                          check=True).stdout.strip()


def _task_file(repo):
    out = subprocess.run(['git', '-C', repo, 'rev-parse', '--absolute-git-dir'], capture_output=True, text=True, check=True)
    return Path(out.stdout.strip()) / 'atelier-claims-task'


def _task(args):
    if args.task:
        return args.task
    if os.environ.get('ATELIER_CLAIMS_TASK'):
        return os.environ['ATELIER_CLAIMS_TASK']
    path = _task_file(args.repo)
    return path.read_text().strip() if path.exists() else None


def _patterns(args):
    out = subprocess.run(['git', '-C', args.repo, 'config', '--get-all', 'atelier.claims.protect'], capture_output=True, text=True)
    return list(args.protect) + out.stdout.split()


def _print(value):
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0


def serve(args):
    from .remote import GitCli, GitLfsCli, LfsHttp
    from .service import Service
    from .store import Store
    token = _token(args)
    if args.lfs_url:
        auth = os.environ.get('ATELIER_CLAIMS_LFS_AUTH')
        lfs = LfsHttp(args.lfs_url, {'Authorization': auth} if auth else {})
    else:
        lfs = GitLfsCli(args.lfs_repo)
    store = Store(args.db, GitCli(args.git_repo, args.git_remote), lfs, coordinators=args.coordinator,
                  heartbeat_timeout=args.heartbeat_timeout, uncertain_settle=args.uncertain_settle)
    service = Service(store, token, args.bind, args.port)
    print(f'claims service listening on {service.url} (reconciling: run `atelier claims reconcile`)', flush=True)
    try:
        service.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        service.server.server_close()
        store.close()
    return 0


def run_check(args, client, task, changes, stage, cached):
    from .client import check
    problems = check(client, _toplevel(args.repo), task, changes, _patterns(args), stage=stage, cached=cached)
    for problem in problems:
        print('claims: ' + problem, file=sys.stderr)
    if problems:
        print(f'claims: {len(problems)} protected changes are not covered by task {task!r} (stage {stage})', file=sys.stderr)
        return 1
    print(f'claims: ok ({len(changes)} changed paths, stage {stage})')
    return 0


def use_task(args):
    """Set this checkout's claims task; the repository hooks check only checkouts that set one."""
    path = _task_file(args.repo)
    if args.clear:
        path.unlink(missing_ok=True)
        print(f'cleared {path}')
    else:
        path.write_text(args.task + '\n')
        print(f'{path}: {args.task}')
    return 0


def main(args):
    from .client import AcquireFailed, Refused, Unreachable, acquire, range_changes, release_locks, staged_changes, Change
    action = args.claims_action
    if action == 'serve':
        return serve(args)
    if action == 'use-task':
        return use_task(args)
    try:
        if action == 'check':
            task = _task(args)
            try:
                client = _client(args)
            except SystemExit as error:  # no actor/token: only unprotected changes can pass
                client = _Offline(str(error))
            repo = _toplevel(args.repo)
            if args.staged:
                changes = staged_changes(repo)
            elif args.range:
                changes = range_changes(repo, args.range)
            else:
                changes = [Change('M', p) for p in args.paths]
            return run_check(args, client, task, changes, args.stage, cached=args.staged)
        client = _client(args)
        if action == 'premerge':
            task = _task(args)
            view = client.call('GET', f'/tasks/{task}')
            for claim in view['claims']:
                if claim['state'] == 'active':
                    client.call('POST', f'/claims/{claim["id"]}/activate')  # live re-verification of every lock
            spec = f'{args.remote}/{view["target_branch"]}...{args.head}'
            return run_check(args, client, task, range_changes(_toplevel(args.repo), spec), 'publish', cached=False)
        if action == 'register-principal':
            return _print(client.call('POST', '/principals', {'name': args.name, 'kind': args.kind, 'git_account': args.git_account}))
        if action == 'register-machine':
            return _print(client.call('POST', '/machines', {'id': args.id}))
        if action == 'register-workspace':
            return _print(client.call('POST', '/workspaces', {'id': args.id, 'principal': args.actor, 'machine': args.machine}))
        if action == 'heartbeat':
            return _print(client.call('POST', f'/workspaces/{args.workspace}/heartbeat'))
        if action == 'task':
            return _task_action(args, client)
        if action == 'request':
            view = client.call('POST', '/claims', {'task': args.task, 'workspace': args.workspace, 'scopes': args.scope,
                                                   'lock_paths': args.lock_path, 'paths': args.path,
                                                   'prefixes': args.prefix, 'base_revision': args.base})
            return _print(acquire(client, view['id'], _locker(args)) if args.acquire else view)
        if action == 'extend':
            view = client.call('POST', f'/claims/{args.claim}/extend', {'lock_paths': args.lock_path, 'paths': args.path})
            return _print(acquire(client, args.claim, _locker(args)) if args.acquire else view)
        if action == 'acquire':
            return _print(acquire(client, args.claim, _locker(args)))
        if action == 'show':
            return _print(client.call('GET', f'/claims/{args.claim}'))
        if action == 'cancel':
            view = client.call('POST', f'/claims/{args.claim}/cancel', {'disposition': args.disposition, 'note': args.note})
            return _print(release_locks(client, view, _locker(args)))
        if action == 'unlock':
            return _print(release_locks(client, client.call('GET', f'/claims/{args.claim}'), _locker(args)))
        if action == 'recover':
            return _print(client.call('POST', f'/claims/{args.claim}/recover', {
                'action': args.action, 'reason': args.reason, 'old_writer_stopped': args.old_writer_stopped,
                'preserved': args.preserved, 'to_workspace': args.to_workspace, 'path': args.path,
                'decision': args.decision, 'lock_id': args.lock_id}))
        if action == 'reconcile':
            return _print(client.call('POST', '/reconcile'))
        if action == 'events':
            return _print(client.call('GET', f'/events?after={args.after}&limit={args.limit}'))
        if action == 'status':
            return _print(client.call('GET', '/status'))
    except AcquireFailed as error:
        print(f'claims: {error}', file=sys.stderr)
        return 1
    except (Refused, Unreachable) as error:
        print(f'claims: {error}', file=sys.stderr)
        payload = getattr(error, 'payload', None)
        if payload:
            print(json.dumps(payload, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    raise SystemExit(f'unknown claims action {action}')


def _task_action(args, client):
    from .client import release_locks
    t = args.task_action
    if t == 'create':
        return _print(client.call('POST', '/tasks', {'id': args.id, 'title': args.title, 'workspace': args.workspace,
                                                     'target_branch': args.target, 'branch': args.branch,
                                                     'base_revision': args.base, 'depends_on': args.depends_on,
                                                     'reads': args.reads}))
    if t == 'show':
        return _print(client.call('GET', f'/tasks/{args.id}'))
    if t == 'update':
        return _print(client.call('POST', f'/tasks/{args.id}/update', {'status': args.status, 'branch': args.branch,
                                                                       'base_revision': args.base, 'note': args.note}))
    if t == 'push':
        return _print(client.call('POST', f'/tasks/{args.id}/push', {'revision': args.revision, 'ok': not args.failed,
                                                                     'detail': args.detail}))
    if t == 'merged':
        view = client.call('POST', f'/tasks/{args.id}/merged', {'revision': args.revision})
        view['claims'] = [release_locks(client, claim, _locker(args)) for claim in view['claims']]
        return _print(view)
    if t == 'cancel':
        view = client.call('POST', f'/tasks/{args.id}/cancel', {'disposition': args.disposition, 'note': args.note})
        view['claims'] = [release_locks(client, claim, _locker(args)) for claim in view['claims']]
        return _print(view)
    raise SystemExit(f'unknown task action {t}')
