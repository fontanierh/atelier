//! The player's paraglider (`hakuba_glider`): each player has one from the start, put away. It is held while the
//! player glides and as they start putting it away, and banks into turns.

use bevy::prelude::*;
use hakuba_characters::Playing;
use hakuba_glider::Glider;

use crate::Player;
use crate::moves::{Action, Mode};

/// How far into putting it away the paraglider goes, in seconds of the clip.
const PUT_AWAY_S: f32 = 0.1;

/// How far it banks for each radian a second the glide turns, at most `MOST_BANK_DEG`.
const BANK_PER_TURN: f32 = 0.12;
const MOST_BANK_DEG: f32 = 12.0;

/// Gives each player's character its paraglider, put away.
pub(crate) fn spawn(mut commands: Commands, players: Query<&Player, Added<Player>>) {
    for player in &players {
        commands.entity(player.body).with_child(Glider::of(player.body));
    }
}

/// Holds the paraglider while the player glides and as they start putting it away, banking it into turns.
pub(crate) fn steer(players: Query<&Player>, bodies: Query<&Playing>, mut gliders: Query<&mut Glider>) {
    for player in &players {
        let Some(mut glider) = gliders.iter_mut().find(|glider| glider.ready_for(player.body)) else { continue };
        let Ok(playing) = bodies.get(player.body) else { continue };
        let motion = &player.motion;
        glider.held = motion.mode == Mode::Glide || (motion.action == Action::GlideClose && playing.time < PUT_AWAY_S);
        let most = MOST_BANK_DEG.to_radians();
        glider.bank = (motion.glide_turn() * BANK_PER_TURN).clamp(-most, most);
    }
}
