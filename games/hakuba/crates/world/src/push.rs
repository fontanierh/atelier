//! Plants moving aside: an entity that carries [`PushesPlants`] parts the grass and bushes around it as it walks
//! through them. Each frame the places of up to [`MOST`] such entities, the nearest to the camera, go to the swaying
//! shader (`wind.wesl`) in one small buffer that every swaying material shares, so no material changes and plants are
//! still drawn together. Plants lean straight away from each one, most at its middle and not at all past its radius,
//! and stand up again as soon as it has gone: the push follows where it is now, not where it was.

use bevy::prelude::*;
use bevy::render::storage::ShaderBuffer;
use bevy::transform::TransformSystems;

/// How many entities can push plants at once.
pub const MOST: usize = 4;

/// Something that pushes plants aside: leaves and blades within `radius_m` of it across the ground, and from its feet,
/// its origin, up to `height_m` above them, lean away from it.
#[derive(Component, Clone, Copy, Debug)]
pub struct PushesPlants {
    pub radius_m: f32,
    pub height_m: f32,
}

impl Default for PushesPlants {
    /// A person: plants part across 1.7 m around them, up to 1.8 m high.
    fn default() -> Self {
        PushesPlants { radius_m: 1.7, height_m: 1.8 }
    }
}

pub struct PushPlugin;

impl Plugin for PushPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Startup, make).add_systems(PostUpdate, feed.after(TransformSystems::Propagate));
    }
}

/// The buffer the swaying shader reads the pushers from: first how many there are, then two four-number rows for
/// each: where its feet are and its radius, then its height. Always the same size, so the GPU keeps one buffer and
/// only rewrites it.
#[derive(Resource, Clone)]
pub struct Pushers(pub Handle<ShaderBuffer>);

/// The buffer's rows.
const ROWS: usize = 1 + 2 * MOST;

fn make(mut commands: Commands, mut buffers: ResMut<Assets<ShaderBuffer>>) {
    commands.insert_resource(Pushers(buffers.add(ShaderBuffer::from(vec![[0.0f32; 4]; ROWS]))));
}

/// Writes where the pushers nearest the camera are into the buffer, every frame.
fn feed(
    pushers: Res<Pushers>,
    mut buffers: ResMut<Assets<ShaderBuffer>>,
    all: Query<(&GlobalTransform, &PushesPlants)>,
    camera: Query<&GlobalTransform, With<Camera3d>>,
) {
    let eye = camera.iter().next().map_or(Vec3::ZERO, GlobalTransform::translation);
    let mut near: Vec<(Vec3, PushesPlants)> = all.iter().map(|(at, pushes)| (at.translation(), *pushes)).collect();
    if near.len() > MOST {
        near.sort_by(|a, b| a.0.distance_squared(eye).total_cmp(&b.0.distance_squared(eye)));
        near.truncate(MOST);
    }
    let mut rows = vec![[0.0f32; 4]; ROWS];
    rows[0][0] = near.len() as f32;
    for (i, (at, pushes)) in near.iter().enumerate() {
        rows[1 + 2 * i] = [at.x, at.y, at.z, pushes.radius_m.max(0.01)];
        rows[2 + 2 * i] = [pushes.height_m, 0.0, 0.0, 0.0];
    }
    if buffers.get(&pushers.0).and_then(|buffer| buffer.cast_slice::<[f32; 4]>()) == Some(&rows[..]) {
        return;
    }
    let Some(mut buffer) = buffers.get_mut(&pushers.0) else { return };
    buffer.clear();
    buffer.extend(rows);
}
