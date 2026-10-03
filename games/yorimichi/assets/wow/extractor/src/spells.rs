use anyhow::{Context, Result};
use benilla_formats::{Chain, SpellDisplay};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};

/// Keep every family rank; level eligibility is metadata, not a declaration of learned spells.
pub fn catalogue(
    chain: &mut Chain,
    family: u32,
    class_id: u32,
    level: u32,
) -> Result<(Value, Vec<String>)> {
    let spells = benilla_formats::load_spell_catalog(chain)
        .context("spell catalogue requires Spell.dbc and SpellIcon.dbc")?;
    let ranges = benilla_formats::load_spell_ranges(chain)?;
    let times = benilla_formats::load_spell_cast_times(chain)?;
    let durations = benilla_formats::load_spell_durations(chain)?;
    let visuals = benilla_formats::load_spell_visual_catalog(chain)?;
    let mut selected = BTreeMap::new();
    let mut pending: Vec<_> = spells
        .iter()
        .filter(|(_, s)| s.spell_family == family)
        .map(|(id, _)| id)
        .collect();
    let mut dependencies = BTreeSet::new();
    while let Some(id) = pending.pop() {
        if selected.contains_key(&id) {
            continue;
        }
        let Some(s) = spells.get(id) else { continue };
        pending.extend(s.effect_trigger_spell.iter().copied().filter(|&id| id != 0));
        if let Some(icon) = &s.icon {
            dependencies.insert(texture_path(icon));
        }
        let mut value = record(s);
        value["level_eligible"] = json!(s.spell_level <= level);
        value["family_member"] = json!(s.spell_family == family);
        value["acquisition"] =
            json!("unresolved: trainer/talent/quest/racial/item rules are not inferred from level");
        value["range"] = ranges
            .get(s.range_index)
            .map(|r| json!({"min_yards":r.min,"max_yards":r.max,"flags":r.flags}))
            .unwrap_or(Value::Null);
        value["cast_time"] = times
            .get(s.casting_time_index)
            .map(|t| {
                json!({"base_ms":t.base_ms,"per_level_ms":t.per_level_ms,"minimum_ms":t.minimum_ms,
            "at_profile_level_ms_before_modifiers":t.resolved_ms(level,s.base_level)})
            })
            .unwrap_or(Value::Null);
        value["duration"] = durations
            .get(s.duration_index)
            .map(|d| json!({"base_ms":d.base_ms,"per_level_ms":d.per_level_ms,"max_ms":d.max_ms}))
            .unwrap_or(Value::Null);
        if let Some(stages) = visuals.stages(s.visual) {
            let ids = [
                stages.precast,
                stages.cast,
                stages.impact,
                stages.state,
                stages.channel,
                stages.area_kit,
            ];
            let kits: Vec<_> = ids.iter().filter_map(|&id| {
                if id == 0 {return None;}
                let kit = visuals.kit(id)?;
                let effects: Vec<_> = kit.effects().map(|(attachment,effect)| {
                    if let Some(path) = visuals.effect_path(effect) { dependencies.insert(path.into()); }
                    json!({"attachment":attachment,"effect_id":effect,"model":visuals.effect_path(effect)})
                }).collect();
                Some(json!({"kit_id":id,"animation_id":kit.anim_id,"sound_id":kit.sound,"effects":effects}))
            }).collect();
            if let Some(path) = visuals.effect_path(stages.missile_model) {
                dependencies.insert(path.into());
            }
            value["visual_stages"] = json!({"precast":stages.precast,"cast":stages.cast,"impact":stages.impact,
                "state":stages.state,"channel":stages.channel,"area_kit":stages.area_kit,"kits":kits,
                "missile_effect_id":stages.missile_model,"missile_model":visuals.effect_path(stages.missile_model),"missile_sound":stages.missile_sound});
        }
        selected.insert(id, value);
    }
    Ok((
        json!({"schema_version":1,"kind":"client_spell_catalogue","class_id":class_id,"spell_family":family,"profile_level":level,
        "spells":selected.values().collect::<Vec<_>>(),"source":"selected Spell.dbc family plus triggered-spell closure",
        "playable":false,"limits":["Not a learned spellbook","No talents, equipment or racial bonuses selected",
            "Client data describes effects; native effect execution and server content remain separate"]}),
        dependencies.into_iter().collect(),
    ))
}

fn texture_path(path: &str) -> String {
    if path.to_ascii_lowercase().ends_with(".blp") {
        path.into()
    } else {
        format!("{path}.blp")
    }
}

fn record(s: &SpellDisplay) -> Value {
    json!({"id":s.id,"name":s.name,"rank":s.rank,"description":s.description,"aura_description":s.aura_description,
        "family":s.spell_family,"family_flags":s.spell_family_flags,"school":s.school,"mechanic":s.mechanic,
        "base_level":s.base_level,"spell_level":s.spell_level,"max_level":s.max_level,"passive":s.passive,
        "icon":s.icon,"visual_id":s.visual,"projectile_speed_yards_per_second":s.speed,
        "attributes":[s.attributes,s.attributes_ex,s.attributes_ex2,s.attributes_ex3,s.attributes_ex4],
        "target_flags":s.targets,"creature_target_mask":s.target_creature_type,
        "cast_time_index":s.casting_time_index,"range_index":s.range_index,"duration_index":s.duration_index,
        "resource":{"type":s.power_type,"cost":s.mana_cost,"cost_pct":s.mana_cost_pct,"cost_per_level":s.mana_cost_per_level,"per_second":s.mana_per_second},
        "cooldown":{"recovery_ms":s.recovery_ms,"category":s.category,"category_recovery_ms":s.category_recovery_ms,
            "global_category":s.start_recovery_category,"global_recovery_ms":s.start_recovery_ms},
        "interrupt":{"cast":s.interrupt_flags,"aura":s.aura_interrupt_flags,"channel":s.channel_interrupt_flags},
        "proc":{"flags":s.proc_flags,"chance":s.proc_chance,"charges":s.proc_charges,"stack_amount":s.stack_amount},
        "reagents":s.reagents,"totems":s.totems,
        "effects":(0..3).map(|i| json!({"type":s.effects[i],"base_points":s.effect_base_points[i],"die_sides":s.effect_die_sides[i],
            "base_dice":s.effect_base_dice[i],"points_per_level":s.effect_real_points_per_level[i],"dice_per_level":s.effect_dice_per_level[i],
            "amplitude_ms":s.effect_amplitude[i],"aura":s.effect_apply_aura[i],"mechanic":s.effect_mechanic[i],
            "radius_index":s.effect_radius_index[i],"chain_targets":s.effect_chain_targets[i],"trigger_spell":s.effect_trigger_spell[i],
            "item_type":s.effect_item_type[i],"misc_value":s.effect_misc_value[i],"target_a":s.effect_implicit_target_a[i],
            "target_b":s.effect_implicit_target_b[i],"damage_multiplier":s.damage_multiplier[i]})).collect::<Vec<_>>()})
}
