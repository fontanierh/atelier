//! The agent board as a small living village. Every moving thing is live board state: an agent at their house with
//! the window lit is busy, one by the campfire is free, and each paper plane is a real message from sender to
//! recipient. The page (world.js) polls the board's JSON API and feeds this scene through `set_agents` and `fly`;
//! all text stays in the page's HTML.

use std::collections::HashMap;
use std::f32::consts::{PI, TAU};
use std::sync::Mutex;

use bevy::camera::ScalingMode;
use bevy::prelude::*;
use serde::Deserialize;
use wasm_bindgen::prelude::*;

#[wasm_bindgen]
extern "C" {
    /// Lets the page time the first frame and notice when frames resume after the app was in the background.
    #[wasm_bindgen(js_namespace = window, js_name = boardWorldFrame)]
    fn board_world_frame(frame: u32);
    /// Where each home is on screen, so the page can pin readable HTML name tags to them: `[[name, x, y], ...]`, with x
    /// and y in ten-thousandths of the viewport.
    #[wasm_bindgen(js_namespace = window, js_name = boardWorldLabels)]
    fn board_world_labels(json: &str);
}

#[derive(Deserialize)]
struct AgentIn {
    name: String,
    #[serde(default)]
    busy: bool,
}

enum Inbound {
    Agents(Vec<AgentIn>),
    Plane { from: String, to: String, topic: String },
    Focus(Option<String>),
    Inset(f32),
}

static INBOX: Mutex<Vec<Inbound>> = Mutex::new(Vec::new());

fn push(item: Inbound) {
    if let Ok(mut inbox) = INBOX.lock() {
        inbox.push(item);
    }
}

/// Replaces the village's residents: `[{"name": "...", "busy": true}, ...]`. Unknown fields are ignored.
#[wasm_bindgen]
pub fn set_agents(json: &str) -> bool {
    match serde_json::from_str::<Vec<AgentIn>>(json) {
        Ok(agents) => {
            push(Inbound::Agents(agents));
            true
        }
        Err(_) => false,
    }
}

/// Sends one paper plane from `from`'s house to `to`'s (the operator's house for anyone the village doesn't know).
#[wasm_bindgen]
pub fn fly(from: &str, to: &str, topic: &str) {
    push(Inbound::Plane { from: from.into(), to: to.into(), topic: topic.into() });
}

/// Eases the view toward one agent's home (an empty name returns to the whole village).
#[wasm_bindgen]
pub fn focus(name: &str) {
    push(Inbound::Focus((!name.is_empty()).then(|| name.to_string())));
}

/// How much of the screen's height a sheet covers (0 to 1), so the village slides up to stay in view above it.
#[wasm_bindgen]
pub fn inset(fraction: f32) {
    push(Inbound::Inset(fraction.clamp(0.0, 0.9)));
}

#[wasm_bindgen]
pub fn run() {
    App::new()
        .insert_resource(ClearColor(SKY))
        .insert_resource(GlobalAmbientLight { color: Color::srgb(1.0, 0.92, 0.86), brightness: 520.0, ..default() })
        .init_resource::<Village>()
        .add_plugins(DefaultPlugins.set(WindowPlugin {
            primary_window: Some(Window {
                canvas: Some("#world".into()),
                fit_canvas_to_parent: true,
                prevent_default_event_handling: false,
                ..default()
            }),
            ..default()
        }))
        .add_systems(Startup, setup)
        .add_systems(Update, (drain_inbox, walk, bob, fly_planes, flicker, sway_trees, look, report_labels, report_frame))
        .run();
}

// Paper, ink, meadow, apricot, terracotta and dusk: a handmade paper-and-clay village (networking's art brief).
const SKY: Color = Color::srgb(0.957, 0.910, 0.831);
const OPERATOR: &str = "operator";
const RING: f32 = 6.4;
const FIRE_RING: f32 = 1.9;
const PASTELS: [(f32, f32, f32); 8] = [
    (0.725, 0.376, 0.314), (0.937, 0.663, 0.475), (0.325, 0.404, 0.498), (0.369, 0.498, 0.416),
    (0.851, 0.659, 0.306), (0.557, 0.361, 0.431), (0.310, 0.541, 0.545), (0.851, 0.533, 0.502),
];

