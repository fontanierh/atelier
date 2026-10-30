//! Synthetic golden payloads exercise every stored field without requiring authoring files.
use super::{camera, gesture_patterns, physics_skeleton, sha256, state_graph::StateGraph};
use std::collections::BTreeSet;

fn fixture(text: &str) -> Vec<u8> {
    let hex: String = text.lines().filter(|line| !line.starts_with("//")).collect();
    (0..hex.len()).step_by(2).map(|i| u8::from_str_radix(&hex[i..i + 2], 16).unwrap()).collect()
}
struct Writer(Vec<u8>);
impl Writer {
    fn new(magic: &[u8; 8]) -> Self {
        Self(magic.to_vec())
    }
    fn word(&mut self, value: u32) {
        self.0.extend(value.to_le_bytes());
    }
    fn wide(&mut self, value: u64) {
        self.0.extend(value.to_le_bytes());
    }
    fn string(&mut self, value: &str) {
        self.word(value.len() as u32);
        self.0.extend(value.as_bytes());
    }
    fn floats<const N: usize>(&mut self, values: [f32; N]) {
        for value in values {
            self.word(value.to_bits());
        }
    }
}
fn graph_bytes(graph: &StateGraph) -> Vec<u8> {
    let strings: BTreeSet<&str> = graph
        .elements
        .iter()
        .flat_map(|e| {
            std::iter::once(e.tag.as_str()).chain(e.attributes.iter().flat_map(|a| [a.name.as_str(), a.text.as_str()]))
        })
        .collect();
    let strings: Vec<_> = strings.into_iter().collect();
    let index = |s: &str| strings.binary_search(&s).unwrap() as u32;
    let mut w = Writer::new(b"ATGRPH01");
    w.word(strings.len() as u32);
    w.word(graph.elements.len() as u32);
    for s in &strings {
        w.string(s);
    }
    for e in &graph.elements {
        for value in [e.source_offset as u32, index(&e.tag), e.attributes.len() as u32, e.children.len() as u32] {
            w.word(value);
        }
        for a in &e.attributes {
            for value in [index(&a.name), index(&a.text), a.float_bits, u32::from(a.boolean_byte)] {
                w.word(value);
            }
        }
        for &child in &e.children {
            w.word(child as u32);
        }
    }
    w.0
}
fn gesture_bytes(sets: &[gesture_patterns::GestureSet]) -> Vec<u8> {
    let mut w = Writer::new(b"ATGEST01");
    w.word(sets.len() as u32);
    for s in sets {
        w.string(&s.name);
        w.word(s.stick as u32);
        w.word(s.patterns.len() as u32);
        for p in &s.patterns {
            w.string(&p.name);
            w.word(p.tolerance_squared.to_bits());
            w.word(p.points.len() as u32);
            for &point in &p.points {
                w.floats(point);
            }
        }
    }
    w.0
}
fn physical_bytes(skeletons: &[physics_skeleton::PhysicsSkeleton]) -> Vec<u8> {
    let mut w = Writer::new(b"ATPHYS01");
    w.string("bank-exact");
    w.word(skeletons.len() as u32);
    for s in skeletons {
        w.string(&s.name);
        w.wide(s.source_offset);
        w.word(s.bones.len() as u32);
        for b in &s.bones {
            w.string(&b.name);
            w.wide(b.source_offset);
            for word in b.words {
                w.word(word);
            }
        }
    }
    w.0
}
fn camera_bytes(camera: &camera::CameraData) -> Vec<u8> {
    let mut w = Writer::new(b"ATCAM001");
    w.string(&camera.source_identity);
    w.word(camera.shots.len() as u32);
    for d in &camera.shots {
        w.string(&d.name);
        w.word(d.shot_type);
        let s = &d.shot;
        w.floats([s.distance, s.lens_length]);
        w.floats(s.smoothing);
        w.floats(s.reference_weights);
        w.floats([s.board_offset, s.position_heading, s.position_elevation]);
        w.floats(s.framing);
        for v in [
            s.follow_subject_in_air,
            s.mirror_for_stance,
            s.snap_to_reference_point,
            s.use_previous_shot,
            s.use_drop_predictor,
            s.use_free_camera_stick,
            s.avoidance_override,
        ] {
            w.word(u32::from(v));
        }
        w.floats([s.blur, s.transition_blur, s.subject_opacity]);
        for v in [s.collision_hint, s.anchor, s.compass_north] {
            w.word(v);
        }
        w.floats([s.world_heading]);
        w.floats(s.arm_orientation);
        w.floats(s.camera_orientation);
        w.floats([d.transition_time]);
        w.word(d.transition_units);
        for child in &d.children {
            w.word(u32::from(child.is_some()));
            if let Some(name) = child {
                w.string(name);
            }
        }
        w.floats(d.blend_points);
        w.floats([d.blend_value]);
        w.word(d.blend_type);
        w.floats([d.blend_smoothing]);
    }
    for samples in &camera.shakes {
        let (rotations, translations) = samples.centered_samples();
        w.word(rotations.len() as u32);
        for (&rotation, &translation) in rotations.iter().zip(translations) {
            w.floats(rotation);
            w.floats(translation);
        }
    }
    w.0
}

