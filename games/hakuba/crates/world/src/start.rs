//! A chosen start instead of the world's spawn: `#start=x,y,z,bearing` after the page's address in the browser, or
//! `HAKUBA_START=x,y,z,bearing` on the desktop. `x`, `y` and `z` are on the map in metres (x east, y north, z up) and
//! the bearing is a compass bearing in degrees east of north, as the world's own spawn is given.

use bevy::prelude::*;

/// The chosen start, in the game's frame, if one is given and valid.
pub fn chosen() -> Option<Transform> {
    parse(&given()?)
}

fn parse(text: &str) -> Option<Transform> {
    let numbers: Vec<f32> = text.split(',').map(|n| n.trim().parse().ok()).collect::<Option<_>>()?;
    let [x, y, z, bearing] = numbers[..] else { return None };
    [x, y, z, bearing]
        .iter()
        .all(|n| n.is_finite())
        .then(|| Transform::from_xyz(x, z, -y).with_rotation(Quat::from_rotation_y(-bearing.to_radians())))
}

#[cfg(target_arch = "wasm32")]
fn given() -> Option<String> {
    let hash = web_sys::window()?.location().hash().ok()?;
    hash.strip_prefix("#start=").map(str::to_owned)
}

#[cfg(not(target_arch = "wasm32"))]
fn given() -> Option<String> {
    std::env::var("HAKUBA_START").ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_map_start_turns_into_the_game_frame() {
        let start = parse("10, 20, 5, 90").unwrap();
        assert_eq!(start.translation, Vec3::new(10.0, 5.0, -20.0));
        // Facing east: the character's front (+Z) turns to +X.
        assert!(
            (start.rotation * Vec3::Z - Vec3::X).length() < 1e-5
                || (start.rotation * Vec3::NEG_Z - Vec3::X).length() < 1e-5
        );
        assert!(parse("1,2,3").is_none());
        assert!(parse("1,2,x,4").is_none());
    }
}