struct Resident {
    house: Entity,
    person: Entity,
    lamp: Handle<StandardMaterial>,
    angle: f32,
    busy: bool,
}

#[derive(Resource, Default)]
struct Village {
    residents: HashMap<String, Resident>,
    operator_door: Vec3,
    shapes: Option<Shapes>,
    focus: Option<String>,
    inset: f32,
}

#[derive(Clone)]
struct Shapes {
    wall: Handle<Mesh>,
    roof: Handle<Mesh>,
    window: Handle<Mesh>,
    body: Handle<Mesh>,
    head: Handle<Mesh>,
    plane: Handle<Mesh>,
    cream: Handle<StandardMaterial>,
}

#[derive(Component)]
struct Person {
    phase: f32,
    target: Vec3,
    busy: bool,
}

#[derive(Component)]
struct Plane {
    from: Vec3,
    to: Vec3,
    age: f32,
    duration: f32,
    lift: f32,
}

#[derive(Component)]
struct Fire;

#[derive(Component)]
struct Tree(f32);

fn pastel(name: &str) -> Color {
    let hash = name.bytes().fold(2166136261u32, |h, b| (h ^ b as u32).wrapping_mul(16777619));
    let (r, g, b) = PASTELS[hash as usize % PASTELS.len()];
    Color::srgb(r, g, b)
}

fn matte(materials: &mut Assets<StandardMaterial>, color: Color) -> Handle<StandardMaterial> {
    materials.add(StandardMaterial { base_color: color, perceptual_roughness: 0.92, reflectance: 0.2, ..default() })
}

fn on_ring(angle: f32, radius: f32) -> Vec3 {
    Vec3::new(angle.cos() * radius, 0.0, angle.sin() * radius)
}

