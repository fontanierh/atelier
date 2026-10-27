//! Every region, each with its implementation of [`Region`] from its folder under the world's `src/regions/`.

use super::authored::AuthoredSurface;
use super::levelling::{Pad, Strip};
use super::openings::{Domain, Opening};
use super::overlay::Overlay;
use super::raised::Raised;
use super::scenery::{Exclusion, Land, Placement, ScatterKind, Scenery};

#[path = "../../../../assets/world/src/regions/momiji-coast/layout.rs"]
mod momiji_coast;
#[path = "../../../../assets/world/src/regions/roadside-houses/layout.rs"]
mod roadside_houses;

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

    /// Areas kept clear of scattered scenery. Explicit placements are unaffected.
    fn scatter_exclusions(&self) -> Vec<Exclusion> {
        Vec::new()
    }

    /// Whether a selected scatter candidate may stand here. Explicit placements are unaffected.
    fn allows_scatter_candidate(&self, _kind: ScatterKind, _placement: &Placement) -> bool {
        true
    }

    /// Named parameter domains this region publishes for others to request openings.
    fn path_domains(&self) -> Vec<Domain> {
        Vec::new()
    }

    /// Closed intervals to leave open on published parameter domains.
    fn path_openings(&self) -> Vec<Opening> {
        Vec::new()
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

    /// What it stands on `land` and runs along it.
    fn scenery(&self, land: &Land) -> Scenery;

    /// The models whose anchors its cables fasten to, by folder under `assets/`. The world reads their exports.
    fn fastens_to(&self) -> Vec<&'static str>;
}

pub const REGIONS: [&dyn Region; 2] = [&momiji_coast::MomijiCoast, &roadside_houses::RoadsideHouses];
