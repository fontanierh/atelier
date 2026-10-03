use anyhow::Result;
use benilla_wmo::{parse_wmo, ParsedWmo};
use serde_json::{json, Value};
use std::io::Cursor;

pub fn wmo(name: &str, bytes: &[u8]) -> Result<(Value, Vec<String>)> {
    match parse_wmo(&mut Cursor::new(bytes))? {
        ParsedWmo::Root(root) => {
            let details = benilla_formats::parse_wmo_root(bytes)?;
            let mut deps = root.textures.clone();
            let stem = name.strip_suffix(".wmo").unwrap_or(name);
            deps.extend((0..root.n_groups).map(|i| format!("{stem}_{i:03}.wmo")));
            deps.extend(details.doodads().iter().map(|d| d.model.clone()));
            let materials: Vec<_> = root.materials.iter().map(|m| json!({"flags":m.flags,"blend_mode":m.blend_mode,
                "texture_index":m.get_texture1_index(&root.texture_offset_index_map),"ground_type":m.ground_type,
                "emission_rgb":m.sidn_rgb,"diffuse_rgb":m.diff_color})).collect();
            let doodads: Vec<_> = details.doodads().iter().enumerate().map(|(i,d)| json!({"index":i,"model":d.model,
                "position":d.position,"orientation_xyzw":d.orientation,"scale":d.scale,"color_rgba":d.color})).collect();
            let sets: Vec<_> = details
                .doodad_sets()
                .iter()
                .map(|s| json!({"start":s.start,"count":s.count}))
                .collect();
            let groups: Vec<_> = details.group_infos().iter().map(|g| json!({"interior":g.interior,"show_skybox":g.show_skybox,"bounds_min":g.bbox_min,"bounds_max":g.bbox_max})).collect();
            let portals = details.portals();
            let portal_planes: Vec<_> = portals
                .infos
                .iter()
                .map(|p| json!({"start_vertex":p.start_vertex,"count":p.count,"plane":p.plane}))
                .collect();
            let portal_refs: Vec<_> = portals
                .refs
                .iter()
                .map(|p| json!({"portal":p.portal,"group":p.group,"side":p.side}))
                .collect();
            if let Some(skybox) = details.skybox() {
                deps.push(skybox.into());
            }
            Ok((
                json!({"schema_version":1,"kind":"wmo_root","group_count":root.n_groups,"textures":root.textures,
                "materials":materials,"doodads":doodads,"doodad_sets":sets,"groups":groups,
                "portals":{"vertices":portals.vertices,"planes":portal_planes,"references":portal_refs}}),
                deps,
            ))
        }
        ParsedWmo::Group(g) => {
            let positions: Vec<_> = g.vertex_positions.iter().map(|p| [p.x, p.y, p.z]).collect();
            let normals: Vec<_> = g.vertex_normals.iter().map(|p| [p.x, p.y, p.z]).collect();
            let uvs: Vec<_> = g.texture_coords.iter().map(|p| [p.u, p.v]).collect();
            let colors: Vec<_> = g
                .vertex_colors
                .iter()
                .map(|p| [p.r, p.g, p.b, p.a])
                .collect();
            let batches: Vec<_> = g
                .render_batches
                .iter()
                .map(|b| json!({"start":b.start_index,"count":b.count,"material":b.material_id}))
                .collect();
            let collision: Vec<_> = g
                .material_info
                .iter()
                .map(|m| [m.flags, m.material_id])
                .collect();
            let liquid = g.liquid.as_ref().map(|l| json!({"xverts":l.xverts,"yverts":l.yverts,"xtiles":l.xtiles,"ytiles":l.ytiles,
                "base":l.base,"heights":l.heights,"opacity":l.opacity,"tile_flags":l.tile_flags,"material":l.material_id}));
            Ok((
                json!({"schema_version":1,"kind":"wmo_group","flags":g.flags,"positions":positions,"normals":normals,
                "uvs":uvs,"vertex_colors_rgba":colors,"indices":g.vertex_indices,"batches":batches,
                "triangle_flags_material":collision,"liquid":liquid,"group_liquid":g.group_liquid}),
                vec![],
            ))
        }
    }
}

pub fn adt(bytes: &[u8]) -> Result<(Value, Vec<String>)> {
    let tile = benilla_formats::adt_to_tile_mesh(bytes)?;
    let mut deps = Vec::new();
    let chunks: Vec<_> = tile.chunks.iter().map(|c| {
        if let Some(t) = &c.base_texture { deps.push(t.clone()); }
        deps.extend(c.layer_textures.clone());
        json!({"index":[c.index_x,c.index_y],"area_id":c.area_id,"positions":c.positions,"normals":c.normals,"uvs":c.uvs,
            "indices":c.indices,"holes":c.holes,"impassable":c.impassable,"base_texture":c.base_texture,
            "layer_textures":c.layer_textures,"layer_effect_ids":c.layer_effect_ids,"alpha_map":c.alpha_map,
            "shadow":c.shadow,"liquid_count":c.liquids.len(),"liquid_geometry":"retained in raw ADT"})
    }).collect();
    let doodads: Vec<_> = tile.doodads.iter().map(|d| {
        deps.push(d.model.clone());
        json!({"model":d.model,"position":d.position,"rotation_degrees":d.rotation,"scale":d.scale,"unique_id":d.unique_id})
    }).collect();
    let wmos: Vec<_> = tile.wmos.iter().map(|w| {
        deps.push(w.model.clone());
        json!({"model":w.model,"position":w.position,"rotation_degrees":w.rotation,"unique_id":w.unique_id,
            "doodad_set":w.doodad_set,"name_set":w.name_set})
    }).collect();
    Ok((
        json!({"schema_version":1,"kind":"adt","units":"yards","axes":"raw WoW world space",
        "chunks":chunks,"doodads":doodads,"wmos":wmos}),
        deps,
    ))
}