#[test]
fn graph_golden_roundtrip_preserves_preorder_duplicate_attributes_and_opaque_words() {
    let bytes = fixture(include_str!("fixtures/graph.hex"));
    assert_eq!(sha256::digest(&bytes), "3941774cc2f2993ec36db8bfeb47e48eeb8c87d3a2f2ea681c0d5b8229dfbf78");
    let graph = StateGraph::from_bytes(&bytes).unwrap();
    assert_eq!(graph.elements[0].source_offset, 0x80000009);
    assert_eq!(graph.elements[0].children, [1, 3]);
    assert_eq!(graph.elements[1].children, [2]);
    assert_eq!(graph.elements[0].attributes[0].name, graph.elements[0].attributes[1].name);
    assert_eq!(graph.elements[0].attributes[0].float_bits, 0x7fc01234);
    assert_eq!(graph.elements[0].attributes[0].boolean_byte, 255);
    assert_eq!(graph_bytes(&graph), bytes);
}
#[test]
fn gestures_golden_roundtrip_preserves_names_sticks_authored_order_and_signed_zero() {
    let bytes = fixture(include_str!("fixtures/gestures.hex"));
    assert_eq!(sha256::digest(&bytes), "bad38c011ab6a3d605604f654fd7ac3fcba76cbfc72fbd72169b906ac61f5325");
    let sets = gesture_patterns::from_bytes(&bytes).unwrap();
    assert_eq!(sets.iter().map(|s| (s.name.as_str(), s.stick)).collect::<Vec<_>>(), [("skater", 1), ("LS", 0)]);
    assert_eq!(sets[0].patterns[0].name, sets[0].patterns[1].name);
    assert_eq!(sets[0].patterns[0].tolerance_squared.to_bits(), 0x80000000);
    assert_eq!(sets[0].patterns[0].points[0][0].to_bits(), 0x80000000);
    assert_eq!(gesture_bytes(&sets), bytes);
}
#[test]
fn physics_golden_roundtrip_preserves_all_words_offsets_and_case_sensitive_names() {
    let bytes = fixture(include_str!("fixtures/physics.hex"));
    assert_eq!(sha256::digest(&bytes), "685f6f4826d1f891c6fe044ce74ff0f19d81a9b8ad3eefe7e758e1f40290783c");
    let skeletons = physics_skeleton::from_bytes(&bytes, "bank-exact").unwrap();
    assert_eq!(skeletons[0].source_offset, 0x12345678abcdef00);
    assert_eq!(skeletons[1].source_offset, 0xfffffffffffffff0);
    assert_eq!(skeletons[0].bones[0].source_offset, 0xabcdef0123456789);
    assert_eq!(skeletons[0].bones[0].words[0], 0x7fc00000);
    assert_eq!(skeletons[0].bones[0].words[27], 0x7fc0001b);
    assert_eq!(skeletons[0].bones[0].translation()[2].to_bits(), 0x80000000);
    assert_eq!(physical_bytes(&skeletons), bytes);
    assert!(physics_skeleton::from_bytes(&bytes, "BANK-EXACT").is_err());
}
#[test]
fn camera_golden_roundtrip_preserves_all_fields_names_child_slots_and_centered_samples() {
    let bytes = fixture(include_str!("fixtures/camera.hex"));
    assert_eq!(sha256::digest(&bytes), "87f6d8a1acc2502c4e53bda0e5056a4d41c417e3b6cce05b07acc633cb5f195b");
    let camera = camera::from_bytes(&bytes).unwrap();
    assert_eq!(camera.source_identity, "camera-identity");
    assert_eq!(camera.shots.iter().map(|s| s.name.as_str()).collect::<Vec<_>>(), ["blend", "Leaf"]);
    assert_eq!(camera.shots[0].children, [None, Some("Leaf".into()), None]);
    assert_eq!(camera.shots[0].shot.distance.to_bits(), 0x80000000);
    assert_eq!(camera.shots[0].shot.lens_length.to_bits(), 0x7fc01234);
    assert_eq!(camera.shots[0].shot.follow_subject_in_air, 233);
    let (rotations, translations) = camera.shakes[0].centered_samples();
    assert_eq!(rotations[0][0].to_bits(), 0x3f800001);
    assert_eq!(translations[0][3].to_bits(), 0xdeadbeef);
    assert_eq!(camera_bytes(&camera), bytes);
}
#[test]
fn readers_reject_every_truncation_and_trailing_byte() {
    let graph = fixture(include_str!("fixtures/graph.hex"));
    let gestures = fixture(include_str!("fixtures/gestures.hex"));
    let physical = fixture(include_str!("fixtures/physics.hex"));
    let camera = fixture(include_str!("fixtures/camera.hex"));
    let cases: [(&[u8], fn(&[u8]) -> bool); 4] = [
        (&graph, |b| StateGraph::from_bytes(b).is_err()),
        (&gestures, |b| gesture_patterns::from_bytes(b).is_err()),
        (&physical, |b| physics_skeleton::from_bytes(b, "bank-exact").is_err()),
        (&camera, |b| camera::from_bytes(b).is_err()),
    ];
    for (bytes, rejects) in cases {
        for end in 0..bytes.len() {
            assert!(rejects(&bytes[..end]), "accepted truncated payload at {end}");
        }
        let mut trailing = bytes.to_vec();
        trailing.push(0);
        assert!(rejects(&trailing));
        let mut signature = bytes.to_vec();
        signature[0] ^= 1;
        assert!(rejects(&signature));
    }
}
#[test]
fn graph_rejects_nonpreorder_shared_children_and_wide_booleans() {
    let bytes = fixture(include_str!("fixtures/graph.hex"));
    let graph = StateGraph::from_bytes(&bytes).unwrap();
    let mut value = graph.clone();
    value.elements[0].children.swap(0, 1);
    assert!(StateGraph::from_bytes(&graph_bytes(&value)).is_err());
    let mut value = graph.clone();
    value.elements[1].children = vec![3];
    assert!(StateGraph::from_bytes(&graph_bytes(&value)).is_err());
    let mut value = graph;
    value.elements[0].children.clear();
    assert!(StateGraph::from_bytes(&graph_bytes(&value)).is_err());
    let mut r = hakuba_skate_schema::Reader::new(&bytes, b"ATGRPH01").unwrap();
    let strings = r.word().unwrap();
    r.word().unwrap();
    for _ in 0..strings {
        r.string().unwrap();
    }
    r.take(16 + 12).unwrap();
    let offset = r.position();
    let mut value = bytes;
    value[offset..offset + 4].copy_from_slice(&256_u32.to_le_bytes());
    assert!(StateGraph::from_bytes(&value).is_err());
}
#[test]
fn gestures_and_physics_apply_native_transform_and_pattern_validation() {
    let bytes = fixture(include_str!("fixtures/gestures.hex"));
    let mut sets = gesture_patterns::from_bytes(&bytes).unwrap();
    sets[0].patterns[0].tolerance_squared = f32::NAN;
    assert!(gesture_patterns::from_bytes(&gesture_bytes(&sets)).is_err());
    sets[0].patterns[0].tolerance_squared = 0.0;
    sets[0].stick = 2;
    assert!(gesture_patterns::from_bytes(&gesture_bytes(&sets)).is_err());
    sets[0].stick = 0;
    sets[0].patterns[0].points.truncate(1);
    assert!(gesture_patterns::from_bytes(&gesture_bytes(&sets)).is_err());
    let bytes = fixture(include_str!("fixtures/physics.hex"));
    let mut skeletons = physics_skeleton::from_bytes(&bytes, "bank-exact").unwrap();
    skeletons[0].bones[0].words[8] = 0x7f800000;
    assert!(physics_skeleton::from_bytes(&physical_bytes(&skeletons), "bank-exact").is_err());
    skeletons[0].bones[0].words[8] = 0;
    skeletons[0].bones[1].name = skeletons[0].bones[0].name.clone();
    assert!(physics_skeleton::from_bytes(&physical_bytes(&skeletons), "bank-exact").is_err());
}
#[test]
fn camera_rejects_duplicate_exact_names_and_missing_exact_references() {
    let bytes = fixture(include_str!("fixtures/camera.hex"));
    let mut camera = camera::from_bytes(&bytes).unwrap();
    camera.shots[0].children[1] = Some("leaf".into());
    assert!(camera::from_bytes(&camera_bytes(&camera)).is_err());
    camera.shots[0].children[1] = None;
    camera.shots[1].name = camera.shots[0].name.clone();
    assert!(camera::from_bytes(&camera_bytes(&camera)).is_err());
}