fn setup(
    mut commands: Commands,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
    mut village: ResMut<Village>,
) {
    // A stable, slightly elevated orthographic view that always fits the whole village, portrait or landscape, so
    // every home stays where the operator learned it.
    commands.spawn((
        Camera3d::default(),
        Projection::from(OrthographicProjection {
            scaling_mode: ScalingMode::AutoMin { min_width: 20.5, min_height: 16.5 },
            ..OrthographicProjection::default_3d()
        }),
        Transform::from_translation(VIEW).looking_at(AIM, Vec3::Y),
        DistanceFog {
            color: SKY,
            directional_light_color: Color::srgba(1.0, 0.85, 0.65, 0.25),
            directional_light_exponent: 18.0,
            falloff: FogFalloff::Linear { start: 44.0, end: 78.0 },
        },
    ));
    commands.spawn((
        DirectionalLight { color: Color::srgb(1.0, 0.92, 0.80), illuminance: 9000.0, shadows_enabled: true, ..default() },
        Transform::from_xyz(-8.0, 14.0, 6.0).looking_at(Vec3::ZERO, Vec3::Y),
    ));

    // The meadow: a soft island on a warm ground that melts into the sky.
    let ground = matte(&mut materials, Color::srgb(0.918, 0.859, 0.761));
    commands.spawn((Mesh3d(meshes.add(Plane3d::default().mesh().size(140.0, 140.0))), MeshMaterial3d(ground),
                    Transform::from_xyz(0.0, -0.32, 0.0)));
    let grass = matte(&mut materials, Color::srgb(0.502, 0.616, 0.525));
    commands.spawn((Mesh3d(meshes.add(Cylinder::new(9.6, 0.6))), MeshMaterial3d(grass), Transform::from_xyz(0.0, -0.3, 0.0)));
    let path = matte(&mut materials, Color::srgb(0.965, 0.925, 0.855));
    commands.spawn((Mesh3d(meshes.add(Torus::new(4.75, 5.35))), MeshMaterial3d(path),
                    Transform::from_xyz(0.0, -0.05, 0.0).with_scale(Vec3::new(1.0, 0.12, 1.0))));

    // The campfire, where free agents gather.
    let stone = matte(&mut materials, Color::srgb(0.80, 0.77, 0.75));
    for i in 0..9 {
        let a = i as f32 / 9.0 * TAU;
        commands.spawn((Mesh3d(meshes.add(Sphere::new(0.2))), MeshMaterial3d(stone.clone()),
                        Transform::from_translation(on_ring(a, 0.62)).with_scale(Vec3::new(1.0, 0.6, 1.0))));
    }
    let flame = materials.add(StandardMaterial {
        base_color: Color::srgb(0.937, 0.663, 0.475),
        emissive: LinearRgba::rgb(5.0, 2.2, 0.7),
        ..default()
    });
    commands.spawn((Mesh3d(meshes.add(Cone { radius: 0.38, height: 0.9 })), MeshMaterial3d(flame),
                    Transform::from_xyz(0.0, 0.42, 0.0), Fire));
    commands.spawn((PointLight { color: Color::srgb(1.0, 0.68, 0.38), intensity: 60_000.0, range: 9.0, ..default() },
                    Transform::from_xyz(0.0, 1.0, 0.0), Fire));

    // Round, swaying trees around the edge, placed the same way every time.
    let leaves = [matte(&mut materials, Color::srgb(0.369, 0.498, 0.416)), matte(&mut materials, Color::srgb(0.541, 0.659, 0.561))];
    let trunk = matte(&mut materials, Color::srgb(0.545, 0.416, 0.333));
    let crown = meshes.add(Sphere::new(0.75).mesh().ico(2).unwrap());
    let stem = meshes.add(Cylinder::new(0.12, 0.7));
    for i in 0..26 {
        let a = i as f32 * 2.399 + 0.3;
        // On the island's rim, behind the houses, and never in front of the operator's door.
        if (a.rem_euclid(TAU) - PI / 2.0).abs() < 0.45 {
            continue;
        }
        let r = 8.75 + (i as f32 * 1.7).sin() * 0.45;
        let size = 0.62 + ((i * 7) % 5) as f32 * 0.09;
        commands
            .spawn((Transform::from_translation(on_ring(a, r)).with_scale(Vec3::splat(size)), Visibility::default(),
                    Tree(i as f32)))
            .with_children(|tree| {
                tree.spawn((Mesh3d(stem.clone()), MeshMaterial3d(trunk.clone()), Transform::from_xyz(0.0, 0.35, 0.0)));
                tree.spawn((Mesh3d(crown.clone()), MeshMaterial3d(leaves[i % 2].clone()), Transform::from_xyz(0.0, 1.15, 0.0)));
            });
    }

    let shapes = Shapes {
        wall: meshes.add(Cuboid::new(1.0, 0.9, 1.0)),
        roof: meshes.add(Cone { radius: 0.86, height: 0.75 }),
        window: meshes.add(Cuboid::new(0.32, 0.32, 0.04)),
        body: meshes.add(Capsule3d::new(0.22, 0.32)),
        head: meshes.add(Sphere::new(0.24)),
        plane: meshes.add(Cone { radius: 0.16, height: 0.5 }),
        cream: matte(&mut materials, Color::srgb(0.984, 0.957, 0.902)),
    };

    // The operator's house: the biggest one, at the front of the village, facing you. Opening the app is coming home.
    let door = Vec3::new(0.0, 0.0, RING + 0.6);
    let roof = matte(&mut materials, Color::srgb(0.725, 0.376, 0.314));
    let glow = materials.add(StandardMaterial { base_color: Color::srgb(1.0, 0.85, 0.55),
                                                emissive: LinearRgba::rgb(3.0, 2.0, 0.8), ..default() });
    commands
        .spawn((Transform::from_translation(door + Vec3::Z * 0.9).with_scale(Vec3::splat(1.45)), Visibility::default()))
        .with_children(|house| {
            house.spawn((Mesh3d(shapes.wall.clone()), MeshMaterial3d(shapes.cream.clone()), Transform::from_xyz(0.0, 0.45, 0.0)));
            house.spawn((Mesh3d(shapes.roof.clone()), MeshMaterial3d(roof), Transform::from_xyz(0.0, 1.27, 0.0)));
            house.spawn((Mesh3d(shapes.window.clone()), MeshMaterial3d(glow), Transform::from_xyz(0.0, 0.5, -0.51)));
        });
    village.operator_door = door + Vec3::Y * 1.2;
    village.shapes = Some(shapes);
}

