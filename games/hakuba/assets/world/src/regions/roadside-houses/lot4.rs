//! The second use of the original roadside house and its authored fourth lot.
use crate::world::raised::{Raised, SurfacePaint};
use crate::world::scenery::{Placement, ScatterKind};
use glam::DVec2;

const CENTRE: [f64; 2] = [26.26, -55.58];
const YAW_DEG: f64 = -163.3;
const LEVEL: f64 = 16.39;
const FRONT: [[f64; 2]; 21] = [
    [-9.5, -9.886],
    [-8.882, -9.9],
    [-7.895, -9.921],
    [-6.907, -9.939],
    [-5.92, -9.955],
    [-4.932, -9.968],
    [-3.944, -9.979],
    [-2.957, -9.987],
    [-1.969, -9.993],
    [-0.981, -9.996],
    [0.007, -9.998],
    [0.994, -9.996],
    [1.982, -9.993],
    [2.97, -9.986],
    [3.957, -9.978],
    [4.945, -9.967],
    [5.933, -9.953],
    [6.921, -9.938],
    [7.909, -9.92],
    [8.897, -9.899],
    [9.5, -9.885],
];
const TOP_VERTICES: [[f64; 4]; 46] = [
    [-9.5, 6.800000190734863, 6.218894004821777, -9.893877983093262],
    [-9.5, -9.435999870300293, 5.441296577453613, -7.302010536193848],
    [-8.881999969482422, 6.800000190734863, 6.120238304138184, -9.923476219177246],
    [-8.881999969482422, -9.449999809265137, 5.341970443725586, -7.329373359680176],
    [-7.894999980926514, 6.800000190734863, 5.962676525115967, -9.970746994018555],
    [-7.894999980926514, -9.470999717712402, 5.183403015136719, -7.373291969299316],
    [-6.9070000648498535, 6.800000190734863, 5.80495548248291, -10.018065452575684],
    [-6.9070000648498535, -9.48900032043457, 5.024819374084473, -7.417737007141113],
    [-5.920000076293945, 6.800000190734863, 5.647393703460693, -10.065336227416992],
    [-5.920000076293945, -9.505000114440918, 4.866491317749023, -7.462453842163086],
    [-4.932000160217285, 6.800000190734863, 5.4896721839904785, -10.112655639648438],
    [-4.932000160217285, -9.517999649047852, 4.708147048950195, -7.507697105407715],
    [-3.944000005722046, 6.800000190734863, 5.331950664520264, -10.159974098205566],
    [-3.944000005722046, -9.529000282287598, 4.549899101257324, -7.55325984954834],
    [-2.9570000171661377, 6.800000190734863, 5.174388885498047, -10.207244873046875],
    [-2.9570000171661377, -9.536999702453613, 4.391953945159912, -7.5992536544799805],
    [-1.968999981880188, 6.800000190734863, 5.016667366027832, -10.254563331604004],
    [-1.968999981880188, -9.543000221252441, 4.233945369720459, -7.6456146240234375],
    [-0.9810000061988831, 6.800000190734863, 4.858945846557617, -10.301881790161133],
    [-0.9810000061988831, -9.545999526977539, 4.076079845428467, -7.6924543380737305],
    [0.007000000216066837, 6.800000190734863, 4.701224327087402, -10.349201202392578],
    [0.007000000216066837, -9.54800033569336, 3.9182627201080322, -7.7394537925720215],
    [0.9940000176429749, -9.545999526977539, 3.7607967853546143, -7.787044048309326],
    [0.9940000176429749, 6.800000190734863, 4.5436625480651855, -10.396471977233887],
    [1.850000023841858, -9.543400764465332, 3.624271869659424, -7.828455448150635],
    [1.850000023841858, 6.800000190734863, 4.407013416290283, -10.437468528747559],
    [1.9819999933242798, -9.543000221252441, 3.6032190322875977, -7.834841251373291],
    [1.9819999933242798, 6.800000190734863, 4.385941028594971, -10.443790435791016],
    [2.9700000286102295, -9.53600025177002, 3.4458329677581787, -7.883277416229248],
    [2.9700000286102295, 6.800000190734863, 4.228219985961914, -10.491108894348145],
    [3.75, -9.529677391052246, 3.3216187953948975, -7.9216437339782715],
    [3.75, 6.800000190734863, 4.103703022003174, -10.52846622467041],
    [3.9570000171661377, -9.527999877929688, 3.288654327392578, -7.931825637817383],
    [3.9570000171661377, 6.800000190734863, 4.070658206939697, -10.538379669189453],
    [4.945000171661377, -9.517000198364258, 3.1314594745635986, -7.980900287628174],
    [4.945000171661377, 6.800000190734863, 3.9129364490509033, -10.585698127746582],
    [5.933000087738037, -9.503000259399414, 2.9744086265563965, -8.0304536819458],
    [5.933000087738037, 6.800000190734863, 3.7552151679992676, -10.633017539978027],
    [6.921000003814697, -9.48799991607666, 2.8174057006835938, -8.080166816711426],
    [6.921000003814697, 6.800000190734863, 3.5974936485290527, -10.680335998535156],
    [7.908999919891357, -9.470000267028809, 2.66054630279541, -8.130359649658203],
    [7.908999919891357, 6.800000190734863, 3.439772367477417, -10.727654457092285],
    [8.897000312805176, -9.449000358581543, 2.5038304328918457, -8.1810302734375],
    [8.897000312805176, 6.800000190734863, 3.282050848007202, -10.774972915649414],
    [9.5, -9.4350004196167, 2.4082398414611816, -8.21214485168457],
    [9.5, 6.800000190734863, 3.1857895851135254, -10.803853034973145],
];

