//! The roadside terrace: its surveyed frame, level and front edge.

use glam::DVec2;

use super::Region;
use crate::world::levelling::Strip;
use crate::world::openings::Opening;
use crate::world::overlay::Overlay;

use crate::world::raised::{Raised, SurfacePaint};
use crate::world::scenery::{Land, Placement, ScatterKind, Scenery};

const CENTRE: [f64; 2] = [-195.74, -108.22];
const FRONT: [[f64; 2]; 21] = [
    [-9.5, -10.079],
    [-9.071, -10.073],
    [-8.069, -10.059],
    [-7.065, -10.046],
    [-6.059, -10.034],
    [-5.053, -10.023],
    [-4.045, -10.014],
    [-3.036, -10.006],
    [-2.025, -10.0],
    [-1.013, -9.997],
    [0.0, -9.996],
    [1.014, -9.998],
    [2.03, -10.003],
    [3.047, -10.011],
    [4.065, -10.023],
    [5.085, -10.039],
    [6.106, -10.059],
    [7.128, -10.083],
    [8.151, -10.113],
    [9.175, -10.147],
    [9.5, -10.159],
];
const LEVEL: f64 = 8.68;
const YAW_DEG: f64 = -163.6;
const TOP_VERTICES: [[f64; 4]; 46] = [
    [-9.5, 6.800000190734863, -30.784433364868164, -18.676849365234375],
    [-9.071000099182129, -9.623000144958496, -31.625839233398438, -16.07123374938965],
    [-9.071000099182129, 6.800000190734863, -30.853023529052734, -18.697036743164062],
    [-9.5, -9.628999710083008, -31.557531356811523, -16.050086975097656],
    [-8.069000244140625, -9.609000205993652, -31.785385131835938, -16.120622634887695],
    [-8.069000244140625, 6.800000190734863, -31.013229370117188, -18.744186401367188],
    [-7.065000057220459, -9.595999717712402, -31.94529914855957, -16.169946670532227],
    [-7.065000057220459, 6.800000190734863, -31.17375373840332, -18.791431427001953],
    [-6.059000015258789, -9.583999633789062, -32.1055793762207, -16.21920394897461],
    [-6.059000015258789, 6.800000190734863, -31.334598541259766, -18.83877182006836],
    [-5.052999973297119, -9.572999954223633, -32.265907287597656, -16.26830291748047],
    [-5.052999973297119, 6.800000190734863, -31.49544334411621, -18.886110305786133],
    [-4.045000076293945, -9.564000129699707, -32.4266471862793, -16.317174911499023],
    [-4.045000076293945, 6.800000190734863, -31.65660858154297, -18.933544158935547],
    [-3.0360000133514404, -9.555999755859375, -32.58759689331055, -16.365934371948242],
    [-3.0360000133514404, 6.800000190734863, -31.817934036254883, -18.98102378845215],
    [-2.0250000953674316, -9.550000190734863, -32.748958587646484, -16.41446876525879],
    [-2.0250000953674316, 6.800000190734863, -31.979578018188477, -19.02859878540039],
    [-1.0130000114440918, -9.54699993133545, -32.910621643066406, -16.462570190429688],
    [-1.0130000114440918, 6.800000190734863, -32.141380310058594, -19.076221466064453],
    [0.0, -9.545999526977539, -33.072540283203125, -16.510398864746094],
    [0.0, 6.800000190734863, -32.3033447265625, -19.123889923095703],
    [1.0140000581741333, 6.800000190734863, -32.46546936035156, -19.17160415649414],
    [1.0140000581741333, -9.54800033569336, -33.23475646972656, -16.55779457092285],
    [1.850000023841858, 6.800000190734863, -32.59913635253906, -19.21094512939453],
    [1.850000023841858, -9.552114486694336, -33.368614196777344, -16.59647560119629],
    [2.0299999713897705, 6.800000190734863, -32.62791442871094, -19.21941566467285],
    [2.0299999713897705, -9.553000450134277, -33.39743423461914, -16.60480499267578],
    [3.046999931335449, 6.800000190734863, -32.79051971435547, -19.267271041870117],
    [3.046999931335449, -9.560999870300293, -33.56041717529297, -16.651382446289062],
    [3.75, 6.800000190734863, -32.902915954589844, -19.300352096557617],
    [3.75, -9.569287300109863, -33.6732063293457, -16.683137893676758],
    [4.065000057220459, 6.800000190734863, -32.95328140258789, -19.315176010131836],
    [4.065000057220459, -9.572999954223633, -33.7237434387207, -16.69736671447754],
    [5.085000038146973, 6.800000190734863, -33.116363525390625, -19.363174438476562],
    [5.085000038146973, -9.58899974822998, -33.88758087158203, -16.742807388305664],
    [6.105999946594238, 6.800000190734863, -33.27960968017578, -19.411218643188477],
    [6.105999946594238, -9.609000205993652, -34.05176544189453, -16.787654876708984],
    [7.127999782562256, 6.800000190734863, -33.44301223754883, -19.45931053161621],
    [7.127999782562256, -9.633000373840332, -34.2162971496582, -16.8319091796875],
    [8.151000022888184, 6.800000190734863, -33.60657501220703, -19.507450103759766],
    [8.151000022888184, -9.663000106811523, -34.38127136230469, -16.87525177001953],
    [9.175000190734863, 6.800000190734863, -33.77029800415039, -19.555635452270508],
    [9.175000190734863, -9.696999549865723, -34.54659652709961, -16.91800308227539],
    [9.5, 6.800000190734863, -33.822261810302734, -19.57093048095703],
    [9.5, -9.708999633789062, -34.59912109375, -16.931377410888672],
];

