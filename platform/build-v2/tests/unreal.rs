//! T0 tests of the Unreal worker's controller side: context identity and validation, the scratch
//! project and its hash receipt, the worker command line and the two evidence files. No Unreal.
use atelier_build_v2::store::ObjectStore;
use atelier_build_v2::unreal::*;
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::fs;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};

static SERIAL: AtomicU64 = AtomicU64::new(0);

struct Workspace(PathBuf);
impl Workspace {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "atelier-v2-unreal-{}-{}",
            std::process::id(),
            SERIAL.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir_all(&path).unwrap();
        Self(path.canonicalize().unwrap())
    }
    fn path(&self, relative: &str) -> PathBuf {
        self.0.join(relative)
    }
    fn write(&self, relative: &str, bytes: &[u8]) -> PathBuf {
        let path = self.path(relative);
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(&path, bytes).unwrap();
        path
    }
}
impl Drop for Workspace {
    fn drop(&mut self) {
        // Unlock anything a test left read-only, then remove it.
        let _ = std::process::Command::new("chmod")
            .args(["-R", "u+w"])
            .arg(&self.0)
            .status();
        let _ = fs::remove_dir_all(&self.0);
    }
}

/// A restored editor compile and the worker plugin, as produced folders.
fn produced(space: &Workspace) -> (PathBuf, PathBuf) {
    space.write(
        "editor/Binaries/Mac/libUnrealEditor-AtelierImport.dylib",
        b"module bytes",
    );
    space.write(
        "editor/Binaries/Mac/UnrealEditor.modules",
        b"{\"BuildId\": \"b1\"}",
    );
    space.write(
        "plugins/AtelierBuildWorker/AtelierBuildWorker.uplugin",
        b"{\"Modules\": []}",
    );
    space.write(
        "plugins/AtelierBuildWorker/Binaries/Mac/libUnrealEditor-AtelierBuildWorker.dylib",
        b"plugin bytes",
    );
    // Sources and intermediates beside the binaries are never cloned.
    space.write("plugins/AtelierBuildWorker/Source/Worker.cpp", b"// source");
    (
        space.path("editor/Binaries/Mac"),
        space.path("plugins/AtelierBuildWorker"),
    )
}

/// The repository's Unreal worker script.
fn repo_worker() -> PathBuf {
    std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../studio/atelier/build_v2/unreal_worker.py")
        .canonicalize()
        .unwrap()
}

/// A copy of the worker and its protocol module under `worker/`, to change in a test.
fn copied_worker(space: &Workspace) -> PathBuf {
    let source = repo_worker();
    let script = space.write("worker/unreal_worker.py", &fs::read(&source).unwrap());
    space.write(
        "worker/protocol.py",
        &fs::read(source.with_file_name("protocol.py")).unwrap(),
    );
    script
}

fn c_worker_files(context: &UnrealContext) -> std::collections::BTreeMap<String, Vec<u8>> {
    context.worker.files().clone()
}

/// The persistent DDC folder of the store at `store/` for `build_id`.
fn ddc(space: &Workspace, build_id: &str) -> UnrealDdc {
    UnrealDdc::open(&ObjectStore::open(space.path("store")).unwrap(), build_id).unwrap()
}

/// An installed engine plugin at `Epic Games/UE/Engine/Plugins/<name>`, with its identity.
fn engine_plugin(space: &Workspace, name: &str) -> Plugin {
    let dir = space.path(&format!("Epic Games/UE/Engine/Plugins/{name}"));
    if !dir.exists() {
        space.write(
            &format!("Epic Games/UE/Engine/Plugins/{name}/{name}.uplugin"),
            b"{}",
        );
        space.write(
            &format!(
                "Epic Games/UE/Engine/Plugins/{name}/Binaries/Mac/libUnrealEditor-{name}.dylib"
            ),
            name.as_bytes(),
        );
    }
    Plugin {
        name: name.into(),
        identity: tree_identity(&dir, Some(name)).unwrap(),
        dir,
    }
}

fn context(space: &Workspace) -> UnrealContext {
    let (editor, plugin) = produced(space);
    UnrealContext {
        // Like the installed engine, the root holds a space: it is only ever the program path.
        engine_root: space.path("Epic Games/UE"),
        build_id: "5.8-build".into(),
        editor: Binaries {
            identity: tree_identity(&editor, None).unwrap(),
            dir: editor,
        },
        modules: vec![Module {
            name: "AtelierImport".into(),
            kind: "UncookedOnly".into(),
            loading_phase: "Default".into(),
        }],
        engine_plugins: vec![
            engine_plugin(space, "PythonScriptPlugin"),
            engine_plugin(space, "Interchange"),
        ],
        plugins: vec![Plugin {
            name: WORKER_PLUGIN.into(),
            identity: tree_identity(&plugin, Some(WORKER_PLUGIN)).unwrap(),
            dir: plugin,
        }],
        settings: vec!["-ForceDPCVars=r.GenerateMeshDistanceFields=0".into()],
        ddc: ddc(space, "5.8-build"),
        worker: UnrealWorkerBundle::read(repo_worker().parent().unwrap()).unwrap(),
    }
}

#[test]
fn the_profile_ignores_locations_and_follows_every_identity_field() {
    let space = Workspace::new();
    let base = context(&space);
    let mut moved = base.clone();
    moved.engine_root = PathBuf::from("/elsewhere/UE_5.8");
    moved.editor.dir = PathBuf::from("/restored/elsewhere");
    assert_eq!(
        moved.profile(),
        base.profile(),
        "locations are not identity"
    );
    let mut reordered = base.clone();
    reordered.engine_plugins.reverse();
    assert_eq!(
        reordered.profile(),
        base.profile(),
        "engine plugins are a set"
    );

    let mut changes: Vec<UnrealContext> = vec![];
    let mut change = |edit: &dyn Fn(&mut UnrealContext)| {
        let mut changed = base.clone();
        edit(&mut changed);
        changes.push(changed);
    };
    change(&|c| c.build_id = "5.8-other".into());
    change(&|c| c.editor.identity = "1".repeat(64));
    change(&|c| c.modules[0].loading_phase = "PostEngineInit".into());
    let paper = engine_plugin(&space, "Paper2D");
    change(&|c| c.engine_plugins.push(paper.clone()));
    change(&|c| c.engine_plugins[0].identity = "3".repeat(64));
    let mut edited = c_worker_files(&base);
    edited.insert("protocol.py".into(), b"# another protocol".to_vec());
    let edited = UnrealWorkerBundle::from_files(edited).unwrap();
    change(&|c| c.worker = edited.clone());
    change(&|c| c.plugins[0].identity = "2".repeat(64));
    change(&|c| c.settings.push("-ini:Engine:[Core.Log]:Global=Log".into()));
    let other_store = space.path("other-store/unreal-ddc/5.8-build");
    change(&|c| c.ddc.dir = other_store.clone());
    let mut profiles: BTreeSet<String> = changes.iter().map(UnrealContext::profile).collect();
    profiles.insert(base.profile());
    assert_eq!(
        profiles.len(),
        10,
        "every identity field separates sessions"
    );
    assert!(base.profile().starts_with("unreal-"));
}

