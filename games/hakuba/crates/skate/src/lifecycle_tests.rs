//! The real host input, transitions and fixed simulation run against exported assets and a flat collision snapshot.
use super::*;
use bevy::input::{gamepad::RawGamepadEvent, keyboard::KeyboardInput, mouse::AccumulatedMouseMotion};
use hakuba_world::{CollisionCoverage, CollisionSnapshot, CollisionTriangle};
use std::{sync::Arc, time::Duration};

fn glb(path: &str) -> serde_json::Value {
    let bytes =
        std::fs::read(std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../assets").join(path)).unwrap();
    let length = u32::from_le_bytes(bytes[12..16].try_into().unwrap()) as usize;
    serde_json::from_slice(&bytes[20..20 + length]).unwrap()
}

// Reconstruct the authored skeleton, not a substitute set of target joints.
fn nox() -> Rig {
    use bevy::math::Affine3A;
    use hakuba_characters::Bone;
    let json = glb("characters/nox/nox.glb");
    let nodes = json["nodes"].as_array().unwrap();
    let mut parents = vec![None; nodes.len()];
    let mut locals = Vec::new();
    for (i, node) in nodes.iter().enumerate() {
        let values = |key: &str, fallback: &[f32]| {
            node[key]
                .as_array()
                .map_or_else(|| fallback.to_vec(), |v| v.iter().map(|x| x.as_f64().unwrap() as f32).collect())
        };
        locals.push(Transform {
            translation: Vec3::from_slice(&values("translation", &[0., 0., 0.])),
            rotation: Quat::from_slice(&values("rotation", &[0., 0., 0., 1.])),
            scale: Vec3::from_slice(&values("scale", &[1., 1., 1.])),
        });
        if let Some(children) = node["children"].as_array() {
            for child in children {
                parents[child.as_u64().unwrap() as usize] = Some(i);
            }
        }
    }
    let depth = |mut i: usize| {
        let mut d = 0;
        while let Some(parent) = parents[i] {
            d += 1;
            i = parent;
        }
        d
    };
    let mut selected: Vec<_> = nodes
        .iter()
        .enumerate()
        .filter_map(|(i, node)| {
            let name = node["name"].as_str()?;
            // Select the exported skeleton nodes with authored bone names.
            (["pelvis", "spine", "spine_mid", "chest", "neck", "head"].contains(&name)
                || [
                    "clavicle_",
                    "upper_arm_",
                    "forearm_",
                    "hand_",
                    "thigh_",
                    "shin_",
                    "foot_",
                    "toe_",
                    "thumb_",
                    "index_",
                    "middle_",
                    "ring_",
                    "pinky_",
                ]
                .iter()
                .any(|prefix| name.starts_with(prefix)))
            .then_some((i, name.to_owned()))
        })
        .collect();
    selected.sort_by_key(|(i, name)| (depth(*i), name.clone()));
    let mut bones = Vec::new();
    for (index, name) in &selected {
        let mut body_rest = locals[*index].compute_affine();
        let mut at = parents[*index];
        while let Some(parent) = at {
            body_rest = locals[parent].compute_affine() * body_rest;
            at = parents[parent];
        }
        let parent = parents[*index].and_then(|p| selected.iter().position(|(i, _)| *i == p));
        let root_parent =
            if parent.is_none() { body_rest * locals[*index].compute_affine().inverse() } else { Affine3A::IDENTITY };
        bones.push(Bone {
            name: name.clone(),
            entity: Entity::PLACEHOLDER,
            parent,
            rest: locals[*index],
            body_rest,
            root_parent,
        });
    }
    Rig { bones }
}

fn app() -> (App, Entity, Entity) {
    let mut app = App::new();
    app.init_resource::<Ride>()
        .init_resource::<RideInput>()
        .init_resource::<SkateStatus>()
        .init_resource::<places::Places>()
        .init_resource::<CollisionFocus>()
        .init_resource::<hakuba_settings::Settings>()
        .init_resource::<Time>()
        .init_resource::<Time<Real>>()
        .init_resource::<ButtonInput<KeyCode>>()
        .init_resource::<ButtonInput<MouseButton>>()
        .init_resource::<AccumulatedMouseMotion>()
        .insert_resource(Assets::<Mesh>::default())
        .add_message::<KeyboardInput>()
        .add_message::<RawGamepadEvent>()
        .add_message::<ride_input::StickReading>()
        .add_message::<crate::AudioEvent>()
        .add_systems(PostUpdate, present);

    let board = glb(BOARD);
    let holder = board["nodes"].as_array().unwrap().iter().find(|n| n["name"] == "holder").unwrap();
    let profile: retarget::DeckProfile = serde_json::from_value(holder["extras"]["deck"].clone()).unwrap();
    app.insert_resource(BoardGrip(Some(profile)));
    let bytes =
        std::fs::read(std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../assets").join(PACKAGE)).unwrap();
    let mut packages = Assets::<Package>::default();
    let package = packages.add(Package(crate::PreparedResources::from_bytes(bytes).unwrap()));
    app.insert_resource(packages);
    let mut models = Assets::<Gltf>::default();
    // Transition checks the loaded handle; board geometry and grip are read from the exported GLB above.
    let model = models.add(Gltf {
        scenes: default(),
        named_scenes: default(),
        meshes: default(),
        named_meshes: default(),
        materials: default(),
        named_materials: default(),
        nodes: default(),
        named_nodes: default(),
        skins: default(),
        named_skins: default(),
        default_scene: None,
        animations: default(),
        named_animations: default(),
        source: None,
    });
    app.insert_resource(models).insert_resource(AssetsToLoad { package, board: model });

    // Reverse world-to-native reflection and winding exactly as the live host does.
    let native = [
        [[-100., 0., -100.], [-100., 0., 100.], [100., 0., -100.]],
        [[100., 0., -100.], [-100., 0., 100.], [100., 0., 100.]],
    ];
    let triangles = native
        .into_iter()
        .enumerate()
        .map(|(source_face, t)| {
            let p = t.map(|p| frame::world_point(Vec3::from(p)));
            CollisionTriangle { points: [p[0], p[2], p[1]], material: "concrete".into(), surface: 129, source_face }
        })
        .collect();
    app.insert_resource(WorldCollision {
        generation: 1,
        snapshot: Arc::new(CollisionSnapshot {
            ready: true,
            triangles,
            coverage: vec![CollisionCoverage { tile: [0, 0], min: Vec2::splat(-100.), max: Vec2::splat(100.) }],
            ..default()
        }),
    });
    let body = app.world_mut().spawn(nox()).id();
    // Player fields have private concrete types; PlayerPlugin's own spawn creates the real walking player.
    app.add_plugins((bevy::state::app::StatesPlugin, hakuba_player::PlayerPlugin));
    app.init_resource::<bevy::input::mouse::AccumulatedMouseScroll>();
    app.insert_resource(hakuba_world::Spawn(Transform::from_xyz(0., 0.1, 0.)));
    app.init_state::<Screen>().add_sub_state::<Pause>().add_sub_state::<DevMode>();
    app.world_mut().resource_mut::<NextState<Screen>>().set(Screen::World);
    app.add_systems(
        Update,
        (ride_input::read, places::read, transition, apply_preferences, simulate)
            .chain()
            .after(PlayerSystems::Input)
            .before(PlayerSystems::Movement)
            .run_if(in_state(Screen::World))
            .run_if(in_state(Pause::Playing))
            .run_if(in_state(DevMode::Off)),
    );
    app.world_mut().spawn((Window::default(), bevy::window::PrimaryWindow));
    app.world_mut().spawn((Camera3d::default(), Transform::default(), Projection::default()));
    app.world_mut().resource_mut::<Time>().advance_by(Duration::from_secs_f64(1. / 60.));
    app.update();
    let player = {
        let world = app.world_mut();
        let mut players = world.query_filtered::<Entity, With<Player>>();
        players.single(world).unwrap()
    };
    app.world_mut().get_mut::<Player>(player).unwrap().body = body;
    (app, player, body)
}

fn step(app: &mut App) {
    let dt = Duration::from_secs_f64(1. / 60.);
    app.world_mut().resource_mut::<Time>().advance_by(dt);
    app.world_mut().resource_mut::<Time<Real>>().advance_by(dt);
    app.update();
    app.world_mut().resource_mut::<ButtonInput<KeyCode>>().clear();
    let status = app.world().resource::<SkateStatus>();
    assert!(status.failure.is_none(), "native host failed: {:?}", status.failure);
}
fn press(app: &mut App, key: KeyCode) {
    app.world_mut().resource_mut::<ButtonInput<KeyCode>>().press(key);
}
fn release(app: &mut App, key: KeyCode) {
    app.world_mut().resource_mut::<ButtonInput<KeyCode>>().release(key);
}
fn tap(app: &mut App, key: KeyCode) {
    press(app, key);
    step(app);
    release(app, key);
}
fn until(app: &mut App, limit: usize, label: &str, mut condition: impl FnMut(&World) -> bool) {
    for _ in 0..limit {
        if condition(app.world()) {
            return;
        }
        step(app);
    }
    let ride = app.world().resource::<Ride>();
    panic!(
        "{label}: state={:?}, desired={:?}, stowing={}, offboard_time={}",
        ride.current.as_ref().map(|p| (&p.state, p.physical_state)),
        ride.desired_on_foot,
        ride.stowing,
        ride.offboard_time
    );
}

#[test]
fn exported_host_retries_mount_carry_remount_and_stows_only_after_grounded() {
    let (mut app, player, body) = app();
    tap(&mut app, KeyCode::KeyV);
    assert_eq!(app.world().get::<Player>(player).unwrap().owner, MovementOwner::Skating);
    assert!(app.world().get::<PoseOverride>(body).is_some());
    until(&mut app, 30, "initial mount request survives native spawn", |w| {
        w.resource::<Ride>().desired_on_foot == Some(false)
    });
    assert!(app.world().resource::<Ride>().current.as_ref().unwrap().physical_state == 500);
    assert!(
        app.world().resource::<Ride>().session.as_ref().unwrap().transition_debug().contains("SpawnDismount"),
        "fixture must request mount before the native spawn animation is interruptible"
    );
    until(&mut app, 300, "native initial mount", |w| {
        w.resource::<Ride>().current.as_ref().is_some_and(|p| p.physical_state == 100)
    });
    press(&mut app, KeyCode::KeyW);
    for _ in 0..120 {
        step(&mut app);
    }
    release(&mut app, KeyCode::KeyW);
    assert!(app.world().resource::<SkateStatus>().speed_mps > 0.5, "native push did not produce speed");
    press(&mut app, KeyCode::Space);
    for _ in 0..12 {
        step(&mut app);
    }
    release(&mut app, KeyCode::Space);
    until(&mut app, 180, "pop enters native air", |w| {
        w.resource::<Ride>().current.as_ref().is_some_and(|p| (200..=202).contains(&p.physical_state))
    });
    until(&mut app, 300, "pop and return to stable riding", |w| {
        w.resource::<Ride>().current.as_ref().is_some_and(|p| p.physical_state == 100)
    });
    tap(&mut app, KeyCode::KeyV);
    until(&mut app, 360, "native dismount to carry", |w| {
        w.resource::<Ride>().current.as_ref().is_some_and(|p| p.physical_state == 500)
    });
    assert_eq!(app.world().get::<Player>(player).unwrap().owner, MovementOwner::Skating);
    // Stow while carrying, then V before the next frame's handback; V must cancel the stow.
    tap(&mut app, KeyCode::KeyF);
    assert!(app.world().resource::<Ride>().stowing);
    tap(&mut app, KeyCode::KeyV);
    assert!(!app.world().resource::<Ride>().stowing);
    assert_eq!(app.world().get::<Player>(player).unwrap().owner, MovementOwner::Skating);
    until(&mut app, 360, "native remount", |w| {
        w.resource::<Ride>().current.as_ref().is_some_and(|p| p.physical_state == 100)
    });
    tap(&mut app, KeyCode::KeyF);
    assert!(app.world().resource::<Ride>().stowing);
    tap(&mut app, KeyCode::KeyV);
    assert!(!app.world().resource::<Ride>().stowing);
    for _ in 0..30 {
        step(&mut app);
    }
    assert_eq!(app.world().get::<Player>(player).unwrap().owner, MovementOwner::Skating);
    // A dismount already accepted by the graph may still finish; V cancels the stow, not the native animation.
    if app.world().resource::<SkateStatus>().on_foot {
        tap(&mut app, KeyCode::KeyV);
    }
    until(&mut app, 360, "riding after cancelled stow", |w| {
        w.resource::<Ride>().current.as_ref().is_some_and(|p| p.physical_state == 100)
    });
    press(&mut app, KeyCode::KeyW);
    for _ in 0..90 {
        step(&mut app);
    }
    release(&mut app, KeyCode::KeyW);
    assert!(app.world().resource::<SkateStatus>().speed_mps > 0.5, "remount did not ride away");
    tap(&mut app, KeyCode::KeyF);
    assert_eq!(
        app.world().get::<Player>(player).unwrap().owner,
        MovementOwner::Skating,
        "F must not teleport to walking"
    );
    until(&mut app, 360, "stow waits for native grounded carry", |w| w.resource::<Ride>().offboard_time >= 0.2);
    assert_eq!(app.world().get::<Player>(player).unwrap().owner, MovementOwner::Skating);
    step(&mut app);
    assert_eq!(app.world().get::<Player>(player).unwrap().owner, MovementOwner::Walking);
    assert!(app.world().get::<PoseOverride>(body).is_none());
    assert!(app.world().resource::<Ride>().session.is_none());
}
