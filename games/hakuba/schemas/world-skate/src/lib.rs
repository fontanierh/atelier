//! Ordered grind lines, contact materials and bounded skating zones in Y-up world metres.
use serde::{Deserialize, Serialize};

/// Packed contact profile and sound: `(profile << 7) | sound`. Imported surfaces enable small-edge riding.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[repr(u16)]
#[serde(rename_all = "snake_case")]
pub enum Surface {
    #[default]
    Concrete = 129,
    Asphalt = 260,
    Wood = 130,
    Stone = 261,
    Metal = 131,
    Dirt = 390,
    Grass = 647,
    Sand = 648,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MaterialSurface {
    /// Authored material name, not an entity or loading-order identifier.
    pub material: String,
    pub surface: Surface,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Rail {
    pub id: String,
    pub points: Vec<[f32; 3]>,
    #[serde(default)]
    pub closed: bool,
    pub kind: String,
    #[serde(default)]
    pub surface: Surface,
}

/// An oriented box. Yaw turns local +X toward -Z about +Y (radians).
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Zone {
    pub id: String,
    pub center: [f32; 3],
    pub half_extent: [f32; 3],
    pub yaw: f32,
    /// Assistance cap for assist zones, additional pump/slide scale for boost zones.
    pub value: f32,
}

#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Metadata {
    pub rails: Vec<Rail>,
    pub assist_zones: Vec<Zone>,
    pub boost_zones: Vec<Zone>,
    pub materials: Vec<MaterialSurface>,
}

impl Metadata {
    pub fn validate(&self) -> Result<(), String> {
        let mut ids = std::collections::BTreeSet::new();
        for rail in &self.rails {
            if rail.id.is_empty()
                || !ids.insert(rail.id.as_str())
                || rail.points.len() < 2
                || rail.kind.is_empty()
                || rail.points.iter().flatten().any(|p| !p.is_finite())
                || rail.points.windows(2).any(|p| p[0] == p[1])
            {
                return Err(format!("invalid or duplicate grind line: {}", rail.id));
            }
        }
        for (zones, boost) in [(&self.assist_zones, false), (&self.boost_zones, true)] {
            let mut ids = std::collections::BTreeSet::new();
            for zone in zones {
                if zone.id.is_empty()
                    || !ids.insert(zone.id.as_str())
                    || zone.center.iter().any(|v| !v.is_finite())
                    || zone.half_extent.iter().any(|v| !v.is_finite() || *v <= 0.0)
                    || !zone.yaw.is_finite()
                    || !zone.value.is_finite()
                    || zone.value < 0.0
                    || (!boost && zone.value > 1.0)
                {
                    return Err(format!("invalid or duplicate skating zone: {}", zone.id));
                }
            }
        }
        let mut materials = std::collections::BTreeSet::new();
        for rule in &self.materials {
            if rule.material.is_empty() || !materials.insert(rule.material.as_str()) {
                return Err(format!("invalid or duplicate material: {}", rule.material));
            }
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn packed_surfaces_keep_contact_profile_and_sound_identity() {
        assert_eq!(
            [
                Surface::Concrete as u16,
                Surface::Wood as u16,
                Surface::Metal as u16,
                Surface::Asphalt as u16,
                Surface::Stone as u16,
                Surface::Dirt as u16,
                Surface::Grass as u16,
                Surface::Sand as u16
            ],
            [129, 130, 131, 260, 261, 390, 647, 648]
        );
    }
    #[test]
    fn rejects_invalid_zones_and_duplicate_rails() {
        let rail = Rail {
            id: "lip".into(),
            points: vec![[0.; 3], [1., 0., 0.]],
            closed: false,
            kind: "coping".into(),
            surface: Surface::Metal,
        };
        let mut metadata = Metadata { rails: vec![rail.clone()], ..Default::default() };
        assert!(metadata.validate().is_ok());
        metadata.rails.push(rail);
        assert!(metadata.validate().is_err());
        metadata.rails.clear();
        metadata.assist_zones.push(Zone {
            id: "cap".into(),
            center: [0.; 3],
            half_extent: [1.; 3],
            yaw: 0.,
            value: 1.1,
        });
        assert!(metadata.validate().is_err());
        metadata.assist_zones[0].value = 0.;
        assert!(metadata.validate().is_ok());
    }
}
