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
            let original = std::mem::take(values);
            for (key, mut value) in original {
                let mut key = Value::String(key);
                replace(&mut key, piece, export, previous)?;
                replace(&mut value, piece, export, previous)?;
                if values
                    .insert(key.as_str().unwrap().to_string(), value)
                    .is_some()
                {
                    return Err("native follower key substitution aliases an authored field".into());
                }
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

#[cfg(test)]
mod substitution_tests {
    use super::*;
    #[test]
    fn native_cook_record_keys_bind_the_expanded_piece_and_refuse_aliases() {
        let mut value =
            serde_json::json!({"record_outputs":{"/Game/Audio/$piece":"records/$piece.cb"}});
        replace(&mut value, "Step", "raw.Step", "finish.Step").unwrap();
        assert_eq!(
            value["record_outputs"]["/Game/Audio/Step"],
            "records/Step.cb"
        );
        let mut aliases = serde_json::json!({"$piece":1,"Step":2});
        assert!(replace(&mut aliases, "Step", "raw.Step", "finish.Step").is_err());
    }
}
