//! Host preference selects the native physics_mode collection, never a multiplier.
use serde::{Deserialize, Serialize};

pub(crate) const NATIVE_MODES: [&str; 5] = ["easy", "normal", "hardcore", "motorized", "test"];

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
#[repr(u32)]
pub(crate) enum Difficulty {
    #[default]
    Easy = 0,
    Normal = 1,
    Hardcore = 2,
}
impl Difficulty {
    pub const ALL: [Self; 3] = [Self::Easy, Self::Normal, Self::Hardcore];
    pub fn key(self) -> &'static str {
        NATIVE_MODES[self as usize]
    }
    pub fn label(self) -> &'static str {
        match self {
            Self::Easy => "Easy",
            Self::Normal => "Normal",
            Self::Hardcore => "Hardcore",
        }
    }
    pub fn parse(value: &str) -> Result<Self, String> {
        Self::ALL
            .into_iter()
            .find(|d| d.key().eq_ignore_ascii_case(value))
            .ok_or_else(|| format!("Unknown difficulty {value:?}; expected easy, normal or hardcore"))
    }
}
#[derive(Serialize, Deserialize)]
struct Saved {
    difficulty: Difficulty,
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn retail_indices_and_saved_names_agree() {
        for (index, d) in Difficulty::ALL.into_iter().enumerate() {
            assert_eq!(d as usize, index);
            assert_eq!(Difficulty::parse(d.label()).unwrap(), d);
            let bytes = serde_json::to_vec(&Saved { difficulty: d }).unwrap();
            assert_eq!(serde_json::from_slice::<Saved>(&bytes).unwrap().difficulty, d);
        }
        assert!(Difficulty::parse("motorized").is_err());
        assert!(serde_json::from_str::<Saved>(r#"{"difficulty":"made-up"}"#).is_err());
    }
}
