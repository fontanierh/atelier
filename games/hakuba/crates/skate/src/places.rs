//! Saved-places bar and marker HUD. Native Pad actions still own placement, hold timing and travel.
use super::{Ride, RideInput, frame};
use crate::{Controls, MarkerSnapshot, MarkerStatus, Session};
use bevy::input::{ButtonState, keyboard::KeyboardInput};
use bevy::prelude::*;
use hakuba_screens::Screen;
use hakuba_settings::{Settings, SkateMarker};

#[derive(Resource, Default)]
pub(super) struct Places {
    open: bool,
    editing: Option<Editor>,
    save_requested: bool,
    save_release_ticks: u8,
    delete_confirm: bool,
    returning: bool,
    close_requested: bool,
    suppress_return: bool,
    pub status: MarkerStatus,
    flash: String,
}
struct Editor {
    name: String,
    rename: bool,
    marker: Option<SkateMarker>,
    letter: usize,
}
#[derive(Component)]
pub(super) struct PlacesHud;
#[cfg(test)]
#[path = "places_tests.rs"]
mod tests;

const LETTERS: &str = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 -_";

fn kept(marker: MarkerSnapshot) -> SkateMarker {
    SkateMarker { transform: marker.transform, on_board: marker.on_board, foot_forward: marker.foot_forward }
}
fn native(marker: SkateMarker) -> MarkerSnapshot {
    MarkerSnapshot { transform: marker.transform, on_board: marker.on_board, foot_forward: marker.foot_forward }
}
pub(super) fn restore(session: &mut Session, settings: &Settings) -> Result<(), String> {
    session.restore_marker(settings.skate_places.marker.map(native))
}
/// A held return requests destination collision before the native action is advanced.
pub(super) fn target(places: &Places, settings: &Settings) -> Option<Vec3> {
    places
        .returning
        .then_some(settings.skate_places.marker)
        .flatten()
        .map(|m| frame::world_point(Vec3::from_slice(&m.transform[3][..3])))
}
/// A bar save is one debounced native press, including release of any prior raw placement chord.
/// Called once per physics tick so catch-up frames and high render rates use the same Pad sequence.
pub(super) fn packet(places: &mut Places, raw: Controls) -> Controls {
    if !places.save_requested {
        return raw;
    }
    if places.save_release_ticks > 0 {
        places.save_release_ticks -= 1;
        Controls::default()
    } else {
        Controls { buttons: 0x0102, ..Default::default() }
    }
}

pub(super) fn publish(session: &Session, places: &mut Places, settings: &mut Settings) {
    let old = places.status;
    places.status = session.marker_status();
    let marker = session.marker().map(kept);
    if settings.skate_places.marker != marker {
        settings.skate_places.marker = marker;
    }
    if places.status.placements != old.placements {
        places.flash = "Marker placed".into();
        if places.save_requested {
            places.save_requested = false;
            places.editing = Some(Editor { name: settings.skate_places.next_name(), rename: false, marker, letter: 0 });
        }
    } else if places.save_requested
        && places.save_release_ticks == 0
        && places.status.visible
        && !places.status.can_place
    {
        places.save_requested = false;
        places.flash = "Stand on clear, stable ground to save a place.".into();
    }
    if places.status.returns != old.returns {
        places.flash = "Returned to marker".into();
    }
}

pub(super) fn spawn(mut commands: Commands) {
    commands.spawn((
        PlacesHud,
        DespawnOnExit(Screen::World),
        Node { position_type: PositionType::Absolute, right: px(22), bottom: px(100), max_width: px(640), ..default() },
        Text::new(""),
        TextFont { font_size: FontSize::Px(17.), ..default() },
        TextColor(Color::srgb(1., 0.95, 0.75)),
    ));
}

/// Consume global pause shortcuts before Screens sees them; close only this focused bar.
pub(super) fn capture_close(
    mut places: ResMut<Places>,
    mut keys: ResMut<ButtonInput<KeyCode>>,
    mut pads: Query<&mut Gamepad>,
) {
    if !places.open {
        return;
    }
    if keys.just_pressed(KeyCode::Escape) {
        places.close_requested = true;
        keys.clear_just_pressed(KeyCode::Escape);
    }
    for mut pad in &mut pads {
        if pad.just_pressed(GamepadButton::Start) {
            places.close_requested = true;
            pad.digital_mut().clear_just_pressed(GamepadButton::Start);
        }
    }
}