/// Spreads the residents around the ring, leaving the front for the operator's house.
fn angles(count: usize) -> Vec<f32> {
    let gap = 0.9;
    let start = PI / 2.0 + gap;
    let span = TAU - 2.0 * gap;
    (0..count).map(|i| start + span * (i as f32 + 0.5) / count.max(1) as f32).collect()
}

fn drain_inbox(
    mut commands: Commands,
    mut village: ResMut<Village>,
    mut materials: ResMut<Assets<StandardMaterial>>,
    mut people: Query<&mut Person>,
    mut houses: Query<&mut Transform, Without<Person>>,
) {
    let items: Vec<Inbound> = match INBOX.lock() {
        Ok(mut inbox) => inbox.drain(..).collect(),
        Err(_) => return,
    };
    let Some(shapes) = village.shapes.clone() else { return };
    for item in items {
        match item {
            Inbound::Agents(mut agents) => {
                agents.retain(|a| a.name != OPERATOR);
                agents.sort_by(|a, b| a.name.cmp(&b.name));
                let names: Vec<String> = agents.iter().map(|a| a.name.clone()).collect();
                let gone: Vec<String> = village.residents.keys().filter(|n| !names.contains(n)).cloned().collect();
                for name in gone {
                    if let Some(resident) = village.residents.remove(&name) {
                        commands.entity(resident.house).despawn();
                        commands.entity(resident.person).despawn();
                    }
                }
                for (agent, angle) in agents.iter().zip(angles(agents.len())) {
                    let lamp_color = |busy: bool| if busy { LinearRgba::rgb(3.2, 2.1, 0.7) } else { LinearRgba::BLACK };
                    if !village.residents.contains_key(&agent.name) {
                        let color = pastel(&agent.name);
                        let roof = matte(&mut materials, color);
                        let coat = matte(&mut materials, color.mix(&Color::WHITE, 0.25));
                        let lamp = materials.add(StandardMaterial { base_color: Color::srgb(0.98, 0.9, 0.7),
                                                                    emissive: lamp_color(agent.busy), ..default() });
                        let spot = on_ring(angle, RING + 0.9);
                        let house = commands
                            .spawn((Transform::from_translation(spot).looking_at(Vec3::new(0.0, 0.0, 0.0), Vec3::Y)
                                        .with_scale(Vec3::splat(1.25)),
                                    Visibility::default()))
                            .with_children(|house| {
                                house.spawn((Mesh3d(shapes.wall.clone()), MeshMaterial3d(shapes.cream.clone()),
                                             Transform::from_xyz(0.0, 0.45, 0.0)));
                                house.spawn((Mesh3d(shapes.roof.clone()), MeshMaterial3d(roof),
                                             Transform::from_xyz(0.0, 1.27, 0.0)));
                                house.spawn((Mesh3d(shapes.window.clone()), MeshMaterial3d(lamp.clone()),
                                             Transform::from_xyz(0.0, 0.5, -0.51)));
                            })
                            .id();
                        let start = on_ring(angle, RING - 0.4);
                        let person = commands
                            .spawn((Transform::from_translation(start), Visibility::default(),
                                    Person { phase: angle * 3.0, target: start, busy: agent.busy }))
                            .with_children(|body| {
                                body.spawn((Mesh3d(shapes.body.clone()), MeshMaterial3d(coat), Transform::from_xyz(0.0, 0.38, 0.0)));
                                body.spawn((Mesh3d(shapes.head.clone()), MeshMaterial3d(shapes.cream.clone()),
                                            Transform::from_xyz(0.0, 0.86, 0.0)));
                            })
                            .id();
                        village.residents.insert(agent.name.clone(),
                                                 Resident { house, person, lamp, angle, busy: agent.busy });
                    }
                    let Some(resident) = village.residents.get_mut(&agent.name) else { continue };
                    if resident.angle != angle {
                        resident.angle = angle;
                        if let Ok(mut transform) = houses.get_mut(resident.house) {
                            *transform = Transform::from_translation(on_ring(angle, RING + 0.9))
                                .looking_at(Vec3::ZERO, Vec3::Y).with_scale(Vec3::splat(1.25));
                        }
                    }
                    resident.busy = agent.busy;
                    if let Some(lamp) = materials.get_mut(&resident.lamp) {
                        lamp.emissive = lamp_color(agent.busy);
                    }
                    if let Ok(mut person) = people.get_mut(resident.person) {
                        person.busy = agent.busy;
                        // Busy: at their own door. Free: a seat by the fire, on their side of it.
                        person.target = if agent.busy { on_ring(angle, RING - 0.4) } else { on_ring(angle, FIRE_RING) };
                    }
                }
            }
            Inbound::Focus(name) => village.focus = name,
            Inbound::Inset(fraction) => village.inset = fraction,
            Inbound::Plane { from, to, topic } => {
                let place = |name: &str| {
                    village.residents.get(name).map(|r| on_ring(r.angle, RING - 0.4) + Vec3::Y * 1.0)
                        .unwrap_or(village.operator_door)
                };
                let (start, end) = (place(&from), place(&to));
                if start.distance(end) < 0.1 {
                    continue;
                }
                let color = match topic.as_str() {
                    "alert" => Color::srgb(0.725, 0.376, 0.314),
                    "request" => Color::srgb(0.937, 0.663, 0.475),
                    "ack" => Color::srgb(0.541, 0.659, 0.561),
                    "evidence" => Color::srgb(0.427, 0.522, 0.631),
                    _ => Color::srgb(0.992, 0.976, 0.945),
                };
                let paper = materials.add(StandardMaterial { base_color: color, perceptual_roughness: 0.7,
                                                             emissive: LinearRgba::from(color) * 0.25, ..default() });
                let distance = start.distance(end);
                commands.spawn((Mesh3d(shapes.plane.clone()), MeshMaterial3d(paper),
                                Transform::from_translation(start).with_scale(Vec3::new(1.0, 0.22, 1.0)),
                                Plane { from: start, to: end, age: 0.0, duration: 1.6 + distance * 0.12,
                                        lift: 1.6 + distance * 0.22 }));
            }
        }
    }
}

