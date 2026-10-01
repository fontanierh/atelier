"""Guard-only frozen camera build with byte-preserving observation extensions.

The archive remains immutable. A second generated workspace appends only field
observers to exact original prefixes; every original production method remains.
"""
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
from collections import defaultdict
import camera_probe_schema as schema
from session_parity import PLUGIN, REFERENCE_REVISION, digest


def frozen_sources(output):
    root = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], cwd=PLUGIN, text=True).strip())
    relative = (PLUGIN / 'ThirdParty/skate-runtime').relative_to(root).as_posix()
    revision = subprocess.check_output(['git', 'rev-parse', REFERENCE_REVISION], cwd=root, text=True).strip()
    archive = subprocess.check_output(['git', 'archive', f'{revision}:{relative}'], cwd=root)
    source = output / 'reference-source'
    if source.exists():
        shutil.rmtree(source)
    source.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        stream.extractall(source, filter='data')
    originals = {p.relative_to(source).as_posix(): digest(p) for p in sorted(source.rglob('*.rs'))}
    return source, dict(reference_revision=revision,
                        source_archive_sha256=hashlib.sha256(archive).hexdigest(),
                        original_source_sha256=originals)


def centered_modules(source):
    path = 'crates/skate-core/src/camera/shake.rs'
    raw = (source / path).read_text()
    start = raw.index('#[derive(Clone,Debug,PartialEq)]\npub struct ShakeSamples')
    end = raw.index('\n#[derive(Clone,Copy,Debug,PartialEq)]\npub struct ShakeSettings', start)
    centered = raw[start:end]
    assert centered.count('pub fn from_rows(') == 1
    assert 'landing_impulse' not in centered
    parse_path = 'crates/skate-host/src/camera/shake_data.rs'
    parse_raw = (source / parse_path).read_text()
    parse_start = parse_raw.index('pub(crate) fn parse(')
    parse = parse_raw[parse_start:]
    # Only these two exact original bodies execute in the export. Numerical
    # impact-response methods are irrelevant and not bound to placeholder APIs.
    report = []
    for name, text, original, begin, finish in (
            (path, centered, raw, start, end),
            (parse_path, parse, parse_raw, parse_start, len(parse_raw))):
        assert original[begin:finish] == text
        report.append(dict(source=name, source_sha256=hashlib.sha256(original.encode()).hexdigest(),
                           begin_byte=len(original[:begin].encode()), end_byte=len(original[:finish].encode()),
                           extracted_sha256=hashlib.sha256(text.encode()).hexdigest()))
    modules = 'mod centered_shake {\n' + centered + '\n}\n'
    modules += 'mod centered_shake_data {\nuse super::centered_shake::ShakeSamples;\n' + parse + '\n}\n'
    return modules, report


def build_data_probe(output, target):
    from reference_build import build_probe
    source, provenance = frozen_sources(output / 'export-source')
    modules, extracted = centered_modules(source)
    template = PLUGIN / 'Tests/Reference/camera_data_probe.rs'
    body = template.read_text()
    assert body.count('// @CENTERED_SHAKE_MODULES@') == 1
    generated = output / 'camera-data-probe.rs'
    generated.write_text(body.replace('// @CENTERED_SHAKE_MODULES@', modules))
    binary = build_probe(output / 'export-build', 'camera-data-reference', generated, target)
    report = dict(provenance, declaration_body_extractions=extracted,
                  template_sha256=digest(template), generated_probe_sha256=digest(generated),
                  boundary='Complete original StockShots constructor/ShotDatabase lookup. Exact original ShakeSamples declaration/from_rows and host parse bodies; no landing/shake-update calls occur in the data exporter and no numerical dependency stubs exist.')
    (output / 'camera-data-extraction-provenance.json').write_text(json.dumps(report, indent=2) + '\n')
    return binary