/// P / LB+DPadLeft opens the bar. The selected controller is the same one used by RideInput.
pub(super) fn read(
    mut places: ResMut<Places>,
    mut ride: ResMut<Ride>,
    mut input: ResMut<RideInput>,
    keys: Res<ButtonInput<KeyCode>>,
    pads: Query<&Gamepad>,
    mut typed: MessageReader<KeyboardInput>,
    mut settings: ResMut<Settings>,
) {
    if ride.session.is_none() {
        places.status = MarkerStatus::default();
        places.open = false;
        places.editing = None;
        places.save_requested = false;
    }
    let pad = input.selected_pad().and_then(|entity| pads.get(entity).ok());
    let pressed = |button| pad.is_some_and(|p| p.just_pressed(button));
    let held = |button| pad.is_some_and(|p| p.pressed(button));
    let opened =
        keys.just_pressed(KeyCode::KeyP) || (held(GamepadButton::LeftTrigger) && pressed(GamepadButton::DPadLeft));
    if opened && ride.session.is_some() {
        places.open = !places.open;
        places.suppress_return = true;
        places.editing = None;
        places.delete_confirm = false;
        places.save_requested = false;
    }
    let mut was_returning = places.returning;
    places.returning = false;
    if !places.open {
        typed.clear();
        places.returning = input.packet.buttons & 0x0101 == 0x0101;
        if places.returning && settings.skate_places.marker.is_none() {
            places.flash = "Place a marker first: M+Down / LB+DPadDown".into();
        }
        return;
    }
    // No push, bail, recovery, mount, grab or transfer leaks through the focused bar.
    input.consume_modal();
    if places.close_requested
        || keys.just_pressed(KeyCode::Escape)
        || pressed(GamepadButton::East)
        || pressed(GamepadButton::Select)
        || pressed(GamepadButton::Start)
    {
        places.close_requested = false;
        places.editing = None;
        places.open = false;
        places.save_requested = false;
        typed.clear();
        return;
    }
    if let Some(mut editor) = places.editing.take() {
        places.suppress_return = true;
        for event in typed.read().filter(|event| event.state == ButtonState::Pressed) {
            if event.key_code == KeyCode::Backspace {
                editor.name.pop();
            } else if let Some(text) = &event.text {
                for c in text.chars().filter(|c| !c.is_control()) {
                    if editor.name.chars().count() < 48 {
                        editor.name.push(c);
                    }
                }
            }
        }
        if pressed(GamepadButton::DPadLeft) {
            editor.letter = (editor.letter + LETTERS.len() - 1) % LETTERS.len();
        }
        if pressed(GamepadButton::DPadRight) {
            editor.letter = (editor.letter + 1) % LETTERS.len();
        }
        if pressed(GamepadButton::North) && editor.name.chars().count() < 48 {
            editor.name.push(LETTERS.as_bytes()[editor.letter] as char);
        }
        if pressed(GamepadButton::West) {
            editor.name.pop();
        }
        if keys.just_pressed(KeyCode::Enter) || pressed(GamepadButton::South) {
            let result = if editor.rename {
                settings.skate_places.rename(&editor.name)
            } else {
                editor
                    .marker
                    .ok_or_else(|| "Place a marker first.".to_owned())
                    .and_then(|m| settings.skate_places.add(&editor.name, m))
            };
            match result {
                Ok(()) => {
                    places.flash = "Place saved".into();
                }
                Err(error) => {
                    places.flash = error;
                    places.editing = Some(editor);
                }
            }
        } else {
            places.editing = Some(editor);
        }
        return;
    }
    typed.clear();
    if !keys.pressed(KeyCode::Enter) && !held(GamepadButton::South) {
        places.suppress_return = false;
    }
    if places.save_requested {
        return;
    }
    let direction = if keys.just_pressed(KeyCode::ArrowLeft) || pressed(GamepadButton::DPadLeft) {
        -1
    } else if keys.just_pressed(KeyCode::ArrowRight) || pressed(GamepadButton::DPadRight) {
        1
    } else {
        0
    };
    if direction != 0 && !opened {
        settings.skate_places.cycle(direction);
        places.delete_confirm = false;
        was_returning = false;
    }
    if keys.just_pressed(KeyCode::Delete) || pressed(GamepadButton::DPadDown) {
        if places.delete_confirm {
            settings.skate_places.delete();
            places.flash = "Place deleted".into();
            places.delete_confirm = false;
        } else {
            places.delete_confirm = settings.skate_places.selected().is_some();
        }
    } else if keys.just_pressed(KeyCode::F2) || pressed(GamepadButton::West) {
        if let Some(saved) = settings.skate_places.selected() {
            places.editing = Some(Editor { name: saved.name.clone(), rename: true, marker: None, letter: 0 });
            places.delete_confirm = false;
        }
    } else if keys.just_pressed(KeyCode::KeyN) || keys.just_pressed(KeyCode::F5) || pressed(GamepadButton::North) {
        if ride.session.is_some() {
            places.save_requested = true;
            places.save_release_ticks = 4;
            places.delete_confirm = false;
        } else {
            places.flash = "Get on or carry the skateboard before saving a place.".into();
        }
    } else if !places.suppress_return && (keys.pressed(KeyCode::Enter) || held(GamepadButton::South)) {
        places.delete_confirm = false;
        if let Some(saved) = settings.skate_places.selected() {
            let marker = saved.marker;
            if let Some(session) = ride.session.as_mut() {
                if !was_returning {
                    match session.restore_marker(Some(native(marker))) {
                        Ok(()) => settings.skate_places.marker = Some(marker),
                        Err(error) => {
                            places.flash = error;
                            return;
                        }
                    }
                }
                places.returning = true;
                input.packet.buttons = 0x0101;
            } else {
                places.flash = "Get on or carry the skateboard before returning.".into();
            }
        } else {
            places.flash = "Save a place first.".into();
        }
    }
}