fn walk(time: Res<Time>, mut people: Query<(&Person, &mut Transform)>) {
    let step = 1.0 - (-time.delta_secs() * 1.6).exp();
    for (person, mut transform) in &mut people {
        let ground = Vec3::new(transform.translation.x, 0.0, transform.translation.z);
        let next = ground.lerp(person.target, step);
        let heading = next - ground;
        if heading.length_squared() > 1e-6 {
            transform.rotation = transform.rotation.slerp(Quat::from_rotation_y(f32::atan2(heading.x, heading.z)), step * 2.0);
        }
        transform.translation.x = next.x;
        transform.translation.z = next.z;
    }
}

fn bob(time: Res<Time>, mut people: Query<(&Person, &mut Transform)>) {
    let t = time.elapsed_secs();
    for (person, mut transform) in &mut people {
        // Working: a quick, busy hop. Free: slow breathing by the fire.
        let (speed, height) = if person.busy { (7.0, 0.07) } else { (1.6, 0.025) };
        transform.translation.y = ((t * speed + person.phase).sin() * 0.5 + 0.5) * height;
        let squash = 1.0 + (t * speed + person.phase).cos() * height * 0.6;
        transform.scale = Vec3::new(1.0 / squash.sqrt(), squash, 1.0 / squash.sqrt());
    }
}

fn fly_planes(mut commands: Commands, time: Res<Time>, mut planes: Query<(Entity, &mut Plane, &mut Transform)>) {
    for (entity, mut plane, mut transform) in &mut planes {
        plane.age += time.delta_secs();
        let s = (plane.age / plane.duration).min(1.0);
        let eased = s * s * (3.0 - 2.0 * s);
        let at = |u: f32| plane.from.lerp(plane.to, u) + Vec3::Y * (PI * u).sin() * plane.lift;
        let here = at(eased);
        let ahead = at((eased + 0.02).min(1.0));
        transform.translation = here;
        if ahead.distance_squared(here) > 1e-7 {
            // The cone's tip leads; a little roll makes it glide rather than slide.
            let forward = (ahead - here).normalize();
            let roll = (plane.age * 3.0).sin() * 0.35;
            transform.rotation = Quat::from_rotation_arc(Vec3::Y, forward) * Quat::from_rotation_y(roll);
        }
        if s >= 1.0 {
            commands.entity(entity).despawn();
        }
    }
}

