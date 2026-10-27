//! Exact source garden and backdrop dressing for all five lots.
use crate::world::scenery::{Land, Placement, ScatterKind};
use glam::DVec2;

// World positions, elevations, headings and scales are the original authored instance values.
const SOURCE: [(&str, [f64; 2], f64, f64, f64); 55] = [
    ("props/stone-lantern", [-193.83, -99.49], 8.71, -161.6_f64, 0.8),
    ("plants/garden-pine-b", [-191.02, -100.54], 8.63, 323.0_f64, 0.42),
    ("plants/garden-maple-b", [-190.05, -99.22], 8.63, 279.2_f64, 0.5),
    ("plants/garden-green-b", [-192.21, -98.6], 8.66, 81.1_f64, 0.55),
    ("props/garden-rock", [-192.88, -98.8], 8.62, 108.1_f64, 0.3),
    ("props/garden-rock", [-192.23, -99.23], 8.62, 314.5_f64, 0.22),
    ("props/garden-rock", [-191.13, -100.16], 8.62, 1.9_f64, 0.26),
    ("plants/garden-flower-b", [-205.8, -102.0], 8.63, 295.6_f64, 0.7),
    ("plants/garden-pine-a", [-186.94, -117.62], 5.46, 109.1_f64, 1.141),
    ("plants/garden-cedar-b", [-192.9, -119.34], 5.44, 181.6_f64, 1.033),
    ("plants/garden-maple-a", [-200.21, -122.03], 5.09, 224.0_f64, 1.043),
    ("props/stone-lantern", [-157.28, -73.43], 9.88, 11.7_f64, 0.8),
    ("plants/garden-pine-b", [-160.09, -72.37], 9.8, 57.7_f64, 0.42),
    ("plants/garden-maple-b", [-161.06, -73.7], 9.8, 220.5_f64, 0.5),
    ("plants/garden-green-b", [-158.9, -74.32], 9.83, 15.8_f64, 0.55),
    ("props/garden-rock", [-158.23, -74.12], 9.79, 12.8_f64, 0.3),
    ("props/garden-rock", [-158.87, -73.69], 9.79, 185.4_f64, 0.22),
    ("props/garden-rock", [-159.98, -72.76], 9.79, 167.8_f64, 0.26),
    ("plants/garden-flower-b", [-145.31, -70.9], 9.8, 330.2_f64, 0.7),
    ("plants/garden-pine-a", [-164.36, -55.96], 11.75, 178.9_f64, 1.135),
    ("plants/garden-cedar-b", [-158.45, -54.74], 11.32, 249.1_f64, 0.98),
    ("plants/garden-maple-a", [-151.78, -53.08], 11.07, 298.8_f64, 0.925),
    ("props/stone-lantern", [-127.77, -65.37], 10.68, 8.2_f64, 0.8),
    ("plants/garden-pine-b", [-130.49, -64.1], 10.6, 316.9_f64, 0.42),
    ("plants/garden-maple-b", [-131.55, -65.35], 10.6, 183.5_f64, 0.5),
    ("plants/garden-green-b", [-129.45, -66.13], 10.63, 305.0_f64, 0.55),
    ("props/garden-rock", [-128.76, -65.99], 10.59, 230.3_f64, 0.3),
    ("props/garden-rock", [-129.37, -65.5], 10.59, 267.0_f64, 0.22),
    ("props/garden-rock", [-130.4, -64.5], 10.59, 32.9_f64, 0.26),
    ("plants/garden-flower-b", [-115.62, -63.84], 10.6, 194.8_f64, 0.7),
    ("plants/garden-pine-a", [-133.9, -46.85], 13.04, 130.1_f64, 1.196),
    ("plants/garden-cedar-b", [-127.46, -46.24], 12.38, 116.3_f64, 0.973),
    ("plants/garden-maple-a", [-119.81, -44.64], 12.37, 352.3_f64, 0.987),
    ("props/stone-lantern", [28.15, -46.92], 16.42, -161.6_f64, 0.8),
    ("plants/garden-pine-b", [30.97, -47.96], 16.34, 229.7_f64, 0.42),
    ("plants/garden-maple-b", [31.93, -46.62], 16.34, 243.5_f64, 0.5),
    ("plants/garden-green-b", [29.76, -46.02], 16.37, 54.3_f64, 0.55),
    ("props/garden-rock", [29.09, -46.22], 16.33, 158.5_f64, 0.3),
    ("props/garden-rock", [29.74, -46.65], 16.33, 86.2_f64, 0.22),
    ("props/garden-rock", [30.85, -47.57], 16.33, 144.9_f64, 0.26),
    ("plants/garden-flower-b", [16.22, -49.59], 16.34, 34.8_f64, 0.7),
    ("plants/garden-pine-a", [34.61, -64.69], 14.1, 241.8_f64, 1.144),
    ("plants/garden-cedar-b", [27.83, -67.42], 13.78, 47.4_f64, 1.077),
    ("plants/garden-maple-a", [22.03, -69.54], 13.49, 205.1_f64, 0.923),
    ("props/stone-lantern", [45.12, -27.02], 17.29, 7.5_f64, 0.8),
    ("plants/garden-pine-b", [42.39, -25.78], 17.21, 334.0_f64, 0.42),
    ("plants/garden-maple-b", [41.33, -27.04], 17.21, 198.8_f64, 0.5),
    ("plants/garden-green-b", [43.45, -27.8], 17.24, 65.0_f64, 0.55),
    ("props/garden-rock", [44.13, -27.65], 17.2, 318.3_f64, 0.3),
    ("props/garden-rock", [43.51, -27.17], 17.2, 231.0_f64, 0.22),
    ("props/garden-rock", [42.47, -26.17], 17.2, 205.1_f64, 0.26),
    ("plants/garden-flower-b", [57.23, -25.32], 17.21, 135.5_f64, 0.7),
    ("plants/garden-pine-a", [38.81, -9.56], 18.79, 13.7_f64, 1.244),
    ("plants/garden-cedar-b", [46.17, -7.47], 19.18, 116.0_f64, 1.063),
    ("plants/garden-maple-a", [51.04, -6.67], 18.97, 10.9_f64, 0.92),
];

