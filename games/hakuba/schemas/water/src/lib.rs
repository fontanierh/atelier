//! Shared validation of source-authored bounded-water index metadata (also used by the exporter).
use serde_json::Value;
use std::collections::HashSet;

fn number(v: &Value) -> Option<f32> {
    let v = v.as_f64()? as f32;
    v.is_finite().then_some(v)
}

fn scalar(v: &Value, key: &str) -> Result<f32, String> {
    v.get(key).and_then(number).ok_or_else(|| format!("water needs finite {key}"))
}

fn vector(v: &Value, key: &str, length: usize) -> Result<Vec<f32>, String> {
    let values = v.get(key).and_then(Value::as_array).ok_or_else(|| format!("water needs {key}"))?;
    if values.len() != length {
        return Err(format!("water {key} needs {length} values"));
    }
    values.iter().map(|v| number(v).ok_or_else(|| format!("water {key} must be finite"))).collect()
}

/// Checks all fields consumed by recovery and the two-harmonic material before an index can be written or read.
pub fn validate(waters: &[Value]) -> Result<(), String> {
    let mut models = HashSet::new();
    for water in waters {
        vector(water, "center_m", 2)?;
        if vector(water, "radii_m", 2)?.iter().any(|r| *r <= 0.0) {
            return Err("water radii must be positive".into());
        }
        scalar(water, "water_height_m")?;
        if scalar(water, "recovery_depth_m")? < 0.0 {
            return Err("water recovery depth must be non-negative".into());
        }
        vector(water, "safe_shore_m", 3)?;
        let harmonics = water.get("shore_harmonics").and_then(Value::as_array).ok_or("water needs shore harmonics")?;
        if harmonics.len() > 2 {
            return Err("water material supports two shore harmonics".into());
        }
        let mut amplitude = 0.0;
        for h in harmonics {
            let h = h.as_array().filter(|h| h.len() == 3).ok_or("invalid shore harmonic")?;
            let f = number(&h[0]).filter(|f| *f > 0.0 && *f <= 1024.0).ok_or("invalid shore frequency")?;
            let a = number(&h[1]).ok_or("invalid shore amplitude")?;
            if !matches!(h[2].as_str(), Some("sin" | "cos")) || !f.is_finite() {
                return Err("invalid shore harmonic".into());
            }
            amplitude += a.abs();
        }
        if amplitude >= 1.0 {
            return Err("water shoreline may not collapse".into());
        }
        let entries = water
            .get("water_models")
            .and_then(Value::as_array)
            .filter(|v| !v.is_empty())
            .ok_or("water needs model associations")?;
        for entry in entries {
            let name = entry.get("model").and_then(Value::as_str).ok_or("invalid water model")?;
            if !name.starts_with("props/") || name.ends_with('/') || name.contains("..") || !models.insert(name) {
                return Err(format!("invalid or duplicate water model {name}"));
            }
        }
        let m = water.get("material").filter(|v| v.is_object()).ok_or("water needs a material")?;
        if m.get("opaque").and_then(Value::as_bool) != Some(true) {
            return Err("water material must be opaque".into());
        }
        let waves = m
            .get("waves")
            .and_then(Value::as_u64)
            .filter(|v| (1..=16).contains(v))
            .ok_or("invalid water wave count")?;
        for key in [
            "direction_start_radians",
            "direction_step_radians",
            "wavenumber_start",
            "wavenumber_ratio",
            "amplitude_start",
            "amplitude_ratio",
            "footprint_fade",
            "warp_frequency",
            "warp_speed",
            "warp_amplitude",
            "phase_step",
            "gravity_factor",
            "shore_calm_start",
            "shore_calm_end",
            "shore_calm_reduction",
            "metallic",
            "specular",
            "crest_scale",
            "crest_strength",
            "drift_strength",
            "chop_scale",
            "fetch_mix",
            "chop_mix",
        ] {
            scalar(m, key)?;
        }
        for key in ["deep_colour_min", "deep_colour_max", "shallows_colour", "glint_colour", "drift_colour"] {
            if vector(m, key, 3)?.iter().any(|v| *v < 0.0) {
                return Err(format!("negative water colour {key}"));
            }
        }
        for key in ["drift_x", "drift_y", "fetch"] {
            vector(m, key, 3)?;
        }
        for key in ["crest_direction", "glint_range", "roughness_range"] {
            vector(m, key, 2)?;
        }
        for key in ["wavenumber_start", "wavenumber_ratio", "amplitude_ratio", "crest_scale"] {
            if scalar(m, key)? <= 0.0 {
                return Err(format!("water {key} must be positive"));
            }
        }
        for key in ["amplitude_start", "footprint_fade", "gravity_factor", "chop_scale"] {
            if scalar(m, key)? < 0.0 {
                return Err(format!("water {key} must be non-negative"));
            }
        }
        for key in ["shore_calm_reduction", "metallic", "specular"] {
            if !(0.0..=1.0).contains(&scalar(m, key)?) {
                return Err(format!("water {key} must be in [0, 1]"));
            }
        }
        let calm_start = scalar(m, "shore_calm_start")?;
        let calm_end = scalar(m, "shore_calm_end")?;
        if calm_start < 0.0 || calm_end > 1.0 || calm_start >= calm_end {
            return Err("invalid water shore calm range".into());
        }
        let glint = vector(m, "glint_range", 2)?;
        if glint[0] >= glint[1] {
            return Err("invalid water glint range".into());
        }
        if vector(m, "roughness_range", 2)?.iter().any(|v| !(0.0..=1.0).contains(v)) {
            return Err("invalid water roughness".into());
        }
        let mut k = scalar(m, "wavenumber_start")?;
        let mut amplitude = scalar(m, "amplitude_start")?;
        let k_ratio = scalar(m, "wavenumber_ratio")?;
        let amplitude_ratio = scalar(m, "amplitude_ratio")?;
        let gravity = scalar(m, "gravity_factor")?;
        let warp_frequency = scalar(m, "warp_frequency")?;
        let footprint_fade = scalar(m, "footprint_fade")?;
        for i in 0..waves {
            if !k.is_finite()
                || !amplitude.is_finite()
                || !(gravity * k).is_finite()
                || !(k * warp_frequency).is_finite()
                || !(k * k * footprint_fade).is_finite()
                || !(amplitude * waves as f32).is_finite()
            {
                return Err("water wave spectrum exceeds finite shader precision".into());
            }
            if i + 1 < waves {
                k *= k_ratio;
                amplitude *= amplitude_ratio;
            }
        }
    }
    // A recovery target must be safe from every body, including overlapping bodies.
    for owner in waters {
        let safe = vector(owner, "safe_shore_m", 3)?;
        for body in waters {
            let centre = vector(body, "center_m", 2)?;
            let radii = vector(body, "radii_m", 2)?;
            let x = (safe[0] - centre[0]) / radii[0];
            let y = (safe[1] - centre[1]) / radii[1];
            let angle = y.atan2(x);
            let mut shore = 1.0;
            for harmonic in body["shore_harmonics"].as_array().unwrap() {
                let h = harmonic.as_array().unwrap();
                let phase = number(&h[0]).unwrap() * angle;
                let value = if h[2].as_str() == Some("sin") { phase.sin() } else { phase.cos() };
                shore += number(&h[1]).unwrap() * value;
            }
            if x * x + y * y < shore * shore
                && safe[2] < scalar(body, "water_height_m")? - scalar(body, "recovery_depth_m")?
            {
                return Err("water recovery target lies in deep water".into());
            }
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn lake() -> Value {
        serde_json::from_str(r#"{"center_m":[0,0],"radii_m":[10,5],"water_height_m":1,"shore_harmonics":[[3,0.05,"sin"],[5,0.03,"cos"]],"recovery_depth_m":0.45,"safe_shore_m":[12,0,1],"water_models":[{"model":"props/test-water"}],"material":{
            "opaque":true,"waves":7,"direction_start_radians":0.6,"direction_step_radians":1.9,"wavenumber_start":1.0,"wavenumber_ratio":1.5,"amplitude_start":0.1,"amplitude_ratio":0.8,"footprint_fade":0.5,"warp_frequency":0.4,"warp_speed":0.3,"warp_amplitude":2.0,"phase_step":2.0,"gravity_factor":3.0,"shore_calm_start":0.7,"shore_calm_end":1.0,"shore_calm_reduction":0.5,
            "deep_colour_min":[0.01,0.04,0.05],"deep_colour_max":[0.02,0.05,0.06],"shallows_colour":[0.03,0.1,0.1],"glint_colour":[0.01,0.02,0.02],"metallic":0.1,"specular":0.5,"roughness_range":[0.2,0.4],"drift_x":[0.2,0.1,0.1],"drift_y":[0.1,-0.2,-0.1],"crest_direction":[0.3,-0.9],"crest_scale":0.1,"crest_strength":0.1,"glint_range":[0.7,1.1],"drift_strength":0.01,"drift_colour":[0.1,0.3,0.2],"fetch":[0.2,-0.1,0.1],"chop_scale":3,"fetch_mix":0.5,"chop_mix":0.6
        }}"#).unwrap()
    }

    #[test]
    fn malformed_water_cannot_reach_recovery_or_shader() {
        let lake = lake();
        assert!(validate(std::slice::from_ref(&lake)).is_ok());
        assert!(validate(&[lake.clone(), lake.clone()]).is_err());
        for (field, value) in [("radii_m", json!([0, 5])), ("shore_harmonics", json!([[3, 0.05, "bad"]]))] {
            let mut bad = lake.clone();
            bad[field] = value;
            assert!(validate(&[bad]).is_err());
        }
        let mut bad = lake.clone();
        bad["material"]["crest_scale"] = json!(0);
        assert!(validate(&[bad]).is_err());
        let mut bad = lake.clone();
        bad["material"]["wavenumber_ratio"] = json!(1e30);
        assert!(validate(&[bad]).is_err());
        let mut bad = lake.clone();
        bad["safe_shore_m"] = json!([0, 0, 0]);
        assert!(validate(&[bad]).is_err());
        let mut other = lake.clone();
        other["water_models"] = json!([{ "model": "props/other-water" }]);
        other["center_m"] = json!([100, 0]);
        other["safe_shore_m"] = json!([0, 0, 0]);
        assert!(validate(&[lake, other]).is_err());
    }
}
