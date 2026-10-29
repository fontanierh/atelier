//! Every region, each with its implementation of [`Region`] from its folder under the world's `src/regions/`.

use super::actors::Actor;
use super::authored::AuthoredSurface;
use super::levelling::{Pad, Strip};
use super::overlay::Overlay;
use super::placed::Placed;
use super::raised::Raised;
use super::scenery::{Land, Placement, ScatterKind, Scenery};

#[path = "../../../../assets/world/src/regions/momiji-coast/layout.rs"]
mod momiji_coast;
#[path = "../../../../assets/world/src/regions/momiji-village/layout.rs"]
mod momiji_village;
#[path = "../../../../assets/world/src/regions/roadside-houses/layout.rs"]
mod roadside_houses;
#[path = "../../../../assets/world/src/regions/woodland/layout.rs"]
mod woodland;

/// What a region adds to the world. Positions are in metres, in the map's frame: x east, y north, z up.
pub trait Region {
    /// The region's folder name.
    fn name(&self) -> &'static str;

    /// The strips of ground it levels, as declared changes to the ground. Everything else the world holds, its
    /// tiles, overlays and scenery, stands on the levelled ground.
    fn levelled(&self) -> Vec<Strip>;

    /// Planar ground footprints and shoulders, applied after strips and owning their final surface at crossings.
    fn pads(&self) -> Vec<Pad> {
        Vec::new()
    }

    /// Whether a selected scatter candidate may stand here. Explicit placements are unaffected.
    fn allows_scatter_candidate(&self, _kind: ScatterKind, _placement: &Placement) -> bool {
        true
    }

    /// The flat shapes it lays over the ground.
    fn overlays(&self) -> Vec<Overlay>;

    /// Independent, source-authored triangle surfaces, including their source crossings with terrain.
    fn authored_surfaces(&self) -> Vec<AuthoredSurface> {
        Vec::new()
    }

    /// Planar surfaces that own their footprints above the ground.
    fn raised(&self) -> Vec<Raised> {
        Vec::new()
    }

    /// Animated actors in this region.
    fn actors(&self) -> Vec<Actor> {
        Vec::new()
    }

    /// Bounded water bodies and their shared material and recovery settings, in map coordinates.
    fn water(&self) -> Vec<serde_json::Value> {
        Vec::new()
    }

    /// What it stands on `land` and runs along it.
    fn scenery(&self, land: &Land) -> Scenery;

    /// Models standing past `land`, at their own explicit heights, which tiles past the ground hold alone.
    fn beyond(&self, _land: &Land) -> Vec<Placement> {
        Vec::new()
    }
}

/// A data-only region, [`Placed`] from its folder's `placements.json`.
macro_rules! placed {
    ($name:literal) => {
        &Placed {
            name: $name,
            placements: include_str!(concat!("../../../../assets/world/src/regions/", $name, "/placements.json")),
        }
    };
}

pub const REGIONS: &[&dyn Region] = &[
    &momiji_coast::MomijiCoast,
    &roadside_houses::RoadsideHouses,
    &momiji_village::MomijiVillage,
    &woodland::Woodland,
    placed!("treehouse"),
    placed!("brinecove"),
    placed!("belmonte"),
    placed!("hidamari"),
    placed!("southwest"),
    placed!("shrines"),
    placed!("zeppelin"),
    placed!("sword-camp"),
    placed!("forest"),
    placed!("railway"),
];
