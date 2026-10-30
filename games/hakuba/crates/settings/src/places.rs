//! Saved skating destinations, stored inside the normal desktop/browser settings document.
use serde::{Deserialize, Serialize};

/// Exact simulation-world marker frame; the runtime owns coordinate conversion and travel validation.
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct SkateMarker {
    pub transform: [[f32; 4]; 4],
    pub on_board: bool,
    pub foot_forward: bool,
}
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct SavedSkatePlace {
    pub name: String,
    pub marker: SkateMarker,
}
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct SkatePlaces {
    pub marker: Option<SkateMarker>,
    pub saved: Vec<SavedSkatePlace>,
    pub selected: Option<usize>,
}
impl SkatePlaces {
    pub fn selected(&self) -> Option<&SavedSkatePlace> {
        self.selected.and_then(|i| self.saved.get(i))
    }
    pub fn next_name(&self) -> String {
        (1..)
            .map(|i| format!("Marker {i}"))
            .find(|name| !self.saved.iter().any(|m| m.name.eq_ignore_ascii_case(name)))
            .unwrap()
    }
    fn name(&self, input: &str, except: Option<usize>) -> Result<String, String> {
        let name = input.trim();
        if name.is_empty() || name.chars().count() > 48 || name.chars().any(char::is_control) {
            return Err("Use a name of 1 to 48 characters.".into());
        }
        if self.saved.iter().enumerate().any(|(i, m)| Some(i) != except && m.name.to_lowercase() == name.to_lowercase())
        {
            return Err("That name is already saved.".into());
        }
        Ok(name.into())
    }
    pub fn add(&mut self, input: &str, marker: SkateMarker) -> Result<(), String> {
        let name = self.name(input, None)?;
        if self.saved.len() >= 64 {
            return Err("64 places saved. Delete one before saving another.".into());
        }
        self.saved.push(SavedSkatePlace { name, marker });
        self.selected = Some(self.saved.len() - 1);
        Ok(())
    }
    pub fn rename(&mut self, input: &str) -> Result<(), String> {
        let i = self.selected.filter(|i| *i < self.saved.len()).ok_or("Select a saved place first.")?;
        let name = self.name(input, Some(i))?;
        self.saved[i].name = name;
        Ok(())
    }
    pub fn cycle(&mut self, delta: isize) {
        if self.saved.is_empty() {
            self.selected = None;
        } else {
            self.selected =
                Some((self.selected.unwrap_or(0) as isize + delta).rem_euclid(self.saved.len() as isize) as usize);
        }
    }
    pub fn delete(&mut self) {
        if let Some(i) = self.selected.filter(|i| *i < self.saved.len()) {
            self.saved.remove(i);
            self.selected = if self.saved.is_empty() { None } else { Some(i.min(self.saved.len() - 1)) };
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn names_selection_and_exact_native_frame_survive_settings_reload() {
        let mut settings = crate::Settings::default();
        let marker = SkateMarker {
            transform: [[1., 0., 0., 0.], [0., 1., 0., 0.], [0., 0., 1., 0.], [123.25, 4.5, -87.75, 0.]],
            on_board: true,
            foot_forward: false,
        };
        settings.skate_places.marker = Some(marker);
        settings.skate_places.add("  First line  ", marker).unwrap();
        assert!(settings.skate_places.add("first LINE", marker).is_err());
        assert!(settings.skate_places.add("bad\nname", marker).is_err());
        settings.skate_places.rename("Under the bridge").unwrap();
        let reloaded: crate::Settings = serde_json::from_str(&serde_json::to_string(&settings).unwrap()).unwrap();
        assert_eq!(reloaded.skate_places, settings.skate_places);
        assert_eq!(reloaded.skate_places.selected().unwrap().marker, marker);
        let old: crate::Settings = serde_json::from_str("{}").unwrap();
        assert!(old.skate_places.saved.is_empty());
    }
}
