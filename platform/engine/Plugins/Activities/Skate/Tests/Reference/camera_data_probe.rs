//! Frozen original stock shot decoder and verbatim centered shake exporter.
#![allow(dead_code)]
#[path = "../../crates/skate-host/src/camera/shot_data.rs"] mod shot_data;
#[path = "../../crates/skate-host/src/camera/stock_names.rs"] mod stock_names;
// The checker inserts only frozen declaration/from_rows/parse slices here.
// Each exact boundary and source/body hash is recorded before the guarded build.
// @CENTERED_SHAKE_MODULES@
use skate_core::camera::{ShotDatabase, ShotDefinition};
use skate_data::collections::Collections;
use serde_json::{json, Value};

fn shot_value(d: &ShotDefinition) -> Value {
    let s = &d.shot;
    json!({"name":d.name,"shot_type":d.shot_type,
        "shot":{"distance":s.distance.to_bits(),"lens_length":s.lens_length.to_bits(),
            "smoothing":s.smoothing.map(f32::to_bits),"reference_weights":s.reference_weights.map(f32::to_bits),
            "board_offset":s.board_offset.to_bits(),"position_heading":s.position_heading.to_bits(),
            "position_elevation":s.position_elevation.to_bits(),"framing":s.framing.map(f32::to_bits),
            "follow_subject_in_air":s.follow_subject_in_air,"mirror_for_stance":s.mirror_for_stance,
            "snap_to_reference_point":s.snap_to_reference_point,"use_previous_shot":s.use_previous_shot,
            "use_drop_predictor":s.use_drop_predictor,"use_free_camera_stick":s.use_free_camera_stick,
            "avoidance_override":s.avoidance_override,"blur":s.blur.to_bits(),
            "transition_blur":s.transition_blur.to_bits(),"subject_opacity":s.subject_opacity.to_bits(),
            "collision_hint":s.collision_hint,"anchor":s.anchor,"compass_north":s.compass_north,
            "world_heading":s.world_heading.to_bits(),"arm_orientation":s.arm_orientation.map(f32::to_bits),
            "camera_orientation":s.camera_orientation.map(f32::to_bits)},
        "transition_time":d.transition_time.to_bits(),"transition_units":d.transition_units,
        "children":d.children,"blend_points":d.blend_points.map(f32::to_bits),
        "blend_value":d.blend_value.to_bits(),"blend_type":d.blend_type,"blend_smoothing":d.blend_smoothing.to_bits()})
}
fn word(out: &mut Vec<u8>, value: u32) { out.extend(value.to_le_bytes()); }
fn float(out: &mut Vec<u8>, value: f32) { word(out, value.to_bits()); }
fn string(out: &mut Vec<u8>, value: &str) { word(out, value.len() as u32); out.extend(value.as_bytes()); }
fn definition(out: &mut Vec<u8>, d: &ShotDefinition) {
    string(out, &d.name); word(out, d.shot_type); let s=&d.shot;
    float(out,s.distance); float(out,s.lens_length);
    for v in s.smoothing { float(out,v); } for v in s.reference_weights { float(out,v); }
    for v in [s.board_offset,s.position_heading,s.position_elevation] { float(out,v); }
    for v in s.framing { float(out,v); }
    for v in [s.follow_subject_in_air,s.mirror_for_stance,s.snap_to_reference_point,s.use_previous_shot,
        s.use_drop_predictor,s.use_free_camera_stick,s.avoidance_override] { word(out,u32::from(v)); }
    for v in [s.blur,s.transition_blur,s.subject_opacity] { float(out,v); }
    for v in [s.collision_hint,s.anchor,s.compass_north] { word(out,v); }
    float(out,s.world_heading); for v in s.arm_orientation { float(out,v); } for v in s.camera_orientation { float(out,v); }
    float(out,d.transition_time); word(out,d.transition_units);
    for child in &d.children { word(out,u32::from(child.is_some())); if let Some(child)=child { string(out,child); } }
    for v in d.blend_points { float(out,v); } float(out,d.blend_value); word(out,d.blend_type); float(out,d.blend_smoothing);
}
fn run() -> Result<(),String> {
    let args:Vec<_>=std::env::args().collect(); let root=std::path::Path::new(&args[1]);
    let output=std::path::Path::new(&args[2]); let identity=&args[3];
    let collections=Collections::load(root)?; let database=shot_data::StockShots::from_collections(&collections)?;
    let mut names:Vec<_>=collections.entries().iter().filter(|c|c.class_name=="camera_shots")
        .map(|c|c.key.to_ascii_lowercase()).collect(); names.sort();
    let definitions:Vec<_>=names.iter().map(|name|database.load(name)).collect::<Result<_,_>>()?;
    let samples:[centered_shake::ShakeSamples;2]=["1.shk","2.shk"].map(|name| {
        let raw=std::fs::read_to_string(root.join("private/stock/data/camera").join(name)).map_err(|e|e.to_string())?;
        centered_shake_data::parse(&raw)
    }).into_iter().collect::<Result<Vec<_>,_>>()?.try_into().unwrap();
    let value=json!({"version":1,"source_identity":identity,"shots":definitions.iter().map(shot_value).collect::<Vec<_>>(),
        "shakes":samples.iter().map(|s|json!({"rotations":s.rotations.iter().map(|v|v.map(f32::to_bits)).collect::<Vec<_>>(),
            "translations":s.translations.iter().map(|v|v.map(f32::to_bits)).collect::<Vec<_>>()})).collect::<Vec<_>>()});
    std::fs::write(output.with_extension("json"),serde_json::to_vec_pretty(&value).map_err(|e|e.to_string())?).map_err(|e|e.to_string())?;
    let mut raw=b"ATCAM001".to_vec(); string(&mut raw,identity); word(&mut raw,definitions.len() as u32);
    for d in &definitions { definition(&mut raw,d); }
    for s in &samples { word(&mut raw,s.rotations.len() as u32);
        for (rotation,translation) in s.rotations.iter().zip(&s.translations) {
            for v in rotation {float(&mut raw,*v);} for v in translation {float(&mut raw,*v);}
        }
    }
    std::fs::write(output.with_extension("raw"),raw).map_err(|e|e.to_string())?;
    Ok(())
}
fn main() { if let Err(error)=run() {eprintln!("{error}");std::process::exit(2);} }
