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
}

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
    use super::{Actor, Route};

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
            route: Some(Route { destination: [1.0; 3], half_cycle_s: 20.0, delay_s: 5.0, travel_s: 7.0 }),
        };
        assert!(actor.validate().is_ok());
        actor.route.as_mut().unwrap().travel_s = 16.0;
        assert!(actor.validate().is_err());
        actor.route = None;
        actor.model = "characters/nox/other.glb";
        assert!(actor.validate().is_err());
    }
}
