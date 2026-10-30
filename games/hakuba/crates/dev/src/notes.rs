//! Notes on the world: N takes one (a screenshot, where the camera is and what it looks at, and the text typed for it)
//! and X exports them all as a zip.

use std::fmt::Write;

use bevy::prelude::*;
use bevy::render::view::screenshot::{Screenshot, ScreenshotCaptured};
use hakuba_world::Ground;
use image::ImageEncoder;
use image::codecs::png::{CompressionType, FilterType, PngEncoder};

/// How far the camera's look reaches for the point a note is about, in metres.
const LOOK_REACH_M: f32 = 3000.0;
/// How far under the camera a note's start looks for ground to stand on, in metres.
const START_REACH_M: f32 = 5000.0;
/// Screenshots wider than this are halved until they are not, to keep the notes small.
const WIDEST_PX: u32 = 1920;

#[derive(Resource, Default)]
pub struct Notes {
    pub taken: Vec<Note>,
    /// Whether a note's screenshot is on its way, so the keys stay out of it.
    pub taking: bool,
    /// The last thing a note or an export did, shown over the keys.
    pub flash: Option<String>,
}

pub struct Note {
    /// On the map, in metres (x east, y north, z up).
    camera: Vec3,
    bearing_deg: f32,
    pitch_deg: f32,
    looking_at: Option<Vec3>,
    /// Where the player could stand to see it: the ground under the camera, or the camera itself.
    start: Vec3,
    text: String,
    png: Vec<u8>,
}

/// "1 note", "2 notes".
pub fn counted(notes: usize) -> String {
    if notes == 1 { "1 note".to_owned() } else { format!("{notes} notes") }
}

/// A point in the game's frame on the map.
pub fn map(at: Vec3) -> Vec3 {
    Vec3::new(at.x, -at.z, at.y)
}

/// N or a controller's North button: takes a screenshot without the keys over it, then asks for the note's text.
pub fn take(
    mut commands: Commands,
    keys: Res<ButtonInput<KeyCode>>,
    gamepads: Query<&Gamepad>,
    mut notes: ResMut<Notes>,
    mut ground: Ground,
    camera: Single<&Transform, With<Camera3d>>,
) {
    let pressed = keys.just_pressed(KeyCode::KeyN) || gamepads.iter().any(|g| g.just_pressed(GamepadButton::North));
    if !pressed || notes.taking {
        return;
    }
    let ahead = camera.forward();
    let looking_at = ground.cast(camera.translation, ahead, LOOK_REACH_M).map(|hit| map(hit.point));
    let start = ground.cast(camera.translation, Dir3::NEG_Y, START_REACH_M).map_or(camera.translation, |hit| hit.point);
    let note = Note {
        camera: map(camera.translation),
        bearing_deg: ahead.x.atan2(-ahead.z).to_degrees().rem_euclid(360.0),
        pitch_deg: ahead.y.clamp(-1.0, 1.0).asin().to_degrees(),
        looking_at,
        start: map(start),
        text: String::new(),
        png: Vec::new(),
    };
    notes.taking = true;
    let mut pending = Some(note);
    // The keys hide this frame, so the screenshot taken as it renders shows the world alone.
    commands.spawn(Screenshot::primary_window()).observe(
        move |captured: On<ScreenshotCaptured>, mut notes: ResMut<Notes>, mut keys: ResMut<ButtonInput<KeyCode>>| {
            let Some(mut note) = pending.take() else { return };
            notes.taking = false;
            let asked = ask(notes.taken.len() + 1);
            // The prompt kept the keys let go meanwhile from the game.
            keys.reset_all();
            let Some(text) = asked else {
                notes.flash = Some("Note dropped".into());
                return;
            };
            note.text = text;
            note.png = png(&captured.image).unwrap_or_default();
            notes.taken.push(note);
            notes.flash = Some(format!("Note {} kept", notes.taken.len()));
        },
    );
}

/// The screenshot as a PNG, halved until it is at most `WIDEST_PX` wide.
fn png(image: &Image) -> Option<Vec<u8>> {
    let mut shot = image.clone().try_into_dynamic().ok()?.to_rgb8();
    while shot.width() > WIDEST_PX {
        let (width, height) = (shot.width() / 2, shot.height() / 2);
        shot = image::imageops::resize(&shot, width, height, image::imageops::FilterType::Triangle);
    }
    let mut png = Vec::new();
    PngEncoder::new_with_quality(&mut png, CompressionType::Fast, FilterType::Adaptive)
        .write_image(&shot, shot.width(), shot.height(), image::ExtendedColorType::Rgb8)
        .ok()?;
    Some(png)
}

/// The text typed for note `number`, or none if it was cancelled.
#[cfg(target_arch = "wasm32")]
fn ask(number: usize) -> Option<String> {
    let window = web_sys::window()?;
    window.prompt_with_message(&format!("Note {number}: what is wrong here?")).ok().flatten()
}

