//! Immutable stock shot definitions. Field order/units follow TU382CA4660.
use crate::core::camera::{ShotDatabase, ShotDefinition};
use std::collections::BTreeMap;

#[derive(Clone)]
pub(crate) struct StockShots(BTreeMap<String, ShotDefinition>);

impl StockShots {
    pub(crate) fn from_definitions(definitions: Vec<ShotDefinition>) -> Result<Self, String> {
        let mut shots = BTreeMap::new();
        for shot in definitions {
            let key = shot.name.clone();
            if shots.insert(key.clone(), shot).is_some() {
                return Err(format!("Duplicate camera shot {key}"));
            }
        }
        for shot in shots.values() {
            for name in shot.children.iter().flatten() {
                if !shots.contains_key(name) {
                    return Err(format!("Camera shot {} references missing shot {name}", shot.name));
                }
            }
        }
        Ok(Self(shots))
    }
}

impl ShotDatabase for StockShots {
    fn load(&self, name: &str) -> Result<ShotDefinition, String> {
        self.0.get(&name.to_ascii_lowercase()).cloned().ok_or_else(|| format!("Missing stock camera shot {name}"))
    }
}
