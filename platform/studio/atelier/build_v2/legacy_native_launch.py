"""One original batch launch intent; no process owner, scheduler or product key encoder."""
from pathlib import Path
from .legacy_native_action import _NativeRuntime, _ORIGIN, worker_argv

# Whole guarded work cap, distinct from the original between-action batch budget.
NATIVE_WORK_SECONDS = 600.


class NativeBatchLaunch:
    """One original Session's closed launch preparation, not a process owner.

    Actual run/monitor/admission/return still belong to build_source and guarded.run.
    The fixed issuer supplies the qualified member/runtime map before Session.write_plan.
    """
    def __init__(self, authority, session, runtimes):
        import hashlib
        self.authority, self.session = authority, session
        self.members = [step.name for step, _, _ in session.candidates]
        if (not 0 < len(self.members) <= 63 or len(self.members) != len(set(self.members))
                or any(name not in runtimes for name in self.members)):
            raise ValueError('native batch members differ from the qualified original candidates')
        code = set()
        for name in self.members:
            runtime = runtimes[name]
            if type(runtime) is not _NativeRuntime or runtime._origin is not _ORIGIN:
                raise ValueError('native member has no fixed selected runtime observation')
            code.update(runtime.files)
        self.files = tuple(sorted(code))
        self.relative = 'build/build-v2/legacy-host/' + authority.nonce + '/guards/native-' + session.nonce
        self.directory = authority.checkout / self.relative
        self.context = self.directory / 'native-context.json'
        self.invocation = hashlib.sha256((authority.nonce + ':native:' + session.nonce).encode()).hexdigest()[:32]
        self.attempt = 'native-' + authority.nonce + '-' + session.nonce
        self.logical = session.guard

    def prepared(self, ctx, command):
        """@cc [owner:fontanierh,label:correctness;safety] native-shared-original-launch-intent
        Complete original member identities, actual argv/environment/resources and one
        absolute queue/work bound MUST be recorded before creating worker context or
        launching. The SAME work bound MUST drive the original guard; native600s and
        an earlier positive command limit MUST NOT inherit texture120s. Original
        Batch.max_seconds240 between-action policy MUST remain unchanged. Checkout
        custody MUST reach only the existing monitor, never worker pass_fds. Normal
        guard return/actual raw receipts remain the authority; this object MUST NOT
        manufacture cleanup or command success. See test_build_v2_legacy_native_action.
        """
        from contextlib import contextmanager
        @contextmanager
        def owned():
            import hashlib
            import json
            import os
            from atelier import build_audit
            from atelier.build_source import environment
            from atelier.build_v2.legacy_client import authority_now_ns
            from atelier.harness import capacity_runtime
            from atelier.harness.capacity_protocol import boot_id, process_start
            from atelier.harness.safety.launch_ownership import prepare
            a = self.authority
            settings = capacity_runtime.read_configuration(capacity_runtime.DEFAULT_CONFIG)
            if settings.get('schema') != 2 or 'ATELIER_CAPACITY_CLIENT' in os.environ:
                raise ValueError('native provider requires fresh automatic full-capacity admission')
            config = {'version': 1, 'source': a.manifest['source_digest'],
                      'issuer': a.manifest['issuer_digest'],
                      'request': a.manifest['scheduler_request']['digest'],
                      'binary': str(Path(ctx.blender).resolve()),
                      'installation': list(map(str, build_audit.installation(command))),
                      'code_files': list(self.files),
                      'atomic_temporary': str(self.session.folder / 'atomic-tmp')}
            raw = (json.dumps(config, sort_keys=True, separators=(',', ':')) + '\n').encode()
            capture = Path(a.manifest['distribution']) / 'platform/studio/atelier/build_v2/controller_client.py'
            capture_raw = dict(a.files)['platform/studio/atelier/build_v2/controller_client.py']
            startup = a.checkout / ('build/build-v2/legacy-host/' + a.nonce + '/startup.json')
            self.argv = worker_argv(command, ctx, startup=startup, specification=self.context,
                                    specification_digest=hashlib.sha256(raw).hexdigest(),
                                    capture_file=capture, capture_digest=hashlib.sha256(capture_raw).hexdigest())
            self.launch_context = prepare(environment(command.env))
            self.environment = dict(self.launch_context.environment)
            now = authority_now_ns()
            original_timeout = getattr(command, 'timeout', 0.)
            self.work_seconds = min(NATIVE_WORK_SECONDS, original_timeout) if original_timeout > 0 else NATIVE_WORK_SECONDS
            self.execution_ns = int(self.work_seconds * 1_000_000_000)
            self.queue_deadline_ns = min(now + 1800 * 1_000_000_000,
                                         a.manifest['work_deadline_ns'] - self.execution_ns)
            if self.queue_deadline_ns <= now:
                raise ValueError('native work and queue do not fit the original authority deadline')
            launch = {'scheduler': {'pid': os.getpid(), 'boot': boot_id(), 'started': str(process_start(os.getpid()))},
                      'program': self.argv[0], 'args': self.argv[1:],
                      'environment_digest': hashlib.sha256(json.dumps(self.environment, sort_keys=True,
                                                                      separators=(',', ':')).encode()).hexdigest(),
                      'kind': 'job', 'threads': command.threads, 'memory_bytes': 10 * 1024**3,
                      'execution_ns': self.execution_ns, 'queue_deadline_ns': self.queue_deadline_ns}
            a.client.request({'type': 'begin_attempt', 'attempt': {'id': self.attempt,
                'members': [*a.metadata_scopes, *self.members], 'execution': {'kind': 'guarded',
                'directory': self.relative, 'invocation': self.invocation, 'launch': launch}, 'guard': None}})
            # No context/report directory exists before its durable launch intent.
            self.directory.mkdir(parents=True, mode=0o700)
            fd = os.open(self.context, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            self.session.guard = self.directory  # Original polling reads the ACTUAL report.
            a.guard_directory, a.guard_relative = self.directory, self.relative
            a.invocation, a.attempt, a.returned = self.invocation, self.attempt, None
            yield self.argv, tuple(self.environment.items()), ()
        return owned()

    def guard_options(self, argv, environment, kind):
        from atelier.build_v2.legacy_client import authority_now_ns
        if list(argv) != self.argv or environment != self.environment or kind != 'job':
            raise ValueError('native command differs from its durable original launch intent')
        remaining = (self.queue_deadline_ns - authority_now_ns()) / 1e9
        if remaining <= 0:
            raise ValueError('recorded native queue deadline expired before admission')
        return {'custody_fds': tuple(self.authority.custody.values()), 'aggregate_tree': True,
                'launch_context': self.launch_context, 'invocation_id': self.invocation,
                'logical_folder': self.logical, 'queue_seconds': remaining}
