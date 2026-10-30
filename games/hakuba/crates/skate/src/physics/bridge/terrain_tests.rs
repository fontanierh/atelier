//! Offline ride regressions against the exported simulation package and real test meshes.
use super::*;
use std::sync::OnceLock;
type Triangle = [[f32; 3]; 3];

fn package() -> &'static [u8] {
    static BYTES: OnceLock<Vec<u8>> = OnceLock::new();
    BYTES.get_or_init(|| {
        std::fs::read(
            std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("../../assets/simulations/skate-simulation/skate-simulation.skatepack"),
        )
        .expect("export the simulation asset before running offline terrain regressions")
    })
}
fn quad(a: [f32; 3], b: [f32; 3], c: [f32; 3], d: [f32; 3]) -> Vec<Triangle> {
    vec![[a, b, c], [a, c, d]]
}
fn flat() -> Vec<Triangle> {
    quad([-4., 0., -40.], [-4., 0., 80.], [4., 0., 80.], [4., 0., -40.])
}
fn quarter() -> Vec<Triangle> {
    let mut tris = quad([-20., 0., -40.], [-20., 0., 10.], [20., 0., 10.], [20., 0., -40.]);
    let mut points: Vec<_> = (0..=32)
        .map(|i| {
            let a = i as f32 * std::f32::consts::FRAC_PI_2 / 32.;
            (10. + 3. * a.sin(), 3. - 3. * a.cos())
        })
        .collect();
    points.push((13., 3.3));
    for pair in points.windows(2) {
        let (za, ya) = pair[0];
        let (zb, yb) = pair[1];
        tris.extend(quad([-20., ya, za], [-20., yb, zb], [20., yb, zb], [20., ya, za]));
    }
    tris.extend(quad([-20., 3.3, 13.], [-20., 3.3, 16.], [20., 3.3, 16.], [20., 3.3, 13.]));
    tris
}
fn box_mesh(cx: f32, cy: f32, cz: f32, w: f32, h: f32, d: f32, bevel: f32) -> Vec<Triangle> {
    let b = bevel.min(w / 3.).min(d / 3.).min(h / 3.);
    if b == 0. {
        let (x0, x1, y0, y1, z0, z1) = (cx - w / 2., cx + w / 2., cy - h / 2., cy + h / 2., cz - d / 2., cz + d / 2.);
        let mut tris = quad([x0, y1, z0], [x0, y1, z1], [x1, y1, z1], [x1, y1, z0]);
        tris.extend(quad([x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1]));
        tris.extend(quad([x0, y0, z0], [x0, y1, z0], [x1, y1, z0], [x1, y0, z0]));
        tris.extend(quad([x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]));
        tris.extend(quad([x0, y0, z0], [x0, y0, z1], [x0, y1, z1], [x0, y1, z0]));
        tris.extend(quad([x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1]));
        return tris;
    }
    let ring = |y, s| {
        [
            (-w / 2. + b, -d / 2.),
            (w / 2. - b, -d / 2.),
            (w / 2., -d / 2. + b),
            (w / 2., d / 2. - b),
            (w / 2. - b, d / 2.),
            (-w / 2. + b, d / 2.),
            (-w / 2., d / 2. - b),
            (-w / 2., -d / 2. + b),
        ]
        .map(|(x, z)| [cx + x * s, cy + y, cz + z * s])
    };
    let rings = [ring(-h / 2., 0.94), ring(-h / 2. + b, 1.), ring(h / 2. - b, 1.), ring(h / 2., 0.94)];
    let mut tris = Vec::new();
    for k in 1..7 {
        tris.push([rings[3][0], rings[3][k + 1], rings[3][k]]);
        tris.push([rings[0][0], rings[0][k], rings[0][k + 1]]);
    }
    for pair in rings.windows(2) {
        for k in 0..8 {
            let (p, q, r, s) = (pair[0][k], pair[0][(k + 1) % 8], pair[1][(k + 1) % 8], pair[1][k]);
            tris.push([p, r, q]);
            tris.push([p, s, r]);
        }
    }
    tris
}
fn planks() -> Vec<Triangle> {
    let mut tris: Vec<_> = flat()
        .into_iter()
        .map(|t| {
            t.map(|mut p| {
                p[1] -= 1.;
                p
            })
        })
        .collect();
    tris.extend(box_mesh(0., -0.03, -4., 2.2, 0.06, 6., 0.));
    tris.extend(quad([-1.1, -0.001, -1.], [-1.1, -0.001, 60.], [1.1, -0.001, 60.], [1.1, -0.001, -1.]));
    let mut z = -1.;
    while z < 60. {
        tris.extend(box_mesh(0., -0.03, z + 0.11, 2.2, 0.06, 0.22, 0.008));
        z += 0.24;
    }
    tris
}
struct Ride {
    distance: f32,
    end_speed: f32,
    peak: f32,
    bailed: bool,
    surface: GroundSurfaceReport,
    transition_landing: bool,
}
fn ride(
    session: &mut Session,
    tris: Vec<Triangle>,
    surface: u16,
    speed: f32,
    frames: usize,
    push: bool,
    difficulty: &str,
    start: f32,
) -> Ride {
    *session =
        Session::from_resources(resources(), tris.clone(), vec![surface; tris.len()], vec![], [0., 0., start], 0.)
            .unwrap();
    session.activate([0., 0., start], 0.).unwrap();
    session.configure(difficulty, false, 0.5).unwrap();
    session.activate([0., 0., start], 0.).unwrap();
    session.launch([0., 0., speed]);
    let mut ride = Ride {
        distance: 0.,
        end_speed: 0.,
        peak: 0.,
        bailed: false,
        surface: Default::default(),
        transition_landing: false,
    };
    let mut airborne = false;
    let mut landing_tick = None;
    for tick in 0..frames {
        session.tick(Controls { buttons: if push { 0x1000 } else { 0 }, ..Default::default() }).unwrap();
        let pose = session.pose();
        let deck = pose.board[6].w_axis;
        ride.peak = ride.peak.max(deck.y);
        ride.distance = deck.z - start;
        ride.end_speed = pose.velocity.length();
        ride.bailed |= pose.state.contains("Wipeout");
        if tick == 60 {
            ride.surface = pose.surface;
            assert_eq!(
                session.skater.player_input.physical.surface_default_mode, ride.surface.physics,
                "wheel surface must feed the next-frame ground profile"
            );
            let variant = session.skater.player_input.player.state_variants_1408
                [session.skater.player_input.processed.state_variant_index_2528 as usize];
            let expected = if variant.surface_override_enabled_60 != 0 {
                match ride.surface.physics {
                    1..=3 => 1,
                    5 => 3,
                    13 => 2,
                    v => v,
                }
            } else {
                ride.surface.physics
            };
            assert_eq!(
                session.skater.player_input.processed.surface_mode_2540, expected,
                "ground profile must use the difficulty-normalized wheel surface"
            );
        }
        airborne |= deck.y > 3.6 && pose.surface.wheels == 0;
        if airborne
            && landing_tick.is_none()
            && deck.y > 0.2
            && deck.y < 3.2
            && deck.z > 10.
            && deck.z < 13.
            && pose.surface.wheels > 0
            && pose.velocity.y < 0.
        {
            landing_tick = Some(tick);
        }
        if landing_tick.is_some_and(|landed| tick >= landed + 30)
            && !ride.bailed
            && pose.surface.wheels > 0
            && pose.velocity.length() > 1.
        {
            ride.transition_landing = true;
            break;
        }
    }
    ride
}
fn resources() -> &'static crate::PreparedResources {
    static RESOURCES: OnceLock<crate::PreparedResources> = OnceLock::new();
    RESOURCES.get_or_init(|| crate::PreparedResources::from_bytes(package().to_vec()).unwrap())
}
fn session() -> Session {
    Session::from_resources(resources(), vec![], vec![], vec![], [0., -1000., 0.], 0.).unwrap()
}

