use anyhow::{bail, Context, Result};
use serde_json::{json, Value};
use std::io::Cursor;

pub fn decode(bytes: &[u8]) -> Result<(Value, Vec<String>)> {
    let version = u32_at(bytes, 4).context("M2 version missing")?;
    if !matches!(version, 256 | 257) {
        bail!("M2 version {version} is outside the targeted vanilla formats");
    }
    let parsed = benilla_m2::parse_m2(&mut Cursor::new(bytes))?;
    let model = parsed.model();
    let mut dependencies = Vec::new();
    let textures: Vec<_> = model
        .textures
        .iter()
        .map(|t| {
            let name = t.filename.string.to_string_lossy().into_owned();
            if !name.is_empty() {
                dependencies.push(name.clone());
            }
            let kind = match t.texture_type {
                benilla_m2::M2TextureType::Hardcoded => 0,
                benilla_m2::M2TextureType::Monster1 => 11,
                benilla_m2::M2TextureType::Monster2 => 12,
                benilla_m2::M2TextureType::Monster3 => 13,
                benilla_m2::M2TextureType::Other(k) => k,
            };
            json!({"path":name,"replaceable_type":kind,"wrap_u":t.wrap_x,"wrap_v":t.wrap_y})
        })
        .collect();
    let bones: Vec<_> = model.bones.iter().enumerate().map(|(i,b)| {
        // Keep raw channel interpolation flags as the format facade's BoneKeys contain values
        // but not interpolation modes. Bounds were validated by parse_m2 above.
        let base = u32_at(bytes, 0x38).unwrap_or(0) as usize + i * 108;
        json!({"index":i,"parent":b.parent,"key_bone":b.key_bone,
            "pivot":[b.pivot.x,b.pivot.y,b.pivot.z],"flags":b.flags.bits(),
            "interpolation":{"translation":u16_at(bytes,base+12),"rotation":u16_at(bytes,base+40),"scale":u16_at(bytes,base+68)}})
    }).collect();
    let animations: Vec<_> = benilla_formats::parse_m2_animations(bytes).iter().map(|a| {
        let tracks: Vec<_> = a.bones.iter().map(|b| json!({"bone":b.bone,"translation":b.translation,"rotation":b.rotation,"scale":b.scale})).collect();
        let events: Vec<_> = a.events.iter().map(|e| json!({"time_seconds":e.time,"tag":String::from_utf8_lossy(&e.ident),"data":e.data,"bone":e.bone,"position":e.position})).collect();
        json!({"animation_id":a.anim_id,"source_sequence":a.seq_index,"duration_seconds":a.duration,
            "looping":a.looping,"source_band_ms":[a.start_ms,a.end_ms],"move_speed_yards_per_second":a.move_speed,
            "blend_seconds":a.blend_time,"frequency":a.frequency,"replay":[a.min_replay,a.max_replay],
            "bounds_min":a.bounds_min,"bounds_max":a.bounds_max,"tracks":tracks,"events":events})
    }).collect();
    let globals: Vec<_> = benilla_formats::parse_m2_global_sequence_bones(bytes).iter().map(|g| {
        json!({"bone":g.bone,
            "translation":g.translation.as_ref().map(|c| json!({"period_ms":c.period_ms,"keys_ms":c.keys})),
            "rotation":g.rotation.as_ref().map(|c| json!({"period_ms":c.period_ms,"keys_ms":c.keys})),
            "scale":g.scale.as_ref().map(|c| json!({"period_ms":c.period_ms,"keys_ms":c.keys}))})
    }).collect();
    let mut skins = Vec::new();
    let skin_count = u32_at(bytes, 0x4c).context("M2 has no skin count")? as usize;
    for index in 0..skin_count {
        let skin = model.parse_embedded_skin(bytes, index)?;
        let triangles = skin
            .triangles()
            .iter()
            .map(|&t| {
                skin.indices()
                    .get(t as usize)
                    .copied()
                    .context("skin triangle outside index array")
            })
            .collect::<Result<Vec<_>>>()?;
        if triangles
            .iter()
            .any(|&t| t as usize >= model.vertices.len())
        {
            bail!("triangle outside vertex array");
        }
        let sections: Vec<_> = skin.submeshes().iter().map(|s| json!({"geoset_id":s.id,"index_start":s.triangle_start,"index_count":s.triangle_count})).collect();
        let batches: Vec<_> = skin.batches().iter().map(|b| json!({
            "section":b.skin_section_index,"material":b.material_index,"texture_combo":b.texture_combo_index,
            "texture_count":b.texture_count,"color_index":b.color_index,"weight_combo":b.weight_combo_index,
            "texture_coord_combo":b.texture_coord_combo_index,"texture_transform_combo":b.texture_transform_combo_index,
            "flags":b.flags,"shader_id":b.shader_id})).collect();
        skins.push(
            json!({"index":index,"triangles":triangles,"sections":sections,"batches":batches}),
        );
    }
    let attachments: Vec<_> = model
        .attachments
        .iter()
        .map(|a| json!({"id":a.id,"bone":a.bone,"position":a.position}))
        .collect();
    let materials: Vec<_> = model
        .materials
        .iter()
        .map(|m| json!({"flags":m.flags.bits(),"blend_mode":m.blend_mode.bits()}))
        .collect();
    let fallback: Vec<_> = model
        .playable_animation_lookup
        .iter()
        .map(|a| json!({"resolved_id":a.resolved_id,"direction_flags":a.dir_flags}))
        .collect();
    let vertices: Vec<_> = model.vertices.iter().map(|v| json!({
        "position":[v.position.x,v.position.y,v.position.z],"normal":[v.normal.x,v.normal.y,v.normal.z],
        "uv":[v.tex_coords.x,v.tex_coords.y],"joints":v.bone_indices,"weights_u8":v.bone_weights})).collect();
    let summary = benilla_formats::parse_m2_animation_summary(bytes)?;
    Ok((
        json!({"schema_version":1,"kind":"m2","source_model_version":version,"units":"yards","axes":"raw WoW model space",
        "vertices":vertices,"skins":skins,"bones":bones,"animations":animations,"global_sequence_bones":globals,
        "global_sequence_periods_ms":model.global_sequences,"animation_lookup":model.animation_lookup,
        "playable_animation_lookup":fallback,"textures":textures,"materials":materials,
        "texture_lookup":model.raw_data.texture_lookup_table,"attachments":attachments,"attachment_lookup":model.attach_lookup,
        "material_animation":{"colors_rgb":model.color_rgb_tracks.iter().map(vec_track).collect::<Vec<_>>(),
            "colors_alpha":model.color_alpha_tracks.iter().map(scalar_track).collect::<Vec<_>>(),
            "transparency":model.transparency_tracks.iter().map(scalar_track).collect::<Vec<_>>()},
        "unsupported_render_features":{"particle_emitters":summary.particle_emitter_count,"ribbon_emitters":summary.ribbon_emitter_count},
        "raw_retained":true}),
        dependencies,
    ))
}

fn vec_track(t: &benilla_m2::M2Vec3Track) -> Value {
    json!({"interpolation":t.interp,"global_sequence":t.gseq,"ranges":t.ranges,"keys_ms":t.keys})
}
fn scalar_track(t: &benilla_m2::M2ScalarTrack) -> Value {
    json!({"interpolation":t.interp,"global_sequence":t.gseq,"ranges":t.ranges,"keys_ms":t.keys})
}
fn u16_at(b: &[u8], p: usize) -> Option<u16> {
    Some(u16::from_le_bytes(b.get(p..p + 2)?.try_into().ok()?))
}
fn u32_at(b: &[u8], p: usize) -> Option<u32> {
    Some(u32::from_le_bytes(b.get(p..p + 4)?.try_into().ok()?))
}
