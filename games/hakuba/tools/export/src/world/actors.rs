//! Moving and posing characters declared by regions and carried by the world index.

use anyhow::{Result, bail};
use serde::Serialize;

/// An actor's model, pose and optional path in map coordinates (east, north, up; metres).
#[derive(Serialize)]
pub struct Actor {
    pub model: &'static str,
    pub position: [f64; 3],
    pub yaw_deg: f64,
    pub scale: f64,
    pub clip: &'static str,
    pub rate: f64,
    pub phase_s: f64,
    pub colour: [f64; 3],
    /// Red and blue ratios identifying cloth, reference green and minimum shade.
    pub cloth: [f64; 4],
    pub route: Option<Route>,
    /// Optional stationary, periodic look around the home bearing.
    pub scan: Option<Scan>,
    /// Optional periodic visual action between idle loops.
    pub practice: Option<Practice>,
    /// Painted rigid models and their component-frame bone attachments.
    pub attachments: Vec<Attachment>,
}

/// Source declarations keep their original precision and static names.
pub type Attachment = hakuba_actor_schema::Attachment<f64, &'static str>;
pub type Practice = hakuba_actor_schema::Practice<f64, &'static str>;
pub type Scan = hakuba_actor_schema::Scan<f64>;

/// An out-and-back walk, with the same rest and travel timing in each direction.
#[derive(Serialize)]
pub struct Route {
    pub destination: [f64; 3],
    pub half_cycle_s: f64,
    pub delay_s: f64,
    pub travel_s: f64,
}

impl Actor {
    /// Reject malformed declarations before they reach the world index.
    pub fn validate(&self) -> Result<()> {
        let Some((folder, file)) = self.model.rsplit_once('/') else { bail!("actor model needs an asset folder") };
        let Some(name) = folder.strip_prefix("characters/") else { bail!("actor model must be a character") };
        if name.is_empty() || name.contains('/') || file != format!("{name}.glb") {
            bail!("actor model must name its character export");
        }
        crate::uri_of_asset(folder, "glb")?;
        if self.position.iter().chain(self.colour.iter()).chain(self.cloth.iter()).any(|v| !v.is_finite())
            || !self.yaw_deg.is_finite()
            || !self.scale.is_finite()
            || self.scale <= 0.0
            || !self.rate.is_finite()
            || self.rate <= 0.0
            || !self.phase_s.is_finite()
            || self.phase_s < 0.0
            || self.clip.is_empty()
            || self.cloth[0] <= 0.0
            || self.cloth[1] <= 0.0
            || self.cloth[2] <= 0.0
            || self.cloth[3] < 0.0
        {
            bail!("invalid actor pose, clip, colour or scale");
        }
        for attachment in &self.attachments {
            let Some((folder, file)) = attachment.model.rsplit_once('/') else {
                bail!("attachment model needs an asset folder")
            };
            let Some(name) = folder.strip_prefix("props/") else { bail!("attachment must be a prop") };
            crate::uri_of_asset(folder, "glb")?;
            let magnitude: f64 = attachment.rotation.iter().map(|v| v * v).sum();
            if name.is_empty()
                || name.contains('/')
                || file != format!("{name}.glb")
                || attachment.position_bone.is_empty()
                || attachment.rotation_bone.is_empty()
                || attachment.offset.iter().chain(attachment.rotation.iter()).any(|v| !v.is_finite())
                || (magnitude - 1.0).abs() >= 1e-4
            {
                bail!("invalid attachment model or pose");
            }
        }
        if let Some(practice) = &self.practice
            && (self.route.is_some()
                || practice.clip.is_empty()
                || !practice.rate.is_finite()
                || practice.rate <= 0.0
                || !practice.duration_s.is_finite()
                || practice.duration_s <= 0.0
                || practice.interval_s.iter().any(|v| !v.is_finite())
                || practice.interval_s[0] <= practice.duration_s
                || practice.interval_s[1] < practice.interval_s[0]
                || !practice.delay_s.is_finite()
                || practice.delay_s < 0.0)
        {
            bail!("invalid visual practice");
        }
        if let Some(scan) = &self.scan
            && (self.route.is_some()
                || !scan.amplitude_deg.is_finite()
                || scan.amplitude_deg < 0.0
                || !scan.frequency.is_finite()
                || scan.frequency <= 0.0
                || !scan.max_speed_deg.is_finite()
                || scan.max_speed_deg <= 0.0)
        {
            bail!("invalid stationary scan");
        }
        if let Some(route) = &self.route
            && (route.destination.iter().any(|v| !v.is_finite())
                || !route.half_cycle_s.is_finite()
                || !route.delay_s.is_finite()
                || !route.travel_s.is_finite()
                || route.half_cycle_s <= 0.0
                || route.delay_s < 0.0
                || route.travel_s <= 0.0
                || route.delay_s + route.travel_s > route.half_cycle_s)
        {
            bail!("invalid actor route timing or destination");
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::{Actor, Route, Scan};

    #[test]
    fn actor_rejects_invalid_route_and_wrong_model_path() {
        let mut actor = Actor {
            model: "characters/nox/nox.glb",
            position: [0.0; 3],
            yaw_deg: 0.0,
            scale: 1.0,
            clip: "idle",
            rate: 1.0,
            phase_s: 0.0,
            colour: [1.0; 3],
            cloth: [1.01, 1.25, 0.3, 0.4],
            attachments: Vec::new(),
            scan: None,
            practice: None,
            route: Some(Route { destination: [1.0; 3], half_cycle_s: 20.0, delay_s: 5.0, travel_s: 7.0 }),
        };
        assert!(actor.validate().is_ok());
        actor.route.as_mut().unwrap().travel_s = 16.0;
        assert!(actor.validate().is_err());
        actor.route = None;
        actor.scan = Some(Scan { amplitude_deg: 28.0, frequency: 0.85, max_speed_deg: 90.0 });
        assert!(actor.validate().is_ok());
        actor.scan.as_mut().unwrap().frequency = 0.0;
        assert!(actor.validate().is_err());
        actor.scan = None;
        actor.model = "characters/nox/other.glb";
        assert!(actor.validate().is_err());
    }
}