const TOP_TRIANGLES: [[usize; 3]; 44] = [
    [0, 1, 2],
    [1, 0, 3],
    [2, 4, 5],
    [4, 2, 1],
    [5, 6, 7],
    [6, 5, 4],
    [7, 8, 9],
    [8, 7, 6],
    [9, 10, 11],
    [10, 9, 8],
    [11, 12, 13],
    [12, 11, 10],
    [13, 14, 15],
    [14, 13, 12],
    [15, 16, 17],
    [16, 15, 14],
    [17, 18, 19],
    [18, 17, 16],
    [19, 20, 21],
    [20, 19, 18],
    [21, 20, 22],
    [22, 20, 23],
    [22, 23, 24],
    [24, 23, 25],
    [24, 25, 26],
    [26, 25, 27],
    [26, 27, 28],
    [28, 27, 29],
    [28, 29, 30],
    [30, 29, 31],
    [30, 31, 32],
    [32, 31, 33],
    [32, 33, 34],
    [34, 33, 35],
    [34, 35, 36],
    [36, 35, 37],
    [36, 37, 38],
    [38, 37, 39],
    [38, 39, 40],
    [40, 39, 41],
    [40, 41, 42],
    [42, 41, 43],
    [42, 43, 44],
    [44, 43, 45],
];

fn world(local: DVec2) -> DVec2 {
    DVec2::from_array(CENTRE) + DVec2::from_angle(YAW_DEG.to_radians()).rotate(local)
}

/// The original top triangles and UVs, in their surveyed frame.
pub fn top(texture: &str) -> Raised {
    let triangles = TOP_TRIANGLES
        .iter()
        .map(|indices| {
            indices.map(|index| {
                let [x, y, u, v] = TOP_VERTICES[index];
                (world(DVec2::new(x, y)), DVec2::new(u, v))
            })
        })
        .collect();
    Raised {
        name: "roadside terrace".into(),
        texture: texture.into(),
        ground: true,
        paint: Some(SurfacePaint { haze_start_m: 30.0, haze_length_m: 9000.0, haze_colour: [0.0932, 0.2301, 0.5328] }),
        height: LEVEL,
        clearance: 0.01,
        triangles,
    }
}

/// The house and the terrace's walls, kerb and garden details share one authored frame.
pub fn placements() -> [Placement; 2] {
    ["props/road-house-a", "props/road-house-lot-1"].map(|model| Placement {
        model,
        at: DVec2::from_array(CENTRE),
        yaw: YAW_DEG.to_radians(),
        scale: 1.0,
        afar: true,
    })
}

