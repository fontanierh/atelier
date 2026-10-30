//! Stock resource-backed input, ground-pump telemetry and boost separation.
use super::*;
use std::sync::OnceLock;

fn package() -> &'static [u8] {
    static BYTES: OnceLock<Vec<u8>> = OnceLock::new();
    BYTES.get_or_init(|| {
        std::fs::read(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/../../assets/simulations/skate-simulation/skate-simulation.skatepack"
        ))
        .expect("export the skating simulation package before the session tests")
    })
}

// 3m quarter transition with 32 facets, joined to a flat floor and deck.
fn quarter() -> Vec<[[f32; 3]; 3]> {
    let mut profile = vec![(-40., 0.), (10., 0.)];
    for i in 1..=32 {
        let angle = f64::from(i) * std::f64::consts::PI / 64.;
        profile.push(((10. + 3. * angle.sin()) as f32, (3. - 3. * angle.cos()) as f32));
    }
    profile.extend([(13., 3.3), (16., 3.3)]);
    let mut triangles = Vec::new();
    for p in profile.windows(2) {
        let [(z0, y0), (z1, y1)] = [p[0], p[1]];
        let (a, b, c, d) = ([-4., y0, z0], [-4., y1, z1], [4., y1, z1], [4., y0, z0]);
        triangles.extend([[a, b, c], [a, c, d]]);
    }
    triangles
}

fn session() -> Session {
    let triangles = quarter();
    let surfaces = vec![1 << 7 | 1; triangles.len()];
    let resources = crate::PreparedResources::from_bytes(package().to_vec()).unwrap();
    let mut s = Session::from_resources(&resources, triangles, surfaces, vec![], [0.; 3], 0.).unwrap();
    // Exercise the same re-entry path as the raw Session replay.
    s.activate([0.; 3], 0.).unwrap();
    s.configure("normal", false, 0.5).unwrap();
    s.tune(1., 1., 1., 1., 0.).unwrap();
    s.set_feel(Default::default()).unwrap();
    s.activate([0.; 3], 0.).unwrap();
    s.launch([0., 0., 9.]);
    s
}

fn input(tick: usize) -> Controls {
    // Stock crouch is the trigger, not the stick-derived zero crouch ramp.
    Controls { triggers: [if (55..95).contains(&tick) { 255 } else { 0 }, 0], ..Default::default() }
}

#[test]
fn intentional_ground_pump_counts_but_boost_and_coasting_do_not() {
    std::thread::Builder::new()
        .stack_size(32 * 1024 * 1024)
        .spawn(|| {
            let mut stock = session();
            let mut boosted = session();
            boosted.set_boost_zone(1.).unwrap();
            let mut saw_intentional_gain = false;
            let mut saw_boost_without_pump_count = false;
            let mut previous_count = 0;
            for tick in 0..120 {
                stock.tick(input(tick)).unwrap();
                boosted.tick(input(tick)).unwrap();
                let p = &stock.skater.ground.pumping;
                let telemetry = stock.telemetry();
                let ground = matches!(
                    stock.skater.player_state.current(),
                    crate::core::player::state::PhysicalStateId::PhysicsGround
                        | crate::core::player::state::PhysicalStateId::RevertGround
                );
                if ground
                    && p.intentional_pumping != 0
                    && p.pumping_time > 0.
                    && p.pumping > 0.
                    && p.pump_acceleration > 0.
                {
                    saw_intentional_gain = true;
                }
                if telemetry.pumps > previous_count {
                    assert!(
                        ground && p.intentional_pumping != 0 && p.pumping_time > 0. && p.pump_acceleration > 0.,
                        "count changed without a native intentional ground pump at tick {tick}"
                    );
                }
                previous_count = telemetry.pumps;
                let b = &boosted.skater.ground.pumping;
                let boost_telemetry = boosted.telemetry();
                if !saw_boost_without_pump_count && boost_telemetry.boost_total > 0. && b.pump_acceleration == 0. {
                    assert_eq!(boost_telemetry.pumps, 0, "boost alone counted as a pump at tick {tick}");
                    saw_boost_without_pump_count = true;
                }
            }
            assert!(saw_intentional_gain, "the input never produced native intentional pumping");
            assert_eq!(stock.telemetry().pumps, 1, "the native intentional pump must count exactly once");
            assert!(stock.telemetry().pump_gain >= 0.5);
            assert!(saw_boost_without_pump_count, "the boost-only witness did not occur");

            let mut coast = session();
            let mut saw_unintentional_gain = false;
            for _ in 0..220 {
                coast.tick(Controls::default()).unwrap();
                let p = &coast.skater.ground.pumping;
                saw_unintentional_gain |= p.intentional_pumping == 0 && p.pump_acceleration > 0.;
                assert_eq!(coast.telemetry().pumps, 0, "gravity or coasting counted as an intentional pump");
            }
            assert!(saw_unintentional_gain, "the downhill negative-control gain did not occur");
        })
        .unwrap()
        .join()
        .unwrap();
}