pub fn placements(land: &Land) -> Vec<Placement> {
    SOURCE
        .into_iter()
        .map(|(model, at, z, yaw, scale)| {
            let at = DVec2::from_array(at);
            // Preserve the published origin independently of terrain detail.
            let stored = at.as_vec2().as_dvec2();
            let _seat = land.height(stored).expect("source dressing stands on exported terrain");
            Placement {
                model,
                at,
                yaw: yaw.to_radians(),
                scale,
                origin_offset_m: 0.0,
                origin_height_m: Some(z),
                afar: true,
            }
        })
        .collect()
}

/// The original lantern clearance tests an oriented 0.7 m source footprint and scaled plant reach.
pub fn lantern_blocks(kind: ScatterKind, plant: &Placement) -> bool {
    let reach = super::scatter_radius(kind, plant.model) * plant.scale + 0.18;
    SOURCE.iter().filter(|(model, _, _, _, _)| *model == "props/stone-lantern").any(|(_, at, _, yaw, scale)| {
        let local = DVec2::from_angle(-yaw.to_radians()).rotate(plant.at - DVec2::from_array(*at));
        let delta = (local.abs() - DVec2::splat(0.35 * scale)).max(DVec2::ZERO);
        delta.length() < reach
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn lantern_clearance_matches_original_footprints() {
        let cases = [
            ("plants/maple-a", ScatterKind::Tree, -194.0197752023289, -99.55312980738941, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, -194.68398841048005, -99.77408413325239, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, -194.9686512139734, -99.86877884433652, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, -195.44308921979567, -100.02660336281006, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, -195.727752023289, -100.1212980738942, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, -199.23859326637364, -101.28919951059848, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, -199.61814367103145, -101.41545912537732, 1.0, false),
            ("plants/green-bush-b", ScatterKind::Bush, -194.0197752023289, -99.55312980738941, 0.55, true),
            ("plants/green-bush-b", ScatterKind::Bush, -194.68398841048005, -99.77408413325239, 0.55, true),
            ("plants/green-bush-b", ScatterKind::Bush, -194.9686512139734, -99.86877884433652, 0.55, true),
            ("plants/green-bush-b", ScatterKind::Bush, -195.44308921979567, -100.02660336281006, 0.55, false),
            ("plants/green-bush-b", ScatterKind::Bush, -195.727752023289, -100.1212980738942, 0.55, false),
            ("plants/green-bush-b", ScatterKind::Bush, -199.23859326637364, -101.28919951059848, 0.55, false),
            ("plants/green-bush-b", ScatterKind::Bush, -199.61814367103145, -101.41545912537732, 0.55, false),
            ("plants/grass-a", ScatterKind::Grass, -194.0197752023289, -99.55312980738941, 1.0, true),
            ("plants/grass-a", ScatterKind::Grass, -194.68398841048005, -99.77408413325239, 1.0, true),
            ("plants/grass-a", ScatterKind::Grass, -194.9686512139734, -99.86877884433652, 1.0, false),
            ("plants/grass-a", ScatterKind::Grass, -195.44308921979567, -100.02660336281006, 1.0, false),
            ("plants/grass-a", ScatterKind::Grass, -195.727752023289, -100.1212980738942, 1.0, false),
            ("plants/grass-a", ScatterKind::Grass, -199.23859326637364, -101.28919951059848, 1.0, false),
            ("plants/grass-a", ScatterKind::Grass, -199.61814367103145, -101.41545912537732, 1.0, false),
            ("plants/maple-a", ScatterKind::Tree, -157.08415543787564, -73.3894425409287, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, -156.39869947044042, -73.24749143417914, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, -156.10493262725387, -73.1866552455722, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, -155.615321221943, -73.08526159789393, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, -155.32155437875647, -73.02442540928698, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, -151.69842997945594, -72.27411241646789, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, -151.30674085520724, -72.19299749832528, 1.0, false),
            ("plants/green-bush-b", ScatterKind::Bush, -157.08415543787564, -73.3894425409287, 0.55, true),
            ("plants/green-bush-b", ScatterKind::Bush, -156.39869947044042, -73.24749143417914, 0.55, true),
            ("plants/green-bush-b", ScatterKind::Bush, -156.10493262725387, -73.1866552455722, 0.55, true),
            ("plants/green-bush-b", ScatterKind::Bush, -155.615321221943, -73.08526159789393, 0.55, false),
            ("plants/green-bush-b", ScatterKind::Bush, -155.32155437875647, -73.02442540928698, 0.55, false),
            ("plants/green-bush-b", ScatterKind::Bush, -151.69842997945594, -72.27411241646789, 0.55, false),
            ("plants/green-bush-b", ScatterKind::Bush, -151.30674085520724, -72.19299749832528, 0.55, false),
            ("plants/grass-a", ScatterKind::Grass, -157.08415543787564, -73.3894425409287, 1.0, true),
            ("plants/grass-a", ScatterKind::Grass, -156.39869947044042, -73.24749143417914, 1.0, true),
            ("plants/grass-a", ScatterKind::Grass, -156.10493262725387, -73.1866552455722, 1.0, false),
            ("plants/grass-a", ScatterKind::Grass, -155.615321221943, -73.08526159789393, 1.0, false),
            ("plants/grass-a", ScatterKind::Grass, -155.32155437875647, -73.02442540928698, 1.0, false),
            ("plants/grass-a", ScatterKind::Grass, -151.69842997945594, -72.27411241646789, 1.0, false),
            ("plants/grass-a", ScatterKind::Grass, -151.30674085520724, -72.19299749832528, 1.0, false),
            ("plants/maple-a", ScatterKind::Tree, -127.57204475381843, -65.3414742132589, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, -126.87920139218299, -65.24163395966504, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, -126.58226852291065, -65.1988452795534, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, -126.08738040745675, -65.12753081270064, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, -125.79044753818442, -65.08474213258899, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, -122.1282754838256, -64.55701507787859, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, -121.73236499146249, -64.49996350439639, 1.0, false),
            ("plants/green-bush-b", ScatterKind::Bush, -127.57204475381843, -65.3414742132589, 0.55, true),
            ("plants/green-bush-b", ScatterKind::Bush, -126.87920139218299, -65.24163395966504, 0.55, true),
            ("plants/green-bush-b", ScatterKind::Bush, -126.58226852291065, -65.1988452795534, 0.55, true),
            ("plants/green-bush-b", ScatterKind::Bush, -126.08738040745675, -65.12753081270064, 0.55, false),
            ("plants/green-bush-b", ScatterKind::Bush, -125.79044753818442, -65.08474213258899, 0.55, false),
            ("plants/green-bush-b", ScatterKind::Bush, -122.1282754838256, -64.55701507787859, 0.55, false),
            ("plants/green-bush-b", ScatterKind::Bush, -121.73236499146249, -64.49996350439639, 0.55, false),
            ("plants/grass-a", ScatterKind::Grass, -127.57204475381843, -65.3414742132589, 1.0, true),
            ("plants/grass-a", ScatterKind::Grass, -126.87920139218299, -65.24163395966504, 1.0, true),
            ("plants/grass-a", ScatterKind::Grass, -126.58226852291065, -65.1988452795534, 1.0, false),
            ("plants/grass-a", ScatterKind::Grass, -126.08738040745675, -65.12753081270064, 1.0, false),
            ("plants/grass-a", ScatterKind::Grass, -125.79044753818442, -65.08474213258899, 1.0, false),
            ("plants/grass-a", ScatterKind::Grass, -122.1282754838256, -64.55701507787859, 1.0, false),
            ("plants/grass-a", ScatterKind::Grass, -121.73236499146249, -64.49996350439639, 1.0, false),
            ("plants/maple-a", ScatterKind::Tree, 27.9602247976711, -46.983129807389425, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, 27.296011589519953, -47.204084133252394, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, 27.011348786026602, -47.298778844336525, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, 26.536910780204355, -47.45660336281008, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, 26.252247976711004, -47.55129807389421, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, 22.74140673362637, -48.719199510598486, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, 22.36185632896857, -48.845459125377324, 1.0, false),
            ("plants/green-bush-b", ScatterKind::Bush, 27.9602247976711, -46.983129807389425, 0.55, true),
            ("plants/green-bush-b", ScatterKind::Bush, 27.296011589519953, -47.204084133252394, 0.55, true),
            ("plants/green-bush-b", ScatterKind::Bush, 27.011348786026602, -47.298778844336525, 0.55, true),
            ("plants/green-bush-b", ScatterKind::Bush, 26.536910780204355, -47.45660336281008, 0.55, false),
            ("plants/green-bush-b", ScatterKind::Bush, 26.252247976711004, -47.55129807389421, 0.55, false),
            ("plants/green-bush-b", ScatterKind::Bush, 22.74140673362637, -48.719199510598486, 0.55, false),
            ("plants/green-bush-b", ScatterKind::Bush, 22.36185632896857, -48.845459125377324, 0.55, false),
            ("plants/grass-a", ScatterKind::Grass, 27.9602247976711, -46.983129807389425, 1.0, true),
            ("plants/grass-a", ScatterKind::Grass, 27.296011589519953, -47.204084133252394, 1.0, true),
            ("plants/grass-a", ScatterKind::Grass, 27.011348786026602, -47.298778844336525, 1.0, false),
            ("plants/grass-a", ScatterKind::Grass, 26.536910780204355, -47.45660336281008, 1.0, false),
            ("plants/grass-a", ScatterKind::Grass, 26.252247976711004, -47.55129807389421, 1.0, false),
            ("plants/grass-a", ScatterKind::Grass, 22.74140673362637, -48.719199510598486, 1.0, false),
            ("plants/grass-a", ScatterKind::Grass, 22.36185632896857, -48.845459125377324, 1.0, false),
            ("plants/maple-a", ScatterKind::Tree, 45.31828897227476, -26.99389476155599, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, 46.01230037523643, -26.902526427001952, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, 46.30973383364857, -26.863368569335936, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, 46.805456264335476, -26.798105473225913, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, 47.10288972274762, -26.758947615559897, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, 50.77123570983072, -26.276000704345705, 1.0, true),
            ("plants/maple-a", ScatterKind::Tree, 51.16781365438024, -26.223790227457684, 1.0, false),
            ("plants/green-bush-b", ScatterKind::Bush, 45.31828897227476, -26.99389476155599, 0.55, true),
            ("plants/green-bush-b", ScatterKind::Bush, 46.01230037523643, -26.902526427001952, 0.55, true),
            ("plants/green-bush-b", ScatterKind::Bush, 46.30973383364857, -26.863368569335936, 0.55, true),
            ("plants/green-bush-b", ScatterKind::Bush, 46.805456264335476, -26.798105473225913, 0.55, false),
            ("plants/green-bush-b", ScatterKind::Bush, 47.10288972274762, -26.758947615559897, 0.55, false),
            ("plants/green-bush-b", ScatterKind::Bush, 50.77123570983072, -26.276000704345705, 0.55, false),
            ("plants/green-bush-b", ScatterKind::Bush, 51.16781365438024, -26.223790227457684, 0.55, false),
            ("plants/grass-a", ScatterKind::Grass, 45.31828897227476, -26.99389476155599, 1.0, true),
            ("plants/grass-a", ScatterKind::Grass, 46.01230037523643, -26.902526427001952, 1.0, true),
            ("plants/grass-a", ScatterKind::Grass, 46.30973383364857, -26.863368569335936, 1.0, false),
            ("plants/grass-a", ScatterKind::Grass, 46.805456264335476, -26.798105473225913, 1.0, false),
            ("plants/grass-a", ScatterKind::Grass, 47.10288972274762, -26.758947615559897, 1.0, false),
            ("plants/grass-a", ScatterKind::Grass, 50.77123570983072, -26.276000704345705, 1.0, false),
            ("plants/grass-a", ScatterKind::Grass, 51.16781365438024, -26.223790227457684, 1.0, false),
        ];
        for (model, kind, x, y, scale, expected) in cases {
            let plant = Placement {
                model,
                at: DVec2::new(x, y),
                yaw: 0.0,
                scale,
                origin_offset_m: 0.0,
                origin_height_m: None,
                afar: true,
            };
            assert_eq!(lantern_blocks(kind, &plant), expected, "{model} at ({x}, {y})");
        }
    }
}

/// The original tree-house-era scatter retains the five former house roof clearings.
pub fn legacy_tree_blocks(kind: ScatterKind, plant: &Placement) -> bool {
    if kind != ScatterKind::Tree {
        return false;
    }
    let source_frames = [
        ([-196.87, -104.39], 106.4_f64),
        ([-145.01, -89.45], 106.2),
        ([-115.82, -59.72], -81.1),
        ([1.16, -60.41], 114.6),
        ([29.65, -27.58], -74.8),
    ];
    source_frames.into_iter().any(|(centre, yaw)| {
        let local = DVec2::from_angle(-yaw.to_radians()).rotate(plant.at - DVec2::from_array(centre));
        let delta = (local.abs() - DVec2::new(5.65, 4.35)).max(DVec2::ZERO);
        delta.length() < 5.5 * plant.scale + 0.18
    })
}

#[cfg(test)]
mod legacy_tests {
    use super::*;
    #[test]
    fn legacy_tree_clearance_matches_original_frames() {
        let cases = [
            (-196.87, -104.39, 0.6, true),
            (-198.46522923116225, -98.96987604384867, 0.6, true),
            (-199.128731654743, -96.71548820367954, 0.6, true),
            (-199.97575602527164, -93.83754628005937, 0.6, false),
            (-200.25809748211452, -92.8782323055193, 0.6, false),
            (-205.98348275813055, -107.07224384000733, 0.6, false),
            (-207.42245371994065, -107.49575602527165, 0.6, false),
            (-196.87, -104.39, 1.0, true),
            (-198.46522923116225, -98.96987604384867, 1.0, true),
            (-199.128731654743, -96.71548820367954, 1.0, true),
            (-199.97575602527164, -93.83754628005937, 1.0, true),
            (-200.25809748211452, -92.8782323055193, 1.0, false),
            (-205.98348275813055, -107.07224384000733, 1.0, true),
            (-207.42245371994065, -107.49575602527165, 1.0, false),
            (-196.87, -104.39, 1.3, true),
            (-198.46522923116225, -98.96987604384867, 1.3, true),
            (-199.128731654743, -96.71548820367954, 1.3, true),
            (-199.97575602527164, -93.83754628005937, 1.3, true),
            (-200.25809748211452, -92.8782323055193, 1.3, true),
            (-205.98348275813055, -107.07224384000733, 1.3, true),
            (-207.42245371994065, -107.49575602527165, 1.3, true),
            (-145.01, -89.45, 0.6, true),
            (-146.58629974912165, -84.02434067592527, 0.6, true),
            (-147.24192884831382, -81.76765051458446, 0.6, true),
            (-148.0789021664315, -78.88676945755363, 0.6, false),
            (-148.35789327247073, -77.92647577187668, 0.6, false),
            (-154.13279001393096, -92.10041550737269, 0.6, false),
            (-155.57323054244637, -92.51890216643153, 0.6, false),
            (-145.01, -89.45, 1.0, true),
            (-146.58629974912165, -84.02434067592527, 1.0, true),
            (-147.24192884831382, -81.76765051458446, 1.0, true),
            (-148.0789021664315, -78.88676945755363, 1.0, true),
            (-148.35789327247073, -77.92647577187668, 1.0, false),
            (-154.13279001393096, -92.10041550737269, 1.0, true),
            (-155.57323054244637, -92.51890216643153, 1.0, false),
            (-145.01, -89.45, 1.3, true),
            (-146.58629974912165, -84.02434067592527, 1.3, true),
            (-147.24192884831382, -81.76765051458446, 1.3, true),
            (-148.0789021664315, -78.88676945755363, 1.3, true),
            (-148.35789327247073, -77.92647577187668, 1.3, true),
            (-154.13279001393096, -92.10041550737269, 1.3, true),
            (-155.57323054244637, -92.51890216643153, 1.3, true),
            (-115.82, -59.72, 0.6, true),
            (-114.945886317408, -65.30197324159705, 0.6, true),
            (-114.58231690960424, -67.62367892615511, 0.6, true),
            (-114.11818575070585, -70.58755852346329, 0.6, false),
            (-113.96347536440638, -71.57551838923267, 0.6, false),
            (-106.4343812751908, -58.25025133015505, 0.6, false),
            (-104.9524414765367, -58.01818575070585, 0.6, false),
            (-115.82, -59.72, 1.0, true),
            (-114.945886317408, -65.30197324159705, 1.0, true),
            (-114.58231690960424, -67.62367892615511, 1.0, true),
            (-114.11818575070585, -70.58755852346329, 1.0, true),
            (-113.96347536440638, -71.57551838923267, 1.0, false),
            (-106.4343812751908, -58.25025133015505, 1.0, true),
            (-104.9524414765367, -58.01818575070585, 1.0, false),
            (-115.82, -59.72, 1.3, true),
            (-114.945886317408, -65.30197324159705, 1.3, true),
            (-114.58231690960424, -67.62367892615511, 1.3, true),
            (-114.11818575070585, -70.58755852346329, 1.3, true),
            (-113.96347536440638, -71.57551838923267, 1.3, true),
            (-106.4343812751908, -58.25025133015505, 1.3, true),
            (-104.9524414765367, -58.01818575070585, 1.3, true),
            (1.16, -60.41, 0.6, true),
            (-1.1919864762712662, -55.27281598388406, 0.6, true),
            (-2.170246338083208, -53.13611112762345, 0.6, true),
            (-3.4190887148644116, -50.40840280048224, 0.6, false),
            (-3.8353695071248124, -49.49916669143517, 0.6, false),
            (-7.477743035947151, -64.36466752647381, 0.6, false),
            (-8.841597199517755, -64.98908871486441, 0.6, false),
            (1.16, -60.41, 1.0, true),
            (-1.1919864762712662, -55.27281598388406, 1.0, true),
            (-2.170246338083208, -53.13611112762345, 1.0, true),
            (-3.4190887148644116, -50.40840280048224, 1.0, true),
            (-3.8353695071248124, -49.49916669143517, 1.0, false),
            (-7.477743035947151, -64.36466752647381, 1.0, true),
            (-8.841597199517755, -64.98908871486441, 1.0, false),
            (1.16, -60.41, 1.3, true),
            (-1.1919864762712662, -55.27281598388406, 1.3, true),
            (-2.170246338083208, -53.13611112762345, 1.3, true),
            (-3.4190887148644116, -50.40840280048224, 1.3, true),
            (-3.8353695071248124, -49.49916669143517, 1.3, true),
            (-7.477743035947151, -64.36466752647381, 1.3, true),
            (-8.841597199517755, -64.98908871486441, 1.3, true),
            (29.65, -27.58, 0.6, true),
            (31.131368859320883, -33.03234319376856, 0.6, true),
            (31.747513429126915, -35.30013195577849, 0.6, true),
            (32.53408096504951, -38.19518143919542, 0.6, false),
            (32.79627014369038, -39.16019793366773, 0.6, false),
            (38.81765669748695, -25.089202802911785, 0.6, false),
            (40.26518143919542, -24.695919034950485, 0.6, false),
            (29.65, -27.58, 1.0, true),
            (31.131368859320883, -33.03234319376856, 1.0, true),
            (31.747513429126915, -35.30013195577849, 1.0, true),
            (32.53408096504951, -38.19518143919542, 1.0, true),
            (32.79627014369038, -39.16019793366773, 1.0, false),
            (38.81765669748695, -25.089202802911785, 1.0, true),
            (40.26518143919542, -24.695919034950485, 1.0, false),
            (29.65, -27.58, 1.3, true),
            (31.131368859320883, -33.03234319376856, 1.3, true),
            (31.747513429126915, -35.30013195577849, 1.3, true),
            (32.53408096504951, -38.19518143919542, 1.3, true),
            (32.79627014369038, -39.16019793366773, 1.3, true),
            (38.81765669748695, -25.089202802911785, 1.3, true),
            (40.26518143919542, -24.695919034950485, 1.3, true),
        ];
        for (x, y, scale, expected) in cases {
            let plant = Placement {
                model: "plants/maple-a",
                at: DVec2::new(x, y),
                yaw: 0.0,
                scale,
                origin_offset_m: 0.0,
                origin_height_m: None,
                afar: true,
            };
            assert_eq!(legacy_tree_blocks(ScatterKind::Tree, &plant), expected, "tree at ({x}, {y}) scale {scale}");
            assert!(!legacy_tree_blocks(ScatterKind::Grass, &plant));
        }
    }
}
