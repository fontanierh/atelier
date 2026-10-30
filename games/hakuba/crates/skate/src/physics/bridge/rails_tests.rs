//! Exported closed grind lines retain their authored last-to-first contact chord.
use super::*;

fn rails_from_world_index() -> Vec<CollisionRail> {
    let bytes = std::fs::read(concat!(env!("CARGO_MANIFEST_DIR"), "/../../assets/world/world.glb"))
        .expect("exported world index");
    assert_eq!(&bytes[..4], b"glTF");
    let length = u32::from_le_bytes(bytes[12..16].try_into().unwrap()) as usize;
    assert_eq!(&bytes[16..20], b"JSON");
    let index: serde_json::Value = serde_json::from_slice(&bytes[20..20 + length]).unwrap();
    let metadata = index["nodes"]
        .as_array()
        .unwrap()
        .iter()
        .find(|node| node["name"] == "skate world")
        .expect("world index must be re-exported with skating metadata");
    metadata["extras"]["rails"]
        .as_array()
        .unwrap()
        .iter()
        .map(|rail| CollisionRail {
            id: rail["id"].as_str().unwrap().to_owned(),
            points: serde_json::from_value::<Vec<[f32; 3]>>(rail["points"].clone())
                .unwrap()
                .into_iter()
                .map(|[x, y, z]| [z, y, x])
                .collect(),
            closed: rail["closed"].as_bool().unwrap(),
        })
        .collect()
}

fn material() -> crate::core::physics::contact::RetailContactMaterial {
    crate::core::physics::contact::RetailContactMaterial {
        static_friction: 0.8,
        dynamic_friction: 0.6,
        restitution: 0.,
    }
}

#[test]
fn exported_closed_rails_keep_every_chord_in_initial_and_replacement_collision() {
    let rails = rails_from_world_index();
    let implicit_loops = rails.iter().filter(|rail| rail.closed && rail.points.first() != rail.points.last()).count();
    assert!(implicit_loops >= 4, "the exported world must contain its four implicit closed coping loops");
    let expected_count: usize = rails
        .iter()
        .map(|rail| rail.points.len() - 1 + usize::from(rail.closed && rail.points.first() != rail.points.last()))
        .sum();
    let map = collision_map(vec![], vec![], rails.clone(), [0.; 3], 0.).unwrap();
    assert_eq!(map.rails.len(), rails.len());
    for (input, output) in rails.iter().zip(&map.rails) {
        assert_eq!(output.name, input.id);
        assert_eq!(output.points, input.points);
        assert_eq!(output.closed, input.closed);
    }
    let initial = crate::grind_world::StaticProvider::new(Some(&map)).unwrap();
    let replacement = CollisionBuilder { material: material() }.build(vec![], vec![], rails.clone()).unwrap();
    for provider in [&initial, replacement.grind.as_ref()] {
        assert_eq!(provider.primitives().len(), expected_count);
        for (i, rail) in rails.iter().enumerate().filter(|(_, rail)| rail.closed) {
            let segments: Vec<_> = provider.primitives().iter().filter(|p| p.owner == (i + 1) as u64).collect();
            let last = segments.last().unwrap();
            let expected_start = if rail.points.first() == rail.points.last() {
                rail.points[rail.points.len() - 2]
            } else {
                *rail.points.last().unwrap()
            };
            assert_eq!(&last.start[..3], &expected_start);
            for axis in 0..3 {
                // Current world coordinates can round a native cubic chord by less than one millimetre.
                assert!((last.end[axis] - rail.points[0][axis]).abs() < 0.001, "{} axis {axis}", rail.id);
            }
            assert_eq!(provider.spline_guids(last.owner), initial.spline_guids(last.owner));
        }
    }
}

#[test]
fn explicit_closed_endpoint_is_not_added_twice_and_open_lines_stay_open() {
    let points = vec![[0., 0., 0.], [1., 0., 0.], [1., 0., 1.], [0., 0., 0.]];
    let rails = vec![
        CollisionRail { id: "closed".into(), points: points.clone(), closed: true },
        CollisionRail { id: "open".into(), points, closed: false },
    ];
    let map = collision_map(vec![], vec![], rails, [0.; 3], 0.).unwrap();
    let provider = crate::grind_world::StaticProvider::new(Some(&map)).unwrap();
    assert_eq!(provider.primitives().len(), 6);
    assert_eq!(provider.primitives().iter().filter(|p| p.owner == 1).count(), 3);
    assert_eq!(provider.primitives().iter().filter(|p| p.owner == 2).count(), 3);
}