#[test]
fn contexts_refuse_what_a_session_cannot_load_honestly() {
    let space = Workspace::new();
    let base = context(&space);
    base.validate().unwrap();
    let refused = |edit: &dyn Fn(&mut UnrealContext), why: &str| {
        let mut changed = base.clone();
        edit(&mut changed);
        let error = changed.validate().unwrap_err();
        assert!(error.to_string().contains(why), "{why}: {error}");
    };
    refused(
        &|c| c.engine_root = PathBuf::from("relative/UE"),
        "absolute",
    );
    // The engine root is only the program path, never Unreal command-line text: spaces are fine.
    let mut spaced = base.clone();
    spaced.engine_root = PathBuf::from("/opt/Epic Games/UE");
    spaced.validate().unwrap();
    refused(&|c| c.build_id.clear(), "BuildId");
    refused(&|c| c.editor.identity = "not-a-digest".into(), "sha256");
    let mut engine_only = base.clone();
    engine_only.modules.clear();
    engine_only.validate().unwrap();
    refused(&|c| c.modules.push(c.modules[0].clone()), "twice");
    refused(&|c| c.plugins.clear(), WORKER_PLUGIN);
    refused(
        &|c| {
            let mut worker = c.plugins[0].clone();
            worker.dir = PathBuf::from("/engine/Plugins/AtelierBuildWorker");
            c.engine_plugins.push(worker)
        },
        "repeated",
    );
    refused(
        &|c| c.engine_plugins[0].identity = "not-a-digest".into(),
        "engine plugin",
    );
    refused(
        &|c| c.settings.push("-ExecCmds=quit".into()),
        "not a declared",
    );
    refused(
        &|c| c.settings.push("-ini:Engine:[A]:B=has space".into()),
        "not a declared",
    );
    refused(&|c| c.build_id = "5.8-other".into(), "DDC folder");
    refused(
        &|c| c.ddc.dir = c.ddc.dir.parent().unwrap().join("..").join("5.8-build"),
        "DDC folder",
    );
}

#[test]
fn the_ddc_folder_persists_per_engine_and_its_flags_and_graph_are_session_identity() {
    let space = Workspace::new();
    let store = ObjectStore::open(space.path("store")).unwrap();
    let first = UnrealDdc::open(&store, "5.8-build").unwrap();
    assert_eq!(
        first.dir,
        store.root().join("unreal-ddc/5.8-build"),
        "under the store root, keyed by the engine BuildId"
    );
    fs::write(first.dir.join("cached"), b"derived").unwrap();
    let again = UnrealDdc::open(&store, "5.8-build").unwrap();
    assert_eq!(again, first);
    assert_eq!(
        fs::read(again.dir.join("cached")).unwrap(),
        b"derived",
        "opening never empties it"
    );
    let other = UnrealDdc::open(&store, "5.8 other/build").unwrap();
    assert_ne!(other.dir, first.dir, "another engine gets its own folder");
    assert_eq!(other.dir.parent(), first.dir.parent());
    assert_eq!(
        first.graph_argument().unwrap(),
        format!(
            "-DDC=(InstalledEnginePak,V2Local=(Type=FileSystem,Path={}))",
            first.dir.display()
        )
    );
    let spaced = ObjectStore::open(space.path("with space")).unwrap();
    assert!(
        UnrealDdc::open(&spaced, "5.8-build").is_err(),
        "not command-line text"
    );

    // The flags, the graph and the folder are hashed into the profile, so a change to any of them is
    // a new session and never a reuse of an old one.
    let context = context(&space);
    let mut arguments: Vec<String> = DDC_FLAGS.iter().map(|flag| flag.to_string()).collect();
    arguments.push(context.ddc.graph_argument().unwrap());
    assert_eq!(context.identity()["ddc"], serde_json::json!(arguments));
    let digest = |identity: &serde_json::Value| {
        format!(
            "unreal-{:x}",
            Sha256::digest(identity.to_string().as_bytes())
        )
    };
    assert_eq!(digest(&context.identity()), context.profile());
    let mut without_flag = context.identity();
    without_flag["ddc"].as_array_mut().unwrap().remove(0);
    let mut other_graph = context.identity();
    other_graph["ddc"][2] = "-DDC=(InstalledEnginePak,ZenLocal)".into();
    for changed in [without_flag, other_graph] {
        assert_ne!(digest(&changed), context.profile());
    }
}

