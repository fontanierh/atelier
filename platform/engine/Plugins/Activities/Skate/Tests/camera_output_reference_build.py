"""Guard-only whole original camera output/publication owner proof.

Production source bytes remain exact prefixes; additions read private state or
supply explicit wire inputs to the actual owners. No numerical producer stub.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from collections import defaultdict
import re
import camera_probe_schema as schema
from camera_reference_build import frozen_sources
from session_parity import PLUGIN,digest
PUBLICATION_TYPES=('CameraStateOutput','CameraAnimationOutput','CameraAirOutput','CameraOffboardOutput','CameraGrindOutput','CameraEventsOutput','CameraPreferences','CameraPublicationInputs')

def output_schemas(read):
    values=schema.schemas(read);path='crates/skate-host/src/camera/publication.rs';source=read(path)
    for name in PUBLICATION_TYPES:
        item=schema.declaration(source,name);item.update(source=path,source_sha256=hashlib.sha256(source.encode()).hexdigest());values[name]=item
    fixture=PLUGIN/'Tests/Reference/camera_output_fixture.rs';item=schema.declaration(fixture.read_text(),'CameraOwnerFixture');item.update(source='self-owned-wire-fixture',source_sha256=digest(fixture));values['CameraOwnerFixture']=item
    return values

def readable_types(values):
    wanted=schema.input_closure(values)|set(PUBLICATION_TYPES)|{'CameraOwnerFixture'};pending=list(wanted)
    while pending:
        for _,kind in values[pending.pop()]['fields']:
            for child in re.findall(r'\b[A-Z]\w*\b',kind):
                if child in values and child not in wanted:wanted.add(child);pending.append(child)
    return wanted

def build_output_probe(output, target):
    source, report = frozen_sources(output)
    observed = output / 'observed-source'
    if observed.exists():
        shutil.rmtree(observed)
    shutil.copytree(source, observed)
    values = output_schemas(lambda path: (source / path).read_text())
    additions = defaultdict(str)
    readable = readable_types(values)
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
    host_extensions['crates/skate-host/src/camera/runtime.rs'] += '\ninclude!("migration_camera_runtime_observer.rs");\npub(super) fn migration_output_observe(runtime:&CameraRuntime,output:&mut Vec<u8>,log:&crate::LogSink){observe_runtime(runtime,output,log); }\n'
    host_extensions['crates/skate-host/src/camera.rs'] += '\npub(crate) fn migration_output_observe(runtime:&CameraRuntime,output:&mut Vec<u8>,log:&crate::LogSink){runtime::migration_output_observe(runtime,output,log); }\n'
    host_extensions['crates/skate-host/src/skater_animation.rs'] += '\nimpl SkaterAnimation {pub(crate) fn migration_set_camera_fixture_flags(&mut self,flags:u32){self.state.flags=flags;}}\n'
    helper=(PLUGIN/'Tests/Reference/camera_output_observer.rs').read_text()
    fixture=(PLUGIN/'Tests/Reference/camera_output_fixture.rs').read_text()
    fixture_item=schema.declaration(fixture,'CameraOwnerFixture')
    assert helper.count('// @OWNER_FIXTURE@')==helper.count('// @OWNER_FIXTURE_READ@')==1
    host_extensions['crates/skate-host/src/physics.rs'] += '\n'+helper.replace('// @OWNER_FIXTURE@',fixture).replace('// @OWNER_FIXTURE_READ@',schema.rust_read(fixture_item,host=True))

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
    template = PLUGIN / 'Tests/Reference/camera_output_probe.rs'
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
name="camera-output-reference"
path="src/migration_probe.rs"
''')
    subprocess.run(['cargo', '+1.97.1', 'build', '--release', '--offline', '--jobs', '2',
                    '--manifest-path', str(cargo), '--target-dir', str(target.resolve()),
                    '--bin', 'camera-output-reference'], check=True)
    for relative, sha in report['original_source_sha256'].items():
        assert digest(source / relative) == sha, relative
        raw = (source / relative).read_bytes()
        assert (observed / relative).read_bytes()[:len(raw)] == raw, relative
    for relative, record in staged.items():
        original = host / relative
        raw = original.read_bytes()
        assert (crate / 'src' / relative).read_bytes()[:len(raw)] == raw
        assert digest(crate / 'src' / relative) == record['generated_sha256']
    binary = output / 'camera-output-reference'
    shutil.copy2(target.resolve() / 'release/camera-output-reference', binary)
    report.update(core_original_prefix_observers=core_extensions, staged_host_original_prefixes=staged,
                  field_schema=values, observation_module_sha256=digest(observer),
                  observer_helper_sha256=digest(helper), probe_sha256=digest(template),
                  binary_sha256=digest(binary), cargo_lock_sha256=digest(crate / 'Cargo.lock'),
                  compiler=subprocess.check_output(['rustc', '+1.97.1', '-vV'], text=True).strip(),
                  output_probe_helper_sha256=digest(PLUGIN/'Tests/Reference/camera_output_observer.rs'), fixture_declaration_sha256=digest(PLUGIN/'Tests/Reference/camera_output_fixture.rs'),
                  boundary='Entire unchanged original camera/publication.rs and physics/camera_output.rs, concrete GamePhysics/SkaterRuntime constructors and Ground output, full original CameraRuntime and real BoardWorld. Every production source retains its exact original prefix. Appended observers read private state; one explicitly named fixture setter writes the otherwise private actor flags. Self-owned fixture writes target actual completed owners, without replacing a producer. StaticWorld collect=0 is the unchanged source adapter. No executed method/callback is substituted. Global phase scheduling and preceding physics/input/scoring producers remain independent owners.')
    (output / 'reference-provenance.json').write_text(json.dumps(report, indent=2) + '\n')
    return binary, values