/// The roadside house and its lot, placed in their surveyed frame.
pub struct RoadsideHouses;

impl Region for RoadsideHouses {
    fn name(&self) -> &'static str {
        "roadside-houses"
    }

    fn path_openings(&self) -> Vec<Opening> {
        vec![Opening { id: "coastal-downhill-rail", from: 86.2, to: 105.9 }]
    }
    fn levelled(&self) -> Vec<Strip> {
        Vec::new()
    }
    fn overlays(&self) -> Vec<Overlay> {
        Vec::new()
    }
    fn raised(&self) -> Vec<Raised> {
        vec![top("road-house-ground")]
    }
    fn scenery(&self, _: &Land) -> Scenery {
        Scenery { placements: placements().into(), ..Default::default() }
    }
    fn fastens_to(&self) -> Vec<&'static str> {
        Vec::new()
    }
    fn allows_scatter_candidate(&self, kind: ScatterKind, placement: &Placement) -> bool {
        !blocked(kind, placement)
    }
}

/// Whether a selected plant's footprint, or a tree's crown, reaches the lot and its verge.
fn blocked(kind: ScatterKind, plant: &Placement) -> bool {
    let local = DVec2::from_angle(-YAW_DEG.to_radians()).rotate(plant.at - DVec2::from_array(CENTRE));
    let x = local.x.clamp(FRONT[0][0], FRONT[FRONT.len() - 1][0]);
    let edge = FRONT.windows(2).find(|pair| x <= pair[1][0]).unwrap_or(&FRONT[FRONT.len() - 2..]);
    let front = edge[0][1] + (edge[1][1] - edge[0][1]) * (x - edge[0][0]) / (edge[1][0] - edge[0][0]);
    let outside_x = (local.x.abs() - 9.5).max(0.0);
    let outside_y = (local.y - 6.8).max(front - local.y).max(0.0);
    let inside = local.x.abs() <= 9.5 && local.y <= 6.8 && local.y >= front;
    let distance = DVec2::new(outside_x, outside_y).length();
    let reach = match kind {
        ScatterKind::Tree => {
            let roof_x = (local.x.abs() - 6.25).max(0.0);
            let roof_y = (local.y - 4.15).max(-5.45 - local.y).max(0.0);
            return inside || distance < 3.0 || DVec2::new(roof_x, roof_y).length() < 5.5 * plant.scale * 0.6 + 0.5;
        }
        ScatterKind::Grass => 0.52 * plant.scale,
        ScatterKind::Bush => match plant.model {
            "plants/green-bush-a" => 1.88 * plant.scale + 0.18,
            "plants/green-bush-b" => 1.48 * plant.scale + 0.18,
            "plants/ochre-bush-a" => 1.98 * plant.scale + 0.18,
            "plants/ochre-bush-b" => 1.58 * plant.scale + 0.18,
            "plants/flower-bush-a" => 1.75 * plant.scale + 0.18,
            "plants/flower-bush-b" => 1.45 * plant.scale + 0.18,
            _ => panic!("no surveyed reach for bush {}", plant.model),
        },
    };
    let verge = local.x.abs() <= 10.5 && local.y < front && local.y > front - 2.4 - reach;
    inside || distance < 2.4 + reach || verge
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn source_scatter_rules_match_reference_candidates() {
        // Expected decisions were sampled independently from the original house scatter rules.
        let cases = [
            ("plants/maple-a", ScatterKind::Tree, 0.0, 0.0, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, 12.4, 0.0, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, 12.6, 0.0, 1.0, false),
            ("plants/maple-a", ScatterKind::Tree, 13.4, 0.0, 1.0, false),
            ("plants/maple-a", ScatterKind::Tree, 14.1, 0.0, 1.0, false),
            ("plants/maple-a", ScatterKind::Tree, 0.0, -13.0, 0.6, false),
            ("plants/maple-a", ScatterKind::Tree, 0.0, -14.0, 1.3, false),
            ("plants/maple-a", ScatterKind::Tree, 0.0, 9.7, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, 0.0, 10.6, 1.0, false),
            ("plants/green-bush-a", ScatterKind::Bush, 0.0, 0.0, 1.0, true),
            ("plants/green-bush-a", ScatterKind::Bush, 12.4, 0.0, 1.0, true),
            ("plants/green-bush-a", ScatterKind::Bush, 12.6, 0.0, 1.0, true),
            ("plants/green-bush-a", ScatterKind::Bush, 13.4, 0.0, 1.0, true),
            ("plants/green-bush-a", ScatterKind::Bush, 14.1, 0.0, 1.0, false),
            ("plants/green-bush-a", ScatterKind::Bush, 0.0, -13.0, 0.6, true),
            ("plants/green-bush-a", ScatterKind::Bush, 0.0, -14.0, 1.3, true),
            ("plants/green-bush-a", ScatterKind::Bush, 0.0, 9.7, 1.0, true),
            ("plants/green-bush-a", ScatterKind::Bush, 0.0, 10.6, 1.0, true),
            ("plants/green-bush-b", ScatterKind::Bush, 0.0, 0.0, 1.0, true),
            ("plants/green-bush-b", ScatterKind::Bush, 12.4, 0.0, 1.0, true),
            ("plants/green-bush-b", ScatterKind::Bush, 12.6, 0.0, 1.0, true),
            ("plants/green-bush-b", ScatterKind::Bush, 13.4, 0.0, 1.0, true),
            ("plants/green-bush-b", ScatterKind::Bush, 14.1, 0.0, 1.0, false),
            ("plants/green-bush-b", ScatterKind::Bush, 0.0, -13.0, 0.6, true),
            ("plants/green-bush-b", ScatterKind::Bush, 0.0, -14.0, 1.3, true),
            ("plants/green-bush-b", ScatterKind::Bush, 0.0, 9.7, 1.0, true),
            ("plants/green-bush-b", ScatterKind::Bush, 0.0, 10.6, 1.0, true),
            ("plants/ochre-bush-a", ScatterKind::Bush, 0.0, 0.0, 1.0, true),
            ("plants/ochre-bush-a", ScatterKind::Bush, 12.4, 0.0, 1.0, true),
            ("plants/ochre-bush-a", ScatterKind::Bush, 12.6, 0.0, 1.0, true),
            ("plants/ochre-bush-a", ScatterKind::Bush, 13.4, 0.0, 1.0, true),
            ("plants/ochre-bush-a", ScatterKind::Bush, 14.1, 0.0, 1.0, false),
            ("plants/ochre-bush-a", ScatterKind::Bush, 0.0, -13.0, 0.6, true),
            ("plants/ochre-bush-a", ScatterKind::Bush, 0.0, -14.0, 1.3, true),
            ("plants/ochre-bush-a", ScatterKind::Bush, 0.0, 9.7, 1.0, true),
            ("plants/ochre-bush-a", ScatterKind::Bush, 0.0, 10.6, 1.0, true),
            ("plants/ochre-bush-b", ScatterKind::Bush, 0.0, 0.0, 1.0, true),
            ("plants/ochre-bush-b", ScatterKind::Bush, 12.4, 0.0, 1.0, true),
            ("plants/ochre-bush-b", ScatterKind::Bush, 12.6, 0.0, 1.0, true),
            ("plants/ochre-bush-b", ScatterKind::Bush, 13.4, 0.0, 1.0, true),
            ("plants/ochre-bush-b", ScatterKind::Bush, 14.1, 0.0, 1.0, false),
            ("plants/ochre-bush-b", ScatterKind::Bush, 0.0, -13.0, 0.6, true),
            ("plants/ochre-bush-b", ScatterKind::Bush, 0.0, -14.0, 1.3, true),
            ("plants/ochre-bush-b", ScatterKind::Bush, 0.0, 9.7, 1.0, true),
            ("plants/ochre-bush-b", ScatterKind::Bush, 0.0, 10.6, 1.0, true),
            ("plants/flower-bush-a", ScatterKind::Bush, 0.0, 0.0, 1.0, true),
            ("plants/flower-bush-a", ScatterKind::Bush, 12.4, 0.0, 1.0, true),
            ("plants/flower-bush-a", ScatterKind::Bush, 12.6, 0.0, 1.0, true),
            ("plants/flower-bush-a", ScatterKind::Bush, 13.4, 0.0, 1.0, true),
            ("plants/flower-bush-a", ScatterKind::Bush, 14.1, 0.0, 1.0, false),
            ("plants/flower-bush-a", ScatterKind::Bush, 0.0, -13.0, 0.6, true),
            ("plants/flower-bush-a", ScatterKind::Bush, 0.0, -14.0, 1.3, true),
            ("plants/flower-bush-a", ScatterKind::Bush, 0.0, 9.7, 1.0, true),
            ("plants/flower-bush-a", ScatterKind::Bush, 0.0, 10.6, 1.0, true),
            ("plants/flower-bush-b", ScatterKind::Bush, 0.0, 0.0, 1.0, true),
            ("plants/flower-bush-b", ScatterKind::Bush, 12.4, 0.0, 1.0, true),
            ("plants/flower-bush-b", ScatterKind::Bush, 12.6, 0.0, 1.0, true),
            ("plants/flower-bush-b", ScatterKind::Bush, 13.4, 0.0, 1.0, true),
            ("plants/flower-bush-b", ScatterKind::Bush, 14.1, 0.0, 1.0, false),
            ("plants/flower-bush-b", ScatterKind::Bush, 0.0, -13.0, 0.6, true),
            ("plants/flower-bush-b", ScatterKind::Bush, 0.0, -14.0, 1.3, true),
            ("plants/flower-bush-b", ScatterKind::Bush, 0.0, 9.7, 1.0, true),
            ("plants/flower-bush-b", ScatterKind::Bush, 0.0, 10.6, 1.0, true),
            ("plants/grass-a", ScatterKind::Grass, 0.0, 0.0, 1.0, true),
            ("plants/grass-a", ScatterKind::Grass, 12.4, 0.0, 1.0, true),
            ("plants/grass-a", ScatterKind::Grass, 12.6, 0.0, 1.0, false),
            ("plants/grass-a", ScatterKind::Grass, 13.4, 0.0, 1.0, false),
            ("plants/grass-a", ScatterKind::Grass, 14.1, 0.0, 1.0, false),
            ("plants/grass-a", ScatterKind::Grass, 0.0, -13.0, 0.6, false),
            ("plants/grass-a", ScatterKind::Grass, 0.0, -14.0, 1.3, false),
            ("plants/grass-a", ScatterKind::Grass, 0.0, 9.7, 1.0, true),
            ("plants/grass-a", ScatterKind::Grass, 0.0, 10.6, 1.0, false),
            ("plants/grass-b", ScatterKind::Grass, 0.0, 0.0, 1.0, true),
            ("plants/grass-b", ScatterKind::Grass, 12.4, 0.0, 1.0, true),
            ("plants/grass-b", ScatterKind::Grass, 12.6, 0.0, 1.0, false),
            ("plants/grass-b", ScatterKind::Grass, 13.4, 0.0, 1.0, false),
            ("plants/grass-b", ScatterKind::Grass, 14.1, 0.0, 1.0, false),
            ("plants/grass-b", ScatterKind::Grass, 0.0, -13.0, 0.6, false),
            ("plants/grass-b", ScatterKind::Grass, 0.0, -14.0, 1.3, false),
            ("plants/grass-b", ScatterKind::Grass, 0.0, 9.7, 1.0, true),
            ("plants/grass-b", ScatterKind::Grass, 0.0, 10.6, 1.0, false),
        ];
        for (model, kind, x, y, scale, expected) in cases {
            let plant = Placement { model, at: world(DVec2::new(x, y)), yaw: 0.0, scale, afar: true };
            assert_eq!(blocked(kind, &plant), expected, "{model} at ({x}, {y}) scale {scale}");
        }
    }
}
