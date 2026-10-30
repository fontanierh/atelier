//! Shared committed exported simulation fixture for full-session regression tests.
use crate::resources::Resources;
pub(crate) fn resources() -> Resources {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../assets/simulations/skate-simulation/skate-simulation.skatepack");
    let bytes = std::fs::read(path).expect("exported skating simulation fixture");
    Resources::from_bytes(bytes).expect("valid exported skating simulation fixture")
}