fn flicker(time: Res<Time>, mut fire: Query<(Option<&mut PointLight>, &mut Transform), With<Fire>>) {
    let t = time.elapsed_secs();
    let wobble = (t * 11.0).sin() * 0.5 + (t * 17.3).sin() * 0.3 + (t * 5.1).sin() * 0.2;
    for (light, mut transform) in &mut fire {
        match light {
            Some(mut light) => light.intensity = 60_000.0 * (1.0 + wobble * 0.18),
            None => transform.scale = Vec3::new(1.0 - wobble * 0.05, 1.0 + wobble * 0.12, 1.0 - wobble * 0.05),
        }
    }
}

fn sway_trees(time: Res<Time>, mut trees: Query<(&Tree, &mut Transform)>) {
    let t = time.elapsed_secs();
    for (tree, mut transform) in &mut trees {
        transform.rotation = Quat::from_rotation_z((t * 0.9 + tree.0).sin() * 0.035) * Quat::from_rotation_x((t * 0.7 + tree.0 * 1.3).sin() * 0.03);
    }
}

const VIEW: Vec3 = Vec3::new(0.0, 30.0, 19.0);
const AIM: Vec3 = Vec3::new(0.0, 0.4, 0.4);

/// The camera keeps its angle and glides: over the whole village, or closer over the focused home.
fn look(time: Res<Time>, village: Res<Village>, mut eye: Query<(&mut Transform, &mut Projection), With<Camera3d>>) {
    let goal = village.focus.as_ref().and_then(|name| village.residents.get(name))
        .map(|r| (on_ring(r.angle, RING) * 0.55, 0.62))
        .unwrap_or((Vec3::ZERO, 1.0));
    // Moving the aim toward the viewer (+z) slides the scene up the screen, clear of a sheet covering the bottom.
    let goal = (goal.0 + Vec3::Z * village.inset * 11.0 * goal.1, goal.1);
    let step = 1.0 - (-time.delta_secs() * 4.5).exp();
    for (mut transform, mut projection) in &mut eye {
        let aim = transform.translation - VIEW;
        let next = aim.lerp(goal.0, step);
        *transform = Transform::from_translation(VIEW + next).looking_at(AIM + next, Vec3::Y);
        if let Projection::Orthographic(ortho) = projection.as_mut() {
            ortho.scale += (goal.1 - ortho.scale) * step;
        }
    }
}

fn report_labels(village: Res<Village>, eye: Query<(&Camera, &GlobalTransform)>, mut last: Local<String>) {
    let Ok((camera, view)) = eye.single() else { return };
    let Some(size) = camera.logical_viewport_size().filter(|s| s.x > 0.0 && s.y > 0.0) else { return };
    // Fractions of the viewport (in ten-thousandths), so the page places tags in its own CSS pixels whatever scale
    // factor the canvas reports.
    let at = |point: Vec3| camera.world_to_viewport(view, point).ok()
        .map(|p| ((p.x / size.x * 10000.0).round() as i32, (p.y / size.y * 10000.0).round() as i32));
    let mut tags: Vec<(&str, i32, i32)> = village.residents.iter()
        .filter_map(|(name, r)| at(on_ring(r.angle, RING + 0.9) + Vec3::Y * 2.3).map(|(x, y)| (name.as_str(), x, y)))
        .collect();
    if let Some((x, y)) = at(village.operator_door + Vec3::Y * 1.6) {
        tags.push((OPERATOR, x, y));
    }
    tags.sort();
    let json = serde_json::to_string(&tags).unwrap_or_default();
    if *last != json {
        board_world_labels(&json);
        *last = json;
    }
}

fn report_frame(mut frames: Local<u32>) {
    *frames += 1;
    board_world_frame(*frames);
}
