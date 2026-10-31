//! ATCAM001 shot fields are already in radians and shake samples already centered.
//! Read their stored words directly: no degree conversion, defaults or second centering.
use crate::core::camera::{ShakeSamples, Shot, ShotDefinition};
use hakuba_skate_schema::{Error, Reader};
use std::collections::BTreeSet;

#[derive(Clone, Debug, PartialEq)]
pub struct CameraData {
    pub source_identity: String,
    pub shots: Vec<ShotDefinition>,
    pub shakes: [ShakeSamples; 2],
}
pub fn from_bytes(bytes: &[u8]) -> Result<CameraData, String> {
    decode(bytes).map_err(|e| e.to_string())
}
fn floats<const N: usize>(r: &mut Reader<'_>) -> Result<[f32; N], Error> {
    let mut values = [0.0; N];
    for value in &mut values {
        *value = r.float()?;
    }
    Ok(values)
}
fn flag(r: &mut Reader<'_>) -> Result<u8, Error> {
    u8::try_from(r.word()?).map_err(|_| Error("camera flag exceeds one byte".into()))
}
fn shake(r: &mut Reader<'_>) -> Result<ShakeSamples, Error> {
    let count = r.word()? as usize;
    if count == 0 || count > r.remaining() / 32 {
        return Err(Error("invalid camera shake sample count".into()));
    }
    let mut rotations = Vec::with_capacity(count);
    let mut translations = Vec::with_capacity(count);
    for _ in 0..count {
        rotations.push(floats(r)?);
        translations.push(floats(r)?);
    }
    Ok(ShakeSamples::from_centered(rotations, translations))
}
fn decode(bytes: &[u8]) -> Result<CameraData, Error> {
    let mut r = Reader::new(bytes, b"ATCAM001")?;
    let source_identity = r.string()?.to_owned();
    let count = r.word()? as usize;
    if count > r.remaining() / 8 {
        return Err(Error("invalid camera shot count".into()));
    }
    let mut shots = Vec::with_capacity(count);
    let mut names = BTreeSet::new();
    for _ in 0..count {
        let name = r.string()?.to_owned();
        let shot_type = r.word()?;
        let shot = Shot {
            distance: r.float()?,
            lens_length: r.float()?,
            smoothing: floats(&mut r)?,
            reference_weights: floats(&mut r)?,
            board_offset: r.float()?,
            position_heading: r.float()?,
            position_elevation: r.float()?,
            framing: floats(&mut r)?,
            follow_subject_in_air: flag(&mut r)?,
            mirror_for_stance: flag(&mut r)?,
            snap_to_reference_point: flag(&mut r)?,
            use_previous_shot: flag(&mut r)?,
            use_drop_predictor: flag(&mut r)?,
            use_free_camera_stick: flag(&mut r)?,
            avoidance_override: flag(&mut r)?,
            blur: r.float()?,
            transition_blur: r.float()?,
            subject_opacity: r.float()?,
            collision_hint: r.word()?,
            anchor: r.word()?,
            compass_north: r.word()?,
            world_heading: r.float()?,
            arm_orientation: floats(&mut r)?,
            camera_orientation: floats(&mut r)?,
        };
        let transition_time = r.float()?;
        let transition_units = r.word()?;
        let mut children = [None, None, None];
        for child in &mut children {
            *child = match r.word()? {
                0 => None,
                1 => Some(r.string()?.to_owned()),
                _ => return Err(Error("invalid camera child presence flag".into())),
            };
        }
        let definition = ShotDefinition {
            name,
            shot_type,
            shot,
            transition_time,
            transition_units,
            children,
            blend_points: floats(&mut r)?,
            blend_value: r.float()?,
            blend_type: r.word()?,
            blend_smoothing: r.float()?,
        };
        if !names.insert(definition.name.clone()) {
            return Err(Error("duplicate camera shot".into()));
        }
        shots.push(definition);
    }
    for shot in &shots {
        for child in shot.children.iter().flatten() {
            if !names.contains(child) {
                return Err(Error(format!("camera shot {} references missing shot {child}", shot.name)));
            }
        }
    }
    let shakes = [shake(&mut r)?, shake(&mut r)?];
    r.end()?;
    Ok(CameraData { source_identity, shots, shakes })
}
