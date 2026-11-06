//! Levels of detail picked by how big a thing looks rather than by how far it is, as Unreal picks them by screen
//! size. The distances at which a tree swaps to its impostor, or a small plant to its middle version, were chosen
//! looking through Bevy's default field of view (in the forest lab and on foot). A wider view shows everything
//! smaller: through the skateboard's, around 68°, a tree 123 m away looks as big as one 200 m away on foot, yet kept its
//! full version, and the riding view drew so many triangles that Apple's GPU split the main pass in two. So each such
//! [`Detail`] range is drawn scaled by how much smaller the camera shows things than the default view does, and never
//! beyond its authored distances: a swap happens at the same size on screen whatever the view.
//!
//! Only swaps between versions of one thing scale. A shadow's reach and a tile's fade belong to the tiles' streaming
//! distances and stay where they are.

use bevy::camera::visibility::{VisibilityRange, VisibilitySystems};
use bevy::prelude::*;

use crate::WorldCamera;

/// How far the drawn scale may drift from the camera's before every [`Detail`] range is rewritten: the riding camera's
/// view breathes a little all the time, and rewriting tens of thousands of ranges each frame would cost more than it
/// saves.
const RESCALE_STEP: f32 = 0.04;

/// A range between versions of one thing, as authored for Bevy's default field of view. Its entity's
/// [`VisibilityRange`] is this scaled to the camera's view.
#[derive(Component, Clone)]
pub(crate) struct Detail(pub VisibilityRange);

/// The scale the [`Detail`] ranges are drawn at.
#[derive(Resource)]
struct Drawn(f32);

pub(crate) struct DetailPlugin;

impl Plugin for DetailPlugin {
    fn build(&self, app: &mut App) {
        app.insert_resource(Drawn(1.0)).add_systems(PostUpdate, rescale.before(VisibilitySystems::CheckVisibility));
    }
}

/// How much smaller a camera with vertical field of view `fov` (radians) shows things than Bevy's default view does,
/// never more than 1.
pub(crate) fn scale(fov: f32) -> f32 {
    let default = PerspectiveProjection::default().fov;
    ((default / 2.0).tan() / (fov / 2.0).tan()).clamp(0.0, 1.0)
}

/// `authored` drawn at `scale`.
fn scaled(authored: &VisibilityRange, scale: f32) -> VisibilityRange {
    let by = |r: &std::ops::Range<f32>| r.start * scale..r.end * scale;
    VisibilityRange { start_margin: by(&authored.start_margin), end_margin: by(&authored.end_margin), ..*authored }
}

/// Follows the world camera's field of view: new [`Detail`] ranges are drawn at the current scale, and every one is
/// rewritten once the camera's scale has drifted a step from it.
fn rescale(
    mut drawn: ResMut<Drawn>,
    camera: Query<&Projection, With<WorldCamera>>,
    mut ranges: Query<(Ref<Detail>, &mut VisibilityRange)>,
) {
    let wanted = match camera.single() {
        Ok(Projection::Perspective(perspective)) => scale(perspective.fov),
        _ => 1.0,
    };
    let all = (wanted - drawn.0).abs() >= RESCALE_STEP || (wanted == 1.0 && drawn.0 != 1.0);
    if all {
        drawn.0 = wanted;
    }
    for (detail, mut range) in &mut ranges {
        if all || detail.is_added() {
            *range = scaled(&detail.0, drawn.0);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_default_view_draws_ranges_as_authored_and_a_wider_one_nearer() {
        let default = PerspectiveProjection::default().fov;
        assert_eq!(scale(default), 1.0);
        assert_eq!(scale(default / 2.0), 1.0, "a narrower view never draws beyond the authored distances");
        let riding = scale(68f32.to_radians());
        assert!(
            (riding * 200.0 - 123.0).abs() < 1.0,
            "a tree 200 m away on foot looks as big as one 123 m away riding"
        );
    }

    #[test]
    fn a_range_follows_the_camera_only_once_it_has_drifted_a_step() {
        let mut app = App::new();
        app.add_plugins(DetailPlugin);
        let authored = VisibilityRange { start_margin: 0.0..0.0, end_margin: 180.0..220.0, use_aabb: false };
        let camera = app.world_mut().spawn((WorldCamera, Projection::Perspective(default()))).id();
        let tree = app.world_mut().spawn((Detail(authored.clone()), authored.clone())).id();
        app.update();
        assert_eq!(app.world().get::<VisibilityRange>(tree).unwrap().end_margin, 180.0..220.0);

        let fov = |app: &mut App, degrees: f32| {
            let mut projection = app.world_mut().get_mut::<Projection>(camera).unwrap();
            let Projection::Perspective(perspective) = &mut *projection else { unreachable!() };
            perspective.fov = degrees.to_radians();
        };
        fov(&mut app, 46.0);
        app.update();
        assert_eq!(app.world().get::<VisibilityRange>(tree).unwrap().end_margin, 180.0..220.0, "within a step");

        fov(&mut app, 68.0);
        app.update();
        let end = app.world().get::<VisibilityRange>(tree).unwrap().end_margin.clone();
        let s = scale(68f32.to_radians());
        assert!((end.start - 180.0 * s).abs() < 1e-3 && (end.end - 220.0 * s).abs() < 1e-3);

        let late = app.world_mut().spawn((Detail(authored.clone()), authored)).id();
        app.update();
        assert_eq!(app.world().get::<VisibilityRange>(late).unwrap().end_margin, end, "a new range is drawn at once");

        fov(&mut app, 45.0);
        app.update();
        assert_eq!(app.world().get::<VisibilityRange>(tree).unwrap().end_margin, 180.0..220.0, "back as authored");
    }
}