def build_runtime_probe(output, target):
    source, report = frozen_sources(output)
    observed = output / 'observed-source'
    if observed.exists():
        shutil.rmtree(observed)
    shutil.copytree(source, observed)
    values = schema.schemas(lambda path: (source / path).read_text())
    additions = defaultdict(str)
    readable = schema.input_closure(values)
    for item in values.values():
        if item['source'].startswith('crates/skate-core/'):
            additions[item['source']] += schema.rust_observe(item)
            if item['name'] in readable:
                additions[item['source']] += schema.rust_read(item)
    additions['crates/skate-core/src/lib.rs'] += '\npub mod migration_camera_observer;\n'
    observer = observed / 'crates/skate-core/src/migration_camera_observer.rs'
    observer.write_text(schema.RUST_OBSERVER)
    controller_path = 'crates/skate-core/src/graph/controller.rs'
    controller_source = (source / controller_path).read_text()
    for name in ('Frame', 'ActiveBehavior', 'Controller'):
        additions[controller_path] += schema.rust_observe(schema.declaration(controller_source, name))
    core_extensions = {}
    for relative, extension in additions.items():
        raw = (source / relative).read_bytes()
        generated = observed / relative
        generated.write_bytes(raw + extension.encode())
        assert generated.read_bytes()[:len(raw)] == raw
        core_extensions[relative] = dict(original_prefix_bytes=len(raw), original_prefix_sha256=digest(source / relative),
                                        appended_observer_sha256=hashlib.sha256(extension.encode()).hexdigest(),
                                        generated_sha256=digest(generated))
    crate = observed / 'atelier-host'
    host = source / 'crates/skate-host/src'
    host_extensions = defaultdict(str)
    for item in values.values():
        if item['source'].startswith('crates/skate-host/'):
            host_extensions[item['source']] += schema.rust_observe(item, host=True)
            if item['name'] in readable:
                host_extensions[item['source']] += schema.rust_read(item, host=True)
    host_extensions['crates/skate-host/src/camera/shot_data.rs'] += '''
impl skate_core::migration_camera_observer::Observe for StockShots {
    fn observe(&self,output:&mut Vec<u8>) {skate_core::migration_camera_observer::Observe::observe(&self.0,output);}
}
'''
    host_extensions['crates/skate-host/src/camera/graph.rs'] += '''
impl CameraGraph {
    pub(super) fn migration_observe(&self,output:&mut Vec<u8>) {
        use skate_core::migration_camera_observer::Observe;
        self.controller.observe(output);self.slow_motion.observe(output);
    }
    pub(super) fn migration_settings(&self)->SlowMotionSettings {self.slow_motion_settings}
    pub(super) fn migration_conditions(&self,manager:&CameraMan,subject:&ManagerSubject,
        physical:CameraGraphSubject,world:&CameraGraphEnvironment)->Vec<bool> {
        self.conditions.iter().map(|condition|condition.evaluate(manager,subject,physical,world)).collect()
    }
}
'''
    host_extensions['crates/skate-host/src/camera/runtime.rs'] += '\ninclude!("migration_camera_runtime_observer.rs");\n'
    host_extensions['crates/skate-host/src/camera.rs'] += '''
pub(crate) fn migration_camera_run(root:&std::path::Path,input:&mut crate::Input,
    output:&mut Vec<u8>,log:&crate::LogSink)->Result<(),String> {
    runtime::migration_run(root,input,output,log)
}
'''
    staged = {}
    for original in sorted(host.rglob('*.rs')):
        relative = original.relative_to(host)
        if relative.as_posix() in ('lib.rs', 'main.rs'):
            continue
        source_relative = original.relative_to(source).as_posix()
        raw = original.read_bytes()
        extension = host_extensions[source_relative].encode()
        destination = crate / 'src' / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw + extension)
        assert destination.read_bytes()[:len(raw)] == raw
        staged[relative.as_posix()] = dict(original_prefix_bytes=len(raw), original_prefix_sha256=digest(original),
                                          appended_observer_sha256=hashlib.sha256(extension).hexdigest(),
                                          generated_sha256=digest(destination))
    helper = PLUGIN / 'Tests/Reference/camera_runtime_observer.rs'
    shutil.copy2(helper, crate / 'src/camera/migration_camera_runtime_observer.rs')
    template = PLUGIN / 'Tests/Reference/camera_runtime_probe.rs'
    shutil.copy2(template, crate / 'src/migration_probe.rs')
    cargo = crate / 'Cargo.toml'
    cargo.write_text(cargo.read_text() + '''
skate-core={path="../crates/skate-core"}
skate-data={path="../crates/skate-data"}
skate-net={path="../crates/skate-net"}
half="2.7.1"
tracing-subscriber={version="0.3.23",features=["fmt"]}
bevy={version="0.19",default-features=false,features=["std","multi_threaded","bevy_log"]}
[[bin]]
name="camera-runtime-reference"
path="src/migration_probe.rs"
''')
    subprocess.run(['cargo', '+1.97.1', 'build', '--release', '--offline', '--jobs', '2',
                    '--manifest-path', str(cargo), '--target-dir', str(target.resolve()),
                    '--bin', 'camera-runtime-reference'], check=True)
    for relative, sha in report['original_source_sha256'].items():
        assert digest(source / relative) == sha, relative
        raw = (source / relative).read_bytes()
        assert (observed / relative).read_bytes()[:len(raw)] == raw, relative
    for relative, record in staged.items():
        original = host / relative
        raw = original.read_bytes()
        assert (crate / 'src' / relative).read_bytes()[:len(raw)] == raw
        assert digest(crate / 'src' / relative) == record['generated_sha256']
    binary = output / 'camera-runtime-reference'
    shutil.copy2(target.resolve() / 'release/camera-runtime-reference', binary)
    report.update(core_original_prefix_observers=core_extensions, staged_host_original_prefixes=staged,
                  field_schema=values, observation_module_sha256=digest(observer),
                  observer_helper_sha256=digest(helper), probe_sha256=digest(template),
                  binary_sha256=digest(binary), cargo_lock_sha256=digest(crate / 'Cargo.lock'),
                  compiler=subprocess.check_output(['rustc', '+1.97.1', '-vV'], text=True).strip(),
                  boundary='Complete original CameraRuntime load/advance, SubjectPublisher, CameraMan, all core camera methods, stock factories/controller and real BoardWorld queries. Every compiled production source retains its exact original prefix. Appended observers read private state only. The only supplied callback is the original mandatory moving-obstacle publication boundary, whose exact calls and returned records are observed. No production methods or executed interfaces are stubbed or omitted.')
    (output / 'reference-provenance.json').write_text(json.dumps(report, indent=2) + '\n')
    return binary, values