#[test]
fn a_worker_bundle_freezes_only_regular_files_and_never_follows_or_blocks() {
    let space = Workspace::new();
    let source = repo_worker();
    let frozen = |protocol: &dyn Fn(&std::path::Path)| {
        let dir = space.path(&format!(
            "bundle-{}",
            SERIAL.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir_all(&dir).unwrap();
        fs::copy(&source, dir.join("unreal_worker.py")).unwrap();
        protocol(&dir.join("protocol.py"));
        UnrealWorkerBundle::read(&dir)
    };
    let regular = frozen(&|path| {
        fs::copy(source.with_file_name("protocol.py"), path).unwrap();
    })
    .unwrap();
    assert_eq!(
        regular.digest(),
        UnrealWorkerBundle::read(source.parent().unwrap())
            .unwrap()
            .digest()
    );
    // A leaf already substituted by a link is never followed, even to a valid protocol module.
    let linked = frozen(&|path| {
        std::os::unix::fs::symlink(source.with_file_name("protocol.py"), path).unwrap();
    });
    assert!(linked.is_err());
    // A FIFO with no writer is refused at once instead of blocking the read.
    let started = std::time::Instant::now();
    let fifo = frozen(&|path| {
        let name = std::ffi::CString::new(path.to_str().unwrap()).unwrap();
        assert_eq!(unsafe { libc::mkfifo(name.as_ptr(), 0o644) }, 0);
    });
    let error = fifo.unwrap_err();
    assert!(error.to_string().contains("not a regular file"), "{error}");
    assert!(started.elapsed() < std::time::Duration::from_secs(5));
}

#[test]
fn the_ddc_policy_allows_only_the_v2_folder_and_the_engine_pak() {
    let policy = DdcPolicy {
        dir: "/store/unreal-ddc/5.8".into(),
        engine_pak: "/engine/Engine/DerivedDataCache/Compressed.ddp".into(),
    };
    let node = |kind: &str, path: &str| DdcNode {
        kind: kind.into(),
        path: path.into(),
    };
    let graph = |nodes: Vec<DdcNode>| DdcGraph {
        graph: "inline".into(),
        nodes,
    };
    let v2 = node("File System", "/store/unreal-ddc/5.8");
    let pak = node("Pak File", "/engine/Engine/DerivedDataCache/Compressed.ddp");
    assert_eq!(policy.problem(&graph(vec![pak.clone(), v2.clone()])), None);
    assert_eq!(
        policy.problem(&graph(vec![v2.clone(), node("Memory", "")])),
        None
    );
    for (bad, why) in [
        (vec![pak.clone()], "no cache node"),
        (vec![v2.clone(), node("Zen", "")], "Zen"),
        (
            vec![v2.clone(), node("File System", "/shared/DerivedDataCache")],
            "outside",
        ),
        (
            vec![
                v2.clone(),
                node("File System", "/store/unreal-ddc/5.8-other"),
            ],
            "outside",
        ),
        (
            vec![v2.clone(), node("File System", "relative/unreal-ddc/5.8")],
            "outside",
        ),
        (
            vec![
                v2.clone(),
                node("Pak File", "/project/DerivedDataCache/DDC.ddp"),
            ],
            "outside",
        ),
        (vec![v2.clone(), node("Http", "https://cache")], "outside"),
        (
            vec![v2.clone(), node("", "/store/unreal-ddc/5.8")],
            "outside",
        ),
    ] {
        let problem = policy.problem(&graph(bad)).expect(why);
        assert!(problem.contains(why), "{why}: {problem}");
    }
}

#[test]
fn a_tree_identity_names_paths_and_bytes_and_refuses_links() {
    let space = Workspace::new();
    let (editor, plugin) = produced(&space);
    let first = tree_identity(&editor, None).unwrap();
    assert_eq!(first, tree_identity(&editor, None).unwrap());
    fs::write(
        editor.join("libUnrealEditor-AtelierImport.dylib"),
        b"other bytes",
    )
    .unwrap();
    let second = tree_identity(&editor, None).unwrap();
    assert_ne!(first, second);
    fs::rename(
        editor.join("libUnrealEditor-AtelierImport.dylib"),
        editor.join("UnrealEditor-Renamed.dylib"),
    )
    .unwrap();
    assert_ne!(
        second,
        tree_identity(&editor, None).unwrap(),
        "paths are named"
    );
    // A plugin identity covers its descriptor and binaries, never its sources.
    let with_source = tree_identity(&plugin, Some(WORKER_PLUGIN)).unwrap();
    fs::write(plugin.join("Source/Worker.cpp"), b"// changed").unwrap();
    assert_eq!(
        with_source,
        tree_identity(&plugin, Some(WORKER_PLUGIN)).unwrap()
    );
    std::os::unix::fs::symlink("/etc/hosts", editor.join("link.dylib")).unwrap();
    assert!(tree_identity(&editor, None).is_err());
}

#[cfg(target_os = "macos")] // the scratch project needs APFS clones
#[test]
fn the_command_line_runs_the_worker_script_on_the_scratch_project_with_declared_settings() {
    let space = Workspace::new();
    let context = context(&space);
    let session = space.path("session");
    fs::create_dir(&session).unwrap();
    let scratch = ScratchProject::prepare(&session, &context).unwrap();
    let script = scratch.worker_script();
    let command = job_loop_command(&context, &scratch).unwrap();
    assert_eq!(
        command.program,
        space.path("Epic Games/UE/Engine/Binaries/Mac/UnrealEditor-Cmd")
    );
    let mut expected = vec![
        scratch.uproject().to_str().unwrap().to_string(),
        "-run=pythonscript".into(),
        format!("-script={}", script.display()),
    ];
    expected.extend(UNREAL_WORKER_FLAGS.iter().map(|flag| flag.to_string()));
    expected.push(format!("-UserDir={}", scratch.user_dir().display()));
    expected.extend(["-nowrite".to_string(), "-NoZenAutoLaunch".to_string()]);
    expected.push(format!(
        "-DDC=(InstalledEnginePak,V2Local=(Type=FileSystem,Path={}))",
        context.ddc.dir.display()
    ));
    expected.push("-ForceDPCVars=r.GenerateMeshDistanceFields=0".into());
    assert_eq!(command.args, expected);
    assert_eq!(
        command.env.keys().collect::<Vec<_>>(),
        ["LC_ALL", "TZ"],
        "nothing inherited"
    );
    let mut other = context.clone();
    other.build_id = "5.8-other".into();
    other.ddc = ddc(&space, "5.8-other");
    let error = job_loop_command(&other, &scratch).unwrap_err();
    assert!(error.to_string().contains("another context"), "{error}");
}

#[cfg(target_os = "macos")] // the scratch project needs APFS clones
#[test]
fn each_session_runs_a_frozen_worker_bundle_whose_digest_is_session_identity() {
    use std::os::unix::fs::PermissionsExt;
    let space = Workspace::new();
    let mut context = context(&space);
    let script = copied_worker(&space);
    let source = script.parent().unwrap().to_path_buf();
    context.worker = UnrealWorkerBundle::read(&source).unwrap();
    let original = fs::read(source.join("protocol.py")).unwrap();
    assert_eq!(
        context.worker.digest(),
        UnrealWorkerBundle::read(repo_worker().parent().unwrap())
            .unwrap()
            .digest(),
        "content, not location"
    );
    assert_eq!(context.identity()["worker"], context.worker.digest());
    assert!(
        UnrealWorkerBundle::from_files(Default::default()).is_err(),
        "exactly the worker files"
    );
    let session = space.path("session");
    fs::create_dir(&session).unwrap();
    let scratch = ScratchProject::prepare(&session, &context).unwrap();
    let frozen = session.join("worker");
    assert_eq!(scratch.worker_script(), frozen.join("unreal_worker.py"));
    for name in UNREAL_WORKER_FILES {
        let metadata = fs::symlink_metadata(frozen.join(name)).unwrap();
        assert_eq!(metadata.permissions().mode() & 0o777, 0o444, "{name}");
        assert_eq!(
            fs::read(frozen.join(name)).unwrap(),
            fs::read(source.join(name)).unwrap(),
            "frozen bytes"
        );
    }
    let command = job_loop_command(&context, &scratch).unwrap();
    assert_eq!(
        command.args[2],
        format!("-script={}", frozen.join("unreal_worker.py").display())
    );

    // Editing or retargeting the source after setup never reaches the session.
    fs::write(source.join("protocol.py"), b"raise SystemExit('live edit')").unwrap();
    fs::remove_file(&script).unwrap();
    std::os::unix::fs::symlink("/etc/hosts", &script).unwrap();
    job_loop_command(&context, &scratch).unwrap();
    assert_eq!(fs::read(frozen.join("protocol.py")).unwrap(), original);
    // A bundle frozen from the edited source is a different worker, so a new session.
    fs::remove_file(&script).unwrap();
    fs::copy(repo_worker(), &script).unwrap();
    let mut next = context.clone();
    next.worker = UnrealWorkerBundle::read(&source).unwrap();
    assert_ne!(next.worker.digest(), context.worker.digest());
    assert_ne!(next.profile(), context.profile());
    assert!(
        UnrealWorkerBundle::read(&{
            let linked = space.path("linked");
            fs::create_dir(&linked).unwrap();
            std::os::unix::fs::symlink(source.join("protocol.py"), linked.join("protocol.py"))
                .unwrap();
            fs::copy(repo_worker(), linked.join("unreal_worker.py")).unwrap();
            linked
        })
        .is_err(),
        "never freezes through a link"
    );

    // A changed frozen copy is refused before launch and by verify.
    fs::set_permissions(&frozen, fs::Permissions::from_mode(0o755)).unwrap();
    fs::set_permissions(
        frozen.join("protocol.py"),
        fs::Permissions::from_mode(0o644),
    )
    .unwrap();
    fs::write(frozen.join("protocol.py"), b"# tampered").unwrap();
    let error = job_loop_command(&context, &scratch).unwrap_err();
    assert!(
        error.to_string().contains("frozen worker changed"),
        "{error}"
    );
    assert!(scratch.verify().is_err());
}

#[test]
fn a_scratch_project_clones_only_declared_binaries_read_only_and_checks_their_identity() {
    let space = Workspace::new();
    let context = context(&space);
    let pak = space.write(
        "Epic Games/UE/Engine/DerivedDataCache/Compressed.ddp",
        b"engine pak",
    );
    let session = space.path("session");
    fs::create_dir(&session).unwrap();
    let scratch = match ScratchProject::prepare(&session, &context) {
        Ok(scratch) => scratch,
        Err(error) => {
            assert!(!cfg!(target_os = "macos"), "{error}");
            assert!(error.to_string().contains("requires macOS"), "{error}");
            return;
        }
    };
    let root = scratch.root().to_path_buf();
    assert_eq!(
        scratch.receipt().files.keys().cloned().collect::<Vec<_>>(),
        [
            "Binaries/Mac/UnrealEditor.modules",
            "Binaries/Mac/libUnrealEditor-AtelierImport.dylib",
            "Plugins/AtelierBuildWorker/AtelierBuildWorker.uplugin",
            "Plugins/AtelierBuildWorker/Binaries/Mac/libUnrealEditor-AtelierBuildWorker.dylib",
        ]
    );
    assert!(
        !root.join("Plugins/AtelierBuildWorker/Source").exists(),
        "no sources"
    );
    for folder in ["Content", "Config", "Saved", "Intermediate"] {
        assert_eq!(
            fs::read_dir(root.join(folder)).unwrap().count(),
            0,
            "{folder} starts empty"
        );
    }
    let descriptor: serde_json::Value =
        serde_json::from_slice(&fs::read(scratch.uproject()).unwrap()).unwrap();
    assert_eq!(descriptor["Modules"][0]["Name"], "AtelierImport");
    assert_eq!(descriptor["Modules"].as_array().unwrap().len(), 1);
    let plugins: Vec<_> = descriptor["Plugins"]
        .as_array()
        .unwrap()
        .iter()
        .map(|p| p["Name"].as_str().unwrap().to_string())
        .collect();
    assert_eq!(
        plugins,
        ["AtelierBuildWorker", "Interchange", "PythonScriptPlugin"]
    );
    assert!(
        descriptor.get("AdditionalPluginDirectories").is_none(),
        "no checkout plugins"
    );
    let expected = scratch.expected();
    assert_eq!(expected.worker_version, UNREAL_JOB_LOOP_VERSION);
    assert_eq!(expected.profile, context.profile());
    assert_eq!(
        expected.libraries.len(),
        2,
        "both libraries, by their cloned bytes"
    );

    // Read-only clones: an editor that wants to rebuild a module fails, by design.
    let library = root.join("Binaries/Mac/libUnrealEditor-AtelierImport.dylib");
    assert!(fs::write(&library, b"rebuilt").is_err());
    assert!(fs::write(root.join("Binaries/Mac/UnrealEditor-New.dylib"), b"new").is_err());
    scratch.verify().unwrap();
    assert_eq!(
        scratch.expected().ddc,
        DdcPolicy {
            dir: context.ddc.dir.to_str().unwrap().into(),
            engine_pak: pak.to_str().unwrap().into(),
        }
    );
    assert!(
        !context.ddc.dir.starts_with(&session),
        "the DDC is never session scratch"
    );

    // The graph check cannot see a writable pak node; a write to the installed pak is caught.
    fs::write(&pak, b"engine pak, rewritten").unwrap();
    let error = scratch.verify().unwrap_err();
    assert!(error.to_string().contains("engine pak changed"), "{error}");
    fs::write(&pak, b"engine pak").unwrap();
    fs::remove_file(&pak).unwrap();
    assert!(scratch.verify().is_err(), "a removed pak is a change too");
    fs::write(&pak, b"engine pak").unwrap();

    // A changed source after the clone is caught.
    fs::write(
        context.editor.dir.join("UnrealEditor.modules"),
        b"{\"BuildId\": \"b2\"}",
    )
    .unwrap();
    let error = scratch.verify().unwrap_err();
    assert!(
        error.to_string().contains("changed after it was cloned"),
        "{error}"
    );
    scratch.remove().unwrap();
    assert!(!root.exists());
    assert!(
        session.join(RECEIPT_FILE).exists(),
        "the receipt outlives the project"
    );

    // A declared identity that the bytes do not match refuses the session.
    let session = space.path("session-2");
    fs::create_dir(&session).unwrap();
    let error = ScratchProject::prepare(&session, &context).unwrap_err();
    assert!(
        error
            .to_string()
            .contains("does not hold the declared binaries"),
        "{error}"
    );
}

#[cfg(target_os = "macos")] // the scratch project needs APFS clones
#[test]
fn context_and_import_evidence_are_required_well_formed_and_exact() {
    let space = Workspace::new();
    let context = context(&space);
    let session = space.path("session");
    fs::create_dir(&session).unwrap();
    let scratch = ScratchProject::prepare(&session, &context).unwrap();
    let report = session.join(CONTEXT_REPORT);
    assert!(
        scratch.verify_context_report().is_err(),
        "missing evidence is refused"
    );
    fs::write(&report, b"{\"version\": 1}").unwrap();
    assert!(
        scratch.verify_context_report().is_err(),
        "malformed evidence is refused"
    );
    let mut loaded = scratch.expected().clone();
    loaded.modules.insert("UndeclaredModule".into());
    let v2 = DdcNode {
        kind: "File System".into(),
        path: context.ddc.dir.to_str().unwrap().into(),
    };
    let write = |loaded: &LoadedContext, nodes: Vec<DdcNode>| {
        let value = ContextReport {
            version: EVIDENCE_VERSION,
            loaded: loaded.clone(),
            ddc_graph: DdcGraph {
                graph: "inline".into(),
                nodes,
            },
            settings_read: vec![],
        };
        fs::write(&report, serde_json::to_vec(&value).unwrap()).unwrap();
    };
    write(&loaded, vec![v2.clone()]);
    let error = scratch.verify_context_report().unwrap_err();
    assert!(
        error.to_string().contains("different native context"),
        "{error}"
    );
    // The recorded effective graph is checked again, whatever the command line said.
    let shared = DdcNode {
        kind: "File System".into(),
        path: space
            .path("shared/DerivedDataCache")
            .to_str()
            .unwrap()
            .into(),
    };
    write(scratch.expected(), vec![v2.clone(), shared]);
    let error = scratch.verify_context_report().unwrap_err();
    assert!(error.to_string().contains("cache graph"), "{error}");
    write(scratch.expected(), vec![v2.clone()]);
    assert_eq!(
        scratch.verify_context_report().unwrap().loaded,
        *scratch.expected()
    );

    let job = space.path("job");
    fs::create_dir_all(job.join("output")).unwrap();
    let declared = BTreeSet::from(["/Game/Meshes/Rock".to_string()]);
    assert!(
        read_import_evidence(&job, &declared).is_err(),
        "missing evidence is refused"
    );
    let evidence = |packages: &[&str]| {
        let value = ImportEvidence {
            version: EVIDENCE_VERSION,
            packages: packages
                .iter()
                .map(|package| PackageImports {
                    package: package.to_string(),
                    imports: vec![("/Script/Engine".into(), "Package".into())],
                })
                .collect(),
        };
        fs::create_dir_all(job.join("evidence")).unwrap();
        fs::write(
            job.join(IMPORT_EVIDENCE),
            serde_json::to_vec(&value).unwrap(),
        )
        .unwrap();
    };
    evidence(&["/Game/Meshes/Other"]);
    assert!(
        read_import_evidence(&job, &declared).is_err(),
        "undeclared package"
    );
    evidence(&[]);
    assert!(
        read_import_evidence(&job, &declared).is_err(),
        "omitted package"
    );
    evidence(&["/Game/Meshes/Rock"]);
    let read = read_import_evidence(&job, &declared).unwrap();
    assert_eq!(read.packages[0].imports[0].1, "Package");
    assert_eq!(
        fs::read_dir(job.join("output")).unwrap().count(),
        0,
        "outside output/"
    );
}

// ---- The worker over the real protocol ----
// macOS only: the scratch project needs APFS clones.
#[cfg(target_os = "macos")]
mod editor_session {
    use super::*;

    use atelier_build_v2::launch::{DirectChild, DirectWorker, LaunchedWorker, StartWorker};
    use atelier_build_v2::protocol::{FailureKind, JobRequest};
    use atelier_build_v2::worker_session::{Channel, Session};
    use std::io::{PipeReader, PipeWriter};
    use std::os::unix::fs::PermissionsExt;
    use std::path::Path;

    const OP: &str = r#"
import unreal
fake = unreal.AtelierFake

def run(context):
    p = context.params
    if 'break' in p:
        fake.break_call(p['break'])
    for relative, data in p.get('before', []):
        fake.write_file(relative, data.encode())  # plain file I/O before the save
    for name, payload in p.get('create', []):
        fake.create_package(name, payload.encode(), imports=[['/Script/Engine', 'StaticMesh']])
        fake.save_package(name, bulk=p['bulk'].encode() if 'bulk' in p else None)
        if p.get('save_twice'):
            fake.save_package(name)  # as a rename does: the same package to the same file again
    for name, payload, into in p.get('save_into', []):
        fake.create_package(name, payload.encode(), imports=[['/Script/Engine', 'StaticMesh']])
        fake.save_package(name, into=into)  # a save with an explicit filename: another package's file
    for name, payload in p.get('import', []):
        fake.import_package(name, payload.encode())
    for name, payload in p.get('create_deferred', []):
        fake.create_package(name, payload.encode(), imports=[['/Script/Engine', 'StaticMesh']])
        fake.save_package(name, deferred=True)  # its bytes land only when the writes are flushed
    if 'overwrite' in p:
        relative, data = p['overwrite']
        fake.write_file(relative, data.encode())  # plain file I/O after the save
    if 'delete' in p:
        (context.content_dir / p['delete']).unlink()
    if 'direct' in p:
        (context.job_dir / 'output' / p['direct']).write_bytes(b'not from a save')
    if 'register' in p:
        fake.register_cvar(p['register'], '0')
    if p.get('ensure'):
        fake.ensure()
    if 'derive' in p:
        source, target = p['derive']
        fake.create_package(target, fake.load_package(context.packages[source]) + b'!')
        fake.save_package(target)
    for name in p.get('keep', []):
        fake.keep_alive(name)
    for name in p.get('dirty', []):
        fake.dirty(name)
    if 'cvar' in p:
        fake.set_cvar(p['cvar'], '1')
    if 'stray' in p:
        fake.write_file(p['stray'], b'x')
    if 'forge' in p:
        with open(context.content_dir / p['forge'], 'wb') as stream:
            stream.write(b'not a saved package')
    if 'raise' in p:
        raise ValueError(p['raise'])
"#;

    fn python() -> PathBuf {
        std::env::split_paths(&std::env::var_os("PATH").unwrap())
            .map(|directory| directory.join("python3"))
            .find(|path| path.is_file())
            .expect("python3 on PATH runs the stand-in editor")
    }

    /// A stand-in engine at `engine/` whose editor is `fake_unreal.py`, reporting `build_id`.
    fn fake_engine(space: &Workspace, build_id: &str) {
        let fixture = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/fake_unreal.py");
        let source = fs::read_to_string(fixture).unwrap();
        let editor = space.write(
            "Epic Games/UE/Engine/Binaries/Mac/UnrealEditor-Cmd",
            format!("#!{} -sS\n{source}", python().display()).as_bytes(),
        );
        fs::set_permissions(&editor, fs::Permissions::from_mode(0o755)).unwrap();
        space.write(
            "Epic Games/UE/Engine/Binaries/Mac/UnrealEditor.modules",
            format!("{{\"BuildId\": \"{build_id}\"}}").as_bytes(),
        );
    }

    struct Editor {
        process: DirectWorker,
        channel: Channel<PipeReader, PipeWriter>,
        scratch: ScratchProject,
    }

    /// A prepared session on the stand-in editor.
    fn editor(space: &Workspace, context: &UnrealContext) -> Editor {
        editor_with(space, context, |_| {})
    }

    /// A prepared session whose command line `edit` changes first.
    fn editor_with(
        space: &Workspace,
        context: &UnrealContext,
        edit: impl FnOnce(&mut Vec<String>),
    ) -> Editor {
        let session = space.path("session");
        fs::create_dir_all(&session).unwrap();
        let scratch = ScratchProject::prepare(&session, context).unwrap();
        let mut command = job_loop_command(context, &scratch).unwrap();
        edit(&mut command.args);
        let (process, pipes) = DirectChild.start(&command).unwrap();
        let channel = Channel::new(
            Session::new(UNREAL_JOB_LOOP_VERSION),
            pipes.responses,
            pipes.requests,
        );
        Editor {
            process,
            channel,
            scratch,
        }
    }

    /// A staged job folder: the op as declared code, input packages under `in/content/Game/`.
    fn job(
        space: &Workspace,
        name: &str,
        params: serde_json::Value,
        outputs: &[&str],
        inputs: &[(&str, &[u8])],
    ) -> JobRequest {
        let dir = space.path(&format!("jobs/{name}"));
        fs::create_dir_all(dir.join("output")).unwrap();
        space.write(&format!("jobs/{name}/ops/op.py"), OP.as_bytes());
        let mut staged = vec![];
        for (logical, bytes) in inputs {
            let path = format!("in/content/Game/{logical}.uasset");
            space.write(&format!("jobs/{name}/{path}"), bytes);
            staged.push(serde_json::json!({"name": logical, "path": path,
            "identity": {"state": "digest", "digest": "0".repeat(64)}}));
        }
        serde_json::from_value(serde_json::json!({
        "job_id": name, "unit": format!("unit.{name}"), "op": {"kind": "unreal_fixture", "version": "1"},
        "job_dir": dir.to_str().unwrap(), "script": "ops/op.py", "code": ["ops/op.py"],
        "inputs": staged, "params": params,
        "outputs": outputs.iter().map(|path| match path.strip_suffix('?') {
            Some(optional) => serde_json::json!({"path": optional, "required": false}),
            None => serde_json::json!({"path": path, "required": true}),
        }).collect::<Vec<_>>(),
    }))
    .unwrap()
    }

    fn output(job: &JobRequest, relative: &str) -> Vec<u8> {
        fs::read(Path::new(&job.job_dir).join("output").join(relative)).unwrap()
    }

    fn empty(path: &Path) -> bool {
        fs::read_dir(path).unwrap().next().is_none()
    }

    #[test]
    fn one_editor_serves_jobs_in_order_with_a_clean_game_folder_between_them() {
        let space = Workspace::new();
        fake_engine(&space, "5.8-build");
        let context = context(&space);
        let mut editor = editor(&space, &context);
        assert_eq!(editor.channel.handshake().unwrap(), UNREAL_JOB_LOOP_VERSION);
        let report = editor.scratch.verify_context_report().unwrap();
        assert_eq!(report.loaded.build_id, "5.8-build");
        assert!(
            !report.loaded.plugins.contains("ContentBrowserData"),
            "engine defaults are platform"
        );

        let rock = |name: &str, payload: &str| {
            job(
                &space,
                name,
                serde_json::json!({"create": [["/Game/Meshes/Rock", payload]]}),
                &["content/Game/Meshes/Rock.uasset"],
                &[],
            )
        };
        let mut bytes = vec![];
        for (name, payload) in [("a-1", "rock"), ("b", "other"), ("a-2", "rock")] {
            let request = rock(name, payload);
            let finished = editor.channel.run(request.clone()).unwrap();
            assert_eq!(
                finished.result.unwrap().files,
                ["content/Game/Meshes/Rock.uasset"]
            );
            bytes.push(output(&request, "content/Game/Meshes/Rock.uasset"));
            assert!(
                empty(&editor.scratch.content()),
                "/Game is empty after {name}"
            );
            let declared = BTreeSet::from(["/Game/Meshes/Rock".to_string()]);
            let evidence = read_import_evidence(Path::new(&request.job_dir), &declared).unwrap();
            assert_eq!(
                evidence.packages[0].imports,
                [("/Script/Engine".into(), "StaticMesh".into())]
            );
        }
        assert_eq!(bytes[0], bytes[2], "A, then B, then A gives the same A");
        assert_ne!(bytes[0], bytes[1]);

        // A package saved twice to one file (as a rename does) is one save, an imported package
        // that survives its first unload is gone after the second pass, and a CVar registered during
        // the job at its default does not retire the editor: the next job still runs.
        let twice = job(
            &space,
            "twice",
            serde_json::json!({"create": [["/Game/Meshes/Rock", "rock"]], "save_twice": true,
                               "import": [["/Game/Meshes/Imported", "imported"]],
                               "register": "r.LoadedOnDemand"}),
            &[
                "content/Game/Meshes/Rock.uasset",
                "content/Game/Meshes/Imported.uasset",
            ],
            &[],
        );
        assert!(editor.channel.run(twice.clone()).unwrap().result.is_ok());
        let declared = BTreeSet::from([
            "/Game/Meshes/Imported".to_string(),
            "/Game/Meshes/Rock".to_string(),
        ]);
        let evidence = read_import_evidence(Path::new(&twice.job_dir), &declared).unwrap();
        assert_eq!(evidence.packages.len(), 2, "each package once");

        // A staged input package sits read-only at its logical path, and is gone afterwards.
        let derived = job(
            &space,
            "derive",
            serde_json::json!({"derive": ["Source", "/Game/Meshes/Derived"]}),
            &["content/Game/Meshes/Derived.uasset"],
            &[("Source", b"source-bytes")],
        );
        assert!(editor.channel.run(derived.clone()).unwrap().result.is_ok());
        assert_eq!(
            output(&derived, "content/Game/Meshes/Derived.uasset"),
            b"source-bytes!"
        );
        assert!(empty(&editor.scratch.content()));

        editor.channel.shutdown().unwrap();
        assert!(editor.process.wait().unwrap().success());
        editor.scratch.verify().unwrap();
    }

    #[test]
    fn undeclared_saves_files_dirty_packages_and_op_errors_fail_and_the_next_job_runs() {
        let space = Workspace::new();
        fake_engine(&space, "5.8-build");
        let context = context(&space);
        let mut editor = editor(&space, &context);
        editor.channel.handshake().unwrap();
        let declared = [
            "content/Game/A.uasset",
            "content/Game/A.ubulk?",
            "content/Game/A.umap?",
            "content/Game/B.uasset?",
        ];
        let cases = [
            (
                serde_json::json!({"create": [["/Game/A", "a"], ["/Game/Extra", "x"]]}),
                FailureKind::Dependency,
                "undeclared packages",
            ),
            (
                serde_json::json!({"create": [["/Game/A", "a"]], "stray": "Stray.bin"}),
                FailureKind::Dependency,
                "undeclared file",
            ),
            (
                serde_json::json!({"create": [["/Game/A", "a"]], "dirty": ["/Game/A"]}),
                FailureKind::Job,
                "unsaved changes",
            ),
            (serde_json::json!({}), FailureKind::Job, "did not save"),
            (
                serde_json::json!({"raise": "bad mesh"}),
                FailureKind::Job,
                "bad mesh",
            ),
            (
                // With -nocrashreports an ensure starts no crash reporter: it fails the job.
                serde_json::json!({"create": [["/Game/A", "a"]], "ensure": true}),
                FailureKind::Job,
                "failed ensure",
            ),
            (
                // A declared package file written by plain file I/O, with no package save.
                serde_json::json!({"create": [["/Game/A", "a"]], "forge": "B.uasset"}),
                FailureKind::Dependency,
                "without saving its package",
            ),
            (
                // Saved, then overwritten by plain file I/O: not the bytes the save wrote.
                serde_json::json!({"create": [["/Game/A", "a"]], "overwrite": ["A.uasset", "forged"]}),
                FailureKind::Dependency,
                "bytes its package save wrote",
            ),
            (
                // A declared companion file added by plain file I/O beside a saved package.
                serde_json::json!({"create": [["/Game/A", "a"]], "overwrite": ["A.ubulk", "bulk"]}),
                FailureKind::Dependency,
                "not written by its package save",
            ),
            (
                // A declared sibling written before the save: the save of A.uasset never wrote
                // the other main extension, so it is not certified as saved.
                serde_json::json!({"before": [["A.umap", "map"]], "create": [["/Game/A", "a"]]}),
                FailureKind::Dependency,
                "not written by its package save",
            ),
            (
                // A declared companion written before a save that leaves it alone.
                serde_json::json!({"before": [["A.ubulk", "bulk"]], "create": [["/Game/A", "a"]]}),
                FailureKind::Dependency,
                "not written by its package save",
            ),
            (
                // The save event arrives before its writes are flushed; hashing unflushed bytes
                // would record the wrong file, so the collected bytes do not match.
                serde_json::json!({"create_deferred": [["/Game/A", "a"]], "break": "flush"}),
                FailureKind::Dependency,
                "bytes its package save wrote",
            ),
            (
                // A second package saved into the first one's file: the bytes are not A's.
                serde_json::json!({"create": [["/Game/A", "a"]], "save_into": [["/Game/B", "b", "/Game/A"]]}),
                FailureKind::Dependency,
                "more than one package saved the same file",
            ),
            (
                // A companion the save wrote, then overwritten by plain file I/O.
                serde_json::json!({"create": [["/Game/A", "a"]], "bulk": "bulk", "overwrite": ["A.ubulk", "forged"]}),
                FailureKind::Dependency,
                "bytes its package save wrote",
            ),
            (
                // Saved, then deleted: a required output is missing.
                serde_json::json!({"create": [["/Game/A", "a"]], "delete": "A.uasset"}),
                FailureKind::Job,
                "required outputs are missing",
            ),
            (
                // An unreadable import table fails closed, never with a guessed import list.
                serde_json::json!({"create": [["/Game/A", "a"]], "break": "imports"}),
                FailureKind::Job,
                "import table",
            ),
        ];
        for (index, (params, kind, reason)) in cases.into_iter().enumerate() {
            let request = job(&space, &format!("bad-{index}"), params, &declared, &[]);
            let failure = editor
                .channel
                .run(request.clone())
                .unwrap()
                .result
                .unwrap_err();
            assert_eq!(failure.kind, kind, "case {index}: {}", failure.message);
            assert!(
                failure.message.contains(reason),
                "case {index}: {}",
                failure.message
            );
            assert!(
                empty(&Path::new(&request.job_dir).join("output")),
                "case {index} left outputs"
            );
            assert!(
                empty(&editor.scratch.content()),
                "case {index} left /Game files"
            );
        }
        // A file written straight into output/ is never an output, and the job fails.
        let direct = job(
            &space,
            "direct",
            serde_json::json!({"create": [["/Game/A", "a"]], "direct": "B.uasset"}),
            &declared,
            &[],
        );
        let failure = editor.channel.run(direct).unwrap().result.unwrap_err();
        assert_eq!(failure.kind, FailureKind::Dependency, "{}", failure.message);
        assert!(
            failure.message.contains("output/ directly"),
            "{}",
            failure.message
        );
        assert!(empty(&editor.scratch.content()));

        // A save whose writes finish only at the flush is hashed after it: the job completes.
        let deferred = job(
            &space,
            "deferred",
            serde_json::json!({"create_deferred": [["/Game/A", "a"]]}),
            &declared,
            &[],
        );
        assert!(editor.channel.run(deferred.clone()).unwrap().result.is_ok());
        assert_eq!(output(&deferred, "content/Game/A.uasset"), b"a");
        // A companion the save replaces is the save's own file, even over a plain write before it.
        let replaced = job(
            &space,
            "replaced",
            serde_json::json!({"before": [["A.ubulk", "stale"]], "create": [["/Game/A", "a"]], "bulk": "fresh"}),
            &declared,
            &[],
        );
        let result = editor.channel.run(replaced.clone()).unwrap().result;
        assert!(result.is_ok(), "{result:?}");
        assert_eq!(output(&replaced, "content/Game/A.ubulk"), b"fresh");
        // A later save that leaves its companion alone keeps the earlier save's attestation of it.
        let resaved = job(
            &space,
            "resaved",
            serde_json::json!({"create": [["/Game/A", "a"]], "bulk": "bulk", "save_twice": true}),
            &declared,
            &[],
        );
        let result = editor.channel.run(resaved.clone()).unwrap().result;
        assert!(result.is_ok(), "{result:?}");
        assert_eq!(output(&resaved, "content/Game/A.ubulk"), b"bulk");
        let good = job(
            &space,
            "good",
            serde_json::json!({"create": [["/Game/A", "a"]]}),
            &declared,
            &[],
        );
        assert!(
            editor.channel.run(good).unwrap().result.is_ok(),
            "the same editor runs the next job"
        );
        editor.channel.shutdown().unwrap();
        assert!(editor.process.wait().unwrap().success());
    }

    #[test]
    fn a_package_left_loaded_a_changed_setting_or_a_raising_reset_retires_the_editor_after_its_reply()
     {
        for (name, extra) in [
            ("keep", serde_json::json!({"keep": ["/Game/A"]})),
            ("cvar", serde_json::json!({"cvar": "r.Test"})),
            // A reset that raises still sends the job's reply before the editor exits.
            ("unload", serde_json::json!({"break": "unload"})),
        ] {
            let space = Workspace::new();
            fake_engine(&space, "5.8-build");
            let context = context(&space);
            let mut editor = editor(&space, &context);
            editor.channel.handshake().unwrap();
            let mut params = serde_json::json!({"create": [["/Game/A", "a"]]});
            params
                .as_object_mut()
                .unwrap()
                .extend(extra.as_object().unwrap().clone());
            let request = job(&space, name, params, &["content/Game/A.uasset"], &[]);
            let finished = editor.channel.run(request).unwrap();
            assert!(finished.result.is_ok(), "{name}: the job itself completed");
            // The editor exits instead of serving another job: the session ends, it is not reused.
            let ended = format!("{:?}", editor.channel.next_event().unwrap_err());
            assert!(
                ended.contains("end of stream in state Idle"),
                "{name}: {ended}"
            );
            assert!(
                editor.process.wait().unwrap().success(),
                "{name}: a clean exit"
            );
        }
    }

    #[test]
    fn a_cache_graph_with_zen_or_a_folder_outside_the_v2_ddc_never_says_hello() {
        // Whatever the command line asks for, the worker reads the editor's effective graph.
        fn elsewhere(space: &Workspace) -> String {
            space.path("elsewhere-ddc").to_str().unwrap().to_string()
        }
        let edits: [(&str, Box<dyn Fn(&Workspace, &mut Vec<String>)>); 3] = [
            (
                "outside the v2 DDC folder",
                Box::new(|space, args| {
                    let graph = args.iter_mut().find(|a| a.starts_with("-DDC=")).unwrap();
                    *graph = format!(
                        "-DDC=(InstalledEnginePak,V2Local=(Type=FileSystem,Path={}))",
                        elsewhere(space)
                    );
                }),
            ),
            (
                "a Zen node",
                Box::new(|_, args| {
                    let graph = args.iter_mut().find(|a| a.starts_with("-DDC=")).unwrap();
                    graph.insert_str(graph.len() - 1, ",ZenLocal=(Type=Zen)");
                }),
            ),
            (
                "a Zen node",
                // No graph argument: the editor's installed default graph (Zen, then a shared folder).
                Box::new(|_, args| args.retain(|a| !a.starts_with("-DDC="))),
            ),
        ];
        for (why, edit) in edits {
            let space = Workspace::new();
            fake_engine(&space, "5.8-build");
            let context = context(&space);
            let mut refused = editor_with(&space, &context, |args| edit(&space, args));
            assert!(refused.channel.handshake().is_err(), "{why}");
            assert!(!refused.process.wait().unwrap().success(), "{why}");
            let error = refused.scratch.verify_context_report().unwrap_err();
            assert!(error.to_string().contains("cache graph"), "{why}: {error}");
            assert!(error.to_string().contains(why), "{why}: {error}");
            let report: ContextReport = serde_json::from_slice(
                &fs::read(refused.scratch.session().join(CONTEXT_REPORT)).unwrap(),
            )
            .unwrap();
            assert!(!report.ddc_graph.nodes.is_empty(), "the graph is recorded");
        }
    }

    #[test]
    fn a_different_native_context_or_a_module_rebuild_never_says_hello() {
        // The installed engine is not the one the session declared: the worker reports it and stops.
        let space = Workspace::new();
        fake_engine(&space, "5.8-other");
        let mut other = editor(&space, &context(&space));
        assert!(other.channel.handshake().is_err());
        assert!(!other.process.wait().unwrap().success());
        let error = other.scratch.verify_context_report().unwrap_err();
        assert!(
            error.to_string().contains("different native context"),
            "{error}"
        );

        // An engine plugin whose installed bytes changed after the context was declared.
        let space = Workspace::new();
        fake_engine(&space, "5.8-build");
        let declared = context(&space);
        fs::write(
            space.path("Epic Games/UE/Engine/Plugins/Interchange/Binaries/Mac/libUnrealEditor-Interchange.dylib"),
            b"replaced",
        )
        .unwrap();
        let mut replaced = editor(&space, &declared);
        assert!(replaced.channel.handshake().is_err());
        assert!(!replaced.process.wait().unwrap().success());
        let error = replaced.scratch.verify_context_report().unwrap_err();
        assert!(
            error.to_string().contains("different native context"),
            "{error}"
        );

        // The source worker is edited after setup: the session still runs the frozen bytes.
        let space = Workspace::new();
        fake_engine(&space, "5.8-build");
        let mut declared = context(&space);
        let script = copied_worker(&space);
        declared.worker = UnrealWorkerBundle::read(script.parent().unwrap()).unwrap();
        let mut frozen = editor_with(&space, &declared, |_| {
            fs::write(
                script.with_file_name("protocol.py"),
                b"raise SystemExit('live')",
            )
            .unwrap();
        });
        frozen.channel.handshake().unwrap();
        let request = job(
            &space,
            "frozen",
            serde_json::json!({"create": [["/Game/A", "a"]]}),
            &["content/Game/A.uasset"],
            &[],
        );
        assert!(frozen.channel.run(request).unwrap().result.is_ok());
        frozen.channel.shutdown().unwrap();
        assert!(frozen.process.wait().unwrap().success());
        let report = frozen.scratch.verify_context_report().unwrap();
        assert_eq!(report.loaded.worker, declared.worker.digest());

        // The frozen copy itself is changed after the command was built: the worker's own digest
        // of the files it loaded differs, so it never says hello.
        let space = Workspace::new();
        fake_engine(&space, "5.8-build");
        let declared = context(&space);
        let mut tampered = editor_with(&space, &declared, |_| {
            let frozen = space.path("session/worker");
            fs::set_permissions(&frozen, fs::Permissions::from_mode(0o755)).unwrap();
            let protocol = frozen.join("protocol.py");
            fs::set_permissions(&protocol, fs::Permissions::from_mode(0o644)).unwrap();
            let mut bytes = fs::read(&protocol).unwrap();
            bytes.extend_from_slice(b"\n# tampered after launch\n");
            fs::write(&protocol, bytes).unwrap();
        });
        assert!(tampered.channel.handshake().is_err());
        assert!(!tampered.process.wait().unwrap().success());
        let error = tampered.scratch.verify_context_report().unwrap_err();
        assert!(
            error.to_string().contains("different native context"),
            "{error}"
        );

        // A declared setting the editor does not hold exactly never says hello. A missing value
        // never matches, even a literal `None`; ini values compare as exact text; console
        // variables as exact text or as the same finite decimal, never through a binary float.
        // The editor's raw readback is recorded either way.
        for (setting, readback, actual, applied) in [
            ("-ForceDPCVars=r.Unknown=1", None, None, false),
            ("-ForceDPCVars=r.Unknown=None", None, None, false),
            (
                "-ini:Engine:[Core.Log]:LogPython=None",
                Some("-FakeReadback=Engine:[Core.Log]:LogPython"),
                None,
                false,
            ),
            (
                "-ForceDPCVars=r.Existing=9007199254740993",
                Some("-FakeReadback=r.Existing|9007199254740992"),
                Some("9007199254740992"),
                false,
            ),
            (
                "-ForceDPCVars=r.Existing=1e999",
                Some("-FakeReadback=r.Existing|2e999"),
                Some("2e999"),
                false,
            ),
            (
                "-ini:Engine:[Core.Log]:LogPython=01",
                Some("-FakeReadback=Engine:[Core.Log]:LogPython|1"),
                Some("1"),
                false,
            ),
            (
                "-ini:Engine:[Core.Log]:LogPython=Verbose",
                None,
                Some("Verbose"),
                true,
            ),
            (
                "-ForceDPCVars=r.Existing=1",
                Some("-FakeReadback=r.Existing|1.000000"),
                Some("1.000000"),
                true,
            ),
        ] {
            let space = Workspace::new();
            fake_engine(&space, "5.8-build");
            let mut declared = context(&space);
            declared.settings.push(setting.into());
            let mut session = editor_with(&space, &declared, |args| {
                args.extend(readback.map(String::from));
            });
            assert_eq!(session.channel.handshake().is_ok(), applied, "{setting}");
            if applied {
                session.channel.shutdown().unwrap();
                assert!(session.process.wait().unwrap().success());
                session.scratch.verify_context_report().unwrap();
            } else {
                assert!(!session.process.wait().unwrap().success(), "{setting}");
            }
            let report: ContextReport = serde_json::from_slice(
                &fs::read(session.scratch.session().join(CONTEXT_REPORT)).unwrap(),
            )
            .unwrap();
            let read = report.settings_read.last().unwrap();
            assert_eq!(read.setting, setting);
            assert_eq!(
                read.actual.as_deref(),
                actual,
                "{setting}: the raw readback is kept"
            );
            if actual.is_none() {
                assert!(
                    report
                        .loaded
                        .settings
                        .last()
                        .unwrap()
                        .starts_with("missing "),
                    "{setting}: {:?}",
                    report.loaded.settings
                );
            }
        }

        // A library the editor wants to rebuild cannot be: the clone is read-only.
        let space = Workspace::new();
        fake_engine(&space, "5.8-build");
        let mut stale = context(&space);
        let library = stale.editor.dir.join("libUnrealEditor-AtelierImport.dylib");
        fs::write(&library, b"stale").unwrap();
        stale.editor.identity = tree_identity(&stale.editor.dir, None).unwrap();
        let mut rebuilding = editor(&space, &stale);
        assert!(rebuilding.channel.handshake().is_err());
        assert!(!rebuilding.process.wait().unwrap().success());
        rebuilding.scratch.verify().unwrap();
        assert_eq!(
            fs::read(
                rebuilding
                    .scratch
                    .root()
                    .join("Binaries/Mac/libUnrealEditor-AtelierImport.dylib")
            )
            .unwrap(),
            b"stale"
        );
    }
}
