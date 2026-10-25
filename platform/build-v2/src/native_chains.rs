//! Authored dependent units over a validated export template expansion.
//! This module performs no I/O, scheduling, keying or result certification.
use crate::schema::Unit;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FollowerTemplate {
    /// $piece, $export and $previous are the only substituted tokens.
    pub unit: Unit,
    pub staged_inputs: BTreeMap<String, String>,
}

pub struct Followers {
    pub units: Vec<Unit>,
    pub staged_inputs: BTreeMap<String, BTreeMap<String, String>>,
}

fn replace(value: &mut Value, piece: &str, export: &str, previous: &str) -> Result<(), String> {
    match value {
        Value::String(text) => {
            *text = text
                .replace("$piece", piece)
                .replace("$export", export)
                .replace("$previous", previous);
            if text.contains('$') {
                return Err("unknown native follower substitution".into());
            }
        }
        Value::Array(values) => {
            for value in values {
                replace(value, piece, export, previous)?;
            }
        }
        Value::Object(values) => {
            for value in values.values_mut() {
                replace(value, piece, export, previous)?;
            }
        }
        _ => {}
    }
    Ok(())
}

/// Instantiate only after the existing group validator established this member.
/// The caller must run the normal graph/ownership validation before any unit keys.
pub fn instantiate(
    templates: &[FollowerTemplate],
    piece: &str,
    export: &str,
) -> Result<Followers, String> {
    crate::groups::name(piece)?;
    let mut previous = export.to_string();
    let mut units = Vec::new();
    let mut staged_inputs = BTreeMap::new();
    for template in templates {
        let mut value = serde_json::to_value(&template.unit).map_err(|e| e.to_string())?;
        replace(&mut value, piece, export, &previous)?;
        let unit: Unit = serde_json::from_value(value).map_err(|e| e.to_string())?;
        if unit.id == export || units.iter().any(|old: &Unit| old.id == unit.id) {
            return Err("native follower overwrites an existing child".into());
        }
        let mut stage = serde_json::to_value(&template.staged_inputs).map_err(|e| e.to_string())?;
        replace(&mut stage, piece, export, &previous)?;
        staged_inputs.insert(
            unit.id.clone(),
            serde_json::from_value(stage).map_err(|e| e.to_string())?,
        );
        previous = unit.id.clone();
        units.push(unit);
    }
    Ok(Followers {
        units,
        staged_inputs,
    })
}