#[test]
fn terrain_quarter_landings_eleven_to_thirteen_ms_all_difficulties() {
    let mut session = session();
    for difficulty in ["easy", "normal", "hardcore"] {
        for speed in [11., 12., 13.] {
            let result = ride(&mut session, quarter(), 129, speed, 600, false, difficulty, 0.);
            eprintln!(
                "quarter {difficulty} {speed}m/s: peak={} transition={} bail={}",
                result.peak, result.transition_landing, result.bailed
            );
            assert!(
                !result.bailed && result.peak > 3.6 && result.transition_landing,
                "{difficulty}/{speed}: bail={} peak={} transition_landing={}",
                result.bailed,
                result.peak,
                result.transition_landing
            );
        }
    }
}
#[test]
fn terrain_smooth_rough_dirt_grass_coasts_use_original_profiles() {
    let mut session = session();
    let mut distances = Vec::new();
    for packed in [129, 130, 260, 261, 390, 647] {
        let result = ride(&mut session, flat(), packed, 6., 240, false, "normal", -3.);
        eprintln!("surface {packed}: coast={}m end={}m/s bail={}", result.distance, result.end_speed, result.bailed);
        assert_eq!((result.surface.physics, result.surface.sound), (u32::from(packed >> 7), u32::from(packed & 127)));
        assert!(!result.bailed);
        distances.push(result.distance);
    }
    assert!((distances[0] - distances[1]).abs() < 0.1);
    assert!(distances[0] > 20. && distances[2] > 0.9 * distances[0] && distances[3] > 0.9 * distances[0]);
    assert!(distances[4] < 0.6 * distances[0] && distances[5] < distances[4]);
}
#[test]
fn terrain_plank_coast_and_push_all_difficulties() {
    let mut session = session();
    for difficulty in ["easy", "normal", "hardcore"] {
        for push in [false, true] {
            let speed = if push { 0. } else { 7. };
            let frames = if push { 300 } else { 240 };
            let baseline = ride(&mut session, flat(), 130, speed, frames, push, difficulty, -3.);
            let planks = ride(&mut session, planks(), 130, speed, frames, push, difficulty, -3.);
            eprintln!(
                "planks {difficulty} push={push}: distance={} flat={} end={} bail={}",
                planks.distance, baseline.distance, planks.end_speed, planks.bailed
            );
            assert!(
                !planks.bailed && planks.distance >= 0.8 * baseline.distance,
                "{difficulty} push={push}: plank={} baseline={} bail={}",
                planks.distance,
                baseline.distance,
                planks.bailed
            );
        }
    }
}