/// On the desktop there is nowhere to type: the note keeps its screenshot and place.
#[cfg(not(target_arch = "wasm32"))]
fn ask(_number: usize) -> Option<String> {
    Some(String::new())
}

/// X: exports every note.
pub fn export(keys: Res<ButtonInput<KeyCode>>, mut notes: ResMut<Notes>) {
    if !keys.just_pressed(KeyCode::KeyX) {
        return;
    }
    if notes.taken.is_empty() {
        notes.flash = Some("No notes yet: N takes one".into());
        return;
    }
    let zip = crate::zip::stored(&files(&notes.taken));
    notes.flash = Some(match save(&zip) {
        Ok(place) => format!("Exported {}: {place}", counted(notes.taken.len())),
        Err(error) => format!("The export failed: {error}"),
    });
}

/// `notes.md`, then each note's screenshot.
fn files(notes: &[Note]) -> Vec<(String, Vec<u8>)> {
    let mut markdown = String::from("# Hakuba notes\n\nMap metres: x east, y north, z up. Bearings east of north.\n");
    let mut files = Vec::new();
    for (index, note) in notes.iter().enumerate() {
        let number = index + 1;
        let shot = format!("note-{number:02}.png");
        let text = if note.text.trim().is_empty() { "(no text)" } else { note.text.trim() };
        let [x, y, z] = note.camera.to_array();
        let [sx, sy, sz] = note.start.to_array();
        let _ = write!(
            markdown,
            "\n## {number}. {text}\n\n- Camera: {x:.1}, {y:.1}, {z:.1}, bearing {:.0}°, pitch {:.0}°\n",
            note.bearing_deg, note.pitch_deg,
        );
        match note.looking_at {
            Some(at) => {
                let _ = writeln!(markdown, "- Looking at: {:.1}, {:.1}, {:.1}", at.x, at.y, at.z);
            }
            None => markdown.push_str("- Looking at: nothing within reach\n"),
        }
        let _ = writeln!(markdown, "- Stand here: `#start={sx:.1},{sy:.1},{sz:.1},{:.0}`", note.bearing_deg);
        if !note.png.is_empty() {
            let _ = writeln!(markdown, "\n![note {number}]({shot})");
            files.push((shot, note.png.clone()));
        }
    }
    files.insert(0, ("notes.md".to_owned(), markdown.into_bytes()));
    files
}

/// Downloads the zip, and sends it to `notes/` beside the page.
#[cfg(target_arch = "wasm32")]
fn save(zip: &[u8]) -> Result<&'static str, String> {
    use wasm_bindgen::JsCast;
    let failed = |error: wasm_bindgen::JsValue| format!("{error:?}");
    let window = web_sys::window().ok_or("no window")?;
    let bytes = js_sys::Uint8Array::from(zip);
    let options = web_sys::BlobPropertyBag::new();
    options.set_type("application/zip");
    let blob =
        web_sys::Blob::new_with_u8_array_sequence_and_options(&js_sys::Array::of1(&bytes), &options).map_err(failed)?;
    let url = web_sys::Url::create_object_url_with_blob(&blob).map_err(failed)?;
    let link: web_sys::HtmlAnchorElement =
        window.document().ok_or("no document")?.create_element("a").map_err(failed)?.unchecked_into();
    link.set_href(&url);
    link.set_download("hakuba-notes.zip");
    link.click();
    // Sent too, so the notes reach the server even when the download stays on another device; a server that keeps
    // none answers with an error, which changes nothing here.
    let init = web_sys::RequestInit::new();
    init.set_method("POST");
    init.set_body(&blob);
    let _ = window.fetch_with_str_and_init("notes/", &init);
    Ok("downloaded hakuba-notes.zip, and sent")
}

/// Writes the zip to the current folder.
#[cfg(not(target_arch = "wasm32"))]
fn save(zip: &[u8]) -> Result<&'static str, String> {
    std::fs::write("hakuba-notes.zip", zip).map_err(|error| error.to_string())?;
    Ok("wrote hakuba-notes.zip")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_notes_list_every_note_and_its_screenshot() {
        let note = |text: &str, png: Vec<u8>| Note {
            camera: Vec3::new(560.0, 400.0, 60.0),
            bearing_deg: 90.0,
            pitch_deg: -10.0,
            looking_at: None,
            start: Vec3::new(560.0, 400.0, 48.3),
            text: text.into(),
            png,
        };
        let files = files(&[note("Tree in the lane", vec![1, 2]), note("", Vec::new())]);
        let names: Vec<_> = files.iter().map(|(name, _)| name.as_str()).collect();
        assert_eq!(names, ["notes.md", "note-01.png"]);
        let markdown = String::from_utf8(files[0].1.clone()).unwrap();
        assert!(markdown.contains("## 1. Tree in the lane"));
        assert!(markdown.contains("`#start=560.0,400.0,48.3,90`"));
        assert!(markdown.contains("![note 1](note-01.png)"));
        assert!(markdown.contains("## 2. (no text)"));
    }
}