const TOP_TRIANGLES: [[usize; 3]; 44] = [
    [0, 1, 2],
    [2, 1, 3],
    [2, 3, 4],
    [4, 3, 5],
    [4, 5, 6],
    [6, 5, 7],
    [6, 7, 8],
    [8, 7, 9],
    [8, 9, 10],
    [10, 9, 11],
    [10, 11, 12],
    [12, 11, 13],
    [12, 13, 14],
    [14, 13, 15],
    [14, 15, 16],
    [16, 15, 17],
    [16, 17, 18],
    [18, 17, 19],
    [18, 19, 20],
    [20, 19, 21],
    [20, 22, 23],
    [22, 20, 21],
    [23, 24, 25],
    [24, 23, 22],
    [25, 26, 27],
    [26, 25, 24],
    [27, 28, 29],
    [28, 27, 26],
    [29, 30, 31],
    [30, 29, 28],
    [31, 32, 33],
    [32, 31, 30],
    [33, 34, 35],
    [34, 33, 32],
    [35, 36, 37],
    [36, 35, 34],
    [37, 38, 39],
    [38, 37, 36],
    [39, 40, 41],
    [40, 39, 38],
    [41, 42, 43],
    [42, 41, 40],
    [43, 44, 45],
    [44, 43, 42],
];

fn world(local: DVec2) -> DVec2 {
    DVec2::from_array(CENTRE) + DVec2::from_angle(YAW_DEG.to_radians()).rotate(local)
}

/// The original stored Ground triangles and their source UVs.
pub fn top() -> Raised {
    let triangles = TOP_TRIANGLES
        .iter()
        .map(|triangle| {
            triangle.map(|index| {
                let [x, y, u, v] = TOP_VERTICES[index];
                (world(DVec2::new(x, y)), DVec2::new(u, v))
            })
        })
        .collect();
    Raised {
        name: "fourth roadside terrace".into(),
        texture: "road-house-ground".into(),
        ground: true,
        paint: Some(SurfacePaint { haze_start_m: 30.0, haze_length_m: 9000.0, haze_colour: [0.0932, 0.2301, 0.5328] }),
        height: LEVEL,
        clearance: 0.01,
        cut_ground: true,
        triangles,
    }
}

/// The house and lot share their original source placement.
pub fn placements() -> [Placement; 2] {
    ["props/road-house-a", "props/road-house-lot-4"].map(|model| Placement {
        model,
        at: DVec2::from_array(CENTRE),
        yaw: YAW_DEG.to_radians(),
        scale: 1.0,
        origin_offset_m: 0.0,
        origin_height_m: None,
        afar: true,
    })
}

/// Apply the surveyed lot boundary and original scatter reach rules.
pub fn blocked(kind: ScatterKind, plant: &Placement) -> bool {
    super::blocked_for(&FRONT, CENTRE, YAW_DEG, [-6.25, 6.25, -5.45, 4.15], 2.4, kind, plant)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn source_scatter_rule_matches_original_candidates() {
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
            let plant = Placement {
                model,
                at: world(DVec2::new(x, y)),
                yaw: 0.0,
                scale,
                origin_offset_m: 0.0,
                origin_height_m: None,
                afar: true,
            };
            assert_eq!(blocked(kind, &plant), expected, "{model} at ({x},{y}) scale {scale}");
        }
    }
}