pub(super) fn set_hud_text(text: &mut Mut<Text>, next: std::borrow::Cow<'_, str>) -> bool {
    if text.0 == next.as_ref() {
        return false;
    }
    text.0 = next.into_owned();
    true
}

pub(super) fn hud(places: Res<Places>, settings: Res<Settings>, mut text: Query<&mut Text, With<PlacesHud>>) {
    for mut text in &mut text {
        let s = places.status;
        let next = if let Some(editor) = &places.editing {
            std::borrow::Cow::Owned(format!(
                "{} place: {}_\nType a name | Enter/A save | Esc/B cancel\nController: left/right choose [{}] | Y append | X erase",
                if editor.rename { "Rename" } else { "Save" },
                editor.name,
                LETTERS.as_bytes()[editor.letter] as char
            ))
        } else if places.open {
            let name = settings.skate_places.selected().map_or("No saved places", |m| m.name.as_str());
            let return_line = if places.returning {
                std::borrow::Cow::Owned(format!(
                    "Return {:.0}% | {}",
                    s.progress * 100.,
                    if s.can_return { "hold Enter/A" } else { "destination unavailable" }
                ))
            } else {
                std::borrow::Cow::Borrowed("Hold Enter/A return | P or Esc/B close")
            };
            std::borrow::Cow::Owned(format!(
                "Saved places | {}\n{}\n{}\n{}",
                name,
                if places.delete_confirm {
                    "Delete again / DPadDown again to delete"
                } else {
                    "Left/right choose | N/Y save here | F2/X rename | Delete/Down twice delete"
                },
                return_line,
                places.flash
            ))
        } else if s.visible || places.returning {
            std::borrow::Cow::Owned(format!(
                "Marker | place {} | return {} | {:.0}%\n{}",
                if s.can_place { "ready" } else { "blocked" },
                if s.can_return { "ready" } else { "unavailable" },
                s.progress * 100.,
                places.flash
            ))
        } else {
            std::borrow::Cow::Borrowed(
                "M+Down place | hold M+Up return | LB+DPad Down/Up | P / LB+DPad Left saved places",
            )
        };
        set_hud_text(&mut text, next);
    }
}
