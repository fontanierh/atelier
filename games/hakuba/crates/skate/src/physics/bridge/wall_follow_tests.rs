//! Resource-backed curved-bowl landing and zero-assist/transfer equality checks.
use super::*;
use std::sync::OnceLock;
const LIP: f32 = 95.0;
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
fn bowl() -> Vec<[[f32; 3]; 3]> {
    let mut profile = vec![(53.0, 0.0)];
    for a in (0..=90).step_by(2) {
        let a = (a as f32).to_radians();
        profile.push((83.0 + 12.0 * a.sin(), 12.0 * (1.0 - a.cos())));
    }
    profile.extend([(95.0, 14.0), (130.0, 14.0)]);
    let point = |r: f32, y: f32, a: f32| [r * a.cos(), y, r * a.sin()];
    let mut triangles = Vec::new();
    for a in -20..200 {
        let (a0, a1) = ((a as f32).to_radians(), ((a + 1) as f32).to_radians());
        for p in profile.windows(2) {
            let ((r0, y0), (r1, y1)) = (p[0], p[1]);
            let (q00, q01, q10, q11) = (point(r0, y0, a0), point(r0, y0, a1), point(r1, y1, a0), point(r1, y1, a1));
            triangles.extend([[q00, q11, q10], [q00, q01, q11]]);
        }
    }
    triangles
}
#[derive(Debug, PartialEq)]
struct Row {
    state: String,
    deck: [f32; 3],
    velocity: [u32; 3],
    root: [u32; 16],
    bones: Vec<[u32; 16]>,
    active: bool,
}
fn ride(strength: f32, speed: f32, limit: f32, assist: f32, transfer: bool) -> Vec<Row> {
    let triangles = bowl();
    let spawn = [LIP - 12.5, 0.0, 0.0];
    let surfaces = vec![1 << 7; triangles.len()];
    let mut session = Session::from_resources(
        &crate::PreparedResources::from_bytes(package().to_vec()).unwrap(),
        triangles,
        surfaces,
        Vec::new(),
        spawn,
        0.0,
    )
    .unwrap();
    session.configure("normal", false, 0.5).unwrap();
    session.tune(1.0, 1.0, 1.0, 1.0, assist).unwrap();
    session.set_feel(crate::feel::FeelTuning { wall_follow: strength, ..Default::default() }).unwrap();
    session.limit_vert_assist(limit).unwrap();
    session.activate(spawn, 0.0).unwrap();
    session.launch([0.0, 0.0, speed]);
    let mut rows = Vec::new();
    for _ in 0..420 {
        session.tick(Controls { buttons: if transfer { TRANSFER } else { 0 }, ..Default::default() }).unwrap();
        let pose = session.pose();
        let p = session.physics.board.bodies()[crate::core::physics::board::BodyId::Deck.index()].rates.position;
        rows.push(Row {
            state: pose.state,
            deck: [p.x, p.y, p.z],
            velocity: pose.velocity.to_array().map(f32::to_bits),
            root: pose.root.to_cols_array().map(f32::to_bits),
            bones: pose.bones.into_iter().map(|m| m.to_cols_array().map(f32::to_bits)).collect(),
            active: session.skater.trajectory.wall_follow.active,
        });
    }
    rows
}
fn landed_on_transition(rows: &[Row]) -> bool {
    let Some(start) = rows.iter().position(|r| r.state.contains("Air")) else { return false };
    let Some(offset) = rows[start..].iter().position(|r| !r.state.contains("Air")) else { return false };
    let end = start + offset;
    if end - start <= 60 || rows.len() < end + 30 {
        return false;
    }
    let p = rows[end].deck;
    let radius = (p[0] * p[0] + p[2] * p[2]).sqrt();
    let wall = if radius > 83.0 && radius <= 95.0 {
        12.0 * (1.0 - (1.0 - ((radius - 83.0) / 12.0).powi(2)).max(0.0).sqrt())
    } else {
        return false;
    };
    p[1] > 1.0
        && (p[1] - wall).abs() < 1.0
        && rows[end..end + 30].iter().all(|r| r.state.contains("Ground") && !r.state.contains("Wipeout"))
}
#[test]
fn wall_follow_bowl_lands_on_transition_and_rides_away() {
    for speed in [38.0, 40.0] {
        let rows = ride(1.0, speed, 1.0, 1.0, false);
        assert!(rows.iter().any(|r| r.active), "wall follow never activated at {speed}");
        assert!(
            landed_on_transition(&rows),
            "failed transition landing at {speed}: {:?}",
            rows.iter()
                .enumerate()
                .filter(|(i, _)| i % 30 == 0)
                .map(|(i, r)| (i, &r.state, r.deck, r.active))
                .collect::<Vec<_>>()
        );
    }
}
#[test]
fn wall_follow_zero_assist_and_transfer_sessions_keep_stock_bits() {
    for (limit, assist, transfer) in [(0.0, 1.0, false), (1.0, 0.0, false), (1.0, 1.0, true)] {
        let stock = ride(0.0, 40.0, limit, assist, transfer);
        let followed = ride(1.0, 40.0, limit, assist, transfer);
        assert!(followed.iter().all(|r| !r.active));
        assert_eq!(stock, followed, "limit={limit} assist={assist} transfer={transfer}");
    }
}
