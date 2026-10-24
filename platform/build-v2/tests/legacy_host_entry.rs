//! Hosted integration through the original Python environment and actual source-bound binary.
//! The Python fixture owns explicit helper-cache setup and stops at Graph discovery/Held.
use std::path::Path;
use std::process::Command;

#[test]
fn original_production_entry_reaches_captured_graph_then_held_without_mutation_permission() {
    let checkout = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap();
    let python = checkout.join(".venv/bin/python");
    let fixture_name = Path::new(env!("ATELIER_LEGACY_ENTRY_TEST_SCRIPT"));
    assert!(
        fixture_name
            .components()
            .all(|part| matches!(part, std::path::Component::Normal(_))),
        "hosted test locator must be repository-relative"
    );
    let fixture = checkout.join(fixture_name);
    let binary = Path::new(env!("CARGO_BIN_EXE_atelier-build-v2"));
    assert!(python.is_file(), "hosted original Python setup is required");
    assert!(fixture.is_file(), "captured-entry fixture must be present");
    assert!(binary.is_file(), "actual compiled controller is required");
    let status = Command::new(&python)
        .arg(&fixture)
        .arg(binary)
        .current_dir(checkout)
        .status()
        .expect("original Python must execute the real entry fixture");
    assert!(
        status.success(),
        "real production entry/Graph/Held fixture failed: {status}"
    );
}
